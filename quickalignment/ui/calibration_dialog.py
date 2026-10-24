"""Calibration window: dated configurations, reference-sample check, expert edits.

Workflow: the newest configuration is loaded at start-up. To check it, select
the reference sample, enter the stage positions where it was found on the
beam (at the analyzer focus) and the optic position at best focus, press
"Check", then decide whether to save the result as a new configuration.
Stage constants are read-only unless "Expert mode" is ticked.
"""

from __future__ import annotations

from dataclasses import replace

from ._qt import QtCore, QtWidgets, Signal
from .stage_panel import CONFIG_SPECS, OPTIC_DIRECTIONS, MotorForm, spin
from ..calibration import CalibrationRecord, CalibrationStore, CheckResult, check_reference
from ..stage import StageConfig

Qt = QtCore.Qt


class CalibrationDialog(QtWidgets.QDialog):
    recordChanged = Signal(object)  # CalibrationRecord now in use

    def __init__(self, store: CalibrationStore, panel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibration")
        self.store = store
        self.panel = panel  # StagePanel: current record, targets, current motors
        self.result: CheckResult | None = None

        # -- configuration files ------------------------------------------------
        self.history = QtWidgets.QComboBox()
        load_btn = QtWidgets.QPushButton("Use selected")
        load_btn.clicked.connect(self.use_selected)
        self.current_label = QtWidgets.QLabel()
        self.current_label.setWordWrap(True)
        files_box = QtWidgets.QGroupBox("Configuration files")
        fb = QtWidgets.QVBoxLayout(files_box)
        fb.addWidget(self.current_label)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.history, 1)
        row.addWidget(load_btn)
        fb.addLayout(row)
        folder = QtWidgets.QLabel(f"Folder: {store.folder}")
        folder.setStyleSheet("color: #777;")
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fb.addWidget(folder)

        # -- reference check ------------------------------------------------------
        self.ref_combo = QtWidgets.QComboBox()
        self.measured = MotorForm()
        copy_btn = QtWidgets.QPushButton("Copy positions from the Stage && Optics tab")
        copy_btn.clicked.connect(lambda: self.measured.set_value(self.panel.motors.value()))
        self.measured_optic = spin(0.0, -10000, 10000, 4, 0.01)
        check_btn = QtWidgets.QPushButton("Check")
        check_btn.setStyleSheet("font-weight: bold;")
        check_btn.clicked.connect(self.run_check)
        self.check_label = QtWidgets.QLabel("Enter where the reference sample was found, then press Check.")
        self.check_label.setWordWrap(True)
        self.check_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.check_label.setStyleSheet("padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("comment for the new configuration (optional)")
        self.accept_btn = QtWidgets.QPushButton("Accept and save as new configuration")
        self.accept_btn.setEnabled(False)
        self.accept_btn.clicked.connect(self.accept_check)

        check_box = QtWidgets.QGroupBox("Check with the reference sample")
        cb = QtWidgets.QVBoxLayout(check_box)
        cf = QtWidgets.QFormLayout()
        cf.addRow("Reference sample", self.ref_combo)
        cb.addLayout(cf)
        cb.addWidget(QtWidgets.QLabel("Stage positions with the reference on the beam, at the analyzer focus\n"
                                      "(preferably at SRn = 120, SRz = 0):"))
        cb.addWidget(self.measured)
        cb.addWidget(copy_btn)
        of = QtWidgets.QFormLayout()
        of.addRow("Optic position at best focus", self.measured_optic)
        cb.addLayout(of)
        cb.addWidget(check_btn)
        cb.addWidget(self.check_label)
        cb.addWidget(self.comment)
        cb.addWidget(self.accept_btn)

        # -- constants (locked unless expert mode) -------------------------------------
        self.expert = QtWidgets.QCheckBox("Expert mode: edit the constants directly")
        self.expert.toggled.connect(self._set_expert)
        self.cfg_boxes = {}
        const_box = QtWidgets.QGroupBox("Constants of the configuration in use")
        kf = QtWidgets.QFormLayout(const_box)
        for name, (label, suffix) in CONFIG_SPECS.items():
            lo, hi = (0, 300) if name == "pi_center" else (-1000, 1000)
            self.cfg_boxes[name] = spin(0.0, lo, hi, 4, 0.1, suffix)
            kf.addRow(label, self.cfg_boxes[name])
        self.optic_dir = QtWidgets.QComboBox()
        self.optic_dir.addItems(OPTIC_DIRECTIONS)
        kf.addRow("Optic motor direction", self.optic_dir)
        self.optics_label = QtWidgets.QLabel()
        self.optics_label.setWordWrap(True)
        kf.addRow("Optics reference", self.optics_label)
        self.save_expert_btn = QtWidgets.QPushButton("Save edited constants as new configuration")
        self.save_expert_btn.clicked.connect(self.save_expert)
        kf.addRow(self.expert)
        kf.addRow(self.save_expert_btn)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.hide)

        left = QtWidgets.QVBoxLayout()
        left.addWidget(files_box)
        left.addWidget(check_box)
        left.addStretch(1)
        right = QtWidgets.QVBoxLayout()
        right.addWidget(const_box)
        right.addStretch(1)
        right.addWidget(close_btn, 0, Qt.AlignRight)
        layout = QtWidgets.QHBoxLayout(self)
        layout.addLayout(left, 3)
        layout.addLayout(right, 2)

        self._set_expert(False)
        self.refresh()

    # -- display -----------------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the folder and show the record in use."""
        rec = self.panel.record
        where = rec.path.name if rec.path else "not saved"
        self.current_label.setText(f"In use: <b>{rec.label}</b> ({where})<br>{rec.comment}")
        self._records = self.store.records()
        self.history.clear()
        for r in self._records:
            self.history.addItem(f"{r.created} — {r.comment}")
        if not self._records:
            self.history.addItem("(no configuration files yet)")
        for name, box in self.cfg_boxes.items():
            box.setValue(getattr(rec.config, name))
        self.optic_dir.setCurrentIndex(0 if rec.optics.optic_sign > 0 else 1)
        o = rec.optics
        self.optics_label.setText(
            f"{o.optic_type}: in focus at optic {o.optic_position:.4f} with ST {o.motors.st:.4f}, SZ {o.motors.sz:.4f}, "
            f"SN {o.motors.sn:.4f}, SRn {o.motors.srn:g}, SRz {o.motors.srz:g}, "
            f"surface H = {o.surface_w - self.panel.model().plate.total_thickness:.3f} mm"
            if o.enabled else f"{o.optic_type}: in focus on the analyzer focus at optic {o.optic_position:.4f}"
        )
        if self.result is None:
            self.measured_optic.setValue(self.panel.optic_pos.value())
        current = self.ref_combo.currentText()
        self.ref_combo.clear()
        self.ref_combo.addItems(["plate centre"] + self.panel.target_labels())
        self.ref_combo.setCurrentIndex(max(self.ref_combo.findText(current), 0))

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def _set_expert(self, on: bool) -> None:
        for box in self.cfg_boxes.values():
            box.setEnabled(on)
        self.optic_dir.setEnabled(on)
        self.save_expert_btn.setEnabled(on)

    # -- actions -------------------------------------------------------------------
    def _use(self, record: CalibrationRecord) -> None:
        self.panel.set_record(record)
        self.recordChanged.emit(record)
        self.refresh()

    def use_selected(self) -> None:
        i = self.history.currentIndex()
        if 0 <= i < len(self._records):
            self._use(self._records[i])

    def run_check(self) -> None:
        label = self.ref_combo.currentText()
        uvw = self.panel.target_point(label)
        if uvw is None:
            return
        self.result = check_reference(
            self.panel.record, self.panel.model().plate, label, uvw,
            self.measured.value(), self.measured_optic.value(), self.comment.text().strip(),
        )
        r = self.result
        rows = [
            ("ST", r.predicted.st, r.measured.st, r.delta_st),
            ("SZ", r.predicted.sz, r.measured.sz, r.delta_sz),
            ("SN", r.predicted.sn, r.measured.sn, r.delta_sn),
        ]
        if r.predicted_optic is not None:
            rows.append(("optic", r.predicted_optic, r.measured_optic, r.delta_optic))
        html = "<table cellspacing=6><tr><th></th><th>predicted</th><th>measured</th><th>Δ</th></tr>"
        for name, p, m, d in rows:
            html += f"<tr><td><b>{name}</b></td><td>{p:.4f}</td><td>{m:.4f}</td><td><b>{d:+.4f}</b></td></tr>"
        html += "</table>"
        if r.predicted_optic is None:
            html += "No optic prediction (the beam misses the plane of the reference).<br>"
        c = r.new_record.config
        html += f"New constants if accepted: ST0 = {c.st0:.4f}, SZ0 = {c.sz0:.4f}, SN_f = {c.sn_f:.4f}"
        self.check_label.setText(html)
        self.accept_btn.setEnabled(True)

    def accept_check(self) -> None:
        if self.result is None:
            return
        record = self.result.new_record
        if self.comment.text().strip():
            record = replace(record, comment=self.comment.text().strip())
        saved = self.store.save(record)
        self.result = None
        self.accept_btn.setEnabled(False)
        self.check_label.setText(f"Saved new configuration <b>{saved.created}</b> ({saved.path.name}).")
        self._use(saved)

    def save_expert(self) -> None:
        rec = self.panel.record
        config = StageConfig(**{k: b.value() for k, b in self.cfg_boxes.items()})
        optics = replace(rec.optics, optic_sign=1 if self.optic_dir.currentIndex() == 0 else -1)
        comment = self.comment.text().strip() or "expert edit of the constants"
        saved = self.store.save(CalibrationRecord(comment=comment, config=config, optics=optics, check=None))
        self.expert.setChecked(False)
        self._use(saved)
