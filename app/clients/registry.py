"""Costruzione degli adapter attivi.

Chiave assente = adapter disattivato con un log informativo, non un errore: si
deve poter girare con un solo provider configurato, e un `run-once` non deve
fallire perche' manca una chiave che non serve.
"""

from __future__ import annotations

import structlog

from app.clients.anthropic_client import AnthropicAdapter
from app.clients.base import ProviderAdapter
from app.clients.gemini_client import GeminiAdapter, GeminiDisabilitatoError
from app.clients.openai_client import OpenAIAdapter
from app.clients.perplexity_client import PerplexityAdapter
from app.core.config import Settings

log = structlog.get_logger(__name__)

# Ordine di priorita' della specifica: prima i due con le citazioni piu'
# affidabili.
COSTRUTTORI = (
    ("openai", OpenAIAdapter),
    ("perplexity", PerplexityAdapter),
    ("anthropic", AnthropicAdapter),
    ("gemini", GeminiAdapter),
)


def costruisci_adapter(settings: Settings, solo: str | None = None) -> list[ProviderAdapter]:
    """Gli adapter per cui esiste una chiave e che sono abilitati."""
    adapter: list[ProviderAdapter] = []

    for nome, classe in COSTRUTTORI:
        if solo and nome != solo:
            continue
        try:
            adapter.append(classe(settings))
        except GeminiDisabilitatoError as exc:
            log.warning(
                "provider disattivato per vincoli di licenza", provider=nome, motivo=str(exc)
            )
        except ValueError:
            log.info("provider non configurato, adapter disattivato", provider=nome)

    if solo and not adapter:
        raise ValueError(
            f"provider '{solo}' non disponibile: chiave assente, oppure disattivato. "
            f"Provider configurati: {', '.join(settings.enabled_providers) or 'nessuno'}"
        )

    log.info("adapter attivi", provider=[a.name for a in adapter])
    return adapter


async def chiudi_adapter(adapter: list[ProviderAdapter]) -> None:
    for a in adapter:
        await a.close()
