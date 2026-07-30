"""Aggregati giornalieri precalcolati.

## Idempotente per costruzione

Il rollup RICALCOLA da zero dai probe grezzi e sovrascrive, invece di
incrementare. E' la differenza fra un job che si puo' rieseguire e uno che
raddoppia i numeri ogni volta che lo fai. Serve perche' il job notturno puo'
girare due volte (riavvio del container), puo' saltare una notte (downtime) e
puo' trovare un ciclo che ha finito dopo mezzanotte.

## Tre regole che rendono il dato leggibile

* **il denominatore conta solo i probe `ok`.** Un'ora di disservizio di un
  provider non deve somigliare a un crollo di visibilita' del giornale, e un
  probe `no_search` non e' un "non citato": e' un "non misurato".
* **il costo somma TUTTI i probe**, anche i falliti: sono stati pagati comunque.
* **`mode` fa parte della chiave.** `retrieval` e `memory` misurano cose
  diverse e mediarle non produce nessuna delle due.

Il giorno e' quello del fuso configurato, non UTC: per un giornale italiano
"oggi" e' oggi a Roma, e aggregare su UTC sposterebbe due ore di dati nel
giorno sbagliato.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings

log = structlog.get_logger(__name__)

# Quanti giorni indietro ricalcolare a ogni giro. Copre un ciclo finito dopo
# mezzanotte e un paio di notti di container spento senza bisogno di sapere che
# c'e' stato un downtime.
GIORNI_DI_RECUPERO = 3

_UPSERT = text(
    """
    INSERT INTO daily_rollup
        (day, provider, mode, category_slug, probes, cited, mentioned, target_hits, cost_eur)
    SELECT
        (p.created_at AT TIME ZONE :tz)::date                                AS day,
        p.provider,
        p.mode,
        coalesce(q.category_slug, '')                                        AS category_slug,
        count(*) FILTER (WHERE p.status = 'ok')                              AS probes,
        count(*) FILTER (WHERE p.status = 'ok' AND p.edunews_cited)          AS cited,
        count(*) FILTER (WHERE p.status = 'ok' AND p.edunews_mention)        AS mentioned,
        count(*) FILTER (WHERE p.status = 'ok' AND p.target_hit)             AS target_hits,
        coalesce(sum(p.cost_eur), 0)                                         AS cost_eur
    FROM probes p
    JOIN queries q ON q.id = p.query_id
    WHERE (p.created_at AT TIME ZONE :tz)::date = :giorno
    GROUP BY 1, 2, 3, 4
    ON CONFLICT (day, provider, mode, category_slug) DO UPDATE SET
        probes      = EXCLUDED.probes,
        cited       = EXCLUDED.cited,
        mentioned   = EXCLUDED.mentioned,
        target_hits = EXCLUDED.target_hits,
        cost_eur    = EXCLUDED.cost_eur
    """
)

# Un giorno che prima aveva righe e ora non ne ha piu' (per esempio dopo una
# cancellazione di probe) lascerebbe aggregati fantasma: si azzerano prima di
# reinserire, cosi' il rollup non e' solo idempotente ma anche coerente.
_PULISCI_GIORNO = text("DELETE FROM daily_rollup WHERE day = :giorno")


@dataclass
class EsitoRollup:
    giorni: list[date]
    righe: int


async def ricalcola_giorno(
    session: AsyncSession, giorno: date, settings: Settings | None = None
) -> int:
    settings = settings or get_settings()
    await session.execute(_PULISCI_GIORNO, {"giorno": giorno})
    risultato = await session.execute(_UPSERT, {"tz": settings.tz, "giorno": giorno})
    return cast("CursorResult[Any]", risultato).rowcount or 0


async def ricalcola(
    session: AsyncSession,
    *,
    giorni: int = GIORNI_DI_RECUPERO,
    settings: Settings | None = None,
    adesso: datetime | None = None,
) -> EsitoRollup:
    """Ricalcola gli ultimi `giorni` giorni, oggi compreso."""
    settings = settings or get_settings()
    adesso = adesso or datetime.now(ZoneInfo(settings.tz))
    oggi = adesso.date()

    elaborati: list[date] = []
    righe = 0
    for indietro in range(giorni):
        giorno = oggi - timedelta(days=indietro)
        righe += await ricalcola_giorno(session, giorno, settings)
        elaborati.append(giorno)

    await session.commit()
    log.info(
        "rollup ricalcolato",
        dal=elaborati[-1].isoformat(),
        al=elaborati[0].isoformat(),
        righe=righe,
    )
    return EsitoRollup(giorni=elaborati, righe=righe)
