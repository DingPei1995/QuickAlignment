"""Sample plate editor: place samples on the plate by dragging rectangles.

* drag on an empty part of the plate  -> draw a new sample
* drag a sample                        -> move it
* drag a sample edge / corner          -> resize it
* mouse wheel                          -> zoom, middle button drag -> pan
* Delete key                           -> remove selected samples

Positions and sizes can also be typed in the table; both views stay in sync.
"""

from __future__ import annotations

import sys

from ._qt import QtCore, QtGui, QtWidgets, Signal, exec_app
from ..geometry import PlateGeometry, Sample, SampleLayout

Qt = QtCore.Qt

COLOR_PLATE = QtGui.QColor("#c9c9c9")
COLOR_RISER = QtGui.QColor("#e6e6e6")
COLOR_SAMPLE = QtGui.QColor(255, 140, 0, 150)
COLOR_SAMPLE_BAD = QtGui.QColor(220, 40, 40, 150)
COLOR_BEAM = QtGui.QColor("#d62728")

COLUMNS = ["Name", "u (mm)", "v (mm)", "L (mm)", "W (mm)", "H (mm)", "Status"]
FIELDS = [None, "u", "v", "length", "width", "height", None]
MIN_SIZE = 0.1  # mm


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

    def fit(self) -> None:
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self.fit()
            self._fitted = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
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
        on_sample = any(isinstance(it, SampleItem) or isinstance(it.parentItem(), SampleItem) for it in self.items(event.pos()))
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


class PlateEditor(QtWidgets.QWidget):
    """Plate view + sample table + controls."""

    layoutChanged = Signal()

    def __init__(self, layout: SampleLayout | None = None, parent=None):
        super().__init__(parent)
        self.layout_model = layout or SampleLayout()
        self.items: dict[int, SampleItem] = {}
        self._updating_table = False

        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = PlateView(self.scene, self)
        self.view.sampleDrawn.connect(self._on_sample_drawn)
        self.view.cursorMoved.connect(self._on_cursor_moved)
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self._draw_plate()

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._on_table_edit)
        self.table.itemSelectionChanged.connect(self._on_table_selection)

        self.snap_box = QtWidgets.QDoubleSpinBox()
        self.snap_box.setRange(0.0, 2.0)
        self.snap_box.setSingleStep(0.05)
        self.snap_box.setDecimals(2)
        self.snap_box.setValue(0.1)
        self.snap_box.setSuffix(" mm")
        self.snap_box.setToolTip("Grid snap for drawing / moving (0 = off)")

        self.height_box = QtWidgets.QDoubleSpinBox()
        self.height_box.setRange(0.0, 20.0)
        self.height_box.setSingleStep(0.1)
        self.height_box.setDecimals(3)
        self.height_box.setValue(0.5)
        self.height_box.setSuffix(" mm")
        self.height_box.setToolTip("Height H given to newly drawn samples")

        add_btn = QtWidgets.QPushButton("Add sample")
        add_btn.clicked.connect(self.add_default_sample)
        del_btn = QtWidgets.QPushButton("Delete selected")
        del_btn.clicked.connect(self.delete_selected)
        fit_btn = QtWidgets.QPushButton("Fit view")
        fit_btn.clicked.connect(self.view.fit)

        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)
        self.cursor_label = QtWidgets.QLabel("u = –, v = –")

        form = QtWidgets.QFormLayout()
        form.addRow("Snap", self.snap_box)
        form.addRow("Default H", self.height_box)
        buttons = QtWidgets.QHBoxLayout()
        for b in (add_btn, del_btn, fit_btn):
            buttons.addWidget(b)

        help_text = QtWidgets.QLabel(
            "View from the analyzer, SRn = 120 (tab up). Origin = plate centre (red cross), "
            "+u = right (+ST, PIX), +v = up (+SZ, PIY).\n"
            "Drag on empty plate to draw a sample; drag a sample to move it, its edges to resize. "
            "Wheel = zoom, middle drag = pan, Del = delete."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #555;")

        right = QtWidgets.QVBoxLayout()
        right.addWidget(help_text)
        right.addLayout(form)
        right.addLayout(buttons)
        right.addWidget(self.table, 1)
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
        # clear() can emit selectionChanged while self.items is stale
        self._updating_table = True
        self.items.clear()
        self.scene.clear()
        self._updating_table = False
        outline = QtGui.QPolygonF([QtCore.QPointF(u, -v) for u, v in plate.outline()])
        self.scene.addPolygon(outline, cosmetic_pen("black", 1.5), QtGui.QBrush(COLOR_PLATE))
        u0, v0, u1, v1 = plate.riser_bounds()
        self.scene.addRect(QtCore.QRectF(u0, -v1, u1 - u0, v1 - v0), cosmetic_pen("black", 1.2), QtGui.QBrush(COLOR_RISER))

        # 1 mm grid on the riser, 5 mm lines darker
        for i in range(int(u0), int(u1) + 1):
            pen = cosmetic_pen("#b0b0b0" if i % 5 else "#808080", 0.6, Qt.DotLine)
            self.scene.addLine(i, -v1, i, -v0, pen)
        for j in range(int(-v1), int(-v0) + 1):
            pen = cosmetic_pen("#b0b0b0" if j % 5 else "#808080", 0.6, Qt.DotLine)
            self.scene.addLine(u0, j, u1, j, pen)

        # axis tick labels every 5 mm
        bottom = plate.height / 2
        for i in range(-5, 6, 5):
            t = self.scene.addSimpleText(f"{i}")
            t.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            t.setPos(i - 0.2, bottom + 0.3)
        for j in range(-5, 6, 5):
            t = self.scene.addSimpleText(f"{j}")
            t.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            t.setPos(-plate.width / 2 - 1.3, -j - 0.4)

        # nominal beam spot / plate centre
        beam_pen = cosmetic_pen(COLOR_BEAM, 2)
        self.scene.addLine(-0.6, 0, 0.6, 0, beam_pen).setZValue(30)
        self.scene.addLine(0, -0.6, 0, 0.6, beam_pen).setZValue(30)

        # axis arrows
        ax_pen = cosmetic_pen("#2ca02c", 1.5)
        ox, oy = -plate.width / 2 - 1.5, plate.height / 2 + 3.5
        self.scene.addLine(ox, oy, ox + 2.5, oy, ax_pen)
        self.scene.addLine(ox, oy, ox, oy - 2.5, ax_pen)
        for text, pos in (("+u (ST, PIX)", (ox + 2.7, oy - 0.4)), ("+v (Z, PIY)", (ox + 0.3, oy - 2.8))):
            t = self.scene.addSimpleText(text)
            t.setBrush(QtGui.QBrush(QtGui.QColor("#2ca02c")))
            t.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            t.setPos(*pos)

        # decorations must not catch clicks meant for samples underneath
        for it in self.scene.items():
            it.setAcceptedMouseButtons(Qt.NoButton)

        margin = 2.5
        top = plate.height / 2 + plate.neck_height + plate.tab_height
        self.scene.setSceneRect(
            QtCore.QRectF(-plate.width / 2 - margin, -top - margin, plate.width + 2 * margin, top + bottom + 2 * margin + 2.5)
        )

    # -- model operations ----------------------------------------------------
    def snap_step(self) -> float:
        return self.snap_box.value()

    def set_layout(self, layout: SampleLayout) -> None:
        self.layout_model = layout
        self._draw_plate()
        for s in layout.samples:
            self._add_item(s)
        self._rebuild_table()
        self._refresh_status()

    def _add_item(self, sample: Sample) -> SampleItem:
        item = SampleItem(sample, self)
        self.scene.addItem(item)
        self.items[id(sample)] = item
        return item

    def add_sample(self, sample: Sample) -> Sample:
        self.layout_model.samples.append(sample)
        item = self._add_item(sample)
        self._rebuild_table()
        self._refresh_status()
        self.scene.clearSelection()
        item.setSelected(True)
        self.layoutChanged.emit()
        return sample

    def add_default_sample(self) -> Sample:
        return self.add_sample(Sample(self.layout_model.unique_name(), height=self.height_box.value()))

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

    def delete_selected(self) -> None:
        selected = [it.sample for it in self.items.values() if it.isSelected()]
        for s in selected:
            # update the model first: removeItem() emits selectionChanged
            self.layout_model.samples.remove(s)
            self.scene.removeItem(self.items.pop(id(s)))
        if selected:
            self._rebuild_table()
            self._refresh_status()
            self.layoutChanged.emit()

    def sample_changed(self, sample: Sample) -> None:
        """Called by a SampleItem while it is moved or resized."""
        self._update_row(self.layout_model.samples.index(sample))
        self._refresh_status()
        self.layoutChanged.emit()

    # -- table -----------------------------------------------------------------
    def _rebuild_table(self) -> None:
        self._updating_table = True
        self.table.setRowCount(len(self.layout_model.samples))
        for row in range(len(self.layout_model.samples)):
            for col in range(len(COLUMNS)):
                if self.table.item(row, col) is None:
                    self.table.setItem(row, col, QtWidgets.QTableWidgetItem())
            self.table.item(row, len(COLUMNS) - 1).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self._updating_table = False
        for row in range(len(self.layout_model.samples)):
            self._update_row(row)

    def _update_row(self, row: int) -> None:
        s = self.layout_model.samples[row]
        self._updating_table = True
        self.table.item(row, 0).setText(s.name)
        for col, attr in enumerate(FIELDS):
            if attr:
                self.table.item(row, col).setText(f"{getattr(s, attr):.3f}")
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
            if value is not None and (FIELDS[col] in ("u", "v") or value >= (0 if FIELDS[col] == "height" else MIN_SIZE)):
                setattr(s, FIELDS[col], value)
        self._update_row(row)
        self._refresh_status()
        self.layoutChanged.emit()

    def _refresh_status(self) -> None:
        self._updating_table = True
        for row, s in enumerate(self.layout_model.samples):
            warnings = self.layout_model.warnings(s)
            self.items[id(s)].sync_from_sample(ok=not warnings)
            status = self.table.item(row, len(COLUMNS) - 1)
            status.setText("; ".join(warnings) or "ok")
            status.setForeground(QtGui.QBrush(QtGui.QColor("#c00000" if warnings else "#207020")))
        self._updating_table = False
        self._update_info()

    def _update_info(self) -> None:
        sel = [it.sample for it in self.items.values() if it.isSelected()]
        if len(sel) != 1:
            self.info.setText(f"{len(self.layout_model.samples)} sample(s).")
            return
        s = sel[0]
        u0, v0, u1, v1 = s.bounds()
        surf = s.surface_height(self.layout_model.plate)
        self.info.setText(
            f"<b>{s.name}</b>: u ∈ [{u0:.2f}, {u1:.2f}], v ∈ [{v0:.2f}, {v1:.2f}] mm<br>"
            f"surface at {surf:.3f} mm above plate back → SN ≈ SN_f + {surf:.3f}"
        )

    # -- selection sync ----------------------------------------------------------
    def _on_scene_selection(self) -> None:
        if self._updating_table:
            return
        self._updating_table = True
        self.table.clearSelection()
        mode = self.table.selectionMode()
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for row, s in enumerate(self.layout_model.samples):
            if self.items[id(s)].isSelected():
                self.table.selectRow(row)
        self.table.setSelectionMode(mode)
        self._updating_table = False
        self._update_info()

    def _on_table_selection(self) -> None:
        if self._updating_table:
            return
        rows = {i.row() for i in self.table.selectedIndexes()}
        self._updating_table = True
        for row, s in enumerate(self.layout_model.samples):
            self.items[id(s)].setSelected(row in rows)
        self._updating_table = False
        self._update_info()

    def _on_cursor_moved(self, u: float, v: float) -> None:
        self.cursor_label.setText(f"cursor: u = {u:.2f} mm, v = {v:.2f} mm")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, layout: SampleLayout | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment — sample plate")
        self.editor = PlateEditor(layout)
        self.setCentralWidget(self.editor)
        self.resize(1200, 720)
        self._path: str | None = None

        bar = self.addToolBar("File")
        for text, slot in (("New", self.new_layout), ("Open…", self.open_layout), ("Save", self.save_layout), ("Save as…", self.save_layout_as)):
            btn = QtWidgets.QToolButton()
            btn.setText(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        self.statusBar().showMessage("Drag on the plate to add a sample.")

    def new_layout(self) -> None:
        self._path = None
        self.editor.set_layout(SampleLayout())

    def open_layout(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open layout", "", "Layout (*.json)")
        if path:
            try:
                self.editor.set_layout(SampleLayout.load(path))
            except (OSError, ValueError, TypeError) as exc:
                QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
                return
            self._path = path
            self.statusBar().showMessage(f"Loaded {path}")

    def save_layout(self) -> None:
        if self._path is None:
            self.save_layout_as()
            return
        self.editor.layout_model.save(self._path)
        self.statusBar().showMessage(f"Saved {self._path}")

    def save_layout_as(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save layout", "layout.json", "Layout (*.json)")
        if path:
            self._path = path
            self.save_layout()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    layout = SampleLayout.load(argv[1]) if len(argv) > 1 else None
    win = MainWindow(layout)
    win.show()
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
