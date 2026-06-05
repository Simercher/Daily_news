from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import case, func, literal, or_
from sqlalchemy.sql.elements import ColumnElement

from news_system.db.models import ArticleModel
from news_system.search.types import SearchQuery

SEARCH_FIELDS = (
    ("title", ArticleModel.title, 5, 8),
    ("description", ArticleModel.description, 3, 5),
    ("content_snippet", ArticleModel.content_snippet, 2, 4),
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_expr(column, term: str) -> ColumnElement[bool]:
    pattern = f"%{_escape_like(term.lower())}%"
    return func.lower(func.coalesce(column, "")).like(pattern, escape="\\")


def article_field_match(term: str) -> ColumnElement[bool]:
    return or_(*(like_expr(column, term) for _, column, _, _ in SEARCH_FIELDS))


def positive_terms(query: SearchQuery) -> list[str]:
    return [*query.must_terms, *query.should_terms]


def positive_phrases(query: SearchQuery) -> list[str]:
    return [*query.must_phrases, *query.should_phrases]


def build_filter_expressions(query: SearchQuery) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    for term in [*query.must_terms, *query.must_phrases]:
        filters.append(article_field_match(term))
    for term in [*query.must_not_terms, *query.must_not_phrases]:
        filters.append(~article_field_match(term))

    if not query.has_positive_must and query.has_positive_should:
        should_parts = [*query.should_terms, *query.should_phrases]
        filters.append(or_(*(article_field_match(term) for term in should_parts)))
    return filters


def _score_for_parts(parts: Iterable[str], *, phrase: bool) -> ColumnElement[int]:
    score = literal(0)
    for part in parts:
        for _, column, term_weight, phrase_weight in SEARCH_FIELDS:
            weight = phrase_weight if phrase else term_weight
            score = score + case((like_expr(column, part), weight), else_=0)
    return score


def build_score_expression(query: SearchQuery) -> ColumnElement[int]:
    score = _score_for_parts(positive_terms(query), phrase=False)
    score = score + _score_for_parts(positive_phrases(query), phrase=True)
    for term in query.should_terms:
        score = score + case((article_field_match(term), 2), else_=0)
    for phrase in query.should_phrases:
        score = score + case((article_field_match(phrase), 3), else_=0)
    return score


def _field_text(article: ArticleModel, field_name: str) -> str:
    return (getattr(article, field_name) or "").lower()


def _matches(article: ArticleModel, part: str, field_name: str) -> bool:
    return part.lower() in _field_text(article, field_name)


def compute_python_match_metadata(article: ArticleModel, query: SearchQuery) -> tuple[int, list[str], list[str]]:
    score = 0
    matched_fields: list[str] = []
    matched_terms: list[str] = []

    field_names = [field_name for field_name, _, _, _ in SEARCH_FIELDS]
    parts_with_phrase_flag: list[tuple[str, bool, bool]] = [
        *((term, False, False) for term in query.must_terms),
        *((term, False, True) for term in query.should_terms),
        *((phrase, True, False) for phrase in query.must_phrases),
        *((phrase, True, True) for phrase in query.should_phrases),
    ]

    for part, is_phrase, is_should in parts_with_phrase_flag:
        part_matched = False
        for field_name, _, term_weight, phrase_weight in SEARCH_FIELDS:
            if _matches(article, part, field_name):
                part_matched = True
                weight = phrase_weight if is_phrase else term_weight
                score += weight
                if field_name not in matched_fields:
                    matched_fields.append(field_name)
        if part_matched:
            if part not in matched_terms:
                matched_terms.append(part)
            if is_should:
                score += 3 if is_phrase else 2

    # Keep output field order stable even if SEARCH_FIELDS is rearranged later.
    matched_fields = [field_name for field_name in field_names if field_name in matched_fields]
    return score, matched_fields, matched_terms
