"""Schedulazione: il ciclo orario e il job notturno di manutenzione.

APScheduler `AsyncIOScheduler` avviato nel lifespan di FastAPI, un solo
processo. Tre impostazioni non sono opzionali:

* `max_instances=1` — un ciclo che dura piu' di un'ora non deve accavallarsi
  con il successivo, altrimenti due lotti competono per lo stesso budget e per
  gli stessi semafori di provider;
* `coalesce=True` — se il processo e' stato giu' per tre ore, al ritorno si
  esegue UN ciclo, non tre di fila;
* `misfire_grace_time` — un'esecuzione in ritardo oltre la soglia si salta
  invece di partire fuori tempo massimo.

## Il minuto 7

Il cron gira al minuto 7 e non allo scoccare dell'ora. Allo zero ci va tutto il
mondo, e i rate limit dei provider si sentono. Non e' una tecnica di
occultamento: e' non mettersi in coda inutilmente.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import structlog
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
    async with fabbrica() as session:
        quante = await quante_query_ora(session, settings)
        if quante == 0:
            # Il salto si SCRIVE, non si logga soltanto. Il tetto di spesa gia'
            # lasciava una riga `skipped_budget` visibile in «Ultimi cicli»;
            # questo ramo no, e l'ora mancante era indistinguibile da un
            # servizio fermo. Due modi diversi di saltare un ciclo devono
            # lasciare la stessa traccia, altrimenti la meta' invisibile e'
            # quella che fa perdere un pomeriggio a capire cosa sia successo.
            motivo = (
                f"budget di query esaurito: {settings.daily_query_budget} query gia' sondate oggi"
            )
            session.add(Run(status="skipped_budget", kind="hourly", notes=motivo))
            await session.commit()
            log.info("ciclo saltato", motivo=motivo, budget=settings.daily_query_budget)
            return
        try:
            await runner.esegui_ciclo(session, quante=quante, kind="hourly", settings=settings)
        except Exception:
            # Un'eccezione qui non deve uccidere lo scheduler: il ciclo
            # successivo deve poter partire comunque.
            log.exception("ciclo orario fallito")


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
        coalesce=True,
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
    return scheduler


def prossime_esecuzioni(scheduler: AsyncIOScheduler | None) -> dict[str, str | None]:
    if scheduler is None or not scheduler.running:
        return {}
    return {
        job.id: job.next_run_time.isoformat() if job.next_run_time else None
        for job in scheduler.get_jobs()
    }
