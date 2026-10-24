"""Initial calibration program (first start, after re-homing motors, maintenance).

Beamline staff measure one reference feature in a few stage orientations;
the stage constants are fitted and saved as a new dated configuration that
QuickAlignment then loads.
"""

from __future__ import annotations

import sys

from ._qt import QtCore, QtWidgets, exec_app
from .stage_panel import OPTIC_DIRECTIONS, align_labels, equal_row, spin
from ..calibration import CalibrationStore
from ..geometry import PLATES
from ..initial_calibration import (
    FIT_PARAMS, PARAM_LABELS, MeasurementSet, NotEnoughData, fit_initial_calibration, initial_record, protocol_sets,
)

Qt = QtCore.Qt

PROTOCOL_HTML = """
<h3>Initial calibration – measurement protocol</h3>
<p><b>When:</b> first use, after re-homing / resetting the manipulator motors, after maintenance or
when the reference check in QuickAlignment shows large deviations.</p>
<p><b>Reference feature:</b> one small, sharp feature that you can find with the beam (e.g. the corner of
a reference sample or a mark), close to the plate centre so that it stays reachable when rotating.
Enter its plate coordinates x, y (mm, from the centre of the back plate, front view, tab up)
and its height H above the plate surface. Use <b>the same feature in every set</b>.</p>
<p><b>For every set:</b></p>
<ol>
<li>Set SRn and SRz to the values of the set; PIX = PIY = 150 µm.</li>
<li>Bring the feature onto the beam with ST / SZ (scan across it, take the centre of the edge / feature).</li>
<li>Bring it to the analyzer focus with SN.</li>
<li>Repeat 2–3 until both are stable, then write down ST, SZ, SN.</li>
</ol>
<p><b>Sets</b> (the minimum is 3: sets 1–3; sets 4–5 are strongly recommended as a check):</p>
<table border=1 cellspacing=0 cellpadding=3>
<tr><th>set</th><th>SRn</th><th>SRz</th><th>determines</th></tr>
<tr><td>1</td><td>120</td><td>0</td><td>ST0, SZ0, SN_f (+ optics reference)</td></tr>
<tr><td>2</td><td>140</td><td>0</td><td>SRn axis position</td></tr>
<tr><td>3</td><td>120</td><td>−10</td><td>SRz axis offsets</td></tr>
<tr><td>4</td><td>100</td><td>0</td><td>check</td></tr>
<tr><td>5</td><td>120</td><td>+10</td><td>check</td></tr>
</table>
<p>Larger rotations give a more precise axis: keep |SRn − 120| ≥ 20° and |SRz| as large as the
geometry allows (≥ 10°). The angles may be changed in the table.</p>
<p><b>Optics:</b> at set 1, also optimise the optic focus and note the optic position.</p>
<p><b>Then</b> press <i>Compute</i>. With 5 sets the residuals should be ≲ 0.01–0.02 mm; a single large residual
usually means one set was measured on a different point or out of focus. Press <i>Save</i> to write the
configuration; QuickAlignment loads the newest one at start-up.</p>
"""

COLS = ["Use", "Set", "SRn (°)", "SRz (°)", "ST (mm)", "SZ (mm)", "SN (mm)"]
NUMERIC = {2: "srn", 3: "srz", 4: "st", 5: "sz", 6: "sn"}
RMS_WARNING = 0.02  # mm


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
        ref_box = QtWidgets.QGroupBox("Reference feature (plate coordinates)")
        rf = QtWidgets.QFormLayout(ref_box)
        rf.addRow("Plate", self.plate_combo)
        rf.addRow("x", self.ref_x)
        rf.addRow("y", self.ref_y)
        rf.addRow("H above plate surface", self.ref_h)

        # measurement sets
        self.table = QtWidgets.QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        # "Use" and "Set" fit their contents, the numeric columns share the rest equally
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
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

        # optics
        self.optics_on = QtWidgets.QCheckBox("Optic focus optimised at set 1")
        self.optics_on.setChecked(True)
        self.optic_pos = spin(0.0, -10000, 10000, 4, 0.01)
        self.optic_dir = QtWidgets.QComboBox()
        self.optic_dir.addItems(OPTIC_DIRECTIONS)
        optics_box = QtWidgets.QGroupBox("Optics")
        of = QtWidgets.QFormLayout(optics_box)
        of.addRow(self.optics_on)
        of.addRow("Optic position at best focus", self.optic_pos)
        of.addRow("Optic motor direction", self.optic_dir)

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

    def _remove_rows(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def sets(self) -> tuple[list[MeasurementSet], list[str]]:
        """Sets from the table; rows that are ticked but incomplete are reported."""
        out, problems = [], []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() != Qt.Checked:
                continue
            name = self.table.item(row, 1).text()
            values = {}
            for col, attr in NUMERIC.items():
                text = (self.table.item(row, col).text() if self.table.item(row, col) else "").strip()
                try:
                    values[attr] = float(text)
                except ValueError:
                    problems.append(f"{name}: {COLS[col]} missing")
                    break
            else:
                out.append(MeasurementSet(name, **values))
        return out, problems

    def plate(self):
        return PLATES[self.plate_combo.currentData()]

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
        latest = self.store.latest()
        try:
            res = fit_initial_calibration(sets, self.plate(), self.ref_uvw(), base=latest.config)
        except NotEnoughData as exc:
            self.result_label.setText(f"<b>{exc}</b><br>The minimum is 3 sets: SRn = 120 / SRz = 0, one SRn rotation, one SRz rotation.")
            return
        self.result = res
        html = "<b>Fitted constants</b><table cellspacing=6><tr><th></th><th>value</th><th>± 1σ</th>"
        html += f"<th>previous ({latest.label})</th></tr>"
        for p in FIT_PARAMS:
            value = getattr(res.config, p)
            sig = f"{res.sigma[p]:.4f}" if res.sigma else "–"
            html += f"<tr><td>{PARAM_LABELS[p]}</td><td><b>{value:.4f}</b></td><td>{sig}</td><td>{getattr(latest.config, p):.4f}</td></tr>"
        html += "</table><b>Residuals</b> (model − measured, mm)<table cellspacing=6><tr><th>set</th><th>ST</th><th>SZ</th><th>SN</th></tr>"
        for name, d_st, d_sz, d_sn in res.residuals:
            html += f"<tr><td>{name}</td><td>{d_st:+.4f}</td><td>{d_sz:+.4f}</td><td>{d_sn:+.4f}</td></tr>"
        html += f"</table>rms = {res.rms:.4f} mm, {res.dof} redundant equation(s).<br>"
        if res.dof <= 2:
            html += "<span style='color:#b36b00'>Minimum data set: mistakes in a set cannot be detected. Measuring sets 4–5 is recommended.</span><br>"
        if res.rms > RMS_WARNING:
            html += f"<span style='color:#c00000'><b>Residuals above {RMS_WARNING} mm: check the sets with the largest residuals.</b></span><br>"
        self.result_label.setText(html)
        self.save_btn.setEnabled(True)

    def save(self) -> None:
        if self.result is None:
            return
        record = initial_record(
            self.result, self.plate(), self.ref_uvw(),
            self.optic_pos.value() if self.optics_on.isChecked() else None,
            1 if self.optic_dir.currentIndex() == 0 else -1,
            self.comment.text().strip(),
        )
        saved = self.store.save(record)
        self.save_btn.setEnabled(False)
        self.result_label.setText(self.result_label.text() + f"<br><b>Saved {saved.path.name}</b> — QuickAlignment will load it at the next start.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    win = InitialCalibrationWindow()
    win.show()
    return exec_app(app)
