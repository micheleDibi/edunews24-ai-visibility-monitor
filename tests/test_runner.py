"""Ciclo completo: dal catalogo ai probe salvati, con provider finti.

Gli adapter veri sono coperti da `test_adapters.py`; qui interessa che il ciclo
scriva la cosa giusta nel database — e soprattutto che un provider in avaria non
somigli a un crollo di visibilita' del giornale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.clients.base import (
    CitazioneGrezza,
    Modo,
    ProviderError,
    RateLimitError,
    RicercaNonEseguitaError,
    RisultatoProbe,
)
from app.core.config import get_settings
from app.models import Citation, Probe, Query, Run, Topic
from app.services import runner

ADESSO = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class AdapterFinto:
    """Provider finto. `comportamento` decide cosa fa ogni probe."""

    supports_retrieval = True

    def __init__(self, name: str, comportamento="ok", model: str = "modello-finto"):
        self.name = name
        self.model = model
        self._comportamento = comportamento
        self.chiamate: list[tuple[str, str]] = []
        self.chiuso = False

    async def probe(self, query: str, mode: Modo) -> RisultatoProbe:
        self.chiamate.append((query, mode))
        if callable(self._comportamento):
            return self._comportamento(query, mode)
        if self._comportamento == "errore":
            raise ProviderError(f"{self.name}: 503")
        if self._comportamento == "rate_limit":
            raise RateLimitError(f"{self.name}: 429")
        if self._comportamento == "no_search":
            raise RicercaNonEseguitaError(f"{self.name}: nessuna ricerca")

        cita = self._comportamento == "cita"
        return RisultatoProbe(
            provider=self.name,
            model=self.model,
            mode=mode,
            answer_text="I posti salgono a 30.000.",
            citazioni=[
                CitazioneGrezza(url="https://orizzontescuola.it/a", kind="source", position=1),
                CitazioneGrezza(
                    url="https://edunews24.it/scuola/articolo-1"
                    if cita
                    else "https://tecnicadellascuola.it/b",
                    kind="citation",
                    position=1,
                ),
            ],
            input_tokens=10_000,
            output_tokens=500,
            search_calls=2,
            latency_ms=1234,
            raw={"finto": True},
        )

    async def close(self) -> None:
        self.chiuso = True


@pytest.fixture
def settings_test():
    # Campionamento memoria a zero: i test che lo vogliono lo alzano.
    return get_settings().model_copy(
        update={"memory_mode_sample_rate": 0.0, "query_rewrite_enabled": False}
    )


@pytest.fixture
async def catalogo(session):
    topics = [
        Topic(
            source_id=n,
            slug=f"articolo-{n}",
            title=f"Titolo dell'articolo numero {n}, con una coda",
            category_slug="scuola",
            keyword=f"argomento numero {n}",
            tags=[],
            faq_questions=[],
            probe_count=0,
            published_at=ADESSO - timedelta(hours=n),
        )
        for n in range(1, 7)
    ]
    session.add_all(topics)
    await session.commit()
    return topics


def _patcha_adapter(monkeypatch, adapters):
    monkeypatch.setattr(runner, "costruisci_adapter", lambda settings, solo=None: adapters)


class TestCicloFelice:
    async def test_scrive_un_probe_per_query_e_provider(
        self, session, catalogo, settings_test, monkeypatch
    ):
        a, b = AdapterFinto("openai"), AdapterFinto("perplexity")
        _patcha_adapter(monkeypatch, [a, b])

        esito = await runner.esegui_ciclo(session, quante=3, settings=settings_test)

        assert esito.status == "ok"
        assert esito.planned == 6  # 3 query x 2 provider
        assert esito.completed == 6
        assert esito.failed == 0
        assert await runner.conta_probe(session, esito.run_id) == 6

    async def test_registra_le_citazioni_di_tutti_i_domini(
        self, session, catalogo, settings_test, monkeypatch
    ):
        _patcha_adapter(monkeypatch, [AdapterFinto("openai", "cita")])

        await runner.esegui_ciclo(session, quante=2, settings=settings_test)

        domini = {d for (d,) in (await session.execute(select(Citation.domain).distinct())).all()}
        assert "edunews24.it" in domini
        assert "orizzontescuola.it" in domini, "servono anche gli altri: chi occupa il posto"

    async def test_distingue_citate_e_recuperate(
        self, session, catalogo, settings_test, monkeypatch
    ):
        _patcha_adapter(monkeypatch, [AdapterFinto("openai", "cita")])

        await runner.esegui_ciclo(session, quante=1, settings=settings_test)

        probe = (await session.execute(select(Probe))).scalars().first()
        assert probe.edunews_cited is True
        assert probe.edunews_retrieved is True
        tipi = {k for (k,) in (await session.execute(select(Citation.kind).distinct())).all()}
        assert tipi == {"citation", "source"}

    async def test_target_hit_solo_sullarticolo_giusto(
        self, session, catalogo, settings_test, monkeypatch
    ):
        """L'adapter finto cita sempre `articolo-1`: solo la query nata da quel
        topic e' un target hit, le altre sono citazioni del sito ma non del pezzo."""
        _patcha_adapter(monkeypatch, [AdapterFinto("openai", "cita")])

        await runner.esegui_ciclo(session, quante=6, settings=settings_test)

        righe = (
            await session.execute(
                select(Topic.slug, Probe.target_hit, Probe.edunews_cited)
                .join(Query, Query.id == Probe.query_id)
                .join(Topic, Topic.id == Query.topic_id)
            )
        ).all()
        assert righe, "servono probe legati a un topic"
        for slug, target_hit, cited in righe:
            assert cited is True
            assert target_hit is (slug == "articolo-1")

    async def test_avanza_la_rotazione(self, session, catalogo, settings_test, monkeypatch):
        _patcha_adapter(monkeypatch, [AdapterFinto("openai")])

        await runner.esegui_ciclo(session, quante=3, settings=settings_test)

        sondati = (
            await session.execute(
                select(func.count()).select_from(Topic).where(Topic.last_probed_at.is_not(None))
            )
        ).scalar_one()
        assert sondati >= 1
        eseguite = (
            await session.execute(
                select(func.count()).select_from(Query).where(Query.run_count > 0)
            )
        ).scalar_one()
        assert eseguite >= 3

    async def test_chiude_sempre_gli_adapter(self, session, catalogo, settings_test, monkeypatch):
        a = AdapterFinto("openai")
        _patcha_adapter(monkeypatch, [a])
        await runner.esegui_ciclo(session, quante=1, settings=settings_test)
        assert a.chiuso is True


