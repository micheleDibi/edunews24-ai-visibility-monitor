"""Ogni fonte citata in una risposta, non solo le proprie.

Registrare anche i domini altrui non costa nulla — arrivano gia' nella stessa
risposta — e senza quel dato non si puo' sapere chi occupa il posto quando
edunews24.it non compare. La dashboard puo' nascondere quella vista; i dati
vanno comunque salvati.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Dominio non estraibile da un URL wrapper di redirect. Sentinella esplicita:
# meglio dichiarare "non risolto" che inventare un dominio plausibile, che
# falserebbe la classifica di chi occupa il posto.
DOMINIO_NON_RISOLTO = "unresolved"

# `citation` = la fonte ha sostenuto una frase della risposta.
# `source`   = la fonte e' stata recuperata e mostrata al modello, che poi puo'
#              averla ignorata. Sommarle gonfierebbe il tasso di citazione.
TIPI_CITAZIONE = ("citation", "source")


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    probe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("probes.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'citation'"))

    # Posizione nella lista di fonti restituita dal provider (1-based).
    position: Mapped[int | None] = mapped_column(Integer)

    domain: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)

    is_own: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    # Slug estratto dal path quando `is_own`: serve a stabilire `target_hit`.
    own_slug: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("kind IN " + str(TIPI_CITAZIONE), name="kind_valido"),
        Index("ix_citations_domain", domain),
        Index("ix_citations_probe_id", probe_id),
        Index("ix_citations_own_slug", own_slug),
        # La classifica dei domini filtra per tipo prima di aggregare: senza
        # `kind` nell'indice ogni vista "chi occupa il posto" fa un seq scan.
        Index("ix_citations_kind_domain", kind, domain),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Citation {self.domain} probe={self.probe_id}>"
