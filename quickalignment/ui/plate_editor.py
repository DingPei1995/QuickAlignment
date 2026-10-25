"""Sample plate editor: place samples on the plate by dragging rectangles.

* drag on an empty part of the plate  -> draw a new sample
* drag a sample                        -> move it
* drag a sample edge / corner          -> resize it
* mouse wheel                          -> zoom, middle button drag -> pan,
                                          right click -> whole plate again
* Delete key                           -> remove selected samples / devices

A substrate is a sample carrying devices: select it, press "Add device", then
choose two reference edges and the distances from them (device table), or
drag the device marker.

Positions and sizes can also be typed in the tables; all views stay in sync.
"""

from __future__ import annotations

import math

from ._qt import QtCore, QtGui, QtWidgets, Signal
from ..geometry import X_EDGES, Y_EDGES, Device, PlateGeometry, Sample, SampleLayout

Qt = QtCore.Qt

COLOR_PLATE = QtGui.QColor("#c9c9c9")
COLOR_RISER = QtGui.QColor("#e6e6e6")
COLOR_SAMPLE = QtGui.QColor(255, 140, 0, 150)
COLOR_SAMPLE_BAD = QtGui.QColor(220, 40, 40, 150)
COLOR_BEAM = QtGui.QColor("#d62728")
COLOR_DEVICE = QtGui.QColor("#1f4fd6")

COLOR_BLOCK = QtGui.QColor("#d4d4d4")
COLOR_PAD = QtGui.QColor("#e8c400")
COLOR_SCREW = QtGui.QColor("#4a3c36")

# x / y: plate coordinates (mm, relative to the plate, not motor positions):
# origin = centre of the 18 x 15.5 mm back plate, x right, y up, front view
# (sample side) with the tab up
COLUMNS = ["Name", "Type", "x (mm)", "y (mm)", "L (mm)", "W (mm)", "H (mm)", "Status"]
FIELDS = [None, None, "u", "v", "length", "width", "height", None]
DEV_COLUMNS = ["Device", "Substrate", "X ref", "dx (mm)", "Y ref", "dy (mm)", "x (mm)", "y (mm)", "Status"]
DEV_EDITABLE = {0, 3, 5, 6, 7}
MIN_SIZE = 0.1  # mm
SNAP_STEP = 0.1  # mm; mouse drawing / moving / resizing is rounded to this grid (typed values are not)
SI_WAFER_THICKNESS = 0.525  # mm, standard 100 mm (4") Si wafer, the usual device substrate


def cosmetic_pen(color, width=1.0, style=Qt.SolidLine) -> QtGui.QPen:
    pen = QtGui.QPen(QtGui.QColor(color), width, style)
    pen.setCosmetic(True)
    return pen


def snap(value: float, step: float) -> float:
    return round(value / step) * step if step > 0 else value


