"""Snapshot locale di un articolo del DB editoriale.

Non e' una copia dell'articolo: e' l'insieme minimo di campi che servono a
generare domande e a segmentare le metriche. Il testo dell'articolo non viene
copiato — non serve alla misura e duplicarlo creerebbe un secondo posto in cui
il contenuto del giornale vive.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Text, func
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # `articles.id` nel DB editoriale. UNIQUE: il sync e' un upsert su questa.
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)

    slug: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category_slug: Mapped[str | None] = mapped_column(Text)

    # `flash` | `editoriale` | `evergreen`. Nullable: le colonne `skill_*` sono
    # popolate solo sugli articoli recenti, e la rotazione deve funzionare
    # comunque (fallback a `editoriale`).
    livello: Mapped[str | None] = mapped_column(Text)
    keyword: Mapped[str | None] = mapped_column(Text)
    angolo: Mapped[str | None] = mapped_column(Text)

    # Sempre array JSON normalizzati, qualunque sia il tipo nella sorgente.
    tags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'[]'::jsonb")
    )
    faq_questions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'[]'::jsonb")
    )

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Watermark del sync incrementale: il massimo tra published_at e updated_at
    # visto nella sorgente. Gli articoli vengono modificati dopo la
    # pubblicazione, quindi il solo published_at non basta a capire cosa e'
    # cambiato dall'ultima sincronizzazione.
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Un articolo tornato in bozza o sparito dalla sorgente viene disattivato,
    # mai cancellato: i probe storici che lo citano devono restare leggibili.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("true"))

    last_probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    probe_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))

    __table_args__ = (
        # La rotazione dell'archivio ordina per `last_probed_at NULLS FIRST`:
        # senza questo indice ogni ciclo orario fa un seq scan sull'intero
        # catalogo.
        Index("ix_topics_last_probed_at", last_probed_at.nullsfirst()),
        Index("ix_topics_published_at", published_at.desc()),
        Index("ix_topics_category_slug", category_slug),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Topic {self.source_id} {self.slug!r}>"
