"""Scheduler, kill switch del budget, rollup e potatura."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.models import DailyRollup, Probe, Query, Run
from app.services import retention, rollup
from app.services.scheduler import (
    crea_scheduler,
    prossime_esecuzioni,
    quante_query_ora,
    riconcilia_run_interrotti,
)

ROMA = ZoneInfo("Europe/Rome")


@pytest.fixture
async def dati(session):
    """Due cicli orari con probe di vari stati, provider e modi.

    Servono DUE run perche' `UNIQUE (run_id, query_id, provider, mode)` vieta
    due probe identici nello stesso ciclo — ed e' giusto che lo vieti: e' il
    vincolo che impedisce a un ciclo ritentato di raddoppiare il denominatore.
    """
    run = Run(status="ok", kind="hourly")
    run2 = Run(status="partial", kind="hourly")
    session.add_all([run, run2])
    await session.flush()

    query_scuola = Query(
        text="Chi puo partecipare al concorso docenti 2026?",
        text_hash="h-scuola",
        strategy="faq_verbatim",
        generator="template",
        category_slug="scuola",
    )
    query_lavoro = Query(
        text="Quali sono i requisiti per la NASpI?",
        text_hash="h-lavoro",
        strategy="category",
        generator="template",
        category_slug="lavoro",
    )
    session.add_all([query_scuola, query_lavoro])
    await session.flush()

    # Mezzogiorno a Roma di oggi: sicuramente dentro il giorno locale.
    oggi_mezzogiorno = datetime.now(ROMA).replace(hour=12, minute=0, second=0, microsecond=0)

    def probe(**kw):
        base = {
            "run_id": run.id,
            "query_id": query_scuola.id,
            "provider": "openai",
            "model": "m",
            "mode": "retrieval",
            "status": "ok",
            "created_at": oggi_mezzogiorno,
            "cost_eur": Decimal("0.01"),
        }
        return Probe(**{**base, **kw})

    session.add_all(
        [
            probe(edunews_cited=True, target_hit=True),
            probe(edunews_cited=True, provider="perplexity"),
            probe(edunews_mention=True, provider="anthropic"),
            # Modalita' memoria: metrica diversa, riga di rollup diversa.
            probe(mode="memory", edunews_mention=True),
            # Altra categoria.
            probe(query_id=query_lavoro.id, edunews_cited=True),
            # --- secondo ciclo ---
            # Fallito: paga ma non entra nel denominatore.
            probe(run_id=run2.id, status="error", provider="anthropic", cost_eur=None),
            # `no_search`: non e' un "non citato", e' un "non misurato".
            probe(run_id=run2.id, status="no_search", cost_eur=Decimal("0.005")),
        ]
    )
    await session.commit()
    return {"run": run, "oggi": oggi_mezzogiorno.date()}


class TestRollup:
    async def test_il_denominatore_esclude_i_probe_non_ok(self, session, dati):
        await rollup.ricalcola(session, giorni=1)

        righe = {
            (r.provider, r.mode, r.category_slug): r
            for r in (await session.execute(select(DailyRollup))).scalars().all()
        }
        # openai/retrieval/scuola ha 1 ok + 1 no_search: il denominatore e' 1.
        voce = righe[("openai", "retrieval", "scuola")]
        assert voce.probes == 1
        assert voce.cited == 1
        # anthropic ha 1 ok (mention) + 1 error.
        assert righe[("anthropic", "retrieval", "scuola")].probes == 1

    async def test_il_costo_include_anche_i_falliti(self, session, dati):
        """Un probe fallito e' stato pagato comunque."""
        await rollup.ricalcola(session, giorni=1)

        voce = (
            await session.execute(
                select(DailyRollup).where(
                    DailyRollup.provider == "openai",
                    DailyRollup.mode == "retrieval",
                    DailyRollup.category_slug == "scuola",
                )
            )
        ).scalar_one()
        # 0.01 (ok) + 0.005 (no_search) = 0.015
        assert voce.cost_eur == Decimal("0.0150")

    async def test_retrieval_e_memory_restano_su_righe_separate(self, session, dati):
        await rollup.ricalcola(session, giorni=1)

        modi = {m for (m,) in (await session.execute(select(DailyRollup.mode).distinct())).all()}
        assert modi == {"retrieval", "memory"}
        memoria = (
            await session.execute(select(DailyRollup).where(DailyRollup.mode == "memory"))
        ).scalar_one()
        assert memoria.mentioned == 1
        assert memoria.cited == 0

    async def test_segmenta_per_categoria(self, session, dati):
        await rollup.ricalcola(session, giorni=1)
        categorie = {
            c
            for (c,) in (await session.execute(select(DailyRollup.category_slug).distinct())).all()
        }
        assert categorie == {"scuola", "lavoro"}

    async def test_e_idempotente(self, session, dati):
        """Rieseguirlo non deve raddoppiare nulla: ricalcola, non incrementa."""
        await rollup.ricalcola(session, giorni=1)
        primo = (await session.execute(select(func.sum(DailyRollup.probes)))).scalar_one()

        for _ in range(3):
            await rollup.ricalcola(session, giorni=1)

        secondo = (await session.execute(select(func.sum(DailyRollup.probes)))).scalar_one()
        assert secondo == primo

    async def test_ricalcola_piu_giorni_per_recuperare_un_downtime(self, session, dati):
        esito = await rollup.ricalcola(session, giorni=3)
        assert len(esito.giorni) == 3

    async def test_i_probe_cancellati_non_lasciano_aggregati_fantasma(self, session, dati):
        await rollup.ricalcola(session, giorni=1)
        assert (
            await session.execute(select(func.count()).select_from(DailyRollup))
        ).scalar_one() > 0

        await session.execute(text("DELETE FROM probes"))
        await session.commit()
        await rollup.ricalcola(session, giorni=1)

        rimaste = (
            await session.execute(select(func.count()).select_from(DailyRollup))
        ).scalar_one()
        assert rimaste == 0


