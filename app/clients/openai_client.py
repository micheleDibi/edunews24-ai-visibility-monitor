"""Adapter OpenAI — Responses API con il tool `web_search`.

Parametri e path di estrazione verificati sulla documentazione ufficiale il
2026-07-30 (docs/providers.md, sezione OpenAI).

## Due cose che decidono se la misura vale

`tool_choice: "required"`. Con il default `auto` il modello risponde ad alcune
domande italiane a memoria, non emette nessun `web_search_call` e non produce
nessuna annotazione: la dashboard leggerebbe "edunews24.it non citato" dove la
verita' e' "nessuna ricerca e' avvenuta". Si forza la ricerca, e in piu' si
verifica che sia davvero avvenuta prima di registrare il dato.

`user_location`. Senza, i risultati pendono verso la geografia di default e le
domande italiane fanno emergere meno domini italiani.
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

# Etichette che OpenAI mette fra le `action.sources` per i feed di terze parti:
# non sono URL e `urlparse` ne farebbe host spazzatura.
FEED_NON_WEB = frozenset({"oai-sports", "oai-weather", "oai-finance"})


class OpenAIAdapter:
    name = "openai"
    supports_retrieval = True

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY assente")
        self.model = settings.openai_model
        self._settings = settings
        # `transport` serve solo ai test, per iniettare risposte finte.
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            timeout=timeout_probe(settings.probe_timeout_seconds),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _corpo(self, query: str, mode: Modo) -> dict[str, Any]:
        # `store: false` — questo e' un banco di misura, non c'e' motivo di
        # lasciare 200 conversazioni al giorno sui server del provider.
        corpo: dict[str, Any] = {"model": self.model, "input": query, "store": False}

        if mode == "memory":
            corpo["instructions"] = PROMPT_SISTEMA_MEMORIA
            # Omettere `tools` E fissare "none": la forma documentata senza
            # ambiguita'. `tools: []` non e' garantito equivalente.
            corpo["tool_choice"] = "none"
            return corpo

        corpo["instructions"] = PROMPT_SISTEMA
        corpo["tools"] = [
            {
                "type": "web_search",
                "search_context_size": self._settings.openai_search_context_size,
                "user_location": {
                    "type": "approximate",
                    "country": self._settings.probe_country,
                    "city": self._settings.probe_city,
                    "region": self._settings.probe_region,
                    "timezone": self._settings.tz,
                },
            }
        ]
        corpo["tool_choice"] = "required"
        # Restituisce l'elenco completo delle URL consultate, che e' un
        # sovrainsieme delle citate: e' il segnale "recuperato ma non citato".
        corpo["include"] = ["web_search_call.action.sources"]
        return corpo

    async def probe(self, query: str, mode: Modo) -> RisultatoProbe:
        inizio = time.monotonic()
        risposta = await richiesta_con_backoff(
            self._client, provider=self.name, url="/responses", json=self._corpo(query, mode)
        )
        latenza = int((time.monotonic() - inizio) * 1000)

        try:
            dati = risposta.json()
        except ValueError as exc:
            raise ProviderError(f"openai: risposta non JSON: {risposta.text[:300]}") from exc

        testo, citazioni = _estrai_testo_e_citazioni(dati)
        ricerche = _conta_ricerche(dati)

        if mode == "retrieval" and ricerche == 0:
            # Campione non valido, non un errore: registrarlo come "non citato"
            # significherebbe scrivere una misura al posto di un buco.
            raise RicercaNonEseguitaError(
                "openai: nessuna ricerca eseguita nonostante tool_choice=required"
            )

        uso = dati.get("usage") or {}
        return RisultatoProbe(
            provider=self.name,
            # Il modello risolto, non quello richiesto: gli alias si spostano.
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


def _estrai_testo_e_citazioni(dati: dict[str, Any]) -> tuple[str | None, list[CitazioneGrezza]]:
    """response.output[] -> message -> content[] -> output_text -> annotations[]."""
    pezzi_testo: list[str] = []
    citazioni: list[CitazioneGrezza] = []

    for elemento in dati.get("output") or []:
        if not isinstance(elemento, dict):
            continue
        tipo = elemento.get("type")

        if tipo == "message":
            for blocco in elemento.get("content") or []:
                if not isinstance(blocco, dict) or blocco.get("type") != "output_text":
                    continue
                if testo := blocco.get("text"):
                    pezzi_testo.append(testo)
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

        elif tipo == "web_search_call":
            citazioni.extend(_fonti_consultate(elemento))

    return ("\n".join(pezzi_testo) or None), citazioni


def _fonti_consultate(chiamata: dict[str, Any]) -> list[CitazioneGrezza]:
    """`web_search_call.action.sources`, la cui forma non e' documentata.

    La documentazione la descrive come "the complete list of URLs the model
    consulted" ma non mostra un esempio di singolo elemento: potrebbe essere
    una stringa nuda o un oggetto con una chiave `url`. Si gestiscono entrambe
    invece di scommettere, perche' sbagliare qui non produce un errore —
    produce zero fonti.
    """
    azione = chiamata.get("action")
    if not isinstance(azione, dict):
        return []

    fonti: list[CitazioneGrezza] = []
    for posizione, fonte in enumerate(azione.get("sources") or [], start=1):
        url: str | None = None
        titolo: str | None = None
        if isinstance(fonte, str):
            url = fonte
        elif isinstance(fonte, dict):
            url = fonte.get("url") or fonte.get("uri")
            titolo = fonte.get("title")

        if not url or url in FEED_NON_WEB:
            continue
        fonti.append(CitazioneGrezza(url=url, title=titolo, kind="source", position=posizione))
    return fonti


def _conta_ricerche(dati: dict[str, Any]) -> int:
    """Solo `action.type == "search"`.

    I modelli con reasoning emettono liberamente anche `open_page` e
    `find_in_page`, che non sono fatturati: contarli gonfierebbe la stima di
    spesa e il numero di ricerche registrato.
    """
    quante = 0
    for elemento in dati.get("output") or []:
        if not isinstance(elemento, dict) or elemento.get("type") != "web_search_call":
            continue
        if elemento.get("status") not in (None, "completed"):
            continue
        azione = elemento.get("action")
        if isinstance(azione, dict) and azione.get("type") == "search":
            quante += 1
    return quante
