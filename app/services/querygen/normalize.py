"""Forma normalizzata di una query e hash di deduplicazione.

Due domande che differiscono solo per maiuscole, accenti o punteggiatura sono
la stessa domanda ai fini della misura. Se le mandassimo entrambe pagheremmo
due volte per un solo dato.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Tutto cio' che non e' lettera, cifra o spazio diventa spazio. Include la
# punteggiatura, i trattini e le virgolette tipografiche.
_NON_ALFANUMERICO = re.compile(r"[^\w\s]", re.UNICODE)
_SPAZI = re.compile(r"\s+")


def normalizza(testo: str) -> str:
    """Minuscole, accenti rimossi, punteggiatura via, spazi collassati.

    Gli accenti si rimuovono di proposito: "perche'" e "perché" sono la stessa
    domanda, e la sorgente non e' coerente su quale forma usa.
    """
    decomposto = unicodedata.normalize("NFKD", testo)
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    pulito = _NON_ALFANUMERICO.sub(" ", senza_accenti.casefold())
    return _SPAZI.sub(" ", pulito).strip()


def calcola_hash(testo: str) -> str:
    """Hash della forma normalizzata. E' la chiave di deduplicazione."""
    return hashlib.sha256(normalizza(testo).encode("utf-8")).hexdigest()


def solo_alfanumerico(testo: str) -> str:
    """Testo ridotto a sole lettere e cifre, minuscole.

    Serve al controllo del brand: "edu news 24", "Edunews24", "edu-news-24" e
    "edunews24.it" collassano tutti sulla stessa stringa, quindi un solo
    confronto li intercetta tutti invece di una lista di varianti che si
    dimentichera' sempre di aggiornare.
    """
    decomposto = unicodedata.normalize("NFKD", testo)
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    return "".join(c for c in senza_accenti.casefold() if c.isalnum())
