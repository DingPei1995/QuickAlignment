"""Stage & optics panel: motor inputs, results and the schematic.

The schematic and the results are only recomputed when "Update" is pressed.
Calibration constants come from the current CalibrationRecord (see the
calibration window).
"""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from dataclasses import replace

from ._qt import QtCore, QtWidgets, Signal
from ..calibration import CalibrationRecord
from ..collision import ACCEPTANCE_HALF_ANGLE, collisions, in_acceptance, motor_limits
from ..schematic import draw_schematic
from ..stage import (
    OPTIC_TYPES, MotorPositions, OpticsCalibration, StageConfig, StageModel, focus_correction, found_offset, sn_to_focus,
)

Qt = QtCore.Qt

MOTOR_SPECS = {  # name: (label, min, max, decimals, step, suffix); min / max: default limits (Configuration window)
    "st": ("ST", -9, 9, 4, 0.1, " mm"),
    # SN: below the focal plane (SN_f ≈ 0) the real limit is a collision (OSA / capillary, analyzer 30 mm away),
    # computed for the current positions by the anti-collision check
    "sn": ("SN", -30, 65, 4, 0.1, " mm"),
    "sz": ("SZ", 35, 45, 4, 0.1, " mm"),
    "srn": ("SRn", -720, 720, 3, 1.0, " °"),
    "srz": ("SRz", -720, 720, 3, 1.0, " °"),
    "pix": ("PIX", 0, 300, 2, 1.0, " µm"),
    "piy": ("PIY", 0, 300, 2, 1.0, " µm"),
}
CONFIG_SPECS = {
    "st0": ("ST0 (plate centre)", " mm"),
    "sz0": ("SZ0 (plate centre)", " mm"),
    "sn_f": ("SN_f (plate surface in focus)", " mm"),
    "srn_ref": ("SRn ref (vertical, tab up)", " °"),
    "pi_center": ("Piezo centre", " µm"),
    "srn_axis_u": ("SRn axis u on plate", " mm"),
    "srn_axis_v": ("SRn axis v on plate", " mm"),
    "srz_offset_t": ("SRz axis offset along +ST", " mm"),
    "srz_offset_n": ("SRz axis offset along +SN", " mm"),
}
TOLERANCE = 1e-3  # mm; below this a move is reported as not needed
LARGE_FOUND_OFFSET = 0.3  # mm; a larger "Found here" correction hints at an outdated configuration
FOCUS_WARNING = 0.05  # mm from the analyzer focus; farther, the spectra would be distorted
TRAVEL = {name: MOTOR_SPECS[name][1:3] for name in ("st", "sn", "sz")}  # kept up to date by set_motor_limits
LIMIT_MOTORS = ("st", "sz", "sn", "srn", "srz")  # limits that can be changed by hand in the Configuration window
DEFAULT_LIMITS = {name: MOTOR_SPECS[name][1:3] for name in LIMIT_MOTORS}


def current_limits() -> dict[str, tuple[float, float]]:
    """Limits in use, {name: (min, max)} for LIMIT_MOTORS."""
    return {name: tuple(MOTOR_SPECS[name][1:3]) for name in LIMIT_MOTORS}


def set_motor_limits(limits: dict[str, tuple[float, float]]) -> None:
    """Use these limits (missing motors: the defaults) everywhere: input ranges, out-of-range and anti-collision
    checks. Input fields already made take them with MotorForm.apply_limits."""
    new = {name: limits.get(name, DEFAULT_LIMITS[name]) for name in LIMIT_MOTORS}
    for name, (lo, hi) in new.items():  # all checked before any is changed
        if not lo < hi:
            raise ValueError(f"{MOTOR_SPECS[name][0]}: min {lo:g} must be below max {hi:g}")
    for name, (lo, hi) in new.items():
        label, _, _, *rest = MOTOR_SPECS[name]
        MOTOR_SPECS[name] = (label, float(lo), float(hi), *rest)
    for name in TRAVEL:
        TRAVEL[name] = MOTOR_SPECS[name][1:3]


