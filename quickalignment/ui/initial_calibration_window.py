"""Initial calibration program (first start, after re-homing motors, maintenance).

Beamline staff measure one reference feature in a few stage orientations;
the stage constants are fitted, tried out at test points and corrected with
what was really found there, until staff are satisfied. The result is saved
as a new dated configuration that QuickAlignment then loads.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ._qt import QtCore, QtGui, QtWidgets, exec_app
from .stage_panel import align_labels, equal_row, out_of_range, spin
from ..calibration import CalibrationStore
from ..geometry import PLATES
from ..initial_calibration import (
    FOUND_TOLERANCE, OPTIC_PARAM, PARAM_LABELS, MeasurementSet, NotEnoughData, TestPoint, fit_initial_calibration,
    initial_record, optic_focus_of, predict_test_point, protocol_sets, verification_angles,
)
from ..schematic import draw_reference_feature, feature_warnings
from ..stage import OPTIC_TYPES, MotorPositions, StageModel

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
saved for that optic and QuickAlignment loads it when that optic is chosen at start-up.
Increasing the optic motor moves the optic towards the sample.</p>
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
<p><b>Then</b> press <i>Compute</i>: all constants are fitted and compared with the newest configuration.
With 5 sets the residuals should be ≲ 0.01–0.02 mm; a single large residual usually means one set was
measured on a different point or out of focus.</p>
<p><b>Test points</b> (repeat until you are satisfied):</p>
<ol>
<li>For each test point, move to the <i>Go to</i> SRn, SRz, ST, SZ, SN and optic position.</li>
<li>If the feature is on the beam and in focus there (within 0.05 mm), tick <i>Found</i>.</li>
<li>If not: keep SRn, SRz and SN, bring the feature onto the beam with ST / SZ, focus the optic, and
enter the real ST, SZ and optic position.</li>
<li>Press <i>Correct the configuration</i>: the answers are added to the fit, and a new round of test
points is predicted with the corrected configuration. The angles of a new test point may be changed.</li>
</ol>
<p>When the feature is found at the predicted positions (or close enough), add a comment and press
<i>Save</i>; QuickAlignment loads the newest configuration of the chosen optic at start-up.</p>
"""

COLS = ["Use", "Set", "SRn (°)", "SRz (°)", "ST (mm)", "SZ (mm)", "SN (mm)", "Optic at focus"]
NUMERIC = {2: "srn", 3: "srz", 4: "st", 5: "sz", 6: "sn"}
OPTIC_COL = 7  # optional
RMS_WARNING = 0.02  # mm

TEST_COLS = ["Round", "Test point", "SRn (°)", "SRz (°)", "Go to\nST", "Go to\nSZ", "Go to\nSN", "Go to\noptic",
             "Found", "Real\nST", "Real\nSZ", "Real\noptic", "Real − predicted\n(ST, SZ, optic)"]
T_SRN, T_SRZ, T_FOUND, T_ST, T_SZ, T_OPTIC, T_DEV = 2, 3, 8, 9, 10, 11, 12
DONE_COLOR = QtGui.QColor("#ececec")


def _fmt(value, digits: int = 4) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


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
        plate = w.plate()
        config, label = w.current_config()
        u, v, h = w.ref_x.value(), w.ref_y.value(), w.ref_h.value()
        draw_reference_feature(self.figure, plate, u, v, h, (config.srn_axis_u, config.srn_axis_v))
        self.canvas.draw_idle()
        lines = [f"<span style='color:#c00000'><b>Check: {t}.</b></span>" for t in feature_warnings(plate, u, v)]
        # where the feature should be found: a rough guide, and a range check
        model = StageModel(config, plate)
        rows = ""
        for s in w.planned_sets():
            m = model.motors_for_target(*w.ref_uvw(), srn=s.srn, srz=s.srz)
            bad = out_of_range(m)
            style = " style='color:#c00000'" if bad else ""
            rows += (f"<tr{style}><td>{s.name}</td><td>{s.srn:g}</td><td>{s.srz:g}</td><td>{m.st:.3f}</td>"
                     f"<td>{m.sz:.3f}</td><td>{m.sn:.3f}</td><td>{', '.join(bad)}</td></tr>")
        lines.append(f"Expected positions with {label}:"
                     "<table cellspacing=6><tr><th>set</th><th>SRn</th><th>SRz</th><th>ST</th><th>SZ</th><th>SN</th>"
                     f"<th></th></tr>{rows}</table>")
        self.info.setText("<br>".join(lines))


