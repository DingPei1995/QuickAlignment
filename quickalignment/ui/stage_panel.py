"""Stage & optics panel: motor inputs, results and the schematic.

The schematic and the results are only recomputed when "Update" is pressed.
Calibration constants come from the current CalibrationRecord (see the
calibration window).
"""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from dataclasses import replace

from ._qt import QtCore, QtWidgets
from ..calibration import CalibrationRecord
from ..schematic import draw_schematic
from ..stage import OPTIC_TYPES, MotorPositions, OpticsCalibration, StageConfig, StageModel, focus_correction

Qt = QtCore.Qt

MOTOR_SPECS = {  # name: (label, min, max, decimals, step, suffix)
    "st": ("ST", -1000, 1000, 4, 0.1, " mm"),
    "sn": ("SN", -1000, 1000, 4, 0.1, " mm"),
    "sz": ("SZ", -1000, 1000, 4, 0.1, " mm"),
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
OPTIC_DIRECTIONS = ["+ moves optic downstream (towards sample)", "+ moves optic upstream (away from sample)"]


def spin(value: float, lo: float = -1000, hi: float = 1000, decimals: int = 3, step: float = 0.1, suffix: str = " mm"):
    box = QtWidgets.QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setSuffix(suffix)
    box.setValue(value)
    box.setKeyboardTracking(False)
    return box


class MotorForm(QtWidgets.QWidget):
    def __init__(self, motors: MotorPositions | None = None, parent=None):
        super().__init__(parent)
        motors = motors or MotorPositions()
        self.boxes = {}
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (name, (label, lo, hi, dec, step, suffix)) in enumerate(MOTOR_SPECS.items()):
            self.boxes[name] = spin(getattr(motors, name), lo, hi, dec, step, suffix)
            grid.addWidget(QtWidgets.QLabel(label), i // 2, 2 * (i % 2))
            grid.addWidget(self.boxes[name], i // 2, 2 * (i % 2) + 1)

    def value(self) -> MotorPositions:
        return MotorPositions(**{k: b.value() for k, b in self.boxes.items()})

    def set_value(self, m: MotorPositions) -> None:
        for k, b in self.boxes.items():
            b.setValue(getattr(m, k))


class StagePanel(QtWidgets.QWidget):
    def __init__(self, layout_getter, parent=None):
        super().__init__(parent)
        self._layout_getter = layout_getter
        self.record = CalibrationRecord()

        self.motors = MotorForm()
        self.target_combo = QtWidgets.QComboBox()
        goto_btn = QtWidgets.QPushButton("Bring target to focus")
        goto_btn.setToolTip("Compute ST / SN / SZ that put the target on the beam at the analyzer focus,\nkeeping SRn, SRz, PIX, PIY as entered.")
        goto_btn.clicked.connect(self.bring_target_to_focus)
        motor_box = QtWidgets.QGroupBox("Sample stage (current / planned positions)")
        mb = QtWidgets.QVBoxLayout(motor_box)
        mb.addWidget(self.motors)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Target"))
        row.addWidget(self.target_combo, 1)
        row.addWidget(goto_btn)
        mb.addLayout(row)

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
            "and this optic position as the optics reference (saved in the user configuration)."
        )
        ref_btn.clicked.connect(self.set_optics_reference)
        self.optic_ref_label = QtWidgets.QLabel()
        self.optic_ref_label.setWordWrap(True)
        self.optic_ref_label.setStyleSheet("color: #555;")
        optic_box = QtWidgets.QGroupBox("Focusing optic (along the beam)")
        of = QtWidgets.QFormLayout(optic_box)
        of.addRow("Type", self.optic_type)
        of.addRow("Optic position", self.optic_pos)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(use_btn)
        buttons.addWidget(ref_btn)
        of.addRow(buttons)
        of.addRow(self.optic_ref_label)

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

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        for w in (motor_box, optic_box, update_btn, self.result_label, self.cal_status):
            lv.addWidget(w)
        lv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(430)

        self.figure = Figure(figsize=(11, 5.5))
        self.canvas = FigureCanvasQTAgg(self.figure)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(1, 1)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)

        self.last_result = None
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
        self._show_record()

    def _show_record(self) -> None:
        record, optics = self.record, self.record.optics
        if optics.enabled:
            m = optics.motors
            ref = (f"in focus at optic {optics.optic_position:.4f} with ST {m.st:.4f}, SZ {m.sz:.4f}, SN {m.sn:.4f}, "
                   f"SRn {m.srn:g}, SRz {m.srz:g}")
        else:
            ref = f"in focus on the analyzer focus at optic {optics.optic_position:.4f}"
        self.optic_ref_label.setText(f"Optics reference: {ref}")
        self.cal_status.setText(f"Configuration in use: <b>{record.label}</b> — {record.comment}")

    def config(self) -> StageConfig:
        return self.record.config

    def calibration(self) -> OpticsCalibration:
        return self.record.optics

    def current_record(self) -> CalibrationRecord:
        """The configuration in use with the optic type and position as entered (for saving)."""
        optics = replace(self.record.optics, optic_type=self.optic_type.currentText(), last_position=self.optic_pos.value())
        return replace(self.record, optics=optics)

    def _on_optic_type(self, text: str) -> None:
        self.record = replace(self.record, optics=replace(self.record.optics, optic_type=text))

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
        current = self.target_combo.currentText()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem("plate centre")
        for label in self.target_labels():
            self.target_combo.addItem(label)
        self.target_combo.setCurrentIndex(max(self.target_combo.findText(current), 0))
        self.target_combo.blockSignals(False)

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
    def bring_target_to_focus(self) -> None:
        t = self.target_point(self.target_combo.currentText())
        if t is None:
            return
        m = self.motors.value()
        new = self.model().motors_for_target(*t, srn=m.srn, srz=m.srz, pix=m.pix, piy=m.piy)
        self.motors.set_value(new)
        self.update_view()

    def update_view(self) -> None:
        layout = self._layout_getter()
        model = self.model()
        m = self.motors.value()
        res = focus_correction(model, m, layout, self.calibration(), self.optic_pos.value())
        draw_schematic(self.figure, model, m, layout, res, self.optic_type.currentText())
        self.canvas.draw_idle()
        self.result_label.setText(self.describe(res))
        self.last_result = res

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
