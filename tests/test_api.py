"""API: autenticazione e — soprattutto — onesta' degli aggregati.

I test che contano qui non sono quelli sui codici di stato. Sono quelli che
verificano che un provider in avaria non somigli a un crollo di visibilita', che
`retrieval` e `memory` non si mescolino, e che una percentuale non esca mai
senza il suo denominatore.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.api.metrics import SOGLIA_AFFIDABILITA, SOGLIA_MINIMA, wilson
from app.core.security import NOME_COOKIE
from app.models import Citation, Probe, Query, Run, Topic
from tests.conftest import PASSWORD_TEST

ADESSO = datetime.now(UTC)


@pytest.fixture
async def client(engine):
    """Client ASGI. Il lifespan NON parte: `assert_readonly` richiederebbe un
    ruolo di sola lettura, che qui non serve e ha test propri."""
    from app.main import crea_app

    trasporto = httpx.ASGITransport(app=crea_app())
    async with httpx.AsyncClient(
        transport=trasporto, base_url="http://test", follow_redirects=True
    ) as c:
        yield c


@pytest.fixture
async def autenticato(client):
    risposta = await client.post("/api/auth/login", json={"password": PASSWORD_TEST})
    assert risposta.status_code == 200, risposta.text
    return client


@pytest.fixture
async def catalogo(session):
    """Un topic, due query, e probe pensati per far emergere le tre regole."""
    topic = Topic(
        source_id=1,
        slug="concorso-docenti-2026",
        title="Concorso docenti 2026, i posti salgono",
        category_slug="scuola",
        keyword="concorso docenti 2026",
        tags=[],
        faq_questions=[],
        probe_count=0,
        published_at=ADESSO - timedelta(days=1),
    )
    session.add(topic)
    await session.flush()

    q_topic = Query(
        text="Chi puo partecipare al concorso docenti 2026?",
        text_hash="h1",
        strategy="faq_verbatim",
        generator="template",
        category_slug="scuola",
        topic_id=topic.id,
    )
    q_cat = Query(
        text="Quali sono i requisiti per la NASpI?",
        text_hash="h2",
        strategy="category",
        generator="template",
        category_slug="lavoro",
    )
    session.add_all([q_topic, q_cat])
    await session.flush()

    run = Run(status="ok", kind="hourly")
    session.add(run)
    await session.flush()

    def probe(n: int, **kw):
        base = {
            "run_id": run.id,
            "query_id": q_topic.id,
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "mode": "retrieval",
            "status": "ok",
            "created_at": ADESSO - timedelta(hours=1),
            "cost_eur": Decimal("0.01"),
            "latency_ms": 1000 + n,
            "search_calls": 2,
        }
        return Probe(**{**base, **kw})

    # 12 probe riusciti su `scuola`, 3 dei quali citano: tasso 25% su n=12,
    # sopra SOGLIA_MINIMA ma sotto SOGLIA_AFFIDABILITA.
    probe_ok = []
    for n in range(12):
        r = Run(status="ok", kind="hourly")
        session.add(r)
        await session.flush()
        probe_ok.append(
            probe(n, run_id=r.id, edunews_cited=n < 3, target_hit=n == 0, edunews_retrieved=n < 5)
        )
    session.add_all(probe_ok)

    # Probe che NON devono entrare nei denominatori.
    run_falliti = Run(status="partial", kind="hourly")
    session.add(run_falliti)
    await session.flush()
    session.add_all(
        [
            probe(90, run_id=run_falliti.id, status="error", cost_eur=None),
            probe(91, run_id=run_falliti.id, status="no_search", provider="anthropic"),
            # Modalita' memoria: metrica diversa.
            probe(92, run_id=run_falliti.id, mode="memory", edunews_mention=True),
            # Altra categoria.
            probe(93, run_id=run_falliti.id, query_id=q_cat.id, edunews_cited=True),
        ]
    )
    await session.flush()

    # Citazioni: domini altrui piu' il nostro, piu' un URL non risolto.
    primo = probe_ok[0]
    session.add_all(
        [
            Citation(
                probe_id=primo.id,
                domain="edunews24.it",
                url="https://edunews24.it/scuola/concorso-docenti-2026",
                kind="citation",
                position=1,
                is_own=True,
                own_slug="concorso-docenti-2026",
            ),
            Citation(
                probe_id=primo.id,
                domain="orizzontescuola.it",
                url="https://orizzontescuola.it/a",
                kind="citation",
                position=2,
            ),
            Citation(
                probe_id=primo.id,
                domain="unresolved",
                url="https://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
                kind="citation",
                position=3,
            ),
        ]
    )
    await session.commit()
    return {"topic": topic, "query": q_topic, "probe": probe_ok}


# ---------------------------------------------------------------------------
# Autenticazione
# ---------------------------------------------------------------------------


class TestAutenticazione:
    async def test_health_e_pubblico(self, client):
        """Lo usa l'HEALTHCHECK del container, che non ha una sessione."""
        risposta = await client.get("/api/health")
        assert risposta.status_code == 200
        assert risposta.json()["database"] == "ok"

    async def test_tutto_il_resto_richiede_la_sessione(self, client):
        for percorso in (
            "/api/me",
            "/api/kpi",
            "/api/trend",
            "/api/providers",
            "/api/categories",
            "/api/gaps",
            "/api/wins",
            "/api/domains",
            "/api/probes",
            "/api/runs",
            "/api/costs",
        ):
            risposta = await client.get(percorso)
            assert risposta.status_code == 401, f"{percorso} non e' protetto"

        assert (await client.post("/api/actions/run-now")).status_code == 401

    async def test_password_sbagliata(self, client):
        risposta = await client.post("/api/auth/login", json={"password": "sbagliata"})
        assert risposta.status_code == 401
        assert NOME_COOKIE not in risposta.cookies

    async def test_login_mette_un_cookie_httponly(self, client):
        risposta = await client.post("/api/auth/login", json={"password": PASSWORD_TEST})
        assert risposta.status_code == 200
        intestazione = risposta.headers["set-cookie"]
        assert "HttpOnly" in intestazione
        # SameSite=Lax e' cio' che protegge `POST /api/actions/run-now` dal CSRF.
        assert "SameSite=lax" in intestazione or "samesite=lax" in intestazione.lower()

    async def test_dopo_il_login_le_rotte_rispondono(self, autenticato):
        assert (await autenticato.get("/api/me")).json() == {"soggetto": "admin"}
        assert (await autenticato.get("/api/kpi")).status_code == 200

    async def test_logout_chiude_la_sessione(self, autenticato):
        await autenticato.post("/api/auth/logout")
        autenticato.cookies.clear()
        assert (await autenticato.get("/api/me")).status_code == 401

    async def test_un_cookie_falsificato_non_vale(self, client):
        client.cookies.set(NOME_COOKIE, "non.un.jwt")
        assert (await client.get("/api/me")).status_code == 401

    async def test_troppi_tentativi_vengono_bloccati(self, client):
        from app.core import security

        security._tentativi.clear()
        codici = [
            (await client.post("/api/auth/login", json={"password": "x"})).status_code
            for _ in range(8)
        ]
        assert 429 in codici, "il login deve avere un freno"
        security._tentativi.clear()


