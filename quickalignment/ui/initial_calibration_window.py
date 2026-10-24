"""Initial calibration program (first start, after re-homing motors, maintenance).

Beamline staff measure one reference feature in a few stage orientations;
the stage constants are fitted and saved as a new dated configuration that
QuickAlignment then loads.
"""

from __future__ import annotations

import sys

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ._qt import QtCore, QtWidgets, exec_app
from .stage_panel import OPTIC_DIRECTIONS, align_labels, equal_row, out_of_range, spin
from ..calibration import CalibrationRecord, CalibrationStore
from ..geometry import PLATES
from ..initial_calibration import (
    CORRECTION_PARAMS, FIT_PARAMS, PARAM_LABELS, MeasurementSet, NotEnoughData, fit_initial_calibration, fit_optics,
    initial_record, protocol_sets,
)
from ..schematic import draw_reference_feature, feature_warnings
from ..stage import OPTIC_TYPES, StageModel

Qt = QtCore.Qt

PROTOCOL_HTML = """
<h3>Initial calibration – measurement protocol</h3>
<p><b>When:</b> first use, after re-homing / resetting the manipulator motors, after maintenance or
when the reference check in QuickAlignment shows large deviations.</p>
<p><b>Reference feature:</b> one small, sharp feature that you can find with the beam (e.g. the corner of
a reference sample or a mark), close to the plate centre so that it stays reachable when rotating.
Enter its plate coordinates x, y (mm, from the centre of the back plate, front view, tab up)
and its height H above the plate surface, then press <i>Show front / side view</i> to check the
position on the drawing. Use <b>the same feature in every set</b>.</p>
<p><b>Optic:</b> choose the focusing optic mounted (zone plate + OSA or capillary); the configuration is
saved for that optic and QuickAlignment loads it when that optic is chosen at start-up.</p>
<p><b>For every set:</b></p>
<ol>
<li>Set SRn and SRz to the values of the set; PIX = PIY = 150 µm.</li>
<li>Bring the feature onto the beam with ST / SZ (scan across it, take the centre of the edge / feature).</li>
<li>Bring it to the analyzer focus with SN.</li>
<li>Repeat 2–3 until both are stable, then write down ST, SZ, SN.</li>
<li>Optimise the optic focus on the feature and write down the optic position (at least in set 1;
in every set is better: the scatter shows how well the focus is reproduced).</li>
</ol>
<p><b>Sets</b> (the minimum is 3: sets 1–3; sets 4–5 are strongly recommended as a check):</p>
<table border=1 cellspacing=0 cellpadding=3>
<tr><th>set</th><th>SRn</th><th>SRz</th><th>determines</th></tr>
<tr><td>1</td><td>120</td><td>0</td><td>ST0, SZ0, SN_f, optics reference</td></tr>
<tr><td>2</td><td>140</td><td>0</td><td>SRn axis position</td></tr>
<tr><td>3</td><td>120</td><td>−10</td><td>SRz axis offsets</td></tr>
<tr><td>4</td><td>100</td><td>0</td><td>check</td></tr>
<tr><td>5</td><td>120</td><td>+10</td><td>check</td></tr>
</table>
<p>Larger rotations give a more precise axis: keep |SRn − 120| ≥ 20° and |SRz| as large as the
geometry allows (≥ 10°). The angles may be changed in the table.</p>
<p><b>Correction of an existing configuration</b> (e.g. after re-homing only ST / SZ / SN): choose
<i>Correct ST0, SZ0, SN_f</i>; the axes are kept from the base configuration and one set is enough
(more sets give a check).</p>
<p><b>Then</b> press <i>Compute</i>. With 5 sets the residuals should be ≲ 0.01–0.02 mm; a single large residual
usually means one set was measured on a different point or out of focus. Press <i>Save</i> to write the
configuration; QuickAlignment loads the newest one at start-up.</p>
"""

