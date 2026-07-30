"""Potatura dei dati grezzi.

`raw_response` serve a verificare il parser, non a essere conservato per sempre:
su Supabase lo spazio si paga e una risposta con web search e' grande. Si azzera
la colonna invece di cancellare la riga, cosi' le metriche storiche restano
tutte leggibili — che e' il punto di tutto il sistema.

Gli aggregati in `daily_rollup` non vengono mai potati: sono minuscoli e sono la
serie storica.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import null, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import Probe

log = structlog.get_logger(__name__)


@dataclass
class EsitoPotatura:
    raw_azzerati: int = 0
    risposte_azzerate: int = 0


async def pota(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    adesso: datetime | None = None,
) -> EsitoPotatura:
    settings = settings or get_settings()
    adesso = adesso or datetime.now(UTC)
    esito = EsitoPotatura()

    limite_raw = adesso - timedelta(days=settings.raw_retention_days)
    risultato = await session.execute(
        update(Probe)
        .where(Probe.created_at < limite_raw, Probe.raw_response.is_not(None))
        # `null()` esplicito, non `None`: su una colonna JSONB `None` diventa
        # JSON `null`, che occupa spazio e resta `IS NOT NULL`.
        .values(raw_response=null())
    )
    esito.raw_azzerati = cast("CursorResult[Any]", risultato).rowcount or 0

    limite_testo = adesso - timedelta(days=settings.answer_retention_days)
    risultato = await session.execute(
        update(Probe)
        .where(Probe.created_at < limite_testo, Probe.answer_text.is_not(None))
        .values(answer_text=None)
    )
    esito.risposte_azzerate = cast("CursorResult[Any]", risultato).rowcount or 0

    await session.commit()
    if esito.raw_azzerati or esito.risposte_azzerate:
        log.info(
            "potatura eseguita",
            raw_azzerati=esito.raw_azzerati,
            risposte_azzerate=esito.risposte_azzerate,
            giorni_raw=settings.raw_retention_days,
            giorni_risposte=settings.answer_retention_days,
        )
    return esito
