"""Adapter dei provider, contro risposte HTTP finte.

Le risposte sono modellate sui campioni JSON delle documentazioni ufficiali
(vedi docs/providers.md). Sono i test che proteggono dalla modalita' di
fallimento peggiore di tutto il sistema: un nome di campo sbagliato non solleva
un'eccezione, restituisce zero citazioni — e zero citazioni somiglia
esattamente a "il giornale non e' citato".
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.clients.anthropic_client import AnthropicAdapter
from app.clients.base import RicercaNonEseguitaError
from app.clients.gemini_client import GeminiAdapter, GeminiDisabilitatoError
from app.clients.openai_client import OpenAIAdapter
from app.clients.perplexity_client import PerplexityAdapter
from app.core.config import get_settings


def _settings(**modifiche):
    base = {
        "openai_api_key": "sk-test",
        "perplexity_api_key": "pplx-test",
        "anthropic_api_key": "ant-test",
        "gemini_api_key": "goog-test",
    }
    return get_settings().model_copy(update={**base, **modifiche})


def _trasporto(payload: dict, *, status: int = 200) -> httpx.MockTransport:
    corpi: list[dict] = []

    def gestore(richiesta: httpx.Request) -> httpx.Response:
        corpi.append(json.loads(richiesta.content))
        return httpx.Response(status, json=payload)

    trasporto = httpx.MockTransport(gestore)
    trasporto.corpi_inviati = corpi  # type: ignore[attr-defined]
    return trasporto


# ---------------------------------------------------------------------------
# OpenAI — Responses API
# ---------------------------------------------------------------------------

RISPOSTA_OPENAI = {
    "model": "gpt-5.6-luna-2026-05-01",
    "usage": {"input_tokens": 15234, "output_tokens": 812, "total_tokens": 16046},
    "output": [
        {
            "type": "web_search_call",
            "id": "ws_67c9",
            "status": "completed",
            "action": {
                "type": "search",
                "query": "concorso docenti 2026",
                "sources": [
                    "https://www.miur.gov.it/concorso",
                    {"url": "https://edunews24.it/scuola/concorso-docenti-2026", "title": "Edu"},
                    "oai-sports",
                ],
            },
        },
        {
            "type": "web_search_call",
            "id": "ws_67ca",
            "status": "completed",
            "action": {"type": "open_page", "url": "https://x.it"},
        },
        {
            "id": "msg_67c9",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "I posti a bando salgono a 30.000.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "start_index": 0,
                            "end_index": 33,
                            "url": "https://www.miur.gov.it/concorso?utm_source=openai",
                            "title": "Ministero",
                        }
                    ],
                }
            ],
        },
    ],
}


class TestOpenAI:
    async def test_estrae_testo_citazioni_e_fonti(self):
        adapter = OpenAIAdapter(_settings(), transport=_trasporto(RISPOSTA_OPENAI))
        try:
            r = await adapter.probe("Quanti posti al concorso docenti 2026?", "retrieval")
        finally:
            await adapter.close()

        assert r.answer_text == "I posti a bando salgono a 30.000."
        assert r.input_tokens == 15234
        assert r.output_tokens == 812
        # Solo `action.type == "search"`: open_page non e' fatturato.
        assert r.search_calls == 1
        # Il modello RISOLTO, non quello richiesto.
        assert r.model == "gpt-5.6-luna-2026-05-01"

        citate = [c for c in r.citazioni if c.kind == "citation"]
        fonti = [c for c in r.citazioni if c.kind == "source"]
        assert len(citate) == 1
        assert citate[0].url.startswith("https://www.miur.gov.it/concorso")
        # Le fonti consultate sono un sovrainsieme, e i feed non-web sono esclusi.
        assert len(fonti) == 2
        assert not any("oai-" in (f.url or "") for f in fonti)

    async def test_gestisce_le_fonti_sia_come_stringa_sia_come_oggetto(self):
        """La forma degli elementi di `action.sources` non e' documentata."""
        adapter = OpenAIAdapter(_settings(), transport=_trasporto(RISPOSTA_OPENAI))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()
        url_fonti = {c.url for c in r.citazioni if c.kind == "source"}
        assert "https://www.miur.gov.it/concorso" in url_fonti
        assert "https://edunews24.it/scuola/concorso-docenti-2026" in url_fonti

    async def test_forza_la_ricerca_nella_richiesta(self):
        """Con `auto` il modello risponderebbe a memoria e la misura sarebbe falsa."""
        trasporto = _trasporto(RISPOSTA_OPENAI)
        adapter = OpenAIAdapter(_settings(), transport=trasporto)
        try:
            await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        corpo = trasporto.corpi_inviati[0]
        assert corpo["tool_choice"] == "required"
        assert corpo["tools"][0]["type"] == "web_search"
        assert corpo["include"] == ["web_search_call.action.sources"]
        assert corpo["store"] is False

    async def test_dichiara_la_localizzazione_italiana(self):
        """Senza, i risultati pendono e la misura e' distorta contro i domini italiani."""
        trasporto = _trasporto(RISPOSTA_OPENAI)
        adapter = OpenAIAdapter(_settings(), transport=trasporto)
        try:
            await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        posizione = trasporto.corpi_inviati[0]["tools"][0]["user_location"]
        assert posizione["country"] == "IT"
        assert posizione["timezone"] == "Europe/Rome"

    async def test_nessuna_ricerca_eseguita_non_e_un_non_citato(self):
        senza_ricerche = {
            "model": "gpt-5.6-luna",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Risposta a memoria.", "annotations": []}
                    ],
                }
            ],
        }
        adapter = OpenAIAdapter(_settings(), transport=_trasporto(senza_ricerche))
        try:
            with pytest.raises(RicercaNonEseguitaError):
                await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

    async def test_modalita_memoria_non_manda_strumenti(self):
        senza_ricerche = {
            "model": "gpt-5.6-luna",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "So che...", "annotations": []}],
                }
            ],
        }
        trasporto = _trasporto(senza_ricerche)
        adapter = OpenAIAdapter(_settings(), transport=trasporto)
        try:
            r = await adapter.probe("x", "memory")
        finally:
            await adapter.close()

        corpo = trasporto.corpi_inviati[0]
        assert "tools" not in corpo
        assert corpo["tool_choice"] == "none"
        assert r.citazioni == []
        assert r.mode == "memory"


