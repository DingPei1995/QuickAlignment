import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
from dataclasses import replace  # noqa: E402

from quickalignment.geometry import Device, Sample, SampleLayout  # noqa: E402
from quickalignment.session import Session  # noqa: E402
from quickalignment.app import MainWindow  # noqa: E402

QtCore, QtGui, QtWidgets = qt.QtCore, qt.QtGui, qt.QtWidgets

Qt = QtCore.Qt


@pytest.fixture
def window(monkeypatch, tmp_path):
    import quickalignment.app as app_module
    from quickalignment.calibration import CalibrationStore
    from quickalignment.geometry import STANDARD_PLATE

    monkeypatch.setattr(app_module, "ask_plate", lambda *a, **k: STANDARD_PLATE)
    # closing asks whether to save the configuration: answer "Discard" unless a test says otherwise
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow(store=CalibrationStore(tmp_path / "configs"))
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
    assert ed.table.item(0, 7).text() == "ok"

    # second, overlapping sample is flagged
    ed.add_sample(Sample("X", u=0, v=s.v, length=1, width=1))
    assert "overlaps X" in ed.table.item(0, 7).text()

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
    # plate coordinates of the device centre
    assert ed.dev_table.item(0, 6).text() == "2.000" and ed.dev_table.item(0, 7).text() == "1.500"

    # moving the substrate in the table moves the device with it
    ed.table.item(0, 2).setText("1.0")
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
    assert ed.dev_table.item(0, 8).text() == "outside substrate"

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
    assert "in focus on Sub/D1" in st.result_label.text()
    sn = st.motors.boxes["sn"].value()
    assert sn == pytest.approx(0.5, abs=0.2)  # SN = SN_f + H

    # optic position comes from the configuration; results are absolute positions
    st.optic_pos.setValue(3.0)
    st.update_view()
    assert st.last_result.required_optic_position == pytest.approx(0.0, abs=1e-3)
    assert "Optic position for focus on Sub/D1: " in st.result_label.text()
    assert "(entered: 3.0000)" in st.result_label.text()
    st.use_required_optic()
    assert st.optic_pos.value() == pytest.approx(0.0, abs=1e-3)

    st.motors.boxes["sn"].setValue(sn + 1.0)
    st.update_view()
    assert st.last_result.delta > 1.0
    assert st.last_result.required_optic_position == pytest.approx(st.last_result.hit[1], abs=1e-6)

    # measured optics reference: optic position follows with the chosen sign
    from dataclasses import replace

    from quickalignment.calibration import CalibrationRecord
    from quickalignment.stage import OpticsCalibration

    cal = OpticsCalibration(enabled=True, motors=st.motors.value(), surface_w=5.5, optic_position=10.0, optic_sign=-1)
    window._on_record(replace(CalibrationRecord(), optics=cal))
    assert st.optic_pos.value() == 10.0  # loaded from the configuration
    st.motors.boxes["sn"].setValue(sn)
    st.update_view()
    res = st.last_result
    assert res.delta < 0 and res.required_optic_position == pytest.approx(10.0 - res.delta, abs=1e-3)

    # the user focuses by hand and takes this state as the optics reference
    st.optic_pos.setValue(9.5)
    st.set_optics_reference()
    assert st.record.optics.optic_position == 9.5 and st.record.optics.motors.sn == pytest.approx(sn)
    assert "in focus" in st.result_label.text()


def test_user_config_saved_on_close_and_loaded_first(window, monkeypatch):
    from datetime import datetime

    from quickalignment.calibration import CalibrationRecord
    from quickalignment.stage import StageConfig

    st, store = window.stage, window.store
    store.save(CalibrationRecord(comment="staff", config=StageConfig(st0=0.4)), now=datetime(2026, 1, 1))
    window._on_record(store.latest())
    st.optic_type.setCurrentText("capillary")
    st.optic_pos.setValue(7.25)

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Save)
    window.close()
    path = store.folder / "user_config.json"
    text = path.read_text()
    assert text.lstrip().startswith('{\n  "created": "')  # time stamp first
    user = store.latest()
    assert user.kind == "user" and user.config.st0 == 0.4
    assert user.optics.optic_type == "capillary" and user.optics.current_position == 7.25
    assert "based on 2026-01-01 00:00:00" in user.comment

    # saving again overwrites the same file; a newer staff calibration wins at start-up
    store.save_user(user)
    assert len(list(store.folder.glob("user_config*.json"))) == 1
    store.save(CalibrationRecord(comment="new staff"), now=datetime(2100, 1, 1))
    assert store.latest().comment == "new staff"

    # Discard leaves the file untouched, Cancel keeps the window open
    window.show()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Cancel)
    window.close()
    assert window.isVisible()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)
    before = path.read_text()
    window.close()
    assert path.read_text() == before


