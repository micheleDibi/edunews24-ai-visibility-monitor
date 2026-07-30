"""Engine e sessioni del database di MONITORAGGIO (lettura/scrittura)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_connect_args(settings: Settings, *, read_only: bool, app_name: str) -> dict[str, Any]:
    """`connect_args` per asyncpg, condivisi tra i due database.

    `application_name` rende riconoscibili le nostre connessioni in
    `pg_stat_activity`: quando il DB editoriale ha una connessione strana, si
    deve poter vedere a colpo d'occhio se e' nostra.
    """
    server_settings: dict[str, str] = {"application_name": app_name}
    if read_only:
        # Cintura e bretelle: anche se il ruolo avesse per errore un privilegio
        # di scrittura, ogni transazione parte in sola lettura.
        server_settings["default_transaction_read_only"] = "on"

    args: dict[str, Any] = {"server_settings": server_settings}
    if settings.db_disable_prepared_statements:
        # `statement_cache_size` e' di asyncpg; `prepared_statement_cache_size`
        # e' della shim DBAPI di SQLAlchemy. Servono entrambi sotto Supavisor /
        # pgbouncer in transaction mode.
        args["statement_cache_size"] = 0
        args["prepared_statement_cache_size"] = 0
    return args


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.monitor_db_url,
            pool_size=settings.monitor_pool_size,
            max_overflow=settings.monitor_max_overflow,
            pool_pre_ping=True,
            future=True,
            connect_args=build_connect_args(
                settings, read_only=False, app_name="edunews24-monitor"
            ),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dipendenza FastAPI: commit se la richiesta va a buon fine, rollback se no."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
