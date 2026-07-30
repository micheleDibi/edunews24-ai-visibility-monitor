"""Parser delle citazioni: e' qui che una misura diventa giusta o sbagliata.

Un errore in questo file non produce un'eccezione, produce un numero in
dashboard che sembra plausibile e non lo e'.
"""

from __future__ import annotations

import pytest

from app.clients.base import CitazioneGrezza
from app.models.citation import DOMINIO_NON_RISOLTO
from app.services.citations import (
    analizza,
    contiene_mention_brand,
    e_dominio_proprio,
    e_target_hit,
    estrai_slug,
    normalizza_host,
    pulisci_url,
)

PROPRIO = "edunews24.it"


class TestNormalizzaHost:
    @pytest.mark.parametrize(
        ("url", "atteso"),
        [
            ("https://edunews24.it/scuola/articolo", "edunews24.it"),
            ("https://www.edunews24.it/scuola/articolo", "edunews24.it"),
            ("HTTPS://WWW.EDUNEWS24.IT/Scuola", "edunews24.it"),
            ("https://orizzontescuola.it/qualcosa", "orizzontescuola.it"),
            ("http://sub.edunews24.it/x", "sub.edunews24.it"),
        ],
    )
    def test_host_normalizzato(self, url, atteso):
        assert normalizza_host(url) == atteso

    @pytest.mark.parametrize("url", [None, "", "   ", "non-un-url", "mailto:a@b.it"])
    def test_url_inutilizzabili_danno_la_sentinella(self, url):
        assert normalizza_host(url) == DOMINIO_NON_RISOLTO

    def test_wrapper_di_redirect_non_viene_indovinato(self):
        """Meglio dichiarare 'non risolto' che inventare un dominio plausibile."""
        wrapper = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbC123xyz"
        assert normalizza_host(wrapper) == DOMINIO_NON_RISOLTO

    def test_google_url_redirect(self):
        assert normalizza_host("https://www.google.com/url?q=https://x.it") == DOMINIO_NON_RISOLTO
        # Ma una pagina google normale resta un dominio legittimo.
        assert normalizza_host("https://www.google.com/search") == "google.com"


class TestPulisciUrl:
    def test_toglie_i_parametri_di_tracciamento(self):
        assert (
            pulisci_url("https://edunews24.it/scuola/x?utm_source=openai&utm_medium=ai")
            == "https://edunews24.it/scuola/x"
        )

    def test_tiene_i_parametri_utili(self):
        assert (
            pulisci_url("https://edunews24.it/cerca?q=concorso&utm_source=openai")
            == "https://edunews24.it/cerca?q=concorso"
        )

    def test_toglie_il_frammento(self):
        assert pulisci_url("https://edunews24.it/x#sezione") == "https://edunews24.it/x"

    def test_none(self):
        assert pulisci_url(None) is None


class TestDominioProprio:
    @pytest.mark.parametrize(
        "host", ["edunews24.it", "www.edunews24.it", "amp.edunews24.it", "sub.edunews24.it"]
    )
    def test_riconosce_il_dominio_e_i_sottodomini(self, host):
        assert e_dominio_proprio(normalizza_host(f"https://{host}/x"), PROPRIO) is True

    @pytest.mark.parametrize(
        "host",
        [
            "orizzontescuola.it",
            "edunews24.it.evil.com",  # non e' nostro
            "notedunews24.it",  # non e' un sottodominio
            "tecnicadellascuola.it",
        ],
    )
    def test_nessun_falso_positivo(self, host):
        assert e_dominio_proprio(host, PROPRIO) is False

    def test_il_dominio_nel_path_non_conta(self):
        """Un aggregatore che mette il nostro dominio nell'URL non e' una citazione."""
        url = "https://aggregatore.com/redirect?to=edunews24.it/scuola/x"
        assert e_dominio_proprio(normalizza_host(url), PROPRIO) is False