class TestFallimenti:
    async def test_un_provider_in_avaria_non_e_un_crollo_di_visibilita(
        self, session, catalogo, settings_test, monkeypatch
    ):
        """I probe falliti restano registrati col proprio stato, fuori dai conti."""
        _patcha_adapter(
            monkeypatch, [AdapterFinto("openai", "cita"), AdapterFinto("perplexity", "errore")]
        )

        esito = await runner.esegui_ciclo(session, quante=2, settings=settings_test)

        assert esito.status == "partial"
        assert esito.completed == 2
        assert esito.failed == 2
        falliti = (
            (await session.execute(select(Probe).where(Probe.provider == "perplexity")))
            .scalars()
            .all()
        )
        assert all(p.status == "error" for p in falliti)
        assert all(p.edunews_cited is False for p in falliti)
        assert all(p.cost_eur is None for p in falliti), "un costo ignoto non si inventa"

    @pytest.mark.parametrize(
        ("comportamento", "stato"),
        [("errore", "error"), ("rate_limit", "rate_limited"), ("no_search", "no_search")],
    )
    async def test_ogni_errore_ha_il_proprio_stato(
        self, session, catalogo, settings_test, monkeypatch, comportamento, stato
    ):
        _patcha_adapter(monkeypatch, [AdapterFinto("openai", comportamento)])

        esito = await runner.esegui_ciclo(session, quante=1, settings=settings_test)

        assert esito.status == "failed"
        assert esito.per_stato == {stato: 1}
        probe = (await session.execute(select(Probe))).scalars().one()
        assert probe.status == stato
        assert probe.error

    async def test_tutti_falliti_da_run_failed(self, session, catalogo, settings_test, monkeypatch):
        _patcha_adapter(monkeypatch, [AdapterFinto("openai", "errore")])
        esito = await runner.esegui_ciclo(session, quante=2, settings=settings_test)
        assert esito.status == "failed"

    async def test_a_catalogo_vuoto_restano_le_domande_di_categoria(
        self, session, settings_test, monkeypatch
    ):
        """Le domande di categoria non dipendono dal catalogo: il ciclo gira comunque."""
        _patcha_adapter(monkeypatch, [AdapterFinto("openai")])
        # Con 10 richieste la quota categoria e' 1 (il 10% di 10).
        esito = await runner.esegui_ciclo(session, quante=10, settings=settings_test)
        assert esito.planned == 1
        assert esito.status == "ok"

    async def test_lotto_troppo_piccolo_e_catalogo_vuoto_spiega_cosa_fare(
        self, session, settings_test, monkeypatch
    ):
        """Con 2 richieste la quota categoria e' 0: senza topic non c'e' nulla da mandare."""
        _patcha_adapter(monkeypatch, [AdapterFinto("openai")])
        esito = await runner.esegui_ciclo(session, quante=2, settings=settings_test)
        assert esito.status == "failed"
        assert "sync-topics" in (esito.note or ""), "l'errore deve dire cosa fare"

    async def test_nessun_provider_configurato(self, session, catalogo, settings_test, monkeypatch):
        _patcha_adapter(monkeypatch, [])
        with pytest.raises(ValueError, match="Nessun provider"):
            await runner.esegui_ciclo(session, quante=1, settings=settings_test)