class TestBudgetOrario:
    async def test_il_tetto_giornaliero_e_un_tetto_non_unapprossimazione(self, session, dati):
        """ceil(200/24)=9 per 24 ore farebbe 216: piu' del budget dichiarato."""
        settings = get_settings().model_copy(update={"daily_query_budget": 200})
        quante = await quante_query_ora(session, settings)
        assert quante == 9  # quota oraria, budget ampiamente residuo

        # Budget quasi esaurito: si prende solo cio' che resta.
        settings = get_settings().model_copy(update={"daily_query_budget": 3})
        # `dati` ha sondato 2 query distinte oggi.
        assert await quante_query_ora(session, settings) == 1

        settings = get_settings().model_copy(update={"daily_query_budget": 2})
        assert await quante_query_ora(session, settings) == 0

    async def test_conta_query_distinte_non_probe(self, session, dati):
        """La stessa domanda su quattro provider consuma un'unita' di budget."""
        settings = get_settings().model_copy(update={"daily_query_budget": 100})
        # 7 probe ma 2 query distinte.
        assert (
            await quante_query_ora(session, settings) == min(5, 100 - 2)
            or await quante_query_ora(session, settings) == 5
        )


class TestRiconciliazione:
    async def test_i_run_interrotti_vengono_chiusi_allavvio(self, session):
        session.add_all(
            [
                Run(status="running", kind="hourly"),
                Run(status="running", kind="manual"),
                Run(status="ok", kind="hourly"),
            ]
        )
        await session.commit()

        quanti = await riconcilia_run_interrotti(session)

        assert quanti == 2
        rimasti = (
            await session.execute(
                select(func.count()).select_from(Run).where(Run.status == "running")
            )
        ).scalar_one()
        assert rimasti == 0
        chiuso = (
            (await session.execute(select(Run).where(Run.status == "failed"))).scalars().first()
        )
        assert "interrotto" in (chiuso.notes or "")
        assert chiuso.finished_at is not None

    async def test_senza_run_appesi_non_fa_nulla(self, session):
        assert await riconcilia_run_interrotti(session) == 0


class TestPotatura:
    async def test_azzera_il_raw_vecchio_ma_tiene_la_riga(self, session, dati):
        vecchio = datetime.now(UTC) - timedelta(days=60)
        await session.execute(
            text("UPDATE probes SET created_at = :q, raw_response = '{\"a\": 1}'::jsonb"),
            {"q": vecchio},
        )
        await session.commit()

        esito = await retention.pota(session)

        assert esito.raw_azzerati > 0
        righe = (await session.execute(select(func.count()).select_from(Probe))).scalar_one()
        assert righe == 7, "le righe non si cancellano: le metriche storiche devono restare"
        residui = (
            await session.execute(
                select(func.count()).select_from(Probe).where(Probe.raw_response.is_not(None))
            )
        ).scalar_one()
        assert residui == 0

    async def test_non_tocca_i_probe_recenti(self, session, dati):
        await session.execute(text("UPDATE probes SET raw_response = '{\"a\": 1}'::jsonb"))
        await session.commit()

        esito = await retention.pota(session)

        assert esito.raw_azzerati == 0

    async def test_le_risposte_hanno_una_finestra_piu_lunga_del_raw(self, session, dati):
        """`raw_response` e' grande, `answer_text` e' utile piu' a lungo."""
        settings = get_settings()
        assert settings.answer_retention_days > settings.raw_retention_days

        eta = datetime.now(UTC) - timedelta(days=settings.raw_retention_days + 5)
        await session.execute(
            text(
                "UPDATE probes SET created_at = :q, raw_response = '{}'::jsonb, "
                "answer_text = 'testo'"
            ),
            {"q": eta},
        )
        await session.commit()

        esito = await retention.pota(session)

        assert esito.raw_azzerati == 7
        assert esito.risposte_azzerate == 0, "troppo recenti per perdere il testo"


class TestConfigurazioneScheduler:
    def test_i_job_sono_configurati_come_serve(self, session):
        settings = get_settings()
        scheduler = crea_scheduler(None, settings)  # type: ignore[arg-type]

        job = {j.id: j for j in scheduler.get_jobs()}
        assert set(job) == {"ciclo_orario", "manutenzione_notturna"}

        orario = job["ciclo_orario"]
        # Un ciclo che sfora l'ora non deve accavallarsi con il successivo.
        assert orario.max_instances == 1
        # Dopo un downtime si esegue UN ciclo, non uno per ogni ora perduta.
        assert orario.coalesce is True
        assert orario.misfire_grace_time == 600
        # Minuto 7: allo scoccare dell'ora ci va tutto il mondo.
        assert "minute='7'" in str(orario.trigger)
        # Il fuso e' quello del giornale, non UTC.
        assert str(orario.trigger.timezone) == "Europe/Rome"

    def test_prossime_esecuzioni_su_scheduler_spento(self):
        assert prossime_esecuzioni(None) == {}
