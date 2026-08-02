"""SLAVE: esecuzione di un ciclo di probe.

Un ciclo genera il lotto di query, lo manda a ogni provider abilitato, estrae
le citazioni e scrive tutto. La stessa funzione serve il cron orario e
`run-once`: se fossero due percorsi diversi, il comando di collaudo non
proverebbe cio' che gira in produzione.

## Un probe fallito non e' un probe senza citazioni

Il denominatore di ogni tasso conta solo i probe `ok`. Un provider in avaria o
una risposta data senza cercare finiscono registrati con il proprio stato e
restano fuori dai conti: altrimenti un'ora di disservizio somiglierebbe a un
crollo di visibilita' del giornale.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.base import Modo, ProviderAdapter, ProviderError, RisultatoProbe
from app.clients.registry import chiudi_adapter, costruisci_adapter
from app.core.config import Settings, get_settings
from app.models import Citation, Probe, Query, Run, Topic
from app.services import budget, citations, pricing
from app.services.querygen import genera_lotto

log = structlog.get_logger(__name__)


class BudgetEsauritoError(RuntimeError):
    pass


@dataclass
class EsitoCiclo:
    run_id: int
    status: str
    planned: int = 0
    completed: int = 0
    failed: int = 0
    cost_eur: Decimal = Decimal("0")
    per_stato: dict[str, int] = field(default_factory=dict)
    note: str | None = None


@dataclass
class _Compito:
    query: Query
    adapter: ProviderAdapter
    mode: Modo
    slug_attesi: set[str]


async def _slug_per_query(session: AsyncSession, query_ids: list[int]) -> dict[int, set[str]]:
    """Slug dell'articolo che ha generato ogni query, per stabilire `target_hit`."""
    if not query_ids:
        return {}
    righe = (
        await session.execute(
            select(Query.id, Topic.slug)
            .join(Topic, Topic.id == Query.topic_id)
            .where(Query.id.in_(query_ids))
        )
    ).all()
    mappa: dict[int, set[str]] = {}
    for query_id, slug in righe:
        if slug:
            mappa.setdefault(query_id, set()).add(slug)
    return mappa


def _pianifica(
    queries: list[Query],
    adapters: list[ProviderAdapter],
    slug: dict[int, set[str]],
    settings: Settings,
    campionatore,
) -> list[_Compito]:
    compiti: list[_Compito] = []
    for query in queries:
        attesi = slug.get(query.id, set())
        for adapter in adapters:
            compiti.append(_Compito(query, adapter, "retrieval", attesi))
            # I probe in modalita' memoria sono AGGIUNTIVI e campionati: misurano
            # una cosa diversa e non sostituiscono mai un probe di retrieval.
            if campionatore() < settings.memory_mode_sample_rate:
                compiti.append(_Compito(query, adapter, "memory", attesi))
    return compiti


async def _esegui_uno(
    compito: _Compito,
    semaforo: asyncio.Semaphore,
    settings: Settings,
) -> tuple[_Compito, RisultatoProbe | None, str, str | None, int]:
    """Un probe. Non solleva: l'errore diventa lo stato del probe.

    L'ultimo elemento della tupla e' la latenza in millisecondi, misurata anche
    sui fallimenti: un rifiuto immediato e 130 secondi bruciati in timeout sono
    guasti diversi, e senza il tempo non si distinguono dai dati.
    """
    async with semaforo:
        avvio = time.monotonic()
        try:
            risultato = await asyncio.wait_for(
                compito.adapter.probe(compito.query.text, compito.mode),
                # Il doppio del timeout di lettura, piu' un margine per il
                # backoff: con `timeout + 10` il ritento interno su un timeout
                # era irraggiungibile — il primo tentativo poteva consumare da
                # solo tutto il budget e la politica di retry esisteva solo
                # sulla carta.
                timeout=settings.probe_timeout_seconds * 2 + 30,
            )
            return compito, risultato, "ok", None, risultato.latency_ms
        except TimeoutError:
            latenza = int((time.monotonic() - avvio) * 1000)
            return compito, None, "timeout", "timeout complessivo del probe", latenza
        except ProviderError as exc:
            latenza = int((time.monotonic() - avvio) * 1000)
            return compito, None, exc.stato, str(exc)[:1000], latenza
        except Exception as exc:  # pragma: no cover — difesa
            log.exception("errore inatteso nel probe", provider=compito.adapter.name)
            latenza = int((time.monotonic() - avvio) * 1000)
            return compito, None, "error", f"{type(exc).__name__}: {exc}"[:1000], latenza


async def esegui_ciclo(
    session: AsyncSession,
    *,
    quante: int,
    provider: str | None = None,
    kind: str = "manual",
    settings: Settings | None = None,
    campionatore=random.random,
) -> EsitoCiclo:
    settings = settings or get_settings()

    # La riga del run si crea PRIMA di qualunque operazione che possa fallire
    # (controllo del budget, costruzione degli adapter, generazione del lotto):
    # cosi' ogni eccezione, ovunque nasca, trova una riga da chiudere e l'ora
    # non sparisce mai senza spiegazione.
    #
    # E si COMMITTA subito, non solo flush: la riga «in corso» deve essere
    # visibile da fuori mentre il ciclo gira. Con il solo flush restava dentro
    # la transazione: un ciclo bloccato non compariva da nessuna parte e un
    # riavvio faceva rollback — l'ora svaniva senza traccia, che in produzione
    # e' stato scambiato per uno scheduler che non rispetta gli orari.
    run = Run(status="running", kind=kind)
    session.add(run)
    await session.commit()
    run_id = run.id

    adapters: list[ProviderAdapter] = []
    try:
        stato_budget = await budget.stato(session, settings)
        if stato_budget.superato:
            motivo = stato_budget.motivo() or "budget esaurito"
            run.status = "skipped_budget"
            run.finished_at = datetime.now(UTC)
            run.notes = motivo
            await session.commit()
            log.warning("ciclo saltato per budget", motivo=motivo, run_id=run.id)
            return EsitoCiclo(run_id=run.id, status="skipped_budget", note=motivo)

        adapters = costruisci_adapter(settings, solo=provider)
        if not adapters:
            raise ValueError(
                "Nessun provider configurato: metti almeno una chiave API nel .env "
                "(OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY)."
            )
        esito_generazione = await genera_lotto(session, quante, settings=settings)
        queries = esito_generazione.query
        if not queries:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.notes = "nessuna query generata: esegui prima `sender.py sync-topics`"
            await session.commit()
            return EsitoCiclo(run_id=run.id, status="failed", note=run.notes)

        slug = await _slug_per_query(session, [q.id for q in queries])
        compiti = _pianifica(queries, adapters, slug, settings, campionatore)

        run.planned = len(compiti)
        # Anche questo si committa: mentre il ciclo gira la dashboard deve
        # poter mostrare «in corso, 0/28», non una riga vuota.
        await session.commit()

        # Un semaforo PER PROVIDER: il limite di concorrenza e' una proprieta'
        # del provider, non del lotto.
        semafori = {
            a.name: asyncio.Semaphore(settings.max_concurrency_per_provider) for a in adapters
        }
        risultati = await asyncio.gather(
            *(_esegui_uno(c, semafori[c.adapter.name], settings) for c in compiti)
        )

        esito = EsitoCiclo(run_id=run.id, status="running", planned=len(compiti))
        guasti: dict[str, dict[str, int]] = {}
        for compito, risultato, stato_probe, errore, latenza_ms in risultati:
            costo = await _registra(
                session, run, compito, risultato, stato_probe, errore, latenza_ms, settings
            )
            esito.cost_eur += costo
            esito.per_stato[stato_probe] = esito.per_stato.get(stato_probe, 0) + 1
            if stato_probe == "ok":
                esito.completed += 1
            else:
                esito.failed += 1
                per_provider = guasti.setdefault(compito.adapter.name, {})
                per_provider[stato_probe] = per_provider.get(stato_probe, 0) + 1

        await _aggiorna_rotazione(session, queries)

        run.completed = esito.completed
        run.failed = esito.failed
        run.cost_eur = esito.cost_eur
        run.finished_at = datetime.now(UTC)
        if esito.completed == 0:
            run.status = "failed"
        elif esito.failed:
            run.status = "partial"
        else:
            run.status = "ok"
        esito.status = run.status
        if guasti:
            # «parziale · 1 falliti» da solo non dice niente: chi e' fallito e
            # perche' devono stare sulla riga del ciclo, non solo nei log.
            run.notes = "falliti: " + "; ".join(
                f"{provider} " + ", ".join(f"{n} {stato}" for stato, n in sorted(stati.items()))
                for provider, stati in sorted(guasti.items())
            )
            esito.note = run.notes

        await session.commit()
        log.info(
            "ciclo terminato",
            run_id=run.id,
            status=run.status,
            pianificati=esito.planned,
            completati=esito.completed,
            falliti=esito.failed,
            per_stato=esito.per_stato,
            costo_eur=str(esito.cost_eur),
        )
        return esito

    except Exception as exc:
        # La sessione puo' essere in uno stato abortito (per esempio dopo un
        # errore del database): prima il rollback, poi un UPDATE mirato sulla
        # riga gia' committata. Toccare l'oggetto `run` dopo il rollback
        # rischierebbe un refresh implicito su una connessione compromessa.
        await session.rollback()
        await session.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "running")
            .values(
                status="failed",
                finished_at=func.now(),
                notes=f"eccezione durante il ciclo: {type(exc).__name__}: {exc}"[:500],
            )
        )
        await session.commit()
        raise
    finally:
        # Il finally gira anche mentre una CancelledError (il tetto di durata
        # dello scheduler) sta risalendo: un errore nella chiusura di un client
        # HTTP non deve sostituirla ne' oscurare l'eccezione originale.
        try:
            await chiudi_adapter(adapters)
        except Exception:
            log.exception("errore nella chiusura degli adapter")


