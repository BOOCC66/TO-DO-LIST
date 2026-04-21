from __future__ import annotations

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from news_push.models import AnalyzedNewsItem, DigestNarrative


def build_markdown_message(
    narrative: DigestNarrative,
    items: list[AnalyzedNewsItem],
    timezone_name: str = "Asia/Shanghai",
) -> str:
    lines = [
        f"# {narrative.headline}",
        "",
        f"> {narrative.summary}",
        "",
    ]
    if narrative.action_points:
        lines.append("**建议动作**")
        for point in narrative.action_points:
            lines.append(f"> - {point}")
        lines.append("")

    lines.append("**新闻清单**")
    zone = _resolve_timezone(timezone_name)
    for idx, entry in enumerate(items, start=1):
        published = (
            entry.item.published_at.astimezone(zone).strftime("%m-%d %H:%M")
            if entry.item.published_at
            else "未知时间"
        )
        reasons = "；".join(entry.reasons[:3]) if entry.reasons else "规则命中"
        lines.extend(
            [
                f"{idx}. [{entry.item.title}]({entry.item.link})",
                f"> 来源: {entry.item.source} | 时间: {published} | 评分: {entry.score:.1f}",
                f"> 判断: {reasons}",
                f"> 摘要: {entry.brief}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _resolve_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Shanghai":
            return timezone(timedelta(hours=8))
        return timezone.utc