# ---------------------------------------------------------------------------
# Le tre regole
# ---------------------------------------------------------------------------


class TestRegoleDiCorrettezza:
    async def test_i_probe_falliti_non_entrano_nel_denominatore(self, autenticato, catalogo):
        """Un provider in avaria non deve somigliare a un crollo di visibilita'."""
        dati = (await autenticato.get("/api/kpi?days=7")).json()

        # 12 riusciti su `scuola` + 1 riuscito su `lavoro` = 13.
        assert dati["citation_rate"]["denominatore"] == 13
        # error e no_search restano visibili, ma a parte.
        assert dati["probe_falliti"] == 1
        assert dati["probe_senza_ricerca"] == 1

    async def test_il_costo_include_i_falliti_e_lo_dichiara(self, autenticato, catalogo):
        dati = (await autenticato.get("/api/kpi?days=7")).json()
        # 13 probe ok + no_search + memory a 0.01, l'error a None.
        assert Decimal(dati["costo_eur"]) > Decimal("0.13")

    async def test_retrieval_e_memory_non_si_mescolano(self, autenticato, catalogo):
        retrieval = (await autenticato.get("/api/kpi?days=7&mode=retrieval")).json()
        memoria = (await autenticato.get("/api/kpi?days=7&mode=memory")).json()

        assert retrieval["citation_rate"]["denominatore"] == 13
        assert memoria["citation_rate"]["denominatore"] == 1
        assert memoria["mention_rate"]["numeratore"] == 1
        assert retrieval["mention_rate"]["numeratore"] == 0

    async def test_nessun_tasso_senza_denominatore(self, autenticato, catalogo):
        """Ogni rapporto esce con numeratore e denominatore visibili."""
        for percorso in ("/api/kpi?days=7", "/api/providers?days=7", "/api/categories?days=7"):
            corpo = (await autenticato.get(percorso)).json()
            righe = corpo if isinstance(corpo, list) else [corpo]
            for riga in righe:
                for chiave, valore in riga.items():
                    if isinstance(valore, dict) and "tasso" in valore:
                        assert "numeratore" in valore, f"{percorso}/{chiave}"
                        assert "denominatore" in valore, f"{percorso}/{chiave}"

    async def test_un_tasso_su_pochi_casi_non_viene_calcolato(self, autenticato, catalogo):
        """`lavoro` ha un solo probe: il conteggio si mostra, la percentuale no."""
        celle = (await autenticato.get("/api/categories?days=7")).json()
        lavoro = next(c for c in celle if c["category_slug"] == "lavoro")

        assert lavoro["citation_rate"]["denominatore"] == 1
        assert lavoro["citation_rate"]["tasso"] is None
        assert lavoro["citation_rate"]["affidabile"] is False

    async def test_un_tasso_calcolabile_ma_non_affidabile_lo_dichiara(self, autenticato, catalogo):
        """12 probe: sopra la soglia minima, sotto quella di affidabilita'."""
        celle = (await autenticato.get("/api/categories?days=7")).json()
        scuola = next(c for c in celle if c["category_slug"] == "scuola")

        assert SOGLIA_MINIMA <= scuola["citation_rate"]["denominatore"] < SOGLIA_AFFIDABILITA
        assert scuola["citation_rate"]["tasso"] == 0.25
        assert scuola["citation_rate"]["affidabile"] is False
        assert scuola["citation_rate"]["ic_basso"] < 0.25 < scuola["citation_rate"]["ic_alto"]


