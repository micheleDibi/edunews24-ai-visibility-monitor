"""Autenticazione a utente singolo: hash della password e JWT in cookie.

## Perche' argon2 e non passlib+bcrypt

passlib non e' piu' mantenuto e si rompe con bcrypt >= 4.1; bcrypt tronca
silenziosamente la password a 72 byte. argon2-cffi e' mantenuto, non tronca, e
ha un'API di due funzioni.

## Perche' nessun refresh token

C'e' un solo utente e una sola sessione. Un refresh token aggiungerebbe una
tabella, una rotazione e un modo di sbagliare, per proteggere una superficie
che non esiste: un access token in cookie `httpOnly` con TTL lungo e' piu'
semplice e non meno sicuro in questo scenario.

## Perche' SameSite=Lax basta contro il CSRF

`Lax` impedisce l'invio del cookie sulle richieste POST cross-site, che e'
esattamente il vettore su `POST /api/actions/run-now`. Un token CSRF separato
proteggerebbe da qualcosa che `Lax` gia' blocca.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

log = structlog.get_logger(__name__)

NOME_COOKIE = "edunews_session"
SOGGETTO = "admin"

_hasher = PasswordHasher()

# Rate limit del login: finestra scorrevole in memoria. Un solo processo e un
# solo utente — una tabella o un Redis per questo sarebbero infrastruttura per
# nulla. Si perde il conteggio a ogni riavvio, che e' accettabile: il costo di
# un riavvio come modo di aggirare il limite e' piu' alto del beneficio.
MAX_TENTATIVI = 5
FINESTRA_TENTATIVI_S = 900
_tentativi: dict[str, list[float]] = defaultdict(list)


class LoginBloccatoError(Exception):
    """Troppi tentativi falliti dallo stesso indirizzo."""


@dataclass(frozen=True)
class Amministratore:
    soggetto: str = SOGGETTO


def genera_hash(password: str) -> str:
    """Usata dalla riga di comando per riempire ADMIN_PASSWORD_HASH."""
    return _hasher.hash(password)


def verifica_password(password: str, hash_atteso: str) -> bool:
    if not hash_atteso:
        log.error(
            "ADMIN_PASSWORD_HASH non configurato: nessun login e' possibile. "
            "Genera l'hash con: python -c \"from argon2 import PasswordHasher; "
            'print(PasswordHasher().hash(input()))"'
        )
        return False
    try:
        return _hasher.verify(hash_atteso, password)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        log.error("ADMIN_PASSWORD_HASH non e' un hash argon2 valido")
        return False


def registra_tentativo(ip: str) -> None:
    """Segna un tentativo fallito e solleva se la soglia e' superata."""
    adesso = time.monotonic()
    recenti = [t for t in _tentativi[ip] if adesso - t < FINESTRA_TENTATIVI_S]
    recenti.append(adesso)
    _tentativi[ip] = recenti
    if len(recenti) > MAX_TENTATIVI:
        raise LoginBloccatoError


def controlla_blocco(ip: str) -> None:
    adesso = time.monotonic()
    recenti = [t for t in _tentativi[ip] if adesso - t < FINESTRA_TENTATIVI_S]
    _tentativi[ip] = recenti
    if len(recenti) > MAX_TENTATIVI:
        raise LoginBloccatoError


def azzera_tentativi(ip: str) -> None:
    _tentativi.pop(ip, None)


def crea_token(settings: Settings) -> str:
    adesso = datetime.now(UTC)
    payload = {
        "sub": SOGGETTO,
        "iat": adesso,
        "exp": adesso + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def leggi_token(token: str, settings: Settings) -> Amministratore | None:
    if not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("sub") != SOGGETTO:
        return None
    return Amministratore()
