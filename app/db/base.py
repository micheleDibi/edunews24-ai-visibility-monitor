"""Base dichiarativa SQLAlchemy 2.0 per il database di MONITORAGGIO.

Il database sorgente (gli articoli) non ha modelli ORM: e' di un'altra
applicazione, e' in sola lettura e lo interroghiamo con SQL testuale in
`app/db/source.py`. Mappare quelle tabelle qui darebbe l'impressione sbagliata
che questo servizio ne sia proprietario.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nomi deterministici per indici e vincoli: senza questa convenzione Alembic
# genera nomi automatici che cambiano tra una macchina e l'altra e i downgrade
# non trovano piu' l'oggetto da eliminare.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    """`created_at` valorizzato dal database, non dal client.

    Il valore lo mette Postgres con `now()`: cosi' l'ora e' quella del server e
    non dipende dall'orologio del container.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
