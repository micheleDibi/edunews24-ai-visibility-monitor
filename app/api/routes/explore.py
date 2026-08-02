"""Esplorazione dei probe, dettaglio, elenco dei cicli."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Admin, Config, Db
from app.api.metrics import Modo, inizio_periodo
from app.models import Citation, Probe, Query, Run, Topic

router = APIRouter(tags=["esplorazione"])


class CitazioneVista(BaseModel):
    domain: str
    url: str | None
    title: str | None
    kind: str
    position: int | None
    is_own: bool
    own_slug: str | None


class ProbeVisto(BaseModel):
    id: int
    run_id: int
    created_at: datetime
    provider: str
    model: str
    mode: Modo
    status: str
    error: str | None
    latency_ms: int | None
    search_calls: int | None
    costo_eur: Decimal | None
    costo_stimato: bool
    edunews_cited: bool
    edunews_mention: bool
    edunews_retrieved: bool
    target_hit: bool
    query_id: int
    query_text: str
    query_strategy: str
    category_slug: str | None
    topic_slug: str | None
    answer_text: str | None
    citazioni: list[CitazioneVista]


class PaginaProbe(BaseModel):
    totale: int
    offset: int
    limit: int
    elementi: list[ProbeVisto]


@router.get("/probes", response_model=PaginaProbe)
async def elenco_probe(
    db: Db,
    admin: Admin,
    days: Annotated[int, QueryParam(ge=1, le=365)] = 30,
    provider: str | None = None,
    mode: Modo | None = None,
    probe_status: Annotated[str | None, QueryParam(alias="status")] = None,
    cited: bool | None = None,
    topic_id: int | None = None,
    q: Annotated[str | None, QueryParam(description="testo contenuto nella domanda")] = None,
    offset: Annotated[int, QueryParam(ge=0)] = 0,
    limit: Annotated[int, QueryParam(ge=1, le=200)] = 50,
) -> PaginaProbe:
    """Elenco paginato con filtri.

    Qui `mode` e' opzionale di proposito, al contrario degli aggregati: questa
    non e' una metrica, e' un'ispezione. Ma il modo di ogni riga e' sempre
    visibile, cosi' non si confondono guardandoli.
    """
    condizioni: list[Any] = [Probe.created_at >= inizio_periodo(days)]
    if provider:
        condizioni.append(Probe.provider == provider)
    if mode:
        condizioni.append(Probe.mode == mode)
    if probe_status:
        condizioni.append(Probe.status == probe_status)
    if cited is not None:
        condizioni.append(Probe.edunews_cited.is_(cited))
    if topic_id is not None:
        condizioni.append(Query.topic_id == topic_id)
    if q:
        condizioni.append(Query.text.ilike(f"%{q}%"))

    totale = (
        await db.execute(
            select(func.count())
            .select_from(Probe)
            .join(Query, Query.id == Probe.query_id)
            .where(*condizioni)
        )
    ).scalar_one()

    righe = (
        await db.execute(
            select(Probe, Query, Topic.slug)
            .join(Query, Query.id == Probe.query_id)
            .outerjoin(Topic, Topic.id == Query.topic_id)
            .where(*condizioni)
            .order_by(Probe.created_at.desc(), Probe.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    ids = [r[0].id for r in righe]
    citazioni: dict[int, list[CitazioneVista]] = {}
    if ids:
        for c in (
            (await db.execute(select(Citation).where(Citation.probe_id.in_(ids)))).scalars().all()
        ):
            citazioni.setdefault(c.probe_id, []).append(
                CitazioneVista(
                    domain=c.domain,
                    url=c.url,
                    title=c.title,
                    kind=c.kind,
                    position=c.position,
                    is_own=c.is_own,
                    own_slug=c.own_slug,
                )
            )

    return PaginaProbe(
        totale=totale,
        offset=offset,
        limit=limit,
        elementi=[_vista(p, query, slug, citazioni.get(p.id, [])) for p, query, slug in righe],
    )


def _vista(
    p: Probe, query: Query, topic_slug: str | None, citazioni: list[CitazioneVista]
) -> ProbeVisto:
    return ProbeVisto(
        id=p.id,
        run_id=p.run_id,
        created_at=p.created_at,
        provider=p.provider,
        model=p.model,
        mode=p.mode,
        status=p.status,
        error=p.error,
        latency_ms=p.latency_ms,
        search_calls=p.search_calls,
        costo_eur=p.cost_eur,
        costo_stimato=p.cost_estimated,
        edunews_cited=p.edunews_cited,
        edunews_mention=p.edunews_mention,
        edunews_retrieved=p.edunews_retrieved,
        target_hit=p.target_hit,
        query_id=query.id,
        query_text=query.text,
        query_strategy=query.strategy,
        category_slug=query.category_slug,
        topic_slug=topic_slug,
        answer_text=p.answer_text,
        citazioni=sorted(citazioni, key=lambda c: (c.kind, c.position or 0)),
    )


class ProbeDettaglio(ProbeVisto):
    raw_response: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Risposta grezza del provider. Azzerata dalla retention dopo "
            "RAW_RETENTION_DAYS: `null` non significa che non c'era, significa "
            "che e' stata potata."
        ),
    )


@router.get("/probes/{probe_id}", response_model=ProbeDettaglio)
async def dettaglio_probe(probe_id: int, db: Db, admin: Admin) -> ProbeDettaglio:
    riga = (
        await db.execute(
            select(Probe, Query, Topic.slug)
            .join(Query, Query.id == Probe.query_id)
            .outerjoin(Topic, Topic.id == Query.topic_id)
            .where(Probe.id == probe_id)
        )
    ).first()
    if riga is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="probe inesistente")

    p, query, slug = riga
    citazioni = [
        CitazioneVista(
            domain=c.domain,
            url=c.url,
            title=c.title,
            kind=c.kind,
            position=c.position,
            is_own=c.is_own,
            own_slug=c.own_slug,
        )
        for c in (
            (await db.execute(select(Citation).where(Citation.probe_id == probe_id)))
            .scalars()
            .all()
        )
    ]
    base = _vista(p, query, slug, citazioni)
    return ProbeDettaglio(**base.model_dump(), raw_response=p.raw_response)


class RunVisto(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    kind: str
    planned: int
    completed: int
    failed: int
    costo_eur: Decimal
    notes: str | None


@router.get("/runs", response_model=list[RunVisto])
async def elenco_run(
    db: Db, admin: Admin, limit: Annotated[int, QueryParam(ge=1, le=500)] = 50
) -> list[RunVisto]:
    righe = (
        (await db.execute(select(Run).order_by(Run.started_at.desc()).limit(limit))).scalars().all()
    )
    return [
        RunVisto(
            id=r.id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            status=r.status,
            kind=r.kind,
            planned=r.planned,
            completed=r.completed,
            failed=r.failed,
            costo_eur=r.cost_eur,
            notes=r.notes,
        )
        for r in righe
    ]


# ---------------------------------------------------------------------------
# Azioni
# ---------------------------------------------------------------------------

# Un solo ciclo manuale per volta. Senza, due clic sul pulsante partirebbero due
# lotti che competono per lo stesso budget.
_lucchetto_manuale = asyncio.Lock()

# Il riferimento al task in corso: un task senza riferimenti e' legittima preda
# del garbage collector, che lo puo' cancellare a meta' ciclo.
_compiti_manuali: set[asyncio.Task[None]] = set()


class EsitoAzione(BaseModel):
    avviato: bool
    messaggio: str


@router.post("/actions/run-now", response_model=EsitoAzione, status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    admin: Admin,
    settings: Config,
    quante: Annotated[int, QueryParam(ge=1, le=50)] = 5,
) -> EsitoAzione:
    """Avvia un ciclo fuori pianificazione e risponde subito.

    Un ciclo dura minuti: tenere aperta la richiesta HTTP fino alla fine
    significherebbe un timeout del reverse proxy e nessun modo di sapere com'e'
    andata. Si risponde 202 e lo stato si legge da `GET /api/runs`.
    """
    if _lucchetto_manuale.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="un ciclo manuale e' gia' in corso: guarda /api/runs",
        )

    async def esegui() -> None:
        from app.db.session import get_sessionmaker
        from app.services.runner import esegui_ciclo

        async with _lucchetto_manuale, get_sessionmaker()() as session:
            try:
                await esegui_ciclo(session, quante=quante, kind="manual", settings=settings)
            except Exception:
                import structlog

                structlog.get_logger(__name__).exception("ciclo manuale fallito")

    compito = asyncio.create_task(esegui())
    _compiti_manuali.add(compito)
    compito.add_done_callback(_compiti_manuali.discard)
    return EsitoAzione(
        avviato=True,
        messaggio=(
            f"Ciclo avviato su {quante} query. Segui l'avanzamento in /api/runs: "
            "la risposta non attende la fine perche' un ciclo dura minuti."
        ),
    )
