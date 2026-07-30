"""Le regole di correttezza degli aggregati, in un posto solo.

Ogni endpoint analitico di questo servizio puo' sbagliare in tre modi che non
producono errori, producono numeri plausibili e falsi:

1. **contare i probe falliti nel denominatore.** Un'ora di disservizio di un
   provider somiglierebbe a un crollo di visibilita' del giornale, e un probe
   `no_search` non e' un "non citato": e' un "non misurato".
2. **mescolare `retrieval` e `memory`.** Misurano cose diverse — se il retrieval
   pesca il giornale, e se il modello lo conosce a memoria — e la loro media non
   e' nessuna delle due.
3. **mostrare una percentuale senza il suo denominatore.** «2,3%» su 3 probe e
   «2,3%» su 3.000 sono la stessa cifra e due informazioni opposte.

Per questo i filtri non sono scritti nei singoli endpoint ma in
`filtri_probe()`, che li impone tutti e tre insieme, e ogni tasso esce dalla
API come `Tasso`, che non permette di esprimere un rapporto senza il suo
numeratore e il suo denominatore.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement

from app.models import Probe

Modo = Literal["retrieval", "memory"]

# Sotto questa numerosita' un tasso non viene dichiarato affidabile. Non e' una
# soglia magica: e' il punto sotto il quale l'intervallo di confidenza diventa
# cosi' largo da non distinguere piu' un 2% da un 10%.
SOGLIA_AFFIDABILITA = 30

# Sotto questa numerosita' il tasso non viene nemmeno calcolato: si restituisce
# `None`, cosi' la UI non ha la tentazione di stamparlo.
SOGLIA_MINIMA = 10


def inizio_periodo(giorni: int, adesso: datetime | None = None) -> datetime:
    return (adesso or datetime.now(UTC)) - timedelta(days=giorni)


def periodo_precedente(giorni: int, adesso: datetime | None = None) -> tuple[datetime, datetime]:
    """Finestra immediatamente precedente, della stessa ampiezza.

    Serve al delta dei KPI: confrontare 30 giorni con i 30 precedenti, non con
    "tutto il resto della storia", che avrebbe un'ampiezza diversa e renderebbe
    il confronto privo di significato.
    """
    fine = inizio_periodo(giorni, adesso)
    return fine - timedelta(days=giorni), fine


def filtri_probe(
    *, mode: Modo, da: datetime, a: datetime | None = None
) -> list[ColumnElement[bool]]:
    """I filtri obbligatori di QUALUNQUE aggregato sui probe.

    `mode` e' un parametro richiesto e senza default di proposito: non si puo'
    scrivere un aggregato dimenticandosi di scegliere quale delle due metriche
    si sta misurando.
    """
    condizioni: list[ColumnElement[bool]] = [
        # Solo i probe riusciti entrano nei conti.
        Probe.status == "ok",
        Probe.mode == mode,
        Probe.created_at >= da,
    ]
    if a is not None:
        condizioni.append(Probe.created_at < a)
    return condizioni


def wilson(successi: int, totale: int, z: float = 1.96) -> tuple[float, float]:
    """Intervallo di confidenza di Wilson al 95%.

    Non l'approssimazione normale: con tassi vicini a zero — che e' il caso
    normale per un giornale locale contro le testate grandi — l'approssimazione
    normale produce estremi negativi e intervalli che non contengono il valore
    vero. Wilson resta dentro [0,1] anche con zero successi.
    """
    if totale <= 0:
        return (0.0, 0.0)
    p = successi / totale
    denominatore = 1 + z**2 / totale
    centro = p + z**2 / (2 * totale)
    scarto = z * math.sqrt(p * (1 - p) / totale + z**2 / (4 * totale**2))
    basso = (centro - scarto) / denominatore
    alto = (centro + scarto) / denominatore
    return (max(0.0, round(basso, 5)), min(1.0, round(alto, 5)))


class Tasso(BaseModel):
    """Un rapporto che non si puo' esprimere senza il suo denominatore."""

    numeratore: int = Field(description="Probe che soddisfano la condizione")
    denominatore: int = Field(description="Probe riusciti nel periodo")
    tasso: float | None = Field(
        default=None,
        description=(
            f"Rapporto in [0,1]. `null` se il denominatore e' sotto {SOGLIA_MINIMA}: "
            "una percentuale su pochi casi e' rumore travestito da misura."
        ),
    )
    ic_basso: float | None = Field(default=None, description="Estremo inferiore, Wilson 95%")
    ic_alto: float | None = Field(default=None, description="Estremo superiore, Wilson 95%")
    affidabile: bool = Field(
        default=False,
        description=f"Vero se il denominatore raggiunge {SOGLIA_AFFIDABILITA}",
    )

    @classmethod
    def da_conteggi(cls, numeratore: int, denominatore: int) -> Tasso:
        if denominatore <= 0:
            return cls(numeratore=0, denominatore=0)
        if denominatore < SOGLIA_MINIMA:
            # Il conteggio si mostra, il tasso no.
            return cls(numeratore=numeratore, denominatore=denominatore)
        basso, alto = wilson(numeratore, denominatore)
        return cls(
            numeratore=numeratore,
            denominatore=denominatore,
            tasso=round(numeratore / denominatore, 5),
            ic_basso=basso,
            ic_alto=alto,
            affidabile=denominatore >= SOGLIA_AFFIDABILITA,
        )


class Delta(BaseModel):
    """Variazione fra due periodi, con entrambi i termini visibili."""

    attuale: Tasso
    precedente: Tasso
    differenza: float | None = Field(
        default=None,
        description=(
            "Differenza fra i due tassi in punti di rapporto. `null` se uno dei "
            "due periodi non ha abbastanza campioni: un delta calcolato su un "
            "tasso non calcolabile e' un numero inventato."
        ),
    )
    significativo: bool = Field(
        default=False,
        description=(
            "Vero solo se gli intervalli di confidenza dei due periodi non si "
            "sovrappongono. Senza questo controllo ogni oscillazione casuale "
            "sembrerebbe un miglioramento o un peggioramento."
        ),
    )

    @classmethod
    def fra(cls, attuale: Tasso, precedente: Tasso) -> Delta:
        if attuale.tasso is None or precedente.tasso is None:
            return cls(attuale=attuale, precedente=precedente)
        disgiunti = (
            attuale.ic_basso is not None
            and precedente.ic_alto is not None
            and attuale.ic_alto is not None
            and precedente.ic_basso is not None
            and (attuale.ic_basso > precedente.ic_alto or attuale.ic_alto < precedente.ic_basso)
        )
        return cls(
            attuale=attuale,
            precedente=precedente,
            differenza=round(attuale.tasso - precedente.tasso, 5),
            significativo=bool(disgiunti),
        )
