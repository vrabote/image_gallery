"""Настройки (config.toml) и секреты (secrets.toml).

Правила:
  * настройки лежат в TOML или JSON, секреты — в отдельном файле, который
    не попадает в git (см. .gitignore);
  * любое секретное значение можно переопределить переменной окружения
    ``SP_<РАЗДЕЛ>_<КЛЮЧ>``, например ``SP_VK_ACCESS_TOKEN`` или
    ``SP_YOUTUBE_CLIENT_SECRET``;
  * пути в конфиге считаются относительными от папки конфига, поэтому проект
    можно переносить целиком.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENV_PREFIX = "SP_"
PACKAGE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "config.toml"


class ConfigError(RuntimeError):
    """Ошибка в конфиге или секретах."""


def load_structured(path: Path) -> dict[str, Any]:
    """Прочитать TOML или JSON в словарь."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Файл не найден: {path}")
    text = path.read_text(encoding="utf-8-sig")
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Не удалось разобрать {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Ожидался объект верхнего уровня в {path}")
    return data


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Слить два словаря; значения из extra главнее."""
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Settings:
    """Настройки приложения."""

    data: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @property
    def home(self) -> Path:
        return self.path.parent if self.path else PACKAGE_DIR

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Settings":
        if path is None:
            path = os.environ.get("SP_CONFIG") or DEFAULT_CONFIG_PATH
        path = Path(path).expanduser()
        if not path.exists():
            return cls({}, path=path)
        return cls(load_structured(path), path=path)

    # --- доступ к значениям -------------------------------------------------
    def section(self, name: str) -> dict[str, Any]:
        value = self.data.get(name)
        return dict(value) if isinstance(value, dict) else {}

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def resolve(self, value: str | os.PathLike, base: Path | None = None) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (base or self.home) / path
        return Path(os.path.normpath(path))

    def state_dir(self) -> Path:
        return self.resolve(self.get("app.state_dir", "state"))

    def browser_headless(self) -> bool:
        return bool(self.get("browser.headless", False))

    def browser_slow_mo(self) -> int:
        try:
            return int(self.get("browser.slow_mo", 80))
        except (TypeError, ValueError):
            return 80


@dataclass
class Secrets:
    """Секреты: токены, client_secret, bot_token."""

    data: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def load(cls, settings: Settings) -> "Secrets":
        candidates: list[Path] = []
        explicit = settings.get("app.secrets_file")
        if explicit:
            candidates.append(settings.resolve(explicit))
        candidates.append(settings.home / "secrets.toml")
        candidates.append(settings.home / "secrets.json")
        # шаблон из пакета: удобно, если конфиг лежит рядом с планами
        candidates.append(PACKAGE_DIR / "secrets.toml")
        for candidate in candidates:
            if candidate.exists():
                return cls(load_structured(candidate), path=candidate)
        return cls({}, path=None)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        env_key = f"{ENV_PREFIX}{section}_{key}".upper().replace("-", "_")
        from_env = os.environ.get(env_key)
        if from_env:
            return from_env
        node = self.data.get(section)
        if not isinstance(node, dict):
            return default
        value = node.get(key, default)
        return default if value in ("", None) else value

    def require(self, section: str, key: str, hint: str = "") -> Any:
        value = self.get(section, key)
        if value in ("", None):
            message = f"Не задан секрет: {section}.{key}"
            if hint:
                message += f" ({hint})"
            raise ConfigError(message)
        return value

    def describe(self) -> str:
        """Где лежат секреты и что в них уже есть (без самих значений)."""
        lines = [f"Файл секретов: {self.path if self.path else 'не найден'}"]
        for section, values in sorted(self.data.items()):
            if isinstance(values, dict) and values:
                keys = ", ".join(sorted(values))
                lines.append(f"  [{section}] {keys}")
        return "\n".join(lines)


def mask(value: str | None, keep: int = 4) -> str:
    """Показать только хвост секрета."""
    if not value:
        return ""
    value = str(value)
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"
