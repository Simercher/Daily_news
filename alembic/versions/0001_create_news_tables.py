"""create Daily_news target tables

Revision ID: 0001_create_news_tables
Revises:
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_create_news_tables"
down_revision = None
branch_labels = None
depends_on = None

jsonb = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
text_array = postgresql.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table("news_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("country", sa.String(length=16), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table("articles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_domain", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_snippet", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("url_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("country", sa.String(length=16), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("raw_payload", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("title_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duplicate_of_article_id", sa.BigInteger(), sa.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for col in ["source_type", "source_name", "source_domain", "normalized_title", "published_at", "collected_at", "category", "is_duplicate", "duplicate_of_article_id"]:
        op.create_index(f"ix_articles_{col}", "articles", [col])

    op.create_table("events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trusted_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("country_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("popular_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("importance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("breaking_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("final_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_breaking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("breaking_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("keywords", text_array, nullable=False, server_default=sa.text("ARRAY[]::TEXT[]")),
        sa.Column("entities", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for col in ["event_date", "category", "status", "is_breaking", "final_score", "breaking_score", "last_seen_at"]:
        op.create_index(f"ix_events_{col}", "events", [col])

    op.create_table("event_articles",
        sa.Column("event_id", sa.BigInteger(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_representative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_event_articles_article_id", "event_articles", ["article_id"])
    op.create_index("ix_event_articles_is_representative", "event_articles", ["is_representative"])

    op.create_table("collection_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("lookback_hours", sa.Integer(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for col in ["source_type", "source_name", "started_at", "status"]:
        op.create_index(f"ix_collection_runs_{col}", "collection_runs", [col])


def downgrade() -> None:
    op.drop_table("collection_runs")
    op.drop_table("event_articles")
    op.drop_table("events")
    op.drop_table("articles")
    op.drop_table("news_sources")
