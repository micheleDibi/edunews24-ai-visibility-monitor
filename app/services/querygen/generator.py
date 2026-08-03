"""Orchestrazione del generatore: dal catalogo al lotto di query salvate.

Ordine dei passaggi, che non e' arbitrario:

1. selezione dei topic e composizione dei template;
2. validazione (brand, lunghezza, lingua);
3. deduplica sull'hash del TEMPLATE, che decide anche se una query esistente
   va riusata invece di crearne una nuova;
4. riscrittura LLM delle sole query nuove;
5. rivalidazione e ricontrollo dell'hash sul testo riscritto, con ripiego sul
   template se la riscrittura collide con qualcosa;
6. salvataggio.

Il punto 3 precede il 4 di proposito: le query verbatim (FAQ della redazione,
domande di categoria) hanno un hash stabile e vanno riconosciute come "gia'
viste" prima che una riscrittura le renda irriconoscibili. Il punto 5 esiste
perche' riscrivere cambia il testo e quindi cambia l'hash — e il ricontrollo
va fatto contro TUTTO il database, non solo contro gli hash dei template del
lotto: il modello normalizza domande simili nello stesso identico testo, e la
riscrittura di oggi finisce spesso addosso a una query di un giorno passato,
il cui hash non era fra quelli cercati. Senza questo controllo l'INSERT
esplodeva sul vincolo unico e l'intero ciclo orario falliva.

Il salvataggio usa comunque `ON CONFLICT DO NOTHING`: un ciclo manuale puo'
girare in parallelo a quello orario e inserire la stessa domanda fra il
controllo e l'INSERT. In quel caso la riga dell'altro ciclo si riusa, non si
fa fallire il lotto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import Query, Topic
from app.services.querygen import categories
from app.services.querygen.normalize import calcola_hash
from app.services.querygen.rewrite import Riscrittore, client_openai, riscrivi_lotto
from app.services.querygen.selection import ripartisci, seleziona_topic
from app.services.querygen.strategies import QueryCandidata, genera_per_topic
from app.services.querygen.validate import MotivoScarto, valida_testo

log = structlog.get_logger(__name__)

# Oltre questo numero di giri di riempimento si smette: se il catalogo non ha
# materiale, insistere produce solo carico sul database.
MAX_TENTATIVI = 3


@dataclass
class EsitoGenerazione:
    query: list[Query] = field(default_factory=list)
    nuove: int = 0
    riusate: int = 0
    scartate: dict[str, int] = field(default_factory=dict)
    composizione: dict[str, int] = field(default_factory=dict)
    riscrittura: str = "disattivata"
    tentativi: int = 0

    def scarta(self, motivo: str) -> None:
        self.scartate[motivo] = self.scartate.get(motivo, 0) + 1


@dataclass
class _Preparata:
    candidata: QueryCandidata
    hash_template: str
    esistente: Query | None = None


async def _faq_gia_usate(session: AsyncSession, topic_ids: list[int]) -> dict[int, set[int]]:
    """Quali FAQ sono gia' diventate query, per ciascun topic.

    Si ricava dalle `queries` esistenti invece di tenere un contatore su
    `topics`: lo stato ha una sola fonte di verita' e non puo' divergere.
    """
    if not topic_ids:
        return {}
    stmt = select(Query.topic_id, Query.source_faq_index).where(
        Query.topic_id.in_(topic_ids), Query.source_faq_index.is_not(None)
    )
    usate: dict[int, set[int]] = {}
    for topic_id, indice in (await session.execute(stmt)).all():
        usate.setdefault(topic_id, set()).add(indice)
    return usate


async def _righe_per_hash(session: AsyncSession, hashes: list[str]) -> dict[str, Query]:
    if not hashes:
        return {}
    stmt = select(Query).where(Query.text_hash.in_(hashes))
    return {q.text_hash: q for q in (await session.execute(stmt)).scalars().all()}


def _eseguita_di_recente(query: Query, adesso: datetime, giorni: int) -> bool:
    if query.last_run_at is None:
        return False
    return query.last_run_at > adesso - timedelta(days=giorni)


async def _candidate_categoria(
    session: AsyncSession, quante: int, adesso: datetime, giorni_dedup: int
) -> list[QueryCandidata]:
    """Domande di categoria, in rotazione dalla meno recente."""
    if quante <= 0:
        return []

    tutte = categories.tutte_le_domande()
    hashes = {domanda: calcola_hash(domanda) for _, domanda in tutte}
    esistenti = await _righe_per_hash(session, list(hashes.values()))

    def chiave(voce: tuple[str, str]) -> tuple[int, datetime]:
        riga = esistenti.get(hashes[voce[1]])
        if riga is None or riga.last_run_at is None:
            return (0, datetime.min.replace(tzinfo=UTC))
        return (1, riga.last_run_at)

    disponibili = [
        voce
        for voce in tutte
        if (riga := esistenti.get(hashes[voce[1]])) is None
        or not _eseguita_di_recente(riga, adesso, giorni_dedup)
    ]
    disponibili.sort(key=chiave)

    return [
        QueryCandidata(text=domanda, strategy="category", category_slug=slug)
        for slug, domanda in disponibili[:quante]
    ]


async def _avvisa_categorie_sconosciute(session: AsyncSession) -> None:
    """Se uno slug curato non esiste nel catalogo, la segmentazione e' sbagliata."""
    presenti = {
        slug
        for (slug,) in (
            await session.execute(
                select(Topic.category_slug).where(Topic.category_slug.is_not(None)).distinct()
            )
        ).all()
    }
    if not presenti:
        return
    ignote = sorted(set(categories.DOMANDE_PER_CATEGORIA) - presenti)
    if ignote:
        log.warning(
            "slug di categoria non presenti nel catalogo: le metriche per categoria "
            "non si aggregheranno con quelle dei topic",
            slug_ignoti=ignote,
            slug_nel_catalogo=sorted(presenti),
        )


