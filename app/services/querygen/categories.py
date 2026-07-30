"""Domande di categoria: il 10% del lotto che non nasce da un articolo.

Sono le domande generiche su cui il giornale compete con le testate grandi —
quelle che un lettore fa senza avere in mente una notizia specifica. Servono a
misurare la visibilita' di fondo, non quella di un pezzo.

Lista curata a mano e versionata, non generata: sono poche decine, devono
suonare come le scriverebbe un genitore, un docente o uno studente, e un
generatore automatico su queste sbaglierebbe piu' spesso di quanto aiuti.

I 12 slug corrispondono alle categorie editoriali di edunews24.it. Se uno slug
non compare fra quelli presenti in `topics`, il generatore lo segnala nei log:
significa che il nome e' cambiato e che la segmentazione delle metriche per
quella categoria sarebbe sbagliata.
"""

from __future__ import annotations

DOMANDE_PER_CATEGORIA: dict[str, tuple[str, ...]] = {
    "scuola": (
        "Quando iniziano le lezioni del prossimo anno scolastico?",
        "Come funziona la messa a disposizione per le supplenze?",
        "Come si calcola il voto di ammissione all'esame di maturità?",
        "Quali sono le regole sulle assenze scolastiche?",
    ),
    "universita": (
        "Come funzionano i test di ingresso a Medicina?",
        "Quali sono le scadenze per l'immatricolazione all'università?",
        "Come si richiede la borsa di studio universitaria?",
        "Come funziona il calcolo dell'ISEE per le tasse universitarie?",
    ),
    "formazione": (
        "Come funziona la formazione obbligatoria dei docenti?",
        "Cosa sono i percorsi ITS e a chi si rivolgono?",
        "Quali certificazioni linguistiche danno punteggio nelle graduatorie?",
        "Come si ottiene una qualifica professionale riconosciuta?",
    ),
    "lavoro": (
        "Quali sono i requisiti per ottenere la NASpI?",
        "Come funziona il contratto di apprendistato?",
        "Come si calcola il TFR?",
        "Quali incentivi ci sono per assumere giovani?",
    ),
    "ricerca": (
        "Come si accede a un dottorato di ricerca?",
        "Come funziona l'abilitazione scientifica nazionale?",
        "Quanto guadagna un assegnista di ricerca?",
        "Quali sono i bandi PRIN aperti in questo momento?",
    ),
    "cultura": (
        "Come funziona la Carta della Cultura Giovani?",
        "Quali musei statali sono gratuiti la prima domenica del mese?",
        "Come si partecipa a un bando per progetti culturali?",
        "Quali sono le agevolazioni culturali per gli studenti?",
    ),
    "mondo": (
        "Come funziona il programma Erasmus+ per gli studenti universitari?",
        "Come si fa a studiare un anno all'estero durante le superiori?",
        "Come si ottiene il riconoscimento di un titolo di studio estero?",
        "Quali requisiti servono per insegnare all'estero?",
    ),
    "editoriali": (
        "Perché mancano insegnanti di sostegno nelle scuole italiane?",
        "Cosa prevede la riforma della scuola in discussione in Parlamento?",
        "Quali effetti ha il dimensionamento scolastico sulle scuole piccole?",
        "Come sta cambiando la valutazione degli studenti in Italia?",
    ),
    "bandi": (
        "Quali bandi PNRR sono aperti per le scuole?",
        "Come si partecipa a un bando per finanziamenti europei?",
        "Quali contributi ci sono per l'edilizia scolastica?",
        "Come funziona la rendicontazione di un bando pubblico?",
    ),
    "interpelli": (
        "Come funzionano gli interpelli per le supplenze?",
        "Dove si trovano gli interpelli pubblicati dalle scuole?",
        "Chi può rispondere a un interpello nazionale?",
        "Quali requisiti servono per un interpello su sostegno?",
    ),
    "selezione-personale": (
        "Quali concorsi pubblici sono aperti nel comparto istruzione?",
        "Come funziona la graduatoria di un concorso ATA?",
        "Quali titoli danno punteggio nelle GPS?",
        "Come si presenta la domanda per un concorso scuola?",
    ),
    "eu-funding": (
        "Come funzionano i fondi del PNRR destinati all'istruzione?",
        "Quali progetti finanzia Italia Domani nel settore scuola?",
        "Come si accede ai fondi europei per la formazione?",
        "Quali sono le scadenze dei bandi europei per l'istruzione?",
    ),
}


def tutte_le_domande() -> list[tuple[str, str]]:
    """Coppie (category_slug, domanda), in ordine deterministico."""
    return [
        (slug, domanda)
        for slug in sorted(DOMANDE_PER_CATEGORIA)
        for domanda in DOMANDE_PER_CATEGORIA[slug]
    ]
