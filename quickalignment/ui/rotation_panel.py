"""Rotate sample tab: ST / SZ (and optionally SN) that keep a sample point on the beam after a rotation.

1. current position: the stage positions with the point of interest on the
   beam and in focus, and the optic (zone plate / capillary) position there;
2. the wanted SRn, SRz;
3. the new ST / SZ with the piezo centred (PIX = PIY = 150 µm) and SN kept,
   with how far the beam spot then moves along the beam (out of the analyzer
   focus); optionally SN is corrected so the point stays where it was.
"""

from __future__ import annotations

from ._qt import QtCore, QtWidgets
from .stage_panel import MOTOR_SPECS, MotorForm, align_labels, equal_row, spin
from ..rotation import relocate

Qt = QtCore.Qt

SPOT_SHIFT_WARNING = 0.05  # mm along the beam


class RotationPanel(QtWidgets.QWidget):
    def __init__(self, stage_panel, layout_getter, height_getter=None, parent=None):
        super().__init__(parent)
        self.stage = stage_panel
        self._layout_getter = layout_getter
        self._height_getter = height_getter or (lambda: 0.0)
        self.result = None  # SN kept
        self.corrected = None  # SN corrected

        # -- 1. current position -------------------------------------------------------
        copy_btn = QtWidgets.QPushButton("From Stage tab")
        copy_btn.setToolTip("Take the positions and the optic position of the Stage && Optics tab.")
        copy_btn.clicked.connect(self.copy_from_stage)
        self.measured = MotorForm()
        self.optic_label = QtWidgets.QLabel()
        self.measured_optic = spin(0.0, -10000, 10000, 4, 0.01)
        self.measured_optic.setToolTip("Optic position at which the beam is in focus on the sample now.")
        self.stage.optic_type.currentTextChanged.connect(self.update_optic)
        now_box = QtWidgets.QGroupBox("1. Current position (sample point on the beam, in focus)")
        nb = QtWidgets.QVBoxLayout(now_box)
        nb.addWidget(self.measured)
        of = QtWidgets.QFormLayout()
        of.addRow(self.optic_label, self.measured_optic)
        nb.addLayout(of)
        nb.addLayout(equal_row(copy_btn))

        # -- 2. wanted angles ------------------------------------------------------------
        label, lo, hi, dec, step, suffix = MOTOR_SPECS["srn"]
        self.new_srn = spin(120.0, lo, hi, dec, step, suffix)
        self.new_srz = spin(0.0, lo, hi, dec, step, suffix)
        compute_btn = QtWidgets.QPushButton("Compute new position")
        compute_btn.setMinimumHeight(34)
        compute_btn.setStyleSheet("font-weight: bold;")
        compute_btn.clicked.connect(self.compute)
        goal_box = QtWidgets.QGroupBox("2. Wanted angles")
        gf = QtWidgets.QFormLayout(goal_box)
        gf.addRow("SRn", self.new_srn)
        gf.addRow("SRz", self.new_srz)
        gf.addRow(compute_btn)

        # -- 3. result ---------------------------------------------------------------------
        self.result_label = QtWidgets.QLabel("Enter the current position and the wanted angles, "
                                             "then press “Compute new position”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.focus_label = QtWidgets.QLabel()
        self.focus_label.setWordWrap(True)
        self.correct_sn = QtWidgets.QCheckBox("Correct SN (keep the point where it is now along the beam)")
        self.correct_sn.setToolTip("Off (default): SN stays, the optic refocuses.\n"
                                   "On: SN, ST and SZ move so the point stays in the analyzer focus; the optic stays.")
        self.correct_sn.toggled.connect(self._show)
        self.corrected_label = QtWidgets.QLabel()
        self.corrected_label.setWordWrap(True)
        self.corrected_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.corrected_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        send_btn = QtWidgets.QPushButton("Send to Stage && Optics tab")
        send_btn.clicked.connect(self.send_to_stage)
        res_box = QtWidgets.QGroupBox("3. New position")
        rb = QtWidgets.QVBoxLayout(res_box)
        for w in (self.result_label, self.focus_label, self.correct_sn, self.corrected_label, send_btn):
            rb.addWidget(w)

        align_labels(self.measured, of, gf)
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        for w in (now_box, goal_box):
            lv.addWidget(w)
        lv.addStretch(1)
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.addWidget(res_box)
        rv.addStretch(1)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 700])
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)
        self.update_optic()
        self._show()

    def optic_name(self) -> str:
        return self.stage.record.optic_name

    def copy_from_stage(self) -> None:
        self.measured.set_value(self.stage.motors.value())
        self.measured_optic.setValue(self.stage.optic_pos.value())

    def update_optic(self, *_) -> None:
        """Name the optic field after the optic of the configuration in use."""
        name = self.optic_name()
        self.optic_label.setText(f"{name[0].upper()}{name[1:]} position")

    # -- computation -----------------------------------------------------------------------
    def compute(self) -> None:
        model, layout, m = self.stage.model(), self._layout_getter(), self.measured.value()
        args = (model, layout, m, self.new_srn.value(), self.new_srz.value(), self.stage.calibration(),
                self.measured_optic.value(), True, False, self._height_getter())
        try:
            self.result = relocate(*args, keep_sn=True)
            self.corrected = relocate(*args, keep_sn=False)
        except ValueError as exc:
            self.result = self.corrected = None
            self.result_label.setText(f"<b>{exc}</b>")
            self._show()
            return
        self._show()

    def spot_shift(self) -> float | None:
        """How far the beam spot moves along the beam with SN kept (mm, + = downstream)."""
        r = self.result
        model, w = self.stage.model(), r.uvw[2]
        old, new = model.beam_hit(r.measured, w), model.beam_hit(r.new, w)
        return None if old is None or new is None else float(new[1] - old[1])

    def _table(self, r, names) -> str:
        rows = []
        for name in names:
            label, *_, suffix = MOTOR_SPECS[name]
            fmt = ".3f" if name in ("srn", "srz") else ".4f"
            a, b = getattr(r.measured, name), getattr(r.new, name)
            rows.append((label, f"{a:{fmt}}", f"<b>{b:{fmt}}</b>", f"{b - a:+{fmt}}", suffix.strip()))
        if r.optic_new is not None:
            a = self.measured_optic.value()
            rows.append((self.optic_name(), f"{a:.4f}", f"<b>{r.optic_new:.4f}</b>", f"{r.optic_new - a:+.4f}", ""))
        body = "".join(f"<tr><td>{a}</td><td align=right>{b}</td><td align=right>{c}</td><td align=right>{d}</td>"
                       f"<td>{u}</td></tr>" for a, b, c, d, u in rows)
        return (f"<table cellspacing=0 cellpadding=3><tr><th></th><th>now</th><th>new</th><th>Δ</th><th></th></tr>"
                f"{body}</table>")

    def _show(self, *_) -> None:
        r = self.result
        self.corrected_label.setVisible(r is not None and self.correct_sn.isChecked())
        if r is None:
            self.focus_label.setText("")
            return
        u, v, w = r.uvw
        pi = self.stage.config().pi_center
        self.result_label.setText(
            f"At SRn = {r.new.srn:.3f}°, SRz = {r.new.srz:.3f}°, PIX = PIY = {pi:g} µm, SN kept:"
            + self._table(r, ("st", "sz", "sn")) + f"Point: <b>{r.target}</b> (plate x = {u:.3f}, y = {v:.3f} mm)."
        )
        shift = self.spot_shift()
        if shift is None:
            self.focus_label.setText("")
        else:
            text = (f"With SN kept the beam spot moves {abs(shift) * 1000:.0f} µm "
                    f"{'downstream' if shift > 0 else 'upstream'} along the beam, i.e. out of the analyzer focus "
                    "(the optic refocuses on it).")
            if abs(shift) > SPOT_SHIFT_WARNING:
                text = f"<span style='color:#b00'><b>{text}</b> This is far from the analyzer focus: correct SN?</span>"
            else:
                text = f"<span style='color:#207020'>{text} Small: no SN correction needed.</span>"
            self.focus_label.setText(text)
        c = self.corrected
        self.corrected_label.setText("With SN corrected (the point stays where it is now along the beam):"
                                     + self._table(c, ("st", "sz", "sn")))

    def chosen(self):
        return self.corrected if self.correct_sn.isChecked() else self.result

    def send_to_stage(self) -> None:
        r = self.chosen()
        if r is None:
            return
        self.stage.motors.set_value(r.new)
        if r.optic_new is not None:
            self.stage.optic_pos.setValue(r.optic_new)
        self.stage.update_view()
