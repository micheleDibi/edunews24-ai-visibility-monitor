"""Calcolo dei costi. E' il percorso dei soldi: un errore qui si paga.

Nessun database: `pricing.calcola` e' pura, legge solo `pricing.yaml`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from app.core.config import get_settings
from app.services import pricing


@pytest.fixture(autouse=True)
def _cache_pulita():
    # Il listino e' memoizzato sul percorso: i test che lo sostituiscono
    # devono partire da una cache vuota.
    pricing._carica_file.cache_clear()
    yield
    pricing._carica_file.cache_clear()


def _settings(**modifiche):
    return get_settings().model_copy(update=modifiche)


class TestCostoDichiarato:
    def test_il_costo_del_provider_vince_e_non_e_stimato(self):
        """Perplexity dichiara il costo esatto, fascia per richiesta inclusa."""
        costo = pricing.calcola(
            provider="perplexity",
            model="sonar",
            input_tokens=120,
            output_tokens=340,
            search_calls=2,
            costo_dichiarato_usd=Decimal("0.0056"),
            settings=_settings(usd_eur_rate=0.92),
        )
        assert costo.usd == Decimal("0.00560")
        assert costo.eur == Decimal("0.00515")
        assert costo.stimato is False

    def test_non_ricalcola_nemmeno_se_i_token_ci_sono(self):
        """Ricalcolare una tariffa a fasce a mano e' sbagliato per costruzione."""
        dichiarato = pricing.calcola(
            provider="perplexity",
            model="sonar",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            search_calls=99,
            costo_dichiarato_usd=Decimal("0.0056"),
        )
        assert dichiarato.usd == Decimal("0.00560")


class TestCostoDaListino:
    def test_token_piu_tariffa_per_ricerca(self):
        """gpt-5.6-luna: $1/1M input, $6/1M output, $0.01 per ricerca."""
        costo = pricing.calcola(
            provider="openai",
            model="gpt-5.6-luna",
            input_tokens=15_234,
            output_tokens=812,
            search_calls=1,
            settings=_settings(usd_eur_rate=0.92),
        )
        # 0.015234 + 0.004872 + 0.01 = 0.030106
        assert costo.usd == Decimal("0.03011")
        assert costo.eur == Decimal("0.02770")
        assert costo.stimato is False

    def test_ogni_ricerca_in_piu_costa(self):
        una = pricing.calcola(
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=1000,
            output_tokens=100,
            search_calls=1,
        )
        cinque = pricing.calcola(
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=1000,
            output_tokens=100,
            search_calls=5,
        )
        assert cinque.usd - una.usd == Decimal("0.04")  # 4 ricerche x $0.01

    def test_il_tasso_di_cambio_e_configurabile(self):
        argomenti = {
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "search_calls": 0,
        }
        a = pricing.calcola(**argomenti, settings=_settings(usd_eur_rate=1.0))
        b = pricing.calcola(**argomenti, settings=_settings(usd_eur_rate=0.5))
        assert a.usd == b.usd
        assert b.eur == a.eur / 2

    def test_risolve_gli_snapshot_datati_sul_prefisso(self):
        """Gli alias si risolvono in `gpt-5.6-luna-2026-05-01`."""
        alias = pricing.calcola(
            provider="openai",
            model="gpt-5.6-luna",
            input_tokens=1000,
            output_tokens=100,
            search_calls=1,
        )
        snapshot = pricing.calcola(
            provider="openai",
            model="gpt-5.6-luna-2026-05-01",
            input_tokens=1000,
            output_tokens=100,
            search_calls=1,
        )
        assert snapshot.usd == alias.usd
        assert snapshot.stimato is False


class TestStime:
    def test_senza_dati_di_usage_il_costo_non_e_zero(self):
        """Uno zero silenzioso farebbe spendere senza che il kill switch veda."""
        costo = pricing.calcola(
            provider="openai",
            model="gpt-5.6-luna",
            input_tokens=None,
            output_tokens=None,
            search_calls=1,
        )
        assert costo.usd > 0
        assert costo.stimato is True

    def test_senza_conteggio_ricerche_si_assume_almeno_una(self):
        costo = pricing.calcola(
            provider="openai",
            model="gpt-5.6-luna",
            input_tokens=1000,
            output_tokens=100,
            search_calls=None,
        )
        assert costo.stimato is True
        assert costo.usd >= Decimal("0.01")

    def test_modello_sconosciuto_marca_stimato(self):
        costo = pricing.calcola(
            provider="openai",
            model="gpt-99-inventato",
            input_tokens=1000,
            output_tokens=100,
            search_calls=1,
        )
        assert costo.stimato is True

    def test_provider_sconosciuto_non_solleva(self):
        costo = pricing.calcola(
            provider="inesistente",
            model="x",
            input_tokens=1000,
            output_tokens=100,
            search_calls=1,
        )
        assert costo.usd == Decimal("0")
        assert costo.stimato is True


class TestListino:
    def test_il_listino_versionato_ha_tutti_i_provider_attivi(self):
        listino = pricing.carica_listino()
        assert set(listino["providers"]) >= {"openai", "perplexity", "anthropic", "gemini"}
        for nome, voce in listino["providers"].items():
            assert voce.get("source_url"), f"{nome} senza fonte del prezzo"
            assert voce.get("models"), f"{nome} senza modelli"

    def test_i_modelli_di_default_sono_nel_listino(self):
        """Un modello configurato ma assente dal listino significa costo a zero."""
        settings = get_settings()
        listino = pricing.carica_listino()
        for provider, modello in (
            ("openai", settings.openai_model),
            ("perplexity", settings.perplexity_model),
            ("anthropic", settings.anthropic_model),
            ("gemini", settings.gemini_model),
        ):
            modelli = listino["providers"][provider]["models"]
            assert any(modello.startswith(n) for n in modelli), (
                f"{provider}/{modello} manca da pricing.yaml"
            )

    def test_un_listino_vecchio_viene_segnalato(self, tmp_path):
        """Un kill switch che calcola su prezzi di un anno fa non protegge."""
        vecchio = (datetime.now(UTC).date() - timedelta(days=200)).isoformat()
        file = tmp_path / "pricing.yaml"
        file.write_text(f"updated: {vecchio}\nproviders: {{}}\n")

        # structlog scrive su stdout con PrintLoggerFactory, non passa da
        # `caplog`: si intercetta la catena di processori.
        with capture_logs() as righe:
            pricing._carica_file(str(file), 90)

        assert any("non aggiornato da troppo tempo" in r["event"] for r in righe)

    def test_un_listino_senza_data_viene_segnalato(self, tmp_path):
        file = tmp_path / "pricing.yaml"
        file.write_text("providers: {}\n")

        with capture_logs() as righe:
            pricing._carica_file(str(file), 90)

        assert any("`updated` valido" in r["event"] for r in righe)

    def test_un_listino_mancante_e_un_errore_esplicito(self, tmp_path):
        with pytest.raises(pricing.ListinoMancanteError, match="kill switch"):
            pricing._carica_file(str(tmp_path / "assente.yaml"), 90)
