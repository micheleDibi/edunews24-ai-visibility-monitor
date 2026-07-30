"""Logica pura del generatore: normalizzazione, validazione, strategie, quote.

Nessun database. Sono i test che devono restare veloci, perche' sono quelli
che si rilanciano ogni volta che si tocca un template.
"""

from __future__ import annotations

import re

import pytest

from app.models import Topic
from app.services.querygen.categories import DOMANDE_PER_CATEGORIA, tutte_le_domande
from app.services.querygen.normalize import calcola_hash, normalizza, solo_alfanumerico
from app.services.querygen.rewrite import ISTRUZIONE, riscrivi_lotto
from app.services.querygen.selection import ripartisci
from app.services.querygen.strategies import (
    TEMPLATE_KEYWORD_INTENT,
    genera_per_topic,
    keyword_da_titolo,
)
from app.services.querygen.validate import (
    LUNGHEZZA_MAX,
    MotivoScarto,
    contiene_brand,
    sembra_italiano,
    valida_testo,
)


def topic(**kwargs) -> Topic:
    """Topic minimo per i test: i default dei server non si applicano in memoria."""
    base = {
        "id": 1,
        "source_id": 100,
        "slug": "uno-slug",
        "title": "Un titolo qualsiasi, con una coda",
        "category_slug": "scuola",
        "livello": None,
        "keyword": None,
        "angolo": None,
        "tags": [],
        "faq_questions": [],
        "probe_count": 0,
    }
    return Topic(**{**base, **kwargs})


class TestNormalizzazione:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("Perché non funziona?", "perche non funziona"),
            ("  Come   funziona?  ", "come funziona"),
            ("Concorso docenti, 2026!", "concorso docenti 2026"),
            ("È vero?", "e vero"),
        ],
    )
    def test_forma_normalizzata(self, a, b):
        assert normalizza(a) == b

    def test_domande_equivalenti_hanno_lo_stesso_hash(self):
        assert calcola_hash("Perché non funziona?") == calcola_hash("perche non funziona")
        assert calcola_hash("Come  funziona?") == calcola_hash("Come funziona!")

    def test_domande_diverse_hanno_hash_diversi(self):
        assert calcola_hash("Come funziona il TFA?") != calcola_hash("Come funziona il TFR?")

    def test_solo_alfanumerico_collassa_le_grafie(self):
        for variante in ("edunews24", "Edunews24", "edu news 24", "EDU-NEWS-24", "edunews24.it"):
            assert solo_alfanumerico(variante).startswith("edunews24")


class TestBrand:
    @pytest.mark.parametrize(
        "testo",
        [
            "Cosa scrive edunews24 sul concorso?",
            "Secondo Edunews24, quali sono le scadenze?",
            "Cosa dice edu news 24 sui concorsi?",
            "Cosa dice EDU NEWS 24 sui concorsi?",
            "Le notizie su edunews24.it parlano di GPS?",
            "Cosa riporta edu-news-24 sul sostegno?",
            "Cosa dice EduNews24 del bonus?",
        ],
    )
    def test_ogni_grafia_del_brand_viene_intercettata(self, testo):
        assert contiene_brand(testo) is True
        assert valida_testo(testo).motivo == MotivoScarto.BRAND

    @pytest.mark.parametrize(
        "testo",
        [
            "Come funziona il concorso docenti 2026?",
            "Quali sono le scadenze per le GPS?",
            "Cosa cambia per la carta del docente?",
            # "news" da solo non e' il brand: non deve essere un falso positivo
            "Dove trovo le news sui concorsi scuola?",
        ],
    )
    def test_nessun_falso_positivo(self, testo):
        assert contiene_brand(testo) is False

    def test_il_dominio_e_configurabile(self):
        assert contiene_brand("Cosa dice altrotesta.it?", own_domain="altrotesta.it") is True


class TestLingua:
    @pytest.mark.parametrize(
        "testo",
        [
            "Come funziona il concorso docenti 2026?",
            "concorso docenti 2026 requisiti",  # frase secca, senza parole funzionali
            "Quanto vale la carta del docente?",
            "GPS 2026 scadenze domanda",
        ],
    )
    def test_accetta_italiano_anche_secco(self, testo):
        assert sembra_italiano(testo) is True

    @pytest.mark.parametrize(
        "testo",
        [
            "What are the requirements for the teaching competition?",
            "How does the Italian school system work?",
            "Как работает итальянская школа?",
            "イタリアの学校はどう機能しますか",
        ],
    )
    def test_rifiuta_altre_lingue(self, testo):
        assert sembra_italiano(testo) is False


