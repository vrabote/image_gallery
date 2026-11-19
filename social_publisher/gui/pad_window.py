"""Окно-блокнот одного сервиса.

Слева — что публикуем (файлы и общие поля: теги, категория, ссылка),
справа — большой блокнот: первая строка поста = заголовок, остальное =
описание, посты разделяются строкой «---».

Окно ничего не публикует: оно только заполняет план. Публикация — после
проверки, из главного окна.
"""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    LEFT,
    RIGHT,
    VERTICAL,
    X,
    Y,
    StringVar,
    Text,
    Toplevel,
    filedialog,
    messagebox,
)
from tkinter import ttk

from . import services as service_specs
from .plan_builder import parse_pad_text, split_posts

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


class PadWindow(Toplevel):
    """Один сервис = одно окно-блокнот."""

    def __init__(self, master, service: str, on_change=None, on_close=None):
        super().__init__(master)
        self.service = service
        self.spec = service_specs.spec(service)
        self.on_change = on_change
        self.on_close = on_close
        self.media: list[str] = []
        self.photos: list[dict[str, str]] = []
        self.photo_text = None
        self.title(f"Блокнот — {self.spec.title}")
        self.geometry("1000x680")
        self.minsize(760, 520)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # -- построение ---------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill=X)
        ttk.Label(top, text=self.spec.title, font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(
            top,
            text=f"  {service_specs.limits_line(self.service)}",
            foreground="#666666",
        ).pack(side=LEFT)
        self.counter = ttk.Label(top, text="", foreground="#0a6b2d")
        self.counter.pack(side=RIGHT)

        body = ttk.Panedwindow(self, orient=HORIZONTAL)
        body.pack(fill=BOTH, expand=True, padx=12, pady=6)
        body.add(self._build_media_panel(body), weight=1)
        body.add(self._build_text_panel(body), weight=3)

        bottom = ttk.Frame(self, padding=(12, 4, 12, 12))
        bottom.pack(fill=X)
        self.hint = ttk.Label(bottom, text="", foreground="#8a5a00")
        self.hint.pack(side=LEFT)
        ttk.Button(bottom, text="Применить", command=self._apply).pack(side=RIGHT)
        ttk.Button(bottom, text="Отмена", command=self._close).pack(side=RIGHT, padx=(0, 8))

    def _build_media_panel(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(0, 0, 8, 0))
        ttk.Label(frame, text="Что публикуем", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=BOTH, expand=True, pady=(4, 6))
        self.media_list = Text(list_frame, height=10, wrap="none", font=("Consolas", 9))
        self.media_list.pack(side=LEFT, fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.media_list.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.media_list.configure(yscrollcommand=scroll.set, state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(fill=X)
        ttk.Button(buttons, text="Добавить файлы…", command=self.add_files).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Убрать выбранный", command=self.remove_selected).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Очистить", command=self.clear_media).pack(fill=X, pady=2)

        if service_specs.spec(self.service).accepts in ("images", "any"):
            ttk.Separator(frame).pack(fill=X, pady=8)
            ttk.Label(frame, text="Подписи к фото", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(
                frame,
                text="Необязательно: подпись добавится в описание поста.",
                foreground="#777777",
                wraplength=240,
                justify="left",
            ).pack(anchor="w")
            self.photo_text = Text(frame, height=5, wrap="word", font=("Segoe UI", 9))
            self.photo_text.pack(fill=X, pady=(4, 0))
            ttk.Label(
                frame,
                text="Формат: путь_к_файлу | подпись",
                foreground="#777777",
                font=("Segoe UI", 8),
            ).pack(anchor="w")

        ttk.Separator(frame).pack(fill=X, pady=8)
        ttk.Label(frame, text="Общее для всех постов", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        form = ttk.Frame(frame)
        form.pack(fill=X, pady=(4, 0))
        form.columnconfigure(1, weight=1)
        self.header_vars: dict[str, StringVar] = {}
        rows = [
            ("title", "Заголовок (если в блокноте пусто)"),
            ("tags", "Теги (через запятую)"),
            ("category", "Категория / плейлист"),
            ("link", "Ссылка"),
        ]
        for row, (key, label) in enumerate(rows):
            ttk.Label(form, text=label, wraplength=240, justify="left").grid(
                row=row, column=0, sticky="w", pady=3
            )
            var = StringVar()
            var.trace_add("write", lambda *_: self._changed())
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)
            self.header_vars[key] = var
        return frame

    def _build_text_panel(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        tip = (
            "Первая строка поста — заголовок, дальше — текст.\n"
            "Несколько постов в этом блокноте разделяйте строкой  ---"
        )
        ttk.Label(frame, text=tip, foreground="#666666", justify="left").pack(anchor="w")
        wrapper = ttk.Frame(frame)
        wrapper.pack(fill=BOTH, expand=True, pady=(4, 0))
        self.text = Text(wrapper, wrap="word", undo=True, font=("Segoe UI", 10))
        self.text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(wrapper, orient=VERTICAL, command=self.text.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.insert("1.0", self.spec.placeholder)
        self.text.bind("<<Modified>>", self._on_modified)
        ttk.Label(
            frame,
            text="Символов: ",
            foreground="#777777",
        ).pack(anchor="e")

        self.text.tag_configure("separator", foreground="#999999")
        return frame

    # -- файлы --------------------------------------------------------------
    def add_files(self) -> None:
        accepts = self.spec.accepts
        if accepts == "video":
            types = [("Видео", "*.mp4 *.mov *.m4v *.webm *.mkv *.avi"), ("Все файлы", "*.*")]
        elif accepts == "images":
            types = [("Изображения", "*.jpg *.jpeg *.png *.webp *.gif *.bmp"), ("Все файлы", "*.*")]
        else:
            types = [
                ("Видео и фото", "*.mp4 *.mov *.m4v *.webm *.jpg *.jpeg *.png *.webp *.gif"),
                ("Все файлы", "*.*"),
            ]
        paths = filedialog.askopenfilenames(title=f"Файлы для {self.spec.title}", filetypes=types, parent=self)
        added = 0
        for path in paths:
            suffix = Path(path).suffix.lower()
            if accepts == "video" and suffix not in VIDEO_EXT:
                messagebox.showwarning(
                    "Только видео", f"{self.spec.title} принимает видео, а не {suffix}.", parent=self
                )
                continue
            if accepts == "images" and suffix not in IMAGE_EXT:
                messagebox.showwarning("Только изображения", f"{Path(path).name} — не изображение.", parent=self)
                continue
            if path not in self.media:
                self.media.append(path)
                if suffix in IMAGE_EXT:
                    self.photos.append({"file": path, "caption": ""})
                added += 1
        if added:
            self._refresh_media()
            self._changed()

    def remove_selected(self) -> None:
        try:
            index = int(self.media_list.index("insert").split(".")[0]) - 1
        except (ValueError, TypeError):
            return
        if 0 <= index < len(self.media):
            removed = self.media.pop(index)
            self.photos = [p for p in self.photos if p["file"] != removed]
            self._refresh_media()
            self._changed()

    def clear_media(self) -> None:
        if self.media and messagebox.askyesno("Очистить", "Убрать все файлы из этого блокнота?", parent=self):
            self.media.clear()
            self.photos.clear()
            self._refresh_media()
            self._changed()

    def _refresh_media(self) -> None:
        self.media_list.configure(state="normal")
        self.media_list.delete("1.0", END)
        for path in self.media:
            try:
                size = os.path.getsize(path) / 1e6
            except OSError:
                size = 0
            self.media_list.insert(END, f"{Path(path).name}  ({size:.1f} МБ)\n")
        self.media_list.configure(state="disabled")
        self._update_counter()

    # -- текст --------------------------------------------------------------
    def _on_modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._changed()

    def _changed(self) -> None:
        self._update_counter()
        if self.on_change:
            self.on_change(self.service)

    def _update_counter(self) -> None:
        text = self.text.get("1.0", END)
        posts = len(parse_pad_text(text))
        chars = len(text.strip())
        limit = self.spec.default_limits.get("text")
        note = ""
        if limit and chars > limit * max(1, posts):
            note = "  ⚠ текст длиннее лимита"
        self.counter.configure(
            text=f"постов: {posts} · символов: {chars} · файлов: {len(self.media)}{note}",
            foreground="#a40000" if note else "#0a6b2d",
        )

    # -- данные -------------------------------------------------------------
    def get_data(self) -> dict:
        captions: dict[str, str] = {}
        if self.photo_text is not None:
            for line in self.photo_text.get("1.0", END).splitlines():
                if "|" in line:
                    path, caption = line.split("|", 1)
                    captions[path.strip()] = caption.strip()
        photos = []
        for item in self.photos:
            file_path = item["file"]
            photos.append({"file": file_path, "caption": captions.get(file_path, item.get("caption", ""))})
        return {
            "header": {key: var.get().strip() for key, var in self.header_vars.items()},
            "media": list(self.media),
            "photo_sources": photos,
            "text": self.text.get("1.0", END),
        }

    def set_data(self, data: dict) -> None:
        header = data.get("header") or {}
        for key, var in self.header_vars.items():
            var.set(str(header.get(key) or ""))
        self.media = [str(m) for m in (data.get("media") or [])]
        self.photos = [dict(p) for p in (data.get("photo_sources") or [])]
        text = str(data.get("text") or "")
        self.text.delete("1.0", END)
        self.text.insert("1.0", text or self.spec.placeholder)
        captions = {p["file"]: p.get("caption", "") for p in self.photos if p.get("caption")}
        if captions and self.photo_text is not None:
            self.photo_text.delete("1.0", END)
            for path, caption in captions.items():
                self.photo_text.insert(END, f"{path} | {caption}\n")
        self._refresh_media()
        self._update_counter()

    # -- завершение ---------------------------------------------------------
    def _apply(self) -> None:
        if not self.media and not self.text.get("1.0", END).strip():
            messagebox.showwarning("Пусто", "Добавьте файлы или текст поста.", parent=self)
            return
        if self.on_change:
            self.on_change(self.service, applied=True)
        self._close()

    def _close(self) -> None:
        if self.on_close:
            self.on_close(self.service)
        self.destroy()
