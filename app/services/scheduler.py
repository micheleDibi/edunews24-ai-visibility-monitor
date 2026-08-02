"""Schedulazione: il ciclo orario e il job notturno di manutenzione.

APScheduler `AsyncIOScheduler` avviato nel lifespan di FastAPI, un solo
processo. Tre impostazioni non sono opzionali:

* `max_instances=1` — un ciclo che dura piu' di un'ora non deve accavallarsi
  con il successivo, altrimenti due lotti competono per lo stesso budget e per
  gli stessi semafori di provider;
* `misfire_grace_time` — un'esecuzione in ritardo oltre la soglia si salta
  invece di partire fuori tempo massimo;
* la regola trasversale: OGNI modo di saltare o fallire un ciclo lascia una
  riga in `runs` — dal job stesso, dai listener sugli eventi di APScheduler, o
  dal marcatore d'avvio per le ore in cui il processo era spento. Un'ora senza
  riga in produzione e' costata un pomeriggio di diagnosi: mai piu'.

## Il minuto 7

Il cron gira al minuto 7 e non allo scoccare dell'ora. Allo zero ci va tutto il
mondo, e i rate limit dei provider si sentono. Non e' una tecnica di
occultamento: e' non mettersi in coda inutilmente.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import structlog
from apscheduler.events import EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Probe, Run
from app.services import retention, rollup, runner
from app.services.topics_sync import sync_topics

log = structlog.get_logger(__name__)

ID_CICLO_ORARIO = "ciclo_orario"
ID_MANUTENZIONE = "manutenzione_notturna"

# Un ciclo in ritardo di piu' di 10 minuti si salta: partire alle 08:20 il lotto
# delle 08:07 sposta la misura senza aggiungere informazione.
GRAZIA_MISFIRE_S = 600

# Quanto un singolo ciclo puo' superare la quota nominale quando recupera ore
# perdute. Senza tetto, un container spento dalle 00 alle 20 farebbe partire alle
# 20:07 un lotto con l'intero budget del giorno: costo concentrato in un'ora e
# campione tutto nella stessa fascia oraria, cioe' il contrario di una misura
# distribuita.
FATTORE_RECUPERO = 2

# Tetto duro alla durata di un ciclo. Un ciclo normale dura minuti; uno che
# arriva qui e' bloccato (connessione morta senza timeout, DB appeso) e va
# interrotto d'ufficio, perche' con `max_instances=1` ogni ora in cui resta
# appeso fa scartare il fire successivo — e APScheduler non lo ritenta mai.
# In produzione e' costato pomeriggi interi di ore senza misure.
TETTO_DURATA_CICLO_S = 45 * 60


async def query_usate_oggi(
    session: AsyncSession, settings: Settings, *, adesso: datetime | None = None
) -> int:
    """Query DISTINTE gia' sondate oggi, nel fuso configurato.

    Il budget della specifica e' in query distinte, non in probe: la stessa
    domanda mandata a quattro provider conta uno.
    """
    adesso = adesso or datetime.now(ZoneInfo(settings.tz))
    inizio = adesso.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        await session.execute(
            select(func.count(func.distinct(Probe.query_id))).where(Probe.created_at >= inizio)
        )
    ).scalar_one()


async def quante_query_ora(
    session: AsyncSession, settings: Settings, *, adesso: datetime | None = None
) -> int:
    """Dimensione del lotto di questa ora. Il budget si spalma sulle ore che
    restano, non si consuma a ritmo fisso finche' finisce.

    La versione precedente prendeva `ceil(budget/24)` e lo ripeteva identico
    fino a esaurimento. Con 200 query al giorno sono 9 all'ora, ma 9 x 24 fa
    216: il budget si esaurisce PRIMA della fine del giorno. Il risultato, in
    produzione, era il ciclo delle 22:07 con 2 query invece di 9 e quello delle
    23:07 saltato del tutto — una fascia oraria senza misure, ogni giorno, che
    nei dati sembra assenza di attivita' dei motori e invece e' un difetto di
    aritmetica.

    Dividere per le ore che mancano rende la copertura h24 una proprieta' della
    formula e non una speranza: a ogni ora si ridistribuisce cio' che resta, e
    l'ultima ora del giorno riceve sempre qualcosa. Si autocorregge anche
    all'indietro, perche' un ciclo saltato lascia piu' budget a quelli dopo.

    Limite dichiarato: sotto le 24 query al giorno la copertura oraria completa
    e' impossibile per costruzione — non si possono coprire 24 ore con meno di
    24 domande — e il lotto minimo di 1 fa consumare il budget nelle prime ore.
    Chi vuole misure a tutte le ore deve tenere DAILY_QUERY_BUDGET >= 24.
    """
    adesso = adesso or datetime.now(ZoneInfo(settings.tz))
    usate = await query_usate_oggi(session, settings, adesso=adesso)
    rimanenti = settings.daily_query_budget - usate
    if rimanenti <= 0:
        return 0

    ore_rimaste = 24 - adesso.hour  # inclusa quella corrente
    nominale = math.ceil(settings.daily_query_budget / 24)
    return max(0, min(math.ceil(rimanenti / ore_rimaste), rimanenti, nominale * FATTORE_RECUPERO))


def _riga_per_evento(evento: Any) -> tuple[str, str]:
    """Da un evento APScheduler di salto alla coppia (status, nota) della riga.

    Funzione pura, separata dal listener per essere testabile senza istanziare
    uno scheduler vero.
    """
    if evento.code == EVENT_JOB_MAX_INSTANCES:
        # JobSubmissionEvent: `scheduled_run_times` e' una lista (coalesce puo'
        # accorpare piu' fire in una submission sola).
        orari = ", ".join(f"{quando:%H:%M}" for quando in evento.scheduled_run_times)
        return (
            "skipped_overlap",
            f"saltato: il ciclo precedente era ancora in corso all'orario previsto ({orari}). "
            "APScheduler non ritenta i fire scartati per max_instances",
        )
    # JobExecutionEvent (EVENT_JOB_MISSED): `scheduled_run_time` singolare.
    return (
        "skipped_misfire",
        f"saltato: l'esecuzione delle {evento.scheduled_run_time:%H:%M} e' arrivata "
        f"oltre il tempo di grazia di {GRAZIA_MISFIRE_S // 60} minuti (processo bloccato)",
    )


# I task creati dai listener: senza un riferimento, il garbage collector puo'
# cancellarli a meta' scrittura.
_compiti_listener: set[asyncio.Task[None]] = set()


async def _scrivi_riga_di_salto(
    fabbrica: async_sessionmaker[AsyncSession], stato: str, nota: str
) -> None:
    try:
        # Un minuto di tetto anche qui: durante una partizione di rete questi
        # task si accumulerebbero appesi, uno per ogni ora saltata.
        async with asyncio.timeout(60), fabbrica() as session:
            session.add(Run(status=stato, kind="hourly", finished_at=func.now(), notes=nota))
            await session.commit()
        log.warning("ciclo saltato dallo scheduler", stato=stato, nota=nota)
    except Exception:
        log.exception("impossibile registrare il ciclo saltato", stato=stato)


async def attendi_compiti_listener(timeout: float = 5.0) -> None:
    """Allo shutdown: da' ai task dei listener il tempo di finire la scrittura.

    Senza quest'attesa, `scheduler.shutdown` seguito da `dispose_engine` puo'
    troncare la riga `skipped_overlap`/`skipped_misfire` in volo.
    """
    if _compiti_listener:
        await asyncio.wait(set(_compiti_listener), timeout=timeout)


async def segna_cicli_persi(
    session: AsyncSession, settings: Settings, *, adesso: datetime | None = None
) -> int:
    """All'avvio: le ore di ciclo trascorse senza ALCUNA riga diventano una
    riga `skipped_offline` che le conta ed elenca.

    Con il jobstore in memoria APScheduler non sa nulla dei fire persi mentre
    il processo era spento: al riavvio il job rinasce vuoto e il prossimo fire
    e' calcolato SOLO in avanti, senza log ne' eventi (verificato sul codice di
    APScheduler 3.11, `schedulers/base.py`: `trigger.get_next_fire_time(None,
    now)`). Vale anche per un fire mancato da pochi secondi: non esiste nessun
    recupero, nemmeno dentro il tempo di grazia, perche' non c'e' nessun fire
    pendente da coalizzare. Percio' si conta perso OGNI minuto 7 attraversato
    fino ad `adesso` — questa funzione gira prima di `scheduler.start()`,
    quindi non puo' contare un fire che verra' ancora eseguito.

    Imprecisioni note e accettate: nella notte del cambio d'ora il conteggio
    puo' sbagliare di uno, e un avvio che attraversa esattamente un minuto 7
    (questa funzione gira alle HH:06:59, lo scheduler parte alle HH:07:01) puo'
    perdere quel fire senza contarlo.
    """
    fuso = ZoneInfo(settings.tz)
    adesso = (adesso or datetime.now(fuso)).astimezone(fuso)
    ultimo = (await session.execute(select(func.max(Run.started_at)))).scalar_one_or_none()
    if ultimo is None:
        return 0  # primo avvio in assoluto: nessuna storia, quindi nessun buco

    candidato = ultimo.astimezone(fuso).replace(minute=7, second=0, microsecond=0)
    if candidato <= ultimo.astimezone(fuso):
        candidato += timedelta(hours=1)

    persi: list[datetime] = []
    while candidato <= adesso:
        persi.append(candidato)
        candidato += timedelta(hours=1)
    if not persi:
        return 0

    if len(persi) == 1:
        dettaglio = f"il ciclo delle {persi[0]:%H:%M} del {persi[0]:%d/%m} non e' mai partito"
    else:
        dettaglio = (
            f"{len(persi)} cicli mai partiti, dalle {persi[0]:%H:%M} del {persi[0]:%d/%m} "
            f"alle {persi[-1]:%H:%M} del {persi[-1]:%d/%m}"
        )
    session.add(
        Run(
            status="skipped_offline",
            kind="hourly",
            finished_at=func.now(),
            notes=f"servizio fermo: {dettaglio}",
        )
    )
    await session.commit()
    log.warning(
        "cicli persi durante il fermo",
        quanti=len(persi),
        dal=str(persi[0]),
        al=str(persi[-1]),
    )
    return len(persi)


async def riconcilia_run_interrotti(session: AsyncSession) -> int:
    """Chiude i `runs` rimasti `running` da un processo ucciso.

    Senza, un container riavviato a metà ciclo lascerebbe per sempre una riga
    "in corso" e la pagina di stato mostrerebbe un'esecuzione che non esiste.
    """
    risultato = await session.execute(
        update(Run)
        .where(Run.status == "running")
        .values(
            status="failed",
            finished_at=func.now(),
            notes="chiuso all'avvio: il processo precedente e' stato interrotto",
        )
    )
    quanti = cast("CursorResult[Any]", risultato).rowcount or 0
    await session.commit()
    if quanti:
        log.warning("run interrotti chiusi all'avvio", quanti=quanti)
    return quanti


async def job_ciclo_orario(fabbrica: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Il ciclo orario. Regola unica: QUALUNQUE esito lascia una riga in `runs`.

    Meta' delle ore di un giorno di produzione e' sparita senza traccia perche'
    i fallimenti prima della creazione del run e i cicli rimasti appesi non
    scrivevano niente. Ogni ramo di questo job — saltato, fallito prima di
    partire, interrotto per durata — ora scrive la propria riga.
    """
    tetto: asyncio.Timeout | None = None
    try:
        # Il tetto avvolge TUTTO il corpo, pre-check compreso: lo scenario che
        # lo motiva — una connessione al DB rimasta appesa — puo' colpire
        # `quante_query_ora` esattamente come il ciclo vero, e un job appeso
        # li' fuori dal tetto bloccherebbe per sempre tutte le ore successive.
        async with asyncio.timeout(TETTO_DURATA_CICLO_S) as tetto:
            async with fabbrica() as session:
                quante = await quante_query_ora(session, settings)
                if quante == 0:
                    # Il salto si SCRIVE, non si logga soltanto: un'ora senza
                    # riga e' indistinguibile da un servizio fermo.
                    motivo = (
                        f"budget di query esaurito: {settings.daily_query_budget} "
                        "query gia' sondate oggi"
                    )
                    session.add(
                        Run(
                            status="skipped_budget",
                            kind="hourly",
                            finished_at=func.now(),
                            notes=motivo,
                        )
                    )
                    await session.commit()
                    log.info("ciclo saltato", motivo=motivo, budget=settings.daily_query_budget)
                    return

            async with fabbrica() as session:
                await runner.esegui_ciclo(session, quante=quante, kind="hourly", settings=settings)
    except TimeoutError as exc:
        if tetto is not None and tetto.expired():
            # Il NOSTRO tetto: il ciclo era bloccato, la cancellazione lo ha
            # interrotto e la sua eventuale riga `running` va chiusa qui.
            log.error(
                "ciclo orario interrotto: oltre il tetto di durata",
                tetto_min=TETTO_DURATA_CICLO_S // 60,
            )
            nota = (
                f"interrotto d'ufficio dopo {TETTO_DURATA_CICLO_S // 60} minuti: "
                "il ciclo era bloccato e avrebbe fatto saltare le ore successive"
            )
        else:
            # Un TimeoutError altrui (driver, pool): e' un fallimento comune e
            # non va raccontato come intervento del tetto.
            log.exception("ciclo orario fallito")
            nota = f"ciclo fallito: TimeoutError: {exc}"[:500]
        await _lascia_traccia_fallimento(fabbrica, nota)
    except Exception as exc:
        # Un'eccezione qui non deve uccidere lo scheduler: il ciclo successivo
        # deve poter partire comunque. La traccia si scrive SEMPRE, senza
        # provare a indovinare se `esegui_ciclo` ha gia' chiuso la sua riga:
        # `_lascia_traccia_fallimento` controlla da solo e non duplica.
        log.exception("ciclo orario fallito")
        await _lascia_traccia_fallimento(
            fabbrica, f"ciclo fallito: {type(exc).__name__}: {exc}"[:500]
        )


