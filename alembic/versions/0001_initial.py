"""Schema iniziale del database di monitoraggio.

Generata con `alembic revision --autogenerate` contro i modelli in
`app/models/`, poi rinominata nella convenzione NNNN_ del progetto.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_rollup",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("category_slug", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("probes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cited", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("mentioned", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("target_hits", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cost_eur",
            sa.Numeric(precision=10, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('retrieval', 'memory')", name=op.f("ck_daily_rollup_mode_valido")
        ),
        sa.PrimaryKeyConstraint(
            "day", "provider", "mode", "category_slug", name=op.f("pk_daily_rollup")
        ),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default=sa.text("'hourly'"), nullable=False),
        sa.Column("planned", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cost_eur",
            sa.Numeric(precision=10, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('hourly', 'manual', 'backfill')", name=op.f("ck_runs_kind_valido")
        ),
        sa.CheckConstraint(
            "status IN ('running', 'ok', 'partial', 'failed', 'skipped_budget')",
            name=op.f("ck_runs_status_valido"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    op.create_index(
        "ix_runs_started_at", "runs", [sa.literal_column("started_at DESC")], unique=False
    )
    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category_slug", sa.Text(), nullable=True),
        sa.Column("livello", sa.Text(), nullable=True),
        sa.Column("keyword", sa.Text(), nullable=True),
        sa.Column("angolo", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "faq_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_probed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("probe_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topics")),
        sa.UniqueConstraint("source_id", name=op.f("uq_topics_source_id")),
    )
    op.create_index("ix_topics_category_slug", "topics", ["category_slug"], unique=False)
    op.create_index(
        "ix_topics_last_probed_at",
        "topics",
        [sa.literal_column("last_probed_at NULLS FIRST")],
        unique=False,
    )
    op.create_index(
        "ix_topics_published_at", "topics", [sa.literal_column("published_at DESC")], unique=False
    )
    op.create_table(
        "queries",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("category_slug", sa.Text(), nullable=True),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("generator", sa.Text(), nullable=False),
        sa.Column("source_faq_index", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("run_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "generator IN ('template', 'llm_rewrite')", name=op.f("ck_queries_generator_valido")
        ),
        sa.CheckConstraint(
            "strategy IN ('faq_verbatim', 'keyword_intent', 'tag_combo', 'angolo', "
            "'evergreen_howto', 'category')",
            name=op.f("ck_queries_strategy_valida"),
        ),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 15 AND 300", name=op.f("ck_queries_lunghezza_testo")
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_queries_topic_id_topics"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_queries")),
        sa.UniqueConstraint("text_hash", name=op.f("uq_queries_text_hash")),
    )
    op.create_index(
        "ix_queries_active_last_run_at",
        "queries",
        ["active", sa.literal_column("last_run_at NULLS FIRST")],
        unique=False,
    )
    op.create_index("ix_queries_topic_id", "queries", ["topic_id"], unique=False)
    op.create_table(
        "probes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("query_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("search_calls", sa.Integer(), nullable=True),
        sa.Column("cost_eur", sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column("cost_estimated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("edunews_cited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("edunews_mention", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("target_hit", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('retrieval', 'memory')", name=op.f("ck_probes_mode_valido")),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'timeout', 'rate_limited')",
            name=op.f("ck_probes_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["queries.id"], name=op.f("fk_probes_query_id_queries")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_probes_run_id_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_probes")),
        sa.UniqueConstraint(
            "run_id", "query_id", "provider", "mode", name="uq_probes_run_query_provider_mode"
        ),
    )
    op.create_index(
        "ix_probes_created_at", "probes", [sa.literal_column("created_at DESC")], unique=False
    )
    op.create_index("ix_probes_created_at_cost", "probes", ["created_at", "cost_eur"], unique=False)
    op.create_index(
        "ix_probes_edunews_cited_created_at",
        "probes",
        ["edunews_cited", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_probes_provider_created_at",
        "probes",
        ["provider", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index("ix_probes_query_id", "probes", ["query_id"], unique=False)
    op.create_index("ix_probes_run_id", "probes", ["run_id"], unique=False)
    op.create_table(
        "citations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("probe_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("is_own", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("own_slug", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["probe_id"],
            ["probes.id"],
            name=op.f("fk_citations_probe_id_probes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_citations")),
    )
    op.create_index("ix_citations_domain", "citations", ["domain"], unique=False)
    op.create_index("ix_citations_own_slug", "citations", ["own_slug"], unique=False)
    op.create_index("ix_citations_probe_id", "citations", ["probe_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_citations_probe_id", table_name="citations")
    op.drop_index("ix_citations_own_slug", table_name="citations")
    op.drop_index("ix_citations_domain", table_name="citations")
    op.drop_table("citations")
    op.drop_index("ix_probes_run_id", table_name="probes")
    op.drop_index("ix_probes_query_id", table_name="probes")
    op.drop_index("ix_probes_provider_created_at", table_name="probes")
    op.drop_index("ix_probes_edunews_cited_created_at", table_name="probes")
    op.drop_index("ix_probes_created_at_cost", table_name="probes")
    op.drop_index("ix_probes_created_at", table_name="probes")
    op.drop_table("probes")
    op.drop_index("ix_queries_topic_id", table_name="queries")
    op.drop_index("ix_queries_active_last_run_at", table_name="queries")
    op.drop_table("queries")
    op.drop_index("ix_topics_published_at", table_name="topics")
    op.drop_index("ix_topics_last_probed_at", table_name="topics")
    op.drop_index("ix_topics_category_slug", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_runs_started_at", table_name="runs")
    op.drop_table("runs")
    op.drop_table("daily_rollup")