class TestWilson:
    def test_resta_dentro_zero_uno_anche_senza_successi(self):
        basso, alto = wilson(0, 20)
        assert basso == 0.0
        assert 0 < alto < 1, "con zero successi il limite superiore non e' zero"

    def test_un_campione_piu_grande_stringe_lintervallo(self):
        piccolo = wilson(5, 20)
        grande = wilson(250, 1000)
        assert (grande[1] - grande[0]) < (piccolo[1] - piccolo[0])

    def test_denominatore_zero(self):
        assert wilson(0, 0) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Le sezioni operative
# ---------------------------------------------------------------------------


class TestSezioniOperative:
    async def test_gaps_richiede_una_numerosita_minima(self, autenticato, catalogo):
        """Un articolo sondato due volte e mai citato e' rumore, non un dato."""
        # Il nostro topic e' citato: non deve comparire fra le lacune.
        assert (await autenticato.get("/api/gaps?days=7&min_probe=1")).json() == []

    async def test_wins_elenca_gli_articoli_citati(self, autenticato, catalogo):
        vittorie = (await autenticato.get("/api/wins?days=7")).json()
        assert len(vittorie) == 1
        v = vittorie[0]
        assert v["slug"] == "concorso-docenti-2026"
        assert v["citazioni"] == 3
        assert v["target_hit"] == 1
        assert v["provider"] == ["openai"]

    async def test_domains_mostra_anche_chi_non_e_nostro(self, autenticato, catalogo):
        """Senza gli altri domini non si sa chi occupa il posto quando manchiamo."""
        domini = {d["domain"]: d for d in (await autenticato.get("/api/domains?days=7")).json()}

        assert "orizzontescuola.it" in domini
        assert domini["edunews24.it"]["proprio"] is True
        assert domini["orizzontescuola.it"]["proprio"] is False

    async def test_domains_dichiara_i_non_risolti_invece_di_nasconderli(
        self, autenticato, catalogo
    ):
        domini = {d["domain"]: d for d in (await autenticato.get("/api/domains?days=7")).json()}
        assert domini["unresolved"]["non_risolto"] is True

    async def test_probes_paginato_e_filtrabile(self, autenticato, catalogo):
        pagina = (await autenticato.get("/api/probes?days=7&limit=5")).json()
        # 12 riusciti + error + no_search + memory + la query di categoria.
        assert pagina["totale"] == 16
        assert len(pagina["elementi"]) == 5

        citati = (await autenticato.get("/api/probes?days=7&cited=true")).json()
        assert citati["totale"] == 4
        assert all(e["edunews_cited"] for e in citati["elementi"])

        per_provider = (await autenticato.get("/api/probes?days=7&provider=anthropic")).json()
        assert per_provider["totale"] == 1

        per_testo = (await autenticato.get("/api/probes?days=7&q=NASpI")).json()
        assert per_testo["totale"] == 1

    async def test_probes_espone_la_query_e_le_citazioni(self, autenticato, catalogo):
        pagina = (await autenticato.get("/api/probes?days=7&cited=true&limit=50")).json()
        con_citazioni = [e for e in pagina["elementi"] if e["citazioni"]]
        assert con_citazioni
        elemento = con_citazioni[0]
        assert elemento["query_text"]
        assert elemento["query_strategy"] == "faq_verbatim"
        assert elemento["topic_slug"] == "concorso-docenti-2026"

    async def test_dettaglio_probe(self, autenticato, catalogo):
        primo = catalogo["probe"][0]
        dati = (await autenticato.get(f"/api/probes/{primo.id}")).json()
        assert dati["id"] == primo.id
        assert len(dati["citazioni"]) == 3
        assert "raw_response" in dati

    async def test_dettaglio_probe_inesistente(self, autenticato, catalogo):
        assert (await autenticato.get("/api/probes/999999")).status_code == 404

    async def test_runs(self, autenticato, catalogo):
        run = (await autenticato.get("/api/runs?limit=5")).json()
        assert run
        assert {"id", "status", "kind", "planned", "costo_eur"} <= set(run[0])

    async def test_costs(self, autenticato, catalogo):
        dati = (await autenticato.get("/api/costs")).json()
        assert Decimal(dati["giorno_eur"]) >= 0
        assert dati["budget_superato"] is False


class TestAzioni:
    async def test_run_now_risponde_subito_e_non_attende(self, autenticato, catalogo, monkeypatch):
        """Un ciclo dura minuti: la richiesta HTTP non lo aspetta."""
        import app.services.runner as runner_mod

        chiamato = {"si": False}

        async def finto(*args, **kwargs):
            chiamato["si"] = True

        monkeypatch.setattr(runner_mod, "esegui_ciclo", finto)

        risposta = await autenticato.post("/api/actions/run-now?quante=2")

        assert risposta.status_code == 202
        assert risposta.json()["avviato"] is True
        assert "/api/runs" in risposta.json()["messaggio"]
