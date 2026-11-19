"""Главное окно: сервисы → проверка → запуск.

Порядок работы:
  1. «Входные данные…» — один раз заполнить токены/входы.
  2. Двойной клик по сервису (или «Открыть блокнот») — окно-блокнот сервиса.
  3. «Проверить» — таблица: файл, сервис, готовность.
  4. «Запустить» — публикация (с подтверждением по каждому посту).
"""

from __future__ import annotations

import queue
import time
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, HORIZONTAL, LEFT, RIGHT, VERTICAL, X, Y, BooleanVar, StringVar, Text, Tk
from tkinter import messagebox, ttk

from .. import __version__
from ..core.models import Plan
from . import services as service_specs
from .pad_window import PadWindow
from .plan_builder import build_plan, document_from_plan, load_plan, write_plan
from .setup_window import SetupWindow
from .tasks import (
    AppContext,
    CheckRow,
    MessageQueue,
    check_plan_file,
    publish_plan,
    rows_problem_count,
    run_in_thread,
)

PLAN_NAME = "plan.toml"


class App(Tk):
    def __init__(self, home: str | Path | None = None):
        super().__init__()
        self.queue = MessageQueue()
        self.log_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.home = Path(home).expanduser().resolve() if home else Path.cwd()
        self.ctx = AppContext.open(self.home, echo=self._log_threadsafe)
        self.pads: dict[str, PadWindow] = {}
        self.documents: dict[str, dict] = {}
        self.shared_photos: list[dict] = []
        self.busy = False
        self.auto_continue = False
        self._build()
        self._load_existing()
        self._refresh_rows()
        self._log(f"Папка программы: {self.home}")
        self._poll()

    # -- сборка интерфейса --------------------------------------------------
    def _build(self) -> None:
        self.title(f"Публикатор клипов и фото — {self.home.name or self.home}")
        self.geometry("1120x760")
        self.minsize(960, 640)
        self._style()

        header = ttk.Frame(self, padding=(16, 12, 16, 4))
        header.pack(fill=X)
        ttk.Label(header, text="Что публикуем куда", font=("Segoe UI", 15, "bold")).pack(side=LEFT)
        self.plan_label = ttk.Label(header, text="", foreground="#666666")
        self.plan_label.pack(side=LEFT, padx=12)
        ttk.Button(header, text="Входные данные…", command=self.open_setup).pack(side=RIGHT)
        ttk.Button(header, text="Открыть готовый план…", command=self.open_plan).pack(side=RIGHT, padx=(0, 8))

        main = ttk.Panedwindow(self, orient=VERTICAL)
        main.pack(fill=BOTH, expand=True, padx=16, pady=(4, 8))

        # --- таблица сервисов
        upper = ttk.Frame(main)
        main.add(upper, weight=1)
        columns = ("service", "accepts", "files", "posts", "state")
        self.tree = ttk.Treeview(upper, columns=columns, show="headings", height=9)
        for column, title, width in (
            ("service", "Сервис", 220),
            ("accepts", "Что принимает", 150),
            ("files", "Файлов", 90),
            ("posts", "Постов", 90),
            ("state", "Состояние", 460),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w" if column != "files" else "center")
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(upper, orient=VERTICAL, command=self.tree.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _e: self.open_selected_pad())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_run_state())

        hints = ttk.Frame(main, padding=(0, 6, 0, 0))
        main.add(hints, weight=0)
        row = ttk.Frame(hints)
        row.pack(fill=X)
        ttk.Button(row, text="Открыть блокнот", command=self.open_selected_pad).pack(side=LEFT)
        ttk.Button(row, text="Открыть все блокноты", command=self.open_all_pads).pack(side=LEFT, padx=8)
        ttk.Button(row, text="Собрать план", command=self.build_and_check).pack(side=LEFT)
        ttk.Label(
            row,
            text="  двойной клик по сервису открывает его блокнот",
            foreground="#777777",
        ).pack(side=LEFT, padx=8)

        # --- проверка
        lower = ttk.Frame(main)
        main.add(lower, weight=2)
        check_header = ttk.Frame(lower)
        check_header.pack(fill=X)
        ttk.Label(check_header, text="Проверка перед запуском", font=("Segoe UI", 11, "bold")).pack(side=LEFT)
        self.check_summary = ttk.Label(check_header, text="", foreground="#555555")
        self.check_summary.pack(side=LEFT, padx=12)
        ttk.Button(check_header, text="Проверить", command=self.check_only).pack(side=RIGHT)

        columns = ("post", "service", "file", "result")
        self.checks = ttk.Treeview(lower, columns=columns, show="headings", height=10)
        for column, title, width in (
            ("post", "Пост", 260),
            ("service", "Сервис", 130),
            ("file", "Файл", 260),
            ("result", "Результат проверки", 460),
        ):
            self.checks.heading(column, text=title)
            self.checks.column(column, width=width, anchor="w")
        self.checks.pack(side=LEFT, fill=BOTH, expand=True, pady=(4, 0))
        cscroll = ttk.Scrollbar(lower, orient=VERTICAL, command=self.checks.yview)
        cscroll.pack(side=RIGHT, fill=Y)
        self.checks.configure(yscrollcommand=cscroll.set)
        self.checks.tag_configure("error", foreground="#a40000")
        self.checks.tag_configure("warn", foreground="#8a5a00")
        self.checks.tag_configure("ok", foreground="#0a6b2d")

        # --- журнал и запуск
        bottom = ttk.Frame(self, padding=(16, 0, 16, 12))
        bottom.pack(fill=X)
        log_frame = ttk.Frame(bottom)
        log_frame.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.log = Text(log_frame, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(side=LEFT, fill=BOTH, expand=True)
        lscroll = ttk.Scrollbar(log_frame, orient=VERTICAL, command=self.log.yview)
        lscroll.pack(side=RIGHT, fill=Y)
        self.log.configure(yscrollcommand=lscroll.set)

        run_row = ttk.Frame(bottom)
        run_row.pack(fill=X)
        self.mode_var = StringVar(value="auto")
        ttk.Label(run_row, text="Режим:").pack(side=LEFT)
        ttk.Combobox(
            run_row,
            textvariable=self.mode_var,
            values=["auto", "api", "browser", "manual"],
            width=9,
            state="readonly",
        ).pack(side=LEFT, padx=(4, 12))
        self.dry_var = BooleanVar(value=True)
        ttk.Checkbutton(run_row, text="Только проверка (ничего не публиковать)", variable=self.dry_var).pack(
            side=LEFT
        )
        self.force_var = BooleanVar(value=False)
        ttk.Checkbutton(run_row, text="Повторить уже опубликованное", variable=self.force_var).pack(
            side=LEFT, padx=12
        )
        self.auto_var = BooleanVar(value=False)
        ttk.Checkbutton(
            run_row,
            text="Без подтверждений",
            variable=self.auto_var,
        ).pack(side=LEFT)

        self.journal_button = ttk.Button(run_row, text="Журнал", command=self.show_journal)
        self.journal_button.pack(side=RIGHT)
        self.progress = ttk.Progressbar(run_row, mode="indeterminate", length=140)
        self.progress.pack(side=RIGHT, padx=12)
        self.run_button = ttk.Button(run_row, text="Запустить", command=self.run_publish)
        self.run_button.pack(side=RIGHT, padx=8)

        self.status = ttk.Label(self, text="Готов", foreground="#555555", padding=(16, 0, 16, 8))
        self.status.pack(fill=X)

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            try:
                style.theme_use("clam")
            except Exception:
                pass
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        style.configure("TButton", padding=(10, 4))

    # -- загрузка/сохранение ------------------------------------------------
    def _plan_path(self) -> Path:
        return self.home / PLAN_NAME

    def _load_existing(self) -> None:
        path = self._plan_path()
        if not path.exists():
            self._log("Плана пока нет: заполните блокноты и нажмите «Собрать план».")
            return
        try:
            plan = load_plan(path)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Не удалось прочитать {path.name}: {exc}")
            return
        document = document_from_plan(plan, service_specs.SERVICE_ORDER)
        self.documents = document.get("services", {})
        self.shared_photos = document.get("photo_sources", [])
        self._log(f"Загружен сохранённый план: {path} (постов: {len(plan.get('posts') or [])})")
        self.plan_label.configure(text=path.name)

    def collect_documents(self) -> dict:
        services = {}
        for name, pad in self.pads.items():
            services[name] = pad.get_data()
        for name, data in self.documents.items():
            services.setdefault(name, data)
        photos: list[dict] = list(self.shared_photos)
        for data in services.values():
            photos.extend(data.get("photo_sources") or [])
        return {"services": services, "photo_sources": photos}

    def build_and_check(self) -> Path | None:
        document = self.collect_documents()
        plan = build_plan(document)
        if not plan["posts"]:
            messagebox.showinfo(
                "Пока нечего публиковать",
                "Откройте блокноты сервисов и добавьте файлы и текст.\n"
                "Блокнот открывается двойным кликом по строке сервиса.",
                parent=self,
            )
            return None
        path = write_plan(plan, self._plan_path())
        self.documents = document.get("services", {})
        self.plan_label.configure(text=f"{path.name} · постов: {len(plan['posts'])}")
        self._log(f"План собран: {path} · постов: {len(plan['posts'])}")
        self.check_plan()
        return path

    # -- строки сервисов ----------------------------------------------------
    def _refresh_rows(self) -> None:
        selected = self.tree.selection()
        current = selected[0] if selected else None
        self.tree.delete(*self.tree.get_children())
        for name in service_specs.SERVICE_ORDER:
            spec = service_specs.spec(name)
            data = self.documents.get(name) or {}
            files = len(data.get("media") or [])
            posts = len(data.get("posts") or [])
            state = self._service_state(name)
            self.tree.insert(
                "",
                END,
                iid=name,
                values=(spec.title, _accepts_label(spec.accepts), files, posts, state),
            )
        if current and current in self.tree.get_children():
            self.tree.selection_set(current)
        self._update_run_state()

    def _service_state(self, name: str) -> str:
        if self.busy:
            return "…"
        from .tasks import check_setup, load_setup

        values = load_setup(self.home).get(name) or {}
        issues = check_setup(name, values, self.home)
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        has_content = bool(self.documents.get(name))
        if not has_content:
            return "не заполнен"
        if errors:
            return "⚠ " + errors[0].text[:80]
        if warnings:
            return "i " + warnings[0].text[:80]
        return "✓ готов"

    def _update_run_state(self) -> None:
        if self.busy:
            self.run_button.state(["disabled"])
        else:
            self.run_button.state(["!disabled"])

    # -- окна ---------------------------------------------------------------
    def open_setup(self) -> None:
        SetupWindow(self, self.ctx, on_saved=self._after_setup)

    def _after_setup(self) -> None:
        self.ctx.reload_secrets()
        self._refresh_rows()
        self._log("Входные данные сохранены.")

    def open_plan(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Открыть план", filetypes=[("План", "*.toml *.json"), ("Все файлы", "*.*")], parent=self
        )
        if not path:
            return
        try:
            plan = load_plan(path)
            document = document_from_plan(plan, service_specs.SERVICE_ORDER)
            write_plan(plan, self._plan_path())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Не удалось открыть план", str(exc), parent=self)
            return
        self.documents = document.get("services", {})
        self.shared_photos = document.get("photo_sources", [])
        self._log(f"Открыт план: {path}")
        self._refresh_rows()
        self.check_plan()

    def open_selected_pad(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Выберите сервис", "Сначала выберите строку сервиса в таблице.", parent=self)
            return
        self.open_pad(selection[0])

    def open_all_pads(self) -> None:
        for name in service_specs.SERVICE_ORDER:
            self.open_pad(name, focus=False)

    def open_pad(self, name: str, focus: bool = True) -> None:
        existing = self.pads.get(name)
        if existing is not None and existing.winfo_exists():
            if focus:
                existing.lift()
                existing.focus_force()
            return
        pad = PadWindow(self, name, on_change=self._on_pad_change, on_close=lambda n: self.pads.pop(n, None))
        data = self.documents.get(name)
        if data:
            pad.set_data(data)
        self.pads[name] = pad
        if focus:
            pad.lift()

    def _on_pad_change(self, name: str, applied: bool = False) -> None:
        pad = self.pads.get(name)
        if pad is None:
            return
        self.documents[name] = pad.get_data()
        if applied:
            self._refresh_rows()

    # -- проверка -----------------------------------------------------------
    def check_only(self) -> None:
        path = self._plan_path()
        if not path.exists():
            path = self.build_and_check()
            if path is None:
                return
        else:
            self.build_and_check()
        self.check_plan()

    def check_plan(self) -> list[CheckRow]:
        path = self._plan_path()
        if not path.exists():
            self.check_summary.configure(text="плана нет")
            return []
        self._set_status("Проверяю файлы и сервисы…")
        try:
            rows = check_plan_file(path, self.ctx, mode=self.mode_var.get())
        except Exception as exc:  # noqa: BLE001
            self._log(f"Ошибка проверки: {exc}")
            self.check_summary.configure(text="ошибка проверки", foreground="#a40000")
            return []
        self.checks.delete(*self.checks.get_children())
        for row in rows:
            self.checks.insert(
                "", END, values=(row.post_id, row.service, row.file, row.message), tags=(row.status,)
            )
        errors, warnings = rows_problem_count(rows)
        self.check_summary.configure(
            text=f"строк: {len(rows)} · ошибок: {errors} · предупреждений: {warnings}",
            foreground="#a40000" if errors else ("#8a5a00" if warnings else "#0a6b2d"),
        )
        self._set_status("Проверка закончена" if not errors else "Есть ошибки — исправьте перед запуском")
        return rows

    # -- запуск -------------------------------------------------------------
    def run_publish(self) -> None:
        if self.busy:
            return
        path = self.build_and_check()
        if path is None:
            return
        rows = self.check_plan()
        errors, _warnings = rows_problem_count(rows)
        if errors:
            if not messagebox.askyesno(
                "Есть ошибки",
                f"Проверка нашла ошибок: {errors}.\n"
                "Публикация с ошибками обычно не проходит.\n\n"
                "Запустить всё равно (ошибочные пары будут пропущены)?",
                parent=self,
            ):
                return
        dry = self.dry_var.get()
        if not dry:
            if not messagebox.askyesno(
                "Публикация",
                "Начать публикацию?\n"
                + (
                    "Подтверждения выключены — всё уйдёт сразу."
                    if self.auto_var.get()
                    else "Перед каждой отправкой будет вопрос подтверждения."
                ),
                parent=self,
            ):
                return
        if not self._has_configured_service():
            messagebox.showinfo(
                "Сначала входные данные",
                "Ни один сервис пока не настроен.\n\n"
                "Нажмите «Входные данные…» и заполните хотя бы один сервис "
                "(проще всего Telegram), затем повторите запуск.",
                parent=self,
            )
            return
        self.busy = True
        self._update_run_state()
        self.auto_continue = self.auto_var.get()
        self._set_status("Идёт публикация…" if not dry else "Тестовый прогон…")
        self.progress.start(12)
        self._log("—" * 60)
        self._log(f"Запуск: режим {self.mode_var.get()}, {'тест' if dry else 'публикация'}"
                  + (", без подтверждений" if self.auto_continue else ", с подтверждениями"))
        mode = self.mode_var.get()
        force = self.force_var.get()

        def work():
            return publish_plan(
                path,
                self.ctx,
                mode=mode,
                dry_run=dry,
                force=force,
                confirm=None if self.auto_continue or dry else self._confirm_from_thread,
                echo=self._log_threadsafe,
            )

        run_in_thread(work, self.queue)

    def _confirm_from_thread(self, question: str) -> bool:
        """Спросить пользователя из фонового потока — через окно."""
        answer = {"value": False}
        done = __import__("threading").Event()

        def ask():
            answer["value"] = messagebox.askyesno("Опубликовать?", question, parent=self)
            done.set()

        self.after(0, ask)
        done.wait(timeout=900)
        return answer["value"]

    def show_journal(self) -> None:
        window = Toplevel_(self)
        window.title("Журнал публикаций")
        window.geometry("900x520")
        text = Text(window, wrap="none", font=("Consolas", 9))
        text.pack(fill=BOTH, expand=True, padx=10, pady=10)
        entries = list(self.ctx.journal.entries)
        if not entries:
            text.insert(END, "Журнал пуст: публикаций ещё не было.")
        for entry in entries:
            mark = {"ok": "✓", "error": "✗", "skipped": "-", "manual": "→", "dry-run": "тест"}.get(entry.status, "?")
            text.insert(
                END,
                f"{mark} {entry.timestamp}  {entry.platform:<10} {entry.post_id:<28} {entry.status:<8} "
                f"{entry.url or entry.message}\n",
            )
        text.configure(state="disabled")
        ttk.Button(window, text="Закрыть", command=window.destroy).pack(pady=(0, 10))

    # -- сообщения из фона --------------------------------------------------
    def _log_threadsafe(self, message: str) -> None:
        self.log_queue.put(("log", message))

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(str(payload))
        for kind, payload in self.queue.drain():
            if kind == "done":
                self._finish(payload)
            elif kind == "error":
                self._finish(None, error=str(payload))
        self.after(150, self._poll)

    def _finish(self, outcome, error: str | None = None) -> None:
        self.busy = False
        self.progress.stop()
        self._update_run_state()
        self._refresh_rows()
        if error:
            self._log(f"ОШИБКА: {error}")
            self._set_status("Ошибка — см. журнал ниже")
            messagebox.showerror("Ошибка", error, parent=self)
            return
        if outcome is not None:
            summary = (
                f"опубликовано: {outcome.ok} · пропущено: {outcome.skipped} · "
                f"вручную: {outcome.manual} · ошибок: {outcome.errors}"
            )
            if outcome.dry:
                summary += f" · тестовый прогон: {outcome.dry}"
            self._log("Итог: " + summary)
            self._set_status(summary)
        else:
            self._set_status("Готов")

    def _has_configured_service(self) -> bool:
        from .tasks import check_setup, load_setup

        values = load_setup(self.home)
        for name, service_values in values.items():
            if not any(str(v).strip() for v in (service_values or {}).values() if isinstance(v, str)):
                continue
            if not [i for i in check_setup(name, service_values, self.home) if i.level == "error"]:
                return True
        return False

    # -- мелочи -------------------------------------------------------------
    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(END, time.strftime("%H:%M:%S  ") + message + "\n")
        self.log.see(END)
        self.log.configure(state="disabled")

    def _log(self, message: str) -> None:
        self._append_log(message)

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def destroy(self) -> None:
        session = (self.ctx.settings.data or {}).get("_browser_session")
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        super().destroy()


def Toplevel_(master):  # noqa: N802 - маленькая обёртка, чтобы не тянуть импорт наверх
    from tkinter import Toplevel

    return Toplevel(master)


def _accepts_label(accepts: str) -> str:
    return {"video": "видео", "images": "фото", "any": "видео и фото"}.get(accepts, accepts)


def main(home: str | Path | None = None) -> int:
    app = App(home)
    app.mainloop()
    return 0