class SampleItem(QtWidgets.QGraphicsRectItem):
    """Movable, resizable rectangle bound to a Sample.

    Scene coordinates are plate mm with y flipped: scene (x, y) = (u, -v).
    The item position is the sample centre.
    """

    HANDLE_PX = 6

    def __init__(self, sample: Sample, editor: PlateEditor):
        super().__init__()
        self.sample = sample
        self.editor = editor
        self._syncing = False
        self._resize_edges: set[str] = set()
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self.label = QtWidgets.QGraphicsSimpleTextItem(self)
        self.label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.sync_from_sample()

    # -- model <-> item ------------------------------------------------------
    def sync_from_sample(self, ok: bool = True) -> None:
        s = self.sample
        self._syncing = True
        self.setPos(s.u, -s.v)
        self.setRect(-s.length / 2, -s.width / 2, s.length, s.width)
        self._syncing = False
        self.label.setText(s.name)
        self.label.setPos(-s.length / 2, -s.width / 2)
        self.setBrush(QtGui.QBrush(COLOR_SAMPLE if ok else COLOR_SAMPLE_BAD))
        self.setPen(cosmetic_pen("black", 1.2))

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and not self._syncing:
            step = self.editor.snap_step()
            return QtCore.QPointF(snap(value.x(), step), snap(value.y(), step))
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged and not self._syncing:
            self.sample.u = self.pos().x()
            self.sample.v = -self.pos().y()
            self.editor.sample_changed(self.sample)
        return super().itemChange(change, value)

    # -- resize handling -----------------------------------------------------
    def _edges_at(self, pos: QtCore.QPointF) -> set[str]:
        views = self.scene().views() if self.scene() else []
        scale = views[0].transform().m11() if views else 1.0
        tol = self.HANDLE_PX / max(scale, 1e-6)
        r = self.rect()
        edges = set()
        if abs(pos.x() - r.left()) < tol:
            edges.add("l")
        elif abs(pos.x() - r.right()) < tol:
            edges.add("r")
        if abs(pos.y() - r.top()) < tol:
            edges.add("t")
        elif abs(pos.y() - r.bottom()) < tol:
            edges.add("b")
        return edges

    @staticmethod
    def _cursor_for(edges: set[str]):
        if edges in ({"l", "t"}, {"r", "b"}):
            return Qt.SizeFDiagCursor
        if edges in ({"r", "t"}, {"l", "b"}):
            return Qt.SizeBDiagCursor
        if edges & {"l", "r"}:
            return Qt.SizeHorCursor
        if edges & {"t", "b"}:
            return Qt.SizeVerCursor
        return Qt.SizeAllCursor

    def hoverMoveEvent(self, event):
        self.setCursor(self._cursor_for(self._edges_at(event.pos())))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        edges = self._edges_at(event.pos()) if event.button() == Qt.LeftButton else set()
        if edges:
            self._resize_edges = edges
            self.scene().clearSelection()
            self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._resize_edges:
            super().mouseMoveEvent(event)
            return
        step = self.editor.snap_step()
        x, y = snap(event.scenePos().x(), step), snap(event.scenePos().y(), step)
        s = self.sample
        left, right = s.u - s.length / 2, s.u + s.length / 2
        top, bottom = -s.v - s.width / 2, -s.v + s.width / 2
        if "l" in self._resize_edges:
            left = min(x, right - MIN_SIZE)
        if "r" in self._resize_edges:
            right = max(x, left + MIN_SIZE)
        if "t" in self._resize_edges:
            top = min(y, bottom - MIN_SIZE)
        if "b" in self._resize_edges:
            bottom = max(y, top + MIN_SIZE)
        s.u, s.v = (left + right) / 2, -(top + bottom) / 2
        s.length, s.width = right - left, bottom - top
        self.editor.sample_changed(s)

    def mouseReleaseEvent(self, event):
        if self._resize_edges:
            self._resize_edges = set()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class DeviceItem(QtWidgets.QGraphicsEllipseItem):
    """Fixed-size draggable marker for a device; a scaled outline shows its size."""

    MARKER_PX = 7

    def __init__(self, sample: Sample, device: Device, editor: PlateEditor):
        r = self.MARKER_PX
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.sample, self.device, self.editor = sample, device, editor
        self._syncing = False
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
            | QtWidgets.QGraphicsItem.ItemIgnoresTransformations
        )
        self.setZValue(15)
        self.setCursor(Qt.SizeAllCursor)
        for x0, y0, x1, y1 in ((-r - 3, 0, r + 3, 0), (0, -r - 3, 0, r + 3)):
            QtWidgets.QGraphicsLineItem(x0, y0, x1, y1, self).setPen(cosmetic_pen(COLOR_DEVICE, 1))
        self.label = QtWidgets.QGraphicsSimpleTextItem(self)
        self.label.setBrush(QtGui.QBrush(COLOR_DEVICE))
        self.label.setPos(r + 2, -r - 12)
        self.outline = QtWidgets.QGraphicsRectItem()
        self.outline.setPen(cosmetic_pen(COLOR_DEVICE, 1))
        self.outline.setBrush(QtGui.QBrush(QtGui.QColor(31, 79, 214, 70)))
        self.outline.setZValue(14)
        self.outline.setAcceptedMouseButtons(Qt.NoButton)

    def sync_from_device(self, ok: bool = True) -> None:
        u, v = self.device.position(self.sample)
        self._syncing = True
        self.setPos(u, -v)
        self._syncing = False
        d = self.device
        self.outline.setRect(u - d.length / 2, -v - d.width / 2, d.length, d.width)
        self.label.setText(d.name)
        color = COLOR_DEVICE if ok else COLOR_SAMPLE_BAD
        self.setPen(cosmetic_pen(color, 2))
        self.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 180)))

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and not self._syncing:
            step = self.editor.snap_step()
            return QtCore.QPointF(snap(value.x(), step), snap(value.y(), step))
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged and not self._syncing:
            self.device.set_position(self.sample, self.pos().x(), -self.pos().y())
            self.editor.device_changed(self.sample, self.device)
        return super().itemChange(change, value)


