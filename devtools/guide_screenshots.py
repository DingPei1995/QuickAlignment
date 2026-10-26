"""Take the screenshots of the user and staff guides (``docs/images/guide/``).

Drives QuickAlignment and InitialCalibration off-screen. The user guide follows
one real example: the gating plate photo of the tests (substrate RG_GMC, device
R7G on the microscope photo), found, then turned to SRn 92 / SRz -24 as on the
beamtime, with the newest capillary configuration of ``configs/``;
InitialCalibration works on a temporary copy of the configurations, so nothing
is written to ``configs/``.

Nothing here is part of the program; run it by hand after a change of the
interface, then rebuild the PDFs (``devtools/build_guides.py``).

Usage:  python devtools/guide_screenshots.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from io import BytesIO
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from quickalignment.calibration import CalibrationStore  # noqa: E402
from quickalignment.geometry import STANDARD_PLATE, SampleLayout  # noqa: E402
from quickalignment.rotation import AnalyzerGeometry, analyzer_angles, plate_to_lab_dir  # noqa: E402
from quickalignment.session import Session  # noqa: E402
from quickalignment.stage import MotorPositions, StageModel  # noqa: E402
from quickalignment import bz_target as bt  # noqa: E402
from quickalignment.ui._qt import QtCore, QtGui, QtWidgets  # noqa: E402

OUT = HERE / "docs" / "images" / "guide"
Qt = QtCore.Qt


def settle(app, n: int = 5) -> None:
    for _ in range(n):
        app.processEvents()


def save(widget, name: str, app) -> None:
    settle(app)
    widget.grab().save(str(OUT / f"{name}.png"))
    print("wrote", name)


def hide_tmp_folder(win) -> None:
    """The screenshots run on a temporary copy of configs/: show the real folder name."""
    for label in win.findChildren(QtWidgets.QLabel):
        if str(win.store.folder) in label.text():
            label.setText(label.text().replace(str(win.store.folder), "QuickAlignment/configs"))


def top_view(stage, half: float = 6.0) -> QtGui.QImage:
    """The top view of the Stage tab schematic (left axes of its figure), zoomed on the analyzer focus (origin of
    the view, +/- `half` mm), with the analyzer focus and the beam spot named."""
    ax = stage.figure.axes[0]
    ax.set_xlim(-half, half)
    ax.set_ylim(-half * 0.75, half * 1.25)
    hit = stage.last_result.hit
    ax.annotate("analyzer focus", (0, 0), (-1.0, -2.2), color="#1f77b4", fontsize=9, ha="right",
                arrowprops=dict(arrowstyle="-", color="#1f77b4", lw=0.8))
    ax.annotate("beam spot on R7G", (hit[0], hit[1]), (2.0, hit[1] + 2.5), color="#d62728", fontsize=9,
                arrowprops=dict(arrowstyle="-", color="#d62728", lw=0.8))
    for text in ax.texts:
        text.set_clip_on(True)
    fig = stage.figure
    fig.canvas.draw()
    box = Bbox.union([ax.bbox, ax.title.get_window_extent(fig.canvas.get_renderer())])
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=2.2 * fig.dpi, bbox_inches=box.transformed(fig.dpi_scale_trans.inverted()),
                pad_inches=0.05)
    img = QtGui.QImage.fromData(buf.getvalue())
    stage.update_view()  # back to the normal view
    return img


def correct_sn_figure(kept: QtGui.QImage, corrected: QtGui.QImage) -> None:
    """Side by side: the top view with SN kept and with SN corrected, after the same rotation."""
    gap, head = 50, 70
    w, h = kept.width() + corrected.width() + gap, max(kept.height(), corrected.height()) + head
    out = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
    out.fill(QtGui.QColor("white"))
    p = QtGui.QPainter(out)
    font = p.font()
    font.setPixelSize(36)
    font.setBold(True)
    p.setFont(font)
    for x, img, text, colour in ((0, kept, "SN kept: 2.0 mm from the analyzer focus", "#b00000"),
                                 (kept.width() + gap, corrected, "Correct SN: on the analyzer focus", "#207020")):
        p.setPen(QtGui.QColor(colour))
        p.drawText(QtCore.QRectF(x, 0, img.width(), head), Qt.AlignCenter, text)
        p.drawImage(x, head, img)
    p.end()
    out.save(str(OUT / "correct_sn.png"))
    print("wrote correct_sn")


def grab_question(app, name: str):
    """QMessageBox.question replacement: shows the question, saves its screenshot as `name` and answers Yes."""
    def question(parent, title, text, buttons=None, default=None):
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question, title, text,
                                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, parent)
        box.show()
        save(box, name, app)
        box.close()
        return QtWidgets.QMessageBox.Yes
    return question


def refuse_warning(parent, title, text, *args, **kwargs):
    """A warning box would wait for a click: stop instead (the example must stay reachable)."""
    raise RuntimeError(f"{title}: {text}")


def quickalignment_shots(app, store: CalibrationStore) -> None:
    """One example all along: the gating plate of the tests (RG_GMC, device R7G; capillary), samples from the
    photo, start positions, R7G found, then turned to SRn 92 / SRz -24 as on the beamtime (2026-10-24)."""
    from quickalignment.app import MainWindow
    from quickalignment.geometry import GATING_PLATE
    from quickalignment.ui.photo_dialog import NAME, PhotoImportDialog
    from quickalignment.ui.plate_choice import PlateChoiceDialog

    QtWidgets.QMessageBox.warning = staticmethod(refuse_warning)
    dlg = PlateChoiceDialog("gating", optic="capillary")
    dlg.show()
    save(dlg, "setup_dialog", app)
    dlg.close()

    win = MainWindow(Session(SampleLayout(plate=GATING_PLATE, samples=[])), store=store, optic="capillary")
    win.resize(1450, 860)
    win.show()
    editor = win.editor

    # samples from a photo: the gating plate photo of the tests, colour picked on the substrate; the pieces of
    # the small chip (broken up by the silver paint) merged by hand
    sys.path.insert(0, str(HERE / "tests"))
    from test_photo_dialog import REAL_CORNERS, REAL_PHOTO

    photo = PhotoImportDialog(GATING_PLATE, 0.525)
    photo.resize(1400, 900)
    photo.show()
    photo.load_photo(str(REAL_PHOTO))
    photo.file_label.setText(REAL_PHOTO.name)
    photo.set_corners(REAL_CORNERS)
    photo.pick_sample_color(3.65, 6.15)
    photo.table.item(0, NAME).setText("RG_GMC")
    photo.table.clearSelection()
    for row in range(1, photo.table.rowCount()):
        photo.table.selectionModel().select(photo.table.model().index(row, 0),
                                            QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
    photo.merge_selected()
    photo.table.clearSelection()
    settle(app)
    photo.reg.photo_view.fit()
    photo.reg.plate_view.fit()
    photo.reg._show_cursor(1.71, 3.09)
    save(photo, "photo_dialog", app)

    # tab 2, devices from a second photo: the microscope photo of the substrate centre. Matched points: the
    # silver paint dot above the centre and the centre circle (black blob and round purple pad under the
    # microscope); device R7G clicked on the flake of the channel between them
    panel = photo.devices_panel
    photo.tabs.setCurrentIndex(1)
    panel.select_substrate("RG_GMC")
    device_photo = HERE / "tests" / "data" / "gating_device_photo.jpg"
    panel.load_photo(str(device_photo))
    panel.file_label.setText(device_photo.name)
    panel.set_pairs([(1.51, 3.66), (1.73, 2.49)], [(235.5, 103.9), (279.1, 328.1)])
    panel.device_radio.setChecked(True)
    panel._on_right_click(275.0, 213.0)
    panel.devices[0].name = "R7G"
    panel._fill_table()
    photo._on_devices_changed()
    settle(app)
    panel.right_view.fit()
    r7g = panel.devices[0]
    panel._show_cursor(r7g.u, r7g.v)
    save(photo, "photo_devices", app)
    editor.import_samples(photo.samples())
    photo.close()

    editor._select_rows(editor.dev_table, [0])
    editor._on_dev_table_selection()
    save(win, "samples_tab", app)

    # samples placed -> start positions in the Stage & Optics tab; R7G brought onto the beam at SRn 120, SRz 0
    win.resize(1450, 1000)
    win.go_to_stage()
    st = win.stage
    target = "RG_GMC/R7G"
    st.target_combo.setCurrentText(target)
    st.found_combo.setCurrentText(target)
    st.motors.set_value(MotorPositions(st=0.0, sn=0.0, sz=40.0, srn=120, srz=0))
    st.bring_target_on_beam()
    m = st.motors.value()
    st.optic_pos.setValue(round(st.last_result.required_optic_position + 0.35, 2))
    st.update_view()
    save(win, "stage_tab", app)

    # R7G found a little off the listed position (the photo is good to 0.1-0.3 mm): Found here. The found
    # position is where the beamtime configuration puts R7G (the device position it was fitted with)
    W = GATING_PLATE.total_thickness + 0.525
    f_st, f_sz, f_sn = st.model().reference_motors(1.51, 2.82, W)
    st.motors.set_value(MotorPositions(st=round(f_st, 4), sn=round(f_sn, 4), sz=round(f_sz, 4), srn=120, srz=0))
    st.update_view()
    st.use_required_optic()
    question = QtWidgets.QMessageBox.question
    QtWidgets.QMessageBox.question = grab_question(app, "found_here")
    st.correct_from_found()
    QtWidgets.QMessageBox.question = question
    st.update_view()

    # Rotate sample tab: to SRn 92, SRz -24 (the second rotation of the beamtime)
    win.resize(1450, 860)
    win.tabs.setCurrentWidget(win.rotation)
    rp = win.rotation
    rp.copy_from_stage()
    rp.new_srn.setValue(92.0)
    rp.new_srz.setValue(-24.0)
    rp.compute()
    rp.correct_sn.setChecked(True)
    save(win, "rotate_tab", app)

    # the SN-kept solution (2.0 mm from the analyzer focus) and the corrected one sent to the Stage tab: R7G on
    # the beam again (the beamtime found it at ST -6.048, SZ 38.988 with SN kept); the corrected one is shown
    win.resize(1450, 1000)
    rp.correct_sn.setChecked(False)
    rp.send_to_stage()
    kept = top_view(st)
    rp.correct_sn.setChecked(True)
    rp.send_to_stage()
    st.target_combo.setCurrentText(target)
    st.bring_target_to_focus()
    win.tabs.setCurrentWidget(st)
    save(win, "rotate_found", app)
    correct_sn_figure(kept, top_view(st))

    # BZ window: graphene K, map at SRn 120 / SRz 0, 95 eV
    QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)
    model, geo = st.model(), AnalyzerGeometry()
    m0 = MotorPositions(srn=120, srz=0)
    a, hv = 2.46, 95.0
    n = np.array([0.02, -0.015, 1.0])
    n /= np.linalg.norm(n)
    e1 = np.array([np.cos(np.radians(12)), np.sin(np.radians(12)), 0.0])
    e1 -= (e1 @ n) * n
    e1 /= np.linalg.norm(e1)
    s = bt.gamma_k(a) / bt.k0(hv)
    lab = plate_to_lab_dir(model, 120, 0)
    gamma = analyzer_angles(geo, lab @ n)
    ref = analyzer_angles(geo, lab @ (np.sqrt(1 - s * s) * n + s * e1))
    rp.measured.set_value(MotorPositions(st=m.st, sn=m.sn, sz=m.sz, srn=120, srz=0))
    rp.open_bz_target()
    d = rp._bz_dialog
    d.take_current()
    d.material.setCurrentText("Graphene")
    d.hv_map.setValue(hv)
    d.hv.setValue(hv)
    d.gamma_th.setValue(round(gamma[0], 2))
    d.gamma_ph.setValue(round(gamma[1], 2))
    d.ref_th.setValue(round(ref[0], 2))
    d.ref_ph.setValue(round(ref[1], 2))
    d.feature.setCurrentIndex(1)
    d.line.setCurrentIndex(0)
    d.compute()
    save(d, "bz_reachable", app)
    d.line.setCurrentIndex(1)
    d.hv.setValue(60.0)
    d.compute()
    save(d, "bz_zone_edge", app)
    d.hv.setValue(95.0)
    d.line.setCurrentIndex(0)
    d.hv.setValue(30.0)
    d.compute()
    save(d, "bz_photon_energy", app)
    d.close()

    win.open_calibration()
    win.cal_dialog.store = store
    hide_tmp_folder(win.cal_dialog)
    save(win.cal_dialog, "configuration_dialog", app)
    win.cal_dialog.close()
    win.close()


def calibration_shots(app, store: CalibrationStore) -> None:
    from quickalignment.ui.initial_calibration_window import (
        T_FOUND, T_OPTIC, T_ST, T_SZ, InitialCalibrationWindow, ModeDialog,
    )
    from quickalignment.initial_calibration import on_beam

    dlg = ModeDialog(store)
    dlg.show()
    save(dlg, "ic_mode", app)
    dlg.close()

    base = store.latest("capillary")
    truth_cfg = base.config.__class__(**{**base.config.__dict__, "st0": base.config.st0 + 0.04,
                                         "sz0": base.config.sz0 - 0.03})
    truth = StageModel(truth_cfg, STANDARD_PLATE)
    uvw, focus = (1.2, -0.8, STANDARD_PLATE.total_thickness + 0.6), 60.1
    rng = np.random.default_rng(1)

    win = InitialCalibrationWindow(store, "full")
    win.resize(1500, 1000)
    win.show()
    win.ref_x.setValue(uvw[0])
    win.ref_y.setValue(uvw[1])
    win.ref_h.setValue(0.6)
    win.optic_type.setCurrentIndex(win.optic_type.findText("capillary", Qt.MatchFixedString))
    hide_tmp_folder(win)
    for row in range(win.table.rowCount()):
        srn, srz = float(win.table.item(row, 2).text()), float(win.table.item(row, 3).text())
        mm = truth.motors_for_target(*uvw, srn=srn, srz=srz)
        noise = rng.normal(0, 0.004, 3)
        for col, value, e in ((4, mm.st, noise[0]), (5, mm.sz, noise[1]), (6, mm.sn, noise[2])):
            win.table.item(row, col).setText(f"{value + e:.4f}")
        st_, sz_, optic = on_beam(truth, uvw, srn, srz, mm.sn, mm.pix, mm.piy, focus)
        win.table.item(row, 7).setText(f"{optic + rng.normal(0, 0.003):.4f}")
    win.compute()
    save(win, "ic_window", app)

    # first round of test points: some found, some entered
    for row in range(win.test_table.rowCount()):
        t = win.tests[row]
        st_, sz_, optic = on_beam(truth, uvw, t.srn, t.srz, t.sn, t.pix, t.piy, focus)
        if row % 2 == 0:
            win.test_table.item(row, T_FOUND).setCheckState(Qt.Checked)
        else:
            for col, value in ((T_ST, st_ + 0.012), (T_SZ, sz_ - 0.008), (T_OPTIC, optic)):
                win.test_table.item(row, col).setText(f"{value:.4f}")
    win.tabs.setCurrentIndex(1)
    save(win, "ic_tests", app)

    win.show_feature()
    win.feature_dialog.resize(1100, 700)
    save(win.feature_dialog, "ic_feature", app)
    win.feature_dialog.close()
    win.close()

    win = InitialCalibrationWindow(store, "optics")
    win.resize(1500, 1000)
    win.show()
    win.ref_x.setValue(uvw[0])
    win.ref_y.setValue(uvw[1])
    win.ref_h.setValue(0.6)
    win.optic_type.setCurrentIndex(win.optic_type.findText("capillary", Qt.MatchFixedString))
    hide_tmp_folder(win)
    save(win, "ic_optics", app)
    win.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "configs"
        shutil.copytree(HERE / "configs", folder)
        store = CalibrationStore(folder)
        quickalignment_shots(app, store)
        calibration_shots(app, store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