class TestValidazione:
    def test_lunghezza_minima(self):
        assert valida_testo("Troppo corta?").motivo == MotivoScarto.TROPPO_CORTA

    def test_lunghezza_massima(self):
        assert valida_testo("Come funziona " + "x" * LUNGHEZZA_MAX).motivo == (
            MotivoScarto.TROPPO_LUNGA
        )

    def test_vuota(self):
        assert valida_testo("   ").motivo == MotivoScarto.VUOTA

    def test_query_buona(self):
        assert valida_testo("Come funziona il concorso docenti 2026?").valida is True


class TestRipartizione:
    def test_il_caso_reale_nove_query(self):
        """9 query/ora e' il caso reale: 200 al giorno divise per 24 ore."""
        quote = ripartisci(9, {"fresh": 50, "recent": 20, "archive": 20, "category": 10})
        assert sum(quote.values()) == 9
        assert quote["fresh"] == 4

    @pytest.mark.parametrize("totale", range(0, 60))
    def test_somma_sempre_esatta(self, totale):
        quote = ripartisci(totale, {"fresh": 50, "recent": 20, "archive": 20, "category": 10})
        assert sum(quote.values()) == totale

    def test_nessuna_quota_negativa(self):
        for totale in range(0, 30):
            quote = ripartisci(totale, {"a": 50, "b": 20, "c": 20, "d": 10})
            assert all(v >= 0 for v in quote.values())

    def test_il_peso_maggiore_prende_la_quota_maggiore(self):
        quote = ripartisci(10, {"fresh": 50, "recent": 20, "archive": 20, "category": 10})
        assert quote == {"fresh": 5, "recent": 2, "archive": 2, "category": 1}

    def test_deterministica(self):
        pesi = {"fresh": 50, "recent": 20, "archive": 20, "category": 10}
        assert [ripartisci(7, pesi) for _ in range(5)] == [ripartisci(7, pesi)] * 5

    def test_totale_zero_o_pesi_vuoti(self):
        assert ripartisci(0, {"a": 1}) == {"a": 0}
        assert ripartisci(5, {"a": 0, "b": 0}) == {"a": 0, "b": 0}


