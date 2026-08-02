"""Ogni modo di saltare un ciclo diventa uno stato distinto e visibile.

In produzione meta' delle ore di un giorno e' sparita dalla tabella `runs`
senza lasciare traccia: cicli mai partiti perche' il processo era fermo,
saltati perche' il precedente era ancora in corso, o persi per un'esecuzione
fuori tempo massimo. Tutti invisibili, tutti indistinguibili tra loro e da un
servizio spento. Tre stati nuovi:

* `skipped_overlap` — il ciclo precedente era ancora in esecuzione al minuto 7
  (`max_instances=1` ha scartato il fire, che APScheduler non ritenta mai);
* `skipped_misfire` — il processo era bloccato e l'esecuzione e' arrivata
  oltre il tempo di grazia;
* `skipped_offline` — riga scritta al riavvio per le ore in cui il servizio
  era proprio spento (con il jobstore in memoria APScheduler non ne sa nulla).

I vincoli CHECK vanno scritti a mano perche' l'autogenerate di Alembic non
rileva le modifiche ai CHECK esistenti.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATI_VECCHI = "('running', 'ok', 'partial', 'failed', 'skipped_budget')"
STATI_NUOVI = (
    "('running', 'ok', 'partial', 'failed', 'skipped_budget', "
    "'skipped_overlap', 'skipped_misfire', 'skipped_offline')"
)


def upgrade() -> None:
    # Un CHECK si allarga solo cancellandolo e ricreandolo. Il nome va passato
    # NUDO: la naming convention di `Base.metadata` lo espande in
    # `ck_runs_status_valido`.
    op.drop_constraint("status_valido", "runs", type_="check")
    op.create_check_constraint("status_valido", "runs", f"status IN {STATI_NUOVI}")


def downgrade() -> None:
    # Le righe con gli stati nuovi sono marcatori senza probe: cancellarle non
    # perde nessuna misura, e senza cancellarle il vincolo vecchio fallirebbe.
    op.execute(
        "DELETE FROM runs WHERE status IN ('skipped_overlap', 'skipped_misfire', 'skipped_offline')"
    )
    op.drop_constraint("status_valido", "runs", type_="check")
    op.create_check_constraint("status_valido", "runs", f"status IN {STATI_VECCHI}")
