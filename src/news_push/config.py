from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from news_push.models import FeedSource


DEFAULT_TOP_N = 5
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_TIMEOUT = 15
DEFAULT_CACHE_FILE = "data/sent_cache.json"
DEFAULT_TIMEZONE = "Asia/Shanghai"


def _env_or_value(value: Any, *env_names: str, default: str = "") -> str:
    for env_name in env_names:
        env_value = os.getenv(env_name)
        if env_value:
            return env_value
    if value not in (None, ""):
        return str(value)
    return default


def _load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _resolve_optional_file(base_dir: Path, file_name: str | None, candidates: list[Path]) -> Path | None:
    if file_name:
        custom = Path(file_name)
        if custom.is_absolute():
            return custom if custom.exists() else None
        local_candidates = [
            base_dir / custom,
            base_dir / "config" / custom,
            base_dir / "config" / "custom" / "ai" / custom.name,
        ]
        for path in local_candidates:
            if path.exists():
                return path
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    timeout_seconds: int = DEFAULT_TIMEOUT
    temperature: float = 0.2
    max_tokens: int = 2000
    language: str = "Chinese"


@dataclass(slots=True)
class FilterConfig:
    method: str = "keyword"
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    focus_keywords: list[str] = field(default_factory=list)
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS
    top_n: int = DEFAULT_TOP_N
    priority_sort_enabled: bool = False


@dataclass(slots=True)
class AIInterestConfig:
    enabled: bool = False
    batch_size: int = 50
    batch_interval: int = 2
    min_score: float = 0.7
    interests_file: str = ""
    interests_text: str = ""


@dataclass(slots=True)
class RuntimeConfig:
    cache_file: str = DEFAULT_CACHE_FILE
    request_timeout_seconds: int = DEFAULT_TIMEOUT
    timezone: str = DEFAULT_TIMEZONE