class TestEstraiSlug:
    @pytest.mark.parametrize(
        ("url", "atteso"),
        [
            ("https://edunews24.it/scuola/concorso-docenti-2026", "concorso-docenti-2026"),
            ("https://edunews24.it/scuola/concorso-docenti-2026/", "concorso-docenti-2026"),
            ("https://edunews24.it/scuola/articolo.html", "articolo"),
            ("https://edunews24.it/", None),
            ("https://edunews24.it", None),
        ],
    )
    def test_ultimo_segmento_del_path(self, url, atteso):
        assert estrai_slug(url) == atteso


class TestMentionBrand:
    @pytest.mark.parametrize(
        "testo",
        [
            "Secondo Edunews24 il concorso slitta.",
            "Come riporta edunews24.it, i posti salgono.",
            "Fonte: EDU NEWS 24",
            "Lo scrive edu-news-24.",
        ],
    )
    def test_riconosce_ogni_grafia(self, testo):
        assert contiene_mention_brand(testo) is True

    @pytest.mark.parametrize("testo", [None, "", "Secondo Orizzonte Scuola il concorso slitta."])
    def test_nessun_falso_positivo(self, testo):
        assert contiene_mention_brand(testo) is False


class TestLivelloStrutturato:
    def test_citazione_propria_riconosciuta(self):
        esito = analizza(
            answer_text="Il concorso slitta.",
            citazioni_strutturate=[
                CitazioneGrezza(url="https://www.miur.gov.it/x", title="MIM", position=1),
                CitazioneGrezza(
                    url="https://edunews24.it/scuola/concorso-docenti-2026",
                    title="Concorso",
                    position=2,
                ),
            ],
            own_domain=PROPRIO,
        )

        assert esito.edunews_cited is True
        assert esito.edunews_retrieved is True
        assert esito.edunews_mention is False, "citata: non e' una mention nuda"
        assert esito.livello == "strutturato"
        assert [c.domain for c in esito.citazioni] == ["miur.gov.it", "edunews24.it"]
        assert esito.slug_propri == {"concorso-docenti-2026"}

    def test_registra_tutti_i_domini_non_solo_i_propri(self):
        """Senza gli altri domini non si sa chi occupa il posto quando manchiamo."""
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[
                CitazioneGrezza(url="https://orizzontescuola.it/a"),
                CitazioneGrezza(url="https://tecnicadellascuola.it/b"),
            ],
            own_domain=PROPRIO,
        )
        assert len(esito.citazioni) == 2
        assert esito.edunews_cited is False
        assert all(not c.is_own for c in esito.citazioni)

    def test_recuperato_ma_non_citato_e_un_segnale_diverso(self):
        esito = analizza(
            answer_text="Il concorso slitta.",
            citazioni_strutturate=[
                CitazioneGrezza(url="https://edunews24.it/scuola/x", kind="source", position=1),
                CitazioneGrezza(url="https://miur.gov.it/y", kind="citation", position=1),
            ],
            own_domain=PROPRIO,
        )
        assert esito.edunews_retrieved is True
        assert esito.edunews_cited is False, "recuperato non vuol dire citato"

    def test_deduplica_la_stessa_fonte(self):
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[
                CitazioneGrezza(url="https://edunews24.it/scuola/x?utm_source=openai"),
                CitazioneGrezza(url="https://edunews24.it/scuola/x"),
                CitazioneGrezza(url="https://edunews24.it/scuola/x/"),
            ],
            own_domain=PROPRIO,
        )
        assert len(esito.citazioni) == 1

    def test_la_stessa_url_come_fonte_e_come_citazione_resta_distinta(self):
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[
                CitazioneGrezza(url="https://edunews24.it/x", kind="source"),
                CitazioneGrezza(url="https://edunews24.it/x", kind="citation"),
            ],
            own_domain=PROPRIO,
        )
        assert len(esito.citazioni) == 2
        assert {c.kind for c in esito.citazioni} == {"source", "citation"}

    def test_url_wrapper_salvato_ma_marcato_non_risolto(self):
        wrapper = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz"
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[CitazioneGrezza(url=wrapper, title="edunews24.it")],
            own_domain=PROPRIO,
        )
        assert esito.citazioni[0].domain == DOMINIO_NON_RISOLTO
        assert esito.citazioni[0].url == wrapper, "l'URL si conserva comunque"
        assert esito.edunews_cited is False, "il titolo non e' una prova di dominio"


