"""Базовый класс площадки и реестр (API + браузерный режим).

Одна площадка может иметь два адаптера:
  * режим ``api``  — по официальным токенам (надёжно, не ломается);
  * режим ``browser`` — через ваш уже открытый/залогиненный браузер.

Реестр хранит оба и умеет выбирать: ``auto`` берёт API, если он настроен,
иначе браузер (если установлен Playwright), иначе сообщает, чего не хватает.

Публикация никогда не бросает исключения наружу: ошибка становится
PublishResult со статусом error, чтобы одна упавшая площадка не остановила
остальные.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from ..core.config import Secrets, Settings
from ..core.http import HTTPClient, HTTPError
from ..core.journal import (
    STATUS_DRY,
    STATUS_ERROR,
    STATUS_MANUAL,
    STATUS_OK,
    STATUS_SKIPPED,
    Journal,
    PublishResult,
)
from ..core.models import Issue, Limits, Media, Post

MODES = ("api", "browser", "manual")


@dataclass
class PlatformInfo:
    """Паспорт площадки."""

    name: str
    title: str
    supports_api: bool = True
    supports_browser: bool = False
    limits: Limits = field(default_factory=Limits)
    notes: str = ""
    docs: str = ""
    requires: tuple[str, ...] = ()


@dataclass
class PublishContext:
    """Всё, что нужно адаптеру для работы."""

    settings: Settings
    secrets: Secrets
    http: HTTPClient
    journal: Journal
    dry_run: bool = False
    #: спрашивать подтверждение перед последним кликом «Опубликовать»
    confirm: Callable[[str], bool] | None = None
    #: прогресс/лог для пользователя
    echo: Callable[[str], None] | None = None

    def cache_dir(self, *parts: str) -> Path:
        path = self.settings.state_dir() / "cache"
        for part in parts:
            path = path / part
        path.mkdir(parents=True, exist_ok=True)
        return path

    def secret(self, section: str, key: str, default: Any = None) -> Any:
        return self.secrets.get(section, key, default)

    def log(self, message: str) -> None:
        if self.echo:
            self.echo(message)

    def ask(self, message: str) -> bool:
        if self.confirm is None:
            return True
        return self.confirm(message)


class Platform(abc.ABC):
    """Адаптер площадки."""

    info: PlatformInfo
    mode: str = "api"
    required_secrets: tuple[tuple[str, str], ...] = ()

    def __init__(self, ctx: PublishContext):
        self.ctx = ctx
        self.settings = ctx.settings
        self.secrets = ctx.secrets
        self.http = ctx.http

    # -- идентификация ------------------------------------------------------
    @property
    def name(self) -> str:
        return self.info.name

    @property
    def limits(self) -> Limits:
        return self.info.limits

    @property
    def key(self) -> str:
        return f"{self.name}:{self.mode}"

    def __repr__(self) -> str:  # pragma: no cover - удобство отладки
        return f"<{type(self).__name__} {self.key}>"

    # -- настройка ----------------------------------------------------------
    def check_env(self) -> list[Issue]:
        """Проверить, хватает ли токенов/условий. Пустой список = всё готово."""
        issues: list[Issue] = []
        for section, key in self.required_secrets:
            if not self.secrets.get(section, key):
                issues.append(
                    Issue(
                        "error",
                        f"Не настроено: [{section}] {key} "
                        f"(secrets.toml или переменная SP_{section.upper()}_{key.upper()})",
                    )
                )
        return issues

    def check_post(self, post: Post) -> list[Issue]:
        return post.check(self.limits)

    # -- публикация ---------------------------------------------------------
    @abc.abstractmethod
    def publish(self, post: Post) -> PublishResult:
        """Опубликовать пост. Не бросать исключения — вернуть результат."""

    # -- утилиты ------------------------------------------------------------
    def result(
        self,
        post: Post,
        status: str,
        *,
        url: str = "",
        message: str = "",
        mode: str | None = None,
        post_key: str = "",
        **details: Any,
    ) -> PublishResult:
        return PublishResult(
            platform=self.name,
            post_id=post.id,
            status=status,
            url=url,
            message=message,
            mode=mode or self.mode,
            post_key=post_key,
            details=details,
        )

    def dry(self, post: Post, message: str = "Тестовая публикация: ничего не отправлено") -> PublishResult:
        return self.result(
            post,
            STATUS_DRY,
            message=message,
            planned=[m.summary() for m in post.media],
            title=post.title_or_first_line(),
        )

    def fail(self, post: Post, message: str, **details: Any) -> PublishResult:
        return self.result(post, STATUS_ERROR, message=message, **details)

    def skip(self, post: Post, message: str) -> PublishResult:
        return self.result(post, STATUS_SKIPPED, message=message)

    def manual(self, post: Post, message: str, url: str = "") -> PublishResult:
        return self.result(post, STATUS_MANUAL, message=message, mode="manual", url=url)

    def saved_token(self, key: str) -> dict[str, Any]:
        path = self.ctx.cache_dir("tokens") / f"{self.name}_{key}.json"
        if path.exists():
            try:
                return json.loads(path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def save_token(self, key: str, payload: dict[str, Any]) -> None:
        path = self.ctx.cache_dir("tokens") / f"{self.name}_{key}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass


PlatformFactory = Callable[[PublishContext], Platform]


class Resolution:
    """Результат выбора адаптера для площадки."""

    def __init__(self, name: str, platform: Platform | None, reason: str = ""):
        self.name = name
        self.platform = platform
        self.reason = reason

    @property
    def ok(self) -> bool:
        return self.platform is not None


class Registry:
    """Известные площадки: имя → {режим: адаптер}."""

    def __init__(self, ctx: PublishContext):
        self.ctx = ctx
        self._instances: dict[str, dict[str, Platform]] = {}
        self._mode_infos: dict[tuple[str, str], PlatformInfo] = {}
        self._infos: dict[str, PlatformInfo] = {}

    def register(self, factory: PlatformFactory) -> None:
        platform = factory(self.ctx)
        self._instances.setdefault(platform.name, {})[platform.mode] = platform
        self._mode_infos[(platform.name, platform.mode)] = platform.info
        # паспорт площадки — от первого зарегистрированного режима (api/manual),
        # браузерный режим не должен переименовывать площадку
        self._infos.setdefault(platform.name, platform.info)

    def names(self) -> list[str]:
        return sorted(self._instances)

    def modes(self, name: str) -> list[str]:
        name = normalise_name(name)
        return sorted(self._instances.get(name, {}))

    def get(self, name: str, mode: str = "api") -> Platform | None:
        return self._instances.get(normalise_name(name), {}).get(mode)

    def resolve(self, name: str, mode: str = "auto") -> Resolution:
        """Выбрать адаптер: api → browser → manual, согласно режиму."""
        name = normalise_name(name)
        variants = self._instances.get(name)
        if not variants:
            known = ", ".join(self.names())
            return Resolution(name, None, f"неизвестная площадка (есть: {known})")

        if mode in ("api", "browser", "manual"):
            platform = variants.get(mode)
            if platform is None:
                available = ", ".join(sorted(variants))
                return Resolution(
                    name,
                    None,
                    f"у площадки нет режима «{mode}» (доступно: {available}) — попробуйте --mode auto",
                )
            missing = platform.check_env()
            if missing and mode != "manual":
                return Resolution(name, None, "; ".join(i.text for i in missing))
            return Resolution(name, platform)

        # auto: сначала API, потом браузер, потом ручной
        for candidate_mode in ("api", "browser", "manual"):
            platform = variants.get(candidate_mode)
            if platform is None:
                continue
            if platform.check_env():
                continue
            return Resolution(name, platform)
        first = variants.get("api") or next(iter(variants.values()))
        reasons = "; ".join(i.text for i in first.check_env())
        return Resolution(name, None, reasons or "площадка не настроена")

    def require(self, name: str, mode: str = "auto") -> Platform:
        resolution = self.resolve(name, mode)
        if not resolution.ok:
            raise KeyError(f"Площадка «{name}» недоступна: {resolution.reason}")
        assert resolution.platform is not None
        return resolution.platform

    def infos(self) -> list[PlatformInfo]:
        return [self._infos[name] for name in self.names()]

    def status(self) -> list[dict[str, Any]]:
        rows = []
        for name in self.names():
            variants = self._instances[name]
            row: dict[str, Any] = {"name": name, "title": self._infos[name].title, "modes": {}}
            for mode, platform in sorted(variants.items()):
                issues = platform.check_env()
                info = self._mode_infos[(name, mode)]
                row["modes"][mode] = {
                    "ready": not issues,
                    "issues": [f"{i.text}" for i in issues],
                    "notes": info.notes,
                    "docs": info.docs,
                }
            rows.append(row)
        return rows


ALIASES = {
    "yt": "youtube",
    "youtube.com": "youtube",
    "ютуб": "youtube",
    "vk": "vk",
    "vkontakte": "vk",
    "вк": "vk",
    "вконтакте": "vk",
    "tg": "telegram",
    "telegram": "telegram",
    "телеграм": "telegram",
    "телеграмм": "telegram",
    "rutube": "rutube",
    "рутуб": "rutube",
    "dzen": "dzen",
    "zen": "dzen",
    "дзен": "dzen",
    "yandex": "dzen",
    "instagram": "instagram",
    "inst": "instagram",
    "инстаграм": "instagram",
    "tiktok": "tiktok",
    "тикток": "tiktok",
}


def normalise_name(name: str) -> str:
    key = str(name).strip().lower()
    return ALIASES.get(key, key)


def build_registry(ctx: PublishContext) -> Registry:
    """Собрать реестр: API-адаптеры + браузерные адаптеры (если есть Playwright)."""
    from . import dzen, instagram, rutube, telegram, tiktok, vk, youtube

    registry = Registry(ctx)
    for module in (youtube, vk, telegram, rutube, dzen, instagram, tiktok):
        registry.register(module.create)

    if ctx.settings.get("app.browser_enabled", True):
        try:
            from .browser import browser_factories

            for factory in browser_factories():
                registry.register(factory)
        except ImportError as exc:  # pragma: no cover - зависит от окружения
            ctx.log(f"Браузерный режим недоступен: установите playwright ({exc})")
        except Exception as exc:  # pragma: no cover
            ctx.log(f"Браузерный режим не загрузился: {exc}")
    return registry


def iter_limits(platforms: Iterable[Platform]) -> dict[str, Limits]:
    return {platform.name: platform.limits for platform in platforms}
