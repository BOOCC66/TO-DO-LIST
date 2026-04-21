from __future__ import annotations

from datetime import datetime, timezone
import json
import time

import requests

from news_push.config import AIInterestConfig, AppConfig, LLMConfig
from news_push.fetcher import host_from_link, is_recent
from news_push.models import AnalyzedNewsItem, DigestNarrative, NewsItem


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _matches_any(text: str, keywords: list[str]) -> bool:
    normalized = _normalize(text)
    return any(keyword.lower() in normalized for keyword in keywords)


def filter_items(items: list[NewsItem], config: AppConfig) -> list[NewsItem]:
    recent_items = [item for item in items if is_recent(item, config.filters.lookback_hours)]
    if config.filters.method == "ai":
        filtered = AIRelevanceFilter(config.llm, config.ai_filter).filter(recent_items)
        if filtered:
            return filtered
    return _filter_items_by_keywords(recent_items, config)


def _filter_items_by_keywords(items: list[NewsItem], config: AppConfig) -> list[NewsItem]:
    results: list[NewsItem] = []
    for item in items:
        haystack = " ".join([item.title, item.summary, " ".join(item.tags)])
        if config.filters.include_keywords and not _matches_any(
            haystack, config.filters.include_keywords
        ):
            continue
        if config.filters.exclude_keywords and _matches_any(
            haystack, config.filters.exclude_keywords
        ):
            continue
        results.append(item)
    return results


def score_item(item: NewsItem, focus_keywords: list[str]) -> AnalyzedNewsItem:
    haystack = " ".join([item.title, item.summary, item.category, " ".join(item.tags)])
    normalized = _normalize(haystack)
    score = 10.0
    reasons: list[str] = []

    for keyword in focus_keywords:
        if keyword.lower() in normalized:
            score += 8
            reasons.append(f"命中重点关键词: {keyword}")

    if item.published_at:
        hours_ago = (datetime.now(timezone.utc) - item.published_at).total_seconds() / 3600
        if hours_ago <= 3:
            score += 6
            reasons.append("发布时间较近")
        elif hours_ago <= 12:
            score += 3
            reasons.append("属于当日热点")

    if len(item.summary) >= 120:
        score += 2
        reasons.append("信息密度较高")

    if item.category and item.category != "general":
        score += 1
        reasons.append(f"分类相关: {item.category}")

    brief = item.summary[:160].strip()
    if not brief:
        brief = f"来源 {host_from_link(item.link)}，适合进一步跟踪。"

    return AnalyzedNewsItem(item=item, score=score, reasons=reasons, brief=brief)


def rank_items(items: list[NewsItem], config: AppConfig) -> list[AnalyzedNewsItem]:
    ranked = [score_item(item, config.filters.focus_keywords) for item in items]
    ranked.sort(
        key=lambda entry: (
            entry.score,
            entry.item.published_at.timestamp() if entry.item.published_at else 0,
        ),
        reverse=True,
    )
    return ranked[: config.filters.top_n]


def build_rule_based_narrative(items: list[AnalyzedNewsItem]) -> DigestNarrative:
    if not items:
        return DigestNarrative(
            headline="本轮没有符合条件的新闻",
            summary="未发现命中筛选条件且值得推送的新增内容。",
            action_points=["可以放宽筛选条件，或增加新的 RSS 数据源。"],
        )

    focus_tags: list[str] = []
    for entry in items:
        focus_tags.extend(entry.item.tags)
    unique_tags = list(dict.fromkeys(tag for tag in focus_tags if tag))

    headline = f"筛选出 {len(items)} 条值得关注的新闻"
    summary = "；".join(
        [
            f"{idx}. {entry.item.title}"
            for idx, entry in enumerate(items[:3], start=1)
        ]
    )
    action_points = [
        "优先阅读前 3 条高分新闻，确认是否需要单独二次解读。",
        "如果你要做行业情报，可以把重点词继续细分成公司、产品、政策三组。",
    ]
    if unique_tags:
        action_points.insert(0, f"本轮关注标签: {', '.join(unique_tags[:6])}")
    return DigestNarrative(headline=headline, summary=summary, action_points=action_points)


