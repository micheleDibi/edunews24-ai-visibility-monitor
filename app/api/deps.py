"""Dipendenze condivise delle rotte."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import NOME_COOKIE, Amministratore, leggi_token
from app.db.session import get_sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Commit se la richiesta va a buon fine, rollback se no."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def admin_corrente(
    edunews_session: Annotated[str | None, Cookie(alias=NOME_COOKIE)] = None,
) -> Amministratore:
    settings: Settings = get_settings()
    if not edunews_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sessione assente")
    admin = leggi_token(edunews_session, settings)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="sessione scaduta o non valida"
        )
    return admin


Db = Annotated[AsyncSession, Depends(get_db)]
Admin = Annotated[Amministratore, Depends(admin_corrente)]
Config = Annotated[Settings, Depends(get_settings)]
