"""Costo di un probe, da `pricing.yaml` piu' token e ricerche.

Due regole che tengono onesto il dato:

* **il costo dichiarato dal provider vince sempre.** Perplexity restituisce
  `usage.cost.total_cost` con la fascia per richiesta gia' inclusa: ricalcolarlo
  da un listino a fasce sarebbe sbagliato per costruzione.
* **un probe senza dati di usage non costa zero.** Si stima dal listino e si
  marca `cost_estimated = true`. Uno zero silenzioso e' il modo piu' facile per
  far sbagliare il kill switch: si spenderebbe senza vederlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.core.config import Settings, get_settings

log = structlog.get_logger(__name__)

# Token stimati quando il provider non dichiara l'uso. Volutamente generosi:
# per il kill switch e' meglio sovrastimare.
TOKEN_INPUT_STIMATI = 15_000
TOKEN_OUTPUT_STIMATI = 800

_CENTESIMI = Decimal("0.00001")


class ListinoMancanteError(RuntimeError):
    pass


@dataclass(frozen=True)
class Costo:
    usd: Decimal
    eur: Decimal
    stimato: bool


# La cache e' sul PERCORSO, non sulle Settings: un modello pydantic non e'
# hashable e `lru_cache` su di esso solleva TypeError al primo probe.
@lru_cache
def _carica_file(percorso: str, eta_massima_giorni: int) -> dict[str, Any]:
    file = Path(percorso)
    if not file.exists():
        raise ListinoMancanteError(
            f"Listino non trovato: {file}. Senza, i costi non sono calcolabili "
            "e il kill switch del budget non protegge nulla."
        )
    dati = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    _avvisa_se_vecchio(dati.get("updated"), eta_massima_giorni)
    return dati


def carica_listino(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    percorso = Path(settings.pricing_file)
    if not percorso.is_absolute():
        percorso = settings.repo_root / percorso
    return _carica_file(str(percorso), settings.pricing_max_age_days)


def _avvisa_se_vecchio(aggiornato: Any, eta_massima_giorni: int) -> None:
    if not isinstance(aggiornato, date):
        log.warning("pricing.yaml senza campo `updated` valido: eta' non verificabile")
        return
    giorni = (datetime.now(UTC).date() - aggiornato).days
    if giorni > eta_massima_giorni:
        log.warning(
            "pricing.yaml non aggiornato da troppo tempo: i costi registrati "
            "potrebbero non corrispondere a quelli fatturati",
            aggiornato=aggiornato.isoformat(),
            giorni=giorni,
            soglia=eta_massima_giorni,
        )


def _tariffe_modello(listino: dict[str, Any], provider: str, model: str) -> dict[str, float]:
    voce = (listino.get("providers") or {}).get(provider) or {}
    modelli = voce.get("models") or {}
    if model in modelli:
        return modelli[model]

    # Gli alias si risolvono in snapshot datati (`gpt-5.4-nano-2026-03-17`): si
    # cerca il prefisso piu' lungo che corrisponde, invece di far cadere il
    # costo a zero perche' il nome esatto non e' in tabella.
    candidati = [n for n in modelli if model.startswith(n)]
    if candidati:
        migliore = max(candidati, key=len)
        return modelli[migliore]

    log.warning(
        "modello assente dal listino: costo non calcolabile, aggiorna pricing.yaml",
        provider=provider,
        model=model,
    )
    return {}


def calcola(
    *,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    search_calls: int | None,
    costo_dichiarato_usd: Decimal | None = None,
    settings: Settings | None = None,
) -> Costo:
    settings = settings or get_settings()
    tasso = Decimal(str(settings.usd_eur_rate))

    if costo_dichiarato_usd is not None:
        usd = costo_dichiarato_usd
        return Costo(
            usd=usd.quantize(_CENTESIMI, rounding=ROUND_HALF_UP),
            eur=(usd * tasso).quantize(_CENTESIMI, rounding=ROUND_HALF_UP),
            stimato=False,
        )

    listino = carica_listino(settings)
    voce_provider = (listino.get("providers") or {}).get(provider) or {}
    tariffe = _tariffe_modello(listino, provider, model)

    stimato = input_tokens is None or output_tokens is None
    input_effettivi = input_tokens if input_tokens is not None else TOKEN_INPUT_STIMATI
    output_effettivi = output_tokens if output_tokens is not None else TOKEN_OUTPUT_STIMATI

    usd = Decimal("0")
    usd += Decimal(str(tariffe.get("input_per_1m", 0))) * Decimal(input_effettivi) / 1_000_000
    usd += Decimal(str(tariffe.get("output_per_1m", 0))) * Decimal(output_effettivi) / 1_000_000

    # Tariffa per ricerca (OpenAI, Anthropic, Gemini 3).
    if (per_search := voce_provider.get("per_search_usd")) is not None:
        if search_calls is None:
            stimato = True
            ricerche = 1
        else:
            ricerche = search_calls
        usd += Decimal(str(per_search)) * ricerche

    # Tariffa per richiesta (Gemini 2.5), indipendente dal numero di ricerche.
    if (per_request := voce_provider.get("per_request_usd")) is not None and search_calls:
        usd += Decimal(str(per_request))

    # Fascia per richiesta di Perplexity: solo come ripiego, perche' di norma il
    # provider dichiara il costo esatto e questa funzione non ci arriva.
    fasce = voce_provider.get("request_fee_usd_by_context") or {}
    if fasce:
        stimato = True
        per_modello: dict[str, Any] = fasce.get(model) or next(iter(fasce.values()), {})
        tariffa = per_modello.get(settings.perplexity_search_context_size)
        if tariffa is not None:
            usd += Decimal(str(tariffa))

    if not tariffe:
        stimato = True

    return Costo(
        usd=usd.quantize(_CENTESIMI, rounding=ROUND_HALF_UP),
        eur=(usd * tasso).quantize(_CENTESIMI, rounding=ROUND_HALF_UP),
        stimato=stimato,
    )