class LLMNarrativeBuilder:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def build(self, items: list[AnalyzedNewsItem]) -> DigestNarrative:
        if not self.config.enabled or not self.config.api_key:
            return build_rule_based_narrative(items)

        prompt_lines = []
        for idx, entry in enumerate(items, start=1):
            published = (
                entry.item.published_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if entry.item.published_at
                else "未知时间"
            )
            prompt_lines.append(
                f"{idx}. 标题: {entry.item.title}\n"
                f"摘要: {entry.brief}\n"
                f"来源: {entry.item.source}\n"
                f"时间: {published}\n"
                f"分数: {entry.score}\n"
                f"理由: {'; '.join(entry.reasons) or '无'}"
            )

        payload = {
            "model": self._provider_model_name(self.config.model),
            "temperature": self.config.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"你是新闻分析助手，请使用 {self.config.language} 输出 JSON，"
                        "包含 headline、summary、action_points。"
                        "summary 控制在 120 字以内，action_points 为 2 到 3 条短句。"
                    ),
                },
                {"role": "user", "content": "\n\n".join(prompt_lines)},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.config.max_tokens > 0:
            payload["max_tokens"] = self.config.max_tokens

        try:
            data = _post_chat_completion(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                timeout_seconds=self.config.timeout_seconds,
                payload=payload,
            )
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return DigestNarrative(
                headline=str(parsed.get("headline", "")) or "本轮新闻分析",
                summary=str(parsed.get("summary", "")) or "已完成新闻摘要。",
                action_points=list(parsed.get("action_points", [])),
            )
        except (requests.RequestException, KeyError, ValueError, TypeError):
            return build_rule_based_narrative(items)

    @staticmethod
    def _provider_model_name(model: str) -> str:
        if "/" not in model:
            return model
        return model.split("/", 1)[1]


class AIRelevanceFilter:
    def __init__(self, llm_config: LLMConfig, ai_filter: AIInterestConfig) -> None:
        self.llm_config = llm_config
        self.ai_filter = ai_filter

    def filter(self, items: list[NewsItem]) -> list[NewsItem]:
        if (
            not self.ai_filter.enabled
            or not self.llm_config.enabled
            or not self.llm_config.api_key
            or not self.ai_filter.interests_text.strip()
        ):
            return []

        kept: list[NewsItem] = []
        batch_size = max(self.ai_filter.batch_size, 1)
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            decisions = self._score_batch(batch)
            for index, score, reason in decisions:
                if 0 <= index < len(batch) and score >= self.ai_filter.min_score:
                    item = batch[index]
                    if reason:
                        item.tags.append(reason)
                    kept.append(item)
            if start + batch_size < len(items) and self.ai_filter.batch_interval > 0:
                time.sleep(self.ai_filter.batch_interval)
        return kept

    def _score_batch(self, items: list[NewsItem]) -> list[tuple[int, float, str]]:
        prompt_lines = []
        for idx, item in enumerate(items):
            prompt_lines.append(
                f"{idx}. 标题: {item.title}\n摘要: {item.summary[:180]}\n来源: {item.source}"
            )
        payload = {
            "model": LLMNarrativeBuilder._provider_model_name(self.llm_config.model),
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是新闻兴趣分类助手。基于给定兴趣描述，为每条新闻打 0 到 1 的相关性分数，"
                        "并返回 JSON 对象，格式为 {\"items\":[{\"index\":0,\"score\":0.82,\"reason\":\"AI基础设施\"}]}。"
                        "只返回 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"兴趣描述:\n{self.ai_filter.interests_text}\n\n"
                        f"待分类新闻:\n{'\n\n'.join(prompt_lines)}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        if self.llm_config.max_tokens > 0:
            payload["max_tokens"] = self.llm_config.max_tokens

        try:
            data = _post_chat_completion(
                base_url=self.llm_config.base_url,
                api_key=self.llm_config.api_key,
                timeout_seconds=self.llm_config.timeout_seconds,
                payload=payload,
            )
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            results = []
            for item in parsed.get("items", []):
                results.append(
                    (
                        int(item.get("index", -1)),
                        float(item.get("score", 0)),
                        str(item.get("reason", "")).strip(),
                    )
                )
            return results
        except (requests.RequestException, KeyError, ValueError, TypeError):
            return []


def _post_chat_completion(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    payload: dict[str, object],
) -> dict[str, object]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()
