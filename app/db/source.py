"""Connettore al database editoriale (gli articoli). SOLA LETTURA.

Questo modulo e' l'unico punto in cui il servizio tocca il database del
giornale, e non deve poterci scrivere. Non e' una questione di disciplina del
codice ma di privilegi: la connection string configurata deve appartenere a un
ruolo che possiede soltanto SELECT (vedi `sql/readonly_role.sql`).

`assert_readonly()` lo verifica all'avvio e ferma l'applicazione se la
verifica fallisce. Un servizio di misura non ha alcun motivo di poter
modificare la cosa che misura.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, get_settings
from app.db.session import build_connect_args

log = structlog.get_logger(__name__)

_source_engine: AsyncEngine | None = None


class SourceDbWritableError(RuntimeError):
    """La connessione al DB editoriale puo' scrivere. L'avvio viene interrotto."""


class SourceTableMissingError(RuntimeError):
    """La tabella sorgente configurata non esiste o non e' visibile al ruolo."""


# Colonne che il generatore di query usa davvero. Le "obbligatorie" servono
# perche' senza di esse non si puo' costruire nemmeno una query minima; le
# altre arricchiscono le strategie e la loro assenza si degrada, non si rompe.
REQUIRED_COLUMNS = frozenset({"id", "title", "slug", "published_at", "isdraft"})
OPTIONAL_COLUMNS = frozenset(
    {
        "category",
        "category_slug",
        "secondary_category_slugs",
        "excerpt",
        "summary",
        "tags",
        "faqs",
        "skill_keyword",
        "skill_angolo",
        "skill_livello",
        "skill_meta_title",
        "skill_meta_description",
        "updated_at",
    }
)


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str  # `information_schema.columns.data_type`
    udt_name: str  # tipo sottostante: `text`, `_text` (array), `jsonb`, ...
    nullable: bool

    @property
    def is_array(self) -> bool:
        """asyncpg restituisce una `list` Python per gli array Postgres."""
        return self.data_type == "ARRAY"

    @property
    def is_json(self) -> bool:
        """asyncpg restituisce una `str` per json/jsonb: va fatto `json.loads`."""
        return self.udt_name in {"json", "jsonb"}


@dataclass(frozen=True)
class SourceSchema:
    """Cosa il servizio ha davvero trovato nella tabella sorgente."""

    columns: dict[str, ColumnInfo]
    missing_required: frozenset[str]
    missing_optional: frozenset[str]

    def has(self, name: str) -> bool:
        return name in self.columns


def get_source_engine() -> AsyncEngine:
    global _source_engine
    if _source_engine is None:
        settings = get_settings()
        _source_engine = create_async_engine(
            settings.source_db_url,
            # Il sync dei topic e' un job periodico, non un percorso di
            # richiesta: due connessioni bastano e teniamo basso il peso sul DB
            # di produzione del giornale.
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=True,
            future=True,
            connect_args=build_connect_args(
                settings, read_only=True, app_name="edunews24-monitor-ro"
            ),
        )
    return _source_engine


async def dispose_source_engine() -> None:
    global _source_engine
    if _source_engine is not None:
        await _source_engine.dispose()
    _source_engine = None


# ---------------------------------------------------------------------------
# Verifica dei privilegi
# ---------------------------------------------------------------------------

_PRIVILEGE_SQL = text(
    """
    SELECT
      current_user                                                        AS role_name,
      (SELECT rolsuper     FROM pg_roles WHERE rolname = current_user)    AS is_superuser,
      (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)    AS bypasses_rls,
      has_schema_privilege(current_user, :schema, 'CREATE')               AS can_create,
      has_table_privilege(current_user, :qualified, 'SELECT')             AS can_select,
      has_table_privilege(current_user, :qualified, 'INSERT')             AS can_insert,
      has_table_privilege(current_user, :qualified, 'UPDATE')             AS can_update,
      has_table_privilege(current_user, :qualified, 'DELETE')             AS can_delete,
      has_table_privilege(current_user, :qualified, 'TRUNCATE')           AS can_truncate
    """
)

# Non basta che il ruolo non possa scrivere su `articles`: non deve poter
# scrivere su NULLA in quello schema. Una credenziale che puo' modificare
# un'altra tabella del giornale e' comunque una credenziale di scrittura.
_WRITABLE_ELSEWHERE_SQL = text(
    """
    SELECT t.table_name
    FROM information_schema.tables t,
         LATERAL format('%I.%I', t.table_schema, t.table_name) AS q(nome)
    WHERE t.table_schema = :schema
      AND t.table_type = 'BASE TABLE'
      AND (
            has_table_privilege(current_user, q.nome, 'INSERT')
         OR has_table_privilege(current_user, q.nome, 'UPDATE')
         OR has_table_privilege(current_user, q.nome, 'DELETE')
         OR has_table_privilege(current_user, q.nome, 'TRUNCATE')
      )
    ORDER BY t.table_name
    LIMIT 10
    """
)


