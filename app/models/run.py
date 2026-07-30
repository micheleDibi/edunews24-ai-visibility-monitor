"""Un ciclo di monitoraggio: un lotto di query mandato a tutti i provider."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, Numeric, Text, func
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATI_RUN = ("running", "ok", "partial", "failed", "skipped_budget")
TIPI_RUN = ("hourly", "manual", "backfill")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Distingue il cron orario da `POST /api/actions/run-now`: senza, un ciclo
    # lanciato a mano fa un picco nei grafici che sembra un'anomalia.
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'hourly'"))

    planned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))

    cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default=sa_text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN " + str(STATI_RUN), name="status_valido"),
        CheckConstraint("kind IN " + str(TIPI_RUN), name="kind_valido"),
        Index("ix_runs_started_at", started_at.desc()),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Run {self.id} {self.status}>"
