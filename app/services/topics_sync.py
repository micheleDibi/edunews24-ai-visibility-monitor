"""Sincronizzazione dei topic dal DB editoriale allo snapshot locale.

Lo snapshot esiste per due ragioni: non interrogare il database di produzione
del giornale a ogni ciclo orario, e poter tenere lo stato di rotazione
(`last_probed_at`, `probe_count`) senza scrivere una sola riga sulla sorgente.

Due modalita':

* **incrementale** (default, gira ogni notte e su richiesta) — legge solo gli
  articoli il cui watermark e' avanzato dall'ultima sincronizzazione;
* **completa** (`--full`) — rilegge tutto e, in piu', disattiva i topic che
  nella sorgente non sono piu' pubblicati. E' l'unica modalita' che se ne
  accorge, perche' un articolo tornato in bozza non compare piu' nel filtro
  dell'incrementale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import structlog
from sqlalchemy import BigInteger, all_, func, literal, literal_column, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.parsing import parse_faq_questions, parse_tags
from app.db.source import SourceSchema, fetch_rows, introspect_source
from app.models import Topic

log = structlog.get_logger(__name__)

LIVELLI_VALIDI = frozenset({"flash", "editoriale", "evergreen"})

# Colonne lette dalla sorgente, se esistono. `id`, `title`, `slug` e
# `published_at` sono obbligatorie e la loro assenza e' gia' stata segnalata
# dall'introspezione.
COLONNE_LETTE = (
    "id",
    "title",
    "slug",
    "published_at",
    "updated_at",
    "category_slug",
    "tags",
    "faqs",
    "skill_keyword",
    "skill_angolo",
    "skill_livello",
)

DIMENSIONE_PAGINA = 500


@dataclass
class SyncStats:
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    deactivated: int = 0
    skipped: int = 0
    motivi_scarto: dict[str, int] = field(default_factory=dict)
    # Modalita' EFFETTIVAMENTE eseguita, non quella richiesta: la prima
    # sincronizzazione e' sempre completa anche se e' stata chiesta
    # incrementale, e il report deve dire cosa e' successo davvero.
    full_eseguito: bool = False

    def scarta(self, motivo: str) -> None:
        self.skipped += 1
        self.motivi_scarto[motivo] = self.motivi_scarto.get(motivo, 0) + 1


def _watermark_expr(schema: SourceSchema) -> str:
    """Espressione SQL che dice "quando questa riga e' cambiata l'ultima volta".

    `GREATEST` in Postgres ignora i NULL e restituisce NULL solo se lo sono
    tutti, quindi funziona anche sugli articoli senza `updated_at`.
    """
    if schema.has("updated_at"):
        return "GREATEST(a.updated_at, a.published_at)"
    return "a.published_at"


def _build_select(settings: Settings, schema: SourceSchema, *, incrementale: bool) -> str:
    colonne = [f"a.{c}" for c in COLONNE_LETTE if schema.has(c)]
    watermark = _watermark_expr(schema)
    colonne.append(f"{watermark} AS _watermark")

    condizioni = [
        "a.isdraft = false",
        "a.published_at IS NOT NULL",
        "a.slug IS NOT NULL",
        "a.id > :last_id",
    ]
    if incrementale:
        condizioni.append(f"{watermark} > :since")

    return (
        f"SELECT {', '.join(colonne)} "
        f"FROM {settings.qualified_source_table} AS a "
        f"WHERE {' AND '.join(condizioni)} "
        "ORDER BY a.id ASC "
        "LIMIT :limite"
    )


def _riga_a_topic(riga: dict[str, Any], stats: SyncStats) -> dict[str, Any] | None:
    """Trasforma una riga della sorgente nel payload di un `Topic`.

    Restituisce `None` se la riga non e' utilizzabile. Non solleva mai: una
    riga malformata e' un articolo in meno da sondare, non un sync fallito.
    """
    source_id = riga.get("id")
    if source_id is None:
        stats.scarta("id_mancante")
        return None

    titolo = (riga.get("title") or "").strip()
    slug = (riga.get("slug") or "").strip()
    if not titolo or not slug:
        stats.scarta("titolo_o_slug_vuoto")
        return None

    livello = (riga.get("skill_livello") or "").strip().lower() or None
    if livello is not None and livello not in LIVELLI_VALIDI:
        log.warning("skill_livello sconosciuto", source_id=source_id, valore=livello)
        livello = None

    keyword = (riga.get("skill_keyword") or "").strip() or None
    angolo = (riga.get("skill_angolo") or "").strip() or None

    return {
        "source_id": int(source_id),
        "slug": slug,
        "title": titolo,
        "category_slug": (riga.get("category_slug") or "").strip() or None,
        "livello": livello,
        "keyword": keyword,
        "angolo": angolo,
        "tags": parse_tags(riga.get("tags"), source_id=source_id),
        "faq_questions": parse_faq_questions(riga.get("faqs"), source_id=source_id),
        "published_at": riga.get("published_at"),
        "source_updated_at": riga.get("_watermark"),
    }


async def _upsert(session: AsyncSession, payloads: list[dict[str, Any]], stats: SyncStats) -> None:
    """Upsert su `source_id`, contando inserimenti e aggiornamenti.

    `xmax = 0` distingue le righe appena inserite da quelle aggiornate: e' un
    dettaglio interno di Postgres, ma e' l'unico modo di avere il conteggio
    senza una seconda query.
    """
    if not payloads:
        return

    inserimento = pg_insert(Topic).values(payloads)
    stmt: Any = inserimento.on_conflict_do_update(
        index_elements=[Topic.source_id],
        set_={
            "slug": inserimento.excluded.slug,
            "title": inserimento.excluded.title,
            "category_slug": inserimento.excluded.category_slug,
            "livello": inserimento.excluded.livello,
            "keyword": inserimento.excluded.keyword,
            "angolo": inserimento.excluded.angolo,
            "tags": inserimento.excluded.tags,
            "faq_questions": inserimento.excluded.faq_questions,
            "published_at": inserimento.excluded.published_at,
            "source_updated_at": inserimento.excluded.source_updated_at,
            "synced_at": func.now(),
            # Un articolo ripubblicato torna attivo. `last_probed_at` e
            # `probe_count` NON si toccano: sono stato di rotazione nostro,
            # non della sorgente.
            "active": True,
        },
    ).returning(literal_column("(xmax = 0)").label("inserito"))

    risultato = await session.execute(stmt)
    for (inserito,) in risultato.all():
        if inserito:
            stats.inserted += 1
        else:
            stats.updated += 1


async def sync_topics(
    session: AsyncSession,
    *,
    full: bool = False,
    settings: Settings | None = None,
) -> SyncStats:
    settings = settings or get_settings()
    stats = SyncStats()

    schema = await introspect_source(settings)
    if schema.missing_required:
        log.error(
            "sync interrotto: mancano colonne obbligatorie",
            missing=sorted(schema.missing_required),
        )
        return stats

    since: datetime | None = None
    if not full:
        since = (await session.execute(select(func.max(Topic.source_updated_at)))).scalar()
        if since is None:
            log.info("nessun topic in archivio: la prima sincronizzazione e' completa")
            full = True

    sql = _build_select(settings, schema, incrementale=not full)
    visti: list[int] = []
    last_id = 0

    while True:
        params: dict[str, Any] = {"last_id": last_id, "limite": DIMENSIONE_PAGINA}
        if not full:
            params["since"] = since

        righe = await fetch_rows(sql, params)
        if not righe:
            break

        stats.fetched += len(righe)
        last_id = int(righe[-1]["id"])

        payloads = [p for r in righe if (p := _riga_a_topic(r, stats)) is not None]
        visti.extend(p["source_id"] for p in payloads)
        await _upsert(session, payloads, stats)

        if len(righe) < DIMENSIONE_PAGINA:
            break

    if full:
        stats.deactivated = await _disattiva_non_visti(session, visti)

    stats.full_eseguito = full
    await session.commit()

    log.info(
        "sync topic completato",
        modalita="completa" if full else "incrementale",
        letti=stats.fetched,
        inseriti=stats.inserted,
        aggiornati=stats.updated,
        disattivati=stats.deactivated,
        scartati=stats.skipped,
        motivi_scarto=stats.motivi_scarto or None,
    )
    return stats


async def _disattiva_non_visti(session: AsyncSession, visti: list[int]) -> int:
    """Disattiva i topic che nella sorgente non sono piu' pubblicati.

    Non si cancella nulla: i probe storici che citano quell'articolo devono
    restare leggibili, altrimenti le metriche passate cambierebbero
    retroattivamente.
    """
    stmt = update(Topic).where(Topic.active.is_(True))
    if visti:
        # `source_id <> ALL(:array)` invece di un `NOT IN (...)` espanso: un
        # solo bind param al posto di una lista SQL da diecimila elementi.
        stmt = stmt.where(Topic.source_id != all_(literal(visti, ARRAY(BigInteger))))
    stmt = stmt.values(active=False)

    risultato = await session.execute(stmt)
    return cast("CursorResult[Any]", risultato).rowcount or 0
