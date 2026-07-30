"""Fixture dei test.

I test che toccano il database girano contro un Postgres usa e getta. Se non
ne trova uno, la suite di database viene saltata invece di fallire: chi lavora
solo sulla logica pura non deve avere un Postgres acceso.

    docker run -d --name edunews24-pg-test \
      -e POSTGRES_PASSWORD=test -e POSTGRES_DB=monitor \
      -p 55432:5432 postgres:17-alpine
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

TEST_DB_URL = os.environ.get(
    "TEST_DB_URL", "postgresql+asyncpg://postgres:test@localhost:55432/monitor"
)

# Le Settings vengono lette una volta sola (`@lru_cache`): l'ambiente va
# preparato prima che qualunque modulo dell'app venga importato.
os.environ.setdefault("SOURCE_DB_URL", TEST_DB_URL)
os.environ.setdefault("MONITOR_DB_URL", TEST_DB_URL)
os.environ.setdefault("ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("DB_DISABLE_PREPARED_STATEMENTS", "false")

# Credenziali di prova per i test dell'API. L'hash e' calcolato a ogni
# esecuzione invece di essere incollato qui: un hash costante in un repository
# e' un invito a riusarlo per sbaglio in produzione.
PASSWORD_TEST = "prova-password-per-i-test"
os.environ.setdefault("JWT_SECRET", "segreto-di-test-abbastanza-lungo-per-il-validatore")
# I test parlano http://, e un cookie `Secure` non viene rimandato su una
# connessione non cifrata. In produzione resta `true`: e' anche il motivo per
# cui il servizio dietro reverse proxy DEVE stare in HTTPS, altrimenti il login
# non funziona e non e' evidente perche'.
os.environ.setdefault("COOKIE_SECURE", "false")
if "ADMIN_PASSWORD_HASH" not in os.environ:
    from argon2 import PasswordHasher

    os.environ["ADMIN_PASSWORD_HASH"] = PasswordHasher().hash(PASSWORD_TEST)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.models import Topic  # noqa: E402  — registra i modelli su Base.metadata

ORA = datetime.now(UTC)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def _chiudi_engine_globali():
    """Gli engine dell'app sono globali, l'event loop dei test no.

    Senza questo teardown il secondo test riuserebbe connessioni agganciate a
    un loop gia' chiuso e fallirebbe con "Event loop is closed". Il `dispose`
    gira dentro il loop del test, che e' l'unico posto in cui puo' funzionare.
    """
    yield
    from app.db.session import dispose_engine
    from app.db.source import dispose_source_engine

    await dispose_source_engine()
    await dispose_engine()


@pytest.fixture
async def engine():
    motore = create_async_engine(TEST_DB_URL, future=True)
    try:
        async with motore.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover — ambiente senza Postgres
        await motore.dispose()
        pytest.skip(f"Postgres di test non raggiungibile su {TEST_DB_URL}: {exc}")

    async with motore.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS articles CASCADE"))
        await conn.run_sync(Base.metadata.create_all)

    yield motore

    async with motore.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS articles CASCADE"))
    await motore.dispose()


@pytest.fixture
async def session(engine):
    fabbrica = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with fabbrica() as s:
        yield s


# --------------------------------------------------------------------------
# Finta tabella sorgente
# --------------------------------------------------------------------------

_DDL_TESTO = """
CREATE TABLE articles (
  id            bigint PRIMARY KEY,
  title         text,
  slug          text,
  excerpt       text,
  published_at  timestamptz,
  updated_at    timestamptz,
  category_slug text,
  isdraft       boolean NOT NULL DEFAULT false,
  tags          text,
  faqs          text,
  skill_keyword text,
  skill_angolo  text,
  skill_livello text
)
"""

_DDL_NATIVO = _DDL_TESTO.replace("tags          text", "tags          text[]").replace(
    "faqs          text", "faqs          jsonb"
)

FAQ_VALIDE = [
    {"question": "Chi puo' partecipare al concorso docenti 2026?", "answer": "..."},
    {"question": "Quali sono le scadenze per la domanda?", "answer": "..."},
]


def _righe(variante: str) -> list[dict]:
    """Righe di prova, una per ogni caso che il sync deve reggere."""
    if variante == "testo":
        tags_ok: object = json.dumps(["concorso docenti", "scuola", "GPS"])
        faqs_ok: object = json.dumps(FAQ_VALIDE)
        tags_rotti: object = "non-json{{["
        faqs_rotti: object = "{questo non e' json"
    else:
        tags_ok = ["concorso docenti", "scuola", "GPS"]
        faqs_ok = json.dumps(FAQ_VALIDE)
        # In una colonna tipizzata il malformato non e' rappresentabile:
        # il caso e' coperto dai test unitari del parser.
        tags_rotti = None
        faqs_rotti = None

    return [
        {
            "id": 1,
            "title": "Concorso docenti 2026, cosa cambia",
            "slug": "concorso-docenti-2026-cosa-cambia",
            "published_at": ORA - timedelta(days=1),
            "updated_at": ORA - timedelta(hours=2),
            "category_slug": "scuola",
            "isdraft": False,
            "tags": tags_ok,
            "faqs": faqs_ok,
            "skill_keyword": "concorso docenti 2026",
            "skill_angolo": "I posti disponibili salgono a 30.000",
            "skill_livello": "flash",
        },
        {  # bozza: deve essere esclusa
            "id": 2,
            "title": "Bozza non pubblicata",
            "slug": "bozza-non-pubblicata",
            "published_at": ORA - timedelta(days=1),
            "updated_at": None,
            "category_slug": "scuola",
            "isdraft": True,
            "tags": None,
            "faqs": None,
            "skill_keyword": None,
            "skill_angolo": None,
            "skill_livello": None,
        },
        {  # senza published_at: deve essere esclusa
            "id": 3,
            "title": "Mai pubblicato",
            "slug": "mai-pubblicato",
            "published_at": None,
            "updated_at": None,
            "category_slug": "lavoro",
            "isdraft": False,
            "tags": None,
            "faqs": None,
            "skill_keyword": None,
            "skill_angolo": None,
            "skill_livello": None,
        },
        {  # tags/faqs a NULL: deve entrare con array vuoti
            "id": 4,
            "title": "Articolo senza tag ne FAQ",
            "slug": "articolo-senza-tag",
            "published_at": ORA - timedelta(days=10),
            "updated_at": None,
            "category_slug": "universita",
            "isdraft": False,
            "tags": None,
            "faqs": None,
            "skill_keyword": None,
            "skill_angolo": None,
            "skill_livello": "evergreen",
        },
        {  # tags/faqs malformati: deve entrare senza far fallire il sync
            "id": 5,
            "title": "Articolo con campi malformati",
            "slug": "articolo-malformato",
            "published_at": ORA - timedelta(days=40),
            "updated_at": None,
            "category_slug": "lavoro",
            "isdraft": False,
            "tags": tags_rotti,
            "faqs": faqs_rotti,
            "skill_keyword": "carta del docente",
            "skill_angolo": None,
            "skill_livello": "editoriale",
        },
        {  # slug vuoto: deve essere scartato
            "id": 6,
            "title": "Senza slug",
            "slug": "   ",
            "published_at": ORA - timedelta(days=2),
            "updated_at": None,
            "category_slug": "scuola",
            "isdraft": False,
            "tags": None,
            "faqs": None,
            "skill_keyword": None,
            "skill_angolo": None,
            "skill_livello": None,
        },
        {  # livello sconosciuto: deve essere normalizzato a NULL
            "id": 7,
            "title": "Livello sconosciuto",
            "slug": "livello-sconosciuto",
            "published_at": ORA - timedelta(days=3),
            "updated_at": None,
            "category_slug": "ricerca",
            "isdraft": False,
            "tags": None,
            "faqs": None,
            "skill_keyword": None,
            "skill_angolo": None,
            "skill_livello": "inventato",
        },
    ]


@pytest.fixture(params=["testo", "nativo"])
async def source_table(request, engine):
    """Crea `articles` con i tipi della variante e la popola."""
    variante = request.param
    ddl = _DDL_TESTO if variante == "testo" else _DDL_NATIVO

    faqs_expr = "CAST(:faqs AS jsonb)" if variante == "nativo" else ":faqs"
    insert_sql = text(
        "INSERT INTO articles (id, title, slug, published_at, updated_at, category_slug, "
        "isdraft, tags, faqs, skill_keyword, skill_angolo, skill_livello) VALUES "
        f"(:id, :title, :slug, :published_at, :updated_at, :category_slug, :isdraft, :tags, "
        f"{faqs_expr}, :skill_keyword, :skill_angolo, :skill_livello)"
    )

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS articles CASCADE"))
        await conn.execute(text(ddl))
        for riga in _righe(variante):
            await conn.execute(insert_sql, riga)

    yield variante

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS articles CASCADE"))


__all__ = ["FAQ_VALIDE", "ORA", "Topic"]
