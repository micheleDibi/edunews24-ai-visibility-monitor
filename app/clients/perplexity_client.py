"""Adapter Perplexity — Sonar API.

Verificato il 2026-07-30 (docs/providers.md, sezione Perplexity).

## Il campo giusto e' `search_results`, non `citations`

Il changelog di Perplexity dichiara `citations` "fully deprecated and removed"
da maggio 2025, ma lo schema OpenAPI corrente e gli esempi lo mostrano ancora
accanto a `search_results`. Si costruisce su `search_results`; `citations` e'
trattato come specchio legacy che puo' sparire senza preavviso. Al contrario,
costruire su `citations` significa che il giorno in cui completano la rimozione
il monitor restituisce zero fonti senza nessun errore.

## Recuperate contro citate

`search_results` e' l'insieme delle fonti recuperate. Quelle davvero citate
sono quelle il cui indice compare come marcatore `[n]` nel testo della
risposta. E' l'unico modo di distinguere i due segnali su questo provider.

## Il prompt di sistema non influenza il retrieval

Documentato: "The system prompt is not visible to search; it reaches the model
only at answer time." La ricerca e' guidata dal solo messaggio utente. Per noi
e' un vantaggio: il prompt non puo' perturbare la misura.
"""

from __future__ import annotations

import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog

from app.clients.base import (
    PROMPT_SISTEMA,
    PROMPT_SISTEMA_MEMORIA,
    CitazioneGrezza,
    Modo,
    ProviderError,
    RisultatoProbe,
    richiesta_con_backoff,
)
from app.core.config import Settings

log = structlog.get_logger(__name__)

BASE_URL = "https://api.perplexity.ai"

# I marcatori `[1]`, `[2]` nel testo mappano 1-based su `search_results`.
_MARCATORE = re.compile(r"\[(\d{1,2})\]")


class PerplexityAdapter:
    name = "perplexity"
    supports_retrieval = True

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not settings.perplexity_api_key:
            raise ValueError("PERPLEXITY_API_KEY assente")
        self.model = settings.perplexity_model
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=settings.probe_timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _corpo(self, query: str, mode: Modo) -> dict[str, Any]:
        sistema = PROMPT_SISTEMA if mode == "retrieval" else PROMPT_SISTEMA_MEMORIA
        corpo: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": query},
            ],
            # In streaming le fonti arrivano solo negli ultimi chunk: una
            # connessione caduta darebbe testo e zero fonti. Per un monitor a
            # lotti lo streaming non porta nulla e aggiunge un modo di rompersi.
            "stream": False,
        }

        if mode == "memory":
            # Presente nello schema OpenAPI ma non descritto nella prosa: da
            # verificare al primo probe reale controllando che `search_results`
            # torni vuoto e `num_search_queries` sia 0.
            corpo["disable_search"] = True
            return corpo

        # NIENTE `search_domain_filter`: mettere edunews24.it in allowlist
        # garantirebbe che compaia, distruggendo la metrica che si misura.
        corpo["web_search_options"] = {
            "search_context_size": self._settings.perplexity_search_context_size
        }
        return corpo

    async def probe(self, query: str, mode: Modo) -> RisultatoProbe:
        inizio = time.monotonic()
        risposta = await richiesta_con_backoff(
            self._client, provider=self.name, url="/v1/sonar", json=self._corpo(query, mode)
        )
        latenza = int((time.monotonic() - inizio) * 1000)

        try:
            dati = risposta.json()
        except ValueError as exc:
            raise ProviderError(f"perplexity: risposta non JSON: {risposta.text[:300]}") from exc

        testo = _testo(dati)
        citazioni = _citazioni(dati, testo)
        uso = dati.get("usage") or {}

        return RisultatoProbe(
            provider=self.name,
            model=dati.get("model") or self.model,
            mode=mode,
            answer_text=testo,
            citazioni=citazioni,
            input_tokens=uso.get("prompt_tokens"),
            output_tokens=uso.get("completion_tokens"),
            search_calls=uso.get("num_search_queries"),
            latency_ms=latenza,
            raw=dati,
            # Perplexity dichiara il costo esatto della chiamata, fascia di
            # prezzo per richiesta compresa. Vale piu' di qualunque stima da
            # listino: ricalcolarlo a mano sarebbe sbagliato per costruzione.
            cost_usd_provider=_costo(uso),
        )


def _testo(dati: dict[str, Any]) -> str | None:
    for scelta in dati.get("choices") or []:
        if isinstance(scelta, dict):
            messaggio = scelta.get("message")
            if isinstance(messaggio, dict) and (contenuto := messaggio.get("content")):
                return contenuto
    return None


def _citazioni(dati: dict[str, Any], testo: str | None) -> list[CitazioneGrezza]:
    """`search_results` come fonti recuperate, i marcatori `[n]` come citate."""
    risultati = dati.get("search_results")
    if not isinstance(risultati, list) or not risultati:
        # Specchio legacy, solo se `search_results` manca del tutto.
        legacy = dati.get("citations")
        if isinstance(legacy, list) and legacy:
            log.warning("perplexity: search_results assente, uso il campo legacy citations")
            risultati = [{"url": u} for u in legacy if isinstance(u, str)]
        else:
            return []

    citati = {int(n) for n in _MARCATORE.findall(testo or "")}

    citazioni: list[CitazioneGrezza] = []
    for posizione, voce in enumerate(risultati, start=1):
        if not isinstance(voce, dict):
            continue
        url = voce.get("url")
        titolo = voce.get("title")
        # Ogni fonte e' comunque stata recuperata...
        citazioni.append(CitazioneGrezza(url=url, title=titolo, kind="source", position=posizione))
        # ...e in piu' e' citata se il suo indice compare nel testo.
        if posizione in citati:
            citazioni.append(
                CitazioneGrezza(url=url, title=titolo, kind="citation", position=posizione)
            )

    if not citati and risultati:
        # Nessun marcatore: il modello ha risposto senza riferimenti espliciti.
        # Le fonti restano registrate come recuperate, non come citate.
        log.debug("perplexity: nessun marcatore [n] nel testo", fonti=len(risultati))

    return citazioni


def _costo(uso: dict[str, Any]) -> Decimal | None:
    costo = uso.get("cost")
    if not isinstance(costo, dict):
        return None
    totale = costo.get("total_cost")
    if totale is None:
        return None
    try:
        return Decimal(str(totale))
    except (InvalidOperation, ValueError):
        log.warning("perplexity: total_cost non interpretabile", valore=totale)
        return None
