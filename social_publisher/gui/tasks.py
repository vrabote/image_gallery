"""Фоновые операции для окна: входы, проверки, публикация.

Работает без tkinter: окно только передаёт колбэки. Результаты публикации и
проверки — обычные dict, чтобы их можно было показать в журнале и в тестах.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..core.config import ConfigError, Secrets, Settings, tokenize_secrets, write_secrets
from ..core.http import HTTPClient
from ..core.journal import STATUS_OK, Journal
from ..core.models import Issue
from ..core.runner import RunOptions, Runner
from ..gui import services as service_specs
from ..platforms.base import PublishContext, build_registry, normalise_name

Echo = Callable[[str], None]
CONFIG_NAME = "config.toml"
SECRETS_NAME = "secrets.toml"


# ---------------------------------------------------------------------------
# общая настройка
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    """Всё, что нужно окну: пути, секреты, реестр площадок."""

    home: Path
    settings: Settings
    secrets: Secrets
    http: HTTPClient
    journal: Journal = field(init=False)

    def __post_init__(self) -> None:
        self.journal = Journal(self.settings.state_dir() / "journal.jsonl")

    @classmethod
    def open(cls, home: str | Path, echo: Echo | None = None) -> "AppContext":
        home = Path(home).expanduser().resolve()
        home.mkdir(parents=True, exist_ok=True)
        settings = Settings.load(home / CONFIG_NAME)
        if settings.path and not settings.path.exists():
            settings = Settings({}, path=home / CONFIG_NAME)
        secrets = Secrets.load(settings) if settings.path else Secrets({}, path=home / SECRETS_NAME)
        if secrets.path is None:
            secrets.path = home / SECRETS_NAME
        # секреты берём из папки пользователя (а не из пакета)
        local = home / SECRETS_NAME
        if local.exists():
            secrets = Secrets.load_file(local)
        http = HTTPClient(
            timeout=float(settings.get("app.http_timeout", 120)),
            retries=int(settings.get("app.http_retries", 3)),
            log=echo or (lambda _m: None),
        )
        ctx = cls(home=home, settings=settings, secrets=secrets, http=http)
        return ctx

    def publish_context(self, echo: Echo | None = None, confirm=None, dry_run: bool = False) -> PublishContext:
        return PublishContext(
            settings=self.settings,
            secrets=self.secrets,
            http=self.http,
            journal=self.journal,
            dry_run=dry_run,
            confirm=confirm,
            echo=echo,
        )

    def registry(self, echo: Echo | None = None):
        ctx = self.publish_context(echo=echo)
        registry = build_registry(ctx)
        self.settings.data.setdefault("_browser_session", None)
        return registry

    def reload_secrets(self) -> Secrets:
        self.secrets = Secrets.load_file(self.home / SECRETS_NAME) if (self.home / SECRETS_NAME).exists() else Secrets({}, path=self.home / SECRETS_NAME)
        return self.secrets


# ---------------------------------------------------------------------------
# входные данные: чтение, проверка, сохранение
# ---------------------------------------------------------------------------

GOOGLE_CLIENT_NAME = "client_secret.json"

FORM_FIELDS = {
    "youtube": [("client_secret_file", "Путь к client_secret.json", ""), ("channel_name", "Название канала (подпись)", "")],
    "vk": [
        ("access_token", "Ключ доступа VK", "secret"),
        ("group_id", "id сообщества (без минуса, пусто = личная страница)", ""),
    ],
    "telegram": [("bot_token", "Токен бота", "secret"), ("chat_id", "@канал или -100…", "")],
    "rutube": [("token", "X-AUTH-TOKEN Rutube", "secret"), ("channel_id", "id канала (можно пусто)", "")],
}  # type: dict[str, list[tuple[str, str, str]]]


def form_fields(service_name: str) -> list[tuple[str, str, str]]:
    return FORM_FIELDS.get(service_name, [])


def load_setup(data_dir: str | Path) -> dict[str, dict[str, str]]:
    import json

    path = Path(data_dir) / "setup.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, ValueError):
            pass
    return {}


def save_setup(data_dir: str | Path, values: dict[str, dict[str, str]]) -> Path:
    import json

    path = Path(data_dir) / "setup.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _chat_id_ok(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    if value.startswith("@"):
        return bool(re.fullmatch(r"@[A-Za-z0-9_]{4,}", value))
    return bool(re.fullmatch(r"-?\d{5,}", value))


def _group_id_ok(value: str) -> bool:
    value = value.strip().lstrip("-")
    return bool(re.fullmatch(r"\d{3,}", value))


def check_setup(service_name: str, values: dict[str, str], data_dir: str | Path) -> list[Issue]:
    """Проверить входные данные сервиса. Пустой список = всё в порядке."""
    service_name = normalise_name(service_name)
    issues: list[Issue] = []
    get = lambda key: str(values.get(key) or "").strip()  # noqa: E731

    if service_name == "youtube":
        client_id = get("client_id")
        client_secret = get("client_secret")
        file_value = get("client_secret_file")
        has_file = False
        if file_value:
            path = Path(file_value).expanduser()
            if not path.is_absolute():
                path = Path(data_dir) / path
            has_file = path.exists()
            if not has_file:
                issues.append(Issue("error", f"Файл не найден: {path}"))
        default_file = Path(data_dir) / GOOGLE_CLIENT_NAME
        if not (client_id and client_secret) and not has_file and not default_file.exists():
            issues.append(
                Issue(
                    "error",
                    "Нет client_secret.json: скачайте OAuth client (Desktop) в Google Cloud "
                    f"и положите в {data_dir}",
                )
            )
        token = _read_json(Path(data_dir) / "state" / "cache" / "tokens" / "youtube_oauth_google.json")
        if not token.get("refresh_token"):
            issues.append(Issue("warning", "Ещё не выполнен вход в Google: нажмите «Войти в Google»"))

    elif service_name == "vk":
        if not get("access_token"):
            issues.append(Issue("error", "Пустой ключ доступа VK"))
        elif len(get("access_token")) < 20:
            issues.append(Issue("error", "Ключ доступа VK выглядит слишком коротким"))
        if get("group_id") and not _group_id_ok(get("group_id")):
            issues.append(Issue("error", "id сообщества — только цифры, без минуса"))

    elif service_name == "telegram":
        token = get("bot_token")
        if not token:
            issues.append(Issue("error", "Пустой токен бота (возьмите у @BotFather)"))
        elif not re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{20,}", token):
            issues.append(Issue("error", "Токен бота выглядит неверно: ожидается 123456:AA…"))
        if not _chat_id_ok(get("chat_id")):
            issues.append(Issue("error", "Укажите @канал или числовой id вида -1001234567890"))

    elif service_name == "rutube":
        if not get("token"):
            issues.append(Issue("warning", "Токена нет — будет использован браузерный режим"))
        elif len(get("token")) < 16:
            issues.append(Issue("error", "Токен Rutube выглядит слишком коротким"))

    return issues


def _read_json(path: Path) -> dict:
    import json

    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_setup_and_secrets(
    ctx: AppContext,
    values: dict[str, dict[str, str]],
    include: list[str] | None = None,
) -> list[Path]:
    """Записать setup.json и secrets.toml (секреты — в secrets.toml)."""
    save_setup_files(ctx.home, values)
    secret_values = tokenize_secrets(values)
    if include:
        secret_values = {name: secret_values[name] for name in include if name in secret_values}
        # сохраняем остальные секции, которые уже были в файле
        existing = Secrets.load_file(ctx.home / SECRETS_NAME).data if (ctx.home / SECRETS_NAME).exists() else {}
        for name, section in existing.items():
            secret_values.setdefault(name, section)
    write_secrets(ctx.home / SECRETS_NAME, secret_values)
    ctx.reload_secrets()
    return [ctx.home / "setup.json", ctx.home / SECRETS_NAME]


# ---------------------------------------------------------------------------
# проверка плана
# ---------------------------------------------------------------------------


@dataclass
class CheckRow:
    """Строка таблицы проверки."""

    post_id: str
    service: str
    file: str
    status: str  # ok | warn | error
    message: str
    mode: str = ""


def check_plan_file(path: str | Path, ctx: AppContext, mode: str = "auto") -> list[CheckRow]:
    """Проверить план: файлы, лимиты, готовность сервисов."""
    from ..core.models import Plan

    plan = Plan.load(path)
    registry = ctx.registry()
    rows: list[CheckRow] = []
    for post in plan.posts:
        if not post.media:
            rows.append(CheckRow(post.id, ", ".join(post.platforms) or "—", "—", "error", "Нет файлов у поста"))
            continue
        for media in post.media:
            file_state = "ok"
            file_message = f"{media.kind}, {media.size_bytes / 1e6:.1f} МБ"
            if media.duration:
                file_message += f", {media.duration:.0f} с"
            if not media.path.exists():
                file_state, file_message = "error", f"Файл не найден: {media.path}"
            rows.append(CheckRow(post.id, ", ".join(post.platforms) or "—", media.name, file_state, file_message))
        for platform_name in post.platforms:
            resolution = registry.resolve(platform_name, mode)
            if not resolution.ok or resolution.platform is None:
                rows.append(
                    CheckRow(
                        post.id,
                        platform_name,
                        "—",
                        "error",
                        f"Сервис не готов: {resolution.reason} (проверьте входные данные)",
                    )
                )
                continue
            platform = resolution.platform
            issues = platform.check_post(post)
            errors = [i for i in issues if i.level == "error"]
            warnings = [i for i in issues if i.level != "error"]
            if errors:
                rows.append(CheckRow(post.id, platform_name, "—", "error", "; ".join(i.text for i in errors), platform.mode))
            elif warnings:
                rows.append(
                    CheckRow(post.id, platform_name, "—", "warn", "; ".join(i.text for i in warnings), platform.mode)
                )
            else:
                rows.append(CheckRow(post.id, platform_name, "—", "ok", "Готово к публикации", platform.mode))
    return rows


def rows_problem_count(rows: list[CheckRow]) -> tuple[int, int]:
    errors = sum(1 for row in rows if row.status == "error")
    warnings = sum(1 for row in rows if row.status == "warn")
    return errors, warnings


# ---------------------------------------------------------------------------
# публикация
# ---------------------------------------------------------------------------


@dataclass
class PublishOutcome:
    ok: int = 0
    errors: int = 0
    skipped: int = 0
    manual: int = 0
    dry: int = 0
    results: list = field(default_factory=list)


def publish_plan(
    path: str | Path,
    ctx: AppContext,
    *,
    mode: str = "auto",
    dry_run: bool = False,
    force: bool = False,
    only: list[str] | None = None,
    confirm=None,
    echo: Echo = print,
) -> PublishOutcome:
    from ..core.models import Plan

    plan = Plan.load(path)
    publish_ctx = ctx.publish_context(echo=echo, dry_run=dry_run)
    registry = build_registry(publish_ctx)
    runner = Runner(registry, ctx.journal, echo=echo, confirm=confirm)
    options = RunOptions(mode=mode, dry_run=dry_run, force=force, assume_yes=confirm is None, only_platforms=only or [])
    report = runner.run(plan, options)
    return PublishOutcome(
        ok=report.ok,
        errors=report.errors,
        skipped=report.skipped,
        manual=report.manual,
        dry=report.dry,
        results=report.results,
    )


# ---------------------------------------------------------------------------
# очередь сообщений из фонового потока в окно
# ---------------------------------------------------------------------------


class MessageQueue:
    """Потокобезопасный «почтовый ящик»: фон пишет, окно разбирает."""

    def __init__(self):
        self._items: list[tuple[str, Any]] = []
        self._lock = threading.Lock()

    def put(self, kind: str, payload: Any = None) -> None:
        with self._lock:
            self._items.append((kind, payload))

    def drain(self) -> list[tuple[str, Any]]:
        with self._lock:
            items, self._items = self._items, []
        return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def run_in_thread(fn: Callable[[], Any], queue: MessageQueue, name: str = "log", done: str = "done") -> threading.Thread:
    """Запустить fn в фоне; в очередь уйдут итог и сообщение об исключении."""

    def wrapper():
        try:
            result = fn()
            queue.put(done, result)
        except Exception as exc:  # noqa: BLE001 - показываем в окне, не роняем
            queue.put("error", f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=wrapper, name=name, daemon=True)
    thread.start()
    return thread


def wait_until(predicate: Callable[[], bool], timeout: float = 30.0, interval: float = 0.05) -> bool:
    """Ждать условия (нужно тестам и синхронным сценариям)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


__all__ = [
    "AppContext",
    "CheckRow",
    "MessageQueue",
    "PublishOutcome",
    "check_plan_file",
    "check_setup",
    "form_fields",
    "load_setup",
    "publish_plan",
    "rows_problem_count",
    "run_in_thread",
    "save_setup",
    "save_setup_and_secrets",
    "wait_until",
    "STATUS_OK",
    "ConfigError",
    "service_specs",
]


def save_setup_files(data_dir: str | Path, values: dict[str, dict[str, str]]) -> Path:
    path = Path(data_dir) / "setup.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
