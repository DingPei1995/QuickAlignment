import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE, Sample, SampleLayout  # noqa: E402
from quickalignment.ui.photo_dialog import PhotoImportDialog  # noqa: E402
from quickalignment.ui.plate_editor import PlateEditor  # noqa: E402

from test_photo import PHOTO_CORNERS, SAMPLES, synthetic_photo  # noqa: E402

QtCore, QtWidgets = qt.QtCore, qt.QtWidgets
Qt = QtCore.Qt

# photo of a gating plate with the RG_GMC substrate (cropped, downscaled), and its sample area corners
REAL_PHOTO = Path(__file__).parent / "data" / "gating_plate_photo.jpg"
REAL_CORNERS = [(200.0, 217.5), (617.5, 327.5), (465.0, 620.0), (127.5, 542.5)]


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_dialog_finds_and_returns_samples(app):
    img, _ = synthetic_photo()
    dlg = PhotoImportDialog(STANDARD_PLATE, 0.3, existing=["S1"])
    dlg.set_photo(img)
    assert not dlg.add_btn.isEnabled()
    dlg.set_corners(PHOTO_CORNERS)
    assert dlg.rectified is not None
    assert len(dlg.detections) == 3 and dlg.add_btn.isEnabled()
    # untick one, change the height of another
    dlg.table.item(1, 0).setCheckState(Qt.Unchecked)
    dlg.table.item(0, 6).setText("0.7")
    samples = dlg.samples()
    assert [s.name for s in samples] == ["S2", "S4"]  # S1 is taken on the plate
    assert samples[0].height == pytest.approx(0.7) and samples[1].height == pytest.approx(0.3)
    (u0, v0, u1, v1), _ = SAMPLES[0]
    assert samples[0].u == pytest.approx((u0 + u1) / 2, abs=0.1)
    assert samples[0].length == pytest.approx(u1 - u0, abs=0.15)
    # threshold change keeps the edits of the rows
    dlg.threshold.setValue(14)
    assert dlg.table.item(0, 6).text() == "0.700"


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
    dlg.set_photo(img)
    dlg.set_corners(PHOTO_CORNERS)
    dlg.table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
    dlg.table.selectRow(0)
    dlg.table.selectRow(1)
    dlg.merge_selected()
    assert len(dlg.detections) == 2
    d = dlg.detections[0]
    assert (d.u0, d.v1) == pytest.approx((-4.0, 4.0), abs=0.1) and (d.u1, d.v0) == pytest.approx((2.5, -1.0), abs=0.1)


def test_real_photo_by_sample_colour(app):
    dlg = PhotoImportDialog(GATING_PLATE, 0.525)
    assert dlg.load_photo(str(REAL_PHOTO))
    dlg.set_corners(REAL_CORNERS)
    # differing from the bare plate also takes the silver paint: the substrate is merged with it
    big = max(dlg.detections, key=lambda d: d.area)
    assert big.u0 < -5
    # picked on the black substrate: only the substrates are found
    assert dlg.pick_sample_color(3.65, 6.15)
    assert dlg.mode.currentIndex() == 1
    big = max(dlg.detections, key=lambda d: d.area)
    assert (big.u0, big.v0, big.u1, big.v1) == pytest.approx((-2.3, -0.55, 5.05, 7.15), abs=0.25)
    # the device found on the beam (fit of the capillary configuration) is on it
    assert big.u0 < 1.51 < big.u1 and big.v0 < 2.82 < big.v1


def test_editor_import(app):
    ed = PlateEditor(SampleLayout(samples=[Sample("S1", u=-3, v=3)]))
    ed.import_samples([Sample("S1", u=2, v=2), Sample("A", u=2, v=-3)])
    assert [s.name for s in ed.layout_model.samples] == ["S1", "S2", "A"]
    assert ed.table.rowCount() == 3
    ed.import_samples([Sample("B", u=0, v=0)], replace=True)
    assert [s.name for s in ed.layout_model.samples] == ["B"]