@dataclass(slots=True)
class WeComConfig:
    webhook: str = ""
    msg_type: str = "markdown"
    mentioned_mobile_list: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    feeds: list[FeedSource]
    filters: FilterConfig
    runtime: RuntimeConfig
    llm: LLMConfig
    ai_filter: AIInterestConfig
    wecom: WeComConfig

    @classmethod
    def load(cls, config_path: str) -> "AppConfig":
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "rss" in raw or "notification" in raw or "ai" in raw:
            return cls._load_trendradar_compatible(path, raw)
        return cls._load_simple(path, raw)

    @classmethod
    def _load_simple(cls, path: Path, raw: dict[str, Any]) -> "AppConfig":
        feeds = [
            FeedSource(
                id=str(feed.get("id", feed["name"])),
                name=feed["name"],
                url=feed["url"],
                category=feed.get("category", "general"),
                tags=list(feed.get("tags", [])),
                max_age_days=feed.get("max_age_days"),
            )
            for feed in raw.get("feeds", [])
            if feed.get("enabled", True)
        ]
        if not feeds:
            raise ValueError("配置文件中至少需要一个启用的 feeds 项。")

        filter_raw = raw.get("filters", {})
        runtime_raw = raw.get("runtime", {})
        llm_raw = raw.get("llm", {})
        wecom_raw = raw.get("wecom", {})

        filters = FilterConfig(
            method=str(filter_raw.get("method", "keyword")),
            include_keywords=list(filter_raw.get("include_keywords", [])),
            exclude_keywords=list(filter_raw.get("exclude_keywords", [])),
            focus_keywords=list(filter_raw.get("focus_keywords", [])),
            lookback_hours=int(filter_raw.get("lookback_hours", DEFAULT_LOOKBACK_HOURS)),
            top_n=int(filter_raw.get("top_n", DEFAULT_TOP_N)),
        )
        runtime = RuntimeConfig(
            cache_file=str(runtime_raw.get("cache_file", DEFAULT_CACHE_FILE)),
            request_timeout_seconds=int(
                runtime_raw.get("request_timeout_seconds", DEFAULT_TIMEOUT)
            ),
            timezone=str(runtime_raw.get("timezone", DEFAULT_TIMEZONE)),
        )
        llm = LLMConfig(
            enabled=bool(llm_raw.get("enabled", False)),
            api_key=_env_or_value(llm_raw.get("api_key"), "AI_API_KEY", "OPENAI_API_KEY"),
            base_url=_env_or_value(
                llm_raw.get("base_url"),
                "AI_API_BASE",
                "OPENAI_BASE_URL",
                default="https://api.openai.com/v1",
            ),
            model=str(llm_raw.get("model", "gpt-4.1-mini")),
            timeout_seconds=int(llm_raw.get("timeout_seconds", DEFAULT_TIMEOUT)),
            temperature=float(llm_raw.get("temperature", 0.2)),
            max_tokens=int(llm_raw.get("max_tokens", 2000)),
            language=str(llm_raw.get("language", "Chinese")),
        )
        ai_filter = AIInterestConfig(
            enabled=filters.method == "ai",
            min_score=float(filter_raw.get("min_score", 0.7)),
        )
        wecom = WeComConfig(
            webhook=_env_or_value(wecom_raw.get("webhook"), "WECOM_WEBHOOK"),
            msg_type=str(wecom_raw.get("msg_type", "markdown")),
            mentioned_mobile_list=list(wecom_raw.get("mentioned_mobile_list", [])),
        )
        return cls(
            feeds=feeds,
            filters=filters,
            runtime=runtime,
            llm=llm,
            ai_filter=ai_filter,
            wecom=wecom,
        )

    @classmethod
    def _load_trendradar_compatible(
        cls,
        path: Path,
        raw: dict[str, Any],
    ) -> "AppConfig":
        base_dir = path.parent
        rss_raw = raw.get("rss", {})
        freshness_raw = rss_raw.get("freshness_filter", {})
        global_max_age_days = int(freshness_raw.get("max_age_days", 1))
        lookback_hours = (
            DEFAULT_LOOKBACK_HOURS
            if global_max_age_days <= 0
            else max(global_max_age_days * 24, 1)
        )

        feeds = [
            FeedSource(
                id=str(feed["id"]),
                name=str(feed["name"]),
                url=str(feed["url"]),
                category="rss",
                tags=[str(feed["id"])],
                max_age_days=feed.get("max_age_days", global_max_age_days),
            )
            for feed in rss_raw.get("feeds", [])
            if feed.get("enabled", True)
        ]
        if not feeds:
            raise ValueError("当前兼容模式至少需要一个启用的 rss.feeds 项。")

        filter_raw = raw.get("filter", {})
        report_raw = raw.get("report", {})
        ai_raw = raw.get("ai", {})
        ai_filter_raw = raw.get("ai_filter", {})
        ai_analysis_raw = raw.get("ai_analysis", {})
        advanced_raw = raw.get("advanced", {})
        advanced_rss = advanced_raw.get("rss", {})
        notification_raw = raw.get("notification", {})
        channels_raw = notification_raw.get("channels", {})
        wework_raw = channels_raw.get("wework", {})
        app_raw = raw.get("app", {})
        storage_raw = raw.get("storage", {})
        local_storage_raw = storage_raw.get("local", {})

        keyword_file = _resolve_optional_file(
            base_dir,
            None,
            [base_dir / "config" / "frequency_words.txt"],
        )
        keyword_lines = _load_lines(keyword_file) if keyword_file else []

        interests_file = _resolve_optional_file(
            base_dir,
            ai_filter_raw.get("interests_file"),
            [base_dir / "config" / "ai_interests.txt"],
        )
        interests_lines = _load_lines(interests_file) if interests_file else []

        max_news_for_analysis = int(ai_analysis_raw.get("max_news_for_analysis", 0))
        report_limit = int(report_raw.get("max_news_per_keyword", 0))
        top_n = report_limit or max_news_for_analysis or DEFAULT_TOP_N

        filters = FilterConfig(
            method=str(filter_raw.get("method", "keyword")),
            include_keywords=keyword_lines,
            exclude_keywords=[],
            focus_keywords=interests_lines if interests_lines else keyword_lines,
            lookback_hours=lookback_hours,
            top_n=max(top_n, 1),
            priority_sort_enabled=bool(filter_raw.get("priority_sort_enabled", False)),
        )
        runtime = RuntimeConfig(
            cache_file=str(
                Path(local_storage_raw.get("data_dir", "output")) / "sent_cache.json"
            ),
            request_timeout_seconds=int(advanced_rss.get("timeout", DEFAULT_TIMEOUT)),
            timezone=str(app_raw.get("timezone", DEFAULT_TIMEZONE)),
        )
        llm = LLMConfig(
            enabled=bool(ai_analysis_raw.get("enabled", False) or filters.method == "ai"),
            api_key=_env_or_value(ai_raw.get("api_key"), "AI_API_KEY", "OPENAI_API_KEY"),
            base_url=_env_or_value(
                ai_raw.get("api_base"),
                "AI_API_BASE",
                "OPENAI_BASE_URL",
                default="https://api.openai.com/v1",
            ),
            model=str(ai_raw.get("model", "openai/gpt-4.1-mini")),
            timeout_seconds=int(ai_raw.get("timeout", DEFAULT_TIMEOUT)),
            temperature=float(ai_raw.get("temperature", 0.2)),
            max_tokens=int(ai_raw.get("max_tokens", 2000)),
            language=str(ai_analysis_raw.get("language", "Chinese")),
        )
        ai_filter = AIInterestConfig(
            enabled=filters.method == "ai",
            batch_size=int(ai_filter_raw.get("batch_size", 50)),
            batch_interval=int(ai_filter_raw.get("batch_interval", 2)),
            min_score=float(ai_filter_raw.get("min_score", 0.7)),
            interests_file=str(interests_file) if interests_file else "",
            interests_text="\n".join(interests_lines),
        )
        wecom = WeComConfig(
            webhook=_env_or_value(wework_raw.get("webhook_url"), "WECOM_WEBHOOK"),
            msg_type=str(wework_raw.get("msg_type", "markdown")),
            mentioned_mobile_list=list(wework_raw.get("mentioned_mobile_list", [])),
        )
        return cls(
            feeds=feeds,
            filters=filters,
            runtime=runtime,
            llm=llm,
            ai_filter=ai_filter,
            wecom=wecom,
        )
