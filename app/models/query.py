"""Una domanda generata, pronta per essere inviata ai provider."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Enum come TEXT + CHECK invece che come tipo ENUM Postgres: aggiungere un
# valore a un ENUM dentro una migrazione Alembic richiede DDL fuori transazione
# e non e' reversibile con un downgrade pulito. Il vincolo qui e' altrettanto
# forte e cambiarlo e' un ALTER TABLE banale.
STRATEGIE = ("faq_verbatim", "keyword_intent", "tag_combo", "angolo", "evergreen_howto", "category")
GENERATORI = ("template", "llm_rewrite")


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Hash della forma normalizzata (minuscole, punteggiatura rimossa, spazi
    # collassati). UNIQUE: la stessa domanda non esiste due volte in tabella.
    # La finestra di 14 giorni non impedisce la creazione ma il RIUSO: se
    # l'hash esiste ed e' vecchio abbastanza, si riusa la riga.
    text_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # Nullable: le query di categoria non nascono da un articolo specifico.
    topic_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="SET NULL")
    )
    category_slug: Mapped[str | None] = mapped_column(Text)

    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    generator: Mapped[str] = mapped_column(Text, nullable=False)

    # Quale `faqs[i].question` dell'articolo e' stata usata, per non ripeterla.
    # Tenerlo qui invece che su `topics` evita di duplicare lo stato: la
    # domanda su quali FAQ siano gia' state usate ha una risposta sola, ed e'
    # l'insieme delle query gia' generate per quel topic.
    source_faq_index: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("true"))

    __table_args__ = (
        CheckConstraint("strategy IN " + str(STRATEGIE), name="strategy_valida"),
        CheckConstraint("generator IN " + str(GENERATORI), name="generator_valido"),
        CheckConstraint("char_length(text) BETWEEN 15 AND 300", name="lunghezza_testo"),
        # Selezione delle candidate al riuso: "attive, non eseguite di recente".
        Index("ix_queries_active_last_run_at", active, last_run_at.nullsfirst()),
        Index("ix_queries_topic_id", topic_id),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Query {self.id} {self.strategy} {self.text[:40]!r}>"