# Finestra entro cui una riga si considera «di questo ciclo». Piu' larga della
# grazia di misfire, molto piu' stretta di un'ora: distingue la riga appena
# creata da una `running` stantia di ore prima, la cui storia non va riscritta.
FINESTRA_TRACCIA_S = 15 * 60


async def _lascia_traccia_fallimento(fabbrica: async_sessionmaker[AsyncSession], nota: str) -> None:
    """Garantisce che il ciclo appena fallito abbia una riga chiusa.

    Tre casi, in ordine: la riga `running` recente del ciclo interrotto si
    chiude con la nota; se non c'e' ma una riga recente esiste gia' (il runner
    l'ha chiusa da solo prima di rilanciare l'eccezione), non si scrive nulla;
    se non esiste proprio — il fallimento e' avvenuto prima di crearla, o il
    suo commit e' fallito — se ne inserisce una nuova. Le righe `running` piu'
    vecchie della finestra restano com'erano: sono un'altra storia, e
    intestargli la nota di quest'ora riscriverebbe il passato
    (`riconcilia_run_interrotti` le sistema al riavvio).
    """
    try:
        async with asyncio.timeout(60):
            soglia = datetime.now(UTC) - timedelta(seconds=FINESTRA_TRACCIA_S)
            async with fabbrica() as session:
                risultato = await session.execute(
                    update(Run)
                    .where(
                        Run.status == "running",
                        Run.kind == "hourly",
                        Run.started_at >= soglia,
                    )
                    .values(status="failed", finished_at=func.now(), notes=nota)
                )
                if not (cast("CursorResult[Any]", risultato).rowcount or 0):
                    gia_scritta = (
                        await session.execute(
                            select(func.count())
                            .select_from(Run)
                            .where(Run.kind == "hourly", Run.started_at >= soglia)
                        )
                    ).scalar_one()
                    if not gia_scritta:
                        session.add(
                            Run(
                                status="failed",
                                kind="hourly",
                                finished_at=func.now(),
                                notes=nota,
                            )
                        )
                await session.commit()
    except Exception:
        # Se nemmeno questo riesce (con il suo tetto di un minuto) il database
        # e' irraggiungibile: resta il log. Ore cosi' non sono ricostruibili
        # nemmeno a posteriori — senza database non si scrive da nessuna parte.
        log.exception("impossibile scrivere la riga del ciclo fallito")


