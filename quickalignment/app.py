"""Main window: "Samples" tab (plate editor) and "Stage & Optics" tab."""

from __future__ import annotations

import sys

from .session import Session
from .ui._qt import QtWidgets, exec_app
from .ui.plate_editor import PlateEditor
from .ui.stage_panel import StagePanel


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, session: Session | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment")
        self.resize(1450, 860)
        self._path: str | None = None

        self.editor = PlateEditor()
        self.stage = StagePanel(lambda: self.editor.layout_model)
        self.editor.layoutChanged.connect(self.stage.refresh_targets)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.editor, "Samples")
        self.tabs.addTab(self.stage, "Stage && Optics")
        self.setCentralWidget(self.tabs)

        bar = self.addToolBar("File")
        for text, slot in (("New", self.new_session), ("Open…", self.open_session), ("Save", self.save_session), ("Save as…", self.save_session_as)):
            btn = QtWidgets.QToolButton()
            btn.setText(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        self.statusBar().showMessage("Draw samples on the plate, then go to “Stage & Optics”.")
        self.set_session(session or Session())

    def session(self) -> Session:
        return Session(self.editor.layout_model, self.stage.config(), self.stage.calibration(), self.stage.motors.value())

    def set_session(self, session: Session) -> None:
        self.editor.set_layout(session.layout)
        self.stage.set_config(session.config)
        self.stage.set_calibration(session.calibration)
        self.stage.motors.set_value(session.motors)
        self.stage.refresh_targets()
        self.stage.update_view()

    def new_session(self) -> None:
        self._path = None
        self.set_session(Session())

    def open_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open session", "", "Session (*.json)")
        if not path:
            return
        try:
            self.set_session(Session.load(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._path = path
        self.statusBar().showMessage(f"Loaded {path}")

    def save_session(self) -> None:
        if self._path is None:
            self.save_session_as()
            return
        self.session().save(self._path)
        self.statusBar().showMessage(f"Saved {self._path}")

    def save_session_as(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save session", "session.json", "Session (*.json)")
        if path:
            self._path = path
            self.save_session()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    session = Session.load(argv[1]) if len(argv) > 1 else None
    win = MainWindow(session)
    win.show()
    return exec_app(app)
