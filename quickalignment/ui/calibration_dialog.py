"""Configuration window: which configuration is in use, its constants (read-only).

Configurations are made by beamline staff with InitialCalibration.py (fit of
all constants, checked at test points). In QuickAlignment the remaining error
of a sample (mostly from drawing it on the plate) is corrected with "Found
here" in the Stage & Optics tab, so no calibration is done here. An older
configuration can be selected for this session.
"""

from __future__ import annotations

from ._qt import QtCore, QtWidgets, Signal
from .stage_panel import CONFIG_SPECS
from ..calibration import CalibrationRecord, CalibrationStore

Qt = QtCore.Qt

HELP = ("Configurations are made by beamline staff with <b>InitialCalibration.py</b> (after re-homing the motors "
        "or maintenance). Where a sample really is on the plate is corrected with <i>Found here</i> in the "
        "Stage &amp; Optics tab.")


class CalibrationDialog(QtWidgets.QDialog):
    recordChanged = Signal(object)  # CalibrationRecord now in use

    def __init__(self, store: CalibrationStore, panel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.store = store
        self.panel = panel  # StagePanel: current record

        self.current_label = QtWidgets.QLabel()
        self.current_label.setWordWrap(True)
        self.current_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.history = QtWidgets.QComboBox()
        # long entries must not widen the dialog
        self.history.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.history.setMinimumContentsLength(28)
        load_btn = QtWidgets.QPushButton("Use selected")
        load_btn.setToolTip("Use an older configuration for this session (the newest is loaded at the next start).")
        load_btn.clicked.connect(self.use_selected)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.history, 1)
        row.addWidget(load_btn)

        self.constants = QtWidgets.QLabel()
        self.constants.setTextInteractionFlags(Qt.TextSelectableByMouse)
        help_label = QtWidgets.QLabel(HELP)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #555;")
        folder = QtWidgets.QLabel(f"Folder: {store.folder}")
        folder.setStyleSheet("color: #777;")
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.hide)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.current_label)
        layout.addLayout(row)
        layout.addWidget(self.constants)
        layout.addWidget(help_label)
        layout.addWidget(folder)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        self.refresh()
        self.resize(max(self.sizeHint().width(), 560), self.sizeHint().height() + 40)

    def refresh(self) -> None:
        """Re-read the folder and show the configuration in use."""
        rec = self.panel.record
        where = rec.path.name if rec.path else "not saved"
        self.current_label.setText(f"In use: <b>{rec.label}</b> ({where})<br><span style='color:#555'>{rec.comment}</span>")
        self._records = self.store.records()
        self.history.clear()
        for i, r in enumerate(self._records):
            self.history.addItem(r.label)
            self.history.setItemData(i, r.comment, Qt.ToolTipRole)
        if not self._records:
            self.history.addItem("(no configuration files yet)")
        rows = "".join(f"<tr><td>{label}</td><td align=right>{getattr(rec.config, name):.4f}</td><td>{suffix.strip()}</td></tr>"
                       for name, (label, suffix) in CONFIG_SPECS.items())
        o = rec.optics
        if o.enabled:
            m = o.motors
            optics = (f"{o.optic_type}: in focus at optic {o.optic_position:.4f} with ST {m.st:.4f}, SZ {m.sz:.4f}, "
                      f"SN {m.sn:.4f}, SRn {m.srn:.3f}, SRz {m.srz:.3f}")
        else:
            optics = f"{o.optic_type}: not calibrated (focus assumed on the analyzer focus at optic {o.optic_position:.4f})"
        self.constants.setText(f"<table cellspacing=4>{rows}</table>Optics reference: {optics}")
        # the wrapped labels make Qt underestimate the height: keep the table whole
        self.constants.setMinimumHeight(self.constants.sizeHint().height())

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def _use(self, record: CalibrationRecord) -> None:
        self.panel.set_record(record)
        self.recordChanged.emit(record)
        self.refresh()

    def use_selected(self) -> None:
        i = self.history.currentIndex()
        if 0 <= i < len(self._records):
            self._use(self._records[i])
