import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
DATABASE_URL=os.getenv('DATABASE_URL','postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news')
engine=create_engine(DATABASE_URL, future=True)
SessionLocal=sessionmaker(bind=engine, future=True)
