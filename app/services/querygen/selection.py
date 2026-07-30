"""Rotazione: quali topic entrano nel lotto di questo ciclo.

L'obiettivo e' coprire il massimo numero di argomenti nel tempo dando la
precedenza alle notizie fresche, perche' e' nelle prime ore che un articolo
entra o non entra negli indici di retrieval dei provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic

log = structlog.get_logger(__name__)

FRESCO_ORE = 72
RECENTE_GIORNI = 30

# Ordine di ripiego quando un bucket non ha abbastanza materiale: prima si
# prova a pescare dalle notizie fresche, che restano la priorita' anche
# quando e' un altro bucket a essere scoperto.
PRIORITA_RIPIEGO = ("fresh", "recent", "archive")


def ripartisci(totale: int, pesi: dict[str, int]) -> dict[str, int]:
    """Trasforma percentuali in numeri interi che sommano esattamente a `totale`.

    Metodo dei resti maggiori (quota di Hare). L'arrotondamento ingenuo su
    50/20/20/10 con totale 9 — che e' il caso reale, 200 query al giorno su 24
    ore — restituisce 4+2+2+1 = 9 solo per fortuna: con `round()` si ottiene
    5+2+2+1 = 10, con `int()` 4+1+1+0 = 6. Nessuno dei due e' il lotto che si
    e' chiesto.

    A parita' di resto vince il peso maggiore, e poi l'ordine alfabetico: il
    risultato deve essere riproducibile, altrimenti non e' testabile.
    """
    somma_pesi = sum(pesi.values())
    if totale <= 0 or somma_pesi <= 0:
        return dict.fromkeys(pesi, 0)

    esatti = {nome: totale * peso / somma_pesi for nome, peso in pesi.items()}
    quote = {nome: int(valore) for nome, valore in esatti.items()}

    da_distribuire = totale - sum(quote.values())
    resti = sorted(
        pesi,
        key=lambda nome: (-(esatti[nome] - quote[nome]), -pesi[nome], nome),
    )
    for nome in resti[:da_distribuire]:
        quote[nome] += 1

    return quote


@dataclass
class SelezioneTopic:
    topics: list[Topic] = field(default_factory=list)
    # Quanti topic sono arrivati davvero da ciascun bucket, dopo i ripieghi.
    composizione: dict[str, int] = field(default_factory=dict)
    # Bucket che non hanno potuto riempire la propria quota.
    scoperti: dict[str, int] = field(default_factory=dict)


def _finestre(adesso: datetime) -> dict[str, tuple[datetime | None, datetime | None]]:
    """Estremi (da, a) di ciascun bucket. Disgiunti per costruzione."""
    limite_fresco = adesso - timedelta(hours=FRESCO_ORE)
    limite_recente = adesso - timedelta(days=RECENTE_GIORNI)
    return {
        "fresh": (limite_fresco, None),
        "recent": (limite_recente, limite_fresco),
        "archive": (None, limite_recente),
    }


async def _candidati(
    session: AsyncSession,
    bucket: str,
    adesso: datetime,
    limite: int,
    esclusi: set[int],
) -> list[Topic]:
    da, a = _finestre(adesso)[bucket]

    stmt = select(Topic).where(Topic.active.is_(True))
    if da is not None:
        stmt = stmt.where(Topic.published_at >= da)
    if a is not None:
        stmt = stmt.where(Topic.published_at < a)
    if esclusi:
        stmt = stmt.where(Topic.id.notin_(esclusi))

    # `last_probed_at NULLS FIRST` e' cio' che garantisce che ogni articolo
    # venga sondato prima o poi: chi non e' mai stato toccato passa davanti.
    stmt = stmt.order_by(Topic.last_probed_at.asc().nullsfirst(), Topic.published_at.desc()).limit(
        limite
    )

    return list((await session.execute(stmt)).scalars().all())


async def seleziona_topic(
    session: AsyncSession,
    quote: dict[str, int],
    *,
    adesso: datetime | None = None,
    esclusi: set[int] | None = None,
) -> SelezioneTopic:
    """Sceglie i topic dei tre bucket temporali, con ripiego sui vicini.

    Un sabato senza pubblicazioni lascia il bucket `fresh` vuoto: in quel caso
    il lotto non si rimpicciolisce, si riempie dagli altri bucket. Un ciclo da
    9 query deve restare da 9 query, altrimenti la serie storica ha buchi che
    somigliano a cali di attivita' e non lo sono.
    """
    adesso = adesso or datetime.now(UTC)
    esclusi = set(esclusi or ())
    totale = sum(quote.values())
    selezione = SelezioneTopic()
    if totale <= 0:
        return selezione

    # Si pesca piu' del necessario da ogni bucket cosi' gli avanzi sono gia'
    # disponibili per i ripieghi, senza una seconda interrogazione.
    limite = totale + 5
    pool = {b: await _candidati(session, b, adesso, limite, esclusi) for b in quote}

    scelti: list[Topic] = []
    consumati: dict[str, int] = {}
    for bucket, quota in quote.items():
        presi = pool[bucket][:quota]
        consumati[bucket] = len(presi)
        scelti.extend(presi)
        if len(presi) < quota:
            selezione.scoperti[bucket] = quota - len(presi)

    mancanti = totale - len(scelti)
    if mancanti:
        for bucket in PRIORITA_RIPIEGO:
            if mancanti <= 0:
                break
            avanzi = pool.get(bucket, [])[consumati.get(bucket, 0) :]
            presi = avanzi[:mancanti]
            scelti.extend(presi)
            consumati[bucket] = consumati.get(bucket, 0) + len(presi)
            mancanti -= len(presi)

        log.info(
            "lotto ricomposto per bucket scoperti",
            scoperti=selezione.scoperti,
            composizione_finale=consumati,
            non_riempiti=mancanti,
        )

    selezione.topics = scelti
    selezione.composizione = consumati
    return selezione