# ---------------------------------------------------------------------------
# Perplexity — Sonar API
# ---------------------------------------------------------------------------

RISPOSTA_PERPLEXITY = {
    "model": "sonar",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "I posti salgono a 30.000 [1]. Le domande si chiudono a marzo [3].",
            }
        }
    ],
    "search_results": [
        {"url": "https://edunews24.it/scuola/concorso-docenti-2026", "title": "Concorso"},
        {"url": "https://orizzontescuola.it/a", "title": "OS"},
        {"url": "https://www.miur.gov.it/b", "title": "MIM"},
    ],
    "usage": {
        "prompt_tokens": 120,
        "completion_tokens": 340,
        "num_search_queries": 2,
        "search_context_size": "low",
        "cost": {"request_cost": 0.005, "total_cost": 0.0056},
    },
}


class TestPerplexity:
    async def test_distingue_recuperate_da_citate(self):
        adapter = PerplexityAdapter(_settings(), transport=_trasporto(RISPOSTA_PERPLEXITY))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        fonti = [c for c in r.citazioni if c.kind == "source"]
        citate = [c for c in r.citazioni if c.kind == "citation"]
        assert len(fonti) == 3, "ogni search_result e' stato recuperato"
        # Nel testo compaiono i marcatori [1] e [3].
        assert {c.position for c in citate} == {1, 3}
        assert citate[0].url == "https://edunews24.it/scuola/concorso-docenti-2026"

    async def test_usa_il_costo_dichiarato_dal_provider(self):
        adapter = PerplexityAdapter(_settings(), transport=_trasporto(RISPOSTA_PERPLEXITY))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()
        assert r.cost_usd_provider == Decimal("0.0056")
        assert r.search_calls == 2

    async def test_ripiego_sul_campo_legacy_citations(self):
        legacy = {
            "model": "sonar",
            "choices": [{"message": {"content": "Testo [1]."}}],
            "citations": ["https://edunews24.it/scuola/x"],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        adapter = PerplexityAdapter(_settings(), transport=_trasporto(legacy))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()
        assert any(c.url == "https://edunews24.it/scuola/x" for c in r.citazioni)

    async def test_non_filtra_mai_sul_proprio_dominio(self):
        """Mettersi in allowlist garantirebbe di comparire: distruggerebbe la metrica."""
        trasporto = _trasporto(RISPOSTA_PERPLEXITY)
        adapter = PerplexityAdapter(_settings(), transport=trasporto)
        try:
            await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        corpo = trasporto.corpi_inviati[0]
        assert "search_domain_filter" not in corpo
        assert corpo["stream"] is False

    async def test_modalita_memoria_disattiva_la_ricerca(self):
        vuota = {
            "model": "sonar",
            "choices": [{"message": {"content": "So che..."}}],
            "search_results": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "num_search_queries": 0},
        }
        trasporto = _trasporto(vuota)
        adapter = PerplexityAdapter(_settings(), transport=trasporto)
        try:
            r = await adapter.probe("x", "memory")
        finally:
            await adapter.close()

        assert trasporto.corpi_inviati[0]["disable_search"] is True
        assert "web_search_options" not in trasporto.corpi_inviati[0]
        assert r.citazioni == []


# ---------------------------------------------------------------------------
# Anthropic — Messages API
# ---------------------------------------------------------------------------

