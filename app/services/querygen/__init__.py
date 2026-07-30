"""MASTER: generazione delle domande da mandare ai motori di risposta.

Il valore di tutto il sistema dipende da questo componente. Se le domande non
somigliano a quelle che un lettore italiano scrive davvero, i probe misurano
la visibilita' su un linguaggio che nessuno usa, e il numero che finisce in
dashboard e' preciso e inutile.
"""

from app.services.querygen.generator import EsitoGenerazione, genera_lotto
from app.services.querygen.normalize import calcola_hash, normalizza
from app.services.querygen.selection import ripartisci, seleziona_topic
from app.services.querygen.strategies import QueryCandidata, genera_per_topic
from app.services.querygen.validate import MotivoScarto, contiene_brand, valida_testo

__all__ = [
    "EsitoGenerazione",
    "MotivoScarto",
    "QueryCandidata",
    "calcola_hash",
    "contiene_brand",
    "genera_lotto",
    "genera_per_topic",
    "normalizza",
    "ripartisci",
    "seleziona_topic",
    "valida_testo",
]