class PlateView(QtWidgets.QGraphicsView):
    """Graphics view of the plate; drawing on empty space creates a sample."""

    sampleDrawn = Signal(float, float, float, float)  # u0, v0, u1, v1
    cursorMoved = Signal(float, float)

    def __init__(self, scene: QtWidgets.QGraphicsScene, editor: PlateEditor):
        super().__init__(scene)
        self.editor = editor
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setMinimumSize(420, 420)
        self._draw_start: QtCore.QPointF | None = None
        self._draw_item: QtWidgets.QGraphicsRectItem | None = None
        self._pan_start: QtCore.QPoint | None = None
        self._fitted = False
        self._zoomed = False

    def fit(self) -> None:
        self._zoomed = False
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self.fit()
            self._fitted = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._zoomed:  # the scroll bars appearing on zoom resize the view: keep the zoom
            self.fit()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoomed = True
        self.scale(factor, factor)

    def _snapped_scene_pos(self, event) -> QtCore.QPointF:
        p = self.mapToScene(event.pos())
        step = self.editor.snap_step()
        return QtCore.QPointF(snap(p.x(), step), snap(p.y(), step))

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.RightButton:
            self.fit()
            return
        on_sample = any(
            isinstance(it, (SampleItem, DeviceItem)) or isinstance(it.parentItem(), SampleItem) for it in self.items(event.pos())
        )
        if event.button() == Qt.LeftButton and not on_sample:
            self.scene().clearSelection()
            self._draw_start = self._snapped_scene_pos(event)
            self._draw_item = self.scene().addRect(
                QtCore.QRectF(self._draw_start, self._draw_start),
                cosmetic_pen("black", 1, Qt.DashLine),
                QtGui.QBrush(COLOR_SAMPLE),
            )
            self._draw_item.setZValue(20)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        p = self.mapToScene(event.pos())
        self.cursorMoved.emit(p.x(), -p.y())
        if self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        if self._draw_item is not None:
            self._draw_item.setRect(QtCore.QRectF(self._draw_start, self._snapped_scene_pos(event)).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_start is not None and event.button() == Qt.MiddleButton:
            self._pan_start = None
            self.unsetCursor()
            return
        if self._draw_item is not None and event.button() == Qt.LeftButton:
            r = self._draw_item.rect()
            self.scene().removeItem(self._draw_item)
            self._draw_item = None
            if r.width() >= MIN_SIZE and r.height() >= MIN_SIZE:
                self.sampleDrawn.emit(r.left(), -r.bottom(), r.right(), -r.top())
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.editor.delete_selected()
            return
        super().keyPressEvent(event)




def draw_plate_items(scene: QtWidgets.QGraphicsScene, plate: PlateGeometry, grid: bool = True) -> None:
    """Plate outline, riser / sample area, contact block, pads and screws (scene = (u, -v))."""

    def rect(r, pen, brush):
        u0, v0, u1, v1 = r
        return scene.addRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0), pen, QtGui.QBrush(brush))

    outline = QtGui.QPolygonF([QtCore.QPointF(u, -v) for u, v in plate.outline()])
    scene.addPolygon(outline, cosmetic_pen("black", 1.5), QtGui.QBrush(COLOR_PLATE))
    area = plate.riser_bounds()
    rect(area, cosmetic_pen("black", 1.2), COLOR_RISER)
    if plate.contact_block:
        rect(plate.contact_block, cosmetic_pen("black", 1.2), COLOR_BLOCK)
        for pad in plate.contact_pads:
            rect(pad, cosmetic_pen("#8a7400", 1), COLOR_PAD)
        r = plate.screw_diameter / 2
        for u, v in plate.screws:
            scene.addEllipse(u - r, -v - r, 2 * r, 2 * r, cosmetic_pen("black", 1), QtGui.QBrush(COLOR_SCREW))
            scene.addLine(u - 0.15, -v + r * 0.8, u + 0.15, -v - r * 0.8, cosmetic_pen("#cccccc", 1.5))
    if grid:
        u0, v0, u1, v1 = area
        for i in range(int(u0), int(u1) + 1):
            pen = cosmetic_pen("#b0b0b0" if i % 5 else "#808080", 0.6, Qt.DotLine)
            scene.addLine(i, -v1, i, -v0, pen)
        for j in range(int(-v1), int(-v0) + 1):
            pen = cosmetic_pen("#b0b0b0" if j % 5 else "#808080", 0.6, Qt.DotLine)
            scene.addLine(u0, j, u1, j, pen)


def plate_pixmap(plate: PlateGeometry, size: int = 220) -> QtGui.QPixmap:
    """Small preview of a plate, e.g. for the plate choice dialog."""
    scene = QtWidgets.QGraphicsScene()
    draw_plate_items(scene, plate, grid=False)
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtGui.QColor("white"))
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    src = scene.itemsBoundingRect().adjusted(-1, -1, 1, 1)
    scene.render(painter, QtCore.QRectF(4, 4, size - 8, size - 8), src, Qt.KeepAspectRatio)
    painter.end()
    return pix


def make_table(columns: list[str]) -> QtWidgets.QTableWidget:
    table = QtWidgets.QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    # the spare width goes to the name, not to the status ("ok" or the warnings)
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
    table.horizontalHeaderItem(len(columns) - 1).setToolTip(
        "Check of the placement: “ok”, or what is wrong (outside the sample area / substrate, overlapping)")
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    return table


class PlateEditor(QtWidgets.QWidget):
    """Plate view + sample / device tables + controls."""

    layoutChanged = Signal()
    samplesPlaced = Signal()  # the user confirmed the samples are marked on the plate

    def __init__(self, layout: SampleLayout | None = None, parent=None):
        super().__init__(parent)
        self.layout_model = layout or SampleLayout()
        self.items: dict[int, SampleItem] = {}
        self.device_items: dict[int, DeviceItem] = {}
        self._device_rows: list[tuple[Sample, Device]] = []
        self._updating_table = False

        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = PlateView(self.scene, self)
        self.view.sampleDrawn.connect(self._on_sample_drawn)
        self.view.cursorMoved.connect(self._on_cursor_moved)
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self._draw_plate()

        self.table = make_table(COLUMNS)
        self.table.itemChanged.connect(self._on_table_edit)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.dev_table = make_table(DEV_COLUMNS)
        self.dev_table.itemChanged.connect(self._on_dev_table_edit)
        self.dev_table.itemSelectionChanged.connect(self._on_dev_table_selection)

        self.height_box = QtWidgets.QDoubleSpinBox()
        self.height_box.setRange(0.0, 20.0)
        self.height_box.setSingleStep(0.1)
        self.height_box.setDecimals(3)
        self.height_box.setValue(SI_WAFER_THICKNESS)
        self.height_box.setSuffix(" mm")
        self.height_box.setToolTip("Height H given to newly drawn samples. Default: Si wafer substrate, "
                                   f"{SI_WAFER_THICKNESS * 1000:.0f} µm (standard 100 mm wafer).")
        self.height_box.setMaximumWidth(self.height_box.sizeHint().width())

        add_btn = QtWidgets.QPushButton("Add sample")
        add_btn.clicked.connect(self.add_default_sample)
        photo_btn = QtWidgets.QPushButton("From photo…")
        photo_btn.setToolTip("Find the samples on a photo of the plate taken from above (sample side)")
        photo_btn.clicked.connect(self.samples_from_photo)
        dev_btn = QtWidgets.QPushButton("Add device")
        dev_btn.setToolTip("Add a device to the selected sample (it becomes a substrate)")
        dev_btn.clicked.connect(self.add_device_to_selected)
        del_btn = QtWidgets.QPushButton("Delete selected")
        del_btn.clicked.connect(self.delete_selected)
        done_btn = QtWidgets.QPushButton("Samples placed → Stage")
        done_btn.setToolTip("When all samples are marked on the plate: go to the Stage && Optics tab,\n"
                            "which then lists where each sample is at the initial rotation.")
        done_btn.setStyleSheet("font-weight: bold;")
        done_btn.clicked.connect(self.confirm_samples_placed)

        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)
        self.cursor_label = QtWidgets.QLabel("cursor: x = –, y = –")

        form = QtWidgets.QHBoxLayout()
        form.addWidget(QtWidgets.QLabel("Default H"))
        form.addWidget(self.height_box)
        si = QtWidgets.QLabel("(Si wafer substrate)")
        si.setStyleSheet("color: #555;")
        form.addWidget(si)
        form.addStretch(1)
        buttons = QtWidgets.QHBoxLayout()
        for b in (add_btn, photo_btn, dev_btn, del_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(done_btn)

        help_text = QtWidgets.QLabel(
            "Sample plate, front view (sample side), tab up. Coordinates x, y are in mm on the plate "
            "(origin = centre of the back plate, red cross), not motor positions.\n"
            "Drag on empty plate to draw a sample; drag a sample to move it, its edges to resize "
            "(mouse positions are rounded to 0.1 mm), or find them on a photo ('From photo…'). "
            "Select a sample and press 'Add device' to mark a device on a substrate. "
            "Wheel = zoom, middle drag = pan, right click = whole plate, Del = delete."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #555;")

        right = QtWidgets.QVBoxLayout()
        right.addWidget(help_text)
        right.addLayout(form)
        right.addLayout(buttons)
        right.addWidget(QtWidgets.QLabel("<b>Samples / substrates</b>"))
        right.addWidget(self.table, 3)
        right.addWidget(QtWidgets.QLabel("<b>Devices</b> (dx, dy: distances from two substrate edges to the device centre)"))
        right.addWidget(self.dev_table, 2)
        right.addWidget(self.info)
        right.addWidget(self.cursor_label)
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.addWidget(splitter)

        self.set_layout(self.layout_model)

    # -- plate drawing -------------------------------------------------------
    def _draw_plate(self) -> None:
        plate = self.layout_model.plate
        # clear() can emit selectionChanged while the item maps are stale
        self._updating_table = True
        self.items.clear()
        self.device_items.clear()
        self.scene.clear()
        self._updating_table = False
        draw_plate_items(self.scene, plate)

        # tick labels every 5 mm and the main plate dimensions
        bottom = -plate.lowest_v()

        def text(t, x, y, color="black"):
            item = self.scene.addSimpleText(t)
            item.setBrush(QtGui.QBrush(QtGui.QColor(color)))
            item.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            item.setPos(x, y)

        for i in range(-5, 6, 5):
            text(f"{i}", i - 0.2, bottom + 0.3)
            text(f"{i}", -plate.width / 2 - 1.6, -i - 0.4)
        text("x (mm)", plate.width / 2 - 1.5, bottom + 0.3)
        text("y (mm)", -plate.width / 2 - 2.0, -plate.height / 2 - 1.3)
        dim_pen = cosmetic_pen("#1f6f8b", 1)
        w, h = plate.width / 2, plate.height / 2
        top = h + plate.neck_height + plate.tab_height
        ry = -top - 0.9
        self.scene.addLine(-w, ry, w, ry, dim_pen)
        text(f"{plate.width:g}", -0.4, ry - 1.1, "#1f6f8b")
        rx = w + 0.9
        self.scene.addLine(rx, -h, rx, h, dim_pen)
        text(f"{plate.height:g}", rx + 0.2, -0.4, "#1f6f8b")
        u0, v0, u1, v1 = plate.riser_bounds()
        text(f"sample area\n{u1 - u0:g} × {v1 - v0:g} mm", plate.tab_width / 2 + 0.6, -h - plate.neck_height - 1.5, "#1f6f8b")

        # plate centre
        beam_pen = cosmetic_pen(COLOR_BEAM, 2)
        self.scene.addLine(-0.6, 0, 0.6, 0, beam_pen).setZValue(30)
        self.scene.addLine(0, -0.6, 0, 0.6, beam_pen).setZValue(30)

        # decorations must not catch clicks meant for samples underneath
        for it in self.scene.items():
            it.setAcceptedMouseButtons(Qt.NoButton)

        margin = 2.5
        top = plate.height / 2 + plate.neck_height + plate.tab_height
        self.scene.setSceneRect(
            QtCore.QRectF(-plate.width / 2 - margin - 1.0, -top - margin - 1.5, plate.width + 2 * margin + 2.5, top + bottom + 2 * margin + 2.5)
        )

    # -- model operations ----------------------------------------------------
    def snap_step(self) -> float:
        return SNAP_STEP

    def default_height(self) -> float:
        return self.height_box.value()

    def confirm_samples_placed(self) -> bool:
        answer = QtWidgets.QMessageBox.question(
            self, "Samples placed?",
            "Have you marked the positions of all samples on the plate?\n\n"
            "Yes: go to “Stage & Optics”, which shows where each sample is at the initial rotation.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return False
        self.samplesPlaced.emit()
        return True

    def set_layout(self, layout: SampleLayout) -> None:
        self.layout_model = layout
        self._draw_plate()
        for s in layout.samples:
            self._add_item(s)
            for d in s.devices:
                self._add_device_item(s, d)
        self._rebuild_tables()
        self._refresh_status()

    def _add_item(self, sample: Sample) -> SampleItem:
        item = SampleItem(sample, self)
        self.scene.addItem(item)
        self.items[id(sample)] = item
        return item

    def _add_device_item(self, sample: Sample, device: Device) -> DeviceItem:
        item = DeviceItem(sample, device, self)
        self.scene.addItem(item.outline)
        self.scene.addItem(item)
        self.device_items[id(device)] = item
        return item

    def add_sample(self, sample: Sample) -> Sample:
        self.layout_model.samples.append(sample)
        item = self._add_item(sample)
        for d in sample.devices:
            self._add_device_item(sample, d)
        self._rebuild_tables()
        self._refresh_status()
        self.scene.clearSelection()
        item.setSelected(True)
        self.layoutChanged.emit()
        return sample

    def add_default_sample(self) -> Sample:
        return self.add_sample(Sample(self.layout_model.unique_name(), height=self.height_box.value()))

    def samples_from_photo(self) -> None:
        from .photo_dialog import PhotoImportDialog

        dialog = PhotoImportDialog(self.layout_model.plate, self.height_box.value(),
                                   [s.name for s in self.layout_model.samples], self)
        if dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec():
            self.import_samples(dialog.samples(), dialog.replace_existing())

    def import_samples(self, samples: list[Sample], replace: bool = False) -> None:
        """Add samples (e.g. found on a photo), optionally instead of the present ones; names are made unique."""
        if replace:
            self.layout_model.samples.clear()
        for s in samples:
            if not s.name or any(o.name == s.name for o in self.layout_model.samples):
                s.name = self.layout_model.unique_name()
            self.layout_model.samples.append(s)
        self.set_layout(self.layout_model)
        self.layoutChanged.emit()

    def add_device(self, sample: Sample, device: Device | None = None) -> Device:
        if device is None:
            device = Device(self.layout_model.unique_device_name(), dx=sample.length / 2, dy=sample.width / 2)
        sample.devices.append(device)
        item = self._add_device_item(sample, device)
        self._rebuild_tables()
        self._refresh_status()
        self.scene.clearSelection()
        item.setSelected(True)
        self.layoutChanged.emit()
        return device

    def add_device_to_selected(self) -> None:
        sel = self.selected_samples()
        if len(sel) != 1:
            QtWidgets.QMessageBox.information(self, "Add device", "Select exactly one sample (substrate) first.")
            return
        self.add_device(sel[0])

    def _on_sample_drawn(self, u0, v0, u1, v1) -> None:
        self.add_sample(
            Sample(
                self.layout_model.unique_name(),
                u=(u0 + u1) / 2,
                v=(v0 + v1) / 2,
                length=u1 - u0,
                width=v1 - v0,
                height=self.height_box.value(),
            )
        )

    def selected_samples(self) -> list[Sample]:
        return [it.sample for it in self.items.values() if it.isSelected()]

    def selected_devices(self) -> list[tuple[Sample, Device]]:
        return [(it.sample, it.device) for it in self.device_items.values() if it.isSelected()]

    def _remove_device_item(self, device: Device) -> None:
        item = self.device_items.pop(id(device))
        self.scene.removeItem(item.outline)
        self.scene.removeItem(item)

    def delete_selected(self) -> None:
        samples = self.selected_samples()
        devices = [(s, d) for s, d in self.selected_devices() if s not in samples]
        # update the model first: removeItem() emits selectionChanged
        self._updating_table = True
        for s, d in devices:
            s.devices.remove(d)
            self._remove_device_item(d)
        for s in samples:
            self.layout_model.samples.remove(s)
            for d in s.devices:
                self._remove_device_item(d)
            self.scene.removeItem(self.items.pop(id(s)))
        self._updating_table = False
        if samples or devices:
            self._rebuild_tables()
            self._refresh_status()
            self.layoutChanged.emit()

    def sample_changed(self, sample: Sample) -> None:
        """Called by a SampleItem while it is moved or resized (devices follow their edges)."""
        self._update_row(self.layout_model.samples.index(sample))
        for row, (s, _) in enumerate(self._device_rows):
            if s is sample:
                self._update_dev_row(row)
        self._refresh_status()
        self.layoutChanged.emit()

    def device_changed(self, sample: Sample, device: Device) -> None:
        """Called by a DeviceItem while it is dragged."""
        for row, (_, d) in enumerate(self._device_rows):
            if d is device:
                self._update_dev_row(row)
        self._refresh_status()
        self.layoutChanged.emit()

    # -- sample table ------------------------------------------------------------
    def _rebuild_tables(self) -> None:
        self._updating_table = True
        n = len(self.layout_model.samples)
        self.table.setRowCount(n)
        for row in range(n):
            for col in range(len(COLUMNS)):
                if self.table.item(row, col) is None:
                    self.table.setItem(row, col, QtWidgets.QTableWidgetItem())
            for col in (1, 7):
                self.table.item(row, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        self._device_rows = [(s, d) for s in self.layout_model.samples for d in s.devices]
        self.dev_table.setRowCount(len(self._device_rows))
        for row, (s, d) in enumerate(self._device_rows):
            for col in range(len(DEV_COLUMNS)):
                if col in (2, 4):
                    combo = QtWidgets.QComboBox()
                    combo.addItems(X_EDGES if col == 2 else Y_EDGES)
                    combo.currentTextChanged.connect(lambda text, r=row, c=col: self._on_edge_changed(r, c, text))
                    self.dev_table.setCellWidget(row, col, combo)
                    continue
                if self.dev_table.item(row, col) is None:
                    self.dev_table.setItem(row, col, QtWidgets.QTableWidgetItem())
                if col not in DEV_EDITABLE:
                    self.dev_table.item(row, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self._updating_table = False
        for row in range(n):
            self._update_row(row)
        for row in range(len(self._device_rows)):
            self._update_dev_row(row)

    def _update_row(self, row: int) -> None:
        s = self.layout_model.samples[row]
        self._updating_table = True
        self.table.item(row, 0).setText(s.name)
        self.table.item(row, 1).setText(f"substrate ({len(s.devices)})" if s.devices else "sample")
        values = {2: s.u, 3: s.v, 4: s.length, 5: s.width, 6: s.height}
        for col, value in values.items():
            self.table.item(row, col).setText(f"{value:.3f}")
        self._updating_table = False

    def _on_table_edit(self, cell: QtWidgets.QTableWidgetItem) -> None:
        if self._updating_table:
            return
        row, col = cell.row(), cell.column()
        s = self.layout_model.samples[row]
        text = cell.text().strip()
        if col == 0:
            if text:
                s.name = text
        elif FIELDS[col]:
            try:
                value = float(text)
            except ValueError:
                value = None
            if value is not None and not math.isfinite(value):
                value = None
            attr = FIELDS[col]
            if value is not None and (attr in ("u", "v") or value >= (0 if attr == "height" else MIN_SIZE)):
                setattr(s, attr, value)
        self.sample_changed(s)

    # -- device table ------------------------------------------------------------
    def _update_dev_row(self, row: int) -> None:
        s, d = self._device_rows[row]
        u, v = d.position(s)
        self._updating_table = True
        values = {0: d.name, 1: s.name, 3: f"{d.dx:.3f}", 5: f"{d.dy:.3f}", 6: f"{u:.3f}", 7: f"{v:.3f}"}
        for col, text in values.items():
            self.dev_table.item(row, col).setText(text)
        for col, edge in ((2, d.x_edge), (4, d.y_edge)):
            combo = self.dev_table.cellWidget(row, col)
            combo.blockSignals(True)
            combo.setCurrentText(edge)
            combo.blockSignals(False)
        self._updating_table = False

    def _on_edge_changed(self, row: int, col: int, text: str) -> None:
        if self._updating_table:
            return
        s, d = self._device_rows[row]
        u, v = d.position(s)
        # keep the device where it is; re-express it from the new edge
        if col == 2:
            d.x_edge = text
        else:
            d.y_edge = text
        d.set_position(s, u, v)
        self._update_dev_row(row)
        self._refresh_status()
        self.layoutChanged.emit()

    def _on_dev_table_edit(self, cell: QtWidgets.QTableWidgetItem) -> None:
        if self._updating_table:
            return
        row, col = cell.row(), cell.column()
        s, d = self._device_rows[row]
        text = cell.text().strip()
        if col == 0:
            if text:
                d.name = text
        else:
            try:
                value = float(text)
            except ValueError:
                value = None
            if value is not None and not math.isfinite(value):
                value = None
            if value is not None:
                if col == 3:
                    d.dx = value
                elif col == 5:
                    d.dy = value
                else:
                    u, v = d.position(s)
                    d.set_position(s, value if col == 6 else u, value if col == 7 else v)
        self.device_changed(s, d)

    # -- status ----------------------------------------------------------------------
    def _refresh_status(self) -> None:
        self._updating_table = True
        for row, s in enumerate(self.layout_model.samples):
            warnings = self.layout_model.warnings(s)
            self.items[id(s)].sync_from_sample(ok=not warnings)
            status = self.table.item(row, len(COLUMNS) - 1)
            status.setText("; ".join(warnings) or "ok")
            status.setToolTip(status.text())
            status.setForeground(QtGui.QBrush(QtGui.QColor("#c00000" if warnings else "#207020")))
        for row, (s, d) in enumerate(self._device_rows):
            warnings = self.layout_model.device_warnings(s, d)
            self.device_items[id(d)].sync_from_device(ok=not warnings)
            status = self.dev_table.item(row, len(DEV_COLUMNS) - 1)
            status.setText("; ".join(warnings) or "ok")
            status.setToolTip(status.text())
            status.setForeground(QtGui.QBrush(QtGui.QColor("#c00000" if warnings else "#207020")))
        self._updating_table = False
        self._update_info()

    def _update_info(self) -> None:
        devs = self.selected_devices()
        sel = self.selected_samples()
        if len(devs) == 1 and not sel:
            s, d = devs[0]
            u, v = d.position(s)
            self.info.setText(
                f"<b>{s.name}/{d.name}</b>: {d.dx:.3f} mm from the {d.x_edge} edge, {d.dy:.3f} mm from the "
                f"{d.y_edge} edge of {s.name}<br>→ x = {u:.3f}, y = {v:.3f} mm on the plate"
            )
            return
        if len(sel) != 1:
            self.info.setText(f"{len(self.layout_model.samples)} sample(s), {len(self._device_rows)} device(s).")
            return
        s = sel[0]
        u0, v0, u1, v1 = s.bounds()
        self.info.setText(
            f"<b>{s.name}</b> ({s.kind}): x ∈ [{u0:.2f}, {u1:.2f}], y ∈ [{v0:.2f}, {v1:.2f}] mm on the plate, "
            f"height {s.height:.3f} mm above the plate surface"
        )

    # -- selection sync ----------------------------------------------------------
    @staticmethod
    def _select_rows(table: QtWidgets.QTableWidget, rows) -> None:
        table.clearSelection()
        mode = table.selectionMode()
        table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for row in rows:
            table.selectRow(row)
        table.setSelectionMode(mode)

    def _on_scene_selection(self) -> None:
        if self._updating_table:
            return
        self._updating_table = True
        self._select_rows(self.table, [r for r, s in enumerate(self.layout_model.samples) if self.items[id(s)].isSelected()])
        self._select_rows(self.dev_table, [r for r, (_, d) in enumerate(self._device_rows) if self.device_items[id(d)].isSelected()])
        self._updating_table = False
        self._update_info()

    def _on_table_selection(self) -> None:
        if self._updating_table:
            return
        rows = {i.row() for i in self.table.selectedIndexes()}
        self._updating_table = True
        self.dev_table.clearSelection()
        for it in self.device_items.values():
            it.setSelected(False)
        for row, s in enumerate(self.layout_model.samples):
            self.items[id(s)].setSelected(row in rows)
        self._updating_table = False
        self._update_info()

    def _on_dev_table_selection(self) -> None:
        if self._updating_table:
            return
        rows = {i.row() for i in self.dev_table.selectedIndexes()}
        self._updating_table = True
        self.table.clearSelection()
        for it in self.items.values():
            it.setSelected(False)
        for row, (_, d) in enumerate(self._device_rows):
            self.device_items[id(d)].setSelected(row in rows)
        self._updating_table = False
        self._update_info()

    def _on_cursor_moved(self, u: float, v: float) -> None:
        self.cursor_label.setText(f"cursor: x = {u:.2f} mm, y = {v:.2f} mm")
