"""Dialog asking which sample plate is mounted."""

from __future__ import annotations

from ._qt import QtCore, QtWidgets
from .plate_editor import plate_pixmap
from ..geometry import PLATES, PlateGeometry

Qt = QtCore.Qt

DESCRIPTIONS = {
    "standard": "Ta plate, 18 × 15.5 mm, 4 mm riser.\nSample area 11 × 15.5 mm.",
    "gating": "Ta plate with contact block (3 gold pads, 4 screws).\nSample area 11 × 10.5 mm above the block.",
}


class PlateChoiceDialog(QtWidgets.QDialog):
    def __init__(self, current: str = "standard", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Which sample plate is used?")
        self.group = QtWidgets.QButtonGroup(self)
        row = QtWidgets.QHBoxLayout()
        self._keys = list(PLATES)
        for i, key in enumerate(self._keys):
            plate = PLATES[key]
            box = QtWidgets.QVBoxLayout()
            img = QtWidgets.QLabel()
            img.setPixmap(plate_pixmap(plate, 220))
            img.setAlignment(Qt.AlignCenter)
            radio = QtWidgets.QRadioButton(plate.name)
            radio.setChecked(key == current)
            self.group.addButton(radio, i)
            desc = QtWidgets.QLabel(DESCRIPTIONS.get(key, ""))
            desc.setStyleSheet("color: #555;")
            box.addWidget(img)
            box.addWidget(radio)
            box.addWidget(desc)
            frame = QtWidgets.QFrame()
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setLayout(box)
            # clicking the picture selects the plate as well
            img.mousePressEvent = lambda _e, r=radio: r.setChecked(True)
            row.addWidget(frame)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Please confirm the sample plate mounted on the manipulator:</b>"))
        layout.addLayout(row)
        layout.addWidget(buttons)

    def plate(self) -> PlateGeometry:
        return PLATES[self._keys[max(self.group.checkedId(), 0)]]


def ask_plate(current: str = "standard", parent=None) -> PlateGeometry | None:
    dlg = PlateChoiceDialog(current, parent)
    ok = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
    return dlg.plate() if ok else None