class TestStrategie:
    def test_le_faq_vengono_prima_di_tutto(self):
        t = topic(
            faq_questions=["Chi può partecipare al concorso docenti 2026?"],
            keyword="concorso docenti 2026",
            angolo="I posti salgono a 30.000",
        )
        c = genera_per_topic(t)
        assert c.strategy == "faq_verbatim"
        assert c.text == "Chi può partecipare al concorso docenti 2026?"
        assert c.source_faq_index == 0

    def test_una_faq_gia_usata_non_si_ripete(self):
        t = topic(
            faq_questions=[
                "Chi può partecipare al concorso docenti 2026?",
                "Quali sono le scadenze per presentare la domanda?",
            ]
        )
        c = genera_per_topic(t, faq_usate={0})
        assert c.source_faq_index == 1
        assert c.text == "Quali sono le scadenze per presentare la domanda?"

    def test_esaurite_le_faq_si_passa_alla_strategia_successiva(self):
        t = topic(faq_questions=["Chi può partecipare?"], keyword="concorso docenti 2026")
        c = genera_per_topic(t, faq_usate={0})
        assert c.strategy == "keyword_intent"

    @pytest.mark.parametrize(
        ("angolo", "attesa"),
        [
            # L'angolo e' la RISPOSTA: la query deve essere la domanda.
            (
                "I posti a bando salgono a 30.000",
                "Concorso docenti 2026: quanti posti sono previsti?",
            ),
            (
                "La domanda si presenta dal 1 marzo sul portale INPS",
                "Concorso docenti 2026: quando si presenta la domanda?",
            ),
            (
                "Gli importi salgono a 201 euro per la prima fascia",
                "Concorso docenti 2026: a quanto ammonta?",
            ),
            (
                "Le iscrizioni si chiudono entro il termine previsto",
                "Concorso docenti 2026: quali sono le scadenze?",
            ),
            (
                "Servono nuovi requisiti di accesso",
                "Concorso docenti 2026: chi può partecipare?",
            ),
        ],
    )
    def test_angolo_chiede_il_dato_invece_di_affermarlo(self, angolo, attesa):
        c = genera_per_topic(topic(keyword="concorso docenti 2026", angolo=angolo))
        assert c.strategy == "angolo"
        assert c.text == attesa

    def test_angolo_indeducibile_ripiega_sulla_strategia_successiva(self):
        c = genera_per_topic(
            topic(keyword="concorso docenti 2026", angolo="Un commento senza dati verificabili")
        )
        assert c.strategy == "keyword_intent"

    def test_evergreen_usa_le_domande_procedurali(self):
        c = genera_per_topic(topic(keyword="carta del docente", livello="evergreen"))
        assert c.strategy == "evergreen_howto"
        assert c.text.startswith("Carta del docente:")

    def test_keyword_intent(self):
        c = genera_per_topic(topic(keyword="concorso docenti 2026", livello="flash"))
        assert c.strategy == "keyword_intent"
        assert c.text.startswith("Concorso docenti 2026:")

    def test_tag_combo_batte_il_ripiego_sul_titolo(self):
        """Il titolo e' l'ultimo ripiego: se coprisse tag_combo, quella strategia
        sarebbe morta su ogni articolo con un titolo utilizzabile."""
        c = genera_per_topic(
            topic(title="Un titolo del tutto utilizzabile come keyword", tags=["GPS", "sostegno"])
        )
        assert c.strategy == "tag_combo"

    def test_tag_combo_preferisce_i_tag_piu_specifici(self):
        """Accostare un tag specifico a uno generico produce una domanda vaga."""
        c = genera_per_topic(
            topic(title="Breve", tags=["dottorato di ricerca", "bandi", "borse di studio"])
        )
        assert c.strategy == "tag_combo"
        testo = c.text.casefold()
        assert "dottorato di ricerca" in testo
        assert "borse di studio" in testo
        assert "bandi" not in testo

    def test_tag_combo_mantiene_lordine_originale(self):
        c = genera_per_topic(topic(title="Breve", tags=["carta del docente", "formazione docenti"]))
        testo = c.text.casefold()
        assert testo.index("carta del docente") < testo.index("formazione docenti")

    def test_ripiego_sul_titolo_per_larchivio_senza_campi_skill(self):
        c = genera_per_topic(topic(title="Graduatorie GPS 2026, cosa cambia per il sostegno"))
        assert c.strategy == "keyword_intent"
        assert c.text.startswith("Graduatorie GPS 2026:")

    def test_topic_senza_materiale_non_produce_query(self):
        assert genera_per_topic(topic(title="Breve")) is None

    def test_la_maiuscola_iniziale_non_rovina_le_sigle(self):
        assert genera_per_topic(topic(keyword="ISEE universitario")).text.startswith("ISEE ")
        assert genera_per_topic(topic(keyword="carta del docente")).text.startswith("Carta ")

    def test_il_template_ruota_con_i_probe(self):
        """Uno stesso articolo sondato piu' volte non riceve sempre la stessa domanda."""
        testi = {
            genera_per_topic(topic(keyword="carta del docente", probe_count=n)).text
            for n in range(len(TEMPLATE_KEYWORD_INTENT))
        }
        assert len(testi) == len(TEMPLATE_KEYWORD_INTENT)

    def test_deterministica_a_parita_di_stato(self):
        t = topic(keyword="concorso docenti 2026", probe_count=3)
        assert genera_per_topic(t).text == genera_per_topic(t).text

    def test_ogni_template_supera_la_validazione(self):
        """Un template che genera una query non valida e' un template morto."""
        for n in range(len(TEMPLATE_KEYWORD_INTENT)):
            t = topic(keyword="concorso docenti 2026", probe_count=n)
            assert valida_testo(genera_per_topic(t).text).valida


