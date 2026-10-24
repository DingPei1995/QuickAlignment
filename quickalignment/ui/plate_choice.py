"""Dialog asking which sample plate (and, at start-up, which focusing optic) is mounted."""

from __future__ import annotations

from ._qt import QtCore, QtWidgets
from .plate_editor import plate_pixmap
from ..geometry import PLATES, STANDARD_PLATE, PlateGeometry, custom_plate, custom_plate_params
from ..stage import OPTIC_TYPES

Qt = QtCore.Qt

TITLES = {"standard": "Standard Ta plate", "gating": "Gating plate", "custom": "Custom plate"}
DESCRIPTIONS = {
    "standard": "Ta plate, 18 × 15.5 mm, height 5.0 mm (from the back face).\nSample area 11 × 15.5 mm.",
    "gating": "Ta plate with contact block (3 gold pads, 4 screws).\nSample area 11 × 10.5 mm above the block.",
    "custom": "Back plate only, with a block centred left–right. Height is measured from the back face "
              "of the plate (standard plate: 5.0 mm).",
}
CUSTOM_DEFAULT = {"length": 11.0, "width": 15.5, "height": 5.0, "center_y": 0.0}
PICTURE = 220
FRAME_WIDTH = 300  # every choice gets the same width


class PlateChoiceDialog(QtWidgets.QDialog):
    """Plate choice; with `optic` (one of OPTIC_TYPES) the focusing optic is asked as well."""

    def __init__(self, current: str | PlateGeometry = "standard", parent=None, optic: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Which sample plate is used?" if optic is None else "Sample plate and focusing optic")
        key = current.key if isinstance(current, PlateGeometry) else current
        params = custom_plate_params(current) if key == "custom" and isinstance(current, PlateGeometry) else CUSTOM_DEFAULT
        self.group = QtWidgets.QButtonGroup(self)
        row = QtWidgets.QHBoxLayout()
        self._keys = [*PLATES, "custom"]
        for i, k in enumerate(self._keys):
            box = QtWidgets.QVBoxLayout()
            img = QtWidgets.QLabel()
            img.setAlignment(Qt.AlignCenter)
            img.setFixedHeight(PICTURE)
            radio = QtWidgets.QRadioButton(TITLES[k])
            radio.setStyleSheet("font-weight: bold;")
            radio.setChecked(k == key)
            self.group.addButton(radio, i)
            desc = QtWidgets.QLabel(DESCRIPTIONS[k])
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #555;")
            for w in (img, radio, desc):
                box.addWidget(w)
            if k in PLATES:
                img.setPixmap(plate_pixmap(PLATES[k], PICTURE))
            else:
                self.custom_img = img
                box.addLayout(self._custom_form(params))
                box.addWidget(self.custom_note)
            box.addStretch(1)
            frame = QtWidgets.QFrame()
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setFixedWidth(FRAME_WIDTH)
            frame.setLayout(box)
            # clicking the picture selects the plate as well
            img.mousePressEvent = lambda _e, r=radio: r.setChecked(True)
            row.addWidget(frame)
        self._update_custom()
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Please confirm the sample plate mounted on the manipulator:</b>"))
        layout.addLayout(row)
        self.optic_group = None
        if optic is not None:
            layout.addWidget(self._optic_box(optic))
        layout.addWidget(buttons)
        # the minimum size Qt computes ignores the wrapped texts, which then run into the pictures
        self.setMinimumSize(self.sizeHint())

    def _optic_box(self, optic: str) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Focusing optic in use (its newest configuration is loaded)")
        row = QtWidgets.QHBoxLayout(box)
        self.optic_group = QtWidgets.QButtonGroup(self)
        for i, name in enumerate(OPTIC_TYPES):
            radio = QtWidgets.QRadioButton(name[0].upper() + name[1:])
            radio.setChecked(name == optic)
            self.optic_group.addButton(radio, i)
            row.addWidget(radio)
        row.addStretch(1)
        return box

    def optic(self) -> str | None:
        if self.optic_group is None:
            return None
        return OPTIC_TYPES[max(self.optic_group.checkedId(), 0)]

    def _custom_form(self, params: dict) -> QtWidgets.QFormLayout:
        base = STANDARD_PLATE

        def box(value, lo, hi, tip):
            b = QtWidgets.QDoubleSpinBox()
            b.setRange(lo, hi)
            b.setDecimals(3)
            b.setSingleStep(0.1)
            b.setSuffix(" mm")
            b.setValue(value)
            b.setToolTip(tip)
            b.valueChanged.connect(self._on_custom_edit)
            return b

        self.custom_length = box(params["length"], 0.1, base.width, "Block size along x (left–right), centred left–right.")
        self.custom_width = box(params["width"], 0.1, base.height, "Block size along y (bottom–top).")
        self.custom_center_y = box(params["center_y"], -base.height / 2, base.height / 2,
                                   "Block centre along y (0 = centre of the back plate, + = towards the tab).")
        self.custom_height = box(params["height"], base.base_thickness + 0.01, 50.0,
                                 "Height of the block top, measured from the back face of the plate (standard plate: 5.0 mm).")
        self.custom_note = QtWidgets.QLabel()
        self.custom_note.setWordWrap(True)
        self.custom_note.setStyleSheet("color: #555;")
        form = QtWidgets.QFormLayout()
        form.addRow("Length (x)", self.custom_length)
        form.addRow("Width (y)", self.custom_width)
        form.addRow("Centre y", self.custom_center_y)
        form.addRow("Height", self.custom_height)
        return form

    def _on_custom_edit(self, *_) -> None:
        # editing the block means the custom plate is meant
        self.group.button(self._keys.index("custom")).setChecked(True)
        self._update_custom()

    def _update_custom(self) -> None:
        try:
            plate = self.custom_plate()
        except ValueError as e:
            self.custom_note.setText(f"<span style='color:#c00'>{e}</span>")
            return
        self.custom_img.setPixmap(plate_pixmap(plate, PICTURE))
        self.custom_note.setText("")

    def custom_plate(self) -> PlateGeometry:
        return custom_plate(self.custom_length.value(), self.custom_width.value(), self.custom_height.value(),
                            self.custom_center_y.value())

    def plate(self) -> PlateGeometry:
        key = self._keys[max(self.group.checkedId(), 0)]
        return self.custom_plate() if key == "custom" else PLATES[key]

    def accept(self) -> None:
        try:
            self.plate()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Custom plate", str(e))
            return
        super().accept()


def ask_plate(current: str | PlateGeometry = "standard", parent=None) -> PlateGeometry | None:
    dlg = PlateChoiceDialog(current, parent)
    ok = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
    return dlg.plate() if ok else None


def ask_setup(current: str | PlateGeometry = "standard", optic: str = OPTIC_TYPES[0],
              parent=None) -> tuple[PlateGeometry, str] | None:
    """Plate and focusing optic (start-up, new session)."""
    dlg = PlateChoiceDialog(current, parent, optic)
    ok = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
    return (dlg.plate(), dlg.optic()) if ok else None
