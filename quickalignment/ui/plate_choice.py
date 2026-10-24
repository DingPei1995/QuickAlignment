"""Dialog asking which sample plate is mounted."""

from __future__ import annotations

from ._qt import QtCore, QtWidgets
from .plate_editor import plate_pixmap
from ..geometry import PLATES, SN_REFERENCE_W, STANDARD_PLATE, PlateGeometry, custom_plate, custom_plate_params

Qt = QtCore.Qt

DESCRIPTIONS = {
    "standard": "Ta plate, 18 × 15.5 mm, 4 mm riser.\nSample area 11 × 15.5 mm.",
    "gating": "Ta plate with contact block (3 gold pads, 4 screws).\nSample area 11 × 10.5 mm above the block.",
}
CUSTOM_DEFAULT = {"length": 11.0, "width": 15.5, "height": 5.0}


class PlateChoiceDialog(QtWidgets.QDialog):
    def __init__(self, current: str | PlateGeometry = "standard", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Which sample plate is used?")
        key = current.key if isinstance(current, PlateGeometry) else current
        params = custom_plate_params(current) if key == "custom" and isinstance(current, PlateGeometry) else CUSTOM_DEFAULT
        self.group = QtWidgets.QButtonGroup(self)
        row = QtWidgets.QHBoxLayout()
        self._keys = [*PLATES, "custom"]
        for i, k in enumerate(self._keys):
            box = QtWidgets.QVBoxLayout()
            img = QtWidgets.QLabel()
            img.setAlignment(Qt.AlignCenter)
            img.setMinimumSize(220, 220)
            radio = QtWidgets.QRadioButton(PLATES[k].name if k in PLATES else "Custom plate")
            radio.setChecked(k == key)
            self.group.addButton(radio, i)
            box.addWidget(img)
            box.addWidget(radio)
            if k in PLATES:
                img.setPixmap(plate_pixmap(PLATES[k], 220))
                desc = QtWidgets.QLabel(DESCRIPTIONS.get(k, ""))
                desc.setStyleSheet("color: #555;")
                box.addWidget(desc)
            else:
                self.custom_img = img
                box.addLayout(self._custom_form(params))
                box.addWidget(self.custom_note)
            box.addStretch(1)
            frame = QtWidgets.QFrame()
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
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
        layout.addWidget(buttons)

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

        self.custom_length = box(params["length"], 0.1, base.width, "Block size along x (left–right), centred on the plate.")
        self.custom_width = box(params["width"], 0.1, base.height, "Block size along y (bottom–top), centred on the plate.")
        self.custom_height = box(params["height"], base.base_thickness + 0.01, 50.0,
                                 "Height of the block top above the back face of the plate (standard plate: 5.0 mm).")
        self.custom_note = QtWidgets.QLabel()
        self.custom_note.setWordWrap(True)
        self.custom_note.setStyleSheet("color: #555;")
        form = QtWidgets.QFormLayout()
        form.addRow(QtWidgets.QLabel("Back plate without riser,\nblock centred on the plate:"))
        form.addRow("Length (x)", self.custom_length)
        form.addRow("Width (y)", self.custom_width)
        form.addRow("Top above back face", self.custom_height)
        return form

    def _update_custom(self, *_) -> None:
        plate = self.custom_plate()
        self.custom_img.setPixmap(plate_pixmap(plate, 220))
        d = plate.total_thickness - SN_REFERENCE_W
        self.custom_note.setText(
            f"SN still refers to the standard plate: the block top is in focus at SN = SN_f {d:+.3f} mm, "
            f"a sample of height H at SN = SN_f {d:+.3f} + H."
        )

    def _on_custom_edit(self, *_) -> None:
        # editing the block means the custom plate is meant
        self.group.button(self._keys.index("custom")).setChecked(True)
        self._update_custom()

    def custom_plate(self) -> PlateGeometry:
        return custom_plate(self.custom_length.value(), self.custom_width.value(), self.custom_height.value())

    def plate(self) -> PlateGeometry:
        key = self._keys[max(self.group.checkedId(), 0)]
        return self.custom_plate() if key == "custom" else PLATES[key]


def ask_plate(current: str | PlateGeometry = "standard", parent=None) -> PlateGeometry | None:
    dlg = PlateChoiceDialog(current, parent)
    ok = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
    return dlg.plate() if ok else None
