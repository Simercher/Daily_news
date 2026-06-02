from .scorer import score_event

def is_breaking(event):
    score_event(event)
    if event.severity_score >= 0.9 and len(event.articles) >= 2:
        return True
    return event.final_score >= 0.7 and event.velocity_score >= 0.3 and event.source_diversity_score >= 0.4

def breaking_events(events):
    return [e for e in events if is_breaking(e)]
