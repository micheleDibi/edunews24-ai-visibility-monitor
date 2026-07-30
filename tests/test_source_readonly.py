"""La garanzia di sola lettura sul DB editoriale.

E' il vincolo piu' importante del sistema: il servizio non deve possedere
credenziali in grado di modificare il database del giornale. Qui la si verifica
contro ruoli Postgres veri, non con dei mock, perche' un mock proverebbe solo
che il codice chiama la funzione giusta — non che la funzione risponda la cosa
giusta a un ruolo davvero pericoloso.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.source import (
    SourceDbWritableError,
    SourceTableMissingError,
    assert_readonly,
    introspect_source,
)
from tests.conftest import TEST_DB_URL

PASSWORD = "prova_ruolo_ro"


def _url_per(ruolo: str) -> str:
    """Sostituisce utente e password nella URL del Postgres di test."""
    prefisso, resto = TEST_DB_URL.split("://", 1)
    _credenziali, host = resto.split("@", 1)
    return f"{prefisso}://{ruolo}:{PASSWORD}@{host}"


# `DROP OWNED BY` fallisce se il ruolo non esiste, e va eseguito prima di
# `DROP ROLE` perche' revoca i privilegi che gli sono stati concessi.
_ELIMINA_RUOLO = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{r}') THEN
    EXECUTE 'DROP OWNED BY {r} CASCADE';
    EXECUTE 'DROP ROLE {r}';
  END IF;
END $$;
"""


@pytest.fixture
async def crea_ruolo(engine):
    """Crea ruoli usa e getta e restituisce un engine che li usa."""
    creati: list[str] = []
    motori: list = []

    async def _crea(nome: str, grants: list[str]):
        async with engine.begin() as conn:
            await conn.execute(text(_ELIMINA_RUOLO.format(r=nome)))
            await conn.execute(
                text(f"CREATE ROLE {nome} LOGIN PASSWORD '{PASSWORD}' NOSUPERUSER NOINHERIT")
            )
            for g in grants:
                await conn.execute(text(g))
        creati.append(nome)
        motore = create_async_engine(_url_per(nome), future=True)
        motori.append(motore)
        return motore

    yield _crea

    for m in motori:
        await m.dispose()
    async with engine.begin() as conn:
        for nome in creati:
            await conn.execute(text(_ELIMINA_RUOLO.format(r=nome)))


GRANT_BASE = [
    "GRANT CONNECT ON DATABASE monitor TO {r}",
    "GRANT USAGE ON SCHEMA public TO {r}",
]


def _grants(nome: str, *extra: str) -> list[str]:
    return [g.format(r=nome) for g in [*GRANT_BASE, *extra]]


class TestAssertReadonly:
    async def test_un_ruolo_con_solo_select_passa(self, source_table, crea_ruolo):
        motore = await crea_ruolo(
            "ro_buono", _grants("ro_buono", "GRANT SELECT ON public.articles TO {r}")
        )
        await assert_readonly(get_settings(), engine=motore)  # non deve sollevare

    async def test_un_superuser_viene_rifiutato(self, source_table, engine):
        # L'engine dei test usa `postgres`, che e' superuser.
        with pytest.raises(SourceDbWritableError, match="SUPERUSER"):
            await assert_readonly(get_settings(), engine=engine)

    async def test_il_privilegio_di_insert_viene_rifiutato(self, source_table, crea_ruolo):
        motore = await crea_ruolo(
            "ro_scrittore",
            _grants("ro_scrittore", "GRANT SELECT, INSERT ON public.articles TO {r}"),
        )
        with pytest.raises(SourceDbWritableError, match="INSERT"):
            await assert_readonly(get_settings(), engine=motore)

    @pytest.mark.parametrize("privilegio", ["UPDATE", "DELETE", "TRUNCATE"])
    async def test_ogni_privilegio_di_scrittura_viene_rifiutato(
        self, source_table, crea_ruolo, privilegio
    ):
        nome = f"ro_{privilegio.lower()}"
        motore = await crea_ruolo(
            nome, _grants(nome, f"GRANT SELECT, {privilegio} ON public.articles TO {{r}}")
        )
        with pytest.raises(SourceDbWritableError, match=privilegio):
            await assert_readonly(get_settings(), engine=motore)

    async def test_la_scrittura_su_unaltra_tabella_viene_rifiutata(
        self, source_table, crea_ruolo, engine
    ):
        """Non basta non poter scrivere su `articles`.

        Una credenziale che puo' modificare un'altra tabella del giornale e'
        comunque una credenziale di scrittura sul database del giornale.
        """
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS altra (id int)"))
        motore = await crea_ruolo(
            "ro_altrove",
            _grants(
                "ro_altrove",
                "GRANT SELECT ON public.articles TO {r}",
                "GRANT INSERT ON public.altra TO {r}",
            ),
        )
        try:
            with pytest.raises(SourceDbWritableError, match="altre tabelle"):
                await assert_readonly(get_settings(), engine=motore)
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DROP TABLE IF EXISTS altra CASCADE"))

    async def test_il_permesso_di_creare_nello_schema_viene_rifiutato(
        self, source_table, crea_ruolo
    ):
        motore = await crea_ruolo(
            "ro_creatore",
            _grants(
                "ro_creatore",
                "GRANT SELECT ON public.articles TO {r}",
                "GRANT CREATE ON SCHEMA public TO {r}",
            ),
        )
        with pytest.raises(SourceDbWritableError, match="creare oggetti"):
            await assert_readonly(get_settings(), engine=motore)

    async def test_senza_select_il_ruolo_e_inutile(self, source_table, crea_ruolo):
        motore = await crea_ruolo("ro_cieco", _grants("ro_cieco"))
        with pytest.raises(SourceDbWritableError, match="SELECT"):
            await assert_readonly(get_settings(), engine=motore)

    async def test_tabella_inesistente_da_un_errore_comprensibile(self, engine, crea_ruolo):
        motore = await crea_ruolo("ro_senza_tabella", _grants("ro_senza_tabella"))
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS articles CASCADE"))
        with pytest.raises(SourceTableMissingError, match="non esiste"):
            await assert_readonly(get_settings(), engine=motore)


class TestIntrospezione:
    async def test_riconosce_le_colonne_presenti_e_assenti(self, source_table):
        schema = await introspect_source(get_settings())

        assert schema.missing_required == frozenset()
        assert schema.has("tags")
        assert schema.has("faqs")
        assert schema.has("skill_livello")
        # La finta tabella non ha `summary` ne le secondarie: devono risultare
        # mancanti come opzionali, senza far fallire nulla.
        assert "summary" in schema.missing_optional
        assert "secondary_category_slugs" in schema.missing_optional

    async def test_rileva_il_tipo_reale_di_tags_e_faqs(self, source_table):
        schema = await introspect_source(get_settings())
        variante = source_table

        if variante == "nativo":
            assert schema.columns["tags"].is_array
            assert schema.columns["faqs"].is_json
        else:
            assert not schema.columns["tags"].is_array
            assert not schema.columns["faqs"].is_json

    async def test_una_tabella_assente_non_solleva(self, engine):
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS articles CASCADE"))

        schema = await introspect_source(get_settings())

        assert schema.columns == {}
        assert schema.missing_required  # segnalate a ERROR, non sollevate