RISPOSTA_ANTHROPIC = {
    "model": "claude-sonnet-5-20260101",
    "content": [
        {
            "type": "server_tool_use",
            "id": "srvtoolu_1",
            "name": "web_search",
            "input": {"query": "concorso"},
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_1",
            "content": [
                {
                    "type": "web_search_result",
                    "url": "https://edunews24.it/scuola/concorso-docenti-2026",
                    "title": "Concorso docenti",
                    "page_age": "July 20, 2026",
                },
                {"type": "web_search_result", "url": "https://miur.gov.it/x", "title": "MIM"},
            ],
        },
        {
            "type": "text",
            "text": "I posti salgono a 30.000.",
            "citations": [
                {
                    "type": "web_search_result_location",
                    "url": "https://edunews24.it/scuola/concorso-docenti-2026",
                    "title": "Concorso docenti",
                    "cited_text": "trentamila posti",
                }
            ],
        },
    ],
    "usage": {
        "input_tokens": 9000,
        "output_tokens": 400,
        "server_tool_use": {"web_search_requests": 3},
    },
}


class TestAnthropic:
    async def test_estrae_entrambi_i_segnali(self):
        adapter = AnthropicAdapter(_settings(), transport=_trasporto(RISPOSTA_ANTHROPIC))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        assert r.answer_text == "I posti salgono a 30.000."
        assert r.search_calls == 3
        assert r.model == "claude-sonnet-5-20260101"
        assert [c.kind for c in r.citazioni].count("source") == 2
        assert [c.kind for c in r.citazioni].count("citation") == 1

    async def test_usa_lautenticazione_x_api_key(self):
        richieste: list[httpx.Request] = []

        def gestore(richiesta: httpx.Request) -> httpx.Response:
            richieste.append(richiesta)
            return httpx.Response(200, json=RISPOSTA_ANTHROPIC)

        adapter = AnthropicAdapter(_settings(), transport=httpx.MockTransport(gestore))
        try:
            await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        assert richieste[0].headers["x-api-key"] == "ant-test"
        assert "authorization" not in richieste[0].headers
        assert richieste[0].headers["anthropic-version"] == "2023-06-01"

    async def test_una_ricerca_in_errore_non_produce_fonti_finte(self):
        con_errore = {
            "model": "claude-sonnet-5",
            "content": [
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srvtoolu_1",
                    "content": {
                        "type": "web_search_tool_result_error",
                        "error_code": "max_uses_exceeded",
                    },
                },
                {"type": "text", "text": "Non ho trovato fonti."},
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "server_tool_use": {"web_search_requests": 1},
            },
        }
        adapter = AnthropicAdapter(_settings(), transport=_trasporto(con_errore))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()
        assert r.citazioni == []

    async def test_modalita_memoria_omette_gli_strumenti(self):
        senza = {
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "So che..."}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        trasporto = _trasporto(senza)
        adapter = AnthropicAdapter(_settings(), transport=trasporto)
        try:
            r = await adapter.probe("x", "memory")
        finally:
            await adapter.close()

        assert "tools" not in trasporto.corpi_inviati[0]
        assert r.search_calls == 0

    async def test_senza_ricerche_in_retrieval_solleva(self):
        senza = {
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "Risposta a memoria."}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        adapter = AnthropicAdapter(_settings(), transport=_trasporto(senza))
        try:
            with pytest.raises(RicercaNonEseguitaError):
                await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()


# ---------------------------------------------------------------------------
# Gemini — spento per vincoli di licenza
# ---------------------------------------------------------------------------


class TestGemini:
    def test_non_parte_senza_abilitazione_esplicita(self):
        """I termini dell'API vietano di raccogliere e analizzare i Link."""
        with pytest.raises(GeminiDisabilitatoError, match="termini"):
            GeminiAdapter(_settings(gemini_enabled=False))

    async def test_se_abilitato_estrae_le_annotazioni(self):
        risposta = {
            "model": "gemini-2.5-flash",
            "usage": {
                "total_input_tokens": 500,
                "total_output_tokens": 200,
                "grounding_tool_count": 2,
            },
            "steps": [
                {"type": "google_search_call", "arguments": {"queries": ["concorso docenti"]}},
                {
                    "type": "model_output",
                    "content": [
                        {
                            "type": "text",
                            "text": "I posti salgono a 30.000.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://edunews24.it/scuola/concorso-docenti-2026",
                                    "title": "edunews24.it",
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        adapter = GeminiAdapter(_settings(gemini_enabled=True), transport=_trasporto(risposta))
        try:
            r = await adapter.probe("x", "retrieval")
        finally:
            await adapter.close()

        assert r.search_calls == 2
        assert len(r.citazioni) == 1
        assert r.citazioni[0].url == "https://edunews24.it/scuola/concorso-docenti-2026"
