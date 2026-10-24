"""Qt binding shim: PyQt5 if available, otherwise PySide6."""

try:
    from PyQt5 import QtCore, QtGui, QtWidgets

    Signal = QtCore.pyqtSignal
except ImportError:  # pragma: no cover
    from PySide6 import QtCore, QtGui, QtWidgets

    Signal = QtCore.Signal


def exec_app(app) -> int:
    return app.exec() if hasattr(app, "exec") else app.exec_()


__all__ = ["QtCore", "QtGui", "QtWidgets", "Signal", "exec_app"]
