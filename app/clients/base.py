"""Contratto comune degli adapter dei provider.

Ogni provider ha una forma di richiesta e di risposta diversa. Qui si definisce
l'unica forma che il resto del sistema conosce, cosi' aggiungere un provider
non tocca nulla a valle.

## Due segnali, non uno

Ogni adapter distingue le fonti *citate* nella risposta da quelle solo
*recuperate* e mostrate al modello. Sono due stadi diversi dello stesso imbuto:
"edunews24.it non e' stato recuperato" e' un problema di indicizzazione,
"e' stato recuperato ma non citato" e' un problema di qualita' percepita del
pezzo. Confonderli renderebbe la dashboard incapace di dire cosa fare.

## Il prompt di sistema e' identico per tutti

Altrimenti il confronto fra provider non vale nulla: la differenza misurata
sarebbe fra i prompt, non fra i motori.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
import structlog

log = structlog.get_logger(__name__)

Modo = Literal["retrieval", "memory"]

# Citata con link/fonte strutturata, oppure soltanto recuperata e mostrata al
# modello fra i risultati di ricerca.
TipoCitazione = Literal["citation", "source"]

# Specifica §6.4: neutro e identico per ogni provider.
PROMPT_SISTEMA = (
    "Rispondi in italiano alla domanda dell'utente. "
    "Se consulti fonti web, cita le fonti che hai usato."
)

# Modalita' `memory`: nessuno strumento. Misura una cosa diversa — se il brand
# e' entrato nella conoscenza parametrica del modello — e per farlo deve
# chiedere esplicitamente le fonti che il modello *ricorda*.
PROMPT_SISTEMA_MEMORIA = (
    "Rispondi in italiano alla domanda dell'utente senza consultare il web. "
    "Indica quali fonti e testate italiane conosci sull'argomento."
)


class ProviderError(Exception):
    """Errore di un provider, con lo stato da registrare sul probe."""

    stato = "error"


class ProviderTimeoutError(ProviderError):
    stato = "timeout"


class RateLimitError(ProviderError):
    stato = "rate_limited"


class RicercaNonEseguitaError(ProviderError):
    """Il provider ha risposto senza cercare: il campione non e' valido.

    Non e' un errore tecnico ed e' la trappola di correttezza piu' insidiosa di
    tutto il sistema. Una risposta data a memoria non contiene citazioni, e
    registrarla come `edunews_cited = false` significherebbe scrivere "non
    citato" dove la verita' e' "non misurato". Il probe va marcato
    `no_search` ed escluso da ogni denominatore.
    """

    stato = "no_search"


@dataclass(frozen=True)
class CitazioneGrezza:
    """Una fonte, come l'ha restituita il provider. Nessuna normalizzazione."""

    url: str | None
    title: str | None = None
    kind: TipoCitazione = "citation"
    position: int | None = None


@dataclass
class RisultatoProbe:
    provider: str
    # Modello EFFETTIVAMENTE risolto dalla risposta, non quello richiesto: gli
    # alias vengono ripuntati, e in una serie storica di mesi un cambio di
    # modello va visto nei dati invece di essere confuso con un cambio di
    # visibilita' del giornale.
    model: str
    mode: Modo
    answer_text: str | None
    citazioni: list[CitazioneGrezza] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    search_calls: int | None = None
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    # Costo dichiarato dal provider, quando lo dichiara (Perplexity lo fa).
    # Vale piu' di qualunque stima da listino.
    cost_usd_provider: Decimal | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    name: str
    supports_retrieval: bool
    model: str

    async def probe(self, query: str, mode: Modo) -> RisultatoProbe: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------

# Nessuno dei quattro provider documenta un header `Retry-After` affidabile
# sulle risposte 429 (verificato il 2026-07-30). Il backoff non puo' dipendere
# da qualcosa che potrebbe non arrivare: esponenziale con jitter, e l'header lo
# si usa solo se c'e'.
# 529 e' l'`overloaded_error` di Anthropic: transitorio per definizione, e
# sotto carico arriva con regolarita'. Non ritentarlo trasformava un ingorgo
# di pochi secondi in un probe fallito a ogni ciclo.
STATI_DA_RITENTARE = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


