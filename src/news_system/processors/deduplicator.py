from datetime import timedelta
from rapidfuzz import fuzz
from .normalizer import canonicalize_url, normalize_title, url_hash

def mark_duplicates(articles):
    seen_hash = {}; kept=[]
    for idx,a in enumerate(articles):
        a.canonical_url = canonicalize_url(a.url); a.url_hash = url_hash(a.url); a.normalized_title = normalize_title(a.title); a.ensure_utc()
        dup = seen_hash.get(a.url_hash)
        if dup is None:
            for j,b in enumerate(kept):
                if abs(a.published_at-b.published_at) <= timedelta(hours=48):
                    if a.normalized_title == b.normalized_title or fuzz.token_set_ratio(a.normalized_title,b.normalized_title) >= 92:
                        dup = j; break
        if dup is not None:
            a.is_duplicate=True; a.duplicate_of_id=dup
        else:
            seen_hash[a.url_hash]=idx; kept.append(a)
    return articles
