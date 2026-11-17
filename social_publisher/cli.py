"""Командная строка: план, проверка, публикация, входы в аккаунты.

Примеры:
    python -m social_publisher doctor
    python -m social_publisher plan example_plan.toml --check
    python -m social_publisher run plan.toml --dry-run
    python -m social_publisher run plan.toml              # с подтверждением
    python -m social_publisher run plan.toml --yes        # без вопросов
    python -m social_publisher run plan.toml --mode browser
    python -m social_publisher auth youtube
    python -m social_publisher login vk
    python -m social_publisher learn youtube
    python -m social_publisher journal
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .core.config import ConfigError, Secrets, Settings
from .core.http import HTTPClient, HTTPError
from .core.journal import STATUS_OK, Journal
from .core.models import Plan
from .core.runner import RunOptions, Runner, check_plan, describe_plan
from .platforms.base import build_registry, normalise_name

OK = "✓"
BAD = "✗"
WARN = "!"


def _settings(args) -> Settings:
    settings = Settings.load(getattr(args, "config", None))
    if settings.path and not settings.path.exists():
        raise ConfigError(f"Файл конфига не найден: {settings.path}")
    return settings


def _context(settings: Settings, *, dry_run: bool = False, echo=print):
    secrets = Secrets.load(settings)
    http = HTTPClient(
        timeout=float(settings.get("app.http_timeout", 120)),
        retries=int(settings.get("app.http_retries", 3)),
        log=lambda msg: echo(f"  {msg}"),
    )
    journal = Journal(settings.state_dir() / "journal.jsonl")
    return secrets, http, journal


def _say(message: str = "") -> None:
    print(message, flush=True)


def _ask(message: str) -> bool:
    _say("")
    for line in message.splitlines():
        _say(f"  {line}")
    try:
        answer = input("\n  Публиковать? [Д/н/в=выйти] ").strip().lower()
    except EOFError:
        return False
    if answer in {"в", "q", "quit", "exit"}:
        raise KeyboardInterrupt
    return answer in {"", "д", "да", "y", "yes"}


# ---------------------------------------------------------------------------
# команды
# ---------------------------------------------------------------------------


def cmd_doctor(args) -> int:
    settings = _settings(args)
    secrets, http, journal = _context(settings)
    _say(f"social_publisher {__version__}")
    _say(f"Python: {sys.version.split()[0]} ({sys.executable})")
    _say(f"Конфиг: {settings.path} {'— найден' if settings.path and settings.path.exists() else '— НЕТ, взяты значения по умолчанию'}")
    _say(f"Секреты: {secrets.path or 'не найдены (secrets.toml)'}")
    _say(f"Папка состояния: {settings.state_dir()}")

    try:
        import playwright  # noqa: F401

        _say(f"Playwright: установлен ({playwright.__file__})")
    except Exception:
        _say("Playwright: не установлен — браузерный режим недоступен (pip install playwright)")
    _say(f"ffprobe: {shutil.which('ffprobe') or 'нет (длительность MP4 читаем сами)'}")

    registry = build_registry(
        _ctx_for(settings, secrets, http, journal),
    )
    _say("\nПлощадки:")
    for row in registry.status():
        modes = row["modes"]
        ready_api = modes.get("api", {}).get("ready")
        ready_browser = modes.get("browser", {}).get("ready")
        marks = []
        if "api" in modes:
            marks.append(f"api {OK if ready_api else BAD}")
        if "browser" in modes:
            marks.append(f"browser {OK if ready_browser else BAD}")
        _say(f"  {row['name']:<10} {row['title']:<34} {' · '.join(marks)}")
        for mode, info in modes.items():
            for issue in info["issues"]:
                _say(f"      {mode}: {issue}")
    _say("\nЧто дальше: заполните secrets.toml, затем run plan.toml --dry-run")
    return 0


def _ctx_for(settings: Settings, secrets: Secrets, http: HTTPClient, journal: Journal, **kwargs):
    from .platforms.base import PublishContext

    return PublishContext(settings=settings, secrets=secrets, http=http, journal=journal, **kwargs)


def cmd_plan(args) -> int:
    settings = _settings(args)
    plan = Plan.load(args.plan, base=settings.home if not Path(args.plan).is_absolute() else None)
    secrets, http, journal = _context(settings)
    registry = build_registry(_ctx_for(settings, secrets, http, journal))

    if args.json:
        print(json.dumps(plan.summary(), ensure_ascii=False, indent=2))
        return 0

    _say(describe_plan(plan, registry))
    problems = check_plan(plan, registry, args.mode)
    if problems:
        _say("\nПроблемы:")
        for problem in problems:
            _say(f"  {WARN} {problem}")
    else:
        _say("\nПроблем не нашлось — можно публиковать.")
    if args.check and problems:
        return 1
    return 0


def cmd_run(args) -> int:
    settings = _settings(args)
    plan_path = Path(args.plan).expanduser()
    if not plan_path.is_absolute():
        plan_path = (Path.cwd() / plan_path)
        if not plan_path.exists():
            plan_path = settings.home / args.plan
    plan = Plan.load(plan_path)
    secrets, http, journal = _context(settings)
    ctx = _ctx_for(settings, secrets, http, journal, dry_run=args.dry_run, echo=_say)
    ctx.confirm = _ask if not args.yes else None
    registry = build_registry(ctx)
    ctx.confirm = None if args.yes or args.dry_run else ctx.confirm

    options = RunOptions(
        mode=args.mode,
        dry_run=args.dry_run,
        assume_yes=args.yes,
        force=args.force,
        limit=args.limit,
        only_platforms=[normalise_name(p) for p in (args.platform or [])],
        skip_platforms=[normalise_name(p) for p in (args.skip or [])],
        stop_on_error=args.stop_on_error,
    )
    runner = Runner(registry, journal, echo=_say, confirm=ctx.confirm)
    try:
        report = runner.run(plan, options)
    except KeyboardInterrupt:
        _say("\nОстановлено пользователем.")
        return 130
    finally:
        session = settings.data.get("_browser_session")
        if session is not None:
            session.close()
    if report.errors:
        return 2
    return 0


def cmd_auth(args) -> int:
    settings = _settings(args)
    secrets, http, journal = _context(settings)
    registry = build_registry(_ctx_for(settings, secrets, http, journal))
    platform = registry.get(normalise_name(args.platform), "api")
    if platform is None:
        _say(f"У площадки «{args.platform}» нет API-режима. Для входа используйте: login {args.platform}")
        return 2
    if not hasattr(platform, "auth"):
        _say(f"{args.platform}: авторизация через эту команду не поддерживается.")
        return 2
    try:
        platform.auth(open_browser=not args.no_browser)
    except Exception as exc:
        _say(f"\nНе удалось авторизоваться: {exc}")
        return 2
    _say("\nГотово: токен сохранён в state/cache/tokens/. Проверьте: doctor")
    return 0


def cmd_login(args) -> int:
    settings = _settings(args)
    try:
        from .platforms.browser import open_for_login
    except Exception as exc:
        _say(f"Браузерный режим недоступен: {exc}")
        return 2
    try:
        open_for_login(settings, normalise_name(args.site), log=_say)
    except Exception as exc:
        _say(f"Не удалось открыть браузер: {exc}")
        return 2
    _say(f"Профиль сохранён: {settings.resolve(settings.get('browser.profile_dir', 'state/browser-profile'))}")
    return 0


def cmd_learn(args) -> int:
    settings = _settings(args)
    try:
        from .platforms.browser import learn_selectors
    except Exception as exc:
        _say(f"Браузерный режим недоступен: {exc}")
        return 2
    try:
        learn_selectors(settings, normalise_name(args.site), log=_say)
    except Exception as exc:
        _say(f"Не удалось: {exc}")
        return 2
    return 0


def cmd_journal(args) -> int:
    settings = _settings(args)
    secrets, http, journal = _context(settings)
    if args.json:
        print(json.dumps([e.to_dict() for e in journal.entries], ensure_ascii=False, indent=2))
        return 0
    if not journal.entries:
        _say(f"Журнал пуст: {journal.path}")
        return 0
    _say(f"Журнал: {journal.path} · записей {len(journal.entries)}")
    rows = journal.entries[-args.last :] if args.last else journal.entries
    for entry in rows:
        if args.failed and entry.status == STATUS_OK:
            continue
        mark = {STATUS_OK: OK, "error": BAD, "skipped": "-", "manual": "→", "dry-run": "тест"}.get(entry.status, "?")
        _say(f"{mark} {entry.timestamp}  {entry.platform:<10} {entry.post_id:<12} {entry.status:<8} {entry.url or entry.message}")
    stats = journal.stats()
    if stats and not args.failed:
        _say("")
        for platform_name, bucket in sorted(stats.items()):
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(bucket.items()))
            _say(f"  {platform_name}: {summary}")
    return 0


def cmd_init(args) -> int:
    target = Path(args.directory).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    package = Path(__file__).resolve().parent
    copied = []
    for name in ("config.toml", "secrets.example.toml", "plan.example.toml"):
        source = package / name
        if not source.exists():
            continue
        destination = target / name
        if destination.exists() and not args.force:
            _say(f"  {name}: уже есть, пропускаю (--force перезапишет)")
            continue
        shutil.copy2(source, destination)
        copied.append(name)
    _say(f"Разложил шаблоны в {target}: {', '.join(copied) or 'нечего'}")
    _say("Дальше: secrets.toml (по образцу secrets.example.toml) и python -m social_publisher doctor")
    return 0


# ---------------------------------------------------------------------------
# парсер аргументов
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m social_publisher",
        description="Публикация клипов и фото в соцсети: API или браузерный режим, с подтверждением.",
    )
    parser.add_argument("--version", action="version", version=f"social_publisher {__version__}")
    parser.add_argument("--config", help="путь к config.toml (по умолчанию рядом с кодом)")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="проверить окружение, токены и готовность площадок")
    doctor.set_defaults(func=cmd_doctor)

    plan = sub.add_parser("plan", help="показать план и проверить файлы/лимиты")
    plan.add_argument("plan", help="путь к plan.toml или plan.json")
    plan.add_argument("--mode", default="auto", choices=["auto", "api", "browser", "manual"])
    plan.add_argument("--check", action="store_true", help="вернуть код 1, если есть проблемы")
    plan.add_argument("--json", action="store_true", help="вывести план в JSON")
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="опубликовать посты из плана")
    run.add_argument("plan", help="путь к plan.toml или plan.json")
    run.add_argument("--mode", default="auto", choices=["auto", "api", "browser", "manual"],
                     help="auto: API если настроен, иначе браузер")
    run.add_argument("--dry-run", action="store_true", help="ничего не публиковать, только показать")
    run.add_argument("--yes", "-y", action="store_true", help="без подтверждений (осторожно)")
    run.add_argument("--force", action="store_true", help="публиковать даже если уже в журнале")
    run.add_argument("--limit", type=int, help="не больше N публикаций за прогон")
    run.add_argument("--platform", action="append", help="только эти площадки (можно несколько)")
    run.add_argument("--skip", action="append", help="пропустить эти площадки")
    run.add_argument("--stop-on-error", action="store_true", help="остановиться на первой ошибке")
    run.set_defaults(func=cmd_run)

    auth = sub.add_parser("auth", help="получить токен (сейчас: youtube)")
    auth.add_argument("platform")
    auth.add_argument("--no-browser", action="store_true", help="не открывать браузер, только ссылку")
    auth.set_defaults(func=cmd_auth)

    login = sub.add_parser("login", help="открыть браузер, чтобы войти в аккаунт (для браузерного режима)")
    login.add_argument("site")
    login.set_defaults(func=cmd_login)

    learn = sub.add_parser("learn", help="показать поля и кнопки страницы — чтобы поправить селекторы")
    learn.add_argument("site")
    learn.set_defaults(func=cmd_learn)

    journal = sub.add_parser("journal", help="что уже опубликовано")
    journal.add_argument("--json", action="store_true")
    journal.add_argument("--last", type=int, default=0, help="показать последние N записей")
    journal.add_argument("--failed", action="store_true", help="только неудачные попытки")
    journal.set_defaults(func=cmd_journal)

    init = sub.add_parser("init", help="разложить шаблоны config/secrets/plan в папку")
    init.add_argument("directory", nargs="?", default=".", help="куда копировать (по умолчанию текущая)")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ConfigError as exc:
        _say(f"\nОшибка настройки: {exc}")
        return 2
    except HTTPError as exc:
        _say(f"\nОшибка сети: {exc}")
        return 2
    except KeyboardInterrupt:
        _say("\nПрервано.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
