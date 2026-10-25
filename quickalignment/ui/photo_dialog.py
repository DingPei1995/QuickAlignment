"""Samples from a photo: the plate photographed from above (sample side).

1. open the photo
2. click the four corners of the sample area (top left, top right, bottom
   right, bottom left; tab at the top), drag them to refine
3. the photo is mapped onto the plate model (right view) and the samples are
   found by their colour: either what differs from the bare plate, or what is
   close to sample colours picked by clicking on samples (leaves out silver
   paint, glue, wires); adjust the ΔE threshold, merge the pieces of a sample
   broken up by paint
4. enter the sample height H (not visible on a photo from above), choose the
   samples to keep and add them to the plate

The detected rectangles are a starting point: they can be moved / resized in
the Samples tab like drawn ones, and "Found here" corrects them later.
"""

from __future__ import annotations

import numpy as np

from ._qt import QtCore, QtGui, QtWidgets, Signal
from .plate_editor import COLOR_SAMPLE, cosmetic_pen, draw_plate_items
from ..geometry import PlateGeometry, Sample
from ..photo import (
    PX_PER_MM, Detection, Rectified, apply_homography, check_corners, corner_points, detect_samples, homography,
    plate_view_bounds, rectify, rgb_to_lab,
)

Qt = QtCore.Qt

COLOR_CORNER = QtGui.QColor("#00b4ff")
COLOR_MODEL = QtGui.QColor("#00b4ff")
COLOR_FOUND = QtGui.QColor("#18c418")
RESULT_COLUMNS = ["Use", "Name", "x (mm)", "y (mm)", "L (mm)", "W (mm)", "H (mm)", "ΔE"]
MODES = ["colour different from the bare plate", "colour of picked samples"]
DEFAULT_THRESHOLD = (12.0, 20.0)  # per mode
PATCH_MM = 0.3  # side of the patch averaged when picking the bare plate colour


def qimage_to_array(image: QtGui.QImage) -> np.ndarray:
    image = image.convertToFormat(QtGui.QImage.Format_RGB888)
    w, h, bpl = image.width(), image.height(), image.bytesPerLine()
    ptr = image.constBits()
    if hasattr(ptr, "setsize"):  # PyQt5
        ptr.setsize(bpl * h)
    data = np.frombuffer(ptr, np.uint8, count=bpl * h).reshape(h, bpl)
    return data[:, : 3 * w].reshape(h, w, 3).copy()


def array_to_qimage(arr: np.ndarray, fmt=QtGui.QImage.Format_RGB888) -> QtGui.QImage:
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    return QtGui.QImage(arr.data, w, h, arr.strides[0], fmt).copy()


class ZoomView(QtWidgets.QGraphicsView):
    """Wheel = zoom, middle drag = pan, right click = fit."""

    clicked = Signal(float, float)  # left click on the scene (not on a corner marker)

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setMinimumSize(380, 380)
        self._pan: QtCore.QPoint | None = None

    def fit(self) -> None:
        if not self.sceneRect().isEmpty():
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def wheelEvent(self, event):
        f = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.RightButton:
            self.fit()
            return
        if event.button() == Qt.LeftButton and not any(isinstance(it, CornerItem) for it in self.items(event.pos())):
            p = self.mapToScene(event.pos())
            self.clicked.emit(p.x(), p.y())
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan is not None:
            d = event.pos() - self._pan
            self._pan = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan is not None and event.button() == Qt.MiddleButton:
            self._pan = None
            self.unsetCursor()
            return
        super().mouseReleaseEvent(event)


class CornerItem(QtWidgets.QGraphicsEllipseItem):
    """Draggable marker of a clicked corner (constant size on screen)."""

    R = 7

    def __init__(self, index: int, dialog: PhotoImportDialog):
        super().__init__(-self.R, -self.R, 2 * self.R, 2 * self.R)
        self.dialog = dialog
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
                      | QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setPen(cosmetic_pen(COLOR_CORNER, 2))
        self.setBrush(QtGui.QBrush(QtGui.QColor(0, 180, 255, 60)))
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(20)
        for x0, y0, x1, y1 in ((-self.R - 4, 0, self.R + 4, 0), (0, -self.R - 4, 0, self.R + 4)):
            QtWidgets.QGraphicsLineItem(x0, y0, x1, y1, self).setPen(cosmetic_pen(COLOR_CORNER, 1))
        label = QtWidgets.QGraphicsSimpleTextItem(str(index + 1), self)
        label.setBrush(QtGui.QBrush(COLOR_CORNER))
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        label.setPos(self.R + 2, -self.R - 14)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self.dialog.corners_moved()
        return super().itemChange(change, value)


