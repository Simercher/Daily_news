from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from news_system.db.session import SessionLocal
from news_system.db.models import EventModel, ArticleModel, EventArticle

app=FastAPI(title='Daily_news')

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

@app.get('/events/daily')
def daily(date: str, limit: int=10, db: Session=Depends(get_db)):
    start=datetime.fromisoformat(date).replace(tzinfo=timezone.utc); end=start+timedelta(days=1)
    return db.query(EventModel).filter(EventModel.event_date>=start, EventModel.event_date<end).order_by(EventModel.final_score.desc()).limit(limit).all()

@app.get('/events/breaking')
def breaking(since_minutes: int=180, limit: int=20, db: Session=Depends(get_db)):
    since=datetime.now(timezone.utc)-timedelta(minutes=since_minutes)
    return db.query(EventModel).filter(EventModel.is_breaking==True, EventModel.created_at>=since).order_by(EventModel.final_score.desc()).limit(limit).all()

@app.get('/events/{event_id}')
def event_detail(event_id: int, db: Session=Depends(get_db)):
    ev=db.get(EventModel,event_id)
    links=db.query(EventArticle).filter_by(event_id=event_id).all()
    articles=[db.get(ArticleModel,l.article_id) for l in links]
    return {'event': ev, 'articles': articles}
