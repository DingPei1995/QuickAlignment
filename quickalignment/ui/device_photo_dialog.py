"""Devices from a close-up photo of a substrate.

A photo of the whole plate often shows only the outline of a substrate; the
devices on it are located on a second, closer photo (microscope, camera):

1. open the close-up photo
2. click on it the four corners of the substrate (or of the sample area), in
   the order of the numbers shown in the right view; drag them to refine
3. the photo is mapped onto the plate model; click on each device (on the
   photo or in the right view): its plate position and its distances from
   the substrate edges are listed
4. add the devices to the substrate

The substrate rectangle must already be at the right place on the plate
(drawn, or found on a photo of the plate); the devices are placed relative
to it and follow it when it is corrected later.
"""

from __future__ import annotations

from ._qt import QtCore, QtGui, QtWidgets
from .photo_widgets import PhotoRegistration
from .plate_editor import COLOR_DEVICE, cosmetic_pen
from ..geometry import Device, Rect, Sample, SampleLayout
from ..photo import plate_view_bounds

Qt = QtCore.Qt

COLOR_NEW = QtGui.QColor("#e00000")
COLUMNS = ["Device", "x (mm)", "y (mm)", "dx from left (mm)", "dy from bottom (mm)", "Status"]
MAX_RECTIFIED_PX = 1600  # rectified close-up: at most this many pixels across
MAX_PX_PER_MM = 100.0  # 10 µm per pixel


def substrate_view(sample: Sample) -> tuple[Rect, float]:
    """Plate rectangle around a substrate for the close-up, and its resolution (px / mm)."""
    u0, v0, u1, v1 = sample.bounds()
    m = max(1.0, 0.3 * max(u1 - u0, v1 - v0))
    bounds = (u0 - m, v0 - m, u1 + m, v1 + m)
    span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
    return bounds, min(MAX_PX_PER_MM, MAX_RECTIFIED_PX / span)


