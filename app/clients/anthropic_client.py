"""Adapter Anthropic — Messages API con il tool server-side di web search.

Verificato il 2026-07-30 (docs/providers.md, sezione Anthropic).

Anthropic e' il provider con la separazione piu' netta fra i due segnali, e la
espone senza doverla dedurre:

* `web_search_tool_result` -> le fonti recuperate, il ventaglio che il modello
  ha visto;
* `citations` sui blocchi di testo -> le fonti che hanno davvero sostenuto una
  frase della risposta.

Si usa la versione base del tool (`web_search_20250305`) e non la piu' recente:
le versioni con dynamic filtering annidano i blocchi dentro risultati di code
execution, e un layout annidato e' un modo in piu' di perdere silenziosamente
citazioni. Il parser gestisce comunque l'annidamento, per sicurezza.

Nota: l'autenticazione e' `x-api-key`, non `Authorization: Bearer`.
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
)
from app.core.config import Settings

log = structlog.get_logger(__name__)

BASE_URL = "https://api.anthropic.com"
VERSIONE_API = "2023-06-01"


class AnthropicAdapter:
    name = "anthropic"
    supports_retrieval = True

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY assente")
        self.model = settings.anthropic_model
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=settings.probe_timeout_seconds,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": VERSIONE_API,
                "content-type": "application/json",
            },
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _corpo(self, query: str, mode: Modo) -> dict[str, Any]:
        # Tutto identico fra i due modi tranne il prompt e la presenza del
        # tool, cosi' i due bracci sono confrontabili.
        corpo: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._settings.anthropic_max_tokens,
            "system": PROMPT_SISTEMA if mode == "retrieval" else PROMPT_SISTEMA_MEMORIA,
            "messages": [{"role": "user", "content": query}],
        }
        if mode == "memory":
            # Si omette `tools` del tutto: con `tools: []` il comportamento non
            # e' documentato.
            return corpo

        corpo["tools"] = [
            {
                "type": self._settings.anthropic_web_search_tool,
                "name": "web_search",
                # Unico freno di spesa reale: ogni ricerca e' fatturata a parte.
                "max_uses": self._settings.anthropic_max_uses,
                "user_location": {
                    "type": "approximate",
                    "city": self._settings.probe_city,
                    "region": self._settings.probe_region,
                    "country": self._settings.probe_country,
                    "timezone": self._settings.tz,
                },
            }
        ]
        return corpo

    async def probe(self, query: str, mode: Modo) -> RisultatoProbe:
        inizio = time.monotonic()
        risposta = await richiesta_con_backoff(
            self._client, provider=self.name, url="/v1/messages", json=self._corpo(query, mode)
        )
        latenza = int((time.monotonic() - inizio) * 1000)

        try:
            dati = risposta.json()
        except ValueError as exc:
            raise ProviderError(f"anthropic: risposta non JSON: {risposta.text[:300]}") from exc

        testo, citazioni = _estrai(dati.get("content") or [])
        uso = dati.get("usage") or {}
        ricerche = _conta_ricerche(uso)

        if mode == "retrieval" and ricerche == 0:
            raise RicercaNonEseguitaError("anthropic: nessuna ricerca eseguita")

        return RisultatoProbe(
            provider=self.name,
            model=dati.get("model") or self.model,
            mode=mode,
            answer_text=testo,
            citazioni=citazioni,
            input_tokens=uso.get("input_tokens"),
            output_tokens=uso.get("output_tokens"),
            search_calls=ricerche,
            latency_ms=latenza,
            raw=dati,
        )


def _estrai(blocchi: list[Any]) -> tuple[str | None, list[CitazioneGrezza]]:
    """Percorre i blocchi, scendendo anche in quelli annidati."""
    pezzi: list[str] = []
    citazioni: list[CitazioneGrezza] = []

    for blocco in blocchi:
        if not isinstance(blocco, dict):
            continue
        tipo = blocco.get("type")

        if tipo == "text":
            if testo := blocco.get("text"):
                pezzi.append(testo)
            for posizione, cit in enumerate(blocco.get("citations") or [], start=1):
                if isinstance(cit, dict) and cit.get("type") == "web_search_result_location":
                    citazioni.append(
                        CitazioneGrezza(
                            url=cit.get("url"),
                            title=cit.get("title"),
                            kind="citation",
                            position=posizione,
                        )
                    )

        elif tipo == "web_search_tool_result":
            interno = blocco.get("content")
            if isinstance(interno, dict) and interno.get("type") == "web_search_tool_result_error":
                log.warning(
                    "anthropic: ricerca in errore",
                    codice=interno.get("error_code"),
                )
                continue
            for posizione, voce in enumerate(interno or [], start=1):
                if isinstance(voce, dict) and voce.get("type") == "web_search_result":
                    citazioni.append(
                        CitazioneGrezza(
                            url=voce.get("url"),
                            title=voce.get("title"),
                            kind="source",
                            position=posizione,
                        )
                    )

        elif tipo in ("code_execution_tool_result", "container_upload"):
            # Con dynamic filtering i blocchi di ricerca finiscono qui dentro.
            annidato = blocco.get("content")
            if isinstance(annidato, list):
                testo_annidato, citazioni_annidate = _estrai(annidato)
                if testo_annidato:
                    pezzi.append(testo_annidato)
                citazioni.extend(citazioni_annidate)

    return ("\n".join(pezzi) or None), citazioni


def _conta_ricerche(uso: dict[str, Any]) -> int:
    """`usage.server_tool_use.web_search_requests`, assente in modalita' memory."""
    server = uso.get("server_tool_use")
    if not isinstance(server, dict):
        return 0
    valore = server.get("web_search_requests")
    return int(valore) if isinstance(valore, int) else 0
