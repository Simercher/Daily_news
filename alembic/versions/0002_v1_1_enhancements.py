"""v1.1 enhancements: new columns, breaking alert states

Revision ID: 0002_v1_1_enhancements
Revises: 0001_create_news_tables
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_v1_1_enhancements"
down_revision = "0001_create_news_tables"
branch_labels = None
depends_on = None

jsonb = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
text_array = postgresql.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # Add columns to articles
    op.add_column("articles", sa.Column("fulltext_status", sa.String(length=32), nullable=True, server_default="not_attempted"))
    op.add_column("articles", sa.Column("fulltext_quality_score", sa.Float(), nullable=True, server_default="0"))
    op.add_column("articles", sa.Column("fulltext_extracted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("articles", sa.Column("fulltext_error_message", sa.Text(), nullable=True))

    # Add columns to news_sources
    op.add_column("news_sources", sa.Column("credibility_score", sa.Float(), nullable=True, server_default="0.5"))
    op.add_column("news_sources", sa.Column("region", sa.String(length=64), nullable=True))
    op.add_column("news_sources", sa.Column("ownership_type", sa.String(length=64), nullable=True))
    op.add_column("news_sources", sa.Column("source_notes", sa.Text(), nullable=True))

    # Add columns to events
    op.add_column("events", sa.Column("event_fingerprint", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("score_breakdown", jsonb, nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.add_column("events", sa.Column("representative_article_id", sa.BigInteger(), nullable=True))
    op.add_column("events", sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("cluster_method", sa.String(length=64), nullable=True))

    # FK for representative_article_id
    op.create_foreign_key(
        "fk_events_representative_article_id",
        "events", "articles",
        ["representative_article_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_events_representative_article_id", "events", ["representative_article_id"])

    # Create breaking_alert_states table
    op.create_table("breaking_alert_states",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_id", sa.BigInteger(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_breaking_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_breaking_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_trusted_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_breaking_alert_states_event_id", "breaking_alert_states", ["event_id"])
    op.create_index("ix_breaking_alert_states_status", "breaking_alert_states", ["status"])


def downgrade() -> None:
    op.drop_table("breaking_alert_states")
    op.drop_index("ix_events_representative_article_id", table_name="events")
    op.drop_constraint("fk_events_representative_article_id", "events", type_="foreignkey")
    op.drop_column("events", "cluster_method")
    op.drop_column("events", "last_scored_at")
    op.drop_column("events", "representative_article_id")
    op.drop_column("events", "score_breakdown")
    op.drop_column("events", "event_fingerprint")
    op.drop_column("news_sources", "source_notes")
    op.drop_column("news_sources", "ownership_type")
    op.drop_column("news_sources", "region")
    op.drop_column("news_sources", "credibility_score")
    op.drop_column("articles", "fulltext_error_message")
    op.drop_column("articles", "fulltext_extracted_at")
    op.drop_column("articles", "fulltext_quality_score")
    op.drop_column("articles", "fulltext_status")