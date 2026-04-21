from __future__ import annotations

import hashlib
import json
from pathlib import Path


class SentCache:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = self._load()

    def _load(self) -> dict[str, bool]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(self._items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def contains(self, value: str) -> bool:
        return self._hash(value) in self._items

    def add_many(self, values: list[str]) -> None:
        for value in values:
            self._items[self._hash(value)] = True
        self._save()
