import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
from quickalignment.geometry import Device, Sample, SampleLayout  # noqa: E402
from quickalignment.session import Session  # noqa: E402
from quickalignment.app import MainWindow  # noqa: E402

QtCore, QtGui, QtWidgets = qt.QtCore, qt.QtGui, qt.QtWidgets

Qt = QtCore.Qt


@pytest.fixture
def window(monkeypatch):
    import quickalignment.app as app_module
    from quickalignment.geometry import STANDARD_PLATE

    monkeypatch.setattr(app_module, "ask_plate", lambda *a, **k: STANDARD_PLATE)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    app.processEvents()
    yield win
    win.close()


def to_view(win, u, v):
    return win.editor.view.mapFromScene(QtCore.QPointF(u, -v))


def send(widget, kind, pos, button, buttons):
    # QGraphicsScene hit-tests with the screen position, so it must be consistent
    local = QtCore.QPointF(pos)
    screen = QtCore.QPointF(widget.mapToGlobal(pos))
    event = QtGui.QMouseEvent(kind, local, local, screen, button, buttons, Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(widget, event)


def drag(widget, p0, p1):
    send(widget, QtCore.QEvent.MouseButtonPress, p0, Qt.LeftButton, Qt.LeftButton)
    for t in (0.25, 0.5, 0.75, 1.0):
        p = QtCore.QPoint(int(p0.x() + (p1.x() - p0.x()) * t), int(p0.y() + (p1.y() - p0.y()) * t))
        send(widget, QtCore.QEvent.MouseMove, p, Qt.NoButton, Qt.LeftButton)
    send(widget, QtCore.QEvent.MouseButtonRelease, p1, Qt.LeftButton, Qt.NoButton)


def test_draw_move_resize_and_edit(window):
    ed = window.editor
    vp = ed.view.viewport()
    drag(vp, to_view(window, -4, 4), to_view(window, -1, 2))
    assert len(ed.layout_model.samples) == 1
    s = ed.layout_model.samples[0]
    assert abs(s.length - 3) < 0.15 and abs(s.width - 2) < 0.15
    assert abs(s.u + 2.5) < 0.15 and abs(s.v - 3) < 0.15

    # move by dragging the middle
    drag(vp, to_view(window, s.u, s.v), to_view(window, s.u + 4, s.v - 5))
    assert abs(s.u - 1.5) < 0.15 and abs(s.v + 2) < 0.15
    assert abs(s.length - 3) < 0.15

    # resize from the right edge
    right = s.u + s.length / 2
    drag(vp, to_view(window, right, s.v), to_view(window, right + 1, s.v))
    assert abs(s.length - 4) < 0.15

    # table edit updates the model and the item
    ed.table.item(0, 6).setText("1.25")
    ed.table.item(0, 2).setText("0")
    assert s.height == 1.25 and s.u == 0
    assert ed.items[id(s)].pos().x() == 0
    assert ed.table.item(0, 8).text() == "ok"

    # second, overlapping sample is flagged
    ed.add_sample(Sample("X", u=0, v=s.v, length=1, width=1))
    assert "overlaps X" in ed.table.item(0, 8).text()

    ed.view.setFocus()
    ed.scene.clearSelection()
    ed.items[id(s)].setSelected(True)
    ed.delete_selected()
    assert [x.name for x in ed.layout_model.samples] == ["X"]


def test_replace_layout_with_selection(window, tmp_path):
    ed = window.editor
    ed.add_sample(Sample("A", u=-2, v=0, length=1, width=1))  # selected after add
    path = tmp_path / "layout.json"
    ed.layout_model.save(path)
    ed.set_layout(SampleLayout.load(path))
    assert [s.name for s in ed.layout_model.samples] == ["A"]
    window.new_session()
    assert ed.layout_model.samples == [] and ed.table.rowCount() == 0


def test_devices_follow_substrate_and_edges(window):
    ed = window.editor
    s = ed.add_sample(Sample("Sub", u=0, v=0, length=6, width=4, height=0.3))
    d = ed.add_device(s, Device("D1", "right", 1.0, "top", 0.5))
    assert d.position(s) == (2.0, 1.5)
    assert ed.table.item(0, 1).text() == "substrate (1)"
    # absolute coordinates: ST = ST0 - u, SZ = SZ0 - v, SN = SN_f + 5.0 + H
    assert ed.dev_table.item(0, 6).text() == "-2.000" and ed.dev_table.item(0, 7).text() == "38.500"
    assert ed.dev_table.item(0, 8).text() == "5.300"

    # moving the substrate in the table moves the device with it
    ed.table.item(0, 2).setText("-1.0")
    assert d.position(s) == (3.0, 1.5)
    assert ed.device_items[id(d)].pos().x() == pytest.approx(3.0)

    # switching the reference edge keeps the device in place
    ed.dev_table.cellWidget(0, 2).setCurrentText("left")
    assert d.x_edge == "left" and d.dx == pytest.approx(5.0)
    assert d.position(s) == pytest.approx((3.0, 1.5))

    # typing a distance moves it
    ed.dev_table.item(0, 5).setText("1.0")
    assert d.position(s) == pytest.approx((3.0, 1.0))
    ed.dev_table.item(0, 3).setText("9")
    assert ed.dev_table.item(0, 9).text() == "outside substrate"

    # dragging the marker updates the distances
    vp = ed.view.viewport()
    ed.dev_table.item(0, 3).setText("2")
    u, v = d.position(s)
    drag(vp, to_view(window, u, v), to_view(window, u + 1, v - 0.5))
    assert d.dx == pytest.approx(3.0, abs=0.15) and d.dy == pytest.approx(1.5, abs=0.15)
    assert s.u == 1.0  # the substrate did not move

    # deleting the substrate removes its devices
    ed.scene.clearSelection()
    ed.items[id(s)].setSelected(True)
    ed.delete_selected()
    assert ed.dev_table.rowCount() == 0 and not ed.device_items


def test_stage_panel_bring_to_focus_and_optics(window):
    ed, st = window.editor, window.stage
    s = ed.add_sample(Sample("Sub", u=2, v=-1, length=4, width=4, height=0.5))
    ed.add_device(s, Device("D1", "left", 1.0, "bottom", 1.0, 0.5, 0.5))
    st.refresh_targets()
    st.target_combo.setCurrentText("Sub/D1")
    st.motors.boxes["srz"].setValue(-5)
    st.bring_target_to_focus()
    res = st.last_result
    assert res.target == "Sub/D1"
    assert abs(res.hit[1]) < 1e-3 and abs(res.delta) < 1e-3
    assert "no move needed" in st.result_label.text()
    sn = st.motors.boxes["sn"].value()
    assert sn == pytest.approx(5.5, abs=0.2)

    st.motors.boxes["sn"].setValue(sn + 1.0)
    st.update_view()
    assert st.last_result.delta > 1.0
    assert "TOWARDS the sample" in st.result_label.text()

    # calibrated: optic position follows with the chosen sign
    st.cal_enabled.setChecked(True)
    st.cal_motors.set_value(st.motors.value())
    st.cal_sample_combo.setCurrentText("Sub")
    st._on_cal_sample()
    st.optic_pos.setValue(10.0)
    st.optic_dir.setCurrentIndex(1)  # + = upstream
    st.motors.boxes["sn"].setValue(sn)
    st.update_view()
    res = st.last_result
    assert res.delta < 0 and res.new_optic_position == pytest.approx(10.0 - res.delta, abs=1e-3)
    assert "AWAY from the sample" in st.result_label.text()


def test_session_roundtrip(window, tmp_path):
    ed, st = window.editor, window.stage
    s = ed.add_sample(Sample("Sub", u=1, v=1, length=3, width=3))
    ed.add_device(s, Device("D9", "right", 0.5, "top", 0.7))
    st.cfg_boxes["srz_offset_n"].setValue(0.25)
    st.cal_enabled.setChecked(True)
    st.optic_pos.setValue(3.5)
    st.motors.boxes["srn"].setValue(131)
    path = tmp_path / "session.json"
    window.session().save(path)
    window.new_session()
    assert ed.layout_model.samples == []
    window.set_session(Session.load(path))
    assert ed.layout_model.samples[0].devices[0].name == "D9"
    assert st.config().srz_offset_n == 0.25
    assert st.calibration().enabled and st.calibration().optic_position == 3.5
    assert st.motors.value().srn == 131


def test_absolute_coordinates_follow_config(window):
    ed, st = window.editor, window.stage
    ed.add_sample(Sample("A", u=1.0, v=2.0, length=2, width=2, height=0.4))
    assert ed.table.item(0, 2).text() == "-1.000" and ed.table.item(0, 3).text() == "38.000"
    assert ed.table.item(0, 7).text() == "5.400"
    st.cfg_boxes["st0"].setValue(0.5)
    st.cfg_boxes["sz0"].setValue(41.0)
    st.cfg_boxes["sn_f"].setValue(-0.2)
    assert ed.table.item(0, 2).text() == "-0.500" and ed.table.item(0, 3).text() == "39.000"
    assert ed.table.item(0, 7).text() == "5.200"
    # typing absolute values places the sample on the plate
    ed.table.item(0, 3).setText("41.0")
    assert ed.layout_model.samples[0].v == pytest.approx(0.0)


def test_gating_plate(window):
    from quickalignment.geometry import GATING_PLATE

    window.set_session(Session(layout=SampleLayout(plate=GATING_PLATE)))
    ed, st = window.editor, window.stage
    assert "Gating" in window.plate_label.text()
    ok = ed.add_sample(Sample("ok", u=0, v=2, length=3, width=3))
    low = ed.add_sample(Sample("low", u=0, v=-4, length=2, width=2))
    assert ed.layout_model.warnings(ok) == []
    assert "outside riser" in ed.layout_model.warnings(low)
    # beam on the contact block
    m = st.model().motors_for_target(-4.0, -7.0, GATING_PLATE.contact_block_top, srn=120, srz=0)
    st.motors.set_value(m)
    st.update_view()
    assert st.last_result.target == "contact block"


def test_change_plate_keeps_samples(window):
    from quickalignment.geometry import GATING_PLATE
    import quickalignment.app as app_module

    window.editor.add_sample(Sample("A", u=0, v=-5, length=2, width=2))
    app_module.ask_plate = lambda *a, **k: GATING_PLATE
    window.change_plate()
    assert window.editor.layout_model.plate.key == "gating"
    assert [s.name for s in window.editor.layout_model.samples] == ["A"]
    assert window.editor.table.item(0, 8).text() == "outside riser"


def test_calibration_dialog_opens(window):
    window.stage.open_calibration()
    assert window.stage.cal_dialog.isVisible()
    assert "OFF" in window.stage.cal_status.text()
    window.stage.cal_enabled.setChecked(True)
    assert "ON" in window.stage.cal_status.text()
