"""Rotate sample tab: new SRn / SRz, ST / SN / SZ and optic from ARPES viewer's numbers.

Inputs, all from ARPES viewer:
1. the Map's metadata (right-click -> Show information -> Export metadata
   (.csv), or the rows pasted): stage positions and zone plate;
2. the k-conversion window: theta / phi offset (k-space origin) and the
   sample rotation from "Set rotation from contour...".
"""

from __future__ import annotations

import math

from dataclasses import replace

from ._qt import QtCore, QtWidgets, Signal
from .stage_panel import MotorForm, spin
from ..rotation import (
    SLIT_ORIENTATIONS, AnalyzerGeometry, align_direction, fit_srn_axis, onto_line, relocate, to_center, wrap180,
)
from ..stage import beam_on_layout
from ..viewer_info import ViewerInfo

Qt = QtCore.Qt

GOALS = (  # key, label, tooltip
    ("align_slit", "Direction along the slit", "Turn SRn so the direction picked with “Set rotation from contour…”\n"
     "lies along the slit (the viewer's “Sample rotation”)."),
    ("align_deflector", "Direction along the deflector", "As above, but along the deflector axis (rotation + 90°)."),
    ("onto_slit", "Origin point onto the slit (SRn)", "Turn SRn so the origin point (θ, φ) comes onto the slit (θ = 0)."),
    ("center", "Origin point to the centre (SRn + SRz)",
     "Turn SRn and SRz so the origin point (θ, φ), e.g. a Dirac cone, comes to the analyzer centre (θ = φ = 0)."),
    ("manual", "Manual ΔSRn / SRz", "Type the SRn change and the new SRz."),
)
FOCUS_MODES = (  # key, label, tooltip
    ("keep_point", "Keep the point where measured (SN adjusts)",
     "The point stays at the same place on the beam as during the measurement, i.e. in the analyzer focus if it\n"
     "was there: ST / SZ / SN compensate, the optic does not move. Errors of ST0 / SZ0 / SN_f mostly cancel."),
    ("keep_sn", "Keep SN, refocus with the optic",
     "SN stays as measured, ST compensates: the point slides along the beam (√2 per mm of SN it would have needed)\n"
     "and the optic refocuses on it. The point then leaves the analyzer focus by that distance."),
    ("analyzer", "Put the point on the analyzer focus",
     "Like “Bring target to focus”: absolute, relies on ST0 / SZ0 / SN_f."),
)
CONFIGURATION_OPTIC = "(configuration's optics reference)"
SPOT_SHIFT_WARNING = 0.05  # mm along the beam
TYPED_OPTIC = "(typed in)"


def angle_spin(tip: str, lo: float = -180, hi: float = 180):
    box = spin(0.0, lo, hi, 4, 0.1, " °")
    box.setToolTip(tip)
    return box


class PasteDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paste metadata")
        self.resize(480, 420)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setPlaceholderText(
            "Paste the rows of ARPES viewer's “Show information” table or of its exported CSV,\n"
            "one “field, value” per line, e.g.\n\nMotor.roughY, -0.35\nMotor.roughX, 40.1\nMotor.focus, 0.51\n"
            "Motor.SRn, 120\nMotor.SRz, 0\nMotor.ZP_ZS, -12.345"
        )
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.text)
        lay.addWidget(buttons)


