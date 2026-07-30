"""Modelli del database di monitoraggio.

L'import di tutti i modelli qui e' cio' che li registra su `Base.metadata`:
`alembic/env.py` importa questo pacchetto e senza di esso l'autogenerate
vedrebbe uno schema vuoto e proporrebbe di cancellare tutte le tabelle.
"""

from app.models.citation import DOMINIO_NON_RISOLTO, Citation
from app.models.daily_rollup import SENZA_CATEGORIA, DailyRollup
from app.models.probe import MODI, STATI_PROBE, Probe
from app.models.query import GENERATORI, STRATEGIE, Query
from app.models.run import STATI_RUN, TIPI_RUN, Run
from app.models.topic import Topic

__all__ = [
    "DOMINIO_NON_RISOLTO",
    "GENERATORI",
    "MODI",
    "SENZA_CATEGORIA",
    "STATI_PROBE",
    "STATI_RUN",
    "STRATEGIE",
    "TIPI_RUN",
    "Citation",
    "DailyRollup",
    "Probe",
    "Query",
    "Run",
    "Topic",
]
