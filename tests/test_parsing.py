"""Il parser dei campi semi-strutturati non deve mai sollevare.

Ogni forma in cui `tags` e `faqs` possono arrivare — lista nativa, stringa
JSON, literal di array Postgres, NULL, spazzatura — deve produrre una lista.
Un articolo con i tag illeggibili e' una strategia di generazione in meno; una
eccezione qui e' il monitoraggio fermo.
"""

from __future__ import annotations

import pytest

from app.core.parsing import parse_faq_questions, parse_json_array, parse_tags


class TestParseJsonArray:
    @pytest.mark.parametrize(
        "valore",
        [None, "", "   ", "null", "[]", "{}", "non-json{{[", 42, 3.14, True, object()],
    )
    def test_valori_non_utilizzabili_danno_lista_vuota(self, valore):
        assert parse_json_array(valore) == []

    def test_lista_nativa_passa_invariata(self):
        assert parse_json_array(["a", "b"]) == ["a", "b"]

    def test_stringa_json(self):
        assert parse_json_array('["a", "b"]') == ["a", "b"]

    def test_oggetto_singolo_diventa_lista_di_uno(self):
        assert parse_json_array({"question": "q"}) == [{"question": "q"}]
        assert parse_json_array('{"question": "q"}') == [{"question": "q"}]

    def test_scalare_json_non_e_un_array(self):
        assert parse_json_array('"solo una stringa"') == []
        assert parse_json_array("123") == []

    @pytest.mark.parametrize(
        ("literal", "atteso"),
        [
            ("{alpha,beta}", ["alpha", "beta"]),
            ('{"con, virgola",beta}', ["con, virgola", "beta"]),
            ("{}", []),
            ("{NULL,beta}", ["beta"]),
        ],
    )
    def test_literal_array_postgres(self, literal, atteso):
        assert parse_json_array(literal) == atteso


class TestParseTags:
    def test_ripulisce_deduplica_e_mantiene_ordine(self):
        grezzi = ["  Scuola  ", "scuola", "GPS", "", "   ", "Scuola"]
        assert parse_tags(grezzi) == ["Scuola", "GPS"]

    def test_scarta_elementi_non_stringa(self):
        assert parse_tags(["ok", 42, None, {"a": 1}]) == ["ok"]

    def test_scarta_tag_assurdamente_lunghi(self):
        assert parse_tags(["x" * 81, "buono"]) == ["buono"]

    def test_rispetta_il_tetto(self):
        assert len(parse_tags([f"tag{i}" for i in range(100)], max_tags=5)) == 5

    def test_json_serializzato(self):
        assert parse_tags('["concorso docenti", "GPS"]') == ["concorso docenti", "GPS"]

    def test_malformato_non_solleva(self):
        assert parse_tags("{{rotto") == []
        assert parse_tags(None) == []


class TestParseFaqQuestions:
    def test_estrae_solo_le_domande(self):
        faqs = [
            {"question": "Chi puo' partecipare al concorso?", "answer": "Tutti."},
            {"question": "Quali sono le scadenze previste?", "answer": "Il 30 settembre."},
        ]
        assert parse_faq_questions(faqs) == [
            "Chi puo' partecipare al concorso?",
            "Quali sono le scadenze previste?",
        ]

    def test_accetta_json_serializzato(self):
        assert parse_faq_questions('[{"question": "Come si presenta la domanda?"}]') == [
            "Come si presenta la domanda?"
        ]

    def test_accetta_lista_di_stringhe(self):
        assert parse_faq_questions(["Come funziona la carta del docente?"]) == [
            "Come funziona la carta del docente?"
        ]

    def test_accetta_la_chiave_italiana(self):
        assert parse_faq_questions([{"domanda": "Quanto vale il bonus nido?"}]) == [
            "Quanto vale il bonus nido?"
        ]

    @pytest.mark.parametrize("valore", [None, "null", "", "{{rotto", [{"answer": "solo risposta"}]])
    def test_assenti_o_malformate_danno_lista_vuota(self, valore):
        assert parse_faq_questions(valore) == []

    def test_scarta_domande_troppo_corte_o_troppo_lunghe(self):
        faqs = [{"question": "Eh?"}, {"question": "x" * 301}, {"question": "Come funziona il TFA?"}]
        assert parse_faq_questions(faqs) == ["Come funziona il TFA?"]

    def test_normalizza_gli_spazi(self):
        assert parse_faq_questions([{"question": "  Come\n\tfunziona   il  TFA?  "}]) == [
            "Come funziona il TFA?"
        ]
