"""Take the screenshots of the user and staff guides (``docs/images/guide/``).

Drives QuickAlignment and InitialCalibration off-screen with an example
plate (standard plate, three samples, one substrate with two devices) and the
newest capillary configuration of ``configs/``; InitialCalibration works on a
temporary copy of the configurations, so nothing is written to ``configs/``.

Nothing here is part of the program; run it by hand after a change of the
interface, then rebuild the PDFs (``devtools/build_guides.py``).

Usage:  python devtools/guide_screenshots.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from quickalignment.calibration import CalibrationStore  # noqa: E402
from quickalignment.geometry import STANDARD_PLATE, Device, Sample, SampleLayout  # noqa: E402
from quickalignment.rotation import AnalyzerGeometry, analyzer_angles, plate_to_lab_dir  # noqa: E402
from quickalignment.session import Session  # noqa: E402
from quickalignment.stage import MotorPositions, StageModel  # noqa: E402
from quickalignment import bz_target as bt  # noqa: E402
from quickalignment.ui._qt import QtCore, QtWidgets  # noqa: E402

OUT = HERE / "docs" / "images" / "guide"
Qt = QtCore.Qt


def settle(app, n: int = 5) -> None:
    for _ in range(n):
        app.processEvents()


def save(widget, name: str, app) -> None:
    settle(app)
    widget.grab().save(str(OUT / f"{name}.png"))
    print("wrote", name)


def example_layout() -> SampleLayout:
    chip = Sample("Chip", u=-1.5, v=1.5, length=4.0, width=4.0, height=0.525,
                  devices=[Device("D1", "left", 2.6, "top", 1.0), Device("D2", "right", 1.1, "bottom", 0.9)])
    return SampleLayout(plate=STANDARD_PLATE, samples=[
        Sample("WSe2", u=3.0, v=3.2, length=2.0, width=1.6, height=0.3),
        chip,
        Sample("Au ref", u=3.2, v=-2.6, length=1.5, width=1.5, height=0.2),
    ])


def hide_tmp_folder(win) -> None:
    """The screenshots run on a temporary copy of configs/: show the real folder name."""
    for label in win.findChildren(QtWidgets.QLabel):
        if str(win.store.folder) in label.text():
            label.setText(label.text().replace(str(win.store.folder), "QuickAlignment/configs"))


def quickalignment_shots(app, store: CalibrationStore) -> None:
    from quickalignment.app import MainWindow
    from quickalignment.ui.plate_choice import PlateChoiceDialog

    dlg = PlateChoiceDialog("standard", optic="capillary")
    dlg.show()
    save(dlg, "setup_dialog", app)
    dlg.close()

    win = MainWindow(Session(example_layout()), store=store, optic="capillary")
    win.resize(1450, 860)
    win.show()
    editor = win.editor
    editor._select_rows(editor.dev_table, [0])
    editor._on_dev_table_selection()
    save(win, "samples_tab", app)

    # samples from a photo: the gating plate photo of the tests, colour picked on the substrate
    from quickalignment.geometry import GATING_PLATE
    from quickalignment.ui.photo_dialog import PhotoImportDialog

    sys.path.insert(0, str(HERE / "tests"))
    from test_photo_dialog import REAL_CORNERS, REAL_PHOTO

    photo = PhotoImportDialog(GATING_PLATE, 0.525)
    photo.resize(1400, 900)
    photo.show()
    photo.load_photo(str(REAL_PHOTO))
    photo.file_label.setText(REAL_PHOTO.name)
    photo.set_corners(REAL_CORNERS)
    photo.pick_sample_color(3.65, 6.15)
    settle(app)
    photo.reg.photo_view.fit()
    photo.reg.plate_view.fit()
    photo.reg._show_cursor(1.51, 2.82)
    save(photo, "photo_dialog", app)

    # tab 2, devices from a second photo. Stand-in for a closer photo: a crop of the same photo around the
    # substrate, turned by 90°, so the matched points (paint dots, centre hole) are surely the same; device R7G
    # clicked where the capillary configuration fit puts it
    from quickalignment.photo import apply_homography

    panel = photo.devices_panel
    photo.tabs.setCurrentIndex(1)
    panel.select_substrate("S1")
    corners = apply_homography(photo.reg.h, [(-1.75, -0.95), (5.5, -0.95), (5.5, 6.8), (-1.75, 6.8)])
    x0, y0 = (int(c) for c in corners.min(axis=0))
    x1, y1 = (int(c) + 1 for c in corners.max(axis=0))
    crop = photo.reg.photo[y0:y1, x0:x1]
    panel.set_photo(np.ascontiguousarray(np.rot90(crop, k=-1)))  # clockwise: (x, y) -> (height - y, x)
    panel.file_label.setText("close-up (stand-in)")
    plate_pts = [(1.85, 2.52), (1.54, 3.81), (2.82, 1.38), (0.75, 1.45)]
    xy = apply_homography(photo.reg.h, plate_pts) - (x0, y0)
    panel.set_pairs(plate_pts, [(crop.shape[0] - y, x) for x, y in xy])
    panel.device_radio.setChecked(True)
    (x, y), = apply_homography(photo.reg.h, [(1.51, 2.82)]) - (x0, y0)
    panel._on_right_click(crop.shape[0] - y, x)
    panel.devices[0].name = "R7G"
    panel._fill_table()
    photo._on_devices_changed()
    settle(app)
    panel.right_view.fit()
    panel._show_cursor(1.51, 2.82)
    save(photo, "photo_devices", app)
    photo.close()

    # samples placed -> start positions in the Stage & Optics tab
    win.resize(1450, 1000)
    win.go_to_stage()
    st = win.stage
    st.target_combo.setCurrentText("Chip/D1")
    m = st.motors.value()
    st.motors.set_value(MotorPositions(st=m.st, sn=m.sn, sz=m.sz, srn=120, srz=0))
    st.bring_target_to_focus()
    st.optic_pos.setValue(st.last_result.required_optic_position + 0.35)
    st.update_view()
    save(win, "stage_tab", app)

    # Rotate sample tab
    win.resize(1450, 860)
    win.tabs.setCurrentWidget(win.rotation)
    rp = win.rotation
    rp.copy_from_stage()
    rp.new_srn.setValue(140.0)
    rp.new_srz.setValue(-12.0)
    rp.compute()
    rp.correct_sn.setChecked(True)
    save(win, "rotate_tab", app)

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