class InitialCalibrationWindow(QtWidgets.QMainWindow):
    def __init__(self, store: CalibrationStore | None = None):
        super().__init__()
        self.setWindowTitle("ANTARES QuickAlignment — initial calibration")
        self.resize(1500, 1000)
        self.store = store or CalibrationStore()
        self.result = None
        self.tests: list[TestPoint] = []  # all test points, one table row each
        self._filling = False

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

        # optic; results are compared with the newest configuration
        self.optic_type = QtWidgets.QComboBox()
        for name in OPTIC_TYPES:
            self.optic_type.addItem(name[0].upper() + name[1:], name)
        self.previous_label = QtWidgets.QLabel()
        self.previous_label.setWordWrap(True)
        self.previous_label.setStyleSheet("color: #555;")
        optics_box = QtWidgets.QGroupBox("Optic")
        of = QtWidgets.QFormLayout(optics_box)
        of.addRow("Focusing optic", self.optic_type)
        of.addRow(QtWidgets.QLabel("Optic motor: + moves the optic towards the sample."))
        of.addRow(self.previous_label)
        self._show_previous()

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
            "for the optics reference).")
        self.table.setMinimumHeight(190)
        add_btn = QtWidgets.QPushButton("Add set")
        add_btn.clicked.connect(lambda: self._add_row(MeasurementSet(f"{self.table.rowCount() + 1} extra", 120.0, 0.0)))
        del_btn = QtWidgets.QPushButton("Remove selected set")
        del_btn.clicked.connect(self._remove_rows)
        compute_btn = QtWidgets.QPushButton("Compute")
        compute_btn.setMinimumHeight(34)
        compute_btn.setStyleSheet("font-weight: bold;")
        compute_btn.clicked.connect(self.compute)
        sets_box = QtWidgets.QGroupBox("Measurement sets: reference feature on the beam, at the analyzer focus")
        sb = QtWidgets.QVBoxLayout(sets_box)
        sb.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        sb.addLayout(row)
        sb.addWidget(compute_btn)
        for s in protocol_sets():
            self._add_row(s)

        self.result_label = QtWidgets.QLabel("Fill in the measured ST, SZ, SN and press Compute.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet("padding: 6px; background: #f6f6f6;")
        self.result_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        result_scroll = QtWidgets.QScrollArea()
        result_scroll.setWidget(self.result_label)
        result_scroll.setWidgetResizable(True)

        # test points: try the configuration out, correct it with what is really found
        self.test_table = QtWidgets.QTableWidget(0, len(TEST_COLS))
        self.test_table.setHorizontalHeaderLabels(TEST_COLS)
        th = self.test_table.horizontalHeader()
        th.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        for col in (0, 1, T_FOUND, T_DEV):
            th.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        self.test_table.verticalHeader().hide()
        self.test_table.horizontalHeaderItem(T_FOUND).setToolTip(
            f"Tick if the feature is on the beam, in focus, at the Go to positions (within {FOUND_TOLERANCE:g} mm).\n"
            "Found points confirm the configuration; they are not fitted.")
        for col in (T_ST, T_SZ, T_OPTIC):
            self.test_table.horizontalHeaderItem(col).setToolTip(
                "Not found: keep SRn, SRz, SN; bring the feature onto the beam with ST / SZ,\n"
                "focus the optic and enter the real values (optic optional).")
        self.test_table.itemChanged.connect(self._on_test_edit)
        self.correct_btn = QtWidgets.QPushButton("Correct the configuration with the test results → new test points")
        self.correct_btn.setMinimumHeight(30)
        self.correct_btn.setEnabled(False)
        self.correct_btn.clicked.connect(self.compute)
        self.test_status = QtWidgets.QLabel("Test points appear after Compute.")
        self.test_status.setWordWrap(True)
        tests_box = QtWidgets.QWidget()
        tb = QtWidgets.QVBoxLayout(tests_box)
        tb.addWidget(QtWidgets.QLabel("<b>Is the feature found at the predicted positions?</b> "
                                      "Tick <i>Found</i>, or enter the real ST, SZ, optic."))
        tb.addWidget(self.test_table, 1)
        tb.addWidget(self.test_status)
        tb.addWidget(self.correct_btn)

        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("comment, e.g. 'after motor re-homing, 2026-10'")
        self.save_btn = QtWidgets.QPushButton("Save as new configuration")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        folder = QtWidgets.QLabel(f"Configuration folder: {self.store.folder}")
        folder.setStyleSheet("color: #777;")

        top = QtWidgets.QWidget()
        tv = QtWidgets.QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        align_labels(rf, of)
        tv.addLayout(equal_row(ref_box, optics_box))
        tv.addWidget(sets_box)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(result_scroll, "Fit results")
        self.tabs.addTab(tests_box, "Test points")
        middle = QtWidgets.QSplitter(Qt.Vertical)
        middle.addWidget(top)
        middle.addWidget(self.tabs)
        middle.setSizes([430, 520])
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.addWidget(middle, 1)
        rv.addWidget(self.comment)
        rv.addWidget(self.save_btn)
        rv.addWidget(folder)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(protocol)
        splitter.addWidget(right)
        splitter.setSizes([480, 1020])
        self.setCentralWidget(splitter)

    # -- measurement sets ------------------------------------------------------------
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

    @staticmethod
    def _cell(table: QtWidgets.QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
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
                    values[attr] = float(self._cell(self.table, row, col))
                except ValueError:
                    problems.append(f"{name}: {COLS[col]} missing")
                    break
            else:
                optic = self._cell(self.table, row, OPTIC_COL)
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
                out.append(MeasurementSet(self.table.item(row, 1).text(),
                                          float(self._cell(self.table, row, 2)), float(self._cell(self.table, row, 3))))
            except ValueError:
                continue
        return out

    def plate(self):
        return PLATES[self.plate_combo.currentData()]

    def optic(self) -> str:
        return self.optic_type.currentData()

    def ref_uvw(self):
        return self.ref_x.value(), self.ref_y.value(), self.plate().total_thickness + self.ref_h.value()

    def previous(self):
        """The newest configuration: start values and comparison."""
        return self.store.latest()

    def _show_previous(self) -> None:
        self.previous_label.setText(f"Results are compared with the newest configuration: <b>{self.previous().label}</b>")

    def current_config(self):
        """The fitted constants once computed, else the newest configuration's (with a label)."""
        if self.result is not None:
            return self.result.config, "the current fit"
        prev = self.previous()
        return prev.config, f"the newest configuration ({prev.label})"

    def show_feature(self) -> None:
        if self.feature_dialog is None:
            self.feature_dialog = FeatureViewDialog(self)
        self.feature_dialog.refresh()
        self.feature_dialog.show()
        self.feature_dialog.raise_()

    def _refresh_feature(self, *_) -> None:
        if self.feature_dialog is not None and self.feature_dialog.isVisible():
            self.feature_dialog.refresh()

    # -- test points -------------------------------------------------------------------
    def _item(self, text: str, editable: bool, done: bool) -> QtWidgets.QTableWidgetItem:
        item = QtWidgets.QTableWidgetItem(text)
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if editable and not done:
            flags |= Qt.ItemIsEditable
        item.setFlags(flags)
        if done:
            item.setBackground(DONE_COLOR)
        return item

    def _fill_test_row(self, row: int) -> None:
        t, done = self.tests[row], self.tests[row].answered and row < self._first_open_row()
        self._filling = True
        values = [str(t.round), t.name, f"{t.srn:g}", f"{t.srz:g}", _fmt(t.pred_st), _fmt(t.pred_sz), _fmt(t.sn),
                  _fmt(t.pred_optic)]
        for col, text in enumerate(values):
            self.test_table.setItem(row, col, self._item(text, col in (T_SRN, T_SRZ), done))
        found = self._item("", False, done)
        if not done:
            found.setFlags(found.flags() | Qt.ItemIsUserCheckable)
        found.setCheckState(Qt.Checked if t.found else Qt.Unchecked)
        self.test_table.setItem(row, T_FOUND, found)
        for col, value in ((T_ST, t.st), (T_SZ, t.sz), (T_OPTIC, t.optic)):
            self.test_table.setItem(row, col, self._item("" if value is None else f"{value:g}", True, done))
        dev = ""
        if t.answered:
            d_st, d_sz, d_optic = t.deviation()
            dev = f"{d_st:+.4f}, {d_sz:+.4f}, {'–' if d_optic is None else f'{d_optic:+.4f}'}"
        self.test_table.setItem(row, T_DEV, self._item(dev, False, done))
        bad = out_of_range(MotorPositions(st=t.pred_st, sz=t.pred_sz, sn=t.sn, srn=t.srn, srz=t.srz))
        if bad:
            for col in (4, 5, 6):
                self.test_table.item(row, col).setForeground(QtGui.QColor("#c00000"))
                self.test_table.item(row, col).setToolTip("Outside the travel range: " + ", ".join(bad)
                                                          + "\nChange SRn / SRz of this test point.")
        self._filling = False

    def _first_open_row(self) -> int:
        """Rows before this belong to earlier rounds (read-only); the last round is open for answers."""
        last = max((t.round for t in self.tests), default=0)
        return next((i for i, t in enumerate(self.tests) if t.round == last), len(self.tests))

    def _rebuild_test_table(self) -> None:
        self._filling = True
        self.test_table.setRowCount(len(self.tests))
        self._filling = False
        for row in range(len(self.tests)):
            self._fill_test_row(row)

    def _on_test_edit(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._filling or self.result is None:
            return
        row, col = item.row(), item.column()
        if col in (T_SRN, T_SRZ):  # new angles: predict again
            try:
                srn, srz = float(self._cell(self.test_table, row, T_SRN)), float(self._cell(self.test_table, row, T_SRZ))
            except ValueError:
                self._fill_test_row(row)
                return
            t = replace(self.tests[row], srn=srn, srz=srz)
            self.tests[row] = predict_test_point(StageModel(self.result.config, self.plate()), self.ref_uvw(), t,
                                                 self.result.optic_focus)
            self._fill_test_row(row)

    def read_tests(self) -> list[str]:
        """Answers of the open round from the table into self.tests; problems reported."""
        problems = []
        for row in range(self._first_open_row(), len(self.tests)):
            t = self.tests[row]
            t.found = self.test_table.item(row, T_FOUND).checkState() == Qt.Checked
            values = {}
            for col, attr in ((T_ST, "st"), (T_SZ, "sz"), (T_OPTIC, "optic")):
                text = self._cell(self.test_table, row, col)
                try:
                    values[attr] = float(text) if text else None
                except ValueError:
                    problems.append(f"test point {t.name}: {TEST_COLS[col]} is not a number")
                    values[attr] = None
            t.st, t.sz, t.optic = values["st"], values["sz"], values["optic"]
            if t.found:
                t.st = t.sz = t.optic = None
            elif (t.st is None) != (t.sz is None):
                problems.append(f"test point {t.name}: enter both the real ST and SZ (or tick Found)")
        return problems

    def _new_round(self) -> None:
        """Keep the answered test points, predict a new round with the current fit."""
        self.tests = [t for t in self.tests if t.answered]
        n = max((t.round for t in self.tests), default=0) + 1
        model = StageModel(self.result.config, self.plate())
        srn_ref = self.result.config.srn_ref
        for name, srn, srz in verification_angles(srn_ref):
            t = TestPoint(f"{n}.{len([x for x in self.tests if x.round == n]) + 1} {name}", srn, srz, round=n)
            self.tests.append(predict_test_point(model, self.ref_uvw(), t, self.result.optic_focus))
        self._rebuild_test_table()
        self.test_table.scrollToItem(self.test_table.item(self._first_open_row(), 0), QtWidgets.QAbstractItemView.PositionAtTop)

    def _round_summary(self) -> str:
        answered = [t for t in self.tests if t.answered]
        if not answered:
            return ""
        last = max(t.round for t in answered)
        lines = []
        for r in range(1, last + 1):
            ts = [t for t in answered if t.round == r]
            if not ts:
                continue
            worst = max(max(abs(d) for d in t.deviation() if d is not None) for t in ts if t.measured) \
                if any(t.measured for t in ts) else None
            found = sum(t.found_within_tolerance for t in ts)
            lines.append(f"round {r}: {found} of {len(ts)} test point(s) found within {FOUND_TOLERANCE:g} mm"
                         + ("" if worst is None else f", largest measured deviation {worst:.4f} mm"))
        ts = [t for t in answered if t.round == last]
        if all(t.found_within_tolerance for t in ts):
            lines.append(f"<span style='color:#1a7f37'><b>All test points of round {last} were found at the "
                         "predictions: if you are satisfied, save the configuration.</b></span>")
        return "<br>".join(lines)

    # -- actions ---------------------------------------------------------------------
    def compute(self) -> None:
        """Fit the sets and the answered test points; predict a new round of test points."""
        sets, problems = self.sets()
        problems += self.read_tests()
        if problems:
            self.result_label.setText("<b>Incomplete entries</b> (untick or fill them in):<br>" + "<br>".join(problems))
            return
        self.result = None
        self.save_btn.setEnabled(False)
        self.correct_btn.setEnabled(False)
        prev = self.previous()
        try:
            res = fit_initial_calibration(sets, self.plate(), self.ref_uvw(), base=prev.config, tests=self.tests)
        except NotEnoughData as exc:
            self.result_label.setText(f"<b>{exc}</b><br>The minimum is 3 sets: SRn = 120 / SRz = 0, "
                                      "one SRn rotation, one SRz rotation.")
            return
        self.result = res
        html = "<b>Fitted constants</b><table cellspacing=6><tr><th></th><th>value</th><th>± 1σ</th>"
        html += f"<th>newest configuration ({prev.label})</th><th>change</th></tr>"
        prev_focus = optic_focus_of(prev, self.plate()) if prev.optics.optic_type == self.optic() else None
        for p in res.params:
            value = res.optic_focus if p == OPTIC_PARAM else getattr(res.config, p)
            old = prev_focus if p == OPTIC_PARAM else getattr(prev.config, p)
            sig = f"{res.sigma[p]:.4f}" if res.sigma else "–"
            change = "" if old is None else f"{value - old:+.4f}"
            html += (f"<tr><td>{PARAM_LABELS[p]}</td><td><b>{value:.4f}</b></td><td>{sig}</td><td>{_fmt(old)}</td>"
                     f"<td>{change}</td></tr>")
        html += "</table><b>Residuals of the sets</b> (model − measured, mm)<table cellspacing=6><tr><th>set</th>"
        html += "<th>ST</th><th>SZ</th><th>SN</th><th>optic</th></tr>"
        optic_res = dict(res.optic_residuals)
        for name, d_st, d_sz, d_sn in res.residuals:
            d_optic = optic_res.get(name)
            html += (f"<tr><td>{name}</td><td>{d_st:+.4f}</td><td>{d_sz:+.4f}</td><td>{d_sn:+.4f}</td>"
                     f"<td>{'' if d_optic is None else f'{d_optic:+.4f}'}</td></tr>")
        html += "</table>"
        if res.test_residuals:
            html += "<b>Residuals of the test points</b> (model − real, mm)<table cellspacing=6><tr><th>test point</th>"
            html += "<th>ST</th><th>SZ</th><th>optic</th></tr>"
            for name, d_st, d_sz, d_optic in res.test_residuals:
                html += (f"<tr><td>{name}</td><td>{d_st:+.4f}</td><td>{d_sz:+.4f}</td>"
                         f"<td>{'' if d_optic is None else f'{d_optic:+.4f}'}</td></tr>")
            html += "</table>"
        html += f"rms = {res.rms:.4f} mm, {res.dof} redundant equation(s).<br>"
        if res.optic_focus is None:
            html += (f"<span style='color:#b36b00'><b>No optic position entered:</b> the "
                     f"{self.optic_type.currentText()} reference is not calibrated (QuickAlignment then assumes the "
                     "optic focus on the analyzer focus).</span><br>")
        if res.dof <= 2 and not res.tests:
            html += "<span style='color:#b36b00'>Minimum data set: mistakes in a set cannot be detected. Measuring sets 4–5 is recommended.</span><br>"
        if res.rms > RMS_WARNING:
            html += f"<span style='color:#c00000'><b>Residuals above {RMS_WARNING} mm: check the entries with the largest residuals.</b></span><br>"
        self.result_label.setText(html)
        self._new_round()
        summary = self._round_summary()
        self.test_status.setText((summary + "<br>" if summary else "") + "Go to the positions of the new test points "
                                 "and tick <i>Found</i> or enter the real ST, SZ, optic; then correct the configuration.")
        self.save_btn.setEnabled(True)
        self.correct_btn.setEnabled(True)
        self.tabs.setTabText(1, f"Test points (round {self.tests[-1].round})")
        self._refresh_feature()

    def save(self) -> None:
        if self.result is None:
            return
        self.read_tests()  # answers of the last round, not fitted: kept in the record as the final check
        record = initial_record(
            self.result, self.plate(), self.ref_uvw(), self.optic(), self.comment.text().strip(),
            tests=[t for t in self.tests if t.answered], previous=self.previous().label,
        )
        saved = self.store.save(record)
        self.save_btn.setEnabled(False)
        self._show_previous()
        self.result_label.setText(
            self.result_label.text() + f"<br><b>Saved {saved.path.name}</b> — QuickAlignment loads it at the next start "
            f"when the {saved.optic_name} is chosen.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    win = InitialCalibrationWindow()
    win.show()
    return exec_app(app)
