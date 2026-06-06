from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from news_system.db.models import Base


POSTGRES_ALEMBIC_GUIDANCE = "PostgreSQL schema is not initialized with Alembic migrations"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _alembic_head_revision() -> str:
    repo_root = _repo_root()
    config_path = repo_root / "alembic.ini"
    script_path = repo_root / "alembic"
    if not config_path.exists() or not script_path.exists():
        raise RuntimeError(
            f"{POSTGRES_ALEMBIC_GUIDANCE}; "
            "alembic.ini and alembic/ are required before using daily-news with PostgreSQL"
        )
    cfg = Config(str(config_path))
    cfg.set_main_option("script_location", str(script_path))
    return ScriptDirectory.from_config(cfg).get_current_head()


def prepare_schema(engine: Engine, *, usage: str = "daily-news") -> None:
    """Prepare or validate the database schema for app-owned DB sessions.

    SQLite and other lightweight/local backends keep the legacy create_all fallback.
    PostgreSQL schemas must be managed by Alembic so generated columns and indexes
    from migrations are present; SQLAlchemy create_all cannot express the Phase 2
    generated search_vector + GIN index contract safely.
    """
    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(engine)
        return

    try:
        with engine.connect() as conn:
            current_revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise RuntimeError(
            f"{POSTGRES_ALEMBIC_GUIDANCE}; "
            f"run `uv run alembic upgrade head` before using {usage}"
        ) from exc

    expected_revision = _alembic_head_revision()
    if current_revision != expected_revision:
        raise RuntimeError(
            f"{POSTGRES_ALEMBIC_GUIDANCE}; "
            f"expected Alembic revision {expected_revision}, found {current_revision or 'none'}; "
            f"run `uv run alembic upgrade head` before using {usage}"
        )
