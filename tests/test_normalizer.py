from news_system.processors.normalizer import canonicalize_url, normalize_title, to_utc

def test_canonicalize_removes_tracking():
    assert canonicalize_url('HTTP://www.Example.com/a/?utm_source=x&b=1#frag') == 'http://example.com/a?b=1'

def test_normalize_title_suffix_fullwidth():
    assert normalize_title('  ＢＲＥＡＫＩＮＧ:  Big   News - Reuters ') == 'breaking big news'

def test_to_utc_naive():
    assert to_utc('2026-01-01T00:00:00').tzinfo is not None
