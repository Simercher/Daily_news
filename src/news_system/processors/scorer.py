from math import log1p

def score_event(event):
    sources={getattr(a,'source_name',None) or getattr(a,'source_id',None) for a in event.articles}
    event.velocity_score=min(1.0, len(event.articles)/10.0)
    event.source_diversity_score=min(1.0, len(sources)/5.0)
    severe={"war","earthquake","attack","crash","死","地震","爆炸","attack"}
    text=(event.title+' '+' '.join(event.keywords)).lower()
    event.severity_score=1.0 if any(k in text for k in severe) else min(0.6, log1p(len(event.articles))/3)
    event.final_score=round(0.4*event.velocity_score+0.3*event.source_diversity_score+0.3*event.severity_score,4)
    return event
