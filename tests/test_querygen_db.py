"""Rotazione e orchestrazione del generatore, contro un database vero."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.models import Query, Topic
from app.services.querygen import genera_lotto, seleziona_topic
from app.services.querygen.normalize import calcola_hash
from app.services.querygen.validate import MotivoScarto, contiene_brand

ADESSO = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def _topic(n: int, *, eta: timedelta, **kwargs) -> Topic:
    base = {
        "source_id": n,
        "slug": f"articolo-{n}",
        "title": f"Titolo dell'articolo numero {n}, con una coda",
        "category_slug": "scuola",
        "keyword": f"argomento numero {n}",
        "tags": [],
        "faq_questions": [],
        "probe_count": 0,
        "active": True,
        "published_at": ADESSO - eta,
    }
    return Topic(**{**base, **kwargs})


@pytest.fixture
async def catalogo(session):
    """6 topic freschi, 4 recenti, 6 in archivio."""
    topics = [
        *[_topic(i, eta=timedelta(hours=6 * i)) for i in range(1, 7)],  # < 72h
        *[_topic(10 + i, eta=timedelta(days=5 * i)) for i in range(1, 5)],  # 5-20 giorni
        *[_topic(20 + i, eta=timedelta(days=40 + i)) for i in range(1, 7)],  # > 30 giorni
    ]
    session.add_all(topics)
    await session.commit()
    return topics


class TestSelezione:
    async def test_i_bucket_rispettano_le_finestre(self, session, catalogo):
        sel = await seleziona_topic(session, {"fresh": 3, "recent": 0, "archive": 0}, adesso=ADESSO)
        assert len(sel.topics) == 3
        assert all(t.published_at >= ADESSO - timedelta(hours=72) for t in sel.topics)

        sel = await seleziona_topic(session, {"fresh": 0, "recent": 0, "archive": 3}, adesso=ADESSO)
        assert all(t.published_at < ADESSO - timedelta(days=30) for t in sel.topics)

    async def test_chi_non_e_mai_stato_sondato_passa_davanti(self, session, catalogo):
        await session.execute(
            update(Topic).where(Topic.source_id.in_([21, 22])).values(last_probed_at=ADESSO)
        )
        await session.commit()

        sel = await seleziona_topic(session, {"archive": 4}, adesso=ADESSO)

        sondati = [t.source_id for t in sel.topics]
        assert 21 not in sondati and 22 not in sondati

    async def test_a_parita_si_prende_il_meno_recente(self, session, catalogo):
        await session.execute(
            update(Topic)
            .where(Topic.source_id == 23)
            .values(last_probed_at=ADESSO - timedelta(days=30))
        )
        await session.execute(
            update(Topic)
            .where(Topic.source_id.in_([24, 25, 26]))
            .values(last_probed_at=ADESSO - timedelta(hours=1))
        )
        await session.commit()

        sel = await seleziona_topic(session, {"archive": 1}, adesso=ADESSO)
        # 21 e 22 non sono mai stati sondati: passano prima. Escludendoli,
        # il piu' vecchio e' 23.
        sel2 = await seleziona_topic(
            session, {"archive": 1}, adesso=ADESSO, esclusi={t.id for t in catalogo[10:12]}
        )
        assert sel.topics[0].last_probed_at is None
        assert sel2.topics[0].source_id == 23

    async def test_un_bucket_vuoto_viene_ripianato_dagli_altri(self, session, catalogo):
        """Un fine settimana senza pubblicazioni non deve rimpicciolire il lotto."""
        await session.execute(
            update(Topic)
            .where(Topic.published_at >= ADESSO - timedelta(hours=72))
            .values(active=False)
        )
        await session.commit()

        sel = await seleziona_topic(session, {"fresh": 4, "recent": 2, "archive": 2}, adesso=ADESSO)

        assert len(sel.topics) == 8, "il lotto resta della dimensione richiesta"
        assert sel.scoperti == {"fresh": 4}

    async def test_gli_inattivi_non_vengono_mai_scelti(self, session, catalogo):
        await session.execute(update(Topic).values(active=False))
        await session.commit()

        sel = await seleziona_topic(session, {"fresh": 3, "recent": 3}, adesso=ADESSO)
        assert sel.topics == []

    async def test_nessun_topic_due_volte_nello_stesso_lotto(self, session, catalogo):
        sel = await seleziona_topic(session, {"fresh": 6, "recent": 4, "archive": 6}, adesso=ADESSO)
        ids = [t.id for t in sel.topics]
        assert len(ids) == len(set(ids))


class TestGenerazione:
    async def test_produce_esattamente_il_numero_richiesto(self, session, catalogo):
        esito = await genera_lotto(session, 9, adesso=ADESSO)
        assert len(esito.query) == 9

    async def test_nessuna_query_nomina_il_giornale(self, session, catalogo):
        esito = await genera_lotto(session, 12, adesso=ADESSO)
        assert esito.query
        for q in esito.query:
            assert not contiene_brand(q.text), q.text

    async def test_nessun_duplicato_nel_lotto(self, session, catalogo):
        esito = await genera_lotto(session, 12, adesso=ADESSO)
        hashes = [q.text_hash for q in esito.query]
        assert len(hashes) == len(set(hashes))

    async def test_tutte_le_query_sono_valide_e_salvate(self, session, catalogo):
        esito = await genera_lotto(session, 9, adesso=ADESSO)

        salvate = (await session.execute(select(func.count()).select_from(Query))).scalar_one()
        assert salvate == len(esito.query)
        for q in esito.query:
            assert 15 <= len(q.text) <= 300
            assert q.text_hash == calcola_hash(q.text)

    async def test_include_le_domande_di_categoria(self, session, catalogo):
        esito = await genera_lotto(session, 10, adesso=ADESSO)
        categoria = [q for q in esito.query if q.strategy == "category"]
        assert len(categoria) == 1
        assert categoria[0].topic_id is None
        assert categoria[0].category_slug

    async def test_la_seconda_chiamata_riusa_invece_di_duplicare(self, session, catalogo):
        primo = await genera_lotto(session, 9, adesso=ADESSO)
        secondo = await genera_lotto(session, 9, adesso=ADESSO)

        totale = (await session.execute(select(func.count()).select_from(Query))).scalar_one()
        assert secondo.riusate > 0, "le stesse domande devono essere riconosciute"
        assert totale < len(primo.query) + len(secondo.query)

    async def test_una_query_eseguita_di_recente_viene_scartata(self, session, catalogo):
        primo = await genera_lotto(session, 9, adesso=ADESSO)
        await session.execute(update(Query).values(last_run_at=ADESSO - timedelta(days=2)))
        await session.commit()

        secondo = await genera_lotto(session, 9, adesso=ADESSO)

        assert secondo.scartate.get(MotivoScarto.DUPLICATA, 0) > 0
        riusati = {q.id for q in secondo.query} & {q.id for q in primo.query}
        assert not riusati, "niente di eseguito negli ultimi 14 giorni va rimandato"

    async def test_una_query_vecchia_torna_disponibile(self, session, catalogo):
        await genera_lotto(session, 9, adesso=ADESSO)
        await session.execute(update(Query).values(last_run_at=ADESSO - timedelta(days=20)))
        await session.commit()

        secondo = await genera_lotto(session, 9, adesso=ADESSO)
        assert secondo.riusate > 0

    async def test_le_faq_non_si_ripetono_tra_lotti(self, session, session_factory=None):
        t = Topic(
            source_id=999,
            slug="con-faq",
            title="Articolo con molte FAQ, per la rotazione",
            category_slug="scuola",
            keyword="argomento con faq",
            tags=[],
            faq_questions=[
                "Chi può partecipare al concorso docenti 2026?",
                "Quali sono le scadenze per presentare la domanda?",
                "Quanto dura la procedura di selezione prevista?",
            ],
            probe_count=0,
            published_at=ADESSO - timedelta(hours=1),
        )
        session.add(t)
        await session.commit()

        indici = []
        for _ in range(3):
            esito = await genera_lotto(session, 1, adesso=ADESSO)
            for q in esito.query:
                if q.strategy == "faq_verbatim":
                    indici.append(q.source_faq_index)
            await session.execute(update(Query).values(last_run_at=ADESSO - timedelta(days=100)))
            await session.commit()

        assert len(set(indici)) == len(indici), "ogni FAQ deve essere usata una volta sola"

    async def test_catalogo_vuoto_non_solleva(self, session):
        esito = await genera_lotto(session, 9, adesso=ADESSO)
        # Le domande di categoria non dipendono dal catalogo: quelle arrivano.
        assert all(q.strategy == "category" for q in esito.query)

    async def test_conteggio_zero(self, session, catalogo):
        esito = await genera_lotto(session, 0, adesso=ADESSO)
        assert esito.query == []

    async def test_i_topic_senza_materiale_vengono_contati(self, session):
        session.add(
            Topic(
                source_id=500,
                slug="muto",
                title="Breve",
                category_slug="scuola",
                tags=[],
                faq_questions=[],
                probe_count=0,
                published_at=ADESSO - timedelta(hours=1),
            )
        )
        await session.commit()

        esito = await genera_lotto(session, 4, adesso=ADESSO)
        assert esito.scartate.get("topic_senza_materiale", 0) >= 1


class TestRiscrittura:
    async def test_una_riscrittura_valida_viene_adottata(self, session, catalogo):
        async def finto(testi: list[str]) -> list[str]:
            return [f"Mi spiegate come funziona {t.split(':')[0]}, per favore?" for t in testi]

        esito = await genera_lotto(session, 4, adesso=ADESSO, riscrittore=finto)

        riscritte = [q for q in esito.query if q.generator == "llm_rewrite"]
        assert riscritte
        assert all(q.text.startswith("Mi spiegate") for q in riscritte)

    async def test_una_riscrittura_che_reintroduce_il_brand_viene_respinta(self, session, catalogo):
        async def avvelenato(testi: list[str]) -> list[str]:
            return [f"Secondo Edunews24, {t}" for t in testi]

        esito = await genera_lotto(session, 4, adesso=ADESSO, riscrittore=avvelenato)

        assert all(not contiene_brand(q.text) for q in esito.query)
        assert all(q.generator == "template" for q in esito.query)

    async def test_un_riordino_viene_intercettato(self, session, catalogo):
        """Il conteggio corretto non basta: l'ordine puo' essere cambiato."""

        async def mescolato(testi: list[str]) -> list[str]:
            return list(reversed([f"Domanda naturale su {t}" for t in testi]))

        esito = await genera_lotto(session, 6, adesso=ADESSO, riscrittore=mescolato)

        # Nessuna query deve risultare accoppiata al topic sbagliato: chi non
        # condivide alcun termine con l'originale torna al template.
        for q in esito.query:
            if q.generator == "llm_rewrite" and q.topic_id is not None:
                topic = await session.get(Topic, q.topic_id)
                assert topic.keyword.split()[-1] in q.text

    async def test_numero_di_elementi_sbagliato_scarta_tutto_il_lotto(self, session, catalogo):
        async def tronco(testi: list[str]) -> list[str]:
            return [f"Domanda su {t}" for t in testi[:-1]]

        esito = await genera_lotto(session, 5, adesso=ADESSO, riscrittore=tronco)
        assert all(q.generator == "template" for q in esito.query)

    async def test_un_errore_del_modello_non_ferma_la_generazione(self, session, catalogo):
        async def esplode(testi: list[str]) -> list[str]:
            raise RuntimeError("502 Bad Gateway")

        esito = await genera_lotto(session, 5, adesso=ADESSO, riscrittore=esplode)
        assert len(esito.query) == 5
        assert all(q.generator == "template" for q in esito.query)

    async def test_riscrittura_disattivata(self, session, catalogo, monkeypatch):
        settings = get_settings().model_copy(update={"query_rewrite_enabled": False})

        chiamato = False

        async def non_deve_essere_chiamato(testi: list[str]) -> list[str]:
            nonlocal chiamato
            chiamato = True
            return testi

        esito = await genera_lotto(
            session, 4, settings=settings, adesso=ADESSO, riscrittore=non_deve_essere_chiamato
        )
        assert not chiamato
        assert esito.riscrittura == "disattivata"
        assert esito.query
