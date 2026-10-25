"""Rotate sample tab: ST / SZ (and optionally SN) that keep a sample point on the beam after a rotation.

1. current position: the stage positions with the point of interest on the
   beam and in focus, and the optic (zone plate / capillary) position there;
2. the wanted SRn, SRz;
3. the new ST / SZ with the piezo centred (PIX = PIY = 150 µm) and SN kept,
   with how far the point then is from the analyzer focus; optionally SN, ST,
   SZ and the optic are corrected to put the point on the analyzer focus (or
   as close as the motor ranges allow).
"""

from __future__ import annotations

from ._qt import QtCore, QtWidgets
from .stage_panel import FOCUS_WARNING, MOTOR_SPECS, MotorForm, align_labels, equal_row, out_of_range, spin
from ..rotation import relocate

Qt = QtCore.Qt

LIMITS = {name: MOTOR_SPECS[name][1:3] for name in ("st", "sn", "sz")}
COLLISION_STYLE = "<br><span style='color:#b00'><b>Collision: the plate would touch {}.</b></span>"


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
        bz_btn = QtWidgets.QPushButton("Find angles for a BZ point…")
        bz_btn.setToolTip("Which SRn / SRz bring Γ, K or M (2-D hexagonal crystal) to the slit centre with the\n"
                          "deflector at 0 and the slit along a high-symmetry line, from angles read on a map.")
        bz_btn.clicked.connect(self.open_bz_target)
        self._bz_dialog = None
        goal_box = QtWidgets.QGroupBox("2. Wanted angles")
        gf = QtWidgets.QFormLayout(goal_box)
        gf.addRow("SRn", self.new_srn)
        gf.addRow("SRz", self.new_srz)
        gf.addRow(bz_btn)
        gf.addRow(compute_btn)

        # -- 3. result ---------------------------------------------------------------------
        self.result_label = QtWidgets.QLabel("Enter the current position and the wanted angles, "
                                             "then press “Compute new position”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.focus_label = QtWidgets.QLabel()
        self.focus_label.setWordWrap(True)
        self.correct_sn = QtWidgets.QCheckBox("Correct SN (put the point on the analyzer focus)")
        self.correct_sn.setToolTip("Off (default): SN stays, ST / SZ keep the point on the beam, the optic refocuses.\n"
                                   "On: SN, ST, SZ and the optic move so the point is on the analyzer focus\n"
                                   "(absolute: relies on the configuration's ST0 / SZ0 / SN_f and rotation axes).")
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

    def open_bz_target(self) -> None:
        from .bz_target_dialog import BZTargetDialog

        if self._bz_dialog is None:
            self._bz_dialog = BZTargetDialog(self, self)
        self._bz_dialog.show()
        self._bz_dialog.raise_()
        self._bz_dialog.activateWindow()

    def set_wanted(self, srn: float, srz: float) -> None:
        """Wanted angles from the BZ window; computes the new position."""
        self.new_srn.setValue(srn)
        self.new_srz.setValue(srz)
        self.compute()

    # -- computation -----------------------------------------------------------------------
    def compute(self) -> None:
        model, layout, m = self.stage.model(), self._layout_getter(), self.measured.value()
        args = (model, layout, m, self.new_srn.value(), self.new_srz.value(), self.stage.calibration(),
                self.measured_optic.value())
        common = dict(recentre_piezo=True, default_height=self._height_getter())
        try:
            self.result = relocate(*args, keep_sn=True, **common)
            self.corrected = relocate(*args, to_analyzer_focus=True, limits=LIMITS, **common)
        except ValueError as exc:
            self.result = self.corrected = None
            self.result_label.setText(f"<b>{exc}</b>")
            self._show()
            return
        # every new position starts with SN kept; SN is corrected only if the user then asks for it
        self.correct_sn.blockSignals(True)
        self.correct_sn.setChecked(False)
        self.correct_sn.blockSignals(False)
        self._show()


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
        bad = out_of_range(r.new)
        self.result_label.setText(
            f"At SRn = {r.new.srn:.3f}°, SRz = {r.new.srz:.3f}°, PIX = PIY = {pi:g} µm, SN kept:"
            + self._table(r, ("st", "sz", "sn")) + f"Point: <b>{r.target}</b> (plate x = {u:.3f}, y = {v:.3f} mm)."
            + (f"<br><span style='color:#b00'><b>Out of range: {', '.join(bad)}</b> — not reachable with SN kept, "
               "use the corrected solution.</span>" if bad else "")
            + self._collision_text(r)
        )
        y = r.beam_offset
        side = "" if abs(y) < 1e-6 else f" {'downstream' if y > 0 else 'upstream'}"
        text = (f"With SN kept the point is {r.focus_distance * 1000:.0f} µm{side} from the analyzer focus "
                f"(now: {r.measured_focus_distance * 1000:.0f} µm, model); the optic refocuses on it.")
        if abs(y) >= 1e-6:
            text += f" Removing it would take ΔSN ≈ {-y / 2 ** 0.5:+.4f} mm (ST compensating)."
        if r.focus_distance > FOCUS_WARNING:
            text = (f"<span style='color:#b00'><b>{text}</b> Too far from the analyzer focus, the data would be "
                    "distorted: correct SN?</span>")
        else:
            text = f"<span style='color:#207020'>{text} Close enough: no SN correction needed.</span>"
        self.focus_label.setText(text)
        c = self.corrected
        if c.focus_distance < 1e-4:
            where = "on the analyzer focus"
        else:
            where = (f"<span style='color:#b00'><b>closest reachable position: {c.focus_distance * 1000:.0f} µm "
                     "from the analyzer focus</b> (motor range)</span>")
        self.corrected_label.setText(f"With SN corrected, the point is {where}:"
                                     + self._table(c, ("st", "sz", "sn")) + self._collision_text(c))

    def collisions(self, r) -> str:
        """What the plate touches at the new position (optic where it is now, or refocused); empty if nothing."""
        return self.stage.move_collisions(r.new, r.optic_new, self.measured_optic.value())

    def _collision_text(self, r) -> str:
        hits = self.collisions(r)
        return COLLISION_STYLE.format(hits) if hits else ""

    def chosen(self):
        return self.corrected if self.correct_sn.isChecked() else self.result

    def send_to_stage(self) -> None:
        r = self.chosen()
        if r is None:
            return
        bad = out_of_range(r.new)
        if bad:
            QtWidgets.QMessageBox.warning(self, "Out of range", "Not reachable:\n" + "\n".join(bad))
            return
        hits = self.collisions(r)
        if hits:
            QtWidgets.QMessageBox.warning(self, "Collision", f"Not reachable: the plate would touch {hits}.")
            return
        self.stage.motors.set_value(r.new)
        if r.optic_new is not None:
            self.stage.optic_pos.setValue(r.optic_new)
        self.stage.update_view()
