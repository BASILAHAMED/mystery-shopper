"""Deterministic replay cache for Tavily search results, keyed by ticket context."""
from __future__ import annotations

import json
from pathlib import Path


class TavilyCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self._data: dict[str, dict] = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._data = {}

    @staticmethod
    def _key_str(key: tuple) -> str:
        return json.dumps(list(key), ensure_ascii=False)

    def get(self, key: tuple) -> dict | None:
        return self._data.get(self._key_str(key))

    def put(self, key: tuple, value: dict) -> None:
        self._data[self._key_str(key)] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