class RotationPanel(QtWidgets.QWidget):
    recordChanged = Signal(object)  # CalibrationRecord with a learned SRn axis

    def __init__(self, stage_panel, layout_getter, parent=None):
        super().__init__(parent)
        self.stage = stage_panel
        self._layout_getter = layout_getter
        self.info: ViewerInfo | None = None
        self.candidates = []
        self.result = None
        self.settings = QtCore.QSettings("ANTARES", "QuickAlignment")
        self.axis_fit = None

        # -- 1. measurement ---------------------------------------------------------
        load_btn = QtWidgets.QPushButton("Load metadata CSV…")
        load_btn.setToolTip("ARPES viewer: right-click the dataset → Show information → Export metadata (.csv)")
        load_btn.clicked.connect(self.load_csv)
        paste_btn = QtWidgets.QPushButton("Paste metadata…")
        paste_btn.clicked.connect(self.paste_info)
        copy_btn = QtWidgets.QPushButton("From Stage tab")
        copy_btn.setToolTip("Take the positions and the optic position of the Stage && Optics tab.")
        copy_btn.clicked.connect(self.copy_from_stage)
        self.info_label = QtWidgets.QLabel("No metadata loaded.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #555;")
        self.measured = MotorForm()
        self.optic_key = QtWidgets.QComboBox()
        self.optic_key.addItems([TYPED_OPTIC, CONFIGURATION_OPTIC])
        self.optic_key.currentTextChanged.connect(self._on_optic_key)
        self.measured_optic = spin(0.0, -10000, 10000, 4, 0.01)
        self.measured_optic.setToolTip("Optic position at which the measurement was in focus.")
        meas_box = QtWidgets.QGroupBox("1. Measurement (ARPES viewer → Show information)")
        mb = QtWidgets.QVBoxLayout(meas_box)
        row = QtWidgets.QHBoxLayout()
        for b in (load_btn, paste_btn, copy_btn):
            row.addWidget(b)
        mb.addLayout(row)
        mb.addWidget(self.info_label)
        hint = QtWidgets.QLabel("Stage positions of the Map / Cut, read from its metadata (editable).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #777;")
        mb.addWidget(hint)
        mb.addWidget(self.measured)
        of = QtWidgets.QFormLayout()
        of.addRow("Optic in focus from", self.optic_key)
        of.addRow("Optic position", self.measured_optic)
        mb.addLayout(of)

        # -- 2. angles -----------------------------------------------------------------
        self.theta = angle_spin("k conversion window: Theta offset (deg) — deflector angle of the origin point.")
        self.phi = angle_spin("k conversion window: Phi offset (deg) — slit angle of the origin point.")
        self.rotation = angle_spin("k conversion window: Sample rotation (deg), e.g. from “Set rotation from contour…”.")
        ang_box = QtWidgets.QGroupBox("2. Angles (ARPES viewer → k conversion)")
        af = QtWidgets.QFormLayout(ang_box)
        af.addRow("Theta offset (deflector)", self.theta)
        af.addRow("Phi offset (slit)", self.phi)
        af.addRow("Sample rotation", self.rotation)

        # -- 3. goal -----------------------------------------------------------------------
        self.goal = QtWidgets.QComboBox()
        for i, (key, text, tip) in enumerate(GOALS):
            self.goal.addItem(text, key)
            self.goal.setItemData(i, tip, Qt.ToolTipRole)
        self.goal.currentIndexChanged.connect(self._on_goal)
        self.d_srn = angle_spin("Manual SRn change.", -360, 360)
        self.new_srz = angle_spin("Manual new SRz.")
        self.candidate_combo = QtWidgets.QComboBox()
        self.candidate_combo.currentIndexChanged.connect(self._show_candidate)
        self.recentre = QtWidgets.QCheckBox("Re-centre the piezo (PIX = PIY = centre)")
        self.focus_mode = QtWidgets.QComboBox()
        for key, text, tip in FOCUS_MODES:
            self.focus_mode.addItem(text, key)
            self.focus_mode.setItemData(self.focus_mode.count() - 1, tip, Qt.ToolTipRole)
        self.height = spin(0.0, 0, 20, 3, 0.05)
        self.height.setToolTip("Used only if the beam does not land on a sample of the layout at the measured position.")
        compute_btn = QtWidgets.QPushButton("Compute new position")
        compute_btn.setMinimumHeight(34)
        compute_btn.setStyleSheet("font-weight: bold;")
        compute_btn.clicked.connect(self.compute)
        goal_box = QtWidgets.QGroupBox("3. Rotation")
        gf = QtWidgets.QFormLayout(goal_box)
        gf.addRow("Goal", self.goal)
        gf.addRow("ΔSRn", self.d_srn)
        gf.addRow("New SRz", self.new_srz)
        gf.addRow(self.recentre)
        gf.addRow("Focus", self.focus_mode)
        gf.addRow("Sample height H if no sample", self.height)
        gf.addRow(compute_btn)
        gf.addRow("Solution", self.candidate_combo)

        # -- analyzer geometry --------------------------------------------------------
        self.slit = QtWidgets.QComboBox()
        self.slit.addItems(SLIT_ORIENTATIONS)
        self.slit_sign = QtWidgets.QComboBox()
        self.defl_sign = QtWidgets.QComboBox()
        self.rot_sign = QtWidgets.QComboBox()
        self.rot_sign.addItems(["+1", "-1"])
        self.rot_sign.setToolTip("Flip if, on the first sample, the picked direction turned the wrong way.")
        self.slit.currentTextChanged.connect(self._on_slit)
        geo_box = QtWidgets.QGroupBox("Analyzer geometry (check once on a known sample)")
        geo_f = QtWidgets.QFormLayout(geo_box)
        geo_f.addRow("Slit", self.slit)
        geo_f.addRow("+φ (slit angle) points", self.slit_sign)
        geo_f.addRow("+θ (deflector) points", self.defl_sign)
        geo_f.addRow("Rotation sense", self.rot_sign)
        note = QtWidgets.QLabel("Directions as seen from the analyzer, right = +ST.")
        note.setStyleSheet("color: #777;")
        geo_f.addRow(note)
        self._load_settings()
        for box in (self.slit, self.slit_sign, self.defl_sign, self.rot_sign):
            box.currentIndexChanged.connect(self._save_settings)

        # -- result --------------------------------------------------------------------------
        self.result_label = QtWidgets.QLabel("Load the metadata, enter the angles and press “Compute new position”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        send_btn = QtWidgets.QPushButton("Send to Stage && Optics tab")
        send_btn.clicked.connect(self.send_to_stage)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        # -- 4. learn the SRn axis of this sample ---------------------------------
        self.second = MotorForm()
        second_load = QtWidgets.QPushButton("Load metadata CSV…")
        second_load.clicked.connect(self.load_second_csv)
        second_paste = QtWidgets.QPushButton("Paste…")
        second_paste.clicked.connect(self.paste_second)
        second_stage = QtWidgets.QPushButton("From Stage tab")
        second_stage.clicked.connect(lambda: self.second.set_value(self.stage.motors.value()))
        fit_btn = QtWidgets.QPushButton("Fit SRn axis")
        fit_btn.clicked.connect(self.fit_axis)
        self.use_axis_btn = QtWidgets.QPushButton("Use for this sample")
        self.use_axis_btn.setToolTip("Put the fitted SRn axis into the configuration in use\n"
                                     "(saved to user_config.json when closing, if you answer Save).")
        self.use_axis_btn.setEnabled(False)
        self.use_axis_btn.clicked.connect(self.use_axis)
        self.axis_label = QtWidgets.QLabel()
        self.axis_label.setWordWrap(True)
        self.axis_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        axis_box = QtWidgets.QGroupBox("4. Learn this sample's SRn axis (same point found again after an SRn turn)")
        ab = QtWidgets.QVBoxLayout(axis_box)
        note = QtWidgets.QLabel("The SRn axis on the plate changes with every mounting. After the first turn, enter where the "
                                "same point was found (e.g. the next Map's metadata); with section 1 this fixes the axis.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #777;")
        ab.addWidget(note)
        row = QtWidgets.QHBoxLayout()
        for b in (second_load, second_paste, second_stage):
            row.addWidget(b)
        ab.addLayout(row)
        ab.addWidget(self.second)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(fit_btn)
        row.addWidget(self.use_axis_btn)
        ab.addLayout(row)
        ab.addWidget(self.axis_label)

        for w in (meas_box, ang_box, goal_box, axis_box, geo_box):
            lv.addWidget(w)
        lv.addStretch(1)
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.addWidget(self.result_label)
        rv.addWidget(send_btn)
        rv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(520)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for combo in (self.goal, self.candidate_combo, self.optic_key):
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([720, 700])
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)
        self._on_goal()

    # -- settings ------------------------------------------------------------------------
    def _on_slit(self, slit: str) -> None:
        up_right = ("up", "down") if slit == "vertical" else ("right (+ST)", "left (−ST)")
        perp = ("right (+ST)", "left (−ST)") if slit == "vertical" else ("up", "down")
        for box, labels in ((self.slit_sign, up_right), (self.defl_sign, perp)):
            i = max(box.currentIndex(), 0)
            box.blockSignals(True)
            box.clear()
            box.addItems(list(labels))
            box.setCurrentIndex(i)
            box.blockSignals(False)

    def _load_settings(self) -> None:
        def get(key, default):
            try:
                return int(self.settings.value(f"rotation/{key}", default))
            except (TypeError, ValueError):
                return default
        slit = self.settings.value("rotation/slit_orientation", SLIT_ORIENTATIONS[0])
        self.slit.setCurrentText(slit if slit in SLIT_ORIENTATIONS else SLIT_ORIENTATIONS[0])
        self._on_slit(self.slit.currentText())
        self.slit_sign.setCurrentIndex(get("slit_sign", 0))
        self.defl_sign.setCurrentIndex(get("deflector_direction", 1))  # default: + theta down (see AnalyzerGeometry)
        self.rot_sign.setCurrentIndex(get("rotation_sign", 0))

    def _save_settings(self, *_) -> None:
        self.settings.setValue("rotation/slit_orientation", self.slit.currentText())
        for key, box in (("slit_sign", self.slit_sign), ("deflector_direction", self.defl_sign),
                         ("rotation_sign", self.rot_sign)):
            self.settings.setValue(f"rotation/{key}", box.currentIndex())

    def geometry(self) -> AnalyzerGeometry:
        return AnalyzerGeometry(
            self.slit.currentText(), 1 if self.slit_sign.currentIndex() == 0 else -1,
            1 if self.defl_sign.currentIndex() == 0 else -1,
        )

    # -- inputs ----------------------------------------------------------------------------
    def load_csv(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "ARPES viewer metadata", "", "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            self.set_info(ViewerInfo.load(path))
        except (OSError, UnicodeDecodeError) as exc:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))

    def paste_info(self) -> None:
        dlg = PasteDialog(self)
        if dlg.exec() if hasattr(dlg, "exec") else dlg.exec_():
            self.set_info(ViewerInfo.from_text(dlg.text.toPlainText()))

    def set_info(self, info: ViewerInfo) -> None:
        self.info = info
        motors, missing = info.motors(self.stage.motors.value())
        self.measured.set_value(motors)
        self.optic_key.blockSignals(True)
        self.optic_key.clear()
        self.optic_key.addItems(info.optic_keys() + [TYPED_OPTIC, CONFIGURATION_OPTIC])
        self.optic_key.blockSignals(False)
        self._on_optic_key(self.optic_key.currentText())
        text = [f"<b>{info.source}</b>: {len(info.rows)} rows"]
        if info.photon_energy is not None:
            text.append(f"hν = {info.photon_energy:g} eV")
        if missing:
            text.append(f"<span style='color:#b00'>not found (taken from the Stage tab): {', '.join(missing)}</span>")
        self.info_label.setText(" — ".join(text))

    # -- SRn axis of this sample -----------------------------------------------------------
    def load_second_csv(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Metadata after the turn", "", "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            self._set_second(ViewerInfo.load(path))
        except (OSError, UnicodeDecodeError) as exc:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))

    def paste_second(self) -> None:
        dlg = PasteDialog(self)
        if dlg.exec() if hasattr(dlg, "exec") else dlg.exec_():
            self._set_second(ViewerInfo.from_text(dlg.text.toPlainText()))

    def _set_second(self, info: ViewerInfo) -> None:
        motors, missing = info.motors(self.measured.value())
        self.second.set_value(motors)
        self.axis_label.setText(f"<b>{info.source}</b>" + (f" — not found: {', '.join(missing)}" if missing else ""))

    def surface_w(self, m) -> float:
        """Plate height of the measured point: the sample of the layout under the beam, else H."""
        layout = self._layout_getter()
        model = self.stage.model()
        hit, _, w, target = beam_on_layout(model, m, layout)
        if hit is not None and any(target.split("/")[0] == s.name for s in layout.samples):
            return w
        return model.plate.total_thickness + self.height.value()

    def fit_axis(self) -> None:
        first, second = self.measured.value(), self.second.value()
        model = self.stage.model()
        try:
            fit = fit_srn_axis(model, [first, second], self.surface_w(first))
        except ValueError as exc:
            self.axis_fit = None
            self.use_axis_btn.setEnabled(False)
            self.axis_label.setText(f"<b>{exc}</b>")
            return
        self.axis_fit = fit
        c = model.config
        self.use_axis_btn.setEnabled(True)
        self.axis_label.setText(
            f"ΔSRn = {second.srn - first.srn:+.3f}°: SRn axis at plate u = <b>{fit.config.srn_axis_u:.4f}</b>, "
            f"v = <b>{fit.config.srn_axis_v:.4f}</b> mm (now {c.srn_axis_u:.4f}, {c.srn_axis_v:.4f}); "
            f"{fit.lever_arm:.3f} mm from the point. ΔSN = {(second.sn - first.sn) * 1000:+.0f} µm"
            + (" (an SRn turn keeps the surface plane: a large ΔSN means the point was not refocused the same way)."
               if abs(second.sn - first.sn) > 0.02 else ".")
        )

    def use_axis(self) -> None:
        if self.axis_fit is None:
            return
        record = self.stage.record
        record = replace(record, config=self.axis_fit.config,
                         comment=f"{record.comment}; SRn axis learned on this sample "
                                 f"({self.axis_fit.config.srn_axis_u:.4f}, {self.axis_fit.config.srn_axis_v:.4f})")
        self.stage.set_record(record)
        self.recordChanged.emit(record)
        self.use_axis_btn.setEnabled(False)
        if self.candidates:
            self._show_candidate(self.candidate_combo.currentIndex())

    def copy_from_stage(self) -> None:
        self.measured.set_value(self.stage.motors.value())
        self.optic_key.setCurrentText(TYPED_OPTIC)
        self.measured_optic.setValue(self.stage.optic_pos.value())

    def _on_optic_key(self, key: str) -> None:
        self.measured_optic.setEnabled(key != CONFIGURATION_OPTIC)
        if self.info is not None and key.startswith("Motor."):
            value = self.info.get(key)
            if value is not None:
                self.measured_optic.setValue(value)

    def _on_goal(self, *_) -> None:
        manual = self.goal.currentData() == "manual"
        self.d_srn.setEnabled(manual)
        self.new_srz.setEnabled(manual)

    # -- computation -----------------------------------------------------------------------
    def compute_candidates(self):
        model, geo, m = self.stage.model(), self.geometry(), self.measured.value()
        goal = self.goal.currentData()
        if goal in ("align_slit", "align_deflector"):
            sign = 1 if self.rot_sign.currentIndex() == 0 else -1
            along = "slit" if goal == "align_slit" else "deflector"
            return align_direction(model, geo, m, self.rotation.value(), along, sign)
        if goal == "onto_slit":
            return onto_line(model, geo, m, self.theta.value(), self.phi.value(), "slit")
        if goal == "center":
            return to_center(model, geo, m, self.theta.value(), self.phi.value())
        from ..rotation import RotationCandidate
        return [RotationCandidate(m.srn + self.d_srn.value(), self.new_srz.value(), "manual", math.nan, math.nan)]

    def compute(self) -> None:
        self.candidates = self.compute_candidates()
        self.candidate_combo.blockSignals(True)
        self.candidate_combo.clear()
        for c in self.candidates:
            extra = "" if math.isnan(c.theta) else f"  → θ = {c.theta:.2f}°, φ = {c.phi:.2f}°"
            self.candidate_combo.addItem(f"SRn = {c.srn:.3f}°, SRz = {c.srz:.3f}°  ({c.description}){extra}")
        self.candidate_combo.blockSignals(False)
        if not self.candidates:
            self.result = None
            self.result_label.setText("<b>No solution</b>: the point cannot be brought there with this goal "
                                      "(e.g. too far off normal emission for the slit with SRn alone).")
            return
        self.candidate_combo.setCurrentIndex(0)
        self._show_candidate(0)

    def _show_candidate(self, index: int) -> None:
        if not (0 <= index < len(self.candidates)):
            return
        c = self.candidates[index]
        optic = None if self.optic_key.currentText() == CONFIGURATION_OPTIC else self.measured_optic.value()
        try:
            self.result = relocate(
                self.stage.model(), self._layout_getter(), self.measured.value(), c.srn, c.srz,
                self.stage.calibration(), optic, self.recentre.isChecked(), self.focus_mode.currentData() == "analyzer",
                self.height.value(), self.focus_mode.currentData() == "keep_sn",
            )
        except ValueError as exc:
            self.result = None
            self.result_label.setText(f"<b>{exc}</b>")
            return
        self.result_label.setText(self.describe(self.result, c))

    def describe(self, r, c) -> str:
        rows = []
        for name, label, unit, fmt in (
            ("srn", "SRn", "°", ".3f"), ("srz", "SRz", "°", ".3f"), ("st", "ST", "mm", ".4f"), ("sz", "SZ", "mm", ".4f"),
            ("sn", "SN", "mm", ".4f"), ("pix", "PIX", "µm", ".2f"), ("piy", "PIY", "µm", ".2f"),
        ):
            a, b = getattr(r.measured, name), getattr(r.new, name)
            rows.append((label, f"{a:{fmt}}", f"<b>{b:{fmt}}</b>", f"{b - a:+{fmt}}", unit))
        if r.optic_new is not None:
            a = self.measured_optic.value() if r.optic_source == "measurement" else r.optic_measured
            rows.append(("Optic", f"{a:.4f}", f"<b>{r.optic_new:.4f}</b>", f"{r.optic_new - a:+.4f}", ""))
        table = "".join(f"<tr><td>{a}</td><td align=right>{b}</td><td align=right>{d}</td><td align=right>{e}</td>"
                        f"<td>{u}</td></tr>" for a, b, d, e, u in rows)
        u, v, w = r.uvw
        lines = [
            f"<b>Rotation:</b> {c.description}"
            + ("" if math.isnan(c.theta) else f"; the picked point is then seen at θ = {c.theta:.2f}°, φ = {c.phi:.2f}°"),
            f"<table cellspacing=0 cellpadding=3><tr><th></th><th>measured</th><th>new</th><th>Δ</th><th></th></tr>{table}</table>",
            f"Point: <b>{r.target}</b> at plate u = {u:.3f}, v = {v:.3f} mm, surface w = {w:.3f} mm.",
            self.focus_note(r),
            f"Optic from the {r.optic_source}"
            + (f" ({self.optic_key.currentText()})." if r.optic_source == "measurement" else "."),
        ]
        if abs(wrap180(r.new.srn - r.measured.srn)) > 0 and self.goal.currentData() in ("align_slit", "align_deflector"):
            lines.append("<span style='color:#555'>The direction is a line: the turn 180° away (second solution) "
                         "is equivalent; for a 6-fold lattice ±60° are too.</span>")
        return "<br>".join(lines)

    def focus_note(self, r) -> str:
        """Where the beam spot ends up along the beam, compared with the measurement."""
        model = self.stage.model()
        w = r.uvw[2]
        y_old, y_new = model.beam_hit(r.measured, w), model.beam_hit(r.new, w)
        if y_old is None or y_new is None:
            return ""
        shift = float(y_new[1] - y_old[1])
        where = ("at the same place along the beam as measured" if abs(shift) < 0.001 else
                 f"{abs(shift) * 1000:.0f} µm {'downstream' if shift > 0 else 'upstream'} of where it was measured")
        text = f"Beam spot {where} (model: {abs(y_new[1]):.3f} mm from the analyzer focus)."
        if abs(shift) > SPOT_SHIFT_WARNING:
            text = f"<span style='color:#b00'><b>{text}</b> It leaves the analyzer focus: consider correcting SN.</span>"
        return text

    def send_to_stage(self) -> None:
        if self.result is None:
            return
        self.stage.motors.set_value(self.result.new)
        if self.result.optic_new is not None:
            self.stage.optic_pos.setValue(self.result.optic_new)
        self.stage.update_view()
