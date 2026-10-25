"""Samples from a photo: the plate photographed from above (sample side).

1. open the photo
2. click on it the four corners of the sample area in the order of the
   numbers shown in the right view (the next one in red); drag them to refine
3. the photo is mapped onto the plate model (right view); samples are found
   by their colour: by default close to sample colours picked by clicking on
   samples (leaves out silver paint, glue, wires), or anything differing from
   the bare plate; adjust the ΔE threshold
4. correct by hand: draw missing boxes, delete wrong ones, merge the pieces of
   a sample broken up by paint (kept when the detection is run again)
5. enter the sample height H (not visible on a photo from above), choose the
   samples to keep and add them to the plate

The boxes are a starting point: they can be moved / resized in the Samples
tab like drawn ones; devices are located on a close-up photo with "Device
from photo…", and "Found here" corrects the positions later.
"""

from __future__ import annotations

import math

import numpy as np

from ._qt import QtCore, QtGui, QtWidgets
from .photo_widgets import PhotoRegistration, array_to_qimage, lab_to_rgb
from .plate_editor import COLOR_SAMPLE, cosmetic_pen
from ..geometry import PlateGeometry, Sample
from ..photo import PX_PER_MM, Detection, detect_samples, overlap, plate_view_bounds, rgb_to_lab

Qt = QtCore.Qt

COLOR_FOUND = QtGui.QColor("#18c418")
RESULT_COLUMNS = ["Use", "Name", "x (mm)", "y (mm)", "L (mm)", "W (mm)", "H (mm)", "ΔE"]
MODES = ["colour different from the bare plate", "colour of picked samples"]
BY_PLATE, BY_SAMPLE = range(2)
DEFAULT_THRESHOLD = (12.0, 20.0)  # per mode
PATCH_MM = 0.3  # side of the patch averaged when picking a colour
SAME_BOX = 0.5  # boxes overlapping more than this (intersection over union) are the same sample
DRAW_STEP = 0.05  # mm, drawn boxes are rounded to this


class PhotoImportDialog(QtWidgets.QDialog):
    def __init__(self, plate: PlateGeometry, default_height: float, existing: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Samples from a photo")
        self.resize(1400, 920)
        self.plate = plate
        self.existing = list(existing or [])
        self.background: np.ndarray | None = None  # picked bare plate colour (Lab), None: automatic
        self.sample_colors: list[np.ndarray] = []  # picked sample colours (Lab)
        self.auto: list[Detection] = []  # found by colour
        self.manual: list[Detection] = []  # drawn or merged by the user
        self.rejected: list = []  # rects of found boxes the user deleted or merged
        self.detections: list[Detection] = []  # shown: auto (not rejected) + manual
        self._shown_background = None
        self._plate_overlay: list[QtWidgets.QGraphicsItem] = []
        self._filling = False

        self.reg = PhotoRegistration(plate, plate.riser_bounds(), "the sample area", plate_view_bounds(plate),
                                     PX_PER_MM)
        self.reg.photo_title.setText("<b>Photo</b> from above (sample side)")
        self.reg.changed.connect(self._on_registration)
        self.reg.plateClicked.connect(self._on_plate_click)
        self.reg.plateDragged.connect(self._on_plate_drag)
        self.reg.cursor_text = self._cursor_text
        self.mask_item = QtWidgets.QGraphicsPixmapItem()
        self.mask_item.setZValue(6)
        self.reg.plate_scene.addItem(self.mask_item)

        open_btn = QtWidgets.QPushButton("Open photo…")
        open_btn.clicked.connect(self.open_photo)
        reset_btn = QtWidgets.QPushButton("Clear points")
        reset_btn.setToolTip("Remove the points clicked on the photo and start again")
        reset_btn.clicked.connect(self.reg.clear_corners)
        self.file_label = QtWidgets.QLabel("no photo")
        self.file_label.setStyleSheet("color: #555;")
        self.instruction = QtWidgets.QLabel()
        self.instruction.setWordWrap(True)

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
        self.mode.setCurrentIndex(BY_SAMPLE)
        self.mode.setToolTip("Picked samples (default): click on each kind of sample; only what has a colour close "
                             "to them is found, silver paint and glue are left out.\nDifferent from the bare plate: "
                             "everything on the plate is found (also silver paint, glue).")
        self.mode.currentIndexChanged.connect(self._on_mode)
        self.threshold = spin(1, 150, DEFAULT_THRESHOLD[BY_SAMPLE], 1, 1, "", "Colour difference ΔE (CIELAB).\n"
                              "Picked samples: a point closer than this to a picked colour belongs to a sample.\n"
                              "Bare plate: a point differing more than this from the bare plate belongs to a sample "
                              "(lower: finds samples close to the plate colour; higher: ignores shadows and "
                              "reflections).")
        self.min_area = spin(0.01, 50, 0.2, 0.05, 2, " mm²", "Smaller spots are ignored (dust, scratches).")
        self.border = spin(0, 1.5, 0.15, 0.05, 2, " mm", "Strip along the sample area edge that is left out "
                           "(the edge itself shows on the photo).\nA sample reaching into it is extended to the edge.")
        self.smooth = spin(0, 0.5, 0.1, 0.05, 2, " mm", "Noise filter: fills small gaps (glare) and removes specks "
                           "of about this size.")

        # what a left click / drag in the views does (one at a time)
        self.pick_btn = QtWidgets.QPushButton("Pick bare plate colour")
        self.pick_btn.setToolTip("Then click on bare plate. Use it when samples cover most of the sample area or "
                                 "the automatic colour is wrong.")
        self.auto_btn = QtWidgets.QPushButton("Automatic")
        self.auto_btn.setToolTip("Bare plate colour estimated from the photo")
        self.auto_btn.clicked.connect(self.auto_background)
        self.swatch = QtWidgets.QLabel()
        self.swatch.setFixedSize(40, 18)
        self.pick_sample_btn = QtWidgets.QPushButton("Pick sample colour")
        self.pick_sample_btn.setToolTip("Then click on a sample, on the photo or in the right view (once per kind "
                                        "of sample).")
        self.clear_colors_btn = QtWidgets.QPushButton("Clear")
        self.clear_colors_btn.setToolTip("Forget the picked sample colours")
        self.clear_colors_btn.clicked.connect(self.clear_sample_colors)
        self.sample_swatches = QtWidgets.QLabel()
        self.draw_btn = QtWidgets.QPushButton("Draw box")
        self.draw_btn.setToolTip("Drag in the right view to add a sample by hand (one the colour does not find).")
        for b in (self.pick_btn, self.pick_sample_btn, self.draw_btn):
            b.setCheckable(True)
            b.toggled.connect(self._on_tool_toggled)
        self.show_mask = QtWidgets.QCheckBox("show what is taken")
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
        self.table.horizontalHeaderItem(7).setToolTip("Mean colour difference; “drawn”: box drawn or merged by hand")
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(130)
        self.table.itemChanged.connect(self._on_table_changed)
        self.table.itemSelectionChanged.connect(self._draw_detections)
        merge_btn = QtWidgets.QPushButton("Merge selected")
        merge_btn.setToolTip("One sample from the selected rows (pieces of a sample broken up by paint or wires).")
        merge_btn.clicked.connect(self.merge_selected)
        delete_btn = QtWidgets.QPushButton("Delete selected")
        delete_btn.setToolTip("Remove wrong boxes (also with the Delete key). They stay removed when the detection "
                              "is run again.")
        delete_btn.clicked.connect(self.delete_selected)
        undo_btn = QtWidgets.QPushButton("Undo hand edits")
        undo_btn.setToolTip("Forget the drawn, merged and deleted boxes: only what the colour finds")
        undo_btn.clicked.connect(self.undo_edits)
        QtWidgets.QShortcut(QtGui.QKeySequence(Qt.Key_Delete), self.table, self.delete_selected)

        self.replace = QtWidgets.QCheckBox("Remove the samples already on the plate")
        self.replace.setVisible(bool(self.existing))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.add_btn = QtWidgets.QPushButton("Add to plate")
        self.add_btn.setStyleSheet("font-weight: bold;")
        self.add_btn.setEnabled(False)
        self.add_btn.setAutoDefault(False)
        self.add_btn.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setAutoDefault(False)
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
        params2.addWidget(self.draw_btn)
        params2.addWidget(self.show_mask)
        params2.addStretch(1)

        height_row = QtWidgets.QHBoxLayout()
        height_row.addWidget(QtWidgets.QLabel("<b>Samples</b>   height H"))
        height_row.addWidget(self.height_box)
        height_row.addWidget(height_all)
        note = QtWidgets.QLabel("(not visible from above; Si wafer substrate 0.525 mm)")
        note.setStyleSheet("color: #555;")
        height_row.addWidget(note)
        height_row.addStretch(1)
        for b in (merge_btn, delete_btn, undo_btn):
            height_row.addWidget(b)
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
        split.addWidget(self.reg)
        split.addWidget(lower_w)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        box = QtWidgets.QVBoxLayout(self)
        box.addLayout(top)
        box.addWidget(self.instruction)
        box.addLayout(params)
        box.addLayout(params2)
        box.addWidget(split, 1)
        box.addLayout(bottom)
        self._on_mode(BY_SAMPLE)

    # -- photo ---------------------------------------------------------------------
    @property
    def rectified(self):
        return self.reg.rectified

    def open_photo(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open plate photo", "",
                                                        "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if path:
            self.load_photo(path)

    def load_photo(self, path: str) -> bool:
        if not self.reg.load_photo(path):
            return False
        self.file_label.setText(path)
        return True

    def set_photo(self, rgb: np.ndarray) -> None:
        self.reg.set_photo(rgb)

    def set_corners(self, points) -> None:
        self.reg.set_corners(points)

    def _on_registration(self) -> None:
        if self.rectified is not None:
            self.reg.place_on_rectified(self.mask_item)
        self.detect()

    def _update_instruction(self, error: str = "") -> None:
        error = error or self.reg.error
        text = self.reg.corner_instruction()
        if self.reg.photo is None:
            text = "Open a photo of the plate taken from straight above (sample side, whole sample area visible)."
        elif text is None and error:
            text = error
        elif text is None and self.draw_btn.isChecked():
            text = "Drag in the right view to draw a sample box."
        elif text is None and self.pick_btn.isChecked():
            text = "Click on bare plate (on the photo or in the right view)."
        elif text is None and (self.pick_sample_btn.isChecked()
                               or (self.mode.currentIndex() == BY_SAMPLE and not self.sample_colors)):
            text = "Click on a sample (on the photo or in the right view) to pick its colour, once per kind of sample."
        elif text is None:
            text = ("Check that the plate model (blue) lies on the plate; drag the points to refine. Adjust the ΔE "
                    "threshold; draw missing boxes, delete wrong ones (click a box to select it).")
        color = "#c00000" if error and text == error else "#00609a"
        self.instruction.setStyleSheet(f"font-weight: bold; color: {color};")
        self.instruction.setText(text)

    # -- tools (what a click does) --------------------------------------------------
    def _on_mode(self, index: int) -> None:
        for w in self.plate_color_widgets:
            w.setVisible(index == BY_PLATE)
        for w in self.sample_color_widgets:
            w.setVisible(index == BY_SAMPLE)
        self.pick_btn.setChecked(False)
        self.pick_sample_btn.setChecked(index == BY_SAMPLE and not self.sample_colors)
        self.threshold.blockSignals(True)
        self.threshold.setValue(DEFAULT_THRESHOLD[index])
        self.threshold.blockSignals(False)
        self.detect()

    def _on_tool_toggled(self, on: bool) -> None:
        if on:
            for b in (self.pick_btn, self.pick_sample_btn, self.draw_btn):
                if b is not self.sender():
                    b.setChecked(False)
        self.reg.plate_view.drag_enabled = self.draw_btn.isChecked()
        tool = any(b.isChecked() for b in (self.pick_btn, self.pick_sample_btn, self.draw_btn))
        self.reg.plate_view.viewport().setCursor(Qt.CrossCursor if tool else Qt.ArrowCursor)
        self._update_instruction()

    def _on_plate_click(self, u: float, v: float) -> None:
        if self.rectified is None:
            return
        if self.pick_btn.isChecked():
            self.pick_background(u, v)
        elif self.pick_sample_btn.isChecked():
            self.pick_sample_color(u, v)
        else:
            self.select_at(u, v)

    def _on_plate_drag(self, u0: float, v0: float, u1: float, v1: float) -> None:
        if self.draw_btn.isChecked():
            self.add_box(u0, v0, u1, v1)

    def _cursor_text(self, u: float, v: float) -> str:
        for row, d in enumerate(self.detections):
            if d.u0 <= u <= d.u1 and d.v0 <= v <= d.v1:
                return f"in {self._name(row)}"
        return ""

    # -- colours -------------------------------------------------------------------
    def auto_background(self) -> None:
        self.background = None
        self.pick_btn.setChecked(False)
        self.detect()

    def clear_sample_colors(self) -> None:
        self.sample_colors = []
        self.pick_sample_btn.setChecked(True)
        self.detect()

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
        self.pick_btn.setChecked(False)
        self.detect()
        return True

    def pick_sample_color(self, u: float, v: float) -> bool:
        lab = self._patch_color(u, v)
        if lab is None:
            return False
        self.sample_colors.append(lab)
        self.pick_sample_btn.setChecked(False)
        if self.mode.currentIndex() != BY_SAMPLE:
            self.mode.setCurrentIndex(BY_SAMPLE)  # detects
        else:
            self.detect()
        return True

    # -- detection -----------------------------------------------------------------
    def detect(self) -> None:
        old = (self.detections, self._row_states())
        by_sample = self.mode.currentIndex() == BY_SAMPLE
        self.auto = []
        self.mask_item.setPixmap(QtGui.QPixmap())
        error = ""
        if self.rectified is not None and not (by_sample and not self.sample_colors):
            try:
                result = detect_samples(self.rectified, self.plate.riser_bounds(), self.threshold.value(),
                                        self.min_area.value(), self.border.value(), self.smooth.value(),
                                        self.background, self.sample_colors if by_sample else None)
            except ValueError as exc:
                error = str(exc)
            else:
                self.auto = result.detections
                if not by_sample:
                    self._shown_background = result.background
                rgba = np.zeros(result.mask.shape + (4,), np.uint8)
                rgba[result.mask] = (255, 0, 200, 110)
                self.mask_item.setPixmap(QtGui.QPixmap.fromImage(array_to_qimage(rgba, QtGui.QImage.Format_RGBA8888)))
        self._update_instruction(error)
        self._rebuild(*old)

    def _rebuild(self, old_detections: list[Detection], old_states: list) -> None:
        """Shown boxes = found (not rejected) + hand-made; rows keep their tick / name / H by box overlap."""
        if self.rectified is None:
            self.detections = []
        else:
            kept = [d for d in self.auto if not any(overlap(d.rect, r) > SAME_BOX for r in self.rejected)]
            self.detections = kept + self.manual
        states, taken = [], set()
        for d in self.detections:
            free = [i for i in range(len(old_detections)) if i not in taken]
            best = max(free, key=lambda i: overlap(d.rect, old_detections[i].rect), default=None)
            ok = best is not None and overlap(d.rect, old_detections[best].rect) > SAME_BOX
            states.append(old_states[best] if ok else None)
            if ok:
                taken.add(best)
        self._fill_table(states)
        self._update_swatch()
        self._draw_detections()

    def _update_swatch(self) -> None:
        self.sample_swatches.setText(" ".join(
            '<span style="background: rgb({},{},{});">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>'.format(*lab_to_rgb(c))
            for c in self.sample_colors) or "none")
        lab = self.background if self.background is not None else self._shown_background
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
            self.reg.plate_scene.removeItem(it)
        self._plate_overlay = []
        selected = self._selected_rows()
        shapes = []
        for row, d in enumerate(self.detections):
            used = self._used(row)
            pen = cosmetic_pen(COLOR_FOUND if used else "#888888", 3 if row in selected else 1.8,
                               Qt.SolidLine if used else Qt.DashLine)
            item = self.reg.plate_scene.addRect(QtCore.QRectF(d.u0, -d.v1, d.u1 - d.u0, d.v1 - d.v0), pen,
                                                QtGui.QBrush(COLOR_SAMPLE if row in selected else Qt.NoBrush))
            item.setZValue(9)
            item.setAcceptedMouseButtons(Qt.NoButton)
            label = self.reg.plate_scene.addSimpleText(self._name(row))
            label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            label.setBrush(QtGui.QBrush(QtGui.QColor("#0a6a0a")))
            label.setPos(d.u0, -d.v1)
            label.setZValue(9)
            label.setAcceptedMouseButtons(Qt.NoButton)
            self._plate_overlay += [item, label]
            if used:
                shapes.append(([(d.u0, d.v0), (d.u1, d.v0), (d.u1, d.v1), (d.u0, d.v1)], COLOR_FOUND,
                               3 if row in selected else 2))
        self.reg.set_photo_overlay(shapes)
        n = sum(self._used(r) for r in range(len(self.detections)))
        self.add_btn.setEnabled(n > 0)
        if self.rectified is None:
            self.status.setText("")
        else:
            self.status.setText(f"{len(self.detections)} sample(s), {n} to add. Touching samples come out as one "
                                "box; positions can be refined afterwards in the Samples tab, devices located with "
                                "“Device from photo…”.")

    # -- hand edits ----------------------------------------------------------------
    def add_box(self, u0: float, v0: float, u1: float, v1: float) -> Detection | None:
        """A sample drawn by hand (plate rectangle)."""
        u0, v0, u1, v1 = (round(x / DRAW_STEP) * DRAW_STEP for x in (u0, v0, u1, v1))
        if u1 - u0 < DRAW_STEP or v1 - v0 < DRAW_STEP:
            return None
        d = Detection(u0, v0, u1, v1, (u1 - u0) * (v1 - v0), math.nan, manual=True)
        old = (self.detections, self._row_states())
        self.manual.append(d)
        self._rebuild(*old)
        self._select_row(self.detections.index(d))
        return d

    def _remove(self, parts: list[Detection]) -> None:
        for d in parts:
            if d.manual:
                self.manual.remove(d)
            else:
                self.rejected.append(d.rect)

    def merge_selected(self) -> None:
        rows = self._selected_rows()
        if len(rows) < 2:
            QtWidgets.QMessageBox.information(self, "Merge", "Select the rows (or boxes) of the pieces to merge "
                                              "(Ctrl + click).")
            return
        old = (self.detections, self._row_states())
        parts = [self.detections[r] for r in rows]
        merged = Detection.merged(parts)
        self._remove(parts)
        self.manual.append(merged)
        # the merged box keeps the name of its first piece
        states = list(old[1])
        self._rebuild(old[0] + [merged], states + [states[rows[0]]])
        self._select_row(self.detections.index(merged))

    def delete_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        old = (self.detections, self._row_states())
        self._remove([self.detections[r] for r in rows])
        self._rebuild(*old)

    def undo_edits(self) -> None:
        old = (self.detections, self._row_states())
        self.manual, self.rejected = [], []
        self._rebuild(*old)

    def select_at(self, u: float, v: float) -> None:
        """Select the (smallest) box under a click."""
        hits = [r for r, d in enumerate(self.detections) if d.u0 <= u <= d.u1 and d.v0 <= v <= d.v1]
        if not hits:
            self.table.clearSelection()
            return
        row = min(hits, key=lambda r: self.detections[r].size[0] * self.detections[r].size[1])
        if QtWidgets.QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.table.selectionModel().select(self.table.model().index(row, 0),
                                               QtCore.QItemSelectionModel.Toggle | QtCore.QItemSelectionModel.Rows)
        else:
            self._select_row(row)

    def _select_row(self, row: int) -> None:
        self.table.clearSelection()
        self.table.selectRow(row)

    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    # -- results table ------------------------------------------------------------
    def _default_names(self, n: int, taken: set) -> list[str]:
        taken = taken | set(self.existing)
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
        names = iter(self._default_names(sum(s is None for s in states), {s[1] for s in states if s}))
        for row, d in enumerate(self.detections):
            (u, v), (length, width) = d.center, d.size
            check, name, height = states[row] or (Qt.Checked, next(names), f"{self.height_box.value():.3f}")
            de = "drawn" if d.manual and math.isnan(d.delta_e) else f"{d.delta_e:.0f}" + (" (merged)" if d.manual else "")
            values = ["", name, f"{u:.2f}", f"{v:.2f}", f"{length:.2f}", f"{width:.2f}", height, de]
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

    def _used(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return item is not None and item.checkState() == Qt.Checked

    def _name(self, row: int) -> str:
        item = self.table.item(row, 1)
        return item.text().strip() if item is not None else ""

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
