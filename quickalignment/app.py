"""Main window: "Samples" tab (plate editor) and "Stage & Optics" tab."""

from __future__ import annotations

import sys

from .calibration import CalibrationRecord, CalibrationStore
from .geometry import SampleLayout
from .session import Session
from .ui._qt import QtWidgets, exec_app
from .ui.calibration_dialog import CalibrationDialog
from .ui.plate_choice import ask_plate
from .ui.plate_editor import PlateEditor
from .ui.stage_panel import StagePanel


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, session: Session | None = None, store: CalibrationStore | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment")
        self.resize(1450, 860)
        self._path: str | None = None

        self.editor = PlateEditor()
        self.stage = StagePanel(lambda: self.editor.layout_model)
        self.editor.layoutChanged.connect(self.stage.refresh_targets)
        self.store = store or CalibrationStore()
        self.cal_dialog = CalibrationDialog(self.store, self.stage, self)
        self.cal_dialog.recordChanged.connect(self._on_record)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.editor, "Samples")
        self.tabs.addTab(self.stage, "Stage && Optics")
        self.setCentralWidget(self.tabs)

        bar = self.addToolBar("File")
        for text, slot in (
            ("New", self.new_session),
            ("Open…", self.open_session),
            ("Save", self.save_session),
            ("Save as…", self.save_session_as),
            (None, None),
            ("Calibration…", self.open_calibration),
            ("Change plate…", self.change_plate),
        ):
            if text is None:
                bar.addSeparator()
                continue
            btn = QtWidgets.QToolButton()
            btn.setText(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addSeparator()
        self.plate_label = QtWidgets.QLabel()
        self.plate_label.setStyleSheet("padding-left: 8px; font-weight: bold;")
        bar.addWidget(self.plate_label)
        self.cal_label = QtWidgets.QLabel()
        self.cal_label.setStyleSheet("padding-left: 12px;")
        bar.addWidget(self.cal_label)
        self.statusBar().showMessage("Draw samples on the plate, then go to “Stage & Optics”.")
        self.set_session(session or Session())
        # the newest calibration configuration is used by default
        self._on_record(self.store.latest())

    def open_calibration(self) -> None:
        self.cal_dialog.show()
        self.cal_dialog.raise_()
        self.cal_dialog.activateWindow()

    def _on_record(self, record: CalibrationRecord) -> None:
        self.stage.set_record(record)
        self.cal_label.setText(f"Calibration: {record.label}")
        self.stage.update_view()

    def session(self) -> Session:
        return Session(self.editor.layout_model, self.stage.motors.value())

    def set_session(self, session: Session) -> None:
        self.editor.set_layout(session.layout)
        self.plate_label.setText(f"Plate: {session.layout.plate.name}")
        self.stage.motors.set_value(session.motors)
        self.stage.refresh_targets()
        self.stage.update_view()

    def new_session(self) -> None:
        plate = ask_plate(self.editor.layout_model.plate.key, self)
        if plate is None:
            return
        self._path = None
        self.set_session(Session(layout=SampleLayout(plate=plate)))

    def change_plate(self) -> None:
        plate = ask_plate(self.editor.layout_model.plate.key, self)
        if plate is None:
            return
        session = self.session()
        session.layout.plate = plate  # samples are kept; misplaced ones are flagged
        self.set_session(session)

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
    if len(argv) > 1:
        session = Session.load(argv[1])
    else:
        plate = ask_plate()
        if plate is None:
            return 0
        session = Session(layout=SampleLayout(plate=plate))
    win = MainWindow(session)
    win.show()
    return exec_app(app)
