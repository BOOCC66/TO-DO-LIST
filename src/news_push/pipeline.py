from __future__ import annotations

import argparse
import sys
import time

from news_push.analyzer import LLMNarrativeBuilder, filter_items, rank_items
from news_push.config import AppConfig
from news_push.fetcher import NewsFetcher
from news_push.formatter import build_markdown_message
from news_push.models import RunResult
from news_push.storage import SentCache
from news_push.wecom import WeComRobotClient


def run_once(config_path: str, dry_run: bool = False, print_only: bool = False) -> RunResult:
    config = AppConfig.load(config_path)
    fetcher = NewsFetcher(timeout_seconds=config.runtime.request_timeout_seconds)
    cache = SentCache(config.runtime.cache_file)

    fetched = fetcher.fetch_all(config.feeds)
    filtered = filter_items(fetched, config)
    candidates = [item for item in filtered if not cache.contains(item.dedupe_key)]
    ranked = rank_items(candidates, config)
    narrative = LLMNarrativeBuilder(config.llm).build(ranked)
    message = build_markdown_message(
        narrative,
        ranked,
        timezone_name=config.runtime.timezone,
    )

    if ranked and not dry_run and not print_only:
        client = WeComRobotClient(config.wecom, config.runtime.request_timeout_seconds)
        client.send(message)
        cache.add_many([entry.item.dedupe_key for entry in ranked])

    return RunResult(
        fetched_count=len(fetched),
        candidate_count=len(candidates),
        selected_count=len(ranked),
        sent_count=len(ranked) if ranked and not dry_run and not print_only else 0,
        message=message,
        narrative=narrative,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="新闻抓取、筛选分析并推送到企业微信。")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径，默认 config.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只跑流程，不发送到企业微信。",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="打印 markdown 消息并退出。",
    )
    parser.add_argument(
        "--loop-minutes",
        type=int,
        default=0,
        help="循环运行的分钟间隔，0 表示只运行一次。",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    while True:
        try:
            result = run_once(
                config_path=args.config,
                dry_run=args.dry_run,
                print_only=args.print_only,
            )
            print(
                (
                    f"[INFO] 抓取 {result.fetched_count} 条，候选 {result.candidate_count} 条，"
                    f"入选 {result.selected_count} 条，发送 {result.sent_count} 条。"
                )
            )
            _safe_print(result.message)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 执行失败: {exc}")
            if args.loop_minutes <= 0:
                return 1

        if args.loop_minutes <= 0:
            return 0

        print(f"[INFO] {args.loop_minutes} 分钟后继续下一轮...")
        time.sleep(args.loop_minutes * 60)


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text)