def test_session_roundtrip(window, tmp_path):
    ed, st = window.editor, window.stage
    s = ed.add_sample(Sample("Sub", u=1, v=1, length=3, width=3))
    ed.add_device(s, Device("D9", "right", 0.5, "top", 0.7))
    st.motors.boxes["srn"].setValue(131)
    path = tmp_path / "session.json"
    window.session().save(path)
    window.new_session()
    assert ed.layout_model.samples == []
    window.set_session(Session.load(path))
    assert ed.layout_model.samples[0].devices[0].name == "D9"
    assert st.motors.value().srn == 131


def test_stage_results_use_absolute_coordinates(window):
    ed, st = window.editor, window.stage
    ed.add_sample(Sample("A", u=1.0, v=2.0, length=2, width=2, height=0.4))
    st.refresh_targets()
    st.target_combo.setCurrentText("A")
    st.bring_target_to_focus()
    m = st.motors.value()
    # ST = ST0 - x, SZ = SZ0 - y, SN = SN_f + H
    assert (m.st, m.sz, m.sn) == pytest.approx((-1.0, 38.0, 0.4), abs=1e-4)
    assert "ST = -1.000, SZ = 38.000, SN = 0.400" in st.result_label.text()


def test_gating_plate(window):
    from quickalignment.geometry import GATING_PLATE

    window.set_session(Session(layout=SampleLayout(plate=GATING_PLATE)))
    ed, st = window.editor, window.stage
    assert "Gating" in window.plate_label.text()
    ok = ed.add_sample(Sample("ok", u=0, v=2, length=3, width=3))
    low = ed.add_sample(Sample("low", u=0, v=-4, length=2, width=2))
    assert ed.layout_model.warnings(ok) == []
    assert "outside sample area" in ed.layout_model.warnings(low)
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
    assert window.editor.table.item(0, 7).text() == "outside sample area"


def test_calibration_check_and_accept(window):
    ed, st, dlg = window.editor, window.stage, window.cal_dialog
    ed.add_sample(Sample("Au", u=-2.0, v=3.0, length=2, width=2, height=0.5))
    st.refresh_targets()
    window.open_calibration()
    assert dlg.isVisible() and "default" in window.cal_label.text()
    # constants locked unless expert mode
    assert not dlg.cfg_boxes["st0"].isEnabled()
    dlg.expert.setChecked(True)
    assert dlg.cfg_boxes["st0"].isEnabled()
    dlg.expert.setChecked(False)

    # reference found 0.1 mm off in ST and SN
    dlg.ref_combo.setCurrentText("Au")
    nominal = st.model().motors_for_target(-2.0, 3.0, 5.5, srn=120, srz=0)
    found = replace(nominal, st=nominal.st + 0.1, sn=nominal.sn + 0.1)
    dlg.measured.set_value(found)
    dlg.measured_optic.setValue(7.5)
    dlg.run_check()
    assert dlg.accept_btn.isEnabled()
    assert "+0.1000" in dlg.check_label.text()
    assert st.record.config.st0 == 0.0  # nothing changes before accepting
    dlg.accept_check()
    rec = st.record
    assert rec.path is not None and rec.path.exists()
    assert rec.config.st0 == pytest.approx(0.1, abs=1e-4) and rec.config.sn_f == pytest.approx(0.1, abs=1e-4)
    assert rec.optics.enabled and rec.optics.optic_position == 7.5
    assert rec.created in window.cal_label.text()
    # the new file is what a fresh start loads
    assert window.store.latest().created == rec.created

    # expert edit saves another configuration
    dlg.expert.setChecked(True)
    dlg.cfg_boxes["srz_offset_n"].setValue(0.3)
    dlg.save_expert()
    assert st.record.config.srz_offset_n == 0.3 and not dlg.expert.isChecked()
    assert len(window.store.records()) == 2


def test_initial_calibration_window(tmp_path):
    from quickalignment.calibration import CalibrationStore
    from quickalignment.geometry import STANDARD_PLATE
    from quickalignment.stage import StageConfig, StageModel
    from quickalignment.ui.initial_calibration_window import InitialCalibrationWindow

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    store = CalibrationStore(tmp_path / "configs")
    win = InitialCalibrationWindow(store)
    assert win.table.rowCount() == 5

    # empty table: incomplete sets are reported, nothing to save
    win.compute()
    assert "Incomplete" in win.result_label.text() and not win.save_btn.isEnabled()

    truth = StageModel(StageConfig(st0=0.2, sz0=40.3, sn_f=-0.1, srn_axis_u=0.5, srz_offset_n=-0.3), STANDARD_PLATE)
    win.ref_x.setValue(1.0)
    win.ref_y.setValue(-0.5)
    win.ref_h.setValue(0.3)
    for row in range(5):
        srn, srz = float(win.table.item(row, 2).text()), float(win.table.item(row, 3).text())
        m = truth.motors_for_target(1.0, -0.5, 5.3, srn=srn, srz=srz)
        for col, value in ((4, m.st), (5, m.sz), (6, m.sn)):
            win.table.item(row, col).setText(f"{value:.6f}")

    # only 2 sets ticked -> not enough data
    for row in range(2, 5):
        win.table.item(row, 0).setCheckState(Qt.Unchecked)
    win.compute()
    assert "Not enough data" in win.result_label.text()

    for row in range(2, 5):
        win.table.item(row, 0).setCheckState(Qt.Checked)
    win.optic_pos.setValue(4.2)
    win.compute()
    assert win.save_btn.isEnabled()
    assert win.result.config.st0 == pytest.approx(0.2, abs=1e-5)
    assert win.result.config.srz_offset_n == pytest.approx(-0.3, abs=1e-5)
    win.save()
    rec = store.latest()
    assert rec.config.srn_axis_u == pytest.approx(0.5, abs=1e-5)
    assert rec.optics.enabled and rec.optics.optic_position == 4.2
    assert "Saved" in win.result_label.text()
    win.close()


