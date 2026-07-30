"""Login a password singola."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import Admin, Config
from app.core.security import (
    NOME_COOKIE,
    LoginBloccatoError,
    azzera_tentativi,
    controlla_blocco,
    crea_token,
    registra_tentativo,
    verifica_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RichiestaLogin(BaseModel):
    password: str = Field(min_length=1)


class EsitoLogin(BaseModel):
    ok: bool = True


def _ip(request: Request) -> str:
    # Dietro reverse proxy `client.host` e' il proxy: uvicorn gira con
    # `proxy_headers=True`, quindi `client.host` e' gia' l'IP reale.
    return request.client.host if request.client else "sconosciuto"


@router.post("/login", response_model=EsitoLogin)
async def login(
    dati: RichiestaLogin, request: Request, response: Response, settings: Config
) -> EsitoLogin:
    ip = _ip(request)
    try:
        controlla_blocco(ip)
    except LoginBloccatoError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="troppi tentativi falliti: riprova fra un quarto d'ora",
        ) from None

    if not verifica_password(dati.password, settings.admin_password_hash):
        try:
            registra_tentativo(ip)
        except LoginBloccatoError:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="troppi tentativi falliti: riprova fra un quarto d'ora",
            ) from None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="password non valida")

    azzera_tentativi(ip)
    response.set_cookie(
        key=NOME_COOKIE,
        value=crea_token(settings),
        max_age=settings.access_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return EsitoLogin()


@router.post("/logout", response_model=EsitoLogin)
async def logout(response: Response, settings: Config) -> EsitoLogin:
    response.delete_cookie(
        key=NOME_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return EsitoLogin()


class Identita(BaseModel):
    soggetto: str


# `/api/me`, non `/api/auth/me`: e' il percorso della specifica, quindi vive su
# un router senza prefisso.
router_radice = APIRouter(tags=["auth"])


@router_radice.get("/me", response_model=Identita)
async def me(admin: Admin) -> Identita:
    return Identita(soggetto=admin.soggetto)
