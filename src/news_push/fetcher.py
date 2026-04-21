from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests

from news_push.models import FeedSource, NewsItem


def _strip_html(value: str) -> str:
    text = value or ""
    fragments: list[str] = []
    inside_tag = False
    for char in text:
        if char == "<":
            inside_tag = True
            continue
        if char == ">":
            inside_tag = False
            continue
        if not inside_tag:
            fragments.append(char)
    return " ".join(unescape("".join(fragments)).split())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None


def _child_text(element: ET.Element, names: list[str]) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _iter_rss_items(root: ET.Element, source: FeedSource) -> Iterable[NewsItem]:
    channel = root.find("channel")
    if channel is None:
        return []
    items = channel.findall("item")
    results: list[NewsItem] = []
    for item in items:
        title = _child_text(item, ["title"])
        link = _child_text(item, ["link"])
        summary = _child_text(item, ["description", "summary"])
        published = _parse_datetime(_child_text(item, ["pubDate"]))
        if not title or not link:
            continue
        results.append(
            NewsItem(
                source=source.name,
                source_id=source.id,
                title=title,
                link=link,
                summary=_strip_html(summary),
                published_at=published,
                category=source.category,
                tags=source.tags.copy(),
                source_max_age_days=source.max_age_days,
            )
        )
    return results


def _iter_atom_items(root: ET.Element, source: FeedSource) -> Iterable[NewsItem]:
    namespace = "{http://www.w3.org/2005/Atom}"
    items = root.findall(f"{namespace}entry")
    results: list[NewsItem] = []
    for item in items:
        title = _child_text(item, [f"{namespace}title"])
        summary = _child_text(item, [f"{namespace}summary", f"{namespace}content"])
        published = _parse_datetime(
            _child_text(item, [f"{namespace}published", f"{namespace}updated"])
        )
        link = ""
        for link_node in item.findall(f"{namespace}link"):
            href = link_node.attrib.get("href", "").strip()
            rel = link_node.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                link = href
                break
        if not link:
            link = _child_text(item, [f"{namespace}id"])
        if not title or not link:
            continue
        results.append(
            NewsItem(
                source=source.name,
                source_id=source.id,
                title=title,
                link=link,
                summary=_strip_html(summary),
                published_at=published,
                category=source.category,
                tags=source.tags.copy(),
                source_max_age_days=source.max_age_days,
            )
        )
    return results


class NewsFetcher:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) CodexNewsPush/1.0"
                )
            }
        )

    def fetch(self, source: FeedSource) -> list[NewsItem]:
        response = self.session.get(source.url, timeout=self.timeout_seconds)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        tag = root.tag.lower()
        if tag.endswith("rss"):
            return list(_iter_rss_items(root, source))
        if tag.endswith("feed"):
            return list(_iter_atom_items(root, source))
        raise ValueError(f"暂不支持的 feed 格式: {source.url}")

    def fetch_all(self, sources: list[FeedSource]) -> list[NewsItem]:
        results: list[NewsItem] = []
        for source in sources:
            try:
                results.extend(self.fetch(source))
            except requests.RequestException as exc:
                print(f"[WARN] 拉取失败 {source.name}: {exc}")
            except ET.ParseError as exc:
                print(f"[WARN] 解析失败 {source.name}: {exc}")
            except ValueError as exc:
                print(f"[WARN] 跳过 {source.name}: {exc}")
        return results


def is_recent(item: NewsItem, lookback_hours: int) -> bool:
    if item.published_at is None:
        return True
    if item.source_max_age_days is not None:
        if int(item.source_max_age_days) <= 0:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(item.source_max_age_days))
        return item.published_at >= cutoff
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    return item.published_at >= cutoff


def host_from_link(link: str) -> str:
    parsed = urlparse(link)
    return parsed.netloc or link
