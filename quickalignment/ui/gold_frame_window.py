"""Gold-frame calibration window: plan the SZ lines, load them, fit them all at once, save the configuration.

SZ is the only fast motor: every measurement is an SZ fly line, ST / SN / SRn / SRz only move between
lines. With the frame turned by 45 deg (SRn ref +- 45) its edges are diagonal, so where an SZ line
crosses them also gives the horizontal position.

1. *Measurement plan…*: the SZ lines to measure (groups A, B, C), placed with the newest configuration,
   checked against the motor ranges and the anti-collision model; CSV for the beamline.
2. *Add files…*: any number of .nxs files (one per SRn / SRz group, ST stepped, SZ fast; single lines;
   an ST x SZ overview map; an SZ x SRn sweep), or .npz from the simulator.
3. Settings: SN gold, gold height, where the frame is taken to be, the optic.
4. *Fit*: every edge of every line at once; the constants, their uncertainties, the change from the newest
   configuration; the data with the fitted edges.
5. *Save as new configuration*.

Optional: *SN at other SRz…* (SN focus points, a separate dialog) adds focus measurements to the fit.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ._qt import QtCore, QtWidgets, exec_app, install_excepthook
from .stage_panel import out_of_range, spin
from ..calibration import CalibrationStore
from ..collision import collisions
from ..geometry import STANDARD_PLATE, Sample, SampleLayout
from ..gold_frame import (
    GROUP_TEXT, PARAM_TEXT, GoldFrame, Instrument, Setup, SNPoint, fit_global, simulated_measurement, sn_point_plan,
    survey_plan,
)
from ..gold_frame_cli import CONFIG_ARGS, calibration_record, load_map, read_sn_points, save_scan, write_plan_csv
from ..gold_frame_plot import draw_survey, is_overview

Qt = QtCore.Qt
ROOT = Path(__file__).resolve().parent.parent.parent
FILE_FILTER = "SPEM scans (*.nxs *.h5 *.hdf5 *.npz);;All files (*)"
LABELS = {
    "st0": "ST0", "sz0": "SZ0", "sn_f": "SN_f", "srn_axis_u": "SRn axis x", "srn_axis_v": "SRn axis y",
    "srz_offset_t": "SRz offset ST", "srz_offset_n": "SRz offset SN",
}
EXTRA = ("frame.rotation", "frame.tilt_u", "instrument.st_scale", "instrument.sz_scale")

HELP_HTML = """
<p><b>Before the lines</b> (SRn 120, SRz 0, PIX = PIY = 150): find the gold, run an SN scan on a gold bar with ST
following (ΔST = −ΔSN): the peak is <i>SN gold</i>, its width the analyzer acceptance. The same scan on the riser
gives the gold height (difference of the peaks). Focus the optic on the gold.</p>
<p><b>Lines</b>: SZ is scanned (fly, step 0.02 mm), ST / SN / SRn / SRz only move between lines. <i>Measurement
plan…</i> lists them: A at SRn 120, B with the frame turned ±45° (a diamond: its diagonal edges give the horizontal
position on the SZ axis), C the diamond at several SRz. One file per SRn / SRz with ST stepped is the natural way;
single lines and an ST × SZ overview map (coarse ST steps) or an SZ × SRn sweep may be added: every line is fitted.
Method and accuracy: docs/pdf/GoldFrame_calibration_report_*.pdf.</p>
"""

PLAN_HELP = """
<p>Every row is one SZ fly line: set SRn, SRz, ST and SN, then scan SZ from <i>SZ from</i> to <i>SZ to</i>
(step 0.02 mm). The lines are placed with the newest configuration and the frame where it is taken to be;
a few tenths of a mm off is fine (the diamond is 2.8 mm across). A file per SRn / SRz (ST stepped over the
group's rows, SZ fast) is the natural way to record them.</p>
"""

SN_HELP = """
<p><b>Optional.</b> At each row: set SRn, SRz, ST, SZ (the middle of the frame's right bar), run an SN scan with ST
following (ΔST = −ΔSN) and enter the <b>ST and SN at the intensity peak</b> (the gold under the beam at the analyzer
focus). These points add the depth of the SRz axis seen by the analyzer to the fit; rows without a measured SN are
not used. <i>Expected SN</i>: where the newest configuration puts the peak.</p>
"""


def _fmt(value, digits=4) -> str:
    return "" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"


def _item(text, editable=False, right=True):
    item = QtWidgets.QTableWidgetItem(text)
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if right:
        item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
    return item


def _number(text: str):
    try:
        value = float(text.strip())
    except (ValueError, AttributeError):
        return None
    return value if np.isfinite(value) else None


class PlanDialog(QtWidgets.QDialog):
    """The SZ lines to measure, with the motor-range and anti-collision checks; CSV export."""

    COLUMNS = ("group", "SRn", "SRz", "ST", "SN", "SZ from", "SZ to", "check")

    def __init__(self, guide: Setup, record, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gold frame – measurement plan (SZ lines)")
        self.resize(900, 760)
        self.plan = survey_plan(guide)
        self.points = sn_point_plan(guide)
        text = QtWidgets.QLabel(PLAN_HELP + "<p>" + "<br>".join(f"<b>{g}</b>: {t}" for g, t in GROUP_TEXT.items())
                                + f"</p><p>Placed with {record.label}.</p>")
        text.setWordWrap(True)
        table = QtWidgets.QTableWidget(len(self.plan), len(self.COLUMNS))
        table.setHorizontalHeaderLabels(self.COLUMNS)
        table.verticalHeader().setVisible(False)
        layout = SampleLayout(STANDARD_PLATE, [Sample("gold frame", guide.frame.u, guide.frame.v, guide.frame.outer,
                                                      guide.frame.outer, guide.frame.height)])
        geo = record.collision_geometry()
        problems = 0
        for r, p in enumerate(self.plan):
            issues = []
            for sz in (p.sz_from, p.sz_to):
                m = replace(p.motors(guide.config.pi_center), sz=sz)
                issues += out_of_range(m)
                hit = collisions(guide.model, m, layout, geo, [0.0])
                issues += [f"collision: {', '.join(hit)}"] if hit else []
            issues = list(dict.fromkeys(issues))
            problems += bool(issues)
            cells = [p.group, f"{p.srn:.1f}", f"{p.srz:.1f}", f"{p.st:.4f}", f"{p.sn:.4f}", f"{p.sz_from:.4f}",
                     f"{p.sz_to:.4f}", "; ".join(issues) or "ok"]
            for c, text_ in enumerate(cells):
                item = _item(text_, right=c not in (0, 7))
                if c == 7 and issues:
                    item.setForeground(Qt.red)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        summary = QtWidgets.QLabel(f"{len(self.plan)} SZ lines in {len({(p.srn, p.srz) for p in self.plan})} SRn / SRz "
                                   "settings" + (f"; <b style='color:#b00020'>{problems} line(s) out of range or "
                                                 "colliding</b>" if problems else "; all within the motor ranges, "
                                                 "no collision in the model."))
        export = QtWidgets.QPushButton("Save as CSV…")
        export.clicked.connect(self.export)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(export)
        buttons.addWidget(close)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(text)
        lay.addWidget(table, 1)
        lay.addWidget(summary)
        lay.addLayout(buttons)

    def export(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save the plan", "gold_frame_plan.csv", "CSV (*.csv)")
        if path:
            write_plan_csv(path, self.plan, self.points)


class SNPointsDialog(QtWidgets.QDialog):
    """Optional SN focus points at other SRz: planned positions, the measured ST / SN at the peak."""

    COLUMNS = ("use", "SRn", "SRz", "ST at peak", "SZ", "SN at peak", "expected SN", "after the fit (µm)")

    def __init__(self, guide: Setup, points: list[SNPoint], residuals=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gold frame – SN at other SRz (optional)")
        self.resize(860, 520)
        self.guide = guide
        text = QtWidgets.QLabel(SN_HELP)
        text.setWordWrap(True)
        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        planned = QtWidgets.QPushButton("Fill the planned positions")
        planned.clicked.connect(self.fill_planned)
        add = QtWidgets.QPushButton("Add row")
        add.clicked.connect(lambda: self._add(None))
        remove = QtWidgets.QPushButton("Remove row")
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        load = QtWidgets.QPushButton("Load CSV…")
        load.clicked.connect(self.load_csv)
        ok = QtWidgets.QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row = QtWidgets.QHBoxLayout()
        for b in (planned, add, remove, load):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(text)
        lay.addWidget(self.table, 1)
        lay.addLayout(row)
        for k, p in enumerate(points):
            self._add(p, None if residuals is None or k >= len(residuals) else residuals[k])

    def _expected(self, srn, srz, st, sz):
        """SN the guide expects at the peak for this SRn / SRz / SZ (ST following SN)."""
        from ..gold_frame import SNPoint as P, sn_focus_error
        if None in (srn, srz, st, sz):
            return None
        p = P(srn, srz, st, sz, 0.0)
        # the error is linear in SN with slope 1 (ST following): SN at the focus = 0 - error at SN 0
        e0 = sn_focus_error(self.guide, p)
        e1 = sn_focus_error(self.guide, replace(p, sn=1.0, st=st - 1.0))
        return -e0 / (e1 - e0) if e1 != e0 else None

    def _add(self, p: SNPoint | None, residual=None, measured=True):
        r = self.table.rowCount()
        self.table.insertRow(r)
        use = QtWidgets.QTableWidgetItem()
        use.setFlags(use.flags() | Qt.ItemIsUserCheckable)
        use.setCheckState(Qt.Checked if (p is None or p.use) else Qt.Unchecked)
        self.table.setItem(r, 0, use)
        values = [p.srn, p.srz, p.st, p.sz, p.sn if measured else None] if p else [120.0, 0.0, None, None, None]
        for c, v in enumerate(values, 1):
            self.table.setItem(r, c, _item(_fmt(v, 1 if c in (1, 2) else 4), editable=True))
        exp = self._expected(*values[:4]) if p else None
        self.table.setItem(r, 6, _item(_fmt(exp)))
        self.table.setItem(r, 7, _item("" if residual is None else f"{residual * 1000:+.1f}"))

    def fill_planned(self):
        self.table.setRowCount(0)
        for p in sn_point_plan(self.guide):
            self._add(p, measured=False)

    def load_csv(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "SN points (columns srn, srz, st, sz, sn)", "",
                                                        "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            points = read_sn_points(path)
        except (OSError, ValueError, IndexError) as exc:
            QtWidgets.QMessageBox.warning(self, "SN points", f"Could not read the file:\n\n{exc}")
            return
        self.table.setRowCount(0)
        for p in points:
            self._add(p)

    def points(self) -> list[SNPoint]:
        out = []
        for r in range(self.table.rowCount()):
            vals = [_number(self.table.item(r, c).text()) if self.table.item(r, c) else None for c in range(1, 6)]
            if None in vals:
                continue  # not measured (yet)
            out.append(SNPoint(*vals, use=self.table.item(r, 0).checkState() == Qt.Checked))
        return out


class GoldFrameWindow(QtWidgets.QMainWindow):
    def __init__(self, store: CalibrationStore | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment – gold-frame calibration")
        self.resize(1560, 940)
        self.store = store or CalibrationStore()
        self.result = None
        self.files: list[tuple[str, object]] = []  # (path, Scan)
        self.sn_points: list[SNPoint] = []

        # -- data ------------------------------------------------------------------------------------------
        plan = QtWidgets.QPushButton("Measurement plan…")
        plan.clicked.connect(self.show_plan)
        add = QtWidgets.QPushButton("Add files…")
        add.clicked.connect(self.choose_files)
        remove = QtWidgets.QPushButton("Remove")
        remove.clicked.connect(self.remove_selected)
        clear = QtWidgets.QPushButton("Clear")
        clear.clicked.connect(self.clear_files)
        self.file_table = QtWidgets.QTableWidget(0, 7)
        self.file_table.setHorizontalHeaderLabels(["file", "lines", "SRn", "SRz", "ST", "SN", "kind"])
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.file_table.setMinimumHeight(220)
        self.file_summary = QtWidgets.QLabel("No file loaded.")
        self.file_summary.setWordWrap(True)
        data = QtWidgets.QGroupBox("Data: SZ lines over the gold frame")
        dv = QtWidgets.QVBoxLayout(data)
        row = QtWidgets.QHBoxLayout()
        for b in (plan, add, remove, clear):
            row.addWidget(b)
        dv.addLayout(row)
        dv.addWidget(self.file_table)
        dv.addWidget(self.file_summary)

        # -- settings --------------------------------------------------------------------------------------
        self.normalize = QtWidgets.QCheckBox("Divide by the diode current (I0)")
        self.normalize.toggled.connect(lambda _: self.reload())
        self.sn_auto = QtWidgets.QCheckBox("SN of a file at SRn 120 / SRz 0")
        self.sn_auto.setChecked(True)
        self.sn_gold = spin(0.0, -30, 65, 4, 0.01)
        self.sn_gold.setEnabled(False)
        self.sn_auto.toggled.connect(lambda on: (self.sn_gold.setEnabled(not on), self._data_changed()))
        self.height = spin(0.05, 0, 3, 3, 0.01)
        self.frame_u = spin(0.0, -5, 5, 3, 0.05)
        self.frame_v = spin(0.0, -5, 5, 3, 0.05)
        self.outer = spin(2.0, 0.1, 10, 3, 0.1)
        self.inner = spin(1.0, 0.05, 10, 3, 0.1)
        self.fit_tilt = QtWidgets.QCheckBox("Fit the tilt of the gold face")
        self.fit_tilt.setChecked(True)
        self.fit_scales = QtWidgets.QCheckBox("Fit the ST / SZ scales")
        self.fit_scales.setChecked(True)
        self.optic = QtWidgets.QComboBox()
        self.optic.addItem("capillary", "capillary")
        self.optic.addItem("zone plate + OSA", "zone_plate")
        self.optic.currentIndexChanged.connect(lambda _: self._show_newest())
        self.optic_auto = QtWidgets.QCheckBox("recorded in a file at SRn 120 / SRz 0, else kept")
        self.optic_auto.setChecked(True)
        self.optic_position = spin(0.0, -1000, 1000, 3, 0.01, "")
        self.optic_position.setEnabled(False)
        self.optic_auto.toggled.connect(lambda on: self.optic_position.setEnabled(not on))

        def pair(a, b):
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(a)
            h.addWidget(b)
            return w

        settings = QtWidgets.QGroupBox("Settings")
        form = QtWidgets.QFormLayout(settings)
        form.addRow("SN gold (gold top at the analyzer focus)", pair(self.sn_auto, self.sn_gold))
        form.addRow("Gold height above the riser top", self.height)
        form.addRow("Frame centre on the plate x, y", pair(self.frame_u, self.frame_v))
        form.addRow("Frame outer / hole size", pair(self.outer, self.inner))
        form.addRow("", pair(self.fit_tilt, self.fit_scales))
        form.addRow("", self.normalize)
        form.addRow("Optic", self.optic)
        form.addRow("Optic position at the gold focus", pair(self.optic_auto, self.optic_position))
        self.newest = QtWidgets.QLabel()
        self.newest.setWordWrap(True)
        form.addRow("Compared with / lines placed with", self.newest)

        help_box = QtWidgets.QTextBrowser()
        help_box.setHtml(HELP_HTML)
        help_box.setMaximumHeight(150)
        inputs = QtWidgets.QWidget()
        iv = QtWidgets.QVBoxLayout(inputs)
        iv.addWidget(help_box)
        iv.addWidget(data)
        iv.addWidget(settings)
        iv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(inputs)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # -- actions (always in sight) ---------------------------------------------------------------------
        self.fit_button = QtWidgets.QPushButton("Fit")
        self.fit_button.setStyleSheet("font-weight: bold;")
        self.fit_button.clicked.connect(self.fit)
        self.sn_button = QtWidgets.QPushButton("SN at other SRz (optional)…")
        self.sn_button.clicked.connect(self.edit_sn_points)
        example = QtWidgets.QPushButton("Load a simulated example")
        example.setToolTip("Simulate the planned lines over a frame with small known faults and load them")
        example.clicked.connect(self.load_example)
        simulator = QtWidgets.QPushButton("Open the simulator…")
        simulator.clicked.connect(self.open_simulator)
        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("comment saved with the configuration (date, sample, reason…)")
        self.save_button = QtWidgets.QPushButton("Save as new configuration")
        self.save_button.setStyleSheet("font-weight: bold;")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.fit_button, 2)
        buttons.addWidget(self.sn_button, 2)
        buttons.addWidget(example, 1)
        buttons.addWidget(simulator, 1)
        save_box = QtWidgets.QGroupBox("Save the configuration")
        sv = QtWidgets.QHBoxLayout(save_box)
        sv.addWidget(self.comment, 1)
        sv.addWidget(self.save_button)
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(scroll, 1)
        lv.addLayout(buttons)
        lv.addWidget(save_box)
        left.setMinimumWidth(max(660, inputs.sizeHint().width() + 30))

        # -- results ---------------------------------------------------------------------------------------
        self.figure = Figure(figsize=(9, 8), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "fitted", "±", "newest configuration", "change"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.details = QtWidgets.QTextBrowser()
        results = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(results)
        rv.addWidget(QtWidgets.QLabel("<b>Configuration</b> (mm)"))
        rv.addWidget(self.table, 3)
        rv.addWidget(QtWidgets.QLabel("<b>Fit details</b>"))
        rv.addWidget(self.details, 2)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.canvas, "Data")
        self.tabs.addTab(results, "Results")

        split = QtWidgets.QSplitter()
        split.addWidget(left)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        split.setSizes([700, 860])
        self.setCentralWidget(split)
        self._show_newest()
        self._draw()

    # -- helpers ------------------------------------------------------------------------------------------
    def newest_record(self):
        return self.store.latest(self.optic.currentData())

    def frame(self) -> GoldFrame:
        return GoldFrame(outer=self.outer.value(), inner=self.inner.value(), height=self.height.value(),
                         u=self.frame_u.value(), v=self.frame_v.value())

    def guide(self) -> Setup:
        """The newest configuration with the frame where it is taken to be: where the lines are placed."""
        return Setup(self.newest_record().config, self.frame())

    def scans(self) -> list:
        return [scan for _, scan in self.files]

    def _show_newest(self):
        r = self.newest_record()
        self.newest.setText(f"{r.label}" + (f" ({r.path.name})" if r.path else ""))
        if self.result is not None:
            self._show_result()

    def _flat_sn(self):
        ref = self.newest_record().config.srn_ref
        for scan in self.scans():
            if np.allclose(scan.base["srn"], ref) and np.allclose(scan.base["srz"], 0):
                return float(scan.base["sn"][0])
        return None

    def _data_changed(self):
        self.result = None
        self.save_button.setEnabled(False)
        if self.sn_auto.isChecked():
            sn = self._flat_sn()
            if sn is not None:
                self.sn_gold.setValue(sn)
        self._fill_file_table()
        self.table.setRowCount(0)
        self.details.clear()
        self._draw()

    def _fill_file_table(self):
        self.file_table.setRowCount(len(self.files))
        lines = 0
        for r, (path, scan) in enumerate(self.files):
            def rng(m, d):
                v = scan.motor_grid(m)
                lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
                return f"{lo:.{d}f}" if hi - lo < 10 ** -d else f"{lo:.{d}f} … {hi:.{d}f}"
            lines += len(scan.x)
            kind = ("overview" if is_overview(scan, self.newest_record().config.srn_ref)
                    else "SRn sweep" if scan.kind == "srn_sz" else "SZ lines" if "sz" in scan.kind else scan.kind)
            cells = [Path(path).name, str(len(scan.x)), rng("srn", 1), rng("srz", 1), rng("st", 3), rng("sn", 3), kind]
            for c, text in enumerate(cells):
                item = _item(text, right=c in (1,))
                item.setToolTip(path)
                self.file_table.setItem(r, c, item)
        self.file_table.resizeColumnsToContents()
        sn = len([p for p in self.sn_points if p.use])
        self.file_summary.setText(f"{len(self.files)} file(s), {lines} lines" + (f"; {sn} SN point(s)" if sn else "")
                                  if self.files else "No file loaded.")
        self.sn_button.setText("SN at other SRz (optional)…" + (f"  [{sn}]" if sn else ""))

    def _draw(self):
        self.figure.clear()
        if not self.files:
            ax = self.figure.add_subplot(111)
            ax.axis("off")
            ax.text(0.5, 0.5, "Add the measured files (left), then press Fit.\nMeasurement plan…: the lines to measure.",
                    ha="center", va="center", fontsize=12)
            self.canvas.draw_idle()
            return
        overlay = {"fit": self.result.setup} if self.result is not None else None
        draw_survey(self.figure, self.scans(), overlay, self.newest_record().config.srn_ref, stacked=True)
        self.canvas.draw_idle()

    # -- data actions -------------------------------------------------------------------------------------
    def show_plan(self):
        dialog = PlanDialog(self.guide(), self.newest_record(), self)
        dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()

    def choose_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add measured files", "", FILE_FILTER)
        if paths:
            self.add_files(paths)

    def add_files(self, paths) -> int:
        added, errors = 0, []
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for path in paths:
                if any(p == str(path) for p, _ in self.files):
                    continue
                try:
                    self.files.append((str(path), load_map([str(path)], normalize=self.normalize.isChecked())))
                    added += 1
                except (OSError, KeyError, ValueError, ImportError) as exc:
                    errors.append(f"{Path(path).name}: {exc}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if errors:
            QtWidgets.QMessageBox.warning(self, "Gold frame calibration", "Could not read:\n\n" + "\n".join(errors))
        self._data_changed()
        return added

    def reload(self):
        paths = [p for p, _ in self.files]
        self.files = []
        self.add_files(paths)

    def remove_selected(self):
        rows = sorted({i.row() for i in self.file_table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.files[r]
        self._data_changed()

    def clear_files(self):
        self.files = []
        self._data_changed()

    def edit_sn_points(self):
        residuals = self.result.sn_residuals if self.result is not None else None
        dialog = SNPointsDialog(self.guide(), self.sn_points, residuals, self)
        ok = dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()
        if ok:
            self.sn_points = dialog.points()
            self._data_changed()

    # -- fit / save ---------------------------------------------------------------------------------------
    def fit(self):
        if not self.files:
            QtWidgets.QMessageBox.information(self, "Gold frame calibration", "Add the measured files first.")
            return
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("Fitting every line…")
        QtWidgets.QApplication.processEvents()
        try:
            self.result = fit_global(self.scans(), self.sn_gold.value(), self.frame(), self.newest_record().config,
                                     free_tilt=self.fit_tilt.isChecked(), free_scales=self.fit_scales.isChecked(),
                                     sn_points=self.sn_points)
        except (ValueError, np.linalg.LinAlgError) as exc:
            self.result = None
            QtWidgets.QApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()
            QtWidgets.QMessageBox.warning(self, "Gold frame calibration", f"The fit failed:\n\n{exc}")
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        self.statusBar().showMessage("Fit done: check the residuals and the drawn edges, then save.", 10000)
        self.save_button.setEnabled(True)
        self._show_result()
        self._draw()
        self.tabs.setCurrentIndex(1)

    def _show_result(self):
        res, old = self.result, self.newest_record().config
        c = res.setup.config
        rows = list(CONFIG_ARGS) + [k for k in EXTRA if k in res.values]
        self.table.setRowCount(len(rows))
        for i, k in enumerate(rows):
            if k in CONFIG_ARGS:
                new, before = getattr(c, k), getattr(old, k)
                cells = [LABELS[k] + ("  (kept)" if k in res.kept else ""), _fmt(new), _fmt(res.sigma.get(k)),
                         _fmt(before), f"{new - before:+.4f}"]
            else:
                cells = [PARAM_TEXT[k], _fmt(res.values[k]), _fmt(res.sigma[k]), "", ""]
            for j, text in enumerate(cells):
                self.table.setItem(i, j, _item(text, right=j > 0))
        html = [f"<p><b>{res.lines_used}</b> of {res.lines_total} lines with gold edges used, {res.edges} edges, "
                f"edge rms <b>{res.rms * 1000:.1f} µm</b>.</p><table cellspacing=0 cellpadding=2>"
                "<tr><th align=left>file</th><th>lines used</th><th>rms (µm)</th></tr>"]
        for (path, _), (used, total, rms) in zip(self.files, res.per_scan):
            html.append(f"<tr><td>{Path(path).name}</td><td align=center>{used}/{total}</td>"
                        f"<td align=right>{_fmt(rms * 1000, 1)}</td></tr>")
        html.append("</table>")
        used_points = [(p, r) for p, r in zip(self.sn_points, res.sn_residuals) if r is not None]
        if used_points:
            html.append("<p><b>SN points</b> (after the fit, distance from the analyzer focus): "
                        + ", ".join(f"SRz {p.srz:g}: {r * 1000:+.1f} µm" for p, r in used_points) + "</p>")
        for k, why in res.kept.items():
            if k in ("srn_axis_u", "srz_offset_t", "frame.tilt_u"):
                html.append(f"<p style='color:#8a5a00'>{PARAM_TEXT[k]}: kept ({why}).</p>")
        for note in res.notes:
            html.append(f"<p style='color:#b00020'>! {note}</p>")
        html.append("<p style='color:#555'>Good fit: edge rms of a few µm, few lines left out (lines where the frame is "
                    "out of the line or not seen), tilt ≲ 2°, scales within 0.5 % of 1, and the fitted edges (orange, Data "
                    "tab) on the gold edges. The frame is taken to be at the given place on the plate: a mounting error "
                    "of the frame goes into ST0 / SZ0 and the axes.</p>")
        self.details.setHtml("".join(html))

    def save(self):
        if self.result is None:
            return
        newest = self.newest_record()
        optic_pos = None if self.optic_auto.isChecked() else self.optic_position.value()
        record = calibration_record(self.result, self.scans(), self.sn_gold.value(), newest, self.optic.currentData(),
                                    optic_pos, self.comment.text(), {"files": [p for p, _ in self.files]},
                                    self.sn_points)
        saved = self.store.save(record)
        self._show_newest()
        QtWidgets.QMessageBox.information(
            self, "Gold frame calibration",
            f"Saved as\n{saved.path}\n\nQuickAlignment loads it at the next start with the {saved.optic_name}.")

    # -- try it -------------------------------------------------------------------------------------------
    def load_example(self):
        """The planned lines simulated over a frame with known faults, written as files and loaded."""
        config = self.newest_record().config
        guide = Setup(config, GoldFrame(height=0.05))
        m = guide.frame_motors()
        truth = Setup(replace(config, srn_axis_u=config.srn_axis_u + 0.1, srz_offset_n=config.srz_offset_n + 0.2),
                      GoldFrame(height=0.05, u=0.15, v=-0.1, rotation=1.5, tilt_u=1.0),
                      Instrument(counts=3000, scale_st_ref=m.st, scale_sz_ref=m.sz))
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("Simulating the planned lines…")
        QtWidgets.QApplication.processEvents()
        try:
            folder = Path(tempfile.mkdtemp(prefix="gold_frame_example_"))
            scans = simulated_measurement(guide, truth, overview=True, rng=np.random.default_rng(0))
            paths = [str(save_scan(scan, folder / key, optic=60.0)) for key, scan in scans.items()]
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.files = []
        self.add_files(paths)
        self.sn_auto.setChecked(False)
        self.sn_gold.setValue(truth.frame_motors().sn)
        c = truth.config
        self.statusBar().showMessage(
            f"Simulated example in {folder}: frame at (0.15, −0.10) mm, turned 1.5°, face tilted 1°; true values with "
            f"the frame taken at the plate centre: ST0 {c.st0 - 0.15:.4f}, SZ0 {c.sz0 + 0.1:.4f}, SRn axis "
            f"({c.srn_axis_u - 0.15:.4f}, {c.srn_axis_v + 0.1:.4f}), SRz offsets ({c.srz_offset_t - 0.15:.4f}, "
            f"{c.srz_offset_n:.4f}). Press Fit.")

    def open_simulator(self):
        subprocess.Popen([sys.executable, str(ROOT / "GoldFrameSimulator.py")])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    install_excepthook("Gold frame calibration")
    win = GoldFrameWindow()
    win.show()
    return exec_app(app)


__all__ = ["GoldFrameWindow", "PlanDialog", "SNPointsDialog", "main"]
