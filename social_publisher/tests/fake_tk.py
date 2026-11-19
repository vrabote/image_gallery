"""Минимальная заглушка tkinter для тестов без графической среды.

Не рисует ничего, но запоминает вызовы и поддерживает те части поведения,
которые нужны нашему окну: Text (содержимое), StringVar/BooleanVar,
Treeview (строки), after (отложенные вызовы складываются в список).
"""

from __future__ import annotations

import sys
import types
from typing import Any

BOTH = "both"
X = "x"
Y = "y"
LEFT = "left"
RIGHT = "right"
END = "end"
VERTICAL = "vertical"
HORIZONTAL = "horizontal"


class Variable:
    def __init__(self, master=None, value=None, **kwargs):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def trace_add(self, *_args, **_kwargs):
        return "trace"


class StringVar(Variable):
    def __init__(self, master=None, value="", **kwargs):
        super().__init__(master, value if value is not None else "")


class BooleanVar(Variable):
    def __init__(self, master=None, value=False, **kwargs):
        super().__init__(master, bool(value))


class _Widget:
    """Любой виджет: принимает любые параметры, методы — запись вызовов."""

    def __init__(self, master=None, **kwargs):
        self.master = master
        self.kwargs = kwargs
        self.calls: list[tuple[str, tuple, dict]] = []
        self.winfo_children_list: list[_Widget] = []

    # геометрия
    def pack(self, *args, **kwargs):
        return self

    def grid(self, *args, **kwargs):
        return self

    def place(self, *args, **kwargs):
        return self

    def pack_forget(self, *args, **kwargs):
        return None

    def grid_configure(self, *args, **kwargs):
        return None

    def columnconfigure(self, *args, **kwargs):
        return None

    def rowconfigure(self, *args, **kwargs):
        return None

    def configure(self, *args, **kwargs):
        self.calls.append(("configure", args, kwargs))
        return None

    config = configure

    def cget(self, key):
        return self.kwargs.get(key, "")

    def bind(self, *args, **kwargs):
        return None

    def winfo_exists(self):
        return True

    def winfo_children(self):
        children = list(self.winfo_children_list)
        for maybe in getattr(self, "_children_refs", []):
            children.append(maybe)
        return children

    def destroy(self):
        return None

    def lift(self):
        return None

    def focus_force(self):
        return None

    def title(self, *_args):
        return None

    def geometry(self, *_args):
        return None

    def minsize(self, *_args):
        return None

    def protocol(self, *_args):
        return None

    def state(self, *_args):
        return None

    def set(self, *_args):
        return None

    def add(self, *args, **kwargs):
        return None

    #: методы виджетов, которые «есть» у любого элемента
    _WIDGET_METHODS = frozenset(
        {
            "pack", "grid", "place", "configure", "config", "cget", "bind", "yview",
            "xview", "see", "insert", "delete", "get", "index", "tag_add", "tag_bind",
            "tag_remove", "focus_set", "focus_force", "lift", "lower", "update",
            "update_idletasks", "winfo_width", "winfo_height", "winfo_exists",
            "winfo_children", "state", "invoke", "event_generate", "after",
            "start", "stop", "set", "add", "title", "geometry", "minsize",
            "protocol", "destroy", "wait_window", "grab_set", "transient",
            "rowconfigure", "columnconfigure", "panes", "identify", "bbox",
        }
    )

    def __getattr__(self, name):
        if name.startswith("_") or name not in self._WIDGET_METHODS:
            raise AttributeError(name)

        def recorder(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return None

        return recorder


class Text(_Widget):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._content = ""
        self._state = "normal"
        self.tags: dict[str, dict] = {}
        self._modified = False
        self._insert_index = 0

    # содержимое
    def insert(self, index, text):
        self._content = (self._content or "") + str(text)
        self.calls.append(("insert", (index, text), {}))

    def get(self, start="1.0", end="end"):
        return self._content

    def delete(self, start, end=None):
        self._content = ""
        self.calls.append(("delete", (start, end), {}))

    def see(self, index):
        return None

    def edit_modified(self, value=None):
        if value is None:
            return self._modified
        self._modified = bool(value)
        return self._modified

    def tag_configure(self, name, **kwargs):
        self.tags[name] = kwargs

    def index(self, index):
        return "1.0"

    def yview(self, *args):
        return None

    def configure(self, **kwargs):
        if "state" in kwargs:
            self._state = kwargs["state"]
        self.calls.append(("configure", (), kwargs))
        return None


class Treeview(_Widget):
    def __init__(self, master=None, columns=(), show="headings", **kwargs):
        super().__init__(master, **kwargs)
        self.columns = list(columns)
        self.rows: dict[str, dict[str, Any]] = {}
        self._selection: tuple[str, ...] = ()
        self.tags: dict[str, dict] = {}
        self.headings: dict[str, str] = {}
        self.order: list[str] = []
        self._counter = 0

    def heading(self, column, text="", **kwargs):
        self.headings[column] = text

    def column(self, column, **kwargs):
        return None

    def tag_configure(self, name, **kwargs):
        self.tags[name] = kwargs

    def insert(self, parent="", index=END, iid=None, values=(), tags=()):
        if iid is None:
            self._counter += 1
            iid = f"I{self._counter:03d}"
        self.rows[iid] = {"values": tuple(values), "tags": tuple(tags)}
        self.order.append(iid)
        return iid

    def delete(self, *items):
        targets = items or tuple(self.order)
        for item in targets:
            self.rows.pop(item, None)
            if item in self.order:
                self.order.remove(item)

    def get_children(self, parent=""):
        return tuple(self.order)

    def selection(self):
        return tuple(i for i in self._selection if i in self.rows)

    def selection_set(self, iid):
        self._selection = (iid,)

    def bind(self, event, callback=None):
        self.calls.append(("bind", (event,), {}))
        return None

    def yview(self, *args):
        return None

    def item(self, iid, **kwargs):
        if kwargs:
            self.rows.setdefault(iid, {"values": (), "tags": ()}).update(kwargs)
        return self.rows.get(iid, {})


class Tk(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(None, **kwargs)
        self.callbacks: list[tuple[int, Any]] = []
        self.after_ids = 0
        self._wm_title = ""
        self.destroyed = False

    def after(self, delay, callback=None, *args):
        self.after_ids += 1
        if callback is not None:
            self.callbacks.append((delay, callback))
        return f"after#{self.after_ids}"

    def mainloop(self, n=0):
        return None

    def quit(self):
        return None

    def destroy(self):
        self.destroyed = True

    def title(self, value=None):
        if value is not None:
            self._wm_title = value
        return self._wm_title

    def update(self):
        return None

    def update_idletasks(self):
        return None


class Toplevel(Tk):
    def __init__(self, master=None, **kwargs):
        super().__init__(**kwargs)
        self.master = master
        if master is not None:
            reference = getattr(master, "_children_refs", None)
            if reference is None:
                reference = []
                master._children_refs = reference
            reference.append(self)


class Style(_Widget):
    def __init__(self, master=None):
        super().__init__(master)
        self.theme = ""

    def theme_use(self, name=None):
        if name is None:
            return self.theme
        if name not in {"vista", "clam", "default"}:
            raise RuntimeError(f"нет темы {name}")
        self.theme = name
        return name

    def configure(self, *args, **kwargs):
        return None


class _Noop:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        def recorder(*args, **kwargs):
            return None

        return recorder


class _StyleModule(types.ModuleType):
    Style = Style

    def __getattr__(self, name):
        return _Noop


class _MessageBox(types.ModuleType):
    def __init__(self):
        super().__init__("tkinter.messagebox")
        self.answers: list[tuple[str, str]] = []
        self.yes = True

    def showinfo(self, title, message, **kwargs):
        self.answers.append(("info", f"{title}: {message}"))
        return "ok"

    def showwarning(self, title, message, **kwargs):
        self.answers.append(("warning", f"{title}: {message}"))
        return "ok"

    def showerror(self, title, message, **kwargs):
        self.answers.append(("error", f"{title}: {message}"))
        return "ok"

    def askyesno(self, title, message, **kwargs):
        self.answers.append(("askyesno", f"{title}: {message}"))
        return self.yes

    def askokcancel(self, title, message, **kwargs):
        self.answers.append(("askokcancel", f"{title}: {message}"))
        return self.yes


class _FileDialog(types.ModuleType):
    def __init__(self):
        super().__init__("tkinter.filedialog")
        self.next_files: tuple[str, ...] = ()
        self.next_file = ""

    def askopenfilenames(self, **kwargs):
        return self.next_files

    def askopenfilename(self, **kwargs):
        return self.next_file

    def asksaveasfilename(self, **kwargs):
        return self.next_file


def install() -> tuple[types.ModuleType, _MessageBox, _FileDialog]:
    """Подменить настоящий tkinter на заглушку; вернуть модуль и управлялки."""
    if "tkinter" in sys.modules and getattr(sys.modules["tkinter"], "_arena_fake", False):
        module = sys.modules["tkinter"]
        return module, module._messagebox, module._filedialog

    module = types.ModuleType("tkinter")
    module._arena_fake = True
    for name, value in {
        "BOTH": BOTH,
        "X": X,
        "Y": Y,
        "LEFT": LEFT,
        "RIGHT": RIGHT,
        "END": END,
        "VERTICAL": VERTICAL,
        "HORIZONTAL": HORIZONTAL,
        "StringVar": StringVar,
        "BooleanVar": BooleanVar,
        "Text": Text,
        "Tk": Tk,
        "Toplevel": Toplevel,
        "Style": Style,
        "Frame": _Widget,
        "Label": _Widget,
        "Button": _Widget,
        "Entry": _Widget,
        "Checkbutton": _Widget,
        "Scrollbar": _Widget,
        "Separator": _Widget,
        "Panedwindow": _Widget,
        "Progressbar": _Widget,
        "Combobox": _Widget,
        "Notebook": _Widget,
        "Treeview": Treeview,
    }.items():
        setattr(module, name, value)

    ttk = _StyleModule("tkinter.ttk")
    for name in ("Frame", "Label", "Button", "Entry", "Checkbutton", "Scrollbar", "Separator",
                 "Panedwindow", "Progressbar", "Combobox", "Notebook"):
        setattr(ttk, name, _Widget)
    ttk.Treeview = Treeview
    ttk.Style = Style

    messagebox = _MessageBox()
    filedialog = _FileDialog()
    module.messagebox = messagebox
    module.filedialog = filedialog
    module.ttk = ttk
    module._messagebox = messagebox
    module._filedialog = filedialog

    sys.modules["tkinter"] = module
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["tkinter.filedialog"] = filedialog
    return module, messagebox, filedialog
