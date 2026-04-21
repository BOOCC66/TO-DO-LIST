from __future__ import annotations

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from news_push.models import AnalyzedNewsItem, DigestNarrative

MAX_MARKDOWN_BYTES = 3600
MAX_SUMMARY_LENGTH = 160
MAX_ACTION_POINT_LENGTH = 48
MAX_TITLE_LENGTH = 48
MAX_REASON_LENGTH = 48
MAX_BRIEF_LENGTH = 72


def build_markdown_message(
    narrative: DigestNarrative,
    items: list[AnalyzedNewsItem],
    timezone_name: str = "Asia/Shanghai",
) -> str:
    lines = [
        f"# {narrative.headline}",
        "",
        f"> {_truncate(narrative.summary, MAX_SUMMARY_LENGTH)}",
        "",
    ]
    if narrative.action_points:
        lines.append("**建议动作**")
        for point in narrative.action_points[:3]:
            lines.append(f"> - {_truncate(point, MAX_ACTION_POINT_LENGTH)}")
        lines.append("")

    lines.append("**新闻清单**")
    zone = _resolve_timezone(timezone_name)
    included_blocks: list[str] = []
    omitted_count = 0

    for idx, entry in enumerate(items, start=1):
        published = (
            entry.item.published_at.astimezone(zone).strftime("%m-%d %H:%M")
            if entry.item.published_at
            else "未知时间"
        )
        reasons = "；".join(entry.reasons[:3]) if entry.reasons else "规则命中"
        block = "\n".join(
            [
                f"{idx}. [{_truncate(entry.item.title, MAX_TITLE_LENGTH)}]({entry.item.link})",
                f"> 来源: {entry.item.source} | 时间: {published} | 评分: {entry.score:.1f}",
                f"> 判断: {_truncate(reasons, MAX_REASON_LENGTH)}",
                f"> 摘要: {_truncate(entry.brief, MAX_BRIEF_LENGTH)}",
                "",
            ]
        )
        candidate = "\n".join(lines + included_blocks + [block]).strip()
        remaining = len(items) - idx
        footer = (
            "\n\n"
            f"> 其余 {remaining} 条因企业微信长度限制已省略，可在终端查看完整结果。"
            if remaining > 0
            else ""
        )
        if _utf8_len(candidate + footer) > MAX_MARKDOWN_BYTES:
            omitted_count += 1
            continue
        included_blocks.append(block)

    if omitted_count:
        included_blocks.append(
            f"> 其余 {omitted_count} 条因企业微信长度限制已省略，可在终端查看完整结果。"
        )

    return "\n".join(lines + included_blocks).strip()


def _truncate(text: str, max_length: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 1].rstrip() + "…"


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _resolve_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Shanghai":
            return timezone(timedelta(hours=8))
        return timezone.utc
