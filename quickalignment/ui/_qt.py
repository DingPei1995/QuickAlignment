"""Qt binding shim: PyQt5 if available, otherwise PySide6, and the program-wide error handler."""

import sys
import traceback

try:
    from PyQt5 import QtCore, QtGui, QtWidgets

    Signal = QtCore.pyqtSignal
except ImportError:  # pragma: no cover
    from PySide6 import QtCore, QtGui, QtWidgets

    Signal = QtCore.Signal


def use_standard_numbers() -> None:
    """Show and read numbers as 1234.5 everywhere, whatever the system language.

    Qt follows the system locale by default, so on a French Windows the spin
    boxes would show and expect "1234,5"; the files and the beamline use ".".
    Widgets take the default locale when they are created, so this runs on import.
    """
    locale = QtCore.QLocale.c()
    locale.setNumberOptions(QtCore.QLocale.OmitGroupSeparator | QtCore.QLocale.RejectGroupSeparator)
    QtCore.QLocale.setDefault(locale)


use_standard_numbers()


def exec_app(app) -> int:
    return app.exec() if hasattr(app, "exec") else app.exec_()


def install_excepthook(title: str) -> None:
    """Report unexpected errors in a dialog and keep running.

    Without this, PyQt5 aborts the whole program on any exception raised in a
    button / signal handler, and the entered positions are lost.
    """
    busy = []

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        sys.stderr.write(text)
        if busy or QtWidgets.QApplication.instance() is None:
            return
        busy.append(1)
        try:
            while QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()
            box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Critical, title,
                                        f"An unexpected error occurred:\n\n{etype.__name__}: {value}\n\n"
                                        "The program keeps running; check the last result before using it, "
                                        "and save the session. Please report the details to the beamline staff.")
            box.setDetailedText(text)
            box.exec() if hasattr(box, "exec") else box.exec_()
        except Exception:  # pragma: no cover - never let the handler itself fail
            pass
        finally:
            busy.clear()

    sys.excepthook = hook


__all__ = ["QtCore", "QtGui", "QtWidgets", "Signal", "exec_app", "install_excepthook", "use_standard_numbers"]
