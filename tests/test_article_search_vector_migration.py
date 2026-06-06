from pathlib import Path

from news_system.db.models import Base


MIGRATION_PATH = Path("alembic/versions/0003_article_search_vector.py")


def test_article_model_exposes_search_vector_for_postgres_fts() -> None:
    articles = Base.metadata.tables["articles"]
    assert "search_vector" in articles.columns


def test_search_vector_migration_documents_db_managed_maintenance_and_index() -> None:
    migration = MIGRATION_PATH.read_text()

    assert 'revision = "0003_article_search_vector"' in migration
    assert 'down_revision = "0002_v1_1_enhancements"' in migration
    assert 'sa.Computed(' in migration
    assert "to_tsvector('simple', coalesce(title, ''))" in migration
    assert "to_tsvector('simple', coalesce(description, ''))" in migration
    assert "to_tsvector('simple', coalesce(content_snippet, ''))" in migration
    assert 'postgresql_using="gin"' in migration
    assert '"ix_articles_search_vector"' in migration
