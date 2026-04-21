from __future__ import annotations

import requests

from news_push.config import WeComConfig


class WeComRobotClient:
    def __init__(self, config: WeComConfig, timeout_seconds: int) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def send(self, content: str) -> None:
        if self.config.msg_type == "text":
            self.send_text(content)
            return
        self.send_markdown(content)

    def send_markdown(self, content: str) -> None:
        if not self.config.webhook:
            raise ValueError("企业微信机器人 webhook 未配置。")
        if self.config.mentioned_mobile_list:
            mentions = " ".join(f"<@{mobile}>" for mobile in self.config.mentioned_mobile_list)
            content = f"{content}\n\n{mentions}".strip()
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        self._post(payload)

    def send_text(self, content: str) -> None:
        if not self.config.webhook:
            raise ValueError("企业微信机器人 webhook 未配置。")
        payload = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_mobile_list": self.config.mentioned_mobile_list,
            },
        }
        self._post(payload)

    def _post(self, payload: dict[str, object]) -> None:
        response = requests.post(
            self.config.webhook,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"企业微信推送失败: {data}")
