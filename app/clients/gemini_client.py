"""Adapter Google Gemini — Interactions API con il tool `google_search`.

## ATTENZIONE: DISATTIVATO PER DEFAULT, E NON E' UNA DIMENTICANZA

I termini dell'API Gemini vietano esplicitamente cio' che questo servizio fa
con i risultati di grounding. Testo verbatim da
https://ai.google.dev/gemini-api/terms, verificato il 2026-07-30:

    "You will not, and will not allow your end user or any third party to,
    cache, frame, syndicate, resell, analyze, train on, or otherwise learn from
    Grounded Results or Search Suggestions."

    "For example, using programmatic or automated means to collect Links, using
    Links to build an index, or using Links to identify destination pages for
    crawling or scraping"

    "You will only display the Grounded Results with the associated Search
    Suggestion(s) to the end user who submitted the prompt."

Un monitor di visibilita' manda prompt in modo programmatico, raccoglie i Link,
li conserva in una tabella e li analizza per contare quante volte compare un
dominio, senza mostrarli ad alcun utente finale. Le tre clausole lo descrivono
tutte e tre.

L'adapter esiste perche' il canale Google e' quello che alimenta le AI
Overviews e quindi il piu' rilevante da misurare, ma parte solo se si imposta
`GEMINI_ENABLED=true`. Fallo dopo un parere legale o un permesso scritto da
Google, non prima.

## Perche' la Interactions API e non `generateContent`

Sulla vecchia `generateContent` le fonti arrivano in
`groundingChunks[].web.uri`, che sono involucri di redirect
`vertexaisearch.cloud.google.com/grounding-api-redirect/<token>`: il dominio
reale dell'editore non e' ricavabile senza seguire il redirect — e seguirlo e'
proprio la "programmatic collection of Links" che i termini vietano. La
Interactions API restituisce annotazioni `url_citation` con URL diretti.

Confidenza media su questo punto: la documentazione descrive il campo solo come
"The URL", senza garantire che sia l'URL dell'editore. Al primo probe reale il
codice verifica che nessun host sia `vertexaisearch.cloud.google.com`, e se lo
trova il parser lo marca `unresolved` invece di indovinare.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.clients.base import (
    PROMPT_SISTEMA,
    PROMPT_SISTEMA_MEMORIA,
    CitazioneGrezza,
    Modo,
    ProviderError,
    RicercaNonEseguitaError,
    RisultatoProbe,
    richiesta_con_backoff,
    timeout_probe,
)
from app.core.config import Settings

log = structlog.get_logger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiDisabilitatoError(RuntimeError):
    """Chiave presente ma `GEMINI_ENABLED` non impostato. Vedi il docstring."""


class GeminiAdapter:
    name = "gemini"
    supports_retrieval = True

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY assente")
        if not settings.gemini_enabled:
            raise GeminiDisabilitatoError(
                "L'adapter Gemini e' disattivato. I termini dell'API vietano di "
                "raccogliere e analizzare in modo programmatico i link dei risultati "
                "di grounding, che e' cio' che questo servizio fa. Abilitalo con "
                "GEMINI_ENABLED=true solo dopo un parere legale o un permesso scritto "
                "da Google. Vedi docs/providers.md."
            )
        self.model = settings.gemini_model
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout_probe(settings.probe_timeout_seconds),
            headers={
                "x-goog-api-key": settings.gemini_api_key,
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _corpo(self, query: str, mode: Modo) -> dict[str, Any]:
        corpo: dict[str, Any] = {
            "model": self.model,
            "input": query,
            "system_instruction": PROMPT_SISTEMA if mode == "retrieval" else PROMPT_SISTEMA_MEMORIA,
            "store": False,
        }
        if mode == "retrieval":
            corpo["tools"] = [{"type": "google_search"}]
        # In memoria si omette `tools`: nessuno strumento e' attivo per default.
        return corpo

    async def probe(self, query: str, mode: Modo) -> RisultatoProbe:
        inizio = time.monotonic()
        risposta = await richiesta_con_backoff(
            self._client,
            provider=self.name,
            url="/v1beta/interactions",
            json=self._corpo(query, mode),
        )
        latenza = int((time.monotonic() - inizio) * 1000)

        try:
            dati = risposta.json()
        except ValueError as exc:
            raise ProviderError(f"gemini: risposta non JSON: {risposta.text[:300]}") from exc

        testo, citazioni = _estrai(dati)
        ricerche = _conta_ricerche(dati)

        if mode == "retrieval" and ricerche == 0:
            raise RicercaNonEseguitaError("gemini: nessuna ricerca di grounding eseguita")

        uso = dati.get("usage") or {}
        return RisultatoProbe(
            provider=self.name,
            model=dati.get("model") or self.model,
            mode=mode,
            answer_text=testo,
            citazioni=citazioni,
            input_tokens=uso.get("total_input_tokens"),
            output_tokens=uso.get("total_output_tokens"),
            search_calls=ricerche,
            latency_ms=latenza,
            raw=dati,
        )


def _estrai(dati: dict[str, Any]) -> tuple[str | None, list[CitazioneGrezza]]:
    """steps[] -> model_output -> content[] -> text -> annotations[] url_citation."""
    pezzi: list[str] = []
    citazioni: list[CitazioneGrezza] = []

    for passo in dati.get("steps") or []:
        if not isinstance(passo, dict) or passo.get("type") != "model_output":
            continue
        for blocco in passo.get("content") or []:
            if not isinstance(blocco, dict) or blocco.get("type") != "text":
                continue
            if testo := blocco.get("text"):
                pezzi.append(testo)
            for posizione, ann in enumerate(blocco.get("annotations") or [], start=1):
                if isinstance(ann, dict) and ann.get("type") == "url_citation":
                    citazioni.append(
                        CitazioneGrezza(
                            url=ann.get("url"),
                            title=ann.get("title"),
                            kind="citation",
                            position=posizione,
                        )
                    )

    return ("\n".join(pezzi) or None), citazioni


def _conta_ricerche(dati: dict[str, Any]) -> int:
    """`usage.grounding_tool_count`, con ripiego sul conteggio dei passi.

    Su Gemini 3 la fatturazione e' per singola query di ricerca, non per
    richiesta: una domanda puo' farne tre o cinque in silenzio. Questo numero
    e' il consumo reale, non una stima.
    """
    uso = dati.get("usage") or {}
    conteggio = uso.get("grounding_tool_count")
    if isinstance(conteggio, int):
        return conteggio
    if isinstance(conteggio, list):
        totale = 0
        for voce in conteggio:
            if isinstance(voce, int):
                totale += voce
            elif isinstance(voce, dict):
                valore = voce.get("count") or voce.get("value")
                if isinstance(valore, int):
                    totale += valore
        if totale:
            return totale

    quante = 0
    for passo in dati.get("steps") or []:
        if isinstance(passo, dict) and passo.get("type") == "google_search_call":
            argomenti = passo.get("arguments")
            if isinstance(argomenti, dict) and isinstance(argomenti.get("queries"), list):
                quante += len(argomenti["queries"])
            else:
                quante += 1
    return quante
