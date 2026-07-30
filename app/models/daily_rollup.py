"""Aggregati giornalieri precalcolati, per i grafici di tendenza.

Due scelte che divergono dalla specifica originale, entrambe necessarie:

1. `mode` fa parte della chiave primaria. Senza, i probe `retrieval` e `memory`
   finirebbero nella stessa riga e ogni tasso di citazione sarebbe la media di
   due misure che non hanno lo stesso significato.

2. `category_slug` e' NOT NULL con default stringa vuota. In Postgres una
   colonna nullable non puo' stare in una PRIMARY KEY, e la specifica la
   voleva nullable: la stringa vuota rappresenta "nessuna categoria".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Integer, Numeric, Text
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.probe import MODI

SENZA_CATEGORIA = ""


class DailyRollup(Base):
    __tablename__ = "daily_rollup"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    mode: Mapped[str] = mapped_column(Text, primary_key=True)
    category_slug: Mapped[str] = mapped_column(Text, primary_key=True, server_default=sa_text("''"))

    # Denominatore: solo i probe con status = 'ok'. Un'outage di provider non
    # deve somigliare a un crollo di visibilita'.
    probes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    cited: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    mentioned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    target_hits: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))

    # Il costo include anche i probe falliti: sono stati pagati comunque.
    cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default=sa_text("0")
    )

    __table_args__ = (CheckConstraint("mode IN " + str(MODI), name="mode_valido"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DailyRollup {self.day} {self.provider}/{self.mode} {self.cited}/{self.probes}>"
