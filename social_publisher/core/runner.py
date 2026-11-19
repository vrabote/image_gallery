"""Прогон плана: проверка → подтверждение → публикация → журнал.

Ключевые свойства:
  * одна упавшая площадка не останавливает остальные;
  * уже опубликованное не публикуется повторно (журнал), если не --force;
  * в режиме подтверждения перед каждой публикацией задаётся вопрос;
  * любые проблемы файла (нет файла, слишком длинное видео) видны заранее.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..core.journal import (
    STATUS_ERROR,
    STATUS_MANUAL,
    STATUS_OK,
    STATUS_SKIPPED,
    Journal,
    PublishResult,
)
from ..core.models import Issue, Plan, Post
from ..platforms.base import Registry


@dataclass
class RunOptions:
    mode: str = "auto"  # auto | api | browser | manual
    dry_run: bool = False
    assume_yes: bool = False
    force: bool = False
    limit: int | None = None
    only_platforms: list[str] = field(default_factory=list)
    skip_platforms: list[str] = field(default_factory=list)
    stop_on_error: bool = False


@dataclass
class RunReport:
    results: list[PublishResult] = field(default_factory=list)
    planned: int = 0

    @property
    def ok(self) -> int:
        return sum(1 for r in self.results if r.status == STATUS_OK)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == STATUS_ERROR)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == STATUS_SKIPPED)

    @property
    def manual(self) -> int:
        return sum(1 for r in self.results if r.status == STATUS_MANUAL)

    @property
    def dry(self) -> int:
        return sum(1 for r in self.results if r.status == "dry-run")

    def summary(self) -> str:
        parts = [f"опубликовано: {self.ok}"]
        if self.dry:
            parts.append(f"тестовый прогон: {self.dry}")
        if self.manual:
            parts.append(f"вручную: {self.manual}")
        if self.skipped:
            parts.append(f"пропущено: {self.skipped}")
        if self.errors:
            parts.append(f"ошибок: {self.errors}")
        return ", ".join(parts)


class Runner:
    def __init__(
        self,
        registry: Registry,
        journal: Journal,
        *,
        echo: Callable[[str], None] = print,
        confirm: Callable[[str], bool] | None = None,
    ):
        self.registry = registry
        self.journal = journal
        self.echo = echo
        self.confirm = confirm

    # -- основной цикл ------------------------------------------------------
    def run(self, plan: Plan, options: RunOptions) -> RunReport:
        report = RunReport()
        tasks: list[tuple[Post, str]] = []
        for post in plan.posts:
            for platform_name in self._targets(post, options):
                tasks.append((post, platform_name))
        if options.limit:
            tasks = tasks[: options.limit]
        report.planned = len(tasks)

        self.echo(
            f"План: {plan.path.name} · постов {len(plan.posts)} · публикаций {len(tasks)} · "
            f"режим {options.mode}{' · ТЕСТ' if options.dry_run else ''}"
        )
        if not tasks:
            self.echo("Нечего публиковать: проверьте platforms в плане.")
            return report

        for index, (post, platform_name) in enumerate(tasks, start=1):
            header = f"[{index}/{len(tasks)}] {post.title_or_first_line()} → {platform_name}"
            self.echo("\n" + header)
            result = self._publish_one(post, platform_name, options)
            report.results.append(result)
            self._print_result(result)
            if options.stop_on_error and result.status == STATUS_ERROR:
                self.echo("Остановка по --stop-on-error")
                break
        self.echo("\nИтог: " + report.summary())
        return report

    # -- одна публикация ----------------------------------------------------
    def _publish_one(self, post: Post, platform_name: str, options: RunOptions) -> PublishResult:
        if platform_name in options.skip_platforms:
            return PublishResult(platform_name, post.id, STATUS_SKIPPED, message="пропущено по --skip")

        resolution = self.registry.resolve(platform_name, options.mode)
        if not resolution.ok or resolution.platform is None:
            self.echo(f"  площадка не готова: {resolution.reason}")
            result = PublishResult(
                platform_name,
                post.id,
                STATUS_ERROR,
                message=f"не настроено: {resolution.reason}",
                mode=options.mode,
            )
            self.journal.append(result)
            return result
        platform = resolution.platform

        # проверка файлов и текста
        issues = platform.check_post(post)
        blocking = [i for i in issues if i.level == "error"]
        for issue in issues:
            self.echo(f"  {issue}")
        if blocking:
            result = PublishResult(
                platform_name,
                post.id,
                STATUS_ERROR,
                message="; ".join(i.text for i in blocking),
                mode=platform.mode,
            )
            self.journal.append(result)
            return result

        # идемпотентность
        if not options.force:
            already = self.journal.published(platform_name, post.id)
            if already is not None:
                self.echo(f"  уже опубликовано {already.timestamp}: {already.url or already.message}")
                return PublishResult(
                    platform_name,
                    post.id,
                    STATUS_SKIPPED,
                    url=already.url,
                    message="уже публиковалось раньше (--force, чтобы повторить)",
                    mode=platform.mode,
                    post_key=already.post_key,
                )

        if self.confirm and not options.assume_yes and not options.dry_run:
            question = self._question(post, platform)
            if not self.confirm(question):
                result = PublishResult(
                    platform_name,
                    post.id,
                    STATUS_MANUAL,
                    message="отложено: вы не подтвердили",
                    mode=platform.mode,
                )
                self.journal.append(result)
                return result

        try:
            result = platform.publish(post)
        except Exception as exc:  # pragma: no cover - адаптеры не должны бросать
            result = platform.fail(post, f"{type(exc).__name__}: {exc}")
        self.journal.append(result)
        return result

    def _question(self, post: Post, platform) -> str:
        files = ", ".join(f"{m.name}{f' ({m.duration:.0f} с)' if m.duration else ''}" for m in post.media)
        lines = [
            f"Площадка: {platform.name} ({platform.mode})",
            f"Пост: {post.title_or_first_line()}",
            f"Файлы: {files or '—'}",
        ]
        if platform.info.limits.max_title_chars:
            lines.append(f"Заголовок: {post.title[: platform.info.limits.max_title_chars]}")
        if post.tags:
            lines.append(f"Теги: {' '.join(post.tags[:15])}")
        return "\n".join(lines)

    # -- вспомогательное ----------------------------------------------------
    def _targets(self, post: Post, options: RunOptions) -> list[str]:
        if post.platforms:
            names = list(post.platforms)
        else:
            # площадки в посте не указаны — берём только те, что реально настроены
            names = [
                name
                for name in self.registry.names()
                if self.registry.resolve(name, options.mode).ok
            ]
            if names:
                self.echo(f"  {post.id}: площадки не указаны — беру настроенные: {', '.join(names)}")
        if options.only_platforms:
            allowed = {n.strip() for n in options.only_platforms}
            names = [n for n in names if n in allowed]
        return [n for n in names if n not in options.skip_platforms]

    def _print_result(self, result: PublishResult) -> None:
        mark = {
            STATUS_OK: "ГОТОВО",
            STATUS_ERROR: "ОШИБКА",
            STATUS_SKIPPED: "пропуск",
            STATUS_MANUAL: "вручную",
            "dry-run": "тест",
        }.get(result.status, result.status)
        line = f"  {mark}: {result.message}"
        if result.url:
            line += f"\n  ссылка: {result.url}"
        self.echo(line)


def describe_plan(plan: Plan, registry: Registry | None = None) -> str:
    """Текстовая сводка плана — то, что видит пользователь до публикации."""
    lines = [f"План: {plan.path}"]
    if plan.defaults:
        lines.append(f"Значения по умолчанию: {plan.defaults}")
    for post in plan.posts:
        lines.append("")
        lines.append(f"— {post.id}: {post.title_or_first_line()}")
        if post.description:
            preview = post.description.replace("\n", " ")
            lines.append(f"  текст: {preview[:160]}{'…' if len(preview) > 160 else ''}")
        if post.tags:
            lines.append(f"  теги: {' '.join(post.tags)}")
        lines.append(f"  площадки: {', '.join(post.platforms) or 'все настроенные'}")
        for media in post.media:
            bits = [media.name, media.kind]
            if media.duration:
                bits.append(f"{media.duration:.0f} с")
            if media.width and media.height:
                bits.append(f"{media.width}x{media.height}")
            bits.append(f"{media.size_bytes / 1e6:.1f} МБ")
            exists = "" if media.path.exists() else "  ← ФАЙЛА НЕТ"
            lines.append(f"  файл: {' · '.join(bits)}{exists}")
    return "\n".join(lines)


def check_plan(plan: Plan, registry: Registry, mode: str = "auto") -> list[str]:
    """Предупреждения по всему плану: чего не хватает для публикации."""
    problems: list[str] = []
    for post in plan.posts:
        for platform_name in post.platforms:
            resolution = registry.resolve(platform_name, mode)
            if not resolution.ok:
                problems.append(f"{post.id} → {platform_name}: {resolution.reason}")
                continue
            assert resolution.platform is not None
            for issue in resolution.platform.check_post(post):
                problems.append(f"{post.id} → {platform_name}: {issue}")
    return problems