class TestLivelloTesto:
    def test_ripiego_su_link_markdown(self):
        esito = analizza(
            answer_text="Vedi [l'articolo](https://edunews24.it/scuola/concorso) per i dettagli.",
            citazioni_strutturate=[],
            own_domain=PROPRIO,
        )
        assert esito.livello == "testo"
        assert esito.edunews_cited is True
        assert esito.citazioni[0].domain == "edunews24.it"

    def test_ripiego_su_url_nudi(self):
        esito = analizza(
            answer_text="Fonte: https://edunews24.it/scuola/concorso-2026, aggiornata ieri.",
            citazioni_strutturate=[],
            own_domain=PROPRIO,
        )
        assert esito.edunews_cited is True
        assert esito.citazioni[0].url == "https://edunews24.it/scuola/concorso-2026"

    def test_non_si_applica_se_il_livello_1_ha_prodotto(self):
        """Applicarlo sempre conterebbe due volte chi cita sia strutturato sia inline."""
        esito = analizza(
            answer_text="Vedi [qui](https://orizzontescuola.it/a) e [qui](https://x.it/b).",
            citazioni_strutturate=[CitazioneGrezza(url="https://miur.gov.it/z")],
            own_domain=PROPRIO,
        )
        assert esito.livello == "strutturato"
        assert len(esito.citazioni) == 1


class TestLivelloMention:
    def test_brand_senza_link(self):
        esito = analizza(
            answer_text="Secondo Edunews24 il concorso slitta a settembre.",
            citazioni_strutturate=[CitazioneGrezza(url="https://miur.gov.it/x")],
            own_domain=PROPRIO,
        )
        assert esito.edunews_mention is True
        assert esito.edunews_cited is False

    def test_brand_con_link_non_e_una_mention(self):
        esito = analizza(
            answer_text="Secondo Edunews24 il concorso slitta.",
            citazioni_strutturate=[CitazioneGrezza(url="https://edunews24.it/scuola/x")],
            own_domain=PROPRIO,
        )
        assert esito.edunews_cited is True
        assert esito.edunews_mention is False

    def test_nessun_segnale(self):
        esito = analizza(
            answer_text="Il concorso slitta a settembre.",
            citazioni_strutturate=[CitazioneGrezza(url="https://miur.gov.it/x")],
            own_domain=PROPRIO,
        )
        assert esito.edunews_cited is False
        assert esito.edunews_mention is False
        assert esito.edunews_retrieved is False


class TestTargetHit:
    def test_articolo_giusto(self):
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[
                CitazioneGrezza(url="https://edunews24.it/scuola/concorso-docenti-2026")
            ],
            own_domain=PROPRIO,
        )
        assert e_target_hit(esito, {"concorso-docenti-2026"}) is True

    def test_articolo_sbagliato_dello_stesso_sito(self):
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[CitazioneGrezza(url="https://edunews24.it/scuola/altro-pezzo")],
            own_domain=PROPRIO,
        )
        assert e_target_hit(esito, {"concorso-docenti-2026"}) is False

    def test_senza_slug_atteso(self):
        esito = analizza(
            answer_text="...",
            citazioni_strutturate=[CitazioneGrezza(url="https://edunews24.it/scuola/x")],
            own_domain=PROPRIO,
        )
        assert e_target_hit(esito, None) is False
        assert e_target_hit(esito, set()) is False


class TestRispostaVuota:
    def test_nessun_testo_nessuna_citazione(self):
        esito = analizza(answer_text=None, citazioni_strutturate=[], own_domain=PROPRIO)
        assert esito.citazioni == []
        assert esito.livello == "nessuno"
        assert not any((esito.edunews_cited, esito.edunews_mention, esito.edunews_retrieved))
