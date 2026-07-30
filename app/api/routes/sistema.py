"""Salute del servizio e stato del budget.

`/api/health` e' l'unica rotta NON autenticata oltre al login: la usa
l'HEALTHCHECK del container, che non ha una sessione. Per questo non espone
nulla di sensibile — nessun conteggio, nessun costo, nessuna query.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import Admin, Config, Db
from app.db.session import get_sessionmaker
from app.services import budget
from app.services.scheduler import prossime_esecuzioni

router = APIRouter(tags=["sistema"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Leggera per costruzione: un `SELECT 1` e lo stato dello scheduler.

    Un healthcheck che interroga la tabella dei probe diventa lento proprio
    quando il sistema e' sotto pressione, cioe' quando serve che risponda.
    """
    dettaglio: dict[str, Any] = {"stato": "ok"}
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        dettaglio["database"] = "ok"
    except Exception as exc:
        dettaglio["stato"] = "degradato"
        dettaglio["database"] = f"errore: {type(exc).__name__}"

    scheduler = getattr(request.app.state, "scheduler", None)
    dettaglio["scheduler"] = "attivo" if scheduler and scheduler.running else "spento"
    dettaglio["prossime_esecuzioni"] = prossime_esecuzioni(scheduler)

    return JSONResponse(dettaglio, status_code=200 if dettaglio["stato"] == "ok" else 503)


class StatoCosti(BaseModel):
    giorno_eur: Decimal
    mese_eur: Decimal
    tetto_giorno_eur: Decimal
    tetto_mese_eur: Decimal
    residuo_giorno_eur: Decimal
    budget_superato: bool = Field(
        description="Se vero, i cicli orari vengono saltati con status `skipped_budget`"
    )
    motivo: str | None


@router.get("/costs", response_model=StatoCosti)
async def costi(db: Db, admin: Admin, settings: Config) -> StatoCosti:
    stato = await budget.stato(db, settings)
    return StatoCosti(
        giorno_eur=stato.giorno_eur,
        mese_eur=stato.mese_eur,
        tetto_giorno_eur=stato.tetto_giorno_eur,
        tetto_mese_eur=stato.tetto_mese_eur,
        residuo_giorno_eur=stato.residuo_giorno_eur,
        budget_superato=stato.superato,
        motivo=stato.motivo(),
    )
