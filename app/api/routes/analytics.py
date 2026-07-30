"""Endpoint analitici.

Ogni aggregato passa da `filtri_probe()` e restituisce `Tasso`: le tre regole
di correttezza (solo probe `ok`, `mode` sempre esplicito, mai una percentuale
senza il suo denominatore) sono imposte dai tipi, non ricordate a memoria. Vedi
`app/api/metrics.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import Select, distinct, func, select

from app.api.deps import Admin, Config, Db
from app.api.metrics import (
    SOGLIA_MINIMA,
    Delta,
    Modo,
    Tasso,
    filtri_probe,
    inizio_periodo,
    periodo_precedente,
)
from app.models import Citation, DailyRollup, Probe, Query, Topic

router = APIRouter(tags=["analytics"])

Giorni = Annotated[int, QueryParam(ge=1, le=365)]


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------


def _conteggi(mode: Modo, da: datetime, a: datetime | None = None) -> Select:
    return select(
        func.count().label("probes"),
        func.count().filter(Probe.edunews_cited).label("cited"),
        func.count().filter(Probe.edunews_mention).label("mentioned"),
        func.count().filter(Probe.target_hit).label("target_hits"),
        func.count().filter(Probe.edunews_retrieved).label("retrieved"),
    ).where(*filtri_probe(mode=mode, da=da, a=a))


class Kpi(BaseModel):
    giorni: int
    mode: Modo
    citation_rate: Tasso
    citation_rate_delta: Delta
    mention_rate: Tasso
    target_hit_rate: Tasso
    retrieval_rate: Tasso = Field(
        description=(
            "Quota di risposte in cui il giornale e' comparso fra le fonti recuperate, "
            "citato o no. Non tutti i provider espongono questo dato: dove manca, il "
            "valore coincide con il citation rate."
        )
    )
    probe_totali: int = Field(description="Probe riusciti nel periodo")
    probe_falliti: int = Field(
        description="Probe non riusciti: esclusi da ogni denominatore, ma pagati"
    )
    probe_senza_ricerca: int = Field(
        description=(
            "Probe in cui il provider ha risposto senza cercare. Non sono "
            "'non citato': sono 'non misurato'."
        )
    )
    costo_eur: Decimal = Field(
        description="Costo di TUTTI i probe del periodo, falliti compresi: sono stati pagati"
    )


@router.get("/kpi", response_model=Kpi)
async def kpi(
    db: Db,
    admin: Admin,
    days: Giorni = 30,
    mode: Modo = "retrieval",
) -> Kpi:
    da = inizio_periodo(days)
    prec_da, prec_a = periodo_precedente(days)

    attuale = (await db.execute(_conteggi(mode, da))).one()
    precedente = (await db.execute(_conteggi(mode, prec_da, prec_a))).one()

    # Il costo NON passa da `filtri_probe`: include i probe falliti, perche'
    # sono stati fatturati comunque. E' l'unica metrica che deliberatamente non
    # segue la regola del denominatore, e per questo sta in una query a parte.
    costo = (
        await db.execute(
            select(func.coalesce(func.sum(Probe.cost_eur), 0)).where(
                Probe.created_at >= da, Probe.mode == mode
            )
        )
    ).scalar_one()

    falliti, senza_ricerca = (
        await db.execute(
            select(
                func.count().filter(Probe.status.notin_(("ok", "no_search"))),
                func.count().filter(Probe.status == "no_search"),
            ).where(Probe.created_at >= da, Probe.mode == mode)
        )
    ).one()

    tasso_attuale = Tasso.da_conteggi(attuale.cited, attuale.probes)
    return Kpi(
        giorni=days,
        mode=mode,
        citation_rate=tasso_attuale,
        citation_rate_delta=Delta.fra(
            tasso_attuale, Tasso.da_conteggi(precedente.cited, precedente.probes)
        ),
        mention_rate=Tasso.da_conteggi(attuale.mentioned, attuale.probes),
        target_hit_rate=Tasso.da_conteggi(attuale.target_hits, attuale.probes),
        retrieval_rate=Tasso.da_conteggi(attuale.retrieved, attuale.probes),
        probe_totali=attuale.probes,
        probe_falliti=falliti,
        probe_senza_ricerca=senza_ricerca,
        costo_eur=Decimal(str(costo)),
    )


# ---------------------------------------------------------------------------
# Tendenza
# ---------------------------------------------------------------------------


class PuntoTendenza(BaseModel):
    giorno: date
    provider: str
    citation_rate: Tasso
    costo_eur: Decimal


@router.get("/trend", response_model=list[PuntoTendenza])
async def trend(
    db: Db,
    admin: Admin,
    settings: Config,
    days: Giorni = 90,
    provider: str | None = None,
    mode: Modo = "retrieval",
) -> list[PuntoTendenza]:
    """Serie giornaliera per provider.

    Legge `daily_rollup` per i giorni chiusi e calcola OGGI dal grezzo. Il
    rollup gira di notte: senza questo innesto, la dashboard mostrerebbe il
    giorno corrente vuoto fino alle tre del mattino, che somiglia a un guasto.
    """
    da = inizio_periodo(days).date()
    oggi = datetime.now().astimezone().date()

    stmt = (
        select(
            DailyRollup.day,
            DailyRollup.provider,
            func.sum(DailyRollup.cited).label("cited"),
            func.sum(DailyRollup.probes).label("probes"),
            func.sum(DailyRollup.cost_eur).label("costo"),
        )
        .where(
            DailyRollup.day >= da,
            DailyRollup.day < oggi,
            DailyRollup.mode == mode,
        )
        .group_by(DailyRollup.day, DailyRollup.provider)
        .order_by(DailyRollup.day, DailyRollup.provider)
    )
    if provider:
        stmt = stmt.where(DailyRollup.provider == provider)

    punti = [
        PuntoTendenza(
            giorno=r.day,
            provider=r.provider,
            citation_rate=Tasso.da_conteggi(r.cited, r.probes),
            costo_eur=Decimal(str(r.costo)),
        )
        for r in (await db.execute(stmt)).all()
    ]

    # Oggi, dal grezzo.
    oggi_da = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt_oggi = (
        select(
            Probe.provider,
            func.count().label("probes"),
            func.count().filter(Probe.edunews_cited).label("cited"),
            func.coalesce(func.sum(Probe.cost_eur), 0).label("costo"),
        )
        .where(*filtri_probe(mode=mode, da=oggi_da))
        .group_by(Probe.provider)
        .order_by(Probe.provider)
    )
    if provider:
        stmt_oggi = stmt_oggi.where(Probe.provider == provider)

    punti.extend(
        PuntoTendenza(
            giorno=oggi,
            provider=r.provider,
            citation_rate=Tasso.da_conteggi(r.cited, r.probes),
            costo_eur=Decimal(str(r.costo)),
        )
        for r in (await db.execute(stmt_oggi)).all()
    )
    return punti


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class RigaProvider(BaseModel):
    provider: str
    model: str | None
    citation_rate: Tasso
    mention_rate: Tasso
    target_hit_rate: Tasso
    # Colonna separata ed etichettata: e' una metrica DIVERSA, non un confronto.
    memoria: Tasso = Field(
        description=(
            "Quota di risposte SENZA web search in cui il modello nomina il giornale a "
            "memoria. Misura se il brand e' nella conoscenza parametrica, non se il "
            "retrieval lo pesca: non va confrontata con il citation rate."
        )
    )
    latenza_mediana_ms: int | None
    ricerche_medie: float | None
    costo_eur: Decimal
    probe_falliti: int


@router.get("/providers", response_model=list[RigaProvider])
async def providers(db: Db, admin: Admin, days: Giorni = 30) -> list[RigaProvider]:
    da = inizio_periodo(days)

    stmt = (
        select(
            Probe.provider,
            func.max(Probe.model).label("model"),
            func.count().label("probes"),
            func.count().filter(Probe.edunews_cited).label("cited"),
            func.count().filter(Probe.edunews_mention).label("mentioned"),
            func.count().filter(Probe.target_hit).label("target_hits"),
            func.percentile_cont(0.5).within_group(Probe.latency_ms).label("latenza_mediana"),
            func.avg(Probe.search_calls).label("ricerche_medie"),
        )
        .where(*filtri_probe(mode="retrieval", da=da))
        .group_by(Probe.provider)
        .order_by(Probe.provider)
    )
    righe = (await db.execute(stmt)).all()

    memoria = {
        r.provider: Tasso.da_conteggi(r.mentioned, r.probes)
        for r in (
            await db.execute(
                select(
                    Probe.provider,
                    func.count().label("probes"),
                    func.count().filter(Probe.edunews_mention).label("mentioned"),
                )
                .where(*filtri_probe(mode="memory", da=da))
                .group_by(Probe.provider)
            )
        ).all()
    }

    costi = {
        r.provider: (Decimal(str(r.costo)), r.falliti)
        for r in (
            await db.execute(
                select(
                    Probe.provider,
                    func.coalesce(func.sum(Probe.cost_eur), 0).label("costo"),
                    func.count().filter(Probe.status != "ok").label("falliti"),
                )
                .where(Probe.created_at >= da)
                .group_by(Probe.provider)
            )
        ).all()
    }

    return [
        RigaProvider(
            provider=r.provider,
            model=r.model,
            citation_rate=Tasso.da_conteggi(r.cited, r.probes),
            mention_rate=Tasso.da_conteggi(r.mentioned, r.probes),
            target_hit_rate=Tasso.da_conteggi(r.target_hits, r.probes),
            memoria=memoria.get(r.provider, Tasso.da_conteggi(0, 0)),
            latenza_mediana_ms=int(r.latenza_mediana) if r.latenza_mediana else None,
            ricerche_medie=round(float(r.ricerche_medie), 2) if r.ricerche_medie else None,
            costo_eur=costi.get(r.provider, (Decimal("0"), 0))[0],
            probe_falliti=costi.get(r.provider, (Decimal("0"), 0))[1],
        )
        for r in righe
    ]


# ---------------------------------------------------------------------------
# Categorie
# ---------------------------------------------------------------------------


class CellaCategoria(BaseModel):
    category_slug: str
    provider: str
    citation_rate: Tasso


@router.get("/categories", response_model=list[CellaCategoria])
async def categories(
    db: Db, admin: Admin, days: Giorni = 30, mode: Modo = "retrieval"
) -> list[CellaCategoria]:
    """Griglia categoria x provider.

    Si legge dal grezzo e non da `daily_rollup` per una ragione precisa: il
    rollup e' gia' aggregato per giorno, e sommare i suoi tassi per ottenere il
    tasso del periodo darebbe la media delle medie giornaliere — che non e' il
    tasso del periodo quando i giorni hanno numerosita' diverse.
    """
    da = inizio_periodo(days)
    stmt = (
        select(
            func.coalesce(Query.category_slug, "").label("categoria"),
            Probe.provider,
            func.count().label("probes"),
            func.count().filter(Probe.edunews_cited).label("cited"),
        )
        .join(Query, Query.id == Probe.query_id)
        .where(*filtri_probe(mode=mode, da=da))
        .group_by("categoria", Probe.provider)
        .order_by("categoria", Probe.provider)
    )
    return [
        CellaCategoria(
            category_slug=r.categoria,
            provider=r.provider,
            citation_rate=Tasso.da_conteggi(r.cited, r.probes),
        )
        for r in (await db.execute(stmt)).all()
    ]


# ---------------------------------------------------------------------------
# Dove sei invisibile / Cosa funziona
# ---------------------------------------------------------------------------


class Lacuna(BaseModel):
    topic_id: int
    source_id: int
    slug: str
    title: str
    category_slug: str | None
    published_at: datetime | None
    probe: int = Field(description="Probe riusciti su questo articolo nel periodo")
    recuperato_mai: bool = Field(
        description=(
            "Vero se il giornale e' comparso almeno una volta fra le fonti recuperate "
            "senza essere citato: e' un problema diverso da non essere trovato affatto."
        )
    )


@router.get("/gaps", response_model=list[Lacuna])
async def gaps(
    db: Db,
    admin: Admin,
    days: Giorni = 30,
    min_probe: Annotated[int, QueryParam(ge=1, le=1000)] = SOGLIA_MINIMA,
    limit: Annotated[int, QueryParam(ge=1, le=500)] = 100,
) -> list[Lacuna]:
    """Argomenti sondati e mai citati, dal piu' sondato.

    `min_probe` non e' arbitrario: un articolo sondato due volte e mai citato e'
    rumore, uno sondato venti volte e mai citato e' un dato. Il default e' la
    stessa soglia sotto la quale non si calcola nessun tasso.
    """
    da = inizio_periodo(days)
    stmt = (
        select(
            Topic.id,
            Topic.source_id,
            Topic.slug,
            Topic.title,
            Topic.category_slug,
            Topic.published_at,
            func.count().label("probe"),
            func.count().filter(Probe.edunews_cited).label("citati"),
            func.count().filter(Probe.edunews_retrieved).label("recuperati"),
        )
        .select_from(Probe)
        .join(Query, Query.id == Probe.query_id)
        .join(Topic, Topic.id == Query.topic_id)
        .where(*filtri_probe(mode="retrieval", da=da))
        .group_by(Topic.id)
        .having(func.count().filter(Probe.edunews_cited) == 0)
        .having(func.count() >= min_probe)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [
        Lacuna(
            topic_id=r.id,
            source_id=r.source_id,
            slug=r.slug,
            title=r.title,
            category_slug=r.category_slug,
            published_at=r.published_at,
            probe=r.probe,
            recuperato_mai=r.recuperati > 0,
        )
        for r in (await db.execute(stmt)).all()
    ]


class Successo(BaseModel):
    topic_id: int
    slug: str
    title: str
    category_slug: str | None
    citazioni: int
    target_hit: int
    probe: int
    citation_rate: Tasso
    provider: list[str]


@router.get("/wins", response_model=list[Successo])
async def wins(
    db: Db,
    admin: Admin,
    days: Giorni = 30,
    limit: Annotated[int, QueryParam(ge=1, le=500)] = 50,
) -> list[Successo]:
    da = inizio_periodo(days)
    stmt = (
        select(
            Topic.id,
            Topic.slug,
            Topic.title,
            Topic.category_slug,
            func.count().label("probe"),
            func.count().filter(Probe.edunews_cited).label("citazioni"),
            func.count().filter(Probe.target_hit).label("target"),
            func.array_agg(distinct(Probe.provider)).label("provider"),
        )
        .select_from(Probe)
        .join(Query, Query.id == Probe.query_id)
        .join(Topic, Topic.id == Query.topic_id)
        .where(*filtri_probe(mode="retrieval", da=da))
        .group_by(Topic.id)
        .having(func.count().filter(Probe.edunews_cited) > 0)
        .order_by(func.count().filter(Probe.edunews_cited).desc())
        .limit(limit)
    )
    return [
        Successo(
            topic_id=r.id,
            slug=r.slug,
            title=r.title,
            category_slug=r.category_slug,
            citazioni=r.citazioni,
            target_hit=r.target,
            probe=r.probe,
            citation_rate=Tasso.da_conteggi(r.citazioni, r.probe),
            provider=sorted(r.provider or []),
        )
        for r in (await db.execute(stmt)).all()
    ]


# ---------------------------------------------------------------------------
# Chi occupa il posto
# ---------------------------------------------------------------------------


class RigaDominio(BaseModel):
    domain: str
    probe: int = Field(description="Probe distinti in cui questo dominio e' stato citato")
    citazioni: int
    quota: Tasso = Field(description="Quota di probe del periodo in cui compare")
    proprio: bool
    non_risolto: bool = Field(
        description=(
            "Vero per la voce `unresolved`: URL avvolti in un redirect da cui il "
            "dominio reale non e' estraibile. Si dichiara invece di indovinarlo, e "
            "si mostra invece di nasconderlo: e' la quota di misura che non abbiamo."
        )
    )


@router.get("/domains", response_model=list[RigaDominio])
async def domains(
    db: Db,
    admin: Admin,
    days: Giorni = 30,
    mode: Modo = "retrieval",
    kind: Annotated[str, QueryParam(pattern="^(citation|source)$")] = "citation",
    limit: Annotated[int, QueryParam(ge=1, le=500)] = 50,
) -> list[RigaDominio]:
    """Classifica dei domini citati: chi c'e' quando il giornale non c'e'."""
    da = inizio_periodo(days)

    totale_probe = (
        await db.execute(select(func.count()).where(*filtri_probe(mode=mode, da=da)))
    ).scalar_one()

    stmt = (
        select(
            Citation.domain,
            func.count(distinct(Citation.probe_id)).label("probe"),
            func.count().label("citazioni"),
            func.bool_or(Citation.is_own).label("proprio"),
        )
        .join(Probe, Probe.id == Citation.probe_id)
        .where(*filtri_probe(mode=mode, da=da), Citation.kind == kind)
        .group_by(Citation.domain)
        .order_by(func.count(distinct(Citation.probe_id)).desc())
        .limit(limit)
    )
    return [
        RigaDominio(
            domain=r.domain,
            probe=r.probe,
            citazioni=r.citazioni,
            quota=Tasso.da_conteggi(r.probe, totale_probe),
            proprio=bool(r.proprio),
            non_risolto=r.domain == "unresolved",
        )
        for r in (await db.execute(stmt)).all()
    ]
