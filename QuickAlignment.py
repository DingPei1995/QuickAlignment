#!/usr/bin/env python3
"""ANTARES QuickAlignment - double-click this file to start the program.

On Windows you can also double-click QuickAlignment.pyw (no console window).
"""

import importlib
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _show_error(text: str) -> None:
    # without Qt there is no window to report in; try Tk, then the console
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("QuickAlignment", text)
    except Exception:
        print(text, file=sys.stderr)
        input("Press Enter to close...")


def launch(module: str) -> int:
    """Import `module` and run its main(), reporting missing packages in a dialog."""
    try:
        main = importlib.import_module(module).main
    except ImportError:
        _show_error(
            "Could not start QuickAlignment, a package is missing:\n\n"
            + traceback.format_exc(limit=1)
            + "\nInstall the requirements with:\n    pip install PyQt5 numpy matplotlib"
        )
        return 1
    return main()


if __name__ == "__main__":
    sys.exit(launch("quickalignment.app"))
