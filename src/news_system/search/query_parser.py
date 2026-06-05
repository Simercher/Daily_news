from __future__ import annotations

from dataclasses import dataclass

from news_system.search.types import SearchQuery


class SearchQueryError(ValueError):
    """Raised when the user search query cannot be parsed."""


@dataclass(frozen=True)
class _Token:
    value: str
    is_phrase: bool = False
    is_negated: bool = False
    is_or: bool = False


def _normalize(value: str) -> str:
    return value.strip().lower()


def _tokenize(raw: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    length = len(raw)
    while i < length:
        while i < length and raw[i].isspace():
            i += 1
        if i >= length:
            break

        is_negated = False
        if raw[i] == "-":
            is_negated = True
            i += 1
            if i >= length or raw[i].isspace():
                raise SearchQueryError("negation must be followed by a term or phrase")

        if raw[i] == '"':
            i += 1
            start = i
            while i < length and raw[i] != '"':
                i += 1
            if i >= length:
                raise SearchQueryError("unmatched quote in query")
            value = _normalize(raw[start:i])
            i += 1
            if not value:
                raise SearchQueryError("phrase must not be blank")
            tokens.append(_Token(value=value, is_phrase=True, is_negated=is_negated))
            continue

        start = i
        while i < length and not raw[i].isspace():
            if raw[i] == '"':
                raise SearchQueryError("unmatched quote in query")
            i += 1
        value = _normalize(raw[start:i])
        if not value:
            continue
        if is_negated and value.upper() == "OR":
            raise SearchQueryError("negation must be followed by a term or phrase")
        if not is_negated and value.upper() == "OR":
            tokens.append(_Token(value="or", is_or=True))
        else:
            tokens.append(_Token(value=value, is_negated=is_negated))
    return tokens


def _append(query: SearchQuery, token: _Token, *, should: bool) -> None:
    if token.is_negated:
        if token.is_phrase:
            query.must_not_phrases.append(token.value)
        else:
            query.must_not_terms.append(token.value)
    elif should:
        if token.is_phrase:
            query.should_phrases.append(token.value)
        else:
            query.should_terms.append(token.value)
    else:
        if token.is_phrase:
            query.must_phrases.append(token.value)
        else:
            query.must_terms.append(token.value)


def parse_search_query(raw: str) -> SearchQuery:
    if not raw.strip():
        raise SearchQueryError("query must not be blank")

    tokens = _tokenize(raw)
    if not tokens:
        raise SearchQueryError("query must not be blank")
    if tokens[0].is_or or tokens[-1].is_or:
        raise SearchQueryError("OR must separate search terms")
    for left, right in zip(tokens, tokens[1:]):
        if left.is_or and right.is_or:
            raise SearchQueryError("OR must separate search terms")

    query = SearchQuery(raw=raw)
    pending_or = False
    positive_must_seen = False

    for idx, token in enumerate(tokens):
        if token.is_or:
            query.has_explicit_or = True
            pending_or = True
            continue

        next_is_or = idx + 1 < len(tokens) and tokens[idx + 1].is_or
        leading_or_branch = next_is_or and not positive_must_seen and not query.has_positive_should
        should = (pending_or or leading_or_branch) and not token.is_negated
        _append(query, token, should=should)
        if not token.is_negated and not should:
            positive_must_seen = True
        pending_or = False

    if not (
        query.must_terms
        or query.should_terms
        or query.must_not_terms
        or query.must_phrases
        or query.should_phrases
        or query.must_not_phrases
    ):
        raise SearchQueryError("query must not be blank")
    return query
