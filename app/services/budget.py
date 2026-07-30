"""Spesa consuntivata e freno prima di spendere.

Il controllo va fatto PRIMA del lotto, non dopo: dopo significa che i soldi
sono gia' usciti. La versione completa del kill switch (run con status
`skipped_budget`, banner in dashboard) arriva con lo scheduler; qui c'e' la
parte che serve subito, perche' `run-once` fa chiamate a pagamento e collaudarlo
senza un freno e' come provare i freni in discesa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import Probe

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StatoBudget:
    giorno_eur: Decimal
    mese_eur: Decimal
    tetto_giorno_eur: Decimal
    tetto_mese_eur: Decimal

    @property
    def giorno_superato(self) -> bool:
        return self.giorno_eur >= self.tetto_giorno_eur

    @property
    def mese_superato(self) -> bool:
        return self.mese_eur >= self.tetto_mese_eur

    @property
    def superato(self) -> bool:
        return self.giorno_superato or self.mese_superato

    @property
    def residuo_giorno_eur(self) -> Decimal:
        return max(Decimal("0"), self.tetto_giorno_eur - self.giorno_eur)

    def motivo(self) -> str | None:
        if self.giorno_superato:
            return (
                f"tetto giornaliero raggiunto: {self.giorno_eur} EUR su {self.tetto_giorno_eur} EUR"
            )
        if self.mese_superato:
            return f"tetto mensile raggiunto: {self.mese_eur} EUR su {self.tetto_mese_eur} EUR"
        return None


async def stato(session: AsyncSession, settings: Settings | None = None) -> StatoBudget:
    """Spesa di oggi e del mese corrente, nel fuso configurato.

    "Oggi" per un giornale italiano e' oggi a Roma, non a UTC: aggregare su UTC
    sposterebbe due ore di spesa nel giorno sbagliato e farebbe scattare il
    freno all'ora sbagliata.
    """
    settings = settings or get_settings()
    adesso = datetime.now(ZoneInfo(settings.tz))
    inizio_giorno = adesso.replace(hour=0, minute=0, second=0, microsecond=0)
    inizio_mese = inizio_giorno.replace(day=1)

    async def somma(da: datetime) -> Decimal:
        # I probe falliti sono compresi: sono stati pagati comunque.
        valore = (
            await session.execute(
                select(func.coalesce(func.sum(Probe.cost_eur), 0)).where(Probe.created_at >= da)
            )
        ).scalar_one()
        return Decimal(str(valore))

    return StatoBudget(
        giorno_eur=await somma(inizio_giorno),
        mese_eur=await somma(inizio_mese),
        tetto_giorno_eur=Decimal(str(settings.max_daily_spend_eur)),
        tetto_mese_eur=Decimal(str(settings.max_monthly_spend_eur)),
    )
