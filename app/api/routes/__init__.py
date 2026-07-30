"""Aggregazione dei router sotto `/api`.

L'ordine di inclusione conta: `/api/probes/{id}` deve venire dopo
`/api/probes`, e il catch-all del frontend (montato in `main.py`) deve venire
dopo TUTTI questi, altrimenti oscura l'API.
"""

from fastapi import APIRouter

from app.api.routes import analytics, auth, explore, sistema

api_router = APIRouter(prefix="/api")
api_router.include_router(sistema.router)
api_router.include_router(auth.router)
api_router.include_router(auth.router_radice)
api_router.include_router(analytics.router)
api_router.include_router(explore.router)

__all__ = ["api_router"]
