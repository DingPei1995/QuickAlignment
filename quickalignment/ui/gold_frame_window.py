"""Gold-frame calibration window: load the three SPEM maps, fit them, save the configuration.

1. Load the maps (ANTARES .nxs: one 2-D map, or several line files, one per angle; or .npz from the
   simulator): map 1 ST x SZ, map 2 SZ x SRn, map 3 ST x SRz. Maps 2 and 3 may be left out: those axes
   are then kept from the newest configuration.
2. Settings: SN with the gold top at the analyzer focus (from the SN scan; default the SN of map 1),
   gold height, where the frame is taken to be on the plate, the optic and its position.
3. Fit: the constants with their uncertainties, the change from the newest configuration, and the
   maps with the fitted edges drawn over them.
4. Save: a new configuration in configs/ that QuickAlignment loads at start-up.
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

from ._qt import QtCore, QtWidgets, Signal, exec_app, install_excepthook
from .stage_panel import spin
from ..calibration import CalibrationStore
from ..gold_frame import GoldFrame, Instrument, Setup, calibrate
from ..gold_frame_cli import CONFIG_ARGS, calibration_record, load_map, nominal_setup
from ..gold_frame_plot import draw_map

Qt = QtCore.Qt
ROOT = Path(__file__).resolve().parent.parent.parent

STEPS = (
    ("step1", "Map 1: ST × SZ  (SRn 120, SRz 0)", ("st_sz",), True),
    ("step2", "Map 2: SZ line × SRn  (ST at the frame centre)", ("srn_sz",), False),
    ("step3", "Map 3: ST line × SRz  (SRn 120, SZ through the hole)", ("srz_st", "srz_surface"), False),
)
LABELS = {
    "st0": "ST0", "sz0": "SZ0", "sn_f": "SN_f", "srn_axis_u": "SRn axis x", "srn_axis_v": "SRn axis y",
    "srz_offset_t": "SRz offset ST", "srz_offset_n": "SRz offset SN",
}
FILE_FILTER = "SPEM scans (*.nxs *.h5 *.hdf5 *.npz);;All files (*)"

HELP_HTML = """
<p><b>Before the maps</b> (SRn 120, SRz 0, PIX = PIY = 150): find the gold, run an SN scan on a gold bar with ST
following (ΔST = −ΔSN): the peak is <i>SN gold</i>, its width the analyzer acceptance. The same scan on the riser
gives the gold height (difference of the peaks). Focus the optic on the gold.</p>
<p><b>Map 1</b> ST × SZ, ±2 mm around the frame, SN = SN gold. <b>Map 2</b> ST at the frame centre, SZ ±2.5 mm,
SRn 60…180° (2° steps). <b>Map 3</b> SRn 120, SZ at the frame centre (through the hole), ST ±3.5 mm,
SRz −25…+10° (1° steps), best with SN following ST along the turned surface (ΔSN = ΔST · tan(−SRz)).</p>
<p>A map is one 2-D file, or several line files (one per SRn / SRz): select them together.
Method and accuracy: docs/pdf/GoldFrame_calibration_report_*.pdf.</p>
"""


def _fmt(value, digits=4) -> str:
    return "" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"


class MapSlot(QtWidgets.QGroupBox):
    """One map: file(s), what was read, Load / Clear."""

    changed = Signal()

    def __init__(self, key: str, title: str, kinds: tuple, required: bool, normalize):
        super().__init__(title + ("" if required else "  (optional)"))
        self.key, self.kinds, self.required, self._normalize = key, kinds, required, normalize
        self.scan = None
        self.paths: list[str] = []
        self.files = QtWidgets.QLineEdit()
        self.files.setReadOnly(True)
        self.files.setPlaceholderText("no file loaded")
        load = QtWidgets.QPushButton("Load…")
        load.clicked.connect(self.choose)
        clear = QtWidgets.QPushButton("Clear")
        clear.clicked.connect(self.clear)
        self.info = QtWidgets.QLabel("")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #555;")
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.files, 1)
        row.addWidget(load)
        row.addWidget(clear)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.info)

    def choose(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, f"Load {self.title()}", "", FILE_FILTER)
        if paths:
            self.load(paths)

    def load(self, paths: list[str]) -> bool:
        try:
            QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
            scan = load_map(list(paths), normalize=self._normalize())
        except (OSError, KeyError, ValueError, ImportError) as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.warning(self, "Gold frame calibration", f"Could not read the map:\n\n{exc}")
            return False
        finally:
            while QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()
        if scan.kind not in self.kinds:
            QtWidgets.QMessageBox.warning(
                self, "Gold frame calibration",
                f"This looks like a {scan.kind} map (scanned: {', '.join(map(str, scan.info.get('kind_from', [])))}),"
                f" not {' / '.join(self.kinds)}. Check that it is the right file for {self.title()}.")
        self.scan, self.paths = scan, list(paths)
        self.files.setText("; ".join(Path(p).name for p in paths))
        self.files.setToolTip("\n".join(paths))
        self.info.setText(self._describe(scan))
        self.changed.emit()
        return True

    def reload(self):
        if self.paths:
            self.load(self.paths)

    def clear(self):
        self.scan, self.paths = None, []
        self.files.clear()
        self.info.setText("")
        self.changed.emit()

    @staticmethod
    def _describe(scan) -> str:
        fixed = ", ".join(f"{m.upper()} {scan.base[m][0]:.3f}" for m in ("st", "sn", "sz", "srn", "srz")
                          if np.ptp(scan.base[m]) == 0 and np.all(scan.slope[m] == 0))
        text = (f"{scan.kind}: {len(scan.x)} lines × {len(scan.y)} points; "
                f"x {scan.x[0]:.3f} … {scan.x[-1]:.3f}, y {scan.y[0]:.3f} … {scan.y[-1]:.3f}")
        if fixed:
            text += f"<br>fixed: {fixed}"
        if scan.info.get("channel"):
            text += f"<br>intensity: {scan.info['channel']}"
        if scan.info.get("optic_position") is not None:
            text += f"; optic {scan.info['optic_position']:.3f}"
        return text


class GoldFrameWindow(QtWidgets.QMainWindow):
    def __init__(self, store: CalibrationStore | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment – gold-frame calibration")
        self.resize(1560, 940)
        self.store = store or CalibrationStore()
        self.result = None

        # -- left: data and settings ------------------------------------------------------------------
        self.normalize = QtWidgets.QCheckBox("Divide by the diode current (I0)")
        self.slots = {key: MapSlot(key, title, kinds, required, self.normalize.isChecked)
                      for key, title, kinds, required in STEPS}
        for slot in self.slots.values():
            slot.changed.connect(self._data_changed)
        self.normalize.toggled.connect(lambda _: [s.reload() for s in self.slots.values()])

        self.sn_from_map = QtWidgets.QCheckBox("SN of map 1")
        self.sn_from_map.setChecked(True)
        self.sn_gold = spin(0.0, -30, 65, 4, 0.01)
        self.sn_gold.setEnabled(False)
        self.sn_from_map.toggled.connect(lambda on: self.sn_gold.setEnabled(not on))
        self.height = spin(0.05, 0, 3, 3, 0.01)
        self.frame_u = spin(0.0, -5, 5, 3, 0.05)
        self.frame_v = spin(0.0, -5, 5, 3, 0.05)
        self.outer = spin(2.0, 0.1, 10, 3, 0.1)
        self.inner = spin(1.0, 0.05, 10, 3, 0.1)
        self.fit_tilt = QtWidgets.QCheckBox("Fit the tilt of the gold face (map 3)")
        self.fit_tilt.setChecked(True)
        self.optic = QtWidgets.QComboBox()
        self.optic.addItem("capillary", "capillary")
        self.optic.addItem("zone plate + OSA", "zone_plate")
        self.optic.currentIndexChanged.connect(lambda _: self._show_newest())
        self.optic_from_map = QtWidgets.QCheckBox("from map 1 (zone plate channel), else kept")
        self.optic_from_map.setChecked(True)
        self.optic_position = spin(0.0, -1000, 1000, 3, 0.01, "")
        self.optic_position.setEnabled(False)
        self.optic_from_map.toggled.connect(lambda on: self.optic_position.setEnabled(not on))

        def pair(a, b):
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(a)
            h.addWidget(b)
            return w

        settings = QtWidgets.QGroupBox("Settings")
        form = QtWidgets.QFormLayout(settings)
        form.addRow("SN gold (gold top at the analyzer focus)", pair(self.sn_from_map, self.sn_gold))
        form.addRow("Gold height above the riser top", self.height)
        form.addRow("Frame centre on the plate x, y", pair(self.frame_u, self.frame_v))
        form.addRow("Frame outer / hole size", pair(self.outer, self.inner))
        form.addRow("", self.fit_tilt)
        form.addRow("", self.normalize)
        form.addRow("Optic", self.optic)
        form.addRow("Optic position at the gold focus", pair(self.optic_from_map, self.optic_position))
        self.newest = QtWidgets.QLabel()
        self.newest.setWordWrap(True)
        form.addRow("Compared with", self.newest)

        self.fit_button = QtWidgets.QPushButton("Fit")
        self.fit_button.setStyleSheet("font-weight: bold;")
        self.fit_button.clicked.connect(self.fit)
        example = QtWidgets.QPushButton("Load a simulated example")
        example.setToolTip("Simulate the three maps of a frame with small known faults and load them (to try the program)")
        example.clicked.connect(self.load_example)
        simulator = QtWidgets.QPushButton("Open the simulator…")
        simulator.clicked.connect(self.open_simulator)
        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("comment saved with the configuration (date, sample, reason…)")
        self.save_button = QtWidgets.QPushButton("Save as new configuration")
        self.save_button.setStyleSheet("font-weight: bold;")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)

        help_box = QtWidgets.QTextBrowser()
        help_box.setHtml(HELP_HTML)
        help_box.setMaximumHeight(150)

        inputs = QtWidgets.QWidget()
        iv = QtWidgets.QVBoxLayout(inputs)
        iv.addWidget(help_box)
        for slot in self.slots.values():
            iv.addWidget(slot)
        iv.addWidget(settings)
        iv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(inputs)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # the actions stay in sight below the inputs
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.fit_button, 2)
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

        # -- right: maps and results --------------------------------------------------------------------
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
        rv.addWidget(self.table, 2)
        rv.addWidget(QtWidgets.QLabel("<b>Fit details</b>"))
        rv.addWidget(self.details, 3)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.canvas, "Maps")
        self.tabs.addTab(results, "Results")

        split = QtWidgets.QSplitter()
        split.addWidget(left)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        split.setSizes([700, 800])
        self.setCentralWidget(split)
        self._show_newest()
        self._draw()

    # -- helpers ------------------------------------------------------------------------------------------
    def newest_record(self):
        return self.store.latest(self.optic.currentData())

    def _show_newest(self):
        r = self.newest_record()
        self.newest.setText(f"{r.label}" + (f" ({r.path.name})" if r.path else ""))
        if self.result is not None:
            self._show_result()

    def _data_changed(self):
        self.result = None
        self.save_button.setEnabled(False)
        s1 = self.slots["step1"].scan
        if s1 is not None and self.sn_from_map.isChecked():
            self.sn_gold.setValue(float(s1.base["sn"][0]))
        self.table.setRowCount(0)
        self.details.clear()
        self._draw()

    def scans(self) -> dict:
        return {k: s.scan for k, s in self.slots.items() if s.scan is not None}

    def frame(self) -> GoldFrame:
        return GoldFrame(outer=self.outer.value(), inner=self.inner.value(), height=self.height.value(),
                         u=self.frame_u.value(), v=self.frame_v.value())

    def _draw(self):
        self.figure.clear()
        scans = self.scans()
        if not scans:
            ax = self.figure.add_subplot(111)
            ax.axis("off")
            ax.text(0.5, 0.5, "Load the maps (left), then press Fit.", ha="center", va="center", fontsize=12)
            self.canvas.draw_idle()
            return
        n = len(scans)
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        overlay = {"fit": self.result.setup} if self.result is not None else None
        for k, (key, scan) in enumerate(scans.items()):
            ax = self.figure.add_subplot(rows, cols, k + 1)
            title = dict((s[0], s[1]) for s in STEPS)[key]
            try:
                draw_map(ax, scan, overlay, title)
            except (ValueError, np.linalg.LinAlgError):
                draw_map(ax, scan, None, title)
        self.canvas.draw_idle()

    # -- actions ------------------------------------------------------------------------------------------
    def fit(self):
        scans = self.scans()
        if "step1" not in scans:
            QtWidgets.QMessageBox.information(self, "Gold frame calibration", "Load map 1 (ST × SZ) first.")
            return
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("Fitting…")
        QtWidgets.QApplication.processEvents()
        try:
            self.result = calibrate(scans["step1"], self.sn_gold.value(), self.frame(), scans.get("step2"),
                                    scans.get("step3"), base=self.newest_record().config,
                                    free_tilt=self.fit_tilt.isChecked())
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
        sigma = {"sz0": res.step1.sigma.get("sz_c"),
                 "st0": (res.step3.sigma["st0"] if res.step3 else res.step1.sigma.get("st_c"))}
        if res.step2:
            sigma.update({"srn_axis_u": res.step2.sigma["srn_axis_u"], "srn_axis_v": res.step2.sigma["srn_axis_v"]})
        if res.step3:
            sigma.update({"srz_offset_t": res.step3.sigma["srz_offset_t"], "srz_offset_n": res.step3.sigma["srz_offset_n"]})
        kept = set()
        if not res.step2:
            kept |= {"srn_axis_u", "srn_axis_v"}
        if not res.step3:
            kept |= {"srz_offset_t", "srz_offset_n"}
        self.table.setRowCount(len(CONFIG_ARGS))
        for i, k in enumerate(CONFIG_ARGS):
            new, before = getattr(c, k), getattr(old, k)
            cells = [LABELS[k] + ("  (kept)" if k in kept else ""), _fmt(new), _fmt(sigma.get(k)), _fmt(before),
                     f"{new - before:+.4f}"]
            for j, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                if j:
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(i, j, item)

        v1 = res.step1.values
        html = [f"<p><b>Map 1</b>: frame centre ST {v1['st_c']:.4f}, SZ {v1['sz_c']:.4f}; in-plane rotation "
                f"{v1['rotation']:.2f}°; scales ST {v1['scale_st']:.4f}, SZ {v1['scale_sz']:.4f}; shear {v1['shear']:.2f}°; "
                f"edge rms {res.step1.rms * 1000:.1f} µm ({res.step1.n} edge points).</p>"]
        for name, r in (("Map 2", res.step2), ("Map 3", res.step3)):
            if r is None:
                html.append(f"<p><b>{name}</b>: not loaded – its axis is kept from the newest configuration.</p>")
                continue
            extra = ""
            if "frame.rotation" in r.values:
                extra += f"; frame rotation {r.values['frame.rotation']:.2f}° (map 1: {v1['rotation']:.2f}°)"
            if "frame.tilt_u" in r.values:
                extra += f"; tilt of the gold face about v {r.values['frame.tilt_u']:.2f} ± {r.sigma['frame.tilt_u']:.2f}°"
            html.append(f"<p><b>{name}</b>: edge rms {r.rms * 1000:.1f} µm, {r.used_lines} lines used{extra}.</p>")
            for note in r.notes:
                html.append(f"<p style='color:#8a5a00'>&nbsp;&nbsp;{note}</p>")
        for note in res.notes:
            html.append(f"<p style='color:#b00020'>! {note}</p>")
        html.append("<p style='color:#555'>Good fit: edge rms of a few µm, lines left out only where the frame is out "
                    "of the map or not seen, tilt ≲ 2°, shear ≲ 0.5°, and the fitted edges (orange, Maps tab) on the "
                    "gold edges. The frame is taken to be at the given place on the plate: a mounting error of the "
                    "frame goes into ST0 / SZ0 and the axes.</p>")
        self.details.setHtml("".join(html))

    def save(self):
        if self.result is None:
            return
        s1 = self.slots["step1"].scan
        newest = self.newest_record()
        optic_pos = None if self.optic_from_map.isChecked() else self.optic_position.value()
        sources = {k: s.paths for k, s in self.slots.items() if s.paths}
        record = calibration_record(self.result, s1, self.sn_gold.value(), newest, self.optic.currentData(),
                                    optic_pos, self.comment.text(), sources)
        saved = self.store.save(record)
        self._show_newest()
        QtWidgets.QMessageBox.information(
            self, "Gold frame calibration",
            f"Saved as\n{saved.path}\n\nQuickAlignment loads it at the next start with the {saved.optic_name}.")

    def load_example(self):
        """Simulated maps of a frame with known faults, loaded as if measured (to try the program)."""
        from ..gold_frame import standard_scans
        config = self.newest_record().config
        nominal = nominal_setup(config, 0.05)
        m = nominal.frame_motors()
        truth = Setup(replace(config, srn_axis_u=config.srn_axis_u + 0.1, srz_offset_n=config.srz_offset_n + 0.2),
                      GoldFrame(height=0.05, u=0.15, v=-0.1, rotation=1.5),
                      Instrument(counts=3000, scale_st_ref=m.st, scale_sz_ref=m.sz))
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("Simulating the three maps…")
        QtWidgets.QApplication.processEvents()
        try:
            folder = Path(tempfile.mkdtemp(prefix="gold_frame_example_"))
            scans = standard_scans(nominal, step=0.02, surface=True)
            files = {}
            for key, scan in scans.items():
                truth.simulate(scan, np.random.default_rng(0))
                try:
                    from ..spem_nxs import write_scan
                    files[key] = folder / f"{key}.nxs"
                    write_scan(files[key], scan, optic_position=60.0)
                except ImportError:
                    files[key] = folder / f"{key}.npz"
                    scan.save(files[key])
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        for key, path in files.items():
            self.slots[key].load([str(path)])
        self.sn_from_map.setChecked(False)
        self.sn_gold.setValue(truth.frame_motors().sn)
        c = truth.config
        self.statusBar().showMessage(
            f"Simulated example in {folder}: frame at (0.15, −0.10) mm, turned 1.5°; true values with the frame "
            f"taken at the plate centre: ST0 {c.st0 - 0.15:.4f}, SZ0 {c.sz0 + 0.1:.4f}, SRn axis "
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


__all__ = ["GoldFrameWindow", "main"]
