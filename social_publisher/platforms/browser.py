"""Браузерный режим: публикация через уже залогиненный браузер (Playwright).

Идея ровно та, о которой вы спрашивали: вы один раз входите в аккаунты, а
программа открывает нужную страницу, прикрепляет файлы, вписывает текст и
нажимает «Опубликовать».

Важно:
  * селекторы вынесены в JSON (social_publisher/selectors.json) — если сайт
    поменяет вёрстку, правится только JSON, код не трогаем;
  * по умолчанию используется установленный Chrome/Edge (не нужен отдельный
    Chromium), профиль сохраняется, так что вход остаётся между запусками;
  * браузерный режим — это автоматизация интерфейса, а не API: правила сайта
    может нарушать автоматизация, поэтому не публикуйте так десятками постов
    в день и не обходите капчи.

Быстрый старт:
    python -m social_publisher login youtube      # войти и сохранить профиль
    python -m social_publisher learn youtube      # подсказать селекторы
    python -m social_publisher run plan.json --mode browser --yes
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..core.config import PACKAGE_DIR
from ..core.http import HTTPError
from ..core.journal import STATUS_ERROR, STATUS_MANUAL, STATUS_OK
from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext

SELECTORS_FILE = PACKAGE_DIR / "selectors.json"
INSTALL_HINT = (
    "Для браузерного режима установите Playwright:\n"
    "    pip install playwright\n"
    "    python -m playwright install chromium\n"
    "или укажите browser.channel = \"msedge\"/\"chrome\" в config.toml, "
    "чтобы использовать уже установленный браузер."
)


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# селекторы
# ---------------------------------------------------------------------------


def load_profiles(settings) -> dict[str, Any]:
    """Прочитать профили селекторов: встроенные + локальные переопределения."""
    profiles: dict[str, Any] = {}
    sources = [SELECTORS_FILE]
    local = settings.get("app.selectors_file")
    if local:
        sources.append(settings.resolve(local))
    sources.append(settings.home / "selectors.local.json")
    for path in sources:
        path = Path(path)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text("utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPError(f"Не удалось прочитать {path}: {exc}") from exc
        for name, profile in data.items():
            if name.startswith("_"):
                continue
            if isinstance(profile, dict):
                base = profiles.get(name, {})
                merged = {**base, **profile}
                if base.get("steps") and profile.get("steps"):
                    merged["steps"] = profile["steps"]
                profiles[name] = merged
    return profiles


def profile_for(settings, name: str) -> dict[str, Any]:
    return load_profiles(settings).get(name, {})


# ---------------------------------------------------------------------------
# сессия браузера
# ---------------------------------------------------------------------------


class BrowserSession:
    """Открывает браузер один раз на прогон и переиспользует его."""

    def __init__(self, settings, log=None):
        self.settings = settings
        self.log = log or (lambda _m: None)
        self._pw = None
        self._context = None
        self._chrome_pid = None

    # -- запуск -------------------------------------------------------------
    def _launch_kwargs(self) -> dict[str, Any]:
        profile_dir = self.settings.resolve(self.settings.get("browser.profile_dir", "state/browser-profile"))
        profile_dir.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": self.settings.browser_headless(),
            "slow_mo": self.settings.browser_slow_mo(),
            "viewport": {"width": 1440, "height": 900},
            "accept_downloads": True,
            "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
        }
        channel = self.settings.get("browser.channel")
        if channel:
            kwargs["channel"] = str(channel)
        return kwargs

    def start(self, *, headless: bool | None = None):
        if not playwright_available():
            raise RuntimeError(INSTALL_HINT)
        from playwright.sync_api import sync_playwright

        if self._context is None:
            self._pw = sync_playwright().start()
            kwargs = self._launch_kwargs()
            if headless is not None:
                kwargs["headless"] = headless
            try:
                self._context = self._pw.chromium.launch_persistent_context(**kwargs)
            except Exception as exc:
                hint = ""
                if "Executable doesn't exist" in str(exc) or "channel" in str(exc):
                    hint = "\n" + INSTALL_HINT
                raise RuntimeError(f"Не удалось запустить браузер: {exc}{hint}") from exc
            self.log(f"Браузер запущен (профиль: {kwargs['user_data_dir']})")
        return self._context

    @property
    def context(self):
        return self.start()

    def page(self):
        context = self.context
        pages = [p for p in context.pages if not p.is_closed()]
        if pages:
            page = pages[0]
        else:
            page = context.new_page()
        page.set_default_timeout(int(self.settings.get("browser.timeout_ms", 60_000)))
        return page

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        finally:
            self._context = None
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:  # pragma: no cover
                    pass
                self._pw = None

    # -- вспомогательное ----------------------------------------------------
    def screenshot(self, page, name: str) -> str:
        folder = self.settings.state_dir() / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        try:
            page.screenshot(path=str(path))
            return str(path)
        except Exception:  # pragma: no cover
            return ""


# ---------------------------------------------------------------------------
# универсальный браузерный адаптер
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


class BrowserPlatform(Platform):
    """Публикация по декларативному профилю из selectors.json."""

    def __init__(self, ctx: PublishContext, site: str, session: BrowserSession):
        super().__init__(ctx)
        self.site = site
        self.profile: dict[str, Any] = profile_for(self.settings, site)
        self.session = session
        self.mode = "browser"
        self.info = PlatformInfo(
            name=site,
            title=self.profile.get("title", site),
            supports_api=False,
            supports_browser=True,
            limits=self._limits(),
            notes=self.profile.get("notes", ""),
            docs=self.profile.get("url", ""),
        )

    def _limits(self) -> Limits:
        raw = self.profile.get("limits", {})
        return Limits(
            max_video_seconds=raw.get("max_video_seconds"),
            max_video_mb=raw.get("max_video_mb"),
            max_image_mb=raw.get("max_image_mb"),
            max_images=raw.get("max_images"),
            max_caption_chars=raw.get("max_caption_chars"),
            max_title_chars=raw.get("max_title_chars"),
            supports_video=raw.get("supports_video", True),
            supports_images=raw.get("supports_images", True),
            supports_carousel=True,
        )

    def check_env(self):
        from ..core.models import Issue

        if not self.profile:
            return [Issue("error", f"Нет профиля браузерного режима для «{self.site}» в selectors.json")]
        if not playwright_available():
            return [Issue("error", INSTALL_HINT)]
        return []

    # -- публикация ---------------------------------------------------------
    def publish(self, post: Post):
        if self.ctx.dry_run:
            return self.dry(post, f"{self.site}: тестовая публикация (браузер не открывался)")
        if not post.media:
            return self.skip(post, f"{self.site}: нечего публиковать — нет файлов")
        try:
            page = self.session.page()
            start_url = self.profile.get("url", "")
            if start_url:
                page.goto(start_url, wait_until="domcontentloaded")
            self._dismiss_overlays(page)
            self._apply_steps(page, "prepare", post)
            self._attach_files(page, post)
            self._fill_texts(page, post)
            self._apply_steps(page, "before_publish", post)
            if not self.ctx.ask(f"{self.site}: нажать «Опубликовать» для «{post.title_or_first_line()}»?"):
                return self.manual(post, f"{self.site}: публикация отложена (вы не подтвердили)")
            self._click_publish(page)
            url = self._wait_result(page)
            return self.result(
                post,
                STATUS_OK,
                url=url,
                message=f"{self.site}: опубликовано через браузер",
                post_key=url or "",
                screenshot=self.session.screenshot(page, f"{self.site}_{post.id}"),
            )
        except Exception as exc:
            shot = ""
            try:
                shot = self.session.screenshot(self.session.page(), f"error_{self.site}_{post.id}")
            except Exception:  # pragma: no cover
                pass
            return self.fail(
                post,
                f"{self.site} (браузер): {type(exc).__name__}: {exc}",
                screenshot=shot,
                hint=self.profile.get("troubleshooting", ""),
            )

    # -- шаги профиля -------------------------------------------------------
    def _apply_steps(self, page, phase: str, post: Post) -> None:
        for step in self.profile.get("steps", []):
            if step.get("when") not in (None, phase):
                continue
            action = step.get("action", "click")
            selectors = _as_list(step.get("selector"))
            if action == "click":
                self._click_any(page, selectors, optional=True)
            elif action == "fill":
                value = self._render(step.get("value", ""), post)
                self._fill_any(page, selectors, value, optional=True)
            elif action == "press":
                key = step.get("key", "Enter")
                self._first_visible(page, selectors, optional=True)
                page.keyboard.press(key)
            elif action == "wait":
                ms = int(step.get("ms", 1000))
                page.wait_for_timeout(min(ms, 60_000))
            elif action == "goto":
                page.goto(self._render(step.get("url", ""), post), wait_until="domcontentloaded")
            elif action == "upload":
                targets = self._pick_media(post, step.get("kinds", ["video", "image"]), step.get("limit"))
                if not targets:
                    continue
                self._first_visible(page, selectors)
                page.set_input_files(selectors[0], [str(t.path) for t in targets])

    def _attach_files(self, page, post: Post) -> None:
        selectors = _as_list(self.profile.get("file_input"))
        if not selectors:
            return
        kinds = self.profile.get("file_kinds", ["video", "image"])
        limit = self.profile.get("file_limit")
        targets = self._pick_media(post, kinds, limit)
        if not targets:
            raise RuntimeError("в посте нет файлов подходящего типа для этой площадки")
        if self.ctx.echo:
            self.ctx.echo(f"{self.site}: прикрепляю {', '.join(t.name for t in targets)}")
        element = self._first_visible(page, selectors)
        element.set_input_files([str(t.path) for t in targets])
        page.wait_for_timeout(int(self.profile.get("after_upload_wait_ms", 4000)))

    def _pick_media(self, post: Post, kinds: Iterable[str], limit: int | None):
        picked = [m for m in post.media if m.kind in set(kinds) and m.path.exists()]
        if limit:
            picked = picked[: int(limit)]
        return picked

    def _fill_texts(self, page, post: Post) -> None:
        title = self._render(self.profile.get("title_value", ""), post) or post.title_or_first_line()
        description = self._render(self.profile.get("description_value", ""), post) or post.full_text()
        tags = " ".join(t.lstrip("#") for t in post.tags)

        fields = ((title, "title_selector"), (description, "description"), (tags, "tags"))
        for text, key in fields:
            selectors = _as_list(self.profile.get(key))
            if not selectors or not text:
                continue
            limited = text[: int(self.profile.get(f"{key}_limit", len(text)))]
            self._fill_any(page, selectors, limited)

    def _render(self, template: str, post: Post) -> str:
        if not template:
            return ""
        values = {
            "title": post.title_or_first_line(),
            "description": post.full_text(),
            "tags": " ".join(t.lstrip("#") for t in post.tags),
            "hashtags": post.hashtags,
            "link": post.link,
            "category": post.category,
            "id": post.id,
        }
        def replace(match: re.Match) -> str:
            return str(values.get(match.group(1), ""))
        return re.sub(r"\{(\w+)\}", replace, template)

    # -- работа с элементами ------------------------------------------------
    def _first_visible(self, page, selectors: Iterable[str], optional: bool = False):
        timeout = int(self.settings.get("browser.timeout_ms", 60_000)) // max(1, len(list(selectors)) or 1)
        last_error: Exception | None = None
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=timeout)
                return locator
            except Exception as exc:  # noqa: BLE001 - перебираем варианты
                last_error = exc
                continue
        if optional:
            return None
        raise RuntimeError(f"не нашёл элемент ({', '.join(selectors)}): {last_error}")

    def _click_any(self, page, selectors: list[str], optional: bool = False) -> bool:
        element = self._first_visible(page, selectors, optional=optional)
        if element is None:
            return False
        try:
            element.click(timeout=15_000)
        except Exception:
            element.click(timeout=15_000, force=True)
        page.wait_for_timeout(500)
        return True

    def _fill_any(self, page, selectors: list[str], value: str, optional: bool = False) -> bool:
        element = self._first_visible(page, selectors, optional=optional)
        if element is None:
            return False
        try:
            element.fill(value)
        except Exception:
            # contenteditable иногда требует клика и ввода с клавиатуры
            element.click()
            page.keyboard.type(value)
        return True

    def _dismiss_overlays(self, page) -> None:
        for selector in _as_list(self.profile.get("dismiss")):
            try:
                page.locator(selector).first.click(timeout=1500)
            except Exception:
                continue

    def _click_publish(self, page) -> None:
        selectors = _as_list(self.profile.get("publish_button"))
        if not selectors:
            raise RuntimeError("в профиле не задан publish_button")
        if not self._click_any(page, selectors):
            raise RuntimeError("кнопка «Опубликовать» не найдена")

    def _wait_result(self, page) -> str:
        success = _as_list(self.profile.get("success"))
        timeout = int(self.settings.get("browser.result_timeout_ms", 240_000))
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            for selector in success:
                try:
                    page.locator(selector).first.wait_for(state="visible", timeout=2000)
                    return page.url
                except Exception:
                    continue
            pattern = self.profile.get("url_pattern")
            if pattern and re.search(pattern, page.url):
                return page.url
            page.wait_for_timeout(2000)
        # не дождались — возможно, идёт обработка: это не ошибка
        return page.url


# ---------------------------------------------------------------------------
# фабрики и сервисные функции
# ---------------------------------------------------------------------------


def browser_factories() -> list:
    """Все браузерные адаптеры по профилям selectors.json."""
    if not playwright_available() or not SELECTORS_FILE.exists():
        return []
    try:
        raw = json.loads(SELECTORS_FILE.read_text("utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    sites = [name for name, profile in raw.items() if not name.startswith("_") and isinstance(profile, dict)]
    factories = []
    for site in sites:
        def factory(ctx: PublishContext, _site: str = site):
            session = ctx.settings.data.setdefault("_browser_session", None)
            if session is None:
                session = BrowserSession(ctx.settings, log=ctx.log)
                ctx.settings.data["_browser_session"] = session
            return BrowserPlatform(ctx, _site, session)
        factories.append(factory)
    return factories


def open_for_login(settings, site: str, log=print, wait_for_enter=input) -> None:
    """Открыть страницу площадки, дать войти руками, сохранить профиль."""
    profile = profile_for(settings, site)
    session = BrowserSession(settings, log=log)
    try:
        page = session.page()
        url = profile.get("login_url") or profile.get("url") or "about:blank"
        log(f"Открываю {url}")
        page.goto(url, wait_until="domcontentloaded")
        log(
            "Войдите в аккаунт в открывшемся окне браузера.\n"
            "Когда закончите — вернитесь в терминал и нажмите Enter."
        )
        try:
            wait_for_enter()
        except EOFError:
            page.wait_for_timeout(120_000)
    finally:
        session.close()


def learn_selectors(settings, site: str, log=print) -> dict[str, Any]:
    """Подсказать селекторы: показать поля ввода и input[type=file] на странице."""
    profile = profile_for(settings, site)
    session = BrowserSession(settings, log=log)
    try:
        page = session.page()
        url = profile.get("url") or profile.get("login_url")
        if not url:
            raise RuntimeError(f"Для «{site}» нет url в selectors.json")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        data = page.evaluate(
            """() => {
                const describe = (el) => ({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    name: el.getAttribute('name'),
                    type: el.getAttribute('type'),
                    accept: el.getAttribute('accept'),
                    placeholder: el.getAttribute('placeholder'),
                    aria: el.getAttribute('aria-label'),
                    role: el.getAttribute('role'),
                    cls: (el.className || '').toString().slice(0, 120),
                });
                const files = [...document.querySelectorAll('input[type=file]')].map(describe);
                const fields = [...document.querySelectorAll('input[type=text], textarea, [contenteditable=true]')]
                    .slice(0, 25).map(describe);
                const buttons = [...document.querySelectorAll('button, [role=button]')]
                    .filter(el => el.offsetParent !== null)
                    .slice(0, 40)
                    .map(el => ({text: (el.innerText || '').trim().slice(0, 60), ...describe(el)}));
                return {files, fields, buttons, url: location.href, title: document.title};
            }"""
        )
        log(json.dumps(data, ensure_ascii=False, indent=2))
        log(
            "\nСкопируйте подходящие селекторы в selectors.local.json "
            "(он лежит рядом с config.toml и переопределяет встроенные)."
        )
        return data
    finally:
        session.close()
