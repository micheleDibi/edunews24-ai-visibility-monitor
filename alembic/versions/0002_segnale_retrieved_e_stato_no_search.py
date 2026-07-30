"""Terzo segnale (recuperato), tipo di citazione, stato no_search.

Tre aggiunte emerse dalla verifica delle API dei provider (docs/providers.md,
2026-07-30):

1. `probes.status = 'no_search'` — OpenAI, Anthropic e Gemini possono
   rispondere senza cercare. Una risposta a memoria non contiene citazioni, e
   registrarla come `edunews_cited = false` scriverebbe "non citato" dove la
   verita' e' "non misurato". Questi probe vanno esclusi da ogni denominatore.

2. `citations.kind` — OpenAI (`annotations` contro `action.sources`), Anthropic
   (`citations` contro `web_search_tool_result`) e Perplexity (marcatori `[n]`
   contro `search_results`) distinguono le fonti CITATE da quelle solo
   RECUPERATE. Sommarle gonfierebbe il tasso di citazione.

3. `probes.edunews_retrieved` — il terzo stadio dell'imbuto. "Non recuperato"
   e' un problema di indicizzazione, "recuperato ma non citato" e' un problema
   di qualita' percepita del pezzo: due azioni editoriali diverse.

I vincoli CHECK vanno scritti a mano perche' l'autogenerate di Alembic non
rileva le modifiche ai CHECK esistenti.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATI_VECCHI = "('ok', 'error', 'timeout', 'rate_limited')"
STATI_NUOVI = "('ok', 'error', 'timeout', 'rate_limited', 'no_search')"


def upgrade() -> None:
    op.add_column(
        "citations",
        sa.Column("kind", sa.Text(), server_default=sa.text("'citation'"), nullable=False),
    )
    op.create_check_constraint("kind_valido", "citations", "kind IN ('citation', 'source')")
    op.create_index("ix_citations_kind_domain", "citations", ["kind", "domain"], unique=False)

    op.add_column(
        "probes",
        sa.Column(
            "edunews_retrieved", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    # Un CHECK si allarga solo cancellandolo e ricreandolo. Il nome va passato
    # NUDO: la naming convention di `Base.metadata` lo espande in
    # `ck_probes_status_valido`, e passarlo gia' espanso lo prefisserebbe due
    # volte (`ck_probes_ck_probes_status_valido`).
    op.drop_constraint("status_valido", "probes", type_="check")
    op.create_check_constraint("status_valido", "probes", f"status IN {STATI_NUOVI}")


def downgrade() -> None:
    # I probe `no_search` non rientrano nel vincolo vecchio: senza cancellarli
    # il downgrade fallirebbe. Sono campioni non validi per costruzione, quindi
    # perderli non perde nessuna misura.
    op.execute("DELETE FROM probes WHERE status = 'no_search'")
    op.drop_constraint("status_valido", "probes", type_="check")
    op.create_check_constraint("status_valido", "probes", f"status IN {STATI_VECCHI}")

    op.drop_column("probes", "edunews_retrieved")
    op.drop_index("ix_citations_kind_domain", table_name="citations")
    op.drop_constraint("kind_valido", "citations", type_="check")
    op.drop_column("citations", "kind")