COLS = ["Use", "Set", "SRn (°)", "SRz (°)", "ST (mm)", "SZ (mm)", "SN (mm)", "Optic at focus"]
NUMERIC = {2: "srn", 3: "srz", 4: "st", 5: "sz", 6: "sn"}
OPTIC_COL = 7  # optional
RMS_WARNING = 0.02  # mm
FIT_MODES = [
    ("New calibration: all 7 constants", FIT_PARAMS),
    ("Correct ST0, SZ0, SN_f of the base configuration (axes kept)", CORRECTION_PARAMS),
]


class FeatureViewDialog(QtWidgets.QDialog):
    """Front and side view of the plate with the reference feature, to check the entered position."""

    def __init__(self, window: InitialCalibrationWindow):
        super().__init__(window)
        self.setWindowTitle("Reference feature – front and side view")
        self.resize(1000, 620)
        self.window_ = window
        self.figure = Figure(figsize=(10, 5.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.info)
        layout.addWidget(close, 0, Qt.AlignRight)
        self.refresh()

    def refresh(self) -> None:
        w = self.window_
        plate, base = w.plate(), w.base_record().config
        u, v, h = w.ref_x.value(), w.ref_y.value(), w.ref_h.value()
        draw_reference_feature(self.figure, plate, u, v, h, (base.srn_axis_u, base.srn_axis_v))
        self.canvas.draw_idle()
        lines = [f"<span style='color:#c00000'><b>Check: {t}.</b></span>" for t in feature_warnings(plate, u, v)]
        # where the feature should be found with the base configuration: a rough guide, and a range check
        model = StageModel(base, plate)
        rows = ""
        for s in w.planned_sets():
            m = model.motors_for_target(*w.ref_uvw(), srn=s.srn, srz=s.srz)
            bad = out_of_range(m)
            style = " style='color:#c00000'" if bad else ""
            rows += (f"<tr{style}><td>{s.name}</td><td>{s.srn:g}</td><td>{s.srz:g}</td><td>{m.st:.3f}</td>"
                     f"<td>{m.sz:.3f}</td><td>{m.sn:.3f}</td><td>{', '.join(bad)}</td></tr>")
        lines.append(f"Expected positions with the base configuration ({w.base_record().label}):"
                     "<table cellspacing=6><tr><th>set</th><th>SRn</th><th>SRz</th><th>ST</th><th>SZ</th><th>SN</th>"
                     f"<th></th></tr>{rows}</table>")
        self.info.setText("<br>".join(lines))


class InitialCalibrationWindow(QtWidgets.QMainWindow):
    def __init__(self, store: CalibrationStore | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment — initial calibration")
        self.resize(1500, 950)
        self.store = store or CalibrationStore()
        self.result = None

        protocol = QtWidgets.QTextBrowser()
        protocol.setHtml(PROTOCOL_HTML)
        protocol.setMinimumWidth(430)

        # reference feature
        self.plate_combo = QtWidgets.QComboBox()
        for key, plate in PLATES.items():
            self.plate_combo.addItem(plate.name, key)
        self.ref_x = spin(0.0, -20, 20, 3, 0.1)
        self.ref_y = spin(0.0, -20, 20, 3, 0.1)
        self.ref_h = spin(0.0, 0, 20, 3, 0.1)
        view_btn = QtWidgets.QPushButton("Show front / side view")
        view_btn.setToolTip("Draw the plate with the reference feature (front and side view) to check\n"
                            "the entered position, with the expected ST / SZ / SN of the sets.")
        view_btn.clicked.connect(self.show_feature)
        self.feature_dialog = None
        ref_box = QtWidgets.QGroupBox("Reference feature (plate coordinates)")
        rf = QtWidgets.QFormLayout(ref_box)
        rf.addRow("Plate", self.plate_combo)
        rf.addRow("x", self.ref_x)
        rf.addRow("y", self.ref_y)
        rf.addRow("H above plate surface", self.ref_h)
        rf.addRow(view_btn)
        for box in (self.ref_x, self.ref_y, self.ref_h):
            box.valueChanged.connect(self._refresh_feature)
        self.plate_combo.currentIndexChanged.connect(self._refresh_feature)

        # measurement sets
        self.table = QtWidgets.QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        # "Use" and "Set" fit their contents, the numeric columns share the rest equally
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeaderItem(OPTIC_COL).setToolTip(
            "Optic position at best focus on the feature (optional; needed in at least one set\n"
            "for the optics reference, the first set with a value is the reference state).")
        self.table.setMinimumHeight(200)
        add_btn = QtWidgets.QPushButton("Add set")
        add_btn.clicked.connect(lambda: self._add_row(MeasurementSet(f"{self.table.rowCount() + 1} extra", 120.0, 0.0)))
        del_btn = QtWidgets.QPushButton("Remove selected set")
        del_btn.clicked.connect(self._remove_rows)
        sets_box = QtWidgets.QGroupBox("Measurement sets: reference feature on the beam, at the analyzer focus")
        sb = QtWidgets.QVBoxLayout(sets_box)
        sb.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        sb.addLayout(row)
        for s in protocol_sets():
            self._add_row(s)

        # optics and what is fitted
        self.optic_type = QtWidgets.QComboBox()
        for name in OPTIC_TYPES:
            self.optic_type.addItem(name[0].upper() + name[1:], name)
        self.optic_type.currentIndexChanged.connect(self._fill_bases)
        self.optic_dir = QtWidgets.QComboBox()
        self.optic_dir.addItems(OPTIC_DIRECTIONS)
        self.base_combo = QtWidgets.QComboBox()
        self.base_combo.setToolTip("Configuration whose other constants (SRn ref, piezo centre and, for a correction,\n"
                                   "the axes) are kept, and that the results are compared with.")
        self.base_combo.currentIndexChanged.connect(self._refresh_feature)
        self.fit_mode = QtWidgets.QComboBox()
        for label, _ in FIT_MODES:
            self.fit_mode.addItem(label)
        optics_box = QtWidgets.QGroupBox("Optics and configuration")
        of = QtWidgets.QFormLayout(optics_box)
        of.addRow("Focusing optic", self.optic_type)
        of.addRow("Optic motor direction", self.optic_dir)
        of.addRow("Base configuration", self.base_combo)
        of.addRow("Fit", self.fit_mode)
        self._fill_bases()

        compute_btn = QtWidgets.QPushButton("Compute")
        compute_btn.setMinimumHeight(34)
        compute_btn.setStyleSheet("font-weight: bold;")
        compute_btn.clicked.connect(self.compute)
        self.result_label = QtWidgets.QLabel("Fill in the measured ST, SZ, SN and press Compute.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("padding: 6px; background: #f6f6f6;")
        self.result_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("comment, e.g. 'after motor re-homing, 2026-10'")
        self.save_btn = QtWidgets.QPushButton("Save as new configuration")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        folder = QtWidgets.QLabel(f"Configuration folder: {self.store.folder}")
        folder.setStyleSheet("color: #777;")

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        align_labels(rf, of)
        rv.addLayout(equal_row(ref_box, optics_box))
        rv.addWidget(sets_box, 0)
        rv.addWidget(compute_btn)
        result_scroll = QtWidgets.QScrollArea()
        result_scroll.setWidget(self.result_label)
        result_scroll.setWidgetResizable(True)
        rv.addWidget(result_scroll, 1)
        rv.addWidget(self.comment)
        rv.addWidget(self.save_btn)
        rv.addWidget(folder)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(protocol)
        splitter.addWidget(right)
        splitter.setSizes([520, 980])
        self.setCentralWidget(splitter)

    # -- table ---------------------------------------------------------------------
    def _add_row(self, s: MeasurementSet) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        use = QtWidgets.QTableWidgetItem()
        use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        use.setCheckState(Qt.Checked if s.use else Qt.Unchecked)
        self.table.setItem(row, 0, use)
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(s.name))
        for col, attr in NUMERIC.items():
            text = "" if attr in ("st", "sz", "sn") and getattr(s, attr) == 0.0 else f"{getattr(s, attr):g}"
            self.table.setItem(row, col, QtWidgets.QTableWidgetItem(text))
        self.table.setItem(row, OPTIC_COL, QtWidgets.QTableWidgetItem("" if s.optic is None else f"{s.optic:g}"))

    def _remove_rows(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return item.text().strip() if item else ""

    def sets(self) -> tuple[list[MeasurementSet], list[str]]:
        """Sets from the table; rows that are ticked but incomplete are reported."""
        out, problems = [], []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() != Qt.Checked:
                continue
            name = self.table.item(row, 1).text()
            values = {}
            for col, attr in NUMERIC.items():
                try:
                    values[attr] = float(self._text(row, col))
                except ValueError:
                    problems.append(f"{name}: {COLS[col]} missing")
                    break
            else:
                optic = self._text(row, OPTIC_COL)
                try:
                    values["optic"] = float(optic) if optic else None
                except ValueError:
                    problems.append(f"{name}: {COLS[OPTIC_COL]} is not a number")
                    continue
                out.append(MeasurementSet(name, **values))
        return out, problems

    def planned_sets(self) -> list[MeasurementSet]:
        """The ticked sets with readable angles (measured values not needed)."""
        out = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() != Qt.Checked:
                continue
            try:
                out.append(MeasurementSet(self.table.item(row, 1).text(), float(self._text(row, 2)), float(self._text(row, 3))))
            except ValueError:
                continue
        return out

    def plate(self):
        return PLATES[self.plate_combo.currentData()]

    def optic(self) -> str:
        return self.optic_type.currentData()

    def fit_params(self) -> tuple[str, ...]:
        return FIT_MODES[self.fit_mode.currentIndex()][1]

    def _fill_bases(self, *_) -> None:
        """Base configurations: the newest for the chosen optic first, then all others."""
        latest = self.store.latest(self.optic())
        self._bases = [latest] + [r for r in self.store.records() if r.path != latest.path]
        if latest.path is not None:
            self._bases.append(CalibrationRecord())  # the built-in default
        self.base_combo.blockSignals(True)
        self.base_combo.clear()
        for i, r in enumerate(self._bases):
            self.base_combo.addItem(("newest for this optic: " if i == 0 else "") + r.label)
        self.base_combo.blockSignals(False)
        self._refresh_feature()

    def base_record(self) -> CalibrationRecord:
        return self._bases[max(self.base_combo.currentIndex(), 0)]

    def show_feature(self) -> None:
        if self.feature_dialog is None:
            self.feature_dialog = FeatureViewDialog(self)
        self.feature_dialog.refresh()
        self.feature_dialog.show()
        self.feature_dialog.raise_()

    def _refresh_feature(self, *_) -> None:
        if getattr(self, "feature_dialog", None) is not None and self.feature_dialog.isVisible():
            self.feature_dialog.refresh()

    def ref_uvw(self):
        return self.ref_x.value(), self.ref_y.value(), self.plate().total_thickness + self.ref_h.value()

    # -- actions ---------------------------------------------------------------------
    def compute(self) -> None:
        self.result = None
        self.save_btn.setEnabled(False)
        sets, problems = self.sets()
        if problems:
            self.result_label.setText("<b>Incomplete sets</b> (untick them or fill them in):<br>" + "<br>".join(problems))
            return
        base = self.base_record()
        params = self.fit_params()
        try:
            res = fit_initial_calibration(sets, self.plate(), self.ref_uvw(), base=base.config, params=params)
        except NotEnoughData as exc:
            minimum = ("The minimum is 3 sets: SRn = 120 / SRz = 0, one SRn rotation, one SRz rotation."
                       if params == FIT_PARAMS else "The minimum is 1 set.")
            self.result_label.setText(f"<b>{exc}</b><br>{minimum}")
            return
        self.result = res
        html = "<b>Fitted constants</b><table cellspacing=6><tr><th></th><th>value</th><th>± 1σ</th>"
        html += f"<th>base ({base.label})</th><th>change</th></tr>"
        for p in FIT_PARAMS:
            value, old = getattr(res.config, p), getattr(base.config, p)
            if p in params:
                sig = f"{res.sigma[p]:.4f}" if res.sigma else "–"
                html += (f"<tr><td>{PARAM_LABELS[p]}</td><td><b>{value:.4f}</b></td><td>{sig}</td><td>{old:.4f}</td>"
                         f"<td>{value - old:+.4f}</td></tr>")
            else:
                html += f"<tr><td>{PARAM_LABELS[p]}</td><td>{value:.4f}</td><td>kept</td><td>{old:.4f}</td><td></td></tr>"
        html += "</table><b>Residuals</b> (model − measured, mm)<table cellspacing=6><tr><th>set</th><th>ST</th><th>SZ</th><th>SN</th></tr>"
        for name, d_st, d_sz, d_sn in res.residuals:
            html += f"<tr><td>{name}</td><td>{d_st:+.4f}</td><td>{d_sz:+.4f}</td><td>{d_sn:+.4f}</td></tr>"
        html += f"</table>rms = {res.rms:.4f} mm, {res.dof} redundant equation(s).<br>"
        html += self._optics_html(res, base)
        if params == FIT_PARAMS and res.dof <= 2:
            html += "<span style='color:#b36b00'>Minimum data set: mistakes in a set cannot be detected. Measuring sets 4–5 is recommended.</span><br>"
        if res.rms > RMS_WARNING:
            html += f"<span style='color:#c00000'><b>Residuals above {RMS_WARNING} mm: check the sets with the largest residuals.</b></span><br>"
        self.result_label.setText(html)
        self.save_btn.setEnabled(True)

    def optic_sign(self) -> int:
        return 1 if self.optic_dir.currentIndex() == 0 else -1

    def _optics_html(self, res, base: CalibrationRecord) -> str:
        fit = fit_optics(res, self.plate(), self.ref_uvw(), self.optic_sign(), self.optic())
        name = self.optic_type.currentText()
        if not fit.residuals:
            if self._kept_optics(base) is not None:
                return f"No optic position entered: the {name} reference of the base configuration is kept.<br>"
            return (f"<span style='color:#b36b00'><b>No optic position entered:</b> the {name} reference is not "
                    "calibrated (QuickAlignment then assumes the optic focus on the analyzer focus).</span><br>")
        sig = f" ± {fit.sigma:.4f}" if fit.sigma is not None else ""
        ref_name = next(s.name for s in res.sets if s.optic is not None)
        html = (f"<b>Optics reference</b> ({name}): position <b>{fit.optics.optic_position:.4f}</b>{sig} with the stage "
                f"as in set “{ref_name}”")
        if base.optics.optic_type == fit.optics.optic_type and base.optics.enabled:
            html += f" (base: {base.optics.optic_position:.4f})"
        html += "<br>"
        if len(fit.residuals) > 1:
            html += "Optic residuals (model − measured): " + ", ".join(f"{n} {d:+.4f}" for n, d in fit.residuals)
            html += f"; rms {fit.rms:.4f}<br>"
        return html

    def _kept_optics(self, base: CalibrationRecord):
        """For a correction: the base configuration's optics reference, if it is for the chosen optic."""
        if self.fit_params() == FIT_PARAMS or not base.optics.enabled or base.optics.optic_type != self.optic():
            return None
        return base.optics

    def save(self) -> None:
        if self.result is None:
            return
        base = self.base_record()
        record = initial_record(
            self.result, self.plate(), self.ref_uvw(), self.optic_sign(), self.optic(), self.comment.text().strip(),
            base_label=None if self.fit_params() == FIT_PARAMS else base.label,
            kept_optics=self._kept_optics(base),
        )
        saved = self.store.save(record)
        self.save_btn.setEnabled(False)
        self._fill_bases()
        self.result_label.setText(
            self.result_label.text() + f"<br><b>Saved {saved.path.name}</b> — QuickAlignment loads it at the next start "
            f"when the {saved.optic_name} is chosen.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    win = InitialCalibrationWindow()
    win.show()
    return exec_app(app)
