"""Окно «Входные данные»: заполняется один раз, сохраняется в secrets.toml.

Проверяет данные до сохранения и умеет сразу войти в аккаунт:
  * YouTube — OAuth в браузере (кнопка «Войти в Google»);
  * остальные сервисы — «Войти в браузере» открывает окно, где вы входите
    руками, а профиль браузера сохраняется для браузерного режима.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, StringVar, Text, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk

from ..core.models import Issue
from . import services as service_specs
from .plan_builder import load_plan
from .tasks import AppContext, check_setup, form_fields, load_setup, save_setup_and_secrets


class SetupWindow(Toplevel):
    def __init__(self, master, ctx: AppContext, on_saved=None):
        super().__init__(master)
        self.ctx = ctx
        self.on_saved = on_saved
        self.title("Входные данные — заполняются один раз")
        self.geometry("760x640")
        self.minsize(680, 560)
        self.vars: dict[str, dict[str, StringVar]] = {}
        self.status_labels: dict[str, ttk.Label] = {}
        self.checks: dict[str, ttk.Label] = {}
        self._build()
        self.load_values()

    # -- интерфейс ----------------------------------------------------------
    def _build(self) -> None:
        header = ttk.Frame(self, padding=(16, 14, 16, 6))
        header.pack(fill=X)
        ttk.Label(
            header,
            text="Входные данные",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Заполните один раз: программа сохранит всё в защищённый файл рядом с собой.\n"
                "Нужны только те сервисы, куда собираетесь публиковать."
            ),
            foreground="#555555",
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True, padx=16, pady=8)
        self.notebook = notebook
        for name in service_specs.SERVICE_ORDER:
            self._build_tab(name, notebook)

        footer = ttk.Frame(self, padding=(16, 6, 16, 14))
        footer.pack(fill=X)
        ttk.Button(footer, text="Проверить всё", command=self.check_all).pack(side=LEFT)
        self.save_button = ttk.Button(footer, text="Сохранить", command=self.save)
        self.save_button.pack(side=RIGHT)
        ttk.Button(footer, text="Закрыть", command=self.destroy).pack(side=RIGHT, padx=(0, 8))
        self.summary = ttk.Label(footer, text="", foreground="#555555")
        self.summary.pack(side=LEFT, padx=12)

    def _build_tab(self, name: str, notebook: ttk.Notebook) -> None:
        spec = service_specs.spec(name)
        frame = ttk.Frame(notebook, padding=14)
        notebook.add(frame, text=spec.title)

        ttk.Label(frame, text=spec.title, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=f"Что нужно: {spec.setup_hint}",
            foreground="#555555",
            wraplength=660,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        form = ttk.Frame(frame)
        form.pack(fill=X)
        form.columnconfigure(1, weight=1)
        self.vars[name] = {}
        fields = form_fields(name)
        if not fields:
            ttk.Label(
                frame,
                text=(
                    "Для этого сервиса токены не нужны — достаточно один раз войти в браузере.\n"
                    "Нажмите «Войти в браузере» и закройте окно, когда войдёте."
                ),
                wraplength=660,
                justify="left",
            ).pack(anchor="w", pady=6)
        for row, (key, label, kind) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            widget = ttk.Entry(form, show="•" if kind == "secret" else "")
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            var = StringVar()
            widget.configure(textvariable=var)
            self.vars[name][key] = var
            if key == "client_secret_file":
                ttk.Button(
                    form, text="Выбрать…", command=lambda v=var: self._pick_client_secret(v)
                ).grid(row=row, column=2, padx=(8, 0))

        row = len(fields)
        if name == "youtube":
            ttk.Label(form, text="client_id / client_secret").grid(row=row, column=0, sticky="w", pady=4)
            pair = ttk.Frame(form)
            pair.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
            pair.columnconfigure(0, weight=1)
            pair.columnconfigure(1, weight=1)
            self.vars[name]["client_id"] = StringVar()
            self.vars[name]["client_secret"] = StringVar()
            ttk.Entry(pair, textvariable=self.vars[name]["client_id"]).grid(row=0, column=0, sticky="ew")
            ttk.Entry(pair, textvariable=self.vars[name]["client_secret"], show="•").grid(
                row=0, column=1, sticky="ew", padx=(6, 0)
            )
            ttk.Label(
                form,
                text="— необязательно, если указан client_secret.json",
                foreground="#777777",
            ).grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 6))

        actions = ttk.Frame(frame)
        actions.pack(fill=X, pady=(12, 4))
        if name == "youtube":
            ttk.Button(actions, text="Войти в Google", command=self.google_login).pack(side=LEFT)
            ttk.Label(
                actions,
                text="  откроется браузер, разрешите доступ к каналу",
                foreground="#777777",
            ).pack(side=LEFT)
        else:
            ttk.Button(
                actions, text="Войти в браузере", command=lambda n=name: self.browser_login(n)
            ).pack(side=LEFT)
            ttk.Label(
                actions,
                text="  откроется окно браузера — войдите и закройте его",
                foreground="#777777",
            ).pack(side=LEFT)

        notes = ttk.Label(
            frame,
            text="\n".join(f"• {line}" for line in spec.notes) or "",
            foreground="#555555",
            wraplength=660,
            justify="left",
        )
        notes.pack(anchor="w", pady=(10, 2))

        self.checks[name] = ttk.Label(frame, text="", wraplength=660, justify="left")
        self.checks[name].pack(anchor="w", pady=(8, 0))

    # -- данные -------------------------------------------------------------
    def load_values(self) -> None:
        saved = load_setup(self.ctx.home)
        loaded_from_plan = False
        for name, variables in self.vars.items():
            values = saved.get(name) or {}
            for key, var in variables.items():
                var.set(str(values.get(key) or ""))
        # подхватываем канал и прочее из saved
        self.saved_values = saved
        # если в папке уже есть план, подскажем в «Сервисах»
        plan_path = self.ctx.home / "plan.toml"
        if plan_path.exists():
            try:
                load_plan(plan_path)
                loaded_from_plan = True
            except Exception:
                loaded_from_plan = False
        if loaded_from_plan:
            self.summary.configure(text="Найден сохранённый plan.toml — его можно открыть из главного окна")
        self.check_all(show_boxes=False)

    def collect(self) -> dict[str, dict[str, str]]:
        values: dict[str, dict[str, str]] = {}
        for name, variables in self.vars.items():
            values[name] = {key: var.get().strip() for key, var in variables.items()}
        return values

    # -- действия -----------------------------------------------------------
    def _pick_client_secret(self, var: StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Выберите client_secret.json из Google Cloud",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if path:
            var.set(path)

    def check_all(self, show_boxes: bool = True) -> list[Issue]:
        values = self.collect()
        all_issues: list[Issue] = []
        for name in self.vars:
            issues = check_setup(name, values.get(name, {}), self.ctx.home)
            # при тихой проверке пустой сервис — не ошибка, его просто не настроили
            if not show_boxes and not any(values.get(name, {}).values()):
                issues = [i for i in issues if i.level != "error"]
            all_issues.extend(issues)
            errors = [i for i in issues if i.level == "error"]
            warnings = [i for i in issues if i.level == "warning"]
            label = self.checks.get(name)
            if label is None:
                continue
            if errors:
                label.configure(text="⚠ " + "\n⚠ ".join(i.text for i in errors), foreground="#a40000")
            elif warnings:
                label.configure(text="i " + "\n i ".join(i.text for i in warnings), foreground="#8a5a00")
            else:
                label.configure(text="✓ Данные заполнены", foreground="#0a6b2d")
        errors_total = sum(1 for i in all_issues if i.level == "error")
        if show_boxes and errors_total:
            messagebox.showwarning(
                "Есть замечания",
                f"Найдено ошибок: {errors_total}.\nИсправьте поля, отмеченные красным.",
                parent=self,
            )
        elif show_boxes:
            messagebox.showinfo("Проверка", "Все обязательные поля заполнены.", parent=self)
        self.summary.configure(
            text=f"ошибок: {errors_total} · предупреждений: {sum(1 for i in all_issues if i.level == 'warning')}"
        )
        return all_issues

    def save(self) -> None:
        values = self.collect()
        errors = [i for name in values for i in check_setup(name, values[name], self.ctx.home) if i.level == "error"]
        mandatory_missing = [i for i in errors if "Ещё не выполнен вход в Google" not in i.text]
        if mandatory_missing:
            if not messagebox.askyesno(
                "Сохранить с замечаниями?",
                "Есть ошибки:\n\n" + "\n".join(i.text for i in mandatory_missing[:8]) + "\n\nСохранить всё равно?",
                parent=self,
            ):
                return
        paths = save_setup_and_secrets(self.ctx, values)
        self._info("Сохранено", "Данные записаны:\n" + "\n".join(str(p) for p in paths))
        if self.on_saved:
            self.on_saved()

    def google_login(self) -> None:
        self.save_quiet()
        if not messagebox.askokcancel(
            "Вход в Google",
            "Сейчас откроется браузер с запросом доступа к вашему каналу.\n"
            "Выберите нужный аккаунт и разрешите загрузку видео.\n\n"
            "Токен сохранится и будет обновляться автоматически.",
            parent=self,
        ):
            return
        try:
            from ..platforms.base import build_registry

            registry = build_registry(self.ctx.publish_context(echo=lambda m: None))
            platform = registry.get("youtube", "api")
            if platform is None or not hasattr(platform, "auth"):
                raise RuntimeError("Не удалось создать адаптер YouTube")
            platform.auth(open_browser=True)
            messagebox.showinfo("Готово", "Вход выполнен, токен сохранён.", parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Не удалось войти",
                f"{exc}\n\nПроверьте client_secret.json и повторите.",
                parent=self,
            )
        self.check_all(show_boxes=False)

    def browser_login(self, name: str) -> None:
        self.save_quiet()
        try:
            from ..platforms.browser import BrowserSession

            if not _playwright_ok():
                messagebox.showerror("Нужен Playwright", _playwright_hint(), parent=self)
                return
            spec = service_specs.spec(name)
            session = BrowserSession(self.ctx.settings, log=lambda m: None)
            page = session.page()
            urls = {
                "vk": "https://vk.com/login",
                "telegram": "https://web.telegram.org/",
                "rutube": "https://rutube.ru/",
                "dzen": "https://dzen.ru/login",
                "instagram": "https://www.instagram.com/accounts/login/",
                "tiktok": "https://www.tiktok.com/login",
                "youtube": "https://accounts.google.com/",
            }
            url = urls.get(name, "about:blank")
            page.goto(url, wait_until="domcontentloaded")
            messagebox.showinfo(
                f"Вход в {spec.title}",
                "В открывшемся окне браузера войдите в аккаунт.\n"
                "Когда закончите — вернитесь сюда и нажмите ОК: профиль сохранится.",
                parent=self,
            )
            session.close()
            self._info("Готово", f"Профиль браузера для {spec.title} сохранён.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка", str(exc), parent=self)
        self.check_all(show_boxes=False)

    # -- мелочи -------------------------------------------------------------
    def save_quiet(self) -> None:
        save_setup_and_secrets(self.ctx, self.collect())

    def _info(self, title: str, text: str) -> None:
        messagebox.showinfo(title, text, parent=self)


def _playwright_ok() -> bool:
    try:
        from ..platforms.browser import playwright_available

        return playwright_available()
    except Exception:
        return False


def _playwright_hint() -> str:
    return (
        "Браузерный режим использует Playwright:\n\n"
        "    pip install playwright\n"
        "    python -m playwright install chromium\n\n"
        "Либо укажите в config.toml browser.channel = \"msedge\",\n"
        "чтобы использовать уже установленный Edge."
    )