class PhotoImportDialog(QtWidgets.QDialog):
    def __init__(self, plate: PlateGeometry, default_height: float, existing: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Samples from a photo")
        self.resize(1400, 900)
        self.plate = plate
        self.existing = list(existing or [])
        self.photo: np.ndarray | None = None
        self.corners: list[CornerItem] = []
        self.rectified: Rectified | None = None
        self.background: np.ndarray | None = None  # picked bare plate colour (Lab), None: automatic
        self.sample_colors: list[np.ndarray] = []  # picked sample colours (Lab)
        self.detections: list[Detection] = []
        self._photo_overlay: list[QtWidgets.QGraphicsItem] = []
        self._plate_overlay: list[QtWidgets.QGraphicsItem] = []
        self._filling = False

        # left: the photo
        self.photo_scene = QtWidgets.QGraphicsScene(self)
        self.photo_view = ZoomView(self.photo_scene)
        self.photo_view.clicked.connect(self._on_photo_click)
        self.photo_item = QtWidgets.QGraphicsPixmapItem()
        self.photo_item.setTransformationMode(Qt.SmoothTransformation)
        self.photo_scene.addItem(self.photo_item)

        # right: the plate model with the rectified photo on it
        self.plate_scene = QtWidgets.QGraphicsScene(self)
        draw_plate_items(self.plate_scene, plate)
        for it in self.plate_scene.items():
            it.setAcceptedMouseButtons(Qt.NoButton)
        self.rect_item = QtWidgets.QGraphicsPixmapItem()
        self.rect_item.setTransformationMode(Qt.SmoothTransformation)
        self.rect_item.setZValue(5)
        self.plate_scene.addItem(self.rect_item)
        self.mask_item = QtWidgets.QGraphicsPixmapItem()
        self.mask_item.setZValue(6)
        self.plate_scene.addItem(self.mask_item)
        self._draw_model_lines()
        u0, v0, u1, v1 = plate_view_bounds(plate, 1.0)
        self.plate_scene.setSceneRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0))
        self.plate_view = ZoomView(self.plate_scene)
        self.plate_view.clicked.connect(self._on_plate_click)

        open_btn = QtWidgets.QPushButton("Open photo…")
        open_btn.clicked.connect(self.open_photo)
        reset_btn = QtWidgets.QPushButton("Clear corners")
        reset_btn.clicked.connect(self.clear_corners)
        self.file_label = QtWidgets.QLabel("no photo")
        self.file_label.setStyleSheet("color: #555;")
        self.instruction = QtWidgets.QLabel()
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet("font-weight: bold; color: #00609a;")

        def spin(lo, hi, value, step, decimals, suffix, tip):
            box = QtWidgets.QDoubleSpinBox()
            box.setRange(lo, hi)
            box.setValue(value)
            box.setSingleStep(step)
            box.setDecimals(decimals)
            box.setSuffix(suffix)
            box.setToolTip(tip)
            box.valueChanged.connect(self.detect)
            return box

        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(MODES)
        self.mode.setToolTip("Different from the bare plate: everything on the plate is found (also silver paint, "
                             "glue).\nPicked samples: click on each kind of sample in the right view; only what has "
                             "a colour close to them is found.")
        self.mode.currentIndexChanged.connect(self._on_mode)
        self.threshold = spin(1, 150, DEFAULT_THRESHOLD[0], 1, 1, "", "Colour difference ΔE (CIELAB).\n"
                              "Bare plate mode: a point differing more than this from the bare plate belongs to a "
                              "sample (lower: finds samples close to the plate colour; higher: ignores shadows and "
                              "reflections).\nPicked samples mode: a point closer than this to a picked colour "
                              "belongs to a sample.")
        self.min_area = spin(0.01, 50, 0.2, 0.05, 2, " mm²", "Smaller spots are ignored (dust, scratches).")
        self.border = spin(0, 1.5, 0.15, 0.05, 2, " mm", "Strip along the sample area edge that is left out "
                           "(the edge itself shows on the photo).\nA sample reaching into it is extended to the edge.")
        self.smooth = spin(0, 0.5, 0.1, 0.05, 2, " mm", "Noise filter: fills small gaps (glare) and removes specks "
                           "of about this size.")
        self.pick_btn = QtWidgets.QPushButton("Pick bare plate colour")
        self.pick_btn.setCheckable(True)
        self.pick_btn.setToolTip("Then click on bare plate in the right view. Use it when samples cover most of "
                                 "the sample area or the automatic colour is wrong.")
        self.auto_btn = QtWidgets.QPushButton("Automatic")
        self.auto_btn.setToolTip("Bare plate colour estimated from the photo")
        self.auto_btn.clicked.connect(self.auto_background)
        self.swatch = QtWidgets.QLabel()
        self.swatch.setFixedSize(40, 18)
        self.pick_sample_btn = QtWidgets.QPushButton("Pick sample colour")
        self.pick_sample_btn.setCheckable(True)
        self.pick_sample_btn.setToolTip("Then click on a sample in the right view (once per kind of sample).")
        self.clear_colors_btn = QtWidgets.QPushButton("Clear")
        self.clear_colors_btn.setToolTip("Forget the picked sample colours")
        self.clear_colors_btn.clicked.connect(self.clear_sample_colors)
        self.sample_swatches = QtWidgets.QLabel()
        for b in (self.pick_btn, self.pick_sample_btn):
            b.toggled.connect(self._on_pick_toggled)
        self.opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(80)
        self.opacity.setMaximumWidth(120)
        self.opacity.setToolTip("Opacity of the photo over the plate model")
        self.opacity.valueChanged.connect(lambda v: self.rect_item.setOpacity(v / 100))
        self.rect_item.setOpacity(0.8)
        self.show_mask = QtWidgets.QCheckBox("show what differs")
        self.show_mask.setChecked(True)
        self.show_mask.toggled.connect(self.mask_item.setVisible)

        self.height_box = QtWidgets.QDoubleSpinBox()
        self.height_box.setRange(0.0, 20.0)
        self.height_box.setDecimals(3)
        self.height_box.setSingleStep(0.1)
        self.height_box.setSuffix(" mm")
        self.height_box.setValue(default_height)
        self.height_box.setToolTip("Sample height H above the plate surface: it cannot be seen on a photo from "
                                   "above.\nIt can be changed per sample in the table.")
        height_all = QtWidgets.QPushButton("Set H of all")
        height_all.clicked.connect(self.set_height_of_all)

        self.table = QtWidgets.QTableWidget(0, len(RESULT_COLUMNS))
        self.table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._on_table_changed)
        self.table.itemSelectionChanged.connect(self._draw_detections)
        merge_btn = QtWidgets.QPushButton("Merge selected")
        merge_btn.setToolTip("One sample from the selected rows (pieces of a sample broken up by paint or wires).\n"
                             "Changing the detection settings afterwards finds the pieces again.")
        merge_btn.clicked.connect(self.merge_selected)

        self.replace = QtWidgets.QCheckBox("Remove the samples already on the plate")
        self.replace.setVisible(bool(self.existing))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.add_btn = QtWidgets.QPushButton("Add to plate")
        self.add_btn.setStyleSheet("font-weight: bold;")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(reset_btn)
        top.addWidget(self.file_label, 1)
        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel("find samples by"))
        params.addWidget(self.mode)
        params.addSpacing(8)
        for text, w in (("ΔE threshold", self.threshold), ("min. size", self.min_area),
                        ("border left out", self.border), ("noise filter", self.smooth)):
            params.addWidget(QtWidgets.QLabel(text))
            params.addWidget(w)
            params.addSpacing(8)
        params.addStretch(1)
        params2 = QtWidgets.QHBoxLayout()
        self.plate_color_widgets = [QtWidgets.QLabel("bare plate colour"), self.swatch, self.pick_btn, self.auto_btn]
        self.sample_color_widgets = [QtWidgets.QLabel("sample colours"), self.sample_swatches, self.pick_sample_btn,
                                     self.clear_colors_btn]
        for w in self.plate_color_widgets + self.sample_color_widgets:
            params2.addWidget(w)
        params2.addSpacing(16)
        params2.addWidget(QtWidgets.QLabel("photo opacity"))
        params2.addWidget(self.opacity)
        params2.addWidget(self.show_mask)
        params2.addStretch(1)

        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel("<b>Photo</b> (from above, sample side): click the corners of the sample area"))
        left.addWidget(self.photo_view, 1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        right = QtWidgets.QVBoxLayout()
        right.addWidget(QtWidgets.QLabel("<b>On the plate model</b> (front view, tab up; green: samples found)"))
        right.addWidget(self.plate_view, 1)
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right)
        views = QtWidgets.QSplitter()
        views.addWidget(left_w)
        views.addWidget(right_w)

        height_row = QtWidgets.QHBoxLayout()
        height_row.addWidget(QtWidgets.QLabel("<b>Samples found</b>   sample height H"))
        height_row.addWidget(self.height_box)
        height_row.addWidget(height_all)
        note = QtWidgets.QLabel("(not visible from above; Si wafer substrate 0.525 mm)")
        note.setStyleSheet("color: #555;")
        height_row.addWidget(note)
        height_row.addStretch(1)
        height_row.addWidget(merge_btn)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self.replace)
        bottom.addStretch(1)
        bottom.addWidget(self.add_btn)
        bottom.addWidget(cancel)

        lower = QtWidgets.QVBoxLayout()
        lower.setContentsMargins(0, 0, 0, 0)
        lower.addLayout(height_row)
        lower.addWidget(self.table, 1)
        lower.addWidget(self.status)
        lower_w = QtWidgets.QWidget()
        lower_w.setLayout(lower)
        split = QtWidgets.QSplitter(Qt.Vertical)
        split.addWidget(views)
        split.addWidget(lower_w)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.table.setMinimumHeight(130)

        box = QtWidgets.QVBoxLayout(self)
        box.addLayout(top)
        box.addWidget(self.instruction)
        box.addLayout(params)
        box.addLayout(params2)
        box.addWidget(split, 1)
        box.addLayout(bottom)
        self._on_mode(0)

    # -- photo and corners ---------------------------------------------------------
    def open_photo(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open plate photo", "",
                                                        "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if path:
            self.load_photo(path)

    def load_photo(self, path: str) -> bool:
        reader = QtGui.QImageReader(path)
        reader.setAutoTransform(True)  # phone photos: EXIF orientation
        image = reader.read()
        if image.isNull():
            QtWidgets.QMessageBox.warning(self, "Open photo", f"The photo could not be read:\n{path}\n\n"
                                          f"{reader.errorString()}")
            return False
        self.set_photo(qimage_to_array(image))
        self.file_label.setText(path)
        return True

    def set_photo(self, rgb: np.ndarray) -> None:
        self.photo = rgb
        self.photo_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(rgb)))
        h, w = rgb.shape[:2]
        self.photo_scene.setSceneRect(QtCore.QRectF(0, 0, w, h))
        self.clear_corners()
        self.photo_view.fit()

    def clear_corners(self) -> None:
        for c in self.corners:
            self.photo_scene.removeItem(c)
        self.corners = []
        self._geometry_changed()

    def set_corners(self, points) -> None:
        """Place all four corners (photo pixel coordinates)."""
        self.clear_corners()
        for x, y in points:
            self._add_corner(x, y)
        self._geometry_changed()

    def _add_corner(self, x: float, y: float) -> None:
        item = CornerItem(len(self.corners), self)
        self.corners.append(item)
        self.photo_scene.addItem(item)
        item.setPos(x, y)

    def _on_photo_click(self, x: float, y: float) -> None:
        if self.photo is None or len(self.corners) >= 4:
            return
        self._add_corner(x, y)
        self._geometry_changed()

    def corners_moved(self) -> None:
        if len(self.corners) == 4:
            self._geometry_changed()

    def corner_positions(self) -> list[tuple[float, float]]:
        return [(c.pos().x(), c.pos().y()) for c in self.corners]

    def _update_instruction(self, error: str = "") -> None:
        if self.photo is None:
            text = "Open a photo of the plate taken from straight above (sample side, whole sample area visible)."
        elif len(self.corners) < 4:
            name, (u, v) = corner_points(self.plate)[len(self.corners)]
            text = (f"Click corner {len(self.corners) + 1} of 4 of the sample area: {name} "
                    f"(x = {u:g}, y = {v:g} mm). Wheel = zoom, middle drag = pan, right click = whole photo.")
        elif error:
            text = error
        elif self.mode.currentIndex() == 1 and not self.sample_colors:
            text = "Click on a sample in the right view to pick its colour (once per kind of sample)."
        else:
            text = ("Check that the plate model (blue) lies on the plate in the photo; drag the corners to refine. "
                    "Adjust the ΔE threshold until the green boxes match the samples.")
        self.instruction.setStyleSheet(f"font-weight: bold; color: {'#c00000' if error else '#00609a'};")
        self.instruction.setText(text)

    # -- mapping -------------------------------------------------------------------
    def _geometry_changed(self) -> None:
        self.rectified = None
        error = ""
        if self.photo is not None and len(self.corners) == 4:
            pts = self.corner_positions()
            try:
                check_corners(self.plate, pts)
                h = homography([p for _, p in corner_points(self.plate)], pts)
                self.rectified = rectify(self.photo, h, plate_view_bounds(self.plate), PX_PER_MM)
                self._h = h
            except ValueError as exc:
                error = str(exc)
        self._update_instruction(error)
        self._draw_photo_overlay()
        if self.rectified is None:
            self.rect_item.setPixmap(QtGui.QPixmap())
        else:
            r = self.rectified
            self.rect_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(r.pixels)))
            self.rect_item.setScale(1 / r.px_per_mm)
            self.rect_item.setPos(r.u0, -r.v1)
            self.mask_item.setScale(1 / r.px_per_mm)
            self.mask_item.setPos(r.u0, -r.v1)
        self.detect()

    def _draw_model_lines(self) -> None:
        """Plate model outlines over the photo in the right view (to check the registration)."""
        pen = cosmetic_pen(COLOR_MODEL, 1.2)
        outline = QtGui.QPolygonF([QtCore.QPointF(u, -v) for u, v in self.plate.outline()])
        items = [self.plate_scene.addPolygon(outline, pen)]
        for r in [self.plate.riser_bounds()] + ([self.plate.contact_block] if self.plate.contact_block else []):
            items.append(self.plate_scene.addRect(QtCore.QRectF(r[0], -r[3], r[2] - r[0], r[3] - r[1]), pen))
        for it in items:
            it.setZValue(8)
            it.setAcceptedMouseButtons(Qt.NoButton)

    def _model_shapes(self) -> list[list[tuple[float, float]]]:
        shapes = [self.plate.outline()]
        for u0, v0, u1, v1 in [self.plate.riser_bounds()] + ([self.plate.contact_block] if self.plate.contact_block else []):
            shapes.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        return shapes

    def _draw_photo_overlay(self) -> None:
        for it in self._photo_overlay:
            self.photo_scene.removeItem(it)
        self._photo_overlay = []
        if self.rectified is None:
            return

        def poly(points, pen, brush=Qt.NoBrush):
            q = apply_homography(self._h, points)
            item = self.photo_scene.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in q]), pen,
                                               QtGui.QBrush(brush))
            item.setZValue(10)
            item.setAcceptedMouseButtons(Qt.NoButton)
            self._photo_overlay.append(item)

        for shape in self._model_shapes():
            poly(shape, cosmetic_pen(COLOR_MODEL, 1.5))
        for row, d in enumerate(self.detections):
            if self._used(row):
                poly([(d.u0, d.v0), (d.u1, d.v0), (d.u1, d.v1), (d.u0, d.v1)], cosmetic_pen(COLOR_FOUND, 2))

    # -- detection -----------------------------------------------------------------
    def _on_mode(self, index: int) -> None:
        for w in self.plate_color_widgets:
            w.setVisible(index == 0)
        for w in self.sample_color_widgets:
            w.setVisible(index == 1)
        self.pick_btn.setChecked(False)
        self.pick_sample_btn.setChecked(index == 1 and not self.sample_colors)
        self.threshold.blockSignals(True)
        self.threshold.setValue(DEFAULT_THRESHOLD[index])
        self.threshold.blockSignals(False)
        self._update_instruction()
        self.detect()

    def _on_pick_toggled(self, on: bool) -> None:
        # one pick mode at a time
        if on:
            other = self.pick_sample_btn if self.sender() is self.pick_btn else self.pick_btn
            other.setChecked(False)
        picking = self.pick_btn.isChecked() or self.pick_sample_btn.isChecked()
        self.plate_view.viewport().setCursor(Qt.CrossCursor if picking else Qt.ArrowCursor)

    def auto_background(self) -> None:
        self.background = None
        self.pick_btn.setChecked(False)
        self.detect()

    def clear_sample_colors(self) -> None:
        self.sample_colors = []
        self.pick_sample_btn.setChecked(True)
        self._update_instruction()
        self.detect()

    def _on_plate_click(self, x: float, y: float) -> None:
        if self.rectified is None:
            return
        if self.pick_btn.isChecked():
            self.pick_background(x, -y)
            self.pick_btn.setChecked(False)
        elif self.pick_sample_btn.isChecked():
            self.pick_sample_color(x, -y)
            self.pick_sample_btn.setChecked(False)

    def _patch_color(self, u: float, v: float) -> np.ndarray | None:
        """Median Lab colour of a small patch around the plate point (u, v)."""
        r = self.rectified
        if r is None:
            return None
        half = PATCH_MM / 2
        m = r.mask_of((u - half, v - half, u + half, v + half)) & r.valid
        return np.median(rgb_to_lab(r.pixels[m]), axis=0) if m.any() else None

    def pick_background(self, u: float, v: float) -> bool:
        lab = self._patch_color(u, v)
        if lab is None:
            return False
        self.background = lab
        self.detect()
        return True

    def pick_sample_color(self, u: float, v: float) -> bool:
        lab = self._patch_color(u, v)
        if lab is None:
            return False
        self.sample_colors.append(lab)
        if self.mode.currentIndex() != 1:
            self.mode.setCurrentIndex(1)  # detects
        else:
            self._update_instruction()
            self.detect()
        return True

    def detect(self) -> None:
        states = self._row_states()
        by_colour = self.mode.currentIndex() == 1
        if self.rectified is None or (by_colour and not self.sample_colors):
            self.detections = []
            self.mask_item.setPixmap(QtGui.QPixmap())
        else:
            try:
                result = detect_samples(self.rectified, self.plate.riser_bounds(), self.threshold.value(),
                                        self.min_area.value(), self.border.value(), self.smooth.value(),
                                        self.background, self.sample_colors if by_colour else None)
            except ValueError as exc:
                self._update_instruction(str(exc))
                self.detections = []
                self.mask_item.setPixmap(QtGui.QPixmap())
            else:
                self.detections = result.detections
                if not by_colour:
                    self._shown_background = result.background
                rgba = np.zeros(result.mask.shape + (4,), np.uint8)
                rgba[result.mask] = (255, 0, 200, 110)
                self.mask_item.setPixmap(QtGui.QPixmap.fromImage(
                    array_to_qimage(rgba, QtGui.QImage.Format_RGBA8888)))
        self._fill_table(states)
        self._update_swatch()
        self._draw_photo_overlay()
        self._draw_detections()

    def _update_swatch(self) -> None:
        self.sample_swatches.setText(" ".join(
            '<span style="background: rgb({},{},{});">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>'.format(*lab_to_rgb(c))
            for c in self.sample_colors) or "none")
        lab = self.background if self.background is not None else getattr(self, "_shown_background", None)
        if lab is None or self.rectified is None:
            self.swatch.setStyleSheet("border: 1px solid #888; background: none;")
            self.swatch.setToolTip("")
            return
        r, g, b = lab_to_rgb(lab)
        self.swatch.setStyleSheet(f"border: 1px solid #888; background: rgb({r},{g},{b});")
        self.swatch.setToolTip(("picked" if self.background is not None else "automatic")
                               + f": L* {lab[0]:.0f}, a* {lab[1]:.0f}, b* {lab[2]:.0f}")

    def _draw_detections(self) -> None:
        for it in self._plate_overlay:
            self.plate_scene.removeItem(it)
        self._plate_overlay = []
        selected = {i.row() for i in self.table.selectedIndexes()}
        for row, d in enumerate(self.detections):
            used = self._used(row)
            pen = cosmetic_pen(COLOR_FOUND if used else "#888888", 3 if row in selected else 1.8,
                               Qt.SolidLine if used else Qt.DashLine)
            item = self.plate_scene.addRect(QtCore.QRectF(d.u0, -d.v1, d.u1 - d.u0, d.v1 - d.v0), pen,
                                            QtGui.QBrush(COLOR_SAMPLE if row in selected else Qt.NoBrush))
            item.setZValue(9)
            item.setAcceptedMouseButtons(Qt.NoButton)
            label = self.plate_scene.addSimpleText(self._name(row))
            label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            label.setBrush(QtGui.QBrush(QtGui.QColor("#0a6a0a")))
            label.setPos(d.u0, -d.v1)
            label.setZValue(9)
            self._plate_overlay += [item, label]
        n = sum(self._used(r) for r in range(len(self.detections)))
        self.add_btn.setEnabled(n > 0)
        if self.rectified is None:
            self.status.setText("")
        else:
            self.status.setText(f"{len(self.detections)} sample(s) found, {n} to add. Touching samples come out as "
                                "one box; positions can be refined afterwards in the Samples tab.")

    # -- results table ------------------------------------------------------------
    def _default_names(self, n: int) -> list[str]:
        taken = set(self.existing)
        names, i = [], 1
        while len(names) < n:
            if f"S{i}" not in taken:
                names.append(f"S{i}")
            i += 1
        return names

    def _row_states(self) -> list[tuple]:
        """(tick, name, H) of the table rows."""
        return [(self.table.item(row, 0).checkState(), self.table.item(row, 1).text(), self.table.item(row, 6).text())
                for row in range(self.table.rowCount())]

    def _fill_table(self, states: list) -> None:
        """Rows for the detections; states[row] (tick, name, H) are kept where given (not None)."""
        self._filling = True
        self.table.setRowCount(len(self.detections))
        names = self._default_names(len(self.detections))
        for row, d in enumerate(self.detections):
            (u, v), (length, width) = d.center, d.size
            state = states[row] if row < len(states) else None
            check, name, height = state or (Qt.Checked, names[row], f"{self.height_box.value():.3f}")
            values = ["", name, f"{u:.2f}", f"{v:.2f}", f"{length:.2f}", f"{width:.2f}", height, f"{d.delta_e:.0f}"]
            for col, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                if col == 0:
                    item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setCheckState(check)
                elif col not in (1, 6):
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, col, item)
        self._filling = False

    def _on_table_changed(self, item) -> None:
        if self._filling:
            return
        if item.column() == 6:
            try:
                value = float(item.text())
                ok = 0 <= value <= 20
            except ValueError:
                ok = False
            self._filling = True
            item.setText(f"{value:.3f}" if ok else f"{self.height_box.value():.3f}")
            self._filling = False
        self._draw_detections()
        self._draw_photo_overlay()

    def _used(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return item is not None and item.checkState() == Qt.Checked

    def _name(self, row: int) -> str:
        item = self.table.item(row, 1)
        return item.text().strip() if item is not None else ""

    def merge_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if len(rows) < 2:
            QtWidgets.QMessageBox.information(self, "Merge", "Select the rows of the pieces to merge (Ctrl + click).")
            return
        states = self._row_states()
        merged = Detection.merged([self.detections[r] for r in rows])
        keep = [r for r in range(len(self.detections)) if r not in rows]
        self.detections = [merged] + [self.detections[r] for r in keep]
        self._fill_table([states[rows[0]]] + [states[r] for r in keep])
        self.table.clearSelection()
        self.table.selectRow(0)
        self._draw_photo_overlay()
        self._draw_detections()

    def set_height_of_all(self) -> None:
        self._filling = True
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setText(f"{self.height_box.value():.3f}")
        self._filling = False

    # -- result ------------------------------------------------------------------
    def samples(self) -> list[Sample]:
        """The ticked samples (names may still clash with existing ones: the editor makes them unique)."""
        out = []
        for row, d in enumerate(self.detections):
            if not self._used(row):
                continue
            (u, v), (length, width) = d.center, d.size
            out.append(Sample(self._name(row), u=round(u, 3), v=round(v, 3), length=round(length, 3),
                              width=round(width, 3), height=float(self.table.item(row, 6).text())))
        return out

    def replace_existing(self) -> bool:
        return self.replace.isVisible() and self.replace.isChecked()


def lab_to_rgb(lab) -> tuple[int, int, int]:
    """CIELAB (D65) -> sRGB, for the colour swatch."""
    lum, a, b = (float(x) for x in lab)
    fy = (lum + 16) / 116
    f = np.array([fy + a / 500, fy, fy - b / 200])
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560],
                  [0.0556434, -0.2040259, 1.0572252]])
    c = np.clip(m @ xyz, 0, 1)
    c = np.where(c > 0.0031308, 1.055 * c ** (1 / 2.4) - 0.055, 12.92 * c)
    r, g, bl = (int(round(x * 255)) for x in c)
    return r, g, bl