class TestGuardieRiscrittura:
    """La riscrittura non deve poter accoppiare una query al topic sbagliato."""

    async def test_riscrittura_buona_adottata(self):
        originali = ["concorso docenti 2026: quali sono le scadenze?"]

        async def finto(testi):
            return ["Quali sono le scadenze del concorso docenti 2026?"]

        assert await riscrivi_lotto(originali, finto) == [
            "Quali sono le scadenze del concorso docenti 2026?"
        ]

    async def test_numero_diverso_di_elementi_scarta_il_lotto(self):
        originali = ["concorso docenti 2026: quali sono le scadenze?", "GPS 2026: come funziona?"]

        async def tronco(testi):
            return ["Una sola risposta ma erano due domande, quindi si scarta"]

        assert await riscrivi_lotto(originali, tronco) == originali

    async def test_il_brand_reintrodotto_fa_tornare_al_template(self):
        originali = ["concorso docenti 2026: quali sono le scadenze?"]

        async def avvelenato(testi):
            return ["Cosa scrive Edunews24 sulle scadenze del concorso docenti 2026?"]

        assert await riscrivi_lotto(originali, avvelenato) == originali

    async def test_cambio_di_lingua_fa_tornare_al_template(self):
        originali = ["concorso docenti 2026: quali sono le scadenze?"]

        async def inglese(testi):
            return ["What are the deadlines for the 2026 teaching competition?"]

        assert await riscrivi_lotto(originali, inglese) == originali

    async def test_un_riordino_viene_intercettato(self):
        originali = [
            "concorso docenti 2026: quali sono le scadenze?",
            "carta del docente: quanto vale?",
        ]

        async def scambiate(testi):
            return [
                "Quanto vale la carta del docente?",
                "Quali sono le scadenze del concorso docenti 2026?",
            ]

        assert await riscrivi_lotto(originali, scambiate) == originali

    async def test_riordino_distinguibile_solo_dal_numero(self):
        """I numeri sono spesso l'unica cosa che distingue due articoli."""
        originali = ["bonus nido: quanto vale nel 2025?", "bonus nido: quanto vale nel 2026?"]

        async def scambiate(testi):
            return [
                "Quanto vale il bonus nido nel 2026?",
                "Quanto vale il bonus nido nel 2025?",
            ]

        assert await riscrivi_lotto(originali, scambiate) == originali

    async def test_un_errore_non_solleva(self):
        originali = ["concorso docenti 2026: quali sono le scadenze?"]

        async def esplode(testi):
            raise RuntimeError("timeout")

        assert await riscrivi_lotto(originali, esplode) == originali

    async def test_risposta_non_lista(self):
        originali = ["concorso docenti 2026: quali sono le scadenze?"]

        async def sbagliata(testi):
            return "non e' una lista"  # type: ignore[return-value]

        assert await riscrivi_lotto(originali, sbagliata) == originali

    async def test_elemento_non_stringa_ripiega_solo_su_quello(self):
        originali = ["concorso docenti 2026: le scadenze?", "carta del docente: quanto vale?"]

        async def mista(testi):
            return [None, "Quanto vale la carta del docente?"]  # type: ignore[list-item]

        assert await riscrivi_lotto(originali, mista) == [
            originali[0],
            "Quanto vale la carta del docente?",
        ]

    async def test_lotto_vuoto(self):
        async def mai_chiamato(testi):
            raise AssertionError("non deve essere chiamato")

        assert await riscrivi_lotto([], mai_chiamato) == []


class TestIstruzioneDiRiscrittura:
    """Il prompt passa da `.format()`: le graffe letterali devono restare tali.

    Regressione da produzione. Con le graffe singole, `{"domande": [...]}` era
    letto come campo da sostituire e `.format(n=...)` sollevava
    `KeyError: '"domande"'` PRIMA della chiamata HTTP. L'eccezione veniva
    catturata dal ripiego, che riportava i template: nessun errore visibile,
    nessuna riga rossa, solo la funzione morta e un log a livello warning fra
    migliaia. Il primo ciclo reale in produzione ha riscritto zero query su
    undici senza che nulla lo dichiarasse.
    """

    def test_il_prompt_si_formatta_senza_esplodere(self):
        reso = ISTRUZIONE.format(n=7)
        assert "7 stringhe" in reso

    def test_il_json_di_esempio_sopravvive_alla_formattazione(self):
        # Se questo salta, il modello riceve un esempio di formato malformato e
        # il `response_format` json_object non basta a salvarlo.
        assert '{"domande": [...]}' in ISTRUZIONE.format(n=3)


class TestDomandeDiCategoria:
    """La lista curata a mano è l'unica parte del generatore senza rete di
    sicurezza: nessun template la produce, nessun modello la rivede."""

    def test_ogni_domanda_supera_la_validazione(self):
        for slug, domanda in tutte_le_domande():
            esito = valida_testo(domanda)
            assert esito.valida, f"{slug}: {domanda} — {esito.motivo}"

    def test_gli_slug_hanno_la_forma_di_uno_slug(self):
        # Uno slug con una maiuscola o uno spazio non corrisponde a nulla in
        # `topics` e la sua categoria sparisce dalla griglia senza un errore.
        for slug in DOMANDE_PER_CATEGORIA:
            assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug), slug

    def test_nessuna_domanda_ripetuta(self):
        domande = [d for _, d in tutte_le_domande()]
        assert len(domande) == len(set(domande))


class TestKeywordDaTitolo:
    @pytest.mark.parametrize(
        ("titolo", "atteso"),
        [
            ("Concorso docenti 2026, i posti salgono", "Concorso docenti 2026"),
            ("Carta del docente: come funziona", "Carta del docente"),
            ("Graduatorie GPS - le novità", "Graduatorie GPS"),
            ("Maturità 2026 — cosa cambia", "Maturità 2026"),
            (
                "Un titolo senza separatori che resta intero",
                "Un titolo senza separatori che resta intero",
            ),
        ],
    )
    def test_taglia_al_primo_separatore(self, titolo, atteso):
        assert keyword_da_titolo(titolo) == atteso

    @pytest.mark.parametrize("titolo", ["Breve", "", "x" * 200])
    def test_scarta_i_titoli_inutilizzabili(self, titolo):
        assert keyword_da_titolo(titolo) is None