def _attesa(tentativo: int, base: float, tetto: float) -> float:
    """Esponenziale con jitter pieno: evita che piu' probe ritentino in coro."""
    return min(tetto, base * (2**tentativo)) * (0.5 + random.random() / 2)


def timeout_probe(secondi: float) -> httpx.Timeout:
    """Timeout per fase, non un numero unico per tutto.

    `secondi` governa la LETTURA, che con la web search puo' legittimamente
    durare piu' di un minuto. Connect e pool invece restano brevi: un host
    irraggiungibile deve fallire in dieci secondi, non consumare l'intero
    budget del probe prima ancora di aver mandato la richiesta.
    """
    return httpx.Timeout(secondi, connect=10.0, pool=10.0)


async def richiesta_con_backoff(
    client: httpx.AsyncClient,
    *,
    provider: str,
    tentativi: int = 3,
    base: float = 2.0,
    tetto: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """POST con ritenti su 429/5xx. Solleva `ProviderError` tipizzato."""
    ultimo: Exception | None = None
    ultimo_status: int | None = None

    for tentativo in range(tentativi):
        try:
            risposta = await client.post(**kwargs)
        except httpx.TimeoutException as exc:
            ultimo = exc
            if tentativo == tentativi - 1:
                raise ProviderTimeoutError(
                    f"{provider}: timeout dopo {tentativi} tentativi"
                ) from exc
            await asyncio.sleep(_attesa(tentativo, base, tetto))
            continue
        except httpx.TransportError as exc:
            # ConnectError, ReadError, RemoteProtocolError: i blip transitori
            # di rete (keep-alive resettata dal peer, handshake fallito una
            # volta). Meritano un ritento quanto un timeout: fallire al primo
            # colpo era una delle due cause dei probe persi a ogni ciclo.
            ultimo = exc
            if tentativo == tentativi - 1:
                raise ProviderError(
                    f"{provider}: errore di rete dopo {tentativi} tentativi: {exc}"
                ) from exc
            await asyncio.sleep(_attesa(tentativo, base, tetto))
            continue
        except httpx.HTTPError as exc:
            raise ProviderError(f"{provider}: errore di rete: {exc}") from exc

        if risposta.status_code not in STATI_DA_RITENTARE:
            if risposta.is_error:
                raise ProviderError(
                    f"{provider}: HTTP {risposta.status_code}: {risposta.text[:400]}"
                )
            return risposta

        # Il corpo si conserva anche qui: un «HTTP 503» muto in `probes.error`
        # non dice se era un overload, una quota o una manutenzione.
        ultimo_status = risposta.status_code
        ultimo = ProviderError(f"{provider}: HTTP {risposta.status_code}: {risposta.text[:200]}")
        if tentativo == tentativi - 1:
            break

        attesa = _attesa(tentativo, base, tetto)
        # Se l'header c'e' lo si rispetta, ma non lo si pretende.
        if (retry_after := risposta.headers.get("retry-after")) is not None:
            with contextlib.suppress(ValueError):
                attesa = max(attesa, min(float(retry_after), tetto))
        log.warning(
            "risposta da ritentare",
            provider=provider,
            status=risposta.status_code,
            tentativo=tentativo + 1,
            attesa_s=round(attesa, 1),
        )
        await asyncio.sleep(attesa)

    # La classificazione guarda lo STATUS CODE, non la stringa dell'errore: un
    # corpo di risposta che contenesse "429" per altri motivi non deve
    # travestire un 503 da rate limit.
    if ultimo_status == 429:
        raise RateLimitError(f"{provider}: rate limit dopo {tentativi} tentativi ({ultimo})")
    raise ProviderError(f"{provider}: esauriti i tentativi ({ultimo})")