class DevicePhotoDialog(QtWidgets.QDialog):
    def __init__(self, layout: SampleLayout, sample: Sample, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Devices on {sample.name} from a photo")
        self.resize(1400, 900)
        self.layout_model, self.sample = layout, sample
        self.new: list[tuple[str, float, float]] = []  # (name, u, v)
        self._items: list[QtWidgets.QGraphicsItem] = []
        self._filling = False

        bounds, px = substrate_view(sample)
        self.reg = PhotoRegistration(layout.plate, sample.bounds(), f"substrate {sample.name}", bounds, px)
        self.reg.photo_title.setText(f"<b>Close-up photo</b> of {sample.name} (from above)")
        self.reg.changed.connect(self._on_registration)
        self.reg.plateClicked.connect(self._on_plate_click)
        self.reg.cursor_text = self._cursor_text
        self._draw_samples()

        open_btn = QtWidgets.QPushButton("Open photo…")
        open_btn.clicked.connect(self.open_photo)
        clear_btn = QtWidgets.QPushButton("Clear points")
        clear_btn.clicked.connect(self.reg.clear_corners)
        self.reference = QtWidgets.QComboBox()
        self.reference.addItems([f"corners of {sample.name}", "corners of the sample area"])
        self.reference.setToolTip("Reference points clicked on the photo: the substrate corners (close-up of the "
                                  "substrate), or the sample area corners (when the photo shows the whole area).")
        self.reference.currentIndexChanged.connect(self._on_reference)
        self.file_label = QtWidgets.QLabel("no photo")
        self.file_label.setStyleSheet("color: #555;")
        self.instruction = QtWidgets.QLabel()
        self.instruction.setWordWrap(True)

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(110)
        self.table.itemChanged.connect(self._on_name_changed)
        self.table.itemSelectionChanged.connect(self._draw_devices)
        delete_btn = QtWidgets.QPushButton("Delete selected")
        delete_btn.clicked.connect(self.delete_selected)
        QtWidgets.QShortcut(QtGui.QKeySequence(Qt.Key_Delete), self.table, self.delete_selected)
        self.add_btn = QtWidgets.QPushButton(f"Add to {sample.name}")
        self.add_btn.setStyleSheet("font-weight: bold;")
        self.add_btn.setEnabled(False)
        self.add_btn.setAutoDefault(False)
        self.add_btn.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(clear_btn)
        top.addWidget(QtWidgets.QLabel("reference"))
        top.addWidget(self.reference)
        top.addWidget(self.file_label, 1)
        rows = QtWidgets.QHBoxLayout()
        rows.addWidget(QtWidgets.QLabel(f"<b>Devices</b> on {sample.name} (edges in the front view, tab up; "
                                        "other edges can be chosen afterwards in the Samples tab)"))
        rows.addStretch(1)
        rows.addWidget(delete_btn)
        lower = QtWidgets.QVBoxLayout()
        lower.setContentsMargins(0, 0, 0, 0)
        lower.addLayout(rows)
        lower.addWidget(self.table, 1)
        lower_w = QtWidgets.QWidget()
        lower_w.setLayout(lower)
        split = QtWidgets.QSplitter(Qt.Vertical)
        split.addWidget(self.reg)
        split.addWidget(lower_w)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.add_btn)
        bottom.addWidget(cancel)
        box = QtWidgets.QVBoxLayout(self)
        box.addLayout(top)
        box.addWidget(self.instruction)
        box.addWidget(split, 1)
        box.addLayout(bottom)
        self._update_instruction()
        QtCore.QTimer.singleShot(0, lambda: self.reg.zoom_to(self._view_bounds()))

    # -- photo and reference --------------------------------------------------------
    def open_photo(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, f"Open photo of {self.sample.name}", "",
                                                        "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if path:
            self.load_photo(path)

    def load_photo(self, path: str) -> bool:
        if not self.reg.load_photo(path):
            return False
        self.file_label.setText(path)
        return True

    def _view_bounds(self) -> Rect:
        if self.reference.currentIndex() == 0:
            return substrate_view(self.sample)[0]
        return plate_view_bounds(self.layout_model.plate)

    def _on_reference(self, index: int) -> None:
        if index == 0:
            bounds, px = substrate_view(self.sample)
            self.reg.set_reference(self.sample.bounds(), f"substrate {self.sample.name}", bounds, px)
        else:
            plate = self.layout_model.plate
            self.reg.set_reference(plate.riser_bounds(), "the sample area", plate_view_bounds(plate), 40.0)
        self.reg.clear_corners()
        self.reg.zoom_to(self._view_bounds())

    def _on_registration(self) -> None:
        self._update_instruction()

    def _update_instruction(self) -> None:
        text = self.reg.corner_instruction()
        error = self.reg.error
        if self.reg.photo is None:
            text = (f"Open a close-up photo of {self.sample.name} taken from above, with its four corners "
                    "visible (or a photo of the whole sample area, then choose that reference).")
        elif text is None and error:
            text = error
        elif text is None:
            text = ("Click on each device (on the photo or in the right view); check that the outline of "
                    f"{self.sample.name} (orange) lies on the substrate, drag the points to refine.")
        color = "#c00000" if error and text == error else "#00609a"
        self.instruction.setStyleSheet(f"font-weight: bold; color: {color};")
        self.instruction.setText(text)

    # -- devices -------------------------------------------------------------------
    def _on_plate_click(self, u: float, v: float) -> None:
        if self.reg.h is not None:
            self.add_device(u, v)

    def add_device(self, u: float, v: float) -> None:
        taken = {d.name for s in self.layout_model.samples for d in s.devices} | {n for n, _, _ in self.new}
        i = 1
        while f"D{i}" in taken:
            i += 1
        self.new.append((f"D{i}", round(u, 3), round(v, 3)))
        self._fill_table()
        self.table.selectRow(len(self.new) - 1)

    def delete_selected(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        self.new = [d for r, d in enumerate(self.new) if r not in rows]
        self._fill_table()

    def devices(self) -> list[Device]:
        out = []
        for name, u, v in self.new:
            d = Device(name)
            d.set_position(self.sample, u, v)
            out.append(d)
        return out

    def _fill_table(self) -> None:
        self._filling = True
        self.table.setRowCount(len(self.new))
        u0, v0, u1, v1 = self.sample.bounds()
        for row, (name, u, v) in enumerate(self.new):
            inside = u0 <= u <= u1 and v0 <= v <= v1
            values = [name, f"{u:.3f}", f"{v:.3f}", f"{u - u0:.3f}", f"{v - v0:.3f}",
                      "ok" if inside else f"outside {self.sample.name}"]
            for col, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                if col:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if col == 5:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#207020" if inside else "#c00000")))
                self.table.setItem(row, col, item)
        self._filling = False
        self.add_btn.setEnabled(bool(self.new))
        self._draw_devices()

    def _on_name_changed(self, item) -> None:
        if self._filling or item.column() != 0:
            return
        name, u, v = self.new[item.row()]
        self.new[item.row()] = (item.text().strip() or name, u, v)
        self._draw_devices()

    # -- drawing -------------------------------------------------------------------
    def _draw_samples(self) -> None:
        """The other samples (grey), this substrate (orange) and its devices (blue) in the plate view."""
        scene = self.reg.plate_scene
        for s in self.layout_model.samples:
            u0, v0, u1, v1 = s.bounds()
            mine = s is self.sample
            item = scene.addRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0),
                                 cosmetic_pen("#ff8c00" if mine else "#909090", 2 if mine else 1),
                                 QtGui.QBrush(Qt.NoBrush))
            item.setZValue(9)
            for d in s.devices if mine else []:
                u, v = d.position(s)
                dot = scene.addEllipse(-4, -4, 8, 8, cosmetic_pen(COLOR_DEVICE, 2))
                dot.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
                dot.setPos(u, -v)
                dot.setZValue(11)
                dot.setToolTip(f"{d.name} (already on {s.name})")
        for it in scene.items():
            if it.zValue() in (9, 11):
                it.setAcceptedMouseButtons(Qt.NoButton)
        u0, v0, u1, v1 = self.sample.bounds()
        self.reg.set_photo_overlay([([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], QtGui.QColor("#ff8c00"), 2)])

    def _draw_devices(self) -> None:
        scene = self.reg.plate_scene
        for it in self._items:
            scene.removeItem(it)
        self._items = []
        selected = {i.row() for i in self.table.selectedIndexes()}
        u0, v0, u1, v1 = self.sample.bounds()
        shapes = [([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], QtGui.QColor("#ff8c00"), 2)]
        for row, (name, u, v) in enumerate(self.new):
            r = 8 if row in selected else 6
            pen = cosmetic_pen(COLOR_NEW, 2.5 if row in selected else 1.5)
            for x0, y0, x1, y1 in ((-r, 0, r, 0), (0, -r, 0, r)):
                line = scene.addLine(x0, y0, x1, y1, pen)
                line.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
                line.setPos(u, -v)
                self._items.append(line)
            label = scene.addSimpleText(name)
            label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            label.setBrush(QtGui.QBrush(COLOR_NEW))
            label.setPos(u, -v)
            self._items.append(label)
            # on the photo: a small square of 0.1 mm around the device
            e = 0.05
            shapes.append(([(u - e, v - e), (u + e, v - e), (u + e, v + e), (u - e, v + e)], COLOR_NEW,
                           3 if row in selected else 2))
        for it in self._items:
            it.setZValue(12)
            it.setAcceptedMouseButtons(Qt.NoButton)
        self.reg.set_photo_overlay(shapes)

    def _cursor_text(self, u: float, v: float) -> str:
        u0, v0, _, _ = self.sample.bounds()
        return f"dx = {u - u0:7.3f}, dy = {v - v0:7.3f} mm from the left / bottom edges of {self.sample.name}"

