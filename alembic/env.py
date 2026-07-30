"""Ambiente Alembic per il database di MONITORAGGIO.

Il database sorgente non e' mai toccato da Alembic: e' di un'altra
applicazione e questo servizio non ha nemmeno i privilegi per modificarlo.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_connect_args
from app.models import *  # noqa: F403 — registra i modelli su Base.metadata

config = context.config
settings = get_settings()

config.set_main_option("sqlalchemy.url", settings.monitor_db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.monitor_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        future=True,
        # Le stesse impostazioni dell'engine applicativo: senza, `alembic
        # upgrade head` all'avvio del container fallisce contro un pooler in
        # transaction mode, che e' esattamente dove gira in produzione.
        connect_args=build_connect_args(settings, read_only=False, app_name="edunews24-alembic"),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
