from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Integer, cast, func, literal
from sqlalchemy.sql.elements import ColumnElement

from news_system.search.types import SearchQuery

DEFAULT_TS_CONFIG = "simple"
DEFAULT_RANK_SCALE = 1_000_000
_LEXEME_RE = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True)
class PostgresFTSQuery:
    config: str
    required_tsquery: str | None
    optional_tsquery: str | None
    excluded_tsquery: str | None
    filter_tsquery: str | None
    rank_tsquery: str | None


def _lexemes(value: str) -> list[str]:
    return [match.group(0).lower() for match in _LEXEME_RE.finditer(value)]


def _quote_lexeme(lexeme: str) -> str:
    return "'" + lexeme.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _term_clauses(terms: list[str]) -> list[str]:
    clauses: list[str] = []
    for term in terms:
        clauses.extend(_quote_lexeme(lexeme) for lexeme in _lexemes(term))
    return clauses


def _phrase_clause(phrase: str) -> str | None:
    lexemes = _lexemes(phrase)
    if not lexemes:
        return None
    return " <-> ".join(_quote_lexeme(lexeme) for lexeme in lexemes)


def _phrase_clauses(phrases: list[str]) -> list[str]:
    return [clause for phrase in phrases if (clause := _phrase_clause(phrase)) is not None]


def _join(clauses: list[str], operator: str) -> str | None:
    if not clauses:
        return None
    return f" {operator} ".join(clauses)


def _compile_positive(terms: list[str], phrases: list[str], operator: str) -> str | None:
    term_query = _join(_term_clauses(terms), operator)
    phrase_query = _join(_phrase_clauses(phrases), operator)
    if term_query and phrase_query:
        return f"({term_query}) {operator} ({phrase_query})"
    return term_query or phrase_query


def _compile_required(query: SearchQuery) -> str | None:
    return _compile_positive(query.must_terms, query.must_phrases, "&")


def _compile_optional(query: SearchQuery) -> str | None:
    return _compile_positive(query.should_terms, query.should_phrases, "|")


def _compile_excluded(query: SearchQuery) -> str | None:
    return _compile_positive(query.must_not_terms, query.must_not_phrases, "|")


def _needs_parentheses(tsquery: str) -> bool:
    return " & " in tsquery or " | " in tsquery


def _negate(tsquery: str) -> str:
    if " <-> " in tsquery or _needs_parentheses(tsquery):
        return f"!({tsquery})"
    return f"!{tsquery}"


def _build_filter(required: str | None, optional: str | None, excluded: str | None) -> str | None:
    positive_filter = required or optional
    if positive_filter and excluded:
        left = f"({positive_filter})" if _needs_parentheses(positive_filter) else positive_filter
        return f"{left} & {_negate(excluded)}"
    if excluded:
        return _negate(excluded)
    return positive_filter


def _build_rank(required: str | None, optional: str | None) -> str | None:
    if required and optional:
        return f"({required}) | ({optional})"
    return required or optional


def compile_postgres_fts_query(query: SearchQuery, *, config: str = DEFAULT_TS_CONFIG) -> PostgresFTSQuery:
    required = _compile_required(query)
    optional = _compile_optional(query)
    excluded = _compile_excluded(query)
    return PostgresFTSQuery(
        config=config,
        required_tsquery=required,
        optional_tsquery=optional,
        excluded_tsquery=excluded,
        filter_tsquery=_build_filter(required, optional, excluded),
        rank_tsquery=_build_rank(required, optional),
    )


def build_fts_filter_expression(search_vector: ColumnElement, query: PostgresFTSQuery) -> ColumnElement[bool] | None:
    if query.filter_tsquery is None:
        return None
    return search_vector.op("@@")(func.to_tsquery(query.config, query.filter_tsquery))


def build_rank_expression(
    search_vector: ColumnElement,
    query: PostgresFTSQuery,
    *,
    scale: int = DEFAULT_RANK_SCALE,
) -> ColumnElement[int]:
    if query.rank_tsquery is None:
        return cast(literal(0), Integer)
    rank = func.ts_rank_cd(search_vector, func.to_tsquery(query.config, query.rank_tsquery))
    return cast(func.round(rank * scale), Integer)
