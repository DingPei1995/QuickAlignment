"""Rotate sample tab: new SRn / SRz, ST / SN / SZ and optic from ARPES viewer's numbers.

Inputs, all from ARPES viewer:
1. the Map's metadata (right-click -> Show information -> Export metadata
   (.csv), or the rows pasted): stage positions and zone plate;
2. the k-conversion window: theta / phi offset (k-space origin) and the
   sample rotation from "Set rotation from contour...".
"""

from __future__ import annotations

import math

from ._qt import QtCore, QtWidgets
from .stage_panel import MotorForm, spin
from ..rotation import (
    SLIT_ORIENTATIONS, AnalyzerGeometry, align_direction, onto_line, relocate, to_center, wrap180,
)
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
CONFIGURATION_OPTIC = "(configuration's optics reference)"
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
    def __init__(self, stage_panel, layout_getter, parent=None):
        super().__init__(parent)
        self.stage = stage_panel
        self._layout_getter = layout_getter
        self.info: ViewerInfo | None = None
        self.candidates = []
        self.result = None
        self.settings = QtCore.QSettings("ANTARES", "QuickAlignment")

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
        self.to_focus = QtWidgets.QCheckBox("Put the point on the analyzer focus")
        self.to_focus.setToolTip(
            "Off (default): the point stays at the same place on the beam as during the measurement; errors of ST0 / SZ0 / SN_f\n"
            "mostly cancel and the optic stays where it was. On: like “Bring target to focus”."
        )
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
        gf.addRow(self.to_focus)
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
        for w in (meas_box, ang_box, goal_box, geo_box):
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
        self.slit.setCurrentIndex(get("slit", 0))
        self._on_slit(self.slit.currentText())
        self.slit_sign.setCurrentIndex(get("slit_sign", 0))
        self.defl_sign.setCurrentIndex(get("deflector_sign", 0))
        self.rot_sign.setCurrentIndex(get("rotation_sign", 0))

    def _save_settings(self, *_) -> None:
        for key, box in (("slit", self.slit), ("slit_sign", self.slit_sign), ("deflector_sign", self.defl_sign),
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
                self.stage.calibration(), optic, self.recentre.isChecked(), self.to_focus.isChecked(),
                self.height.value(),
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
            "Kept where it was measured on the beam." if not self.to_focus.isChecked() else "Put on the analyzer focus.",
            f"Optic from the {r.optic_source}"
            + (f" ({self.optic_key.currentText()})." if r.optic_source == "measurement" else "."),
        ]
        if abs(wrap180(r.new.srn - r.measured.srn)) > 0 and self.goal.currentData() in ("align_slit", "align_deflector"):
            lines.append("<span style='color:#555'>The direction is a line: the turn 180° away (second solution) "
                         "is equivalent; for a 6-fold lattice ±60° are too.</span>")
        return "<br>".join(lines)

    def send_to_stage(self) -> None:
        if self.result is None:
            return
        self.stage.motors.set_value(self.result.new)
        if self.result.optic_new is not None:
            self.stage.optic_pos.setValue(self.result.optic_new)
        self.stage.update_view()
