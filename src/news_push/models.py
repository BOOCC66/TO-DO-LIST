from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class FeedSource:
    id: str
    name: str
    url: str
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    max_age_days: int | None = None


@dataclass(slots=True)
class NewsItem:
    source: str
    title: str
    link: str
    summary: str
    published_at: datetime | None
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    source_id: str = ""
    source_max_age_days: int | None = None

    @property
    def dedupe_key(self) -> str:
        timestamp = self.published_at.isoformat() if self.published_at else ""
        return "|".join([self.source, self.title.strip(), self.link.strip(), timestamp])


@dataclass(slots=True)
class AnalyzedNewsItem:
    item: NewsItem
    score: float
    reasons: list[str] = field(default_factory=list)
    brief: str = ""


@dataclass(slots=True)
class DigestNarrative:
    headline: str
    summary: str
    action_points: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunResult:
    fetched_count: int
    candidate_count: int
    selected_count: int
    sent_count: int
    message: str
    narrative: DigestNarrative
