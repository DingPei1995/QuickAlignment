import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE, Sample, SampleLayout  # noqa: E402
from quickalignment.ui.photo_dialog import BY_PLATE, BY_SAMPLE, PhotoImportDialog  # noqa: E402
from quickalignment.ui.plate_editor import PlateEditor  # noqa: E402

from quickalignment.photo import apply_homography  # noqa: E402
from test_photo import PHOTO_CORNERS, SAMPLES, synthetic_photo  # noqa: E402

QtCore, QtWidgets = qt.QtCore, qt.QtWidgets
Qt = QtCore.Qt

# photo of a gating plate with the RG_GMC substrate (cropped, downscaled), and its sample area corners
REAL_PHOTO = Path(__file__).parent / "data" / "gating_plate_photo.jpg"
REAL_CORNERS = [(207.5, 212.0), (543.5, 298.0), (466.5, 624.0), (128.0, 542.0)]


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_dialog_finds_and_returns_samples(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.3, existing=["S1"])
    assert dlg.mode.currentIndex() == BY_SAMPLE  # default: silver paint is not a sample
    dlg.mode.setCurrentIndex(BY_PLATE)
    dlg.set_photo(img)
    assert not dlg.add_btn.isEnabled()
    dlg.set_corners(PHOTO_CORNERS)
    assert dlg.rectified is not None
    assert len(dlg.detections) == 3 and dlg.add_btn.isEnabled()
    # delete one (not a sample), change the height of another
    dlg._select_row(1)
    dlg.delete_selected()
    dlg.table.item(0, 5).setText("0.7")
    samples = dlg.samples()
    assert [s.name for s in samples] == ["S2", "S4"]  # S1 is taken on the plate
    assert samples[0].height == pytest.approx(0.7) and samples[1].height == pytest.approx(0.3)
    (u0, v0, u1, v1), _ = SAMPLES[0]
    assert samples[0].u == pytest.approx((u0 + u1) / 2, abs=0.1)
    assert samples[0].length == pytest.approx(u1 - u0, abs=0.15)
    # threshold change keeps the edits of the rows
    dlg.threshold.setValue(14)
    assert dlg.table.item(0, 5).text() == "0.700"


