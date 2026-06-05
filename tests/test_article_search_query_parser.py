import pytest

from news_system.search.query_parser import SearchQueryError, parse_search_query


def test_parse_space_separated_terms_as_must_and():
    query = parse_search_query("taiwan semiconductor")

    assert query.must_terms == ["taiwan", "semiconductor"]
    assert query.should_terms == []
    assert query.must_not_terms == []
    assert query.must_phrases == []


def test_parse_explicit_or_as_should_terms_when_query_has_no_other_musts():
    query = parse_search_query("taiwan OR tsmc")

    assert query.must_terms == []
    assert query.should_terms == ["taiwan", "tsmc"]
    assert query.has_explicit_or is True


def test_parse_negated_term():
    query = parse_search_query("taiwan -sports")

    assert query.must_terms == ["taiwan"]
    assert query.must_not_terms == ["sports"]


def test_parse_quoted_phrase():
    query = parse_search_query('"south china sea"')

    assert query.must_phrases == ["south china sea"]
    assert query.must_terms == []


def test_parse_negated_quoted_phrase():
    query = parse_search_query('-"south china sea"')

    assert query.must_not_phrases == ["south china sea"]


def test_parse_mixed_phase_one_query_shape():
    query = parse_search_query('"south china sea" taiwan OR tsmc -sports')

    assert query.must_phrases == ["south china sea"]
    assert query.must_terms == ["taiwan"]
    assert query.should_terms == ["tsmc"]
    assert query.must_not_terms == ["sports"]
    assert query.should_phrases == []
    assert query.must_not_phrases == []


@pytest.mark.parametrize("raw, message", [
    ("   ", "query must not be blank"),
    ('"south china sea', "unmatched quote in query"),
    ("OR", "OR must separate search terms"),
    ("taiwan OR", "OR must separate search terms"),
    ("-", "negation must be followed by a term or phrase"),
])
def test_parse_invalid_queries(raw, message):
    with pytest.raises(SearchQueryError, match=message):
        parse_search_query(raw)
