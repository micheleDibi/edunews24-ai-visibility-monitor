"""Configurazione: le trappole che non producono errori ma valori sbagliati."""

from __future__ import annotations

import pytest

from app.core.config import Settings

HASH_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$BBBBBBBBBBBBBBBBBBBB"
URL = "postgresql+asyncpg://u:p@h:5432/d"


def _settings(**modifiche) -> Settings:
    base = {"source_db_url": URL, "monitor_db_url": URL}
    return Settings(**{**base, **modifiche})  # type: ignore[arg-type]


class TestApiciAttorno:
    """Docker Compose interpola i `$` nei valori di `env_file`.

    Un hash argon2 va quindi racchiuso fra apici singoli, che Compose rimuove.
    Ma `docker run --env-file` non interpola E non rimuove gli apici: lo stesso
    file, usato in quel modo, consegnerebbe un valore con gli apici attaccati e
    un login che non funziona senza nessun errore che spieghi perche'.
    """

    @pytest.mark.parametrize("apice", ["'", '"'])
    def test_gli_apici_attorno_allhash_vengono_rimossi(self, apice):
        s = _settings(admin_password_hash=f"{apice}{HASH_ARGON2}{apice}")
        assert s.admin_password_hash == HASH_ARGON2

    def test_un_hash_nudo_resta_intatto(self):
        assert _settings(admin_password_hash=HASH_ARGON2).admin_password_hash == HASH_ARGON2

    def test_gli_apici_non_toccano_il_contenuto(self):
        """Un apice DENTRO il valore non deve essere rimosso."""
        con_apice = "abc'def"
        assert _settings(jwt_secret=con_apice).jwt_secret == con_apice

    def test_apici_spaiati_non_vengono_rimossi(self):
        assert _settings(jwt_secret="'senza-chiusura").jwt_secret == "'senza-chiusura"

    def test_vale_anche_per_le_connection_string(self):
        s = _settings(source_db_url=f"'{URL}'")
        assert s.source_db_url == URL

    def test_stringa_di_due_apici_diventa_vuota(self):
        # `ADMIN_PASSWORD_HASH=''` nel .env.example: e' un valore non impostato.
        assert _settings(admin_password_hash="''").admin_password_hash == ""


class TestValidatori:
    def test_una_url_senza_asyncpg_viene_respinta(self):
        with pytest.raises(ValueError, match="asyncpg"):
            _settings(source_db_url="postgresql://u:p@h/d")

    def test_i_bucket_devono_sommare_a_cento(self):
        with pytest.raises(ValueError, match="sommare a 100"):
            _settings(bucket_fresh_pct=50, bucket_recent_pct=50, bucket_archive_pct=50)

    def test_in_produzione_i_segreti_sono_obbligatori(self):
        with pytest.raises(ValueError, match="JWT_SECRET"):
            _settings(env="production", jwt_secret="", admin_password_hash="x")

    def test_in_produzione_il_segreto_deve_essere_lungo(self):
        with pytest.raises(ValueError, match="32 caratteri"):
            _settings(env="production", jwt_secret="corto", admin_password_hash="x")

    def test_gemini_resta_spento_anche_con_la_chiave(self):
        """I termini dell'API vietano l'uso analitico dei link di grounding."""
        s = _settings(gemini_api_key="chiave", gemini_enabled=False)
        assert "gemini" not in s.enabled_providers
        assert "gemini" in _settings(gemini_api_key="chiave", gemini_enabled=True).enabled_providers


class TestHashPassword:
    """`hash-password` deve funzionare PRIMA che esista una configurazione.

    E' il comando che genera `ADMIN_PASSWORD_HASH`, che in produzione la
    configurazione pretende: se lo caricasse, il primo comando della procedura
    di installazione fallirebbe chiedendo il valore che sta per produrre.
    """

    def test_non_carica_le_settings(self, monkeypatch, capsys):
        import app.cli as cli

        def esplodi():
            raise AssertionError("hash-password non deve leggere la configurazione")

        monkeypatch.setattr(cli, "get_settings", esplodi)
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("una-password-lunga\n"))

        assert cli.main(["hash-password"]) == 0
        assert "ADMIN_PASSWORD_HASH='$argon2" in capsys.readouterr().out

    def test_la_riga_stampata_ha_gli_apici(self, monkeypatch, capsys):
        import app.cli as cli

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("una-password-lunga\n"))
        cli.main(["hash-password"])
        riga = next(
            r for r in capsys.readouterr().out.splitlines() if r.startswith("ADMIN_PASSWORD_HASH=")
        )
        assert riga.endswith("'"), "senza apici Compose distrugge l'hash"

    def test_password_troppo_corta(self, monkeypatch):
        import app.cli as cli

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("corta\n"))
        assert cli.main(["hash-password"]) == 2
