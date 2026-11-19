"""Запуск окна: python -m social_publisher.gui [--home ПАПКА]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Публикатор: оконный интерфейс")
    parser.add_argument("--home", default=None, help="папка с config.toml, secrets.toml и plan.toml")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(
            "В этой сборке Python нет tkinter — установите Python с python.org "
            "(при установке отметьте «tcl/tk and IDLE»).",
            file=sys.stderr,
        )
        return 2

    from .main_window import App

    home = Path(args.home).expanduser().resolve() if args.home else Path(__file__).resolve().parents[1]
    app = App(home)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
