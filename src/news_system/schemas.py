from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class Article(BaseModel):
    source_id: str | None = None
    source_type: str = "rss"
    source_name: str | None = None
    source_domain: str | None = None
    title: str
    url: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    author: str | None = None
    description: str | None = None
    content: str | None = None
    image_url: str | None = None
    language: str | None = None
    country: str | None = None
    category: str | None = None
    raw: dict = Field(default_factory=dict)
    normalized_title: str | None = None
    canonical_url: str | None = None
    url_hash: str | None = None
    is_duplicate: bool = False
    duplicate_of_id: int | None = None
    entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    def ensure_utc(self) -> "Article":
        if self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        else:
            self.published_at = self.published_at.astimezone(timezone.utc)
        return self