def test_bad_corner_order_reported(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    dlg.set_photo(img)
    dlg.set_corners(PHOTO_CORNERS[::-1])
    assert dlg.rectified is None and dlg.detections == []
    assert "order" in dlg.instruction.text()


def test_merge_selected(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    dlg.mode.setCurrentIndex(BY_PLATE)
    dlg.set_photo(img)
    dlg.set_corners(PHOTO_CORNERS)
    dlg.table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
    dlg.table.selectRow(0)
    dlg.table.selectRow(1)
    dlg.merge_selected()
    assert len(dlg.detections) == 2
    d = next(x for x in dlg.detections if x.manual)
    assert dlg.samples()[[x.manual for x in dlg.detections].index(True)].name == "S1"
    # the merge is kept when the detection runs again
    dlg.threshold.setValue(13)
    assert len(dlg.detections) == 2 and any(x.manual for x in dlg.detections)
    assert (d.u0, d.v1) == pytest.approx((-4.0, 4.0), abs=0.1) and (d.u1, d.v0) == pytest.approx((2.5, -1.0), abs=0.1)


def test_real_photo_by_sample_colour(app):
    dlg = PhotoImportDialog(GATING_PLATE, 0.525)
    assert dlg.load_photo(str(REAL_PHOTO))
    dlg.mode.setCurrentIndex(BY_PLATE)
    dlg.set_corners(REAL_CORNERS)
    # differing from the bare plate also takes the silver paint: the substrate is merged with it
    big = max(dlg.detections, key=lambda d: d.area)
    assert big.u0 < -5
    # picked on the black substrate: only the substrates are found
    assert dlg.pick_sample_color(3.65, 6.15)
    assert dlg.mode.currentIndex() == 1
    big = max(dlg.detections, key=lambda d: d.area)
    assert (big.u0, big.v0, big.u1, big.v1) == pytest.approx((-1.85, -0.95, 5.5, 6.75), abs=0.25)
    # the device found on the beam (fit of the capillary configuration) is on it
    assert big.u0 < 1.51 < big.u1 and big.v0 < 2.82 < big.v1


def test_editor_import(app):
    ed = PlateEditor(SampleLayout(samples=[Sample("S1", u=-3, v=3)]))
    ed.import_samples([Sample("S1", u=2, v=2), Sample("A", u=2, v=-3)])
    assert [s.name for s in ed.layout_model.samples] == ["S1", "S2", "A"]
    assert ed.table.rowCount() == 3
    ed.import_samples([Sample("B", u=0, v=0)], replace=True)
    assert [s.name for s in ed.layout_model.samples] == ["B"]


def test_reference_points_numbered_in_plate_view(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    dlg.set_photo(img)
    states = lambda: [m.pen().color().name() for m in dlg.reg.ref_markers]  # noqa: E731
    assert states()[0] == "#e00000" and states()[1] == "#808080"  # point 1 next (red)
    assert "point 1" in dlg.instruction.text()
    for x, y in PHOTO_CORNERS[:2]:
        dlg.reg._on_photo_click(x, y)
    assert states()[:3] == ["#00b4ff", "#00b4ff", "#e00000"]
    assert "point 3" in dlg.instruction.text()
    for x, y in PHOTO_CORNERS[2:]:
        dlg.reg._on_photo_click(x, y)
    assert dlg.rectified is not None
    # a click on the registered photo picks a sample colour there (default mode, no colour yet)
    (u0, v0, u1, v1), _ = SAMPLES[0]
    (x, y), = apply_homography(dlg.reg.h, [((u0 + u1) / 2, (v0 + v1) / 2)])
    assert dlg.pick_sample_btn.isChecked()
    dlg.reg._on_photo_click(x, y)
    assert len(dlg.sample_colors) == 1 and len(dlg.detections) == 1
    d = dlg.detections[0]
    assert (d.u0, d.v0, d.u1, d.v1) == pytest.approx((u0, v0, u1, v1), abs=0.1)
    # cursor read-out in plate coordinates
    dlg.reg._show_cursor(-2.5, 3.0)
    assert "x =  -2.500" in dlg.reg.cursor_label.text() and "in S1" in dlg.reg.cursor_label.text()


def test_draw_delete_kept_on_redetection(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    dlg.mode.setCurrentIndex(BY_PLATE)
    dlg.set_photo(img)
    dlg.set_corners(PHOTO_CORNERS)
    assert len(dlg.detections) == 3
    # delete a wrong box (selected by clicking on it)
    dlg.select_at(1.5, 0.0)
    assert dlg._selected_rows() == [1]
    dlg.delete_selected()
    assert len(dlg.detections) == 2
    # draw a missing one by dragging in the right view
    dlg.draw_btn.setChecked(True)
    assert dlg.reg.plate_view.drag_enabled
    dlg.reg.plateDragged.emit(-5.0, -7.0, -3.02, -5.48)
    drawn = [d for d in dlg.detections if d.manual]
    assert len(drawn) == 1 and drawn[0].rect == pytest.approx((-5.0, -7.0, -3.0, -5.5))
    assert dlg.table.item(dlg.detections.index(drawn[0]), 7).text() == "drawn"
    assert dlg.table.columnCount() == 8 and dlg.table.horizontalHeaderItem(0).text() == "Name"
    names = [s.name for s in dlg.samples()]
    assert len(names) == len(set(names)) == 3
    # both edits survive a new detection, the names stay
    dlg.threshold.setValue(15)
    assert len(dlg.detections) == 3 and [s.name for s in dlg.samples()] == names
    dlg.undo_edits()
    assert len(dlg.detections) == 3 and not any(d.manual for d in dlg.detections)


def test_zoom_kept_when_view_resizes(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    dlg.show()
    dlg.set_photo(img)
    view = dlg.reg.photo_view
    app.processEvents()
    fit = view.transform().m11()
    for _ in range(8):
        view.wheelEvent(_Wheel(120))
        app.processEvents()
    view.resize(view.width() - 20, view.height() - 20)  # e.g. scroll bars appearing
    app.processEvents()
    assert view.transform().m11() > 3 * fit
    dlg.close()


class _Wheel:
    def __init__(self, dy):
        self.dy = dy

    def angleDelta(self):
        return QtCore.QPoint(0, self.dy)


def test_devices_from_second_photo_by_point_pairs(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.5)
    dlg.mode.setCurrentIndex(BY_PLATE)
    dlg.set_photo(img)
    dlg.set_corners(PHOTO_CORNERS)
    panel = dlg.devices_panel
    assert [n for n, _ in panel.substrates] == ["S1", "S2", "S3"]
    (u0, v0, u1, v1), _ = SAMPLES[0]
    panel.select_substrate("S1")
    assert panel.crop_item.pixmap().width() > 0
    # device photo: 200 px/mm, turned by 25°, not showing the substrate edges
    c, s_ = np.cos(np.radians(25)), np.sin(np.radians(25))
    t_true = np.array([[c, -s_, -2.5], [s_, c, 3.0], [0, 0, 1]]) @ np.diag([1 / 200, -1 / 200, 1])
    panel.set_photo(np.full((500, 700, 3), 90, np.uint8))
    dlg.tabs.setCurrentIndex(1)
    assert "point 1 on the left" in dlg.instruction.text()
    # pairs by clicking: left (plate photo crop, scene = (u, -v)) then right (device photo)
    plate_pts = [(-3.5, 2.5), (-1.5, 3.6), (-2.0, 2.2)]
    photo_pts = apply_homography(np.linalg.inv(t_true), plate_pts)
    for (u, v), (x, y) in zip(plate_pts[:2], photo_pts[:2]):
        panel._on_left_click(u, -v)
        assert "same point" in dlg.instruction.text()
        panel._on_right_click(x, y)
    assert panel.t is not None and "rotation + scale + shift" in panel.match_label.text()
    panel._on_left_click(*np.array(plate_pts[2]) * [1, -1])
    panel._on_right_click(*photo_pts[2])
    assert "affine" in panel.match_label.text() and panel.rms < 1e-6
    # devices clicked on the device photo get plate coordinates
    panel.device_radio.setChecked(True)
    target = (u0 + 0.8, v0 + 0.6)
    (x, y), = apply_homography(np.linalg.inv(t_true), [target])
    panel._on_right_click(x, y)
    assert len(panel.devices) == 1
    assert (panel.devices[0].u, panel.devices[0].v) == pytest.approx(target, abs=1e-6)
    assert panel.table.item(0, 1).text() == "S1" and dlg.table.item(0, 6).text() == "1"
    # dragging a point moves the devices of this photo with the matching
    panel.right_pts[0].setPos(panel.right_pts[0].pos() + QtCore.QPointF(10, 0))
    assert panel.devices[0].u != pytest.approx(target[0], abs=1e-6)
    panel.right_pts[0].setPos(panel.right_pts[0].pos() - QtCore.QPointF(10, 0))
    # a new device photo keeps the devices already placed
    panel.set_photo(np.zeros((100, 100, 3), np.uint8))
    assert panel.t is None and panel.devices[0].px is None
    assert panel.devices[0].u == pytest.approx(target[0], abs=1e-6)
    # added with the samples, relative to their substrate; no height
    sample = dlg.samples()[0]
    assert sample.name == "S1" and [d.name for d in sample.devices] == ["D1"]
    dev = sample.devices[0]
    assert dev.position(sample) == pytest.approx(target, abs=1e-3)
    assert not hasattr(dev, "height")


def test_plate_editor_zoom_kept(app):
    ed = PlateEditor()
    ed.show()
    app.processEvents()
    fit = ed.view.transform().m11()
    for _ in range(6):
        ed.view.wheelEvent(_Wheel(120))
    ed.view.resize(ed.view.width() - 20, ed.view.height())
    app.processEvents()
    assert ed.view.transform().m11() > 2 * fit
    ed.close()
