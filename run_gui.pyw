"""Запуск окна «Публикатор» двойным кликом (Windows, без консоли).

Файл .pyw открывается через pythonw.exe — консольного окна не будет.
Всё, что рядом (config.toml, secrets.toml, plan.toml), считается рабочей папкой.
"""

import sys
import traceback
from pathlib import Path

HOME = Path(__file__).resolve().parent
sys.path.insert(0, str(HOME))

try:
    from social_publisher.gui.__main__ import main as gui_main

    raise SystemExit(gui_main(["--home", str(HOME)]))
except SystemExit:
    raise
except Exception:  # noqa: BLE001 - без консоли ошибку видно только в файле
    log = HOME / "gui_error.log"
    log.write_text(traceback.format_exc(), encoding="utf-8")
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(
            "Не удалось запустить",
            f"Подробности записаны в {log}.\n\n"
            "Чаще всего помогает: установить Python с python.org "
            "(с галочкой «tcl/tk and IDLE»).",
        )
    except Exception:
        pass
    raise
