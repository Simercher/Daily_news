import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)


def get_engine():
    url = os.getenv("DATABASE_URL", DATABASE_URL)
    if str(engine.url) == url:
        return engine
    return create_engine(url, future=True)


def get_session_local():
    return sessionmaker(bind=get_engine(), future=True)