async def assert_readonly(
    settings: Settings | None = None, engine: AsyncEngine | None = None
) -> None:
    """Verifica che la connessione al DB editoriale non possa scrivere.

    Solleva `SourceDbWritableError` con un messaggio che dice esattamente cosa
    fare. Chiamata nel lifespan e all'inizio di ogni comando CLI che tocca la
    sorgente. `engine` e' iniettabile solo per i test.
    """
    settings = settings or get_settings()
    engine = engine or get_source_engine()
    qualified = settings.qualified_source_table

    async with engine.connect() as conn:
        esiste = (await conn.execute(text("SELECT to_regclass(:q)"), {"q": qualified})).scalar()
        if esiste is None:
            raise SourceTableMissingError(
                f"La tabella '{qualified}' non esiste, oppure il ruolo configurato non ha "
                f"USAGE sullo schema '{settings.source_schema}' e quindi non la vede. "
                "Controlla SOURCE_TABLE/SOURCE_SCHEMA e i GRANT di sql/readonly_role.sql."
            )

        riga = (
            (
                await conn.execute(
                    _PRIVILEGE_SQL, {"schema": settings.source_schema, "qualified": qualified}
                )
            )
            .mappings()
            .one()
        )

        scrivibili = [
            r[0]
            for r in (
                await conn.execute(_WRITABLE_ELSEWHERE_SQL, {"schema": settings.source_schema})
            ).all()
        ]

    problemi: list[str] = []
    if riga["is_superuser"]:
        problemi.append("e' SUPERUSER")
    if riga["bypasses_rls"]:
        problemi.append("ha BYPASSRLS")
    if riga["can_create"]:
        problemi.append(f"puo' creare oggetti nello schema '{settings.source_schema}'")
    for privilegio in ("insert", "update", "delete", "truncate"):
        if riga[f"can_{privilegio}"]:
            problemi.append(f"ha il privilegio {privilegio.upper()} su {qualified}")
    if scrivibili:
        problemi.append("puo' scrivere su altre tabelle dello schema: " + ", ".join(scrivibili))

    if problemi:
        raise SourceDbWritableError(
            f"SOURCE_DB_URL usa il ruolo '{riga['role_name']}', che "
            + "; ".join(problemi)
            + ".\nIl servizio non deve possedere credenziali in grado di scrivere sul "
            "database degli articoli. Crea un ruolo di sola lettura con "
            "sql/readonly_role.sql e riconfigura SOURCE_DB_URL."
        )

    if not riga["can_select"]:
        raise SourceDbWritableError(
            f"Il ruolo '{riga['role_name']}' non ha il privilegio SELECT su {qualified}: "
            "non puo' leggere nulla. Esegui i GRANT di sql/readonly_role.sql."
        )

    log.info(
        "db sorgente verificato in sola lettura",
        role=riga["role_name"],
        table=qualified,
    )


# ---------------------------------------------------------------------------
# Introspezione delle colonne
# ---------------------------------------------------------------------------

_COLUMNS_SQL = text(
    """
    SELECT column_name, data_type, udt_name, is_nullable
    FROM information_schema.columns
    WHERE table_schema = :schema AND table_name = :table
    ORDER BY ordinal_position
    """
)


async def introspect_source(settings: Settings | None = None) -> SourceSchema:
    """Legge le colonne reali della tabella sorgente.

    Non solleva eccezioni per le colonne mancanti: le logga. Lo schema di un
    giornale in produzione cambia senza preavviso, e una colonna `skill_*`
    assente deve degradare una strategia di generazione, non impedire l'avvio
    del monitor. Le colonne obbligatorie sono l'unica eccezione, e vengono
    segnalate a ERROR perche' senza di esse il sync non produrra' nulla di
    utile.
    """
    settings = settings or get_settings()
    engine = get_source_engine()

    async with engine.connect() as conn:
        righe = (
            (
                await conn.execute(
                    _COLUMNS_SQL, {"schema": settings.source_schema, "table": settings.source_table}
                )
            )
            .mappings()
            .all()
        )

    colonne = {
        r["column_name"]: ColumnInfo(
            name=r["column_name"],
            data_type=r["data_type"],
            udt_name=r["udt_name"],
            nullable=r["is_nullable"] == "YES",
        )
        for r in righe
    }

    mancanti_req = frozenset(REQUIRED_COLUMNS - colonne.keys())
    mancanti_opt = frozenset(OPTIONAL_COLUMNS - colonne.keys())

    if mancanti_req:
        log.error(
            "colonne obbligatorie mancanti nella tabella sorgente",
            table=settings.qualified_source_table,
            missing=sorted(mancanti_req),
        )
    if mancanti_opt:
        log.warning(
            "colonne opzionali assenti: alcune strategie di generazione saranno disattivate",
            table=settings.qualified_source_table,
            missing=sorted(mancanti_opt),
        )

    # Il tipo reale di `tags` e `faqs` non e' documentato da nessuna parte: puo'
    # essere un array/jsonb nativo (asyncpg restituisce list) oppure una colonna
    # text che contiene un array JSON serializzato (asyncpg restituisce str).
    # Il parser gestisce entrambi, ma il tipo trovato va scritto nei log perche'
    # e' l'informazione che spiega qualunque anomalia successiva.
    for nome in ("tags", "faqs", "secondary_category_slugs"):
        if nome in colonne:
            c = colonne[nome]
            log.info(
                "tipo colonna sorgente",
                column=nome,
                data_type=c.data_type,
                udt_name=c.udt_name,
                parsing="nativo" if (c.is_array or c.is_json) else "json.loads su testo",
            )

    return SourceSchema(
        columns=colonne, missing_required=mancanti_req, missing_optional=mancanti_opt
    )


async def fetch_rows(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Esegue una SELECT sulla sorgente e restituisce dizionari.

    Unico modo previsto per leggere dal DB editoriale. Nessuna sessione ORM,
    nessun `commit`: la transazione e' in sola lettura per costruzione.
    """
    engine = get_source_engine()
    async with engine.connect() as conn:
        risultato = await conn.execute(text(sql), params)
        return [dict(r) for r in risultato.mappings().all()]
