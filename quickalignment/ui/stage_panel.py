"""Stage & optics panel: motor inputs, optics calibration and the schematic.

The schematic and the results are only recomputed when "Update" is pressed.
"""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ._qt import QtCore, QtWidgets, Signal
from ..schematic import draw_schematic
from ..stage import MotorPositions, OpticsCalibration, StageConfig, StageModel, focus_correction

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
    "sn_f": ("SN_f (back face in focus)", " mm"),
    "srn_ref": ("SRn ref (vertical, tab up)", " °"),
    "pi_center": ("Piezo centre", " µm"),
    "srn_axis_u": ("SRn axis u on plate", " mm"),
    "srn_axis_v": ("SRn axis v on plate", " mm"),
    "srz_offset_t": ("SRz axis offset along +ST", " mm"),
    "srz_offset_n": ("SRz axis offset along +SN", " mm"),
}
MANUAL_H = "(enter H manually)"
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
    configChanged = Signal()

    def __init__(self, layout_getter, parent=None):
        super().__init__(parent)
        self._layout_getter = layout_getter

        # -- current motors ---------------------------------------------------
        self.motors = MotorForm()
        self.target_combo = QtWidgets.QComboBox()
        goto_btn = QtWidgets.QPushButton("Bring target to focus")
        goto_btn.setToolTip("Compute ST / SN / SZ that put the target on the analyzer focus,\nkeeping SRn, SRz, PIX, PIY as entered.")
        goto_btn.clicked.connect(self.bring_target_to_focus)
        motor_box = QtWidgets.QGroupBox("Sample stage (current / planned positions)")
        mb = QtWidgets.QVBoxLayout(motor_box)
        mb.addWidget(self.motors)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Target"))
        row.addWidget(self.target_combo, 1)
        row.addWidget(goto_btn)
        mb.addLayout(row)

        # -- optics calibration -------------------------------------------------
        self.cal_enabled = QtWidgets.QCheckBox("Use calibration (otherwise the optics focus is at the analyzer focus)")
        self.cal_motors = MotorForm()
        copy_btn = QtWidgets.QPushButton("Copy current stage positions")
        copy_btn.clicked.connect(lambda: self.cal_motors.set_value(self.motors.value()))
        self.cal_sample_combo = QtWidgets.QComboBox()
        self.cal_sample_combo.currentIndexChanged.connect(self._on_cal_sample)
        self.cal_h = spin(0.5, 0, 50, 3, 0.1)
        self.optic_pos = spin(0.0, -10000, 10000, 4, 0.01)
        self.optic_dir = QtWidgets.QComboBox()
        self.optic_dir.addItems(OPTIC_DIRECTIONS)
        cal_box = QtWidgets.QGroupBox("Optics calibration (after the first focusing)")
        cb = QtWidgets.QVBoxLayout(cal_box)
        cb.addWidget(self.cal_enabled)
        cb.addWidget(QtWidgets.QLabel("Stage positions when the focus was optimised:"))
        cb.addWidget(self.cal_motors)
        cb.addWidget(copy_btn)
        cf = QtWidgets.QFormLayout()
        hrow = QtWidgets.QHBoxLayout()
        hrow.addWidget(self.cal_sample_combo, 1)
        hrow.addWidget(self.cal_h)
        cf.addRow("Illuminated sample / H", hrow)
        cf.addRow("Optic position at best focus", self.optic_pos)
        cf.addRow("Optic motor direction", self.optic_dir)
        cb.addLayout(cf)

        # -- stage parameters ---------------------------------------------------
        cfg = StageConfig()
        self.cfg_boxes = {}
        par_box = QtWidgets.QGroupBox("Stage parameters (calibration constants)")
        pf = QtWidgets.QFormLayout(par_box)
        for name, (label, suffix) in CONFIG_SPECS.items():
            lo, hi = (0, 300) if name == "pi_center" else (-1000, 1000)
            self.cfg_boxes[name] = spin(getattr(cfg, name), lo, hi, 4, 0.1, suffix)
            self.cfg_boxes[name].valueChanged.connect(self.configChanged)
            pf.addRow(label, self.cfg_boxes[name])

        # calibration lives in its own (non-modal) window, opened from the toolbar
        self.cal_dialog = QtWidgets.QDialog(self)
        self.cal_dialog.setWindowTitle("Calibration")
        dv = QtWidgets.QVBoxLayout(self.cal_dialog)
        dv.addWidget(cal_box)
        dv.addWidget(par_box)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.cal_dialog.hide)
        dv.addWidget(close_btn, 0, Qt.AlignRight)

        update_btn = QtWidgets.QPushButton("Update schematic && optics")
        update_btn.setMinimumHeight(36)
        update_btn.setStyleSheet("font-weight: bold;")
        update_btn.clicked.connect(self.update_view)

        self.cal_status = QtWidgets.QLabel()
        self.cal_status.setWordWrap(True)
        self.cal_status.setStyleSheet("color: #555;")
        self.cal_enabled.toggled.connect(self._update_cal_status)
        self.optic_pos.valueChanged.connect(self._update_cal_status)
        self._update_cal_status()

        self.result_label = QtWidgets.QLabel("Press “Update schematic & optics”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        for w in (motor_box, update_btn, self.result_label, self.cal_status):
            lv.addWidget(w)
        lv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(430)

        # -- right: schematic ---------------------------------------------------------
        self.figure = Figure(figsize=(11, 5.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        right = self.canvas

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)

        self.last_result = None
        self.refresh_targets()

    # -- state ----------------------------------------------------------------
    def config(self) -> StageConfig:
        return StageConfig(**{k: b.value() for k, b in self.cfg_boxes.items()})

    def set_config(self, cfg: StageConfig) -> None:
        for k, b in self.cfg_boxes.items():
            b.setValue(getattr(cfg, k))

    def calibration(self) -> OpticsCalibration:
        return OpticsCalibration(
            enabled=self.cal_enabled.isChecked(),
            motors=self.cal_motors.value(),
            surface_w=self._layout_getter().plate.total_thickness + self.cal_h.value(),
            optic_position=self.optic_pos.value(),
            optic_sign=1 if self.optic_dir.currentIndex() == 0 else -1,
        )

    def set_calibration(self, cal: OpticsCalibration) -> None:
        self.cal_enabled.setChecked(cal.enabled)
        self.cal_motors.set_value(cal.motors)
        self.cal_h.setValue(cal.surface_w - self._layout_getter().plate.total_thickness)
        self.optic_pos.setValue(cal.optic_position)
        self.optic_dir.setCurrentIndex(0 if cal.optic_sign > 0 else 1)

    def model(self) -> StageModel:
        return StageModel(self.config(), self._layout_getter().plate)

    def open_calibration(self) -> None:
        self.cal_dialog.show()
        self.cal_dialog.raise_()
        self.cal_dialog.activateWindow()

    def _update_cal_status(self) -> None:
        if self.cal_enabled.isChecked():
            self.cal_status.setText(f"Optics calibration ON (optic at {self.optic_pos.value():.4f} at the reference). Edit via “Calibration…”.")
        else:
            self.cal_status.setText("Optics calibration OFF: optics focus assumed at the analyzer focus. Set it via “Calibration…”.")

    # -- actions ----------------------------------------------------------------
    def refresh_targets(self) -> None:
        targets = self._layout_getter().targets()
        for combo in (self.target_combo, self.cal_sample_combo):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("plate centre" if combo is self.target_combo else MANUAL_H)
            for label, *_ in targets:
                combo.addItem(label)
            idx = combo.findText(current)
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)

    def _target(self, label: str):
        plate = self._layout_getter().plate
        if label == "plate centre":
            return 0.0, 0.0, plate.total_thickness
        for name, u, v, h in self._layout_getter().targets():
            if name == label:
                return u, v, plate.total_thickness + h
        return None

    def _on_cal_sample(self) -> None:
        t = self._target(self.cal_sample_combo.currentText())
        if t is not None:
            self.cal_h.setValue(t[2] - self._layout_getter().plate.total_thickness)

    def bring_target_to_focus(self) -> None:
        t = self._target(self.target_combo.currentText())
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
        cal = self.calibration()
        res = focus_correction(model, m, layout, cal)
        draw_schematic(self.figure, model, m, layout, res)
        self.canvas.draw_idle()
        self.result_label.setText(self.describe(res))
        self.last_result = res

    def describe(self, res) -> str:
        if res.hit is None:
            return "<b>The beam misses the plate</b> (or runs parallel to it)."
        st, sz, sn = self.model().reference_motors(*res.plate_uv, res.surface_w)
        lines = [
            f"Beam lands on <b>{res.target}</b>, at the point found at ST = {st:.3f}, SZ = {sz:.3f}, SN = {sn:.3f} "
            "(SRn = ref, SRz = 0).",
            f"Beam spot is {abs(res.hit[1]):.3f} mm {'downstream' if res.hit[1] > 0 else 'upstream'} of the analyzer focus"
            if abs(res.hit[1]) >= TOLERANCE else "Beam spot is on the analyzer focus.",
        ]
        d = res.delta
        if abs(d) < TOLERANCE:
            lines.append("<b>Optics: no move needed.</b>")
        else:
            where = "TOWARDS the sample (downstream)" if d > 0 else "AWAY from the sample (upstream)"
            lines.append(f"<b>Optics: move the focus {abs(d):.3f} mm along the beam, {where}.</b>")
        if res.new_optic_position is not None:
            lines.append(f"New optic motor position: <b>{res.new_optic_position:.4f}</b> (from calibration).")
        else:
            lines.append("Not calibrated: move is relative to the analyzer focus.")
        return "<br>".join(lines)