async def _registra(
    session: AsyncSession,
    run: Run,
    compito: _Compito,
    risultato: RisultatoProbe | None,
    stato_probe: str,
    errore: str | None,
    latenza_ms: int,
    settings: Settings,
) -> Decimal:
    """Scrive il probe e le sue citazioni. Restituisce il costo in EUR."""
    if risultato is None:
        # Un probe fallito non ha costo noto: non si inventa. Se il provider ha
        # fatturato la chiamata comunque, lo si vedra' in fattura e non qui —
        # meglio un buco dichiarato che un numero inventato.
        session.add(
            Probe(
                run_id=run.id,
                query_id=compito.query.id,
                provider=compito.adapter.name,
                model=compito.adapter.model,
                mode=compito.mode,
                status=stato_probe,
                error=errore,
                latency_ms=latenza_ms,
            )
        )
        return Decimal("0")

    esito_parsing = citations.analizza(
        answer_text=risultato.answer_text,
        citazioni_strutturate=risultato.citazioni,
        own_domain=settings.own_domain,
    )
    costo = pricing.calcola(
        provider=risultato.provider,
        model=risultato.model,
        input_tokens=risultato.input_tokens,
        output_tokens=risultato.output_tokens,
        search_calls=risultato.search_calls,
        costo_dichiarato_usd=risultato.cost_usd_provider,
        settings=settings,
    )

    probe = Probe(
        run_id=run.id,
        query_id=compito.query.id,
        provider=risultato.provider,
        model=risultato.model,
        mode=risultato.mode,
        status="ok",
        latency_ms=risultato.latency_ms,
        input_tokens=risultato.input_tokens,
        output_tokens=risultato.output_tokens,
        search_calls=risultato.search_calls,
        cost_eur=costo.eur,
        cost_estimated=costo.stimato,
        answer_text=risultato.answer_text,
        raw_response=risultato.raw,
        edunews_cited=esito_parsing.edunews_cited,
        edunews_mention=esito_parsing.edunews_mention,
        edunews_retrieved=esito_parsing.edunews_retrieved,
        target_hit=citations.e_target_hit(esito_parsing, compito.slug_attesi),
    )
    session.add(probe)
    # Il flush serve subito: le citazioni hanno bisogno di `probe.id`, che lo
    # assegna Postgres.
    await session.flush()

    for citazione in esito_parsing.citazioni:
        session.add(
            Citation(
                probe_id=probe.id,
                domain=citazione.domain,
                url=citazione.url,
                title=citazione.title,
                kind=citazione.kind,
                position=citazione.position,
                is_own=citazione.is_own,
                own_slug=citazione.own_slug,
            )
        )

    return costo.eur


async def _aggiorna_rotazione(session: AsyncSession, queries: list[Query]) -> None:
    """Segna query e topic come sondati, cosi' la rotazione avanza."""
    adesso = datetime.now(UTC)
    query_ids = [q.id for q in queries]
    topic_ids = [q.topic_id for q in queries if q.topic_id is not None]

    if query_ids:
        await session.execute(
            update(Query)
            .where(Query.id.in_(query_ids))
            .values(last_run_at=adesso, run_count=Query.run_count + 1)
        )
    if topic_ids:
        await session.execute(
            update(Topic)
            .where(Topic.id.in_(topic_ids))
            .values(last_probed_at=adesso, probe_count=Topic.probe_count + 1)
        )


async def conta_probe(session: AsyncSession, run_id: int) -> int:
    return (
        await session.execute(select(func.count()).select_from(Probe).where(Probe.run_id == run_id))
    ).scalar_one()