def unsigned_zero(x: float, decimals: int) -> float:
    """x rounded to `decimals`, a value that rounds to zero without its sign (shown 0.000, not -0.000)."""
    return round(x, decimals) + 0.0


def set_range(box: QtWidgets.QDoubleSpinBox, name: str) -> None:
    box.setRange(*MOTOR_SPECS[name][1:3])


def spin(value: float, lo: float = -1000, hi: float = 1000, decimals: int = 3, step: float = 0.1, suffix: str = " mm"):
    box = QtWidgets.QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setSuffix(suffix)
    box.setValue(value)
    box.setKeyboardTracking(False)
    return box


def equal_row(*widgets) -> QtWidgets.QHBoxLayout:
    """A row of widgets (buttons, panels) that all get the same width."""
    row = QtWidgets.QHBoxLayout()
    width = max(w.sizeHint().width() for w in widgets)
    for w in widgets:
        w.setMinimumWidth(width)
        row.addWidget(w, 1)
    return row


def form_labels(form: QtWidgets.QFormLayout) -> list:
    out = []
    for i in range(form.rowCount()):
        item = form.itemAt(i, QtWidgets.QFormLayout.LabelRole)
        if item is not None and item.widget() is not None:
            out.append(item.widget())
    return out


def align_labels(*parts) -> None:
    """Give the label column of several forms (QFormLayout or MotorForm) the same
    width, so that their input fields start at the same x."""
    labels = [w for p in parts for w in (p.labels if isinstance(p, MotorForm) else form_labels(p))]
    width = max(w.sizeHint().width() for w in labels)
    for w in labels:
        w.setMinimumWidth(width)


def out_of_range(m: MotorPositions) -> list[str]:
    """Motors of m outside their range, e.g. ["ST = 9.2000 (range −9 … 9)"]."""
    out = []
    for name, (label, lo, hi, dec, *_) in MOTOR_SPECS.items():
        value = getattr(m, name)
        if not lo <= value <= hi:
            out.append(f"{label} = {value:.{dec}f} (range {lo:g} … {hi:g})")
    return out