class TestBudget:
    async def test_il_ciclo_si_salta_se_il_tetto_e_raggiunto(self, session, catalogo, monkeypatch):
        """Il controllo va fatto prima di spendere: dopo, i soldi sono usciti."""
        adapter = AdapterFinto("openai")
        _patcha_adapter(monkeypatch, [adapter])
        settings = get_settings().model_copy(
            update={
                "memory_mode_sample_rate": 0.0,
                "query_rewrite_enabled": False,
                "max_daily_spend_eur": 0.001,
            }
        )
        # Un probe pregresso che ha gia' consumato il tetto.
        run = Run(status="ok", kind="manual")
        session.add(run)
        await session.flush()
        session.add(
            Query(
                text="Una domanda qualsiasi sulla scuola?",
                text_hash="h1",
                strategy="category",
                generator="template",
            )
        )
        await session.flush()
        query = (await session.execute(select(Query))).scalars().first()
        session.add(
            Probe(
                run_id=run.id,
                query_id=query.id,
                provider="openai",
                model="m",
                mode="retrieval",
                status="ok",
                cost_eur=Decimal("5.00"),
            )
        )
        await session.commit()

        esito = await runner.esegui_ciclo(session, quante=3, settings=settings)

        assert esito.status == "skipped_budget"
        assert adapter.chiamate == [], "nessuna chiamata a pagamento deve partire"
        salvato = (await session.execute(select(Run).where(Run.id == esito.run_id))).scalar_one()
        assert salvato.status == "skipped_budget"
        assert "tetto giornaliero" in (salvato.notes or "")


class TestModalitaMemoria:
    async def test_i_probe_di_memoria_sono_aggiuntivi(self, session, catalogo, monkeypatch):
        """Non sostituiscono mai un probe di retrieval: misurano un'altra cosa."""
        _patcha_adapter(monkeypatch, [AdapterFinto("openai")])
        settings = get_settings().model_copy(
            update={"memory_mode_sample_rate": 1.0, "query_rewrite_enabled": False}
        )

        esito = await runner.esegui_ciclo(
            session, quante=2, settings=settings, campionatore=lambda: 0.0
        )

        assert esito.planned == 4  # 2 query x (retrieval + memory)
        modi = [m for (m,) in (await session.execute(select(Probe.mode))).all()]
        assert modi.count("retrieval") == 2
        assert modi.count("memory") == 2

    async def test_campionamento_a_zero_non_produce_probe_di_memoria(
        self, session, catalogo, settings_test, monkeypatch
    ):
        _patcha_adapter(monkeypatch, [AdapterFinto("openai")])
        await runner.esegui_ciclo(
            session, quante=2, settings=settings_test, campionatore=lambda: 0.99
        )
        modi = {m for (m,) in (await session.execute(select(Probe.mode))).all()}
        assert modi == {"retrieval"}
