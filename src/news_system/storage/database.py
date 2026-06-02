from news_system.db.session import SessionLocal, engine
from news_system.db.models import Base

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

__all__ = ["Base", "SessionLocal", "engine", "init_db"]