def test_rotation_tab_from_viewer_metadata(window):
    from quickalignment.viewer_info import ViewerInfo

    win = window
    win.editor.set_layout(win.editor.layout_model.__class__(samples=[Sample("WSe2", length=6, width=6, height=0.2)]))
    panel = win.rotation
    panel.set_info(ViewerInfo.from_text(
        "field,value\nMotor.roughY,0.0\nMotor.roughX,40.0\nMotor.focus,0.2\nMotor.SRn,120\nMotor.SRz,0\n"
        "Motor.fine_x,150\nMotor.fine_y,150\nMotor.ZP_ZS,-5.5\nPhotonEnergy,95\n"))
    assert panel.optic_key.currentText() == "Motor.ZP_ZS" and panel.measured_optic.value() == -5.5
    panel.rotation.setValue(30.0)
    panel.goal.setCurrentIndex(0)
    panel.compute()
    assert panel.result is not None and panel.result.target == "WSe2"
    assert abs(abs(panel.result.new.srn - 120) - 30) < 1e-6 or abs(abs(panel.result.new.srn - 120) - 150) < 1e-6
    panel.send_to_stage()
    assert win.stage.motors.value().srn == panel.result.new.srn
    assert win.stage.optic_pos.value() == panel.result.optic_new
    # analyzer centre: SRn + SRz
    panel.goal.setCurrentIndex(3)
    panel.theta.setValue(8.0)
    panel.phi.setValue(3.0)
    panel.compute()
    assert panel.result is not None and abs(panel.result.new.srz) > 1


def test_rotation_tab_learns_srn_axis(window):
    from quickalignment.stage import MotorPositions

    panel = window.rotation
    panel.measured.set_value(MotorPositions(st=-0.24994375, sz=43.202, sn=0.34838125, srn=132.0005, srz=0.003))
    panel.second.set_value(MotorPositions(st=0.24625625, sz=42.901, sn=0.34788125, srn=118.0003, srz=0.003))
    panel.fit_axis()
    assert panel.use_axis_btn.isEnabled() and abs(panel.axis_fit.lever_arm - 2.379) < 0.01
    panel.use_axis()
    assert window.stage.config().srn_axis_v == panel.axis_fit.config.srn_axis_v
    # the learned axis now predicts the second position from the first
    panel.goal.setCurrentIndex(4)  # manual
    panel.d_srn.setValue(118.0003 - 132.0005)
    panel.new_srz.setValue(0.003)
    panel.compute()
    assert abs(panel.result.new.st - 0.24625625) < 2e-3 and abs(panel.result.new.sz - 42.901) < 2e-3


def test_custom_plate_dialog_and_focus(window, monkeypatch):
    from quickalignment.geometry import custom_plate
    from quickalignment.ui.plate_choice import PlateChoiceDialog
    import quickalignment.app as app_module

    dlg = PlateChoiceDialog("standard")
    assert dlg.plate().key == "standard"
    dlg.custom_length.setValue(6.0)  # editing the block selects the custom plate
    dlg.custom_width.setValue(4.0)
    dlg.custom_height.setValue(8.2)
    dlg.custom_center_y.setValue(1.5)  # only left-right is centred
    plate = dlg.plate()
    assert plate.key == "custom" and plate.riser_bounds() == (-3.0, -0.5, 3.0, 3.5)
    dlg.custom_center_y.setValue(6.0)  # the block would stick out at the top
    assert "must fit" in dlg.custom_note.text()
    dlg.custom_center_y.setValue(1.5)
    assert PlateChoiceDialog(plate).plate() == plate  # reopens with the plate in use

    monkeypatch.setattr(app_module, "ask_plate", lambda *a, **k: custom_plate(6.0, 4.0, 8.2, 0.5))
    window.change_plate()
    window.editor.add_sample(Sample("A", u=0, v=0, length=2, width=2, height=0.3))
    st = window.stage
    st.record = replace(st.record, config=replace(st.record.config, sn_f=-0.1))
    st.refresh_targets()
    st.target_combo.setCurrentText("A")
    st.bring_target_to_focus()
    assert abs(st.motors.value().sn - 3.4) < 1e-6  # SN_f + (8.2 - 5.0) + 0.3
    assert "H = 0.300 mm above the plate top" in st.result_label.text()
