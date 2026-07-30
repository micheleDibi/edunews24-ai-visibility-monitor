"""Sincronizzazione dei topic, contro un finto DB editoriale.

Ogni test gira due volte: una con `tags`/`faqs` come colonne di testo che
contengono JSON serializzato, una con `text[]`/`jsonb` nativi. Quale delle due
sia la forma reale non e' documentato da nessuna parte, quindi il sync deve
funzionare in entrambe.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, text

from app.services.topics_sync import sync_topics
from tests.conftest import ORA, Topic


async def _topics(session) -> dict[int, Topic]:
    session.expire_all()
    righe = (await session.execute(select(Topic))).scalars().all()
    return {t.source_id: t for t in righe}


class TestSyncIniziale:
    async def test_esclude_bozze_e_non_pubblicati(self, session, source_table):
        stats = await sync_topics(session)

        topics = await _topics(session)
        assert set(topics) == {1, 4, 5, 7}, "bozza, non pubblicato e slug vuoto vanno esclusi"
        assert stats.inserted == 4
        assert stats.updated == 0

    async def test_slug_vuoto_viene_scartato_con_motivo(self, session, source_table):
        stats = await sync_topics(session)

        assert stats.skipped == 1
        assert stats.motivi_scarto == {"titolo_o_slug_vuoto": 1}

    async def test_tags_e_faq_parsati(self, session, source_table):
        await sync_topics(session)
        topics = await _topics(session)

        assert topics[1].tags == ["concorso docenti", "scuola", "GPS"]
        assert topics[1].faq_questions == [
            "Chi puo' partecipare al concorso docenti 2026?",
            "Quali sono le scadenze per la domanda?",
        ]

    async def test_campi_assenti_o_malformati_non_fanno_fallire_il_sync(
        self, session, source_table
    ):
        await sync_topics(session)
        topics = await _topics(session)

        # id=4 ha tags e faqs a NULL, id=5 li ha malformati (nella variante
        # testuale). In entrambi i casi il topic esiste con array vuoti.
        assert topics[4].tags == []
        assert topics[4].faq_questions == []
        assert topics[5].tags == []
        assert topics[5].faq_questions == []

    async def test_livello_sconosciuto_normalizzato_a_null(self, session, source_table):
        await sync_topics(session)
        topics = await _topics(session)

        assert topics[7].livello is None, "un livello fuori dall'enum non deve essere propagato"
        assert topics[1].livello == "flash"
        assert topics[4].livello == "evergreen"

    async def test_campi_skill_e_metadati(self, session, source_table):
        await sync_topics(session)
        topics = await _topics(session)

        t = topics[1]
        assert t.slug == "concorso-docenti-2026-cosa-cambia"
        assert t.category_slug == "scuola"
        assert t.keyword == "concorso docenti 2026"
        assert t.angolo == "I posti disponibili salgono a 30.000"
        assert t.active is True
        assert t.probe_count == 0
        assert t.last_probed_at is None
        # Watermark = GREATEST(updated_at, published_at) = updated_at.
        assert t.source_updated_at is not None
        assert abs((t.source_updated_at - (ORA - timedelta(hours=2))).total_seconds()) < 2


class TestSyncIncrementale:
    async def test_seconda_esecuzione_non_rilegge_nulla(self, session, source_table):
        await sync_topics(session)
        stats = await sync_topics(session)

        assert stats.fetched == 0
        assert stats.inserted == 0
        assert stats.updated == 0

    async def test_un_articolo_modificato_viene_riletto(self, session, source_table, engine):
        await sync_topics(session)

        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE articles SET updated_at = :ora, title = :t WHERE id = 1"),
                {"ora": ORA, "t": "Concorso docenti 2026, il titolo aggiornato"},
            )

        stats = await sync_topics(session)

        assert stats.fetched == 1
        assert stats.updated == 1
        assert stats.inserted == 0
        topics = await _topics(session)
        assert topics[1].title == "Concorso docenti 2026, il titolo aggiornato"

    async def test_lo_stato_di_rotazione_sopravvive_a_un_aggiornamento(
        self, session, source_table, engine
    ):
        """`last_probed_at` e `probe_count` sono nostri, non della sorgente."""
        await sync_topics(session)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE topics SET probe_count = 7, last_probed_at = :ora WHERE source_id = 1"
                ),
                {"ora": ORA},
            )
            await conn.execute(
                text("UPDATE articles SET updated_at = :ora WHERE id = 1"), {"ora": ORA}
            )

        await sync_topics(session)

        topics = await _topics(session)
        assert topics[1].probe_count == 7
        assert topics[1].last_probed_at is not None


class TestSyncCompleto:
    async def test_un_articolo_tornato_bozza_viene_disattivato_non_cancellato(
        self, session, source_table, engine
    ):
        await sync_topics(session)

        async with engine.begin() as conn:
            await conn.execute(text("UPDATE articles SET isdraft = true WHERE id = 1"))

        stats = await sync_topics(session, full=True)

        topics = await _topics(session)
        assert 1 in topics, "il topic non va cancellato: i probe storici devono restare leggibili"
        assert topics[1].active is False
        assert stats.deactivated == 1
        assert all(topics[i].active for i in (4, 5, 7))

    async def test_un_articolo_ripubblicato_torna_attivo(self, session, source_table, engine):
        await sync_topics(session)
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE articles SET isdraft = true WHERE id = 1"))
        await sync_topics(session, full=True)

        async with engine.begin() as conn:
            await conn.execute(text("UPDATE articles SET isdraft = false WHERE id = 1"))
        await sync_topics(session, full=True)

        topics = await _topics(session)
        assert topics[1].active is True

    async def test_il_completo_rilegge_tutto(self, session, source_table):
        await sync_topics(session)
        stats = await sync_topics(session, full=True)

        assert stats.fetched == 5  # 4 utilizzabili + 1 con slug vuoto
        assert stats.updated == 4
        assert stats.inserted == 0