class MotorForm(QtWidgets.QWidget):
    def __init__(self, motors: MotorPositions | None = None, parent=None):
        super().__init__(parent)
        motors = motors or MotorPositions()
        self.boxes = {}
        self.labels = []  # first column, see align_labels
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (name, (label, lo, hi, dec, step, suffix)) in enumerate(MOTOR_SPECS.items()):
            self.boxes[name] = spin(getattr(motors, name), lo, hi, dec, step, suffix)
            text = QtWidgets.QLabel(label)
            if i % 2 == 0:
                self.labels.append(text)
            grid.addWidget(text, i // 2, 2 * (i % 2))
            grid.addWidget(self.boxes[name], i // 2, 2 * (i % 2) + 1)
        # both columns of fields equally wide, labels only as wide as needed
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

    def apply_limits(self) -> None:
        """Input ranges from MOTOR_SPECS (after set_motor_limits)."""
        for name, box in self.boxes.items():
            set_range(box, name)

    def value(self) -> MotorPositions:
        return MotorPositions(**{k: b.value() for k, b in self.boxes.items()})

    def set_value(self, m: MotorPositions) -> None:
        for k, b in self.boxes.items():
            b.setValue(getattr(m, k))


class StagePanel(QtWidgets.QWidget):
    layoutCorrected = Signal(str)  # a sample was moved to where its target was found

    def __init__(self, layout_getter, parent=None):
        super().__init__(parent)
        self._layout_getter = layout_getter
        self.record = CalibrationRecord()

        self.motors = MotorForm()
        self.target_combo = QtWidgets.QComboBox()
        goto_btn = QtWidgets.QPushButton("Bring target onto the beam")
        goto_btn.setToolTip("Compute ST / SZ that put the target on the beam with SN kept as entered (how the stage\n"
                            "is run), keeping SRn, SRz, PIX, PIY; tells how far the target then is from the analyzer\n"
                            "focus. The optic refocuses on it.")
        goto_btn.clicked.connect(self.bring_target_on_beam)
        self.correct_sn_btn = QtWidgets.QPushButton("Correct SN")
        self.correct_sn_btn.setToolTip("Only if the target is too far from the analyzer focus: compute SN, ST, SZ that put it\n"
                                       "on the analyzer focus (absolute: relies on the configuration's SN_f).")
        self.correct_sn_btn.clicked.connect(self.bring_target_to_focus)
        self.goto_label = QtWidgets.QLabel()
        self.goto_label.setWordWrap(True)
        self.goto_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.goto_label.hide()
        self.limits_label = QtWidgets.QLabel()
        self.limits_label.setWordWrap(True)
        self.limits_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.limits_label.setToolTip(
            "Anti-collision check: the plate with its samples against the analyzer nose (MBS A1, front 30 mm from\n"
            "the focus) and the focusing optic (OSA / zone plate, or capillary) at the entered optic position.\n"
            "Each range moves one motor with the others kept. Working distances: under the optic position.")
        self.limits_label.hide()
        for box in self.motors.boxes.values():  # the readouts only hold for the positions they were computed for
            box.valueChanged.connect(self.goto_label.hide)
            box.valueChanged.connect(self.limits_label.hide)
        motor_box = QtWidgets.QGroupBox("Sample stage (current / planned positions)")
        mb = QtWidgets.QVBoxLayout(motor_box)
        mb.addWidget(self.motors)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Target"))
        row.addWidget(self.target_combo, 1)
        mb.addLayout(row)
        mb.addLayout(equal_row(goto_btn, self.correct_sn_btn))
        mb.addWidget(self.goto_label)
        mb.addWidget(self.limits_label)

        # focusing optic: absolute position along the beam
        self.optic_type = QtWidgets.QComboBox()
        self.optic_type.addItems(OPTIC_TYPES)
        self.optic_type.currentTextChanged.connect(self._on_optic_type)
        self.optic_pos = spin(0.0, -10000, 10000, 4, 0.01)
        self.optic_pos.setToolTip("Absolute optic motor position along the beam (from the configuration, or typed in).")
        use_btn = QtWidgets.QPushButton("Use required position")
        use_btn.setToolTip("Copy the optic position computed by the last update into the field.")
        use_btn.clicked.connect(self.use_required_optic)
        ref_btn = QtWidgets.QPushButton("Set as optics reference")
        ref_btn.setToolTip(
            "The beam is in focus now: take the current stage positions, the illuminated surface\n"
            "and this optic position as the optics reference (for this session; configurations are\n"
            "made by beamline staff with InitialCalibration.py)."
        )
        ref_btn.clicked.connect(self.set_optics_reference)
        self.optic_ref_label = QtWidgets.QLabel()
        self.optic_ref_label.setWordWrap(True)
        self.optic_ref_label.setStyleSheet("color: #555;")
        optic_box = QtWidgets.QGroupBox("Focusing optic (along the beam)")
        of = QtWidgets.QFormLayout(optic_box)
        of.addRow("Type", self.optic_type)
        of.addRow("Optic position", self.optic_pos)
        of.addRow(equal_row(use_btn, ref_btn))
        of.addRow(self.optic_ref_label)
        # working distances of the optic solids (anti-collision); filled from the configuration
        self.distance_form = QtWidgets.QFormLayout()
        self.distance_boxes = []
        of.addRow(self.distance_form)
        align_labels(self.motors, of)

        update_btn = QtWidgets.QPushButton("Update schematic && optics")
        update_btn.setMinimumHeight(36)
        update_btn.setStyleSheet("font-weight: bold;")
        update_btn.clicked.connect(self.update_view)

        self.result_label = QtWidgets.QLabel("Press “Update schematic & optics”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.cal_status = QtWidgets.QLabel()
        self.cal_status.setWordWrap(True)
        self.cal_status.setStyleSheet("color: #555;")

        # filled when the user confirms in the Samples tab that the samples are placed
        self.start_label = QtWidgets.QLabel()
        self.start_label.setWordWrap(True)
        self.start_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.start_box = QtWidgets.QGroupBox("Where the samples are at the initial rotation")
        self.start_box.setStyleSheet("QGroupBox { background: #eef6ee; }")
        self.found_combo = QtWidgets.QComboBox()
        found_btn = QtWidgets.QPushButton("Found here: correct its sample")
        found_btn.setToolTip("The chosen device is on the beam, in the analyzer focus, at the stage positions\n"
                             "entered below: move its sample (with all its devices) there on the plate.")
        found_btn.clicked.connect(self.correct_from_found)
        sb = QtWidgets.QVBoxLayout(self.start_box)
        sb.addWidget(self.start_label)
        found_row = QtWidgets.QHBoxLayout()
        found_row.addWidget(QtWidgets.QLabel("Found"))
        found_row.addWidget(self.found_combo, 1)
        found_row.addWidget(found_btn)
        sb.addLayout(found_row)
        self.start_box.hide()

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        # result_label / cal_status are kept up to date but not shown (too long for the panel)
        for w in (self.start_box, motor_box, optic_box, update_btn):
            lv.addWidget(w)
        lv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(430)

        self.figure = Figure(figsize=(11, 5.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self.canvas.mpl_connect("figure_leave_event", lambda _event: self._show_cursor(None))
        self.cursor_label = QtWidgets.QLabel()
        self.cursor_label.setToolTip("Mouse position in the sample plane view (as of the last update): the ST, SZ\n"
                                     "that bring this point onto the beam, and where it is on the plate.")
        self._plane = None  # (axes, model, motors, layout) of the last drawn sample plane view
        self._show_cursor(None)
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.canvas, 1)
        rv.addWidget(self.cursor_label)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)

        self.last_result = None
        self._target_labels = None
        self.set_record(self.record)
        self.refresh_targets()

    # -- state ----------------------------------------------------------------
    def set_record(self, record: CalibrationRecord) -> None:
        """Use a configuration; the optic fields are loaded from it."""
        self.record = record
        self.optic_type.blockSignals(True)
        if self.optic_type.findText(record.optics.optic_type) < 0:
            self.optic_type.addItem(record.optics.optic_type)
        self.optic_type.setCurrentText(record.optics.optic_type)
        self.optic_type.blockSignals(False)
        self.optic_pos.setValue(record.optics.current_position)
        self._fill_distances()
        self._show_record()
        if not self.start_box.isHidden():
            self.show_start_positions()

    def _show_record(self) -> None:
        record, optics = self.record, self.record.optics
        if optics.enabled:
            m = optics.motors
            ref = (f"in focus at optic {optics.optic_position:.4f} with ST {m.st:.4f}, SZ {m.sz:.4f}, SN {m.sn:.4f}, "
                   f"SRn {m.srn:.3f}, SRz {m.srz:.3f}")
        else:
            ref = f"in focus on the analyzer focus at optic {optics.optic_position:.4f}"
        self.optic_ref_label.setText(f"Optics reference: {ref}")
        self.cal_status.setText(f"Configuration in use: <b>{record.label}</b> — {record.comment}")

    def config(self) -> StageConfig:
        return self.record.config

    def calibration(self) -> OpticsCalibration:
        return self.record.optics

    def _on_optic_type(self, text: str) -> None:
        # the collision solids of the configuration belong to its optic: another optic takes its defaults
        self.record = replace(self.record, optics=replace(self.record.optics, optic_type=text), collision=None)
        self._fill_distances()

    def _fill_distances(self) -> None:
        """One field per optic assembly (the capillary is one, whatever its parts): the distance of its front
        from the focus (working distance)."""
        while self.distance_form.rowCount():
            self.distance_form.removeRow(0)
        self.distance_boxes = []
        optics = self.record.collision_geometry().optics
        for name in dict.fromkeys(b.assembly for b in optics):  # in order, once each
            parts = [b for b in optics if b.assembly == name]
            box = spin(min(b.distance for b in parts), 0, 500, 2, 0.5)
            box.setToolTip(f"Distance of the {name} front from the focus along the beam, used by the anti-collision\n"
                           "check (for this session; beamline staff keep it in the configuration). "
                           + ("It moves with the optic motor." if parts[0].moves else
                              "It stays put when the optic refocuses (placed for the configuration's optics reference)."))
            box.valueChanged.connect(lambda value, name=name: self._set_distance(name, value))
            self.distance_form.addRow(f"{name} working distance", box)
            self.distance_boxes.append(box)

    def _set_distance(self, name: str, value: float) -> None:
        """Move the whole assembly `name` so that its front is `value` from the focus."""
        geo = self.record.collision_geometry()
        optics = list(geo.optics)
        shift = value - min(b.distance for b in optics if b.assembly == name)
        for i, body in enumerate(optics):
            if body.assembly == name:
                optics[i] = replace(body, distance=body.distance + shift)
        self.record = replace(self.record, collision=replace(geo, optics=tuple(optics)))
        self.limits_label.hide()  # computed for the old distances

    def use_required_optic(self) -> None:
        if self.last_result is not None and self.last_result.required_optic_position is not None:
            self.optic_pos.setValue(self.last_result.required_optic_position)
            self.update_view()

    def set_optics_reference(self) -> None:
        """The current state is in focus: make it the optics reference."""
        res = focus_correction(self.model(), self.motors.value(), self._layout_getter(), self.calibration())
        if res.hit is None:
            QtWidgets.QMessageBox.warning(self, "Optics reference", "The beam does not hit the plate: no reference possible.")
            return
        optics = replace(
            self.record.optics, enabled=True, motors=self.motors.value(), surface_w=res.surface_w,
            optic_position=self.optic_pos.value(),
        )
        self.record = replace(self.record, optics=optics)
        self._show_record()
        self.update_view()

    def model(self) -> StageModel:
        return StageModel(self.config(), self._layout_getter().plate)

    # -- targets ----------------------------------------------------------------
    def refresh_targets(self) -> None:
        # called on every mouse move while a sample is dragged: the lists only change with the names
        labels = self.target_labels()
        if labels != self._target_labels:
            self._target_labels = labels
            current = self.target_combo.currentText()
            self.target_combo.blockSignals(True)
            self.target_combo.clear()
            self.target_combo.addItems(["plate centre", *labels])
            self.target_combo.setCurrentIndex(max(self.target_combo.findText(current), 0))
            self.target_combo.blockSignals(False)
            found = self.found_combo.currentText()
            self.found_combo.clear()
            self.found_combo.addItems(labels)
            self.found_combo.setCurrentIndex(max(self.found_combo.findText(found), 0))
        if not self.start_box.isHidden():
            self.show_start_positions()

    def show_start_positions(self) -> None:
        """List the ST / SZ / SN putting each sample / device on the analyzer focus at SRn = ref, SRz = 0."""
        model = self.model()
        c = model.config
        rows = []
        for label in ["plate centre", *self.target_labels()]:
            st, sz, sn = (unsigned_zero(x, 3) for x in model.reference_motors(*self.target_point(label)))
            rows.append(f"<tr><td>{label}</td><td align=right>{st:.3f}</td><td align=right>{sz:.3f}</td>"
                        f"<td align=right>{sn:.3f}</td></tr>")
        self.start_label.setText(
            f"At SRn = {c.srn_ref:g}° (plate vertical, tab up), SRz = 0°, PIX = PIY = {c.pi_center:g} µm, "
            "each sample centre is on the beam at the analyzer focus at:"
            "<table cellspacing=0 cellpadding=3><tr><th align=left>sample</th><th>ST (mm)</th><th>SZ (mm)</th>"
            f"<th>SN (mm)</th></tr>{''.join(rows)}</table>"
            f"(ST = ST0 − x, SZ = SZ0 − y with ST0 = {c.st0:g}, SZ0 = {c.sz0:g}; SN puts the sample surface "
            "in the analyzer focal plane.) <i>Bring target onto the beam</i> gives ST, SZ for the entered SN, rotations "
            "and piezo, and how far the target then is from the analyzer focus; <i>Correct SN</i> only if that is too far."
        )
        self.start_box.show()

    def correct_from_found(self) -> tuple[float, float, float] | None:
        """The chosen target is on the analyzer focus at the entered positions: move its sample there."""
        label = self.found_combo.currentText()
        t = self.target_point(label) if label else None
        sample = self._layout_getter().sample_of(label) if label else None
        if t is None or sample is None:
            return None
        m = self.motors.value()
        du, dv, dw = found_offset(self.model(), m, *t)
        su, sv, sw = (unsigned_zero(x, 3) for x in (du, dv, dw))
        large = ""
        if max(abs(du), abs(dv), abs(dw)) > LARGE_FOUND_OFFSET:
            large = (f"\n\nThis is more than {LARGE_FOUND_OFFSET:g} mm. If other samples show the same shift, the "
                     "configuration may be outdated (motors re-homed?): ask beamline staff to run InitialCalibration.")
        answer = QtWidgets.QMessageBox.question(
            self, "Correct the sample position?",
            f"{label} is on the beam, in the analyzer focus, at ST = {m.st:.4f}, SZ = {m.sz:.4f}, SN = {m.sn:.4f} "
            f"(SRn = {m.srn:g}°, SRz = {m.srz:g}°)?\n\n"
            f"Then it is at Δx = {su:+.3f}, Δy = {sv:+.3f} mm on the plate and ΔH = {sw:+.3f} mm from where it was "
            f"drawn. {sample.name} (with its devices) is moved there; the other samples stay." + large,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return None
        sample.u += du
        sample.v += dv
        sample.height = max(sample.height + dw, 0.0)
        self.layoutCorrected.emit(sample.name)
        self.refresh_targets()
        self.update_view()
        return du, dv, dw

    def target_labels(self) -> list[str]:
        return [label for label, *_ in self._layout_getter().targets()]

    def target_point(self, label: str):
        """(u, v, w) of a target: sample / device surface centre, or the plate centre."""
        plate = self._layout_getter().plate
        if label == "plate centre":
            return 0.0, 0.0, plate.total_thickness
        for name, u, v, h in self._layout_getter().targets():
            if name == label:
                return u, v, plate.total_thickness + h
        return None

    # -- actions ----------------------------------------------------------------
    def bring_target_on_beam(self) -> MotorPositions | None:
        """ST / SZ putting the target on the beam with SN as entered; reports its distance from the analyzer focus."""
        label = self.target_combo.currentText()
        t = self.target_point(label)
        if t is None:
            return None
        m = self.motors.value()
        new = self.model().motors_on_beam(*t, srn=m.srn, srz=m.srz, sn=m.sn, pix=m.pix, piy=m.piy)
        if not self._go_to(new, "The target cannot be brought onto the beam with SN kept",
                           "\n\nCorrect SN may reach it (it also moves SN)."):
            return None
        self._show_goto(label, t, new)
        return new

    def bring_target_to_focus(self) -> MotorPositions | None:
        """Second step, when the target is too far from the analyzer focus with SN kept: SN, ST, SZ putting it there."""
        label = self.target_combo.currentText()
        t = self.target_point(label)
        if t is None:
            return None
        m = self.motors.value()
        new = self.model().motors_for_target(*t, srn=m.srn, srz=m.srz, pix=m.pix, piy=m.piy)
        if not self._go_to(new, "The target cannot be brought to the analyzer focus"):
            return None
        self._show_goto(label, t, new, m.sn)
        return new

    def _go_to(self, new: MotorPositions, what: str, hint: str = "") -> bool:
        bad = out_of_range(new)
        if bad:
            QtWidgets.QMessageBox.warning(self, "Out of range", f"{what}:\n" + "\n".join(bad)
                                          + "\n\nThe positions are not changed." + hint)
            return False
        hits = self.move_collisions(new)
        if hits:
            QtWidgets.QMessageBox.warning(self, "Collision", f"{what}: the plate would touch {hits}."
                                          "\n\nThe positions are not changed." + hint)
            return False
        self.motors.set_value(new)
        self.update_view()
        return True

    def _show_goto(self, label: str, t, m: MotorPositions, sn_before: float | None = None) -> None:
        """Where the target is along the beam after a move, and the SN correction that would remove it."""
        model = self.model()
        y = model.beam_position(m, *t)
        res = self.last_result
        optic = (f" Optic for focus on it: <b>{res.required_optic_position:.4f}</b>."
                 if res is not None and res.required_optic_position is not None else "")
        if sn_before is not None:
            text = (f"<b>{label}</b> on the analyzer focus: ST = {m.st:.4f}, SZ = {m.sz:.4f}, "
                    f"<b>SN = {m.sn:.4f}</b> (ΔSN = {unsigned_zero(m.sn - sn_before, 4):+.4f} mm).{optic}")
            self.goto_label.setStyleSheet("color: #207020;")
        else:
            text = f"<b>{label}</b> on the beam with SN = {m.sn:.4f} kept: ST = {m.st:.4f}, SZ = {m.sz:.4f}.{optic}<br>"
            if abs(y) < TOLERANCE:
                text += "It is on the analyzer focus."
            else:
                text += (f"It is <b>{abs(y) * 1000:.0f} µm {'downstream' if y > 0 else 'upstream'}</b> of the analyzer "
                         f"focus (model); ΔSN = {sn_to_focus(model, m, *t):+.4f} mm (ST compensating) would remove it.")
                text += (" <b>Too far: the spectra would be distorted — Correct SN?</b>" if abs(y) > FOCUS_WARNING
                         else " Close enough: no SN correction needed.")
            self.goto_label.setStyleSheet("color: #b00;" if abs(y) > FOCUS_WARNING else "color: #207020;")
        self.goto_label.setText(text)
        self.goto_label.show()

    # -- anti-collision ------------------------------------------------------
    def collision_hits(self, m: MotorPositions, optic_positions) -> list[str]:
        """Solids (analyzer, OSA, ...) the plate touches at m with the optic at any of these absolute positions."""
        model = self.model()
        ys = [self.calibration().focus_for_position(model, p) for p in optic_positions]
        return collisions(model, m, self._layout_getter(), self.record.collision_geometry(), ys,
                          self.calibration().reference_y(model))

    def move_collisions(self, new: MotorPositions, optic_new: float | None = None, optic_now: float | None = None) -> str:
        """What the plate touches at `new`, with the optic where it is now (`optic_now`, default: the entered
        position) or refocused (`optic_new`, default: the position focusing on the illuminated surface at
        `new`); empty if nothing."""
        optic_now = self.optic_pos.value() if optic_now is None else optic_now
        if optic_new is None:
            res = focus_correction(self.model(), new, self._layout_getter(), self.calibration(), self.optic_pos.value())
            optic_new = res.required_optic_position
        out = []
        for name, positions in (("with the optic where it is now", [optic_now]),
                                ("with the optic refocused", [] if optic_new is None else [optic_new])):
            hits = self.collision_hits(new, positions)
            if hits:
                out.append(f"{', '.join(hits)} ({name})")
        return "; ".join(out)

    def describe_limits(self, m: MotorPositions) -> tuple[str, list[str]]:
        """Collision-free ST / SN / SZ ranges at m (optic as entered) as text, and the solids touched now."""
        model, layout, geo = self.model(), self._layout_getter(), self.record.collision_geometry()
        y = self.calibration().focus_for_position(model, self.optic_pos.value())
        fixed_y = self.calibration().reference_y(model)  # where the OSA stays
        hits = collisions(model, m, layout, geo, [y], fixed_y)
        head = (f"Anti-collision ({self.optic_type.currentText()} at {self.optic_pos.value():.4f}, "
                f"margin {geo.margin:g} mm)")
        if hits:
            return f"<b>{head}: COLLISION now with {', '.join(hits)}.</b>", hits
        limits = motor_limits(model, m, layout, geo, [y], TRAVEL, fixed_y)
        parts = []
        for name, lim in limits.items():
            label, *_ = MOTOR_SPECS[name]
            lo = f"{lim.lo:.3f}" + (f" ({lim.lo_by})" if lim.lo_by != "travel" else "")
            hi = f"{lim.hi:.3f}" + (f" ({lim.hi_by})" if lim.hi_by != "travel" else "")
            parts.append(f"{label} {lo} … {hi}")
        text = f"{head}, one motor moved at a time: " + " · ".join(parts)
        shadow = in_acceptance(geo, [y], fixed_y)
        if shadow:
            text += (f"<br><b>{', '.join(shadow)} in the analyzer acceptance cone (±{ACCEPTANCE_HALF_ANGLE:g}°): "
                     "it would shadow the electrons.</b>")
        return text, []

    def update_view(self) -> None:
        layout = self._layout_getter()
        model = self.model()
        m = self.motors.value()
        res = focus_correction(model, m, layout, self.calibration(), self.optic_pos.value())
        text, hits = self.describe_limits(m)
        self.limits_label.setText(text)
        self.limits_label.setStyleSheet("color: #b00;" if hits else "color: #555;")
        self.limits_label.show()
        _, ax_plane = draw_schematic(self.figure, model, m, layout, res, self.optic_type.currentText(),
                                     self.record.collision_geometry(), tuple(hits),
                                     self.calibration().reference_y(model))
        self._plane = (ax_plane, model, m, layout)
        self._show_cursor(None)
        self.canvas.draw_idle()
        self.result_label.setText(self.describe(res))
        self.last_result = res

    # -- cursor readout ------------------------------------------------------
    def _on_canvas_motion(self, event) -> None:
        if self._plane is None or event.inaxes is not self._plane[0] or event.xdata is None:
            self._show_cursor(None)
        else:
            self._show_cursor((event.xdata, event.ydata))

    def cursor_text(self, st: float, sz: float) -> str:
        """Readout for the sample plane point (ST, SZ): plate position and what lies there."""
        _, model, m, layout = self._plane
        c = model.config
        u, v = model.plate_from_stage_frame(m, (c.st0 - st, c.sz0 - sz))
        text = f"cursor: ST = {st:.3f} mm, SZ = {sz:.3f} mm   (plate x = {u:.2f}, y = {v:.2f} mm)"
        hits = []
        for s in layout.samples:
            u0, v0, u1, v1 = s.bounds()
            if u0 <= u <= u1 and v0 <= v <= v1:
                hits.append(s.name)
        if hits:
            text += "   on " + ", ".join(hits)
        return text

    def _show_cursor(self, point) -> None:
        self.cursor_label.setText("cursor: ST = –, SZ = –" if point is None else self.cursor_text(*point))

    def describe_focal_plane(self) -> str:
        """Which surface height is on the analyzer focal plane (the camera "SN = 0" line) now.

        SN_f refers to the standard plate, so a surface put on that line shows its height
        above the plate top whatever SN reads (e.g. SN_f = -0.1 after maintenance)."""
        model, m = self.model(), self.motors.value()
        plate = model.plate
        w = model.focal_plane_height(m)
        _, _, sn_top = model.reference_motors(0.0, 0.0, plate.total_thickness)
        return (f"Analyzer focal plane (camera “SN = 0” line) at these positions: surface "
                f"H = {w - plate.total_thickness:.3f} mm above the plate top "
                f"(plate top in focus at SN = {sn_top:.3f}, SN_f = {self.config().sn_f:.3f}).")

    def describe(self, res) -> str:
        if res.hit is None:
            return "<b>The beam misses the plate</b> (or runs parallel to it).<br>" + self.describe_focal_plane()
        st, sz, sn = self.model().reference_motors(*res.plate_uv, res.surface_w)
        lines = [
            f"Beam lands on <b>{res.target}</b>: the point that comes onto the beam at ST = {st:.3f}, "
            f"SZ = {sz:.3f}, SN = {sn:.3f} with SRn = {self.config().srn_ref:g}, SRz = 0.",
            f"Beam spot is {abs(res.hit[1]):.3f} mm {'downstream' if res.hit[1] > 0 else 'upstream'} of the analyzer focus."
            if abs(res.hit[1]) >= TOLERANCE else "Beam spot is on the analyzer focus.",
            self.describe_focal_plane(),
        ]
        if abs(res.required_optic_position - res.optic_position) < TOLERANCE:
            lines.append(f"<b>Optic position {res.optic_position:.4f}: in focus on {res.target}.</b>")
        else:
            lines.append(
                f"<b>Optic position for focus on {res.target}: {res.required_optic_position:.4f}</b> "
                f"(entered: {res.optic_position:.4f})."
            )
        return "<br>".join(lines)
