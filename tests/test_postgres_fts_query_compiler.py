from sqlalchemy import column
from sqlalchemy.dialects import postgresql

from news_system.search.postgres_fts import (
    build_fts_filter_expression,
    build_rank_expression,
    compile_postgres_fts_query,
)
from news_system.search.query_parser import parse_search_query


def compiled(raw: str):
    return compile_postgres_fts_query(parse_search_query(raw))


def test_compile_space_separated_terms_as_required_and_filter():
    query = compiled("taiwan semiconductor")

    assert query.required_tsquery == "'taiwan' & 'semiconductor'"
    assert query.optional_tsquery is None
    assert query.excluded_tsquery is None
    assert query.filter_tsquery == "'taiwan' & 'semiconductor'"
    assert query.rank_tsquery == "'taiwan' & 'semiconductor'"


def test_compile_explicit_or_terms_as_optional_or_filter_when_no_musts():
    query = compiled("taiwan OR tsmc")

    assert query.required_tsquery is None
    assert query.optional_tsquery == "'taiwan' | 'tsmc'"
    assert query.filter_tsquery == "'taiwan' | 'tsmc'"
    assert query.rank_tsquery == "'taiwan' | 'tsmc'"


def test_compile_must_and_negated_term_as_required_and_not_filter():
    query = compiled("taiwan -sports")

    assert query.required_tsquery == "'taiwan'"
    assert query.excluded_tsquery == "'sports'"
    assert query.filter_tsquery == "'taiwan' & !'sports'"
    assert query.rank_tsquery == "'taiwan'"


def test_compile_phrase_as_adjacency_tsquery():
    query = compiled('"south china sea"')

    assert query.required_tsquery == "'south' <-> 'china' <-> 'sea'"
    assert query.filter_tsquery == "'south' <-> 'china' <-> 'sea'"


def test_compile_negated_phrase_parenthesizes_not_phrase():
    query = compiled('-"south china sea"')

    assert query.required_tsquery is None
    assert query.excluded_tsquery == "'south' <-> 'china' <-> 'sea'"
    assert query.filter_tsquery == "!('south' <-> 'china' <-> 'sea')"
    assert query.rank_tsquery is None


def test_compile_mixed_phase_one_shape_keeps_should_terms_out_of_filter_when_must_exists():
    query = compiled('"south china sea" taiwan OR tsmc -sports')

    assert query.required_tsquery == "('taiwan') & ('south' <-> 'china' <-> 'sea')"
    assert query.optional_tsquery == "'tsmc'"
    assert query.excluded_tsquery == "'sports'"
    assert query.filter_tsquery == "(('taiwan') & ('south' <-> 'china' <-> 'sea')) & !'sports'"
    assert query.rank_tsquery == "(('taiwan') & ('south' <-> 'china' <-> 'sea')) | ('tsmc')"


def test_compile_special_characters_deterministically_as_fts_lexemes():
    query = compiled("AI/ML 'quoted' C++")

    assert query.required_tsquery == "'ai' & 'ml' & 'quoted' & 'c'"
    assert query.filter_tsquery == "'ai' & 'ml' & 'quoted' & 'c'"


def test_build_fts_filter_expression_uses_compiled_filter_tsquery():
    query = compiled("taiwan OR tsmc")
    expression = build_fts_filter_expression(column("search_vector"), query)

    assert expression is not None
    compiled_expression = expression.compile(dialect=postgresql.dialect())

    assert str(compiled_expression) == "search_vector @@ to_tsquery(%(to_tsquery_1)s, %(to_tsquery_2)s)"
    assert compiled_expression.params == {
        "to_tsquery_1": "simple",
        "to_tsquery_2": "'taiwan' | 'tsmc'",
    }


def test_build_rank_expression_scales_ts_rank_cd_to_integer_contract():
    query = compiled("taiwan OR tsmc")
    expression = build_rank_expression(column("search_vector"), query)

    compiled_expression = expression.compile(dialect=postgresql.dialect())

    assert str(compiled_expression) == (
        "CAST(round(ts_rank_cd(search_vector, to_tsquery(%(to_tsquery_1)s, %(to_tsquery_2)s)) * %(ts_rank_cd_1)s) AS INTEGER)"
    )
    assert compiled_expression.params == {
        "to_tsquery_1": "simple",
        "to_tsquery_2": "'taiwan' | 'tsmc'",
        "ts_rank_cd_1": 1_000_000,
    }
