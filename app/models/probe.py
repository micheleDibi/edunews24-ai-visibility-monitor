"""Una singola interrogazione a un provider: l'unita' elementare della misura."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MODI = ("retrieval", "memory")

# `no_search` non e' un errore tecnico: il provider ha risposto, ma senza
# cercare. Una risposta data a memoria non contiene citazioni, e registrarla
# come `edunews_cited = false` scriverebbe "non citato" dove la verita' e' "non
# misurato". E' la trappola di correttezza piu' insidiosa del sistema, e questo
# stato esiste per escludere quei probe da ogni denominatore.
STATI_PROBE = ("ok", "error", "timeout", "rate_limited", "no_search")


class Probe(Base):
    __tablename__ = "probes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("runs.id"), nullable=False)
    query_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("queries.id"), nullable=False)

    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)

    # `retrieval` misura la citazione vera (web search attiva).
    # `memory` misura se il brand e' nella conoscenza parametrica del modello.
    # Sono due metriche diverse e non vanno MAI sommate: ogni aggregato deve
    # filtrare esplicitamente questa colonna.
    mode: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    search_calls: Mapped[int | None] = mapped_column(Integer)

    cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 5))
    # True quando il provider non ha restituito dati di usage e il costo e'
    # stato stimato dal listino. Un costo stimato non deve poter passare per
    # misurato: il kill switch del budget si fida di questa colonna.
    cost_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )

    answer_text: Mapped[str | None] = mapped_column(Text)
    # Azzerato dalla retention dopo RAW_RETENTION_DAYS: serve a verificare il
    # parser, non a essere conservato per sempre.
    #
    # `none_as_null=True` non e' un dettaglio: senza, SQLAlchemy scrive `None`
    # come JSON `null` (cioe' `'null'::jsonb`), che NON e' SQL NULL. La
    # potatura riporterebbe successo lasciando i dati in tabella, e lo spazio
    # continuerebbe a essere pagato.
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))

    # Citazione con link/fonte strutturata.
    edunews_cited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    # Brand nominato nel testo senza URL corrispondente. Segnale diverso:
    # la mention indica riconoscimento, la citazione indica retrieval.
    edunews_mention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    # Il giornale e' comparso fra le fonti recuperate e mostrate al modello, ma
    # non necessariamente fra quelle citate. Terzo stadio dell'imbuto: "non
    # recuperato" e' un problema di indicizzazione, "recuperato ma non citato"
    # e' un problema di qualita' percepita del pezzo, e sono due azioni
    # editoriali diverse.
    edunews_retrieved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    # Citato proprio l'articolo che ha generato la query, non un altro.
    target_hit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("mode IN " + str(MODI), name="mode_valido"),
        CheckConstraint("status IN " + str(STATI_PROBE), name="status_valido"),
        # Se un ciclo viene ritentato, la stessa combinazione non deve produrre
        # due righe: raddoppierebbe silenziosamente il denominatore di ogni
        # tasso di citazione.
        UniqueConstraint(
            "run_id", "query_id", "provider", "mode", name="uq_probes_run_query_provider_mode"
        ),
        Index("ix_probes_created_at", created_at.desc()),
        Index("ix_probes_provider_created_at", provider, created_at.desc()),
        Index("ix_probes_edunews_cited_created_at", edunews_cited, created_at.desc()),
        # Il kill switch somma il costo del giorno e del mese prima di ogni
        # lotto: deve essere un index-only scan, non una scansione della tabella.
        Index("ix_probes_created_at_cost", created_at, cost_eur),
        Index("ix_probes_query_id", query_id),
        Index("ix_probes_run_id", run_id),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Probe {self.id} {self.provider}/{self.mode} {self.status}>"