async def job_manutenzione(fabbrica: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Rollup, risincronizzazione dei topic e potatura. In quest'ordine.

    Il rollup viene prima: se il sync o la potatura falliscono, gli aggregati
    del giorno appena chiuso sono comunque scritti.
    """
    async with fabbrica() as session:
        for nome, azione in (
            ("rollup", lambda: rollup.ricalcola(session, settings=settings)),
            ("sync_topics", lambda: sync_topics(session, full=True, settings=settings)),
            ("retention", lambda: retention.pota(session, settings=settings)),
        ):
            try:
                await azione()
            except Exception:
                log.exception("job di manutenzione fallito", passo=nome)


def crea_scheduler(
    fabbrica: async_sessionmaker[AsyncSession], settings: Settings
) -> AsyncIOScheduler:
    fuso = ZoneInfo(settings.tz)
    scheduler = AsyncIOScheduler(timezone=fuso)

    scheduler.add_job(
        job_ciclo_orario,
        CronTrigger(minute=7, timezone=fuso),
        args=[fabbrica, settings],
        id=ID_CICLO_ORARIO,
        name="lotto di probe orario",
        # `coalesce=False` di proposito: con la grazia di 10 minuti su un job
        # orario al massimo UN fire arretrato puo' essere ancora eseguibile,
        # quindi la semantica di esecuzione non cambia. Cambia la traccia: con
        # True i fire accumulati da un loop bloccato venivano accorpati PRIMA
        # del controllo di misfire e sparivano senza evento; con False ognuno
        # passa dal controllo, emette EVENT_JOB_MISSED e lascia la sua riga.
        coalesce=False,
        max_instances=1,
        misfire_grace_time=GRAZIA_MISFIRE_S,
        replace_existing=True,
    )
    scheduler.add_job(
        job_manutenzione,
        CronTrigger(hour=3, minute=20, timezone=fuso),
        args=[fabbrica, settings],
        id=ID_MANUTENZIONE,
        name="rollup, sync topic e potatura",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )

    def su_ciclo_saltato(evento: Any) -> None:
        """Un fire scartato da APScheduler diventa una riga, non solo un log.

        `max_instances=1` scarta il fire se il ciclo precedente e' ancora in
        corso; la grace scaduta lo scarta se il processo era bloccato. In
        entrambi i casi APScheduler emette un evento e passa oltre: senza
        questa scrittura l'ora sparirebbe dalla dashboard. Il listener e'
        sincrono e gira nel thread dell'event loop (garantito da
        AsyncIOScheduler), quindi `get_running_loop` qui e' sicuro.
        """
        if evento.job_id != ID_CICLO_ORARIO:
            return
        stato, nota = _riga_per_evento(evento)
        compito = asyncio.get_running_loop().create_task(
            _scrivi_riga_di_salto(fabbrica, stato, nota)
        )
        _compiti_listener.add(compito)
        compito.add_done_callback(_compiti_listener.discard)

    scheduler.add_listener(su_ciclo_saltato, EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)
    return scheduler


def prossime_esecuzioni(scheduler: AsyncIOScheduler | None) -> dict[str, str | None]:
    if scheduler is None or not scheduler.running:
        return {}
    return {
        job.id: job.next_run_time.isoformat() if job.next_run_time else None
        for job in scheduler.get_jobs()
    }
