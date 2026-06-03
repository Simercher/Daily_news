from .scorer import score_event, _severity_keyword_score

def is_breaking(event):
    score_event(event)
    # New scoring formula checks
    # severity_keyword_score >= 0.5 means at least one severity keyword matched (e.g., "earthquake")
    sev_kw = _severity_keyword_score(event.articles)
    if sev_kw >= 0.5 and len(event.articles) >= 2:
        return True
    return event.final_score >= 0.3 and event.velocity_score >= 0.1 and event.source_diversity_score >= 0.1

def breaking_events(events):
    return [e for e in events if is_breaking(e)]