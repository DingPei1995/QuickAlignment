"""Window "Find angles for a BZ point" of the Rotate sample tab (2-D hexagonal crystals).

Input, read on the contour of a map in ARPES viewer (theta = deflector across,
phi = angle along the slit up): the stage angles and photon energy of the map,
the angles of Gamma and of one K or M point, and the lattice constant. Output:
SRn / SRz putting the wanted point (Gamma, K, K', M) at the slit centre with
the deflector at 0 and the slit along the wanted high-symmetry line, whether
that is within the ranges (|theta|, |phi| <= 5 deg, SRn 60 ... 180, SRz -25 ...
+10), what to do otherwise, and a preview of the map and of the 2-D zone.
"""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ._qt import QtCore, QtGui, QtWidgets
from .stage_panel import MOTOR_SPECS, spin
from .. import bz_target as bt
from ..rotation import AnalyzerGeometry
from ..stage import MotorPositions

Qt = QtCore.Qt

COLUMNS = ("Point (azimuth from the reference)", "SRn", "SRz", "θ (defl.)", "φ (slit)", "Slit vs line", "Beam to normal", "Status")


def _angle(value=0.0, lo=-90.0, hi=90.0):
    return spin(value, lo, hi, 2, 0.1, " °")


def _pair(a, b) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    for text, box in (("θ", a), ("φ", b)):
        row.addWidget(QtWidgets.QLabel(text))
        row.addWidget(box, 1)
    return w


class BZTargetDialog(QtWidgets.QDialog):
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel  # RotationPanel
        self.geo = AnalyzerGeometry()
        self.advice = None
        self.target = None
        self.setWindowTitle("Find angles for a Brillouin-zone point")
        self.resize(1460, 880)

        # -- 1. the map ---------------------------------------------------------------------
        self.map_srn = spin(120.0, *MOTOR_SPECS["srn"][1:])
        self.map_srz = spin(0.0, *MOTOR_SPECS["srz"][1:])
        from_btn = QtWidgets.QPushButton("From current position")
        from_btn.setToolTip("SRn / SRz of “1. Current position” in the Rotate sample tab.")
        from_btn.clicked.connect(self.take_current)
        self.hv_map = spin(95.0, 10, 1000, 2, 1.0, " eV")
        self.gamma_th, self.gamma_ph = _angle(), _angle()
        self.ref_label = QtWidgets.QComboBox()
        self.ref_label.addItems(["K", "M"])
        self.ref_th, self.ref_ph = _angle(), _angle()
        self.ref_check = QtWidgets.QLabel()
        self.ref_check.setWordWrap(True)
        map_box = QtWidgets.QGroupBox("1. The map (read on the ARPES viewer contour)")
        mf = QtWidgets.QFormLayout(map_box)
        axes = QtWidgets.QLabel("θ = deflector angle (contour x), φ = angle along the slit (contour y).")
        axes.setWordWrap(True)
        axes.setStyleSheet("color: #555;")
        mf.addRow(axes)
        mf.addRow("SRn of the map", self.map_srn)
        mf.addRow("SRz of the map", self.map_srz)
        mf.addRow("", from_btn)
        mf.addRow("Photon energy", self.hv_map)
        mf.addRow("Γ at", _pair(self.gamma_th, self.gamma_ph))
        ref_row = QtWidgets.QHBoxLayout()
        ref_row.addWidget(self.ref_label)
        ref_row.addWidget(_pair(self.ref_th, self.ref_ph), 1)
        mf.addRow("Reference point", ref_row)
        mf.addRow(self.ref_check)

        # -- 2. crystal ------------------------------------------------------------------------
        self.material = QtWidgets.QComboBox()
        self.material.addItems(list(bt.MATERIALS) + ["Other"])
        self.material.setCurrentText("WSe2")
        self.a = spin(bt.MATERIALS["WSe2"], 0.5, 50, 3, 0.01, " Å")
        self.material.currentTextChanged.connect(self._material_changed)
        self.a.valueChanged.connect(self._a_changed)
        crystal_box = QtWidgets.QGroupBox("2. Crystal (2-D hexagonal)")
        cf = QtWidgets.QFormLayout(crystal_box)
        cf.addRow("Material", self.material)
        cf.addRow("Lattice constant a", self.a)

        # -- 3. wanted ------------------------------------------------------------------------
        self.feature = QtWidgets.QComboBox()
        self.feature.addItems(bt.FEATURES)
        self.feature.setCurrentIndex(1)
        self.line = QtWidgets.QComboBox()
        self.feature.currentTextChanged.connect(self._fill_lines)
        self.hv = spin(95.0, 10, 1000, 2, 1.0, " eV")
        self.hv.setToolTip(f"Photon energy of the new measurement. ANTARES: {bt.HV_RANGE[0]:g} … {bt.HV_RANGE[1]:g} eV "
                           f"with the capillary; the zone plate works at {bt.ZONE_PLATE_HV:g} eV only.")
        self.binding = spin(0.0, -20, 5, 3, 0.1, " eV")
        self.binding.setToolTip("Energy of the feature, E − E_F (e.g. −1.0 for a band 1 eV below E_F).")
        self.work_function = spin(bt.WORK_FUNCTION, 0, 10, 2, 0.1, " eV")
        compute_btn = QtWidgets.QPushButton("Compute")
        compute_btn.setMinimumHeight(34)
        compute_btn.setStyleSheet("font-weight: bold;")
        compute_btn.clicked.connect(self.compute)
        want_box = QtWidgets.QGroupBox("3. Wanted: point at the slit centre, deflector at 0")
        wf = QtWidgets.QFormLayout(want_box)
        wf.addRow("Point", self.feature)
        wf.addRow("Slit along", self.line)
        wf.addRow("Photon energy", self.hv)
        wf.addRow("E − E_F of the point", self.binding)
        wf.addRow("Work function", self.work_function)
        wf.addRow(compute_btn)
        limits = QtWidgets.QLabel(
            f"Accepted: |θ| ≤ {bt.DEFLECTOR_OK:g}° and |φ| ≤ {bt.SLIT_OK:g}° with the deflector at 0, slit within "
            f"{bt.DIRECTION_TOL:g}° of the line; SRn {bt.SRN_RANGE[0]:g} … {bt.SRN_RANGE[1]:g}°, SRz "
            f"{bt.SRZ_RANGE[0]:g} … {bt.SRZ_RANGE[1]:+g}°. Deflector: gaps beyond ±{bt.DEFLECTOR_GAP:g}°, "
            f"max ±{bt.DEFLECTOR_MAX:g}°.")
        limits.setWordWrap(True)
        limits.setStyleSheet("color: #555;")

        # -- results ----------------------------------------------------------------------------
        self.result_label = QtWidgets.QLabel("Enter the numbers read on the map and press “Compute”.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f6f6f6; border: 1px solid #ddd;")
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(170)
        self.table.itemSelectionChanged.connect(self._draw)
        self.figure = Figure(figsize=(10, 4.6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.use_btn = QtWidgets.QPushButton("Use these angles")
        self.use_btn.setToolTip("Put SRn / SRz of the selected row into “2. Wanted angles” and compute the new position.")
        self.use_btn.clicked.connect(self.use)
        self.radial_btn = QtWidgets.QPushButton("Show the radial alternative")
        self.radial_btn.clicked.connect(self.show_radial)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.radial_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.use_btn)
        buttons.addWidget(close_btn)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        for w in (map_box, crystal_box, want_box, limits):
            lv.addWidget(w)
        lv.addStretch(1)
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.addWidget(self.result_label)
        rv.addWidget(self.table)
        rv.addWidget(self.canvas, 1)
        rv.addLayout(buttons)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([540, 900])
        box = QtWidgets.QVBoxLayout(self)
        box.addWidget(splitter)

        self._fill_lines()
        self.take_current()
        if "zone" in self.panel.optic_name():
            self.hv_map.setValue(bt.ZONE_PLATE_HV)
            self.hv.setValue(bt.ZONE_PLATE_HV)
        self._update_buttons()

    # -- inputs -----------------------------------------------------------------------------------
    def take_current(self) -> None:
        m = self.panel.measured.value()
        self.map_srn.setValue(m.srn)
        self.map_srz.setValue(m.srz)

    def _material_changed(self, name: str) -> None:
        if name in bt.MATERIALS:
            self.a.blockSignals(True)
            self.a.setValue(bt.MATERIALS[name])
            self.a.blockSignals(False)

    def _a_changed(self, value: float) -> None:
        name = next((k for k, v in bt.MATERIALS.items() if abs(v - value) < 1e-6), "Other")
        self.material.blockSignals(True)
        self.material.setCurrentText(name)
        self.material.blockSignals(False)

    def _fill_lines(self, *_) -> None:
        kind = bt.feature_kind(self.feature.currentText())
        current = self.line.currentIndex()
        self.line.clear()
        self.line.addItems([label for label, _ in bt.LINES[kind]])
        self.line.setCurrentIndex(max(current, 0))

    def make_target(self) -> bt.HexTarget:
        m = MotorPositions(srn=self.map_srn.value(), srz=self.map_srz.value())
        return bt.HexTarget(
            a=self.a.value(), hv_map=self.hv_map.value(), gamma=(self.gamma_th.value(), self.gamma_ph.value()),
            ref_label=self.ref_label.currentText(), ref=(self.ref_th.value(), self.ref_ph.value()), measured=m,
            feature=self.feature.currentText(), line=self.line.currentIndex(), binding=self.binding.value(),
            work_function=self.work_function.value())

    # -- computation ------------------------------------------------------------------------------
    def compute(self) -> None:
        model = self.panel.stage.model()
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(Qt.WaitCursor))
        try:
            self.target = self.make_target()
            self.advice = bt.advise(model, self.geo, self.target, self.hv.value(), self.panel.optic_name())
        except ValueError as exc:
            self.advice = None
            self.result_label.setText(f"<b style='color:#b00'>{exc}</b>")
            self.table.setRowCount(0)
            self._update_buttons()
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._show()

    def _show(self) -> None:
        adv, t = self.advice, self.target
        f = adv.frame
        self.ref_check.setText(
            f"Γ–{t.ref_label} on the map: {f.ref_k:.3f} Å⁻¹ (lattice: {f.ref_k_expected:.3f} Å⁻¹); Γ is "
            f"{f.tilt:.1f}° from the plate normal.")
        line = bt.LINES[bt.feature_kind(t.feature)][t.line][0].split(" ")[0]
        best = adv.best
        if best is None:
            head = (f"<b style='color:#b00'>The point is not seen at hν = {adv.hv:g} eV</b> "
                    "(outside the photoemission horizon).")
        elif adv.ok:
            head = (f"<b style='color:#207020'>Reachable at hν = {adv.hv:g} eV:</b> "
                    f"<b>SRn = {best.srn:.2f}°, SRz = {best.srz:.2f}°</b>.<br>With the deflector at 0 the point "
                    f"({best.label}) is at θ = {best.theta:.2f}°, φ = {best.phi:.2f}°; the slit runs along {line} "
                    f"(within {best.direction_error:.1f}°). Beam {best.incidence:.0f}° from the surface normal.")
        else:
            head = (f"<b style='color:#b00'>Not reachable at hν = {adv.hv:g} eV.</b> Closest ({best.label}): "
                    + "; ".join(best.problems) + ".")
        body = "".join(f"<li>{m}</li>" for m in adv.messages)
        what = "What to do / remarks" if not adv.ok else "Remarks"
        self.result_label.setText(head + (f"<br><b>{what}:</b><ul style='margin:0'>{body}</ul>" if body else ""))
        self.table.setRowCount(len(adv.candidates))
        for row, c in enumerate(adv.candidates):
            values = (c.label, f"{c.srn:.2f}", f"{c.srz:.2f}", f"{c.theta:.2f}", f"{c.phi:.2f}",
                      f"{c.direction_error:.1f}°", f"{c.incidence:.0f}°", "ok" if c.ok else "; ".join(c.problems))
            for col, v in enumerate(values):
                item = QtWidgets.QTableWidgetItem(v)
                if col == len(values) - 1:
                    item.setForeground(QtGui.QColor("#207020" if c.ok else "#b00"))
                    item.setToolTip(v)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        if adv.candidates:
            self.table.selectRow(0)
        self._draw()

    def selected(self):
        if self.advice is None or not self.advice.candidates:
            return None
        rows = self.table.selectionModel().selectedRows()
        return self.advice.candidates[rows[0].row() if rows else 0]

    def _draw(self) -> None:
        if self.advice is not None:
            bt.draw_preview(self.figure, self.panel.stage.model(), self.geo, self.target, self.advice.hv,
                            self.selected(), self.advice.frame)
            self.canvas.draw_idle()
        self._update_buttons()

    def _update_buttons(self) -> None:
        c = self.selected()
        self.use_btn.setEnabled(c is not None)
        self.radial_btn.setVisible(self.advice is not None and self.advice.alternative is not None)

    def show_radial(self) -> None:
        self.line.setCurrentIndex(0)
        self.compute()

    def use(self) -> None:
        c = self.selected()
        if c is None:
            return
        if not c.ok:
            answer = QtWidgets.QMessageBox.question(
                self, "Not within the limits",
                f"This solution is not within the limits:\n• " + "\n• ".join(c.problems) + "\n\nUse it anyway?")
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self.panel.set_wanted(c.srn, c.srz)
        note = (f"Set the deflector to 0. The point is expected at θ = {c.theta:.2f}°, φ = {c.phi:.2f}°.")
        if abs(self.advice.hv - self.hv_map.value()) > 0.01:
            note += f"\nSet the photon energy to {self.advice.hv:g} eV."
        QtWidgets.QMessageBox.information(self, "Angles taken", f"SRn = {c.srn:.3f}°, SRz = {c.srz:.3f}° are in "
                                          f"“2. Wanted angles”; the new position is computed.\n\n{note}")
