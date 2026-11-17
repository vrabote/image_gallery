"""Результаты публикации и журнал (state/journal.jsonl).

Журнал — основной источник правды: по нему видно, что уже опубликовано,
где ссылка на пост и что пошло не так. Формат JSON Lines: дописываем строку
на каждую попытку, ничего не переписываем.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STATUS_OK = "ok"
STATUS_DRY = "dry-run"
STATUS_MANUAL = "manual"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class PublishResult:
    """Итог публикации одного поста на одной площадке."""

    platform: str
    post_id: str
    status: str
    url: str = ""
    message: str = ""
    mode: str = ""  # api | browser | manual
    post_key: str = ""  # стабильный ключ id поста на площадке
    timestamp: str = field(default_factory=now_iso)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_OK, STATUS_DRY, STATUS_MANUAL)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Journal:
    """Дописываемый журнал публикаций."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: list[PublishResult] = []
        if self.path.exists():
            self.entries = list(self._read())

    # -- чтение -------------------------------------------------------------
    def _read(self) -> Iterable[PublishResult]:
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                known = {k: data.get(k) for k in PublishResult.__dataclass_fields__}
                try:
                    yield PublishResult(**known)
                except TypeError:
                    continue

    # -- запись -------------------------------------------------------------
    def append(self, result: PublishResult) -> PublishResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.entries.append(result)
        return result

    # -- запросы ------------------------------------------------------------
    def published(self, platform: str, post_id: str) -> PublishResult | None:
        for entry in reversed(self.entries):
            if entry.platform == platform and entry.post_id == post_id and entry.status == STATUS_OK:
                return entry
        return None

    def last_attempt(self, platform: str, post_id: str) -> PublishResult | None:
        for entry in reversed(self.entries):
            if entry.platform == platform and entry.post_id == post_id:
                return entry
        return None

    def stats(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for entry in self.entries:
            bucket = stats.setdefault(entry.platform, {})
            bucket[entry.status] = bucket.get(entry.status, 0) + 1
        return stats