async def genera_lotto(
    session: AsyncSession,
    count: int,
    *,
    settings: Settings | None = None,
    riscrittore: Riscrittore | None = None,
    adesso: datetime | None = None,
) -> EsitoGenerazione:
    settings = settings or get_settings()
    adesso = adesso or datetime.now(UTC)
    esito = EsitoGenerazione()
    if count <= 0:
        return esito

    await _avvisa_categorie_sconosciute(session)

    quote = ripartisci(
        count,
        {
            "fresh": settings.bucket_fresh_pct,
            "recent": settings.bucket_recent_pct,
            "archive": settings.bucket_archive_pct,
            "category": settings.bucket_category_pct,
        },
    )

    preparate: list[_Preparata] = []
    hash_nel_lotto: set[str] = set()
    topic_usati: set[int] = set()

    # --- domande di categoria -------------------------------------------
    for candidata in await _candidate_categoria(
        session, quote["category"], adesso, settings.query_dedup_window_days
    ):
        _prepara(candidata, preparate, hash_nel_lotto, esito, settings)

    # --- domande dai topic, con giri di riempimento ----------------------
    quote_topic = {b: quote[b] for b in ("fresh", "recent", "archive")}

    for tentativo in range(1, MAX_TENTATIVI + 1):
        esito.tentativi = tentativo
        mancanti = count - len(preparate)
        if mancanti <= 0:
            break

        richiesta = quote_topic if tentativo == 1 else ripartisci(mancanti, quote_topic)
        selezione = await seleziona_topic(session, richiesta, adesso=adesso, esclusi=topic_usati)
        if not selezione.topics:
            log.warning(
                "nessun topic disponibile per riempire il lotto",
                tentativo=tentativo,
                mancanti=mancanti,
            )
            break

        for bucket, quanti in selezione.composizione.items():
            esito.composizione[bucket] = esito.composizione.get(bucket, 0) + quanti

        faq_usate = await _faq_gia_usate(session, [t.id for t in selezione.topics])
        for topic in selezione.topics:
            topic_usati.add(topic.id)
            if len(preparate) >= count:
                break
            da_topic = genera_per_topic(topic, faq_usate.get(topic.id, set()))
            if da_topic is None:
                esito.scarta("topic_senza_materiale")
                continue
            _prepara(da_topic, preparate, hash_nel_lotto, esito, settings)

    esito.composizione["category"] = sum(1 for p in preparate if p.candidata.strategy == "category")

    # --- deduplica contro il database -----------------------------------
    esistenti = await _righe_per_hash(session, [p.hash_template for p in preparate])
    da_riscrivere: list[_Preparata] = []
    riusate: list[Query] = []

    for preparata in preparate:
        riga = esistenti.get(preparata.hash_template)
        if riga is None:
            da_riscrivere.append(preparata)
        elif _eseguita_di_recente(riga, adesso, settings.query_dedup_window_days):
            esito.scarta(MotivoScarto.DUPLICATA)
        else:
            # Stessa domanda, non piu' eseguita da abbastanza tempo: si riusa
            # la riga invece di crearne una gemella con un hash diverso.
            preparata.esistente = riga
            riusate.append(riga)

    # --- riscrittura delle sole query nuove ------------------------------
    testi = [p.candidata.text for p in da_riscrivere]
    if not settings.query_rewrite_enabled:
        esito.riscrittura = "disattivata"
        finali = testi
    elif (riscrittore := riscrittore or client_openai(settings)) is None:
        esito.riscrittura = "non disponibile (nessuna chiave API)"
        finali = testi
    else:
        finali = await riscrivi_lotto(testi, riscrittore, own_domain=settings.own_domain)
        esito.riscrittura = "eseguita" if finali != testi else "eseguita (nessuna modifica)"

    # --- salvataggio ------------------------------------------------------
    # Secondo controllo sul database, stavolta sugli hash dei testi RISCRITTI:
    # la riscrittura puo' collidere con una query di un giorno passato, il cui
    # hash non era fra quelli dei template del lotto.
    hash_riscritti = {calcola_hash(t) for t in finali} - set(esistenti)
    esistenti_riscritte = await _righe_per_hash(session, list(hash_riscritti))
    hash_usati = set(esistenti) | set(esistenti_riscritte) | {p.hash_template for p in preparate}

    valori: list[dict[str, object]] = []
    hash_nuovi: set[str] = set()

    for preparata, testo_finale in zip(da_riscrivere, finali, strict=True):
        testo = testo_finale
        h = calcola_hash(testo)
        if testo != preparata.candidata.text and (h in hash_usati or h in hash_nuovi):
            # La riscrittura e' finita addosso a una query gia' esistente —
            # nel database o in questo stesso lotto: si torna al template, il
            # cui hash e' gia' stato verificato libero.
            testo = preparata.candidata.text
            h = preparata.hash_template
        if h in hash_nuovi:  # pragma: no cover — difesa: i template sono unici
            esito.scarta(MotivoScarto.DUPLICATA)
            continue
        hash_nuovi.add(h)

        c = preparata.candidata
        valori.append(
            {
                "text": testo,
                "text_hash": h,
                "topic_id": c.topic_id,
                "category_slug": c.category_slug,
                "strategy": c.strategy,
                "generator": "llm_rewrite" if testo != c.text else "template",
                "source_faq_index": c.source_faq_index,
            }
        )

    nuove: list[Query] = []
    if valori:
        # ON CONFLICT DO NOTHING: se un ciclo concorrente ha inserito la
        # stessa domanda fra il controllo e l'INSERT, la sua riga si riusa —
        # un lotto non deve mai fallire per una corsa persa.
        inserite = await session.scalars(
            pg_insert(Query)
            .values(valori)
            .on_conflict_do_nothing(index_elements=["text_hash"])
            .returning(Query)
        )
        nuove = list(inserite.all())
        if len(nuove) < len(valori):
            in_corsa = hash_nuovi - {q.text_hash for q in nuove}
            recuperate = await _righe_per_hash(session, list(in_corsa))
            riusate.extend(recuperate.values())
            log.warning(
                "query inserite da un ciclo concorrente durante il lotto: riusate",
                quante=len(recuperate),
            )
    await session.commit()

    esito.query = [*riusate, *nuove]
    esito.nuove = len(nuove)
    esito.riusate = len(riusate)

    log.info(
        "lotto di query generato",
        richieste=count,
        prodotte=len(esito.query),
        nuove=esito.nuove,
        riusate=esito.riusate,
        scartate=esito.scartate or None,
        composizione=esito.composizione,
        riscrittura=esito.riscrittura,
    )
    return esito


def _prepara(
    candidata: QueryCandidata,
    preparate: list[_Preparata],
    hash_nel_lotto: set[str],
    esito: EsitoGenerazione,
    settings: Settings,
) -> None:
    """Valida e accoda una candidata, evitando i doppioni interni al lotto."""
    verdetto = valida_testo(candidata.text, settings.own_domain)
    if not verdetto.valida:
        assert verdetto.motivo is not None
        esito.scarta(verdetto.motivo)
        log.debug("query scartata", motivo=verdetto.motivo, testo=candidata.text)
        return

    h = calcola_hash(candidata.text)
    if h in hash_nel_lotto:
        esito.scarta(MotivoScarto.DUPLICATA)
        return

    hash_nel_lotto.add(h)
    preparate.append(_Preparata(candidata=candidata, hash_template=h))


async def conta_query_attive(session: AsyncSession) -> int:
    return (
        await session.execute(select(func.count()).select_from(Query).where(Query.active.is_(True)))
    ).scalar_one()
