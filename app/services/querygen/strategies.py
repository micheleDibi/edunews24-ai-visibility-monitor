"""Dalle proprieta' di un topic al testo di una domanda. Logica pura.

Nessun accesso al database: si testa costruendo `Topic` a mano.

## Perche' i template usano la forma con i due punti

"concorso docenti 2026" + "quali sono le scadenze" non si puo' comporre in
"Quali sono le scadenze per concorso docenti 2026?": in italiano servirebbe
"per il concorso", e sapere se ci vuole il/lo/la/i/gli/le — e quale
preposizione articolata — richiede il genere e il numero della keyword, che
non abbiamo.

Le alternative erano una libreria di morfologia italiana (una dipendenza
pesante per un problema di contorno) o indovinare (che produce italiano
sbagliato, cioe' query che nessun lettore scriverebbe, cioe' una misura di
qualcos'altro).

La forma "concorso docenti 2026: quali sono le scadenze?" e' grammaticalmente
corretta, e' esattamente come si scrive un titolo o una ricerca, e non
richiede alcuna concordanza. Il passaggio di naturalizzazione LLM la
trasforma poi in una domanda distesa; se quel passaggio salta, cio' che resta
e' comunque italiano corretto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.models import Topic

# Modificatori di intento della specifica, in forma componibile.
TEMPLATE_KEYWORD_INTENT = (
    "{k}: come funziona?",
    "{k}: chi può partecipare?",
    "{k}: quali sono le scadenze?",
    "{k}: quanto costa?",
    "{k}: come si presenta la domanda?",
    "{k}: cosa cambia nel {anno}?",
    "{k}: quali sono i requisiti?",
    "{k}: a chi spetta?",
)

# Solo forme di approfondimento, nessuna comparativa. "Che differenza c'e' tra
# scuola e GPS?" e' una domanda che nessuno farebbe: due tag dello stesso
# articolo sono co-occorrenti, non alternative fra cui scegliere.
TEMPLATE_TAG_COMBO = (
    "{a} e {b}: cosa c'è da sapere?",
    "{a} e {b}: cosa cambia nel {anno}?",
    "{a} e {b}: come funzionano?",
)

TEMPLATE_EVERGREEN = (
    "{k}: come si richiede?",
    "{k}: quali documenti servono?",
    "{k}: come funziona?",
    "{k}: a chi conviene?",
)

# `skill_angolo` contiene la RISPOSTA ("I posti a bando salgono a 30.000"),
# non la domanda. Girarlo in "I posti a bando salgono a 30.000?" produce una
# richiesta di conferma, che nessuno digita: si cerca "quanti posti", non "è
# vero che sono trentamila".
#
# Da cosa contiene l'angolo si deduce quale domanda quell'articolo risponde, e
# si chiede quella. Sono le query in cui un pezzo con dati verificati ha piu'
# probabilita' di essere la fonte migliore disponibile, quindi vale la pena
# comporle bene. L'ordine conta: il primo pattern che corrisponde vince.
MESI = (
    "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
)
INFERENZE_ANGOLO: tuple[tuple[str, str], ...] = (
    (rf"domand\w*.*(\d|{MESI})|(\d|{MESI}).*domand\w*", "{k}: quando si presenta la domanda?"),
    (
        rf"scadenz|entro (il|la)|termine|proroga|si chiud|si apr|{MESI}",
        "{k}: quali sono le scadenze?",
    ),
    (
        r"euro|€|import\w*|stipendi\w*|aument\w*|indennit|assegn\w*|rimbors",
        "{k}: a quanto ammonta?",
    ),
    (r"\bposti\b|cattedr|assunzion|immission", "{k}: quanti posti sono previsti?"),
    (r"requisit|possono partecipare|ammess|esclus|titol", "{k}: chi può partecipare?"),
)

# Separatori tipici dei titoli giornalistici: la parte prima del primo
# separatore e' quasi sempre il soggetto della notizia.
# Lineetta media e lunga sono intenzionali: i titoli italiani le usano al posto
# del trattino, e senza di esse il ripiego sul titolo non taglierebbe.
_SEPARATORI_TITOLO = re.compile(r"\s*[,:;]\s*|\s+[-–—]\s+")  # noqa: RUF001
_PUNTEGGIATURA_FINALE = re.compile(r"[.!?…]+\s*$")


@dataclass(frozen=True)
class QueryCandidata:
    text: str
    strategy: str
    topic_id: int | None = None
    category_slug: str | None = None
    source_faq_index: int | None = None
    generator: str = "template"


def _anno_corrente() -> int:
    return date.today().year


def keyword_da_titolo(titolo: str) -> str | None:
    """Ricava una keyword dal titolo quando `skill_keyword` non c'e'.

    Gli articoli piu' vecchi non hanno le colonne `skill_*`, ma senza una
    keyword l'intero bucket archivio resterebbe non sondabile. I titoli
    italiani hanno quasi sempre la forma "Soggetto della notizia, cosa
    succede": la parte prima del primo separatore e' una keyword utilizzabile.
    """
    testa = _SEPARATORI_TITOLO.split(titolo.strip(), maxsplit=1)[0].strip()
    testa = _PUNTEGGIATURA_FINALE.sub("", testa)
    if 8 <= len(testa) <= 80:
        return testa
    return None


def _indice_template(topic: Topic, quanti: int) -> int:
    """Sceglie il template in modo deterministico ma variabile nel tempo.

    Dipende anche da `probe_count`: uno stesso articolo sondato piu' volte nel
    corso dei mesi non riceve sempre la stessa domanda, ma a parita' di stato
    il risultato e' riproducibile e quindi testabile.
    """
    return ((topic.source_id or 0) + (topic.probe_count or 0)) % quanti


def _pulisci(testo: str) -> str:
    return " ".join(testo.split())


def _iniziale_maiuscola(testo: str) -> str:
    """Solo la prima lettera, senza toccare il resto.

    `str.capitalize()` abbasserebbe tutto il resto e trasformerebbe "ISEE
    universitario" in "Isee universitario" e "GPS" in "Gps": sigle e nomi
    propri sono esattamente le entita' che la misura deve conservare.
    """
    return testo[:1].upper() + testo[1:] if testo else testo


def domanda_da_angolo(angolo: str, keyword: str) -> str | None:
    """La domanda a cui l'angolo dell'articolo risponde, se deducibile."""
    minuscolo = angolo.casefold()
    for pattern, template in INFERENZE_ANGOLO:
        if re.search(pattern, minuscolo):
            return template.format(k=keyword)
    return None


def _tag_piu_specifici(tags: list[str]) -> list[str]:
    """I due tag piu' informativi, nell'ordine originale.

    I primi due tag di un articolo sono spesso il piu' specifico e il piu'
    generico ("dottorato", "bandi"), e accostarli produce una domanda vaga.
    Si preferiscono quelli con piu' parole, e a parita' i piu' lunghi.
    """
    migliori = sorted(tags, key=lambda t: (-len(t.split()), -len(t)))[:2]
    return [t for t in tags if t in migliori][:2]


def prima_faq_inutilizzata(topic: Topic, usate: set[int]) -> tuple[int, str] | None:
    for indice, domanda in enumerate(topic.faq_questions or []):
        if indice in usate or not isinstance(domanda, str):
            continue
        pulita = _pulisci(domanda)
        if pulita:
            return indice, pulita
    return None


def genera_per_topic(
    topic: Topic,
    faq_usate: set[int] | None = None,
    *,
    anno: int | None = None,
) -> QueryCandidata | None:
    """Una query per topic, con la strategia migliore fra quelle possibili.

    L'ordine e' quello della specifica: le FAQ per prime perche' sono gia'
    domande formulate da un umano per un lettore, e nessun template le batte.
    Restituisce `None` se il topic non ha abbastanza materiale.
    """
    faq_usate = faq_usate or set()
    anno = anno or _anno_corrente()
    comune: dict[str, Any] = {"topic_id": topic.id, "category_slug": topic.category_slug}

    # 1. faq_verbatim — la domanda l'ha gia' scritta la redazione.
    if (faq := prima_faq_inutilizzata(topic, faq_usate)) is not None:
        indice, domanda = faq
        return QueryCandidata(
            text=domanda, strategy="faq_verbatim", source_faq_index=indice, **comune
        )

    tags = [_pulisci(t) for t in (topic.tags or []) if isinstance(t, str) and t.strip()]
    keyword = _pulisci(topic.keyword) if topic.keyword else None
    # Gli articoli anteriori alle colonne `skill_*` non hanno una keyword: si
    # ricava dal titolo. E' un ripiego e resta in fondo alla scala, altrimenti
    # coprirebbe `tag_combo` per ogni articolo con un titolo utilizzabile —
    # cioe' quasi tutti — e una delle cinque strategie diventerebbe morta.
    ripiego = keyword_da_titolo(topic.title or "")

    def candidata(testo: str, strategia: str) -> QueryCandidata:
        return QueryCandidata(text=_iniziale_maiuscola(testo), strategy=strategia, **comune)

    # 2. angolo — la domanda a cui il dato specifico dell'articolo risponde.
    #    Se dall'angolo non si deduce nulla si prosegue: meglio una domanda
    #    generica ma sensata che una costruita male su un dato buono.
    if topic.angolo and (soggetto := keyword or ripiego):
        angolo = _PUNTEGGIATURA_FINALE.sub("", _pulisci(topic.angolo))
        if angolo and (testo := domanda_da_angolo(angolo, soggetto)) is not None:
            return candidata(testo, "angolo")

    # 3. evergreen_howto — prima di keyword_intent solo per gli evergreen, per
    #    cui la domanda procedurale e' piu' naturale di quella d'attualita'.
    if topic.livello == "evergreen" and (soggetto := keyword or ripiego):
        template = TEMPLATE_EVERGREEN[_indice_template(topic, len(TEMPLATE_EVERGREEN))]
        return candidata(template.format(k=soggetto), "evergreen_howto")

    # 4. keyword_intent, sulla keyword redazionale
    if keyword:
        template = TEMPLATE_KEYWORD_INTENT[_indice_template(topic, len(TEMPLATE_KEYWORD_INTENT))]
        return candidata(template.format(k=keyword, anno=anno), "keyword_intent")

    # 5. tag_combo
    if len(tags) >= 2:
        a, b = _tag_piu_specifici(tags)
        template = TEMPLATE_TAG_COMBO[_indice_template(topic, len(TEMPLATE_TAG_COMBO))]
        return candidata(template.format(a=a, b=b, anno=anno), "tag_combo")

    # 6. Ultimo ripiego: la keyword dal titolo.
    if ripiego:
        template = TEMPLATE_KEYWORD_INTENT[_indice_template(topic, len(TEMPLATE_KEYWORD_INTENT))]
        return candidata(template.format(k=ripiego, anno=anno), "keyword_intent")

    return None
