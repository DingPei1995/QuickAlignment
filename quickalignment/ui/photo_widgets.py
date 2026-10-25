"""Shared parts of the photo dialogs: a photo registered on the plate model.

PhotoRegistration shows the photo (left) and the plate model (right). The
reference points (corners of a plate rectangle: the sample area, or a
substrate) are numbered in the right view, the next one to click in red;
each click on the photo places that point. With four points a homography
maps the photo onto the plate model, the rectified photo is laid over it, and
the cursor shows plate coordinates in both views.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from ._qt import QtCore, QtGui, QtWidgets, Signal
from .plate_editor import cosmetic_pen, draw_plate_items
from ..geometry import PlateGeometry, Rect
from ..photo import Rectified, apply_homography, check_corners, homography, plate_view_bounds, rect_corners, rectify

Qt = QtCore.Qt

COLOR_CORNER = QtGui.QColor("#00b4ff")
COLOR_MODEL = QtGui.QColor("#00b4ff")
COLOR_NEXT = QtGui.QColor("#e00000")
COLOR_TODO = QtGui.QColor("#808080")
DRAG_PX = 4  # a left press moved less than this is a click


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


def read_photo(path: str, parent=None) -> np.ndarray | None:
    reader = QtGui.QImageReader(path)
    reader.setAutoTransform(True)  # phone photos: EXIF orientation
    image = reader.read()
    if image.isNull():
        QtWidgets.QMessageBox.warning(parent, "Open photo", f"The photo could not be read:\n{path}\n\n"
                                      f"{reader.errorString()}")
        return None
    return qimage_to_array(image)


def lab_to_rgb(lab) -> tuple[int, int, int]:
    """CIELAB (D65) -> sRGB, for colour swatches."""
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


class ZoomView(QtWidgets.QGraphicsView):
    """Wheel = zoom, middle drag = pan, right click = fit; left click / drag reported in scene coordinates."""

    clicked = Signal(float, float)
    dragged = Signal(float, float, float, float)  # x0, y0, x1, y1 (only with drag_enabled)
    hovered = Signal(float, float)
    left = Signal()

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 360)
        self.drag_enabled = False
        self._zoomed = False  # the user zoomed: a resize (e.g. scroll bars appearing) must not refit
        self._pan: QtCore.QPoint | None = None
        self._press: QtCore.QPoint | None = None
        self._band: QtWidgets.QGraphicsRectItem | None = None

    def fit(self) -> None:
        self._zoomed = False
        if not self.sceneRect().isEmpty():
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._zoomed:
            self.fit()

    def wheelEvent(self, event):
        f = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        scale = self.transform().m11() * f
        view = self.viewport().rect()
        rect = self.sceneRect()
        fit_scale = min(view.width() / max(rect.width(), 1e-9), view.height() / max(rect.height(), 1e-9))
        if f < 1 and scale < fit_scale * 0.5:
            return
        self._zoomed = True
        self.scale(f, f)

    def _on_marker(self, pos) -> bool:
        return any(it.flags() & QtWidgets.QGraphicsItem.ItemIsMovable for it in self.items(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.RightButton:
            self.fit()
            return
        if event.button() == Qt.LeftButton and not self._on_marker(event.pos()):
            self._press = event.pos()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        p = self.mapToScene(event.pos())
        self.hovered.emit(p.x(), p.y())
        if self._pan is not None:
            d = event.pos() - self._pan
            self._pan = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        if self._press is not None:
            if self.drag_enabled and (event.pos() - self._press).manhattanLength() >= DRAG_PX:
                r = QtCore.QRectF(self.mapToScene(self._press), p).normalized()
                if self._band is None:
                    self._band = self.scene().addRect(r, cosmetic_pen("#18c418", 1.5, Qt.DashLine))
                    self._band.setZValue(50)
                self._band.setRect(r)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan is not None and event.button() == Qt.MiddleButton:
            self._pan = None
            self.unsetCursor()
            return
        if self._press is not None and event.button() == Qt.LeftButton:
            p0, p1 = self.mapToScene(self._press), self.mapToScene(event.pos())
            moved = (event.pos() - self._press).manhattanLength() >= DRAG_PX
            self._press = None
            if self._band is not None:
                self.scene().removeItem(self._band)
                self._band = None
            if moved and self.drag_enabled:
                self.dragged.emit(p0.x(), p0.y(), p1.x(), p1.y())
            elif not moved:
                self.clicked.emit(p1.x(), p1.y())
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.left.emit()
        super().leaveEvent(event)


class CornerItem(QtWidgets.QGraphicsEllipseItem):
    """Draggable marker of a point clicked on the photo (constant size on screen)."""

    R = 7

    def __init__(self, index: int, on_moved: Callable[[], None]):
        super().__init__(-self.R, -self.R, 2 * self.R, 2 * self.R)
        self.on_moved = on_moved
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
        font.setPointSize(font.pointSize() + 2)
        label.setFont(font)
        label.setPos(self.R + 2, -self.R - 16)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self.on_moved()
        return super().itemChange(change, value)


class RefMarker(QtWidgets.QGraphicsEllipseItem):
    """Numbered reference point in the plate view: red = click it next on the photo, blue = placed."""

    R = 9

    def __init__(self, index: int):
        super().__init__(-self.R, -self.R, 2 * self.R, 2 * self.R)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setZValue(30)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.label = QtWidgets.QGraphicsSimpleTextItem(str(index + 1), self)
        font = self.label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 3)
        self.label.setFont(font)
        rect = self.label.boundingRect()
        self.label.setPos(-rect.width() / 2, -rect.height() / 2)

    def set_state(self, state: str) -> None:
        color = {"next": COLOR_NEXT, "done": COLOR_CORNER}.get(state, COLOR_TODO)
        big = state == "next"
        r = self.R + (4 if big else 0)
        self.setRect(-r, -r, 2 * r, 2 * r)
        self.setPen(cosmetic_pen(color, 3 if big else 2))
        self.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 220)))
        self.label.setBrush(QtGui.QBrush(color))


class PhotoRegistration(QtWidgets.QWidget):
    """Photo (left) registered on the plate model (right) by four reference points."""

    changed = Signal()  # photo, points or registration changed
    plateClicked = Signal(float, float)  # u, v: click on the right view, or on the registered photo
    plateDragged = Signal(float, float, float, float)  # u0, v0, u1, v1 (right view, with drag_enabled)

    def __init__(self, plate: PlateGeometry, ref_rect: Rect, ref_label: str, view_bounds: Rect, px_per_mm: float,
                 parent=None):
        super().__init__(parent)
        self.plate = plate
        self.photo: np.ndarray | None = None
        self.corners: list[CornerItem] = []
        self.rectified: Rectified | None = None
        self.h: np.ndarray | None = None  # plate -> photo
        self.error = ""
        self.cursor_text: Callable[[float, float], str] | None = None  # extra text for the cursor read-out
        self._photo_overlay: list[QtWidgets.QGraphicsItem] = []
        self._overlay_shapes: list = []

        self.photo_scene = QtWidgets.QGraphicsScene(self)
        self.photo_view = ZoomView(self.photo_scene)
        self.photo_view.clicked.connect(self._on_photo_click)
        self.photo_view.hovered.connect(self._on_photo_hover)
        self.photo_view.left.connect(lambda: self.cursor_label.setText(self._idle_cursor_text()))
        self.photo_item = QtWidgets.QGraphicsPixmapItem()
        self.photo_item.setTransformationMode(Qt.SmoothTransformation)
        self.photo_scene.addItem(self.photo_item)

        self.plate_scene = QtWidgets.QGraphicsScene(self)
        draw_plate_items(self.plate_scene, plate)
        for it in self.plate_scene.items():
            it.setAcceptedMouseButtons(Qt.NoButton)
        self.rect_item = QtWidgets.QGraphicsPixmapItem()
        self.rect_item.setTransformationMode(Qt.SmoothTransformation)
        self.rect_item.setZValue(5)
        self.rect_item.setOpacity(0.8)
        self.plate_scene.addItem(self.rect_item)
        self._model_items = []
        u0, v0, u1, v1 = plate_view_bounds(plate, 1.0)
        self.plate_scene.setSceneRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0))
        self.plate_view = ZoomView(self.plate_scene)
        self.plate_view.clicked.connect(lambda x, y: self.plateClicked.emit(x, -y))
        self.plate_view.dragged.connect(lambda x0, y0, x1, y1: self.plateDragged.emit(
            min(x0, x1), -max(y0, y1), max(x0, x1), -min(y0, y1)))
        self.plate_view.hovered.connect(lambda x, y: self._show_cursor(x, -y))
        self.plate_view.left.connect(lambda: self.cursor_label.setText(self._idle_cursor_text()))
        self.ref_markers = [RefMarker(i) for i in range(4)]
        for m in self.ref_markers:
            self.plate_scene.addItem(m)
        self.set_reference(ref_rect, ref_label, view_bounds, px_per_mm)

        self.photo_title = QtWidgets.QLabel()
        self.cursor_label = QtWidgets.QLabel()
        self.cursor_label.setStyleSheet("font-family: monospace;")
        self.opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(80)
        self.opacity.setMaximumWidth(120)
        self.opacity.setToolTip("Opacity of the photo over the plate model")
        self.opacity.valueChanged.connect(lambda v: self.rect_item.setOpacity(v / 100))

        left = QtWidgets.QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(self.photo_title)
        left.addWidget(self.photo_view, 1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QHBoxLayout()
        title.addWidget(QtWidgets.QLabel("<b>Plate model</b> (front view, tab up)"))
        title.addStretch(1)
        title.addWidget(QtWidgets.QLabel("photo opacity"))
        title.addWidget(self.opacity)
        right.addLayout(title)
        right.addWidget(self.plate_view, 1)
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right)
        split = QtWidgets.QSplitter()
        split.addWidget(left_w)
        split.addWidget(right_w)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(split, 1)
        box.addWidget(self.cursor_label)
        self._update_markers()

    # -- reference -----------------------------------------------------------------
    def set_reference(self, ref_rect: Rect, ref_label: str, view_bounds: Rect, px_per_mm: float) -> None:
        """Reference rectangle whose corners are clicked, and the plate rectangle the photo is mapped on
        (view_bounds, at px_per_mm); clears the clicked points."""
        self.ref_rect, self.ref_label, self.view_bounds, self.px_per_mm = ref_rect, ref_label, view_bounds, px_per_mm
        self.ref_points = rect_corners(ref_rect)
        for marker, (_, (u, v)) in zip(self.ref_markers, self.ref_points):
            marker.setPos(u, -v)
        for it in self._model_items:
            self.plate_scene.removeItem(it)
        pen = cosmetic_pen(COLOR_MODEL, 1.2)
        outline = QtGui.QPolygonF([QtCore.QPointF(u, -v) for u, v in self.plate.outline()])
        self._model_items = [self.plate_scene.addPolygon(outline, pen)]
        for u0, v0, u1, v1 in self.model_rects():
            self._model_items.append(self.plate_scene.addRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0), pen))
        for it in self._model_items:
            it.setZValue(8)
            it.setAcceptedMouseButtons(Qt.NoButton)
        if self.corners:
            self.clear_corners()

    def zoom_to(self, rect: Rect) -> None:
        """Show this plate rectangle in the right view."""
        u0, v0, u1, v1 = rect
        self.plate_view.fitInView(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0), Qt.KeepAspectRatio)
        self.plate_view._zoomed = True

    def model_rects(self) -> list[Rect]:
        rects = [self.plate.riser_bounds()] + ([self.plate.contact_block] if self.plate.contact_block else [])
        return rects + ([self.ref_rect] if self.ref_rect not in rects else [])

    def _update_markers(self) -> None:
        n = len(self.corners)
        for i, m in enumerate(self.ref_markers):
            m.set_state("done" if i < n else "next" if i == n else "todo")

    def corner_instruction(self) -> str | None:
        """What to click next, or None when the four points are placed."""
        if self.photo is None:
            return None
        n = len(self.corners)
        if n >= 4:
            return None
        name, (u, v) = self.ref_points[n]
        return (f"Click on the photo the point {n + 1} shown in red in the right view: {name} corner of "
                f"{self.ref_label} (x = {u:g}, y = {v:g} mm). Wheel = zoom, middle drag = pan, right click = "
                "whole view; markers can be dragged afterwards.")

    # -- photo and points ----------------------------------------------------------
    def load_photo(self, path: str) -> bool:
        rgb = read_photo(path, self)
        if rgb is None:
            return False
        self.set_photo(rgb)
        return True

    def set_photo(self, rgb: np.ndarray) -> None:
        self.photo = rgb
        self.photo_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(rgb)))
        h, w = rgb.shape[:2]
        m = 0.15 * max(w, h)  # margin: points at the photo edge can be centred when zoomed in
        self.photo_scene.setSceneRect(QtCore.QRectF(-m, -m, w + 2 * m, h + 2 * m))
        self.clear_corners()
        self.photo_view.fit()

    def clear_corners(self) -> None:
        for c in self.corners:
            self.photo_scene.removeItem(c)
        self.corners = []
        self._registration_changed()

    def set_corners(self, points) -> None:
        """Place all four points (photo pixel coordinates)."""
        for c in self.corners:
            self.photo_scene.removeItem(c)
        self.corners = []
        for x, y in points:
            self._add_corner(x, y)
        self._registration_changed()

    def corner_positions(self) -> list[tuple[float, float]]:
        return [(c.pos().x(), c.pos().y()) for c in self.corners]

    def _add_corner(self, x: float, y: float) -> None:
        item = CornerItem(len(self.corners), self._on_corner_moved)
        self.corners.append(item)
        self.photo_scene.addItem(item)
        item.setPos(x, y)

    def _on_corner_moved(self) -> None:
        if len(self.corners) == 4:
            self._registration_changed()

    def _on_photo_click(self, x: float, y: float) -> None:
        if self.photo is None:
            return
        if len(self.corners) < 4:
            self._add_corner(x, y)
            self._registration_changed()
        elif self.h is not None:
            u, v = self.photo_to_plate(x, y)
            self.plateClicked.emit(u, v)

    # -- registration --------------------------------------------------------------
    def _registration_changed(self) -> None:
        self.rectified, self.h, self.error = None, None, ""
        if self.photo is not None and len(self.corners) == 4:
            pts = self.corner_positions()
            ref = [p for _, p in self.ref_points]
            try:
                check_corners(ref, pts)
                self.h = homography(ref, pts)
                self.rectified = rectify(self.photo, self.h, self.view_bounds, self.px_per_mm)
            except ValueError as exc:
                self.h, self.error = None, str(exc)
        self._update_markers()
        if self.rectified is None:
            self.rect_item.setPixmap(QtGui.QPixmap())
        else:
            r = self.rectified
            self.rect_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(r.pixels)))
            self.rect_item.setScale(1 / r.px_per_mm)
            self.rect_item.setPos(r.u0, -r.v1)
        self._redraw_photo_overlay()
        self.cursor_label.setText(self._idle_cursor_text())
        self.changed.emit()

    def photo_to_plate(self, x: float, y: float) -> tuple[float, float]:
        u, v = apply_homography(np.linalg.inv(self.h), [(x, y)])[0]
        return float(u), float(v)

    def place_on_rectified(self, item: QtWidgets.QGraphicsPixmapItem) -> None:
        """Put a pixmap made on the rectified grid at its place in the plate view."""
        r = self.rectified
        item.setScale(1 / r.px_per_mm)
        item.setPos(r.u0, -r.v1)

    # -- photo overlay: plate model + shapes given by the dialog --------------------
    def set_photo_overlay(self, shapes) -> None:
        """Shapes drawn on the photo: [(plate points, colour, width), …], besides the plate model."""
        self._overlay_shapes = list(shapes)
        self._redraw_photo_overlay()

    def _redraw_photo_overlay(self) -> None:
        for it in self._photo_overlay:
            self.photo_scene.removeItem(it)
        self._photo_overlay = []
        if self.h is None:
            return
        model = [(self.plate.outline(), COLOR_MODEL, 1.5)]
        model += [([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], COLOR_MODEL, 1.5) for u0, v0, u1, v1 in self.model_rects()]
        for points, color, width in model + self._overlay_shapes:
            q = apply_homography(self.h, points)
            item = self.photo_scene.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in q]),
                                               cosmetic_pen(color, width))
            item.setZValue(10)
            item.setAcceptedMouseButtons(Qt.NoButton)
            self._photo_overlay.append(item)

    # -- cursor read-out -----------------------------------------------------------
    def _idle_cursor_text(self) -> str:
        return "cursor: x = –, y = – (plate mm)"

    def _show_cursor(self, u: float, v: float) -> None:
        extra = self.cursor_text(u, v) if self.cursor_text else ""
        self.cursor_label.setText(f"cursor: x = {u:7.3f} mm, y = {v:7.3f} mm on the plate" + (f"   {extra}" if extra else ""))

    def _on_photo_hover(self, x: float, y: float) -> None:
        if self.h is not None:
            self._show_cursor(*self.photo_to_plate(x, y))
