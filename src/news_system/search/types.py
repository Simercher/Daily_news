from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from news_system.db.models import ArticleModel


@dataclass
class SearchQuery:
    raw: str
    must_terms: list[str] = field(default_factory=list)
    should_terms: list[str] = field(default_factory=list)
    must_not_terms: list[str] = field(default_factory=list)
    must_phrases: list[str] = field(default_factory=list)
    should_phrases: list[str] = field(default_factory=list)
    must_not_phrases: list[str] = field(default_factory=list)
    has_explicit_or: bool = False

    @property
    def has_positive_must(self) -> bool:
        return bool(self.must_terms or self.must_phrases)

    @property
    def has_positive_should(self) -> bool:
        return bool(self.should_terms or self.should_phrases)


@dataclass(frozen=True)
class SearchResult:
    article: ArticleModel
    score: int
    matched_fields: list[str]
    matched_terms: list[str]
