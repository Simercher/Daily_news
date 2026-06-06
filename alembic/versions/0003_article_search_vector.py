"""add PostgreSQL article search vector

Revision ID: 0003_article_search_vector
Revises: 0002_v1_1_enhancements
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_article_search_vector"
down_revision = "0002_v1_1_enhancements"
branch_labels = None
depends_on = None

SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(description, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(content_snippet, '')), 'C')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "articles",
            sa.Column(
                "search_vector",
                postgresql.TSVECTOR(),
                sa.Computed(SEARCH_VECTOR_EXPR, persisted=True),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_articles_search_vector",
            "articles",
            ["search_vector"],
            postgresql_using="gin",
        )
    else:
        op.add_column("articles", sa.Column("search_vector", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("ix_articles_search_vector", table_name="articles")
    op.drop_column("articles", "search_vector")
