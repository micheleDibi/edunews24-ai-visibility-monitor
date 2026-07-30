"""Validazione delle query generate.

Il controllo che conta e' il primo: una domanda che nomina il giornale falsa
la misura, perche' chiede al modello di parlare di edunews24 invece di
osservare se ci arriva da solo. Non e' un dettaglio di forma, e' la
correttezza del dato.

La validazione gira DUE volte: sui template e di nuovo dopo la riscrittura
LLM, perche' il modello puo' reintrodurre un nome che gli abbiamo tolto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.querygen.normalize import solo_alfanumerico

LUNGHEZZA_MIN = 15
LUNGHEZZA_MAX = 300

# Il brand, ridotto a sole lettere e cifre. Qualunque grafia con spazi,
# trattini, punti o maiuscole diverse collassa su questa.
_BRAND_COLLASSATI = ("edunews", "edunews24")

# Marcatori di lingua. Non servono a riconoscere l'italiano — servono a
# riconoscere che NON e' italiano, che e' un problema diverso e piu' facile.
# Il rischio reale e' che il modello di riscrittura risponda in inglese.
# Scritti come testo e divisi a runtime: una lista di ottanta stringhe fra
# virgolette e' illeggibile, e queste liste si rileggono ogni volta che si
# indaga un falso positivo.
_MARCATORI_ITALIANI = frozenset(
    """
    il lo la i gli le un uno una di del della dei delle da dal dalla in nel nella
    con su sul sulla per tra fra e o ma che chi cosa come quando dove quanto quanti
    quale quali perche non si ci ne sono e' essere fare puo posso devo deve serve
    quest questo questa questi queste al alla ai alle piu meno anche gia ancora
    """.split()  # noqa: SIM905
)
_MARCATORI_INGLESI = frozenset(
    """
    the and or of to in for with what how when where which who is are was were
    do does did can could should would about from this that these those you your
    """.split()  # noqa: SIM905
)

# Alfabeti che in una domanda italiana non hanno motivo di comparire. Un
# risultato in cirillico o in cinese e' un modello che ha perso il filo.
_SCRITTURA_ESTRANEA = re.compile(
    r"[Ѐ-ӿ֐-׿؀-ۿऀ-ॿ"
    r"぀-ヿ一-鿿가-힯]"
)

_PAROLE = re.compile(r"[a-zà-ÿ']+", re.IGNORECASE)


class MotivoScarto(StrEnum):
    BRAND = "contiene_il_brand"
    TROPPO_CORTA = "troppo_corta"
    TROPPO_LUNGA = "troppo_lunga"
    NON_ITALIANA = "non_italiana"
    DUPLICATA = "duplicata"
    VUOTA = "vuota"


@dataclass(frozen=True)
class Esito:
    valida: bool
    motivo: MotivoScarto | None = None

    @staticmethod
    def ok() -> Esito:
        return Esito(True)

    @staticmethod
    def no(motivo: MotivoScarto) -> Esito:
        return Esito(False, motivo)


def contiene_brand(testo: str, own_domain: str = "edunews24.it") -> bool:
    """True se la domanda nomina il giornale, in qualunque grafia.

    Confronta la stringa ridotta a sole lettere e cifre, cosi' "edu news 24",
    "EduNews24", "edu-news-24" e "edunews24.it" ricadono tutte nello stesso
    caso senza dover elencare le varianti.
    """
    collassato = solo_alfanumerico(testo)
    if any(b in collassato for b in _BRAND_COLLASSATI):
        return True
    # Il dominio e' configurabile: se un giorno cambia, il controllo lo segue.
    dominio = solo_alfanumerico(own_domain)
    return bool(dominio) and dominio in collassato


def sembra_italiano(testo: str) -> bool:
    """Euristica volutamente permissiva.

    Le query da template sono italiane per costruzione; qui si intercetta il
    caso in cui la riscrittura LLM cambia lingua. Una "frase secca" senza
    parole funzionali ("concorso docenti 2026 requisiti") e' una query
    legittima e non va scartata, quindi si respinge solo cio' che e'
    chiaramente altro.
    """
    if _SCRITTURA_ESTRANEA.search(testo):
        return False

    parole = [p.casefold() for p in _PAROLE.findall(testo)]
    if not parole:
        return False

    italiane = sum(1 for p in parole if p in _MARCATORI_ITALIANI)
    inglesi = sum(1 for p in parole if p in _MARCATORI_INGLESI)

    return not (inglesi >= 2 and inglesi > italiane)


def valida_testo(testo: str, own_domain: str = "edunews24.it") -> Esito:
    """Controlli che non richiedono il database. La deduplica sta altrove."""
    ripulito = testo.strip()
    if not ripulito:
        return Esito.no(MotivoScarto.VUOTA)
    if contiene_brand(ripulito, own_domain):
        return Esito.no(MotivoScarto.BRAND)
    if len(ripulito) < LUNGHEZZA_MIN:
        return Esito.no(MotivoScarto.TROPPO_CORTA)
    if len(ripulito) > LUNGHEZZA_MAX:
        return Esito.no(MotivoScarto.TROPPO_LUNGA)
    if not sembra_italiano(ripulito):
        return Esito.no(MotivoScarto.NON_ITALIANA)
    return Esito.ok()
