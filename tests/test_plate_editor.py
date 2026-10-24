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
    monkeypatch.setattr(app_module, "ask_setup", lambda *a, **k: (STANDARD_PLATE, "zone plate + OSA"))
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
    assert ed.default_height() == 0.525  # Si wafer substrate

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


def test_close_asks_nothing_and_writes_no_configuration(window, monkeypatch):
    asked = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: asked.append(a) or QtWidgets.QMessageBox.Yes)
    window.close()
    assert not window.isVisible() and not asked
    assert not window.store.folder.exists() or not any(window.store.folder.iterdir())


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
    win.table.item(0, 7).setText("4.2")
    win.table.item(3, 7).setText("4.2")
    win.optic_type.setCurrentIndex(1)  # capillary
    win.compute()
    assert win.save_btn.isEnabled() and "Optics reference" in win.result_label.text()
    assert win.result.config.st0 == pytest.approx(0.2, abs=1e-5)
    assert win.result.config.srz_offset_n == pytest.approx(-0.3, abs=1e-5)

    # front / side view of the entered feature, with the expected positions of the sets
    win.show_feature()
    assert win.feature_dialog.isVisible() and "Expected positions" in win.feature_dialog.info.text()
    assert len(win.feature_dialog.figure.axes) == 2
    win.ref_x.setValue(8.0)  # off the riser: flagged
    assert "outside the sample area" in win.feature_dialog.info.text()
    win.ref_x.setValue(1.0)
    win.feature_dialog.close()

    win.save()
    rec = store.latest("capillary")
    assert rec.path.name.endswith("_capillary.json") and rec.optics.optic_type == "capillary"
    assert rec.config.srn_axis_u == pytest.approx(0.5, abs=1e-5)
    assert rec.optics.enabled and rec.optics.optic_position == pytest.approx(4.2)
    assert "Saved" in win.result_label.text()
    assert not store.latest("zone plate + OSA").optics.enabled

    # correction of the saved configuration after re-homing: one set, ST0 / SZ0 / SN_f only
    win.optic_type.setCurrentIndex(1)
    assert win.base_record().path == rec.path
    win.fit_mode.setCurrentIndex(1)
    shifted = StageModel(replace(rec.config, st0=0.25, sz0=40.2, sn_f=0.05), STANDARD_PLATE)
    m = shifted.motors_for_target(1.0, -0.5, 5.3, srn=120.0, srz=0.0)
    for col, value in ((4, m.st), (5, m.sz), (6, m.sn), (7, "")):
        win.table.item(0, col).setText(value if value == "" else f"{value:.6f}")
    for row in range(1, 5):
        win.table.item(row, 0).setCheckState(Qt.Unchecked)
    win.compute()
    assert win.save_btn.isEnabled() and "kept" in win.result_label.text()
    win.save()
    corrected = store.latest("capillary")
    assert corrected.path != rec.path and corrected.check["type"] == "configuration correction"
    assert (corrected.config.st0, corrected.config.sz0, corrected.config.sn_f) == pytest.approx((0.25, 40.2, 0.05), abs=1e-5)
    assert corrected.config.srn_axis_u == rec.config.srn_axis_u
    assert corrected.optics.optic_position == rec.optics.optic_position  # kept: no optic position entered
    win.close()


def test_main_window_loads_initial_calibration(monkeypatch, tmp_path):
    """A configuration written by InitialCalibration is the one QuickAlignment starts with, for its optic."""
    import quickalignment.app as app_module
    from quickalignment.calibration import CalibrationStore
    from quickalignment.geometry import STANDARD_PLATE
    from quickalignment.initial_calibration import fit_initial_calibration, initial_record, protocol_sets
    from quickalignment.stage import StageConfig, StageModel

    truth = StageModel(StageConfig(st0=0.2, sz0=40.3, sn_f=-0.1, srn_axis_u=0.5, srz_offset_n=-0.3), STANDARD_PLATE)
    sets = protocol_sets()[:3]
    for s in sets:
        m = truth.motors_for_target(0.0, 0.0, 5.0, srn=s.srn, srz=s.srz)
        s.st, s.sz, s.sn, s.optic = m.st, m.sz, m.sn, 7.5
    res = fit_initial_calibration(sets, STANDARD_PLATE, (0.0, 0.0, 5.0))
    store = CalibrationStore(tmp_path / "configs")
    saved = store.save(initial_record(res, STANDARD_PLATE, (0.0, 0.0, 5.0), optic_type="capillary"))

    monkeypatch.setattr(app_module, "ask_setup", lambda *a, **k: (STANDARD_PLATE, "capillary"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow(store=store, optic="capillary")
    st = win.stage
    assert st.record.path == saved.path and st.optic_type.currentText() == "capillary"
    assert st.optic_pos.value() == pytest.approx(7.5)
    assert st.config().sz0 == pytest.approx(40.3, abs=1e-6)
    win.close()


def test_rotation_tab(window):
    win = window
    win.editor.set_layout(win.editor.layout_model.__class__(samples=[Sample("WSe2", length=6, width=6, height=0.2)]))
    panel = win.rotation
    st = win.stage
    st.record = replace(st.record, config=replace(st.record.config, srn_axis_u=1.2, srn_axis_v=-1.0, srz_offset_n=10.0))
    # a point of the sample on the analyzer focus, piezo off centre
    panel.measured.set_value(st.model().motors_for_target(0.3, -0.2, 5.2, srn=120, srz=0, pix=100, piy=200))
    panel.measured_optic.setValue(-5.5)
    assert panel.optic_label.text() == "Zone plate position"

    # SRn only: the surface plane stays, the point stays on the analyzer focus
    panel.new_srn.setValue(150.0)
    panel.compute()
    r = panel.result
    assert r.target == "WSe2" and (r.new.pix, r.new.piy) == (150, 150)
    assert r.new.sn == pytest.approx(r.measured.sn) and r.focus_distance < 1e-6
    assert "no SN correction needed" in panel.focus_label.text()
    assert not panel.correct_sn.isChecked()

    # SRz with the axis ~10 mm behind the surface: with SN kept the point leaves the analyzer focus
    panel.new_srz.setValue(5.0)
    panel.compute()
    r = panel.result
    assert r.new.sn == pytest.approx(r.measured.sn) and r.focus_distance > 0.05
    assert "correct SN?" in panel.focus_label.text()
    panel.send_to_stage()
    assert st.motors.value().st == pytest.approx(r.new.st, abs=1e-4) and st.motors.value().sn == pytest.approx(r.new.sn)
    assert st.optic_pos.value() == pytest.approx(r.optic_new, abs=1e-4)

    # corrected: SN, ST, SZ put the point on the analyzer focus, the optic focuses there (as when measured)
    panel.correct_sn.setChecked(True)
    c = panel.corrected
    assert c.focus_distance < 1e-6 and abs(c.new.sn - r.measured.sn) > 1e-3
    assert c.optic_new == pytest.approx(-5.5)
    assert "on the analyzer focus" in panel.corrected_label.text()
    panel.send_to_stage()
    assert st.motors.value().sn == pytest.approx(c.new.sn, abs=1e-4)


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


def test_toolbar_has_no_save_as(window):
    texts = [w.text() for w in window.findChildren(QtWidgets.QToolButton)]
    assert "Save" in texts and "Save as…" not in texts


def test_samples_placed_goes_to_stage(window, monkeypatch):
    ed = window.editor
    ed.add_sample(Sample("A", u=1.0, v=2.0, length=2, width=2, height=0.4))
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.No)
    assert not ed.confirm_samples_placed()
    assert window.tabs.currentWidget() is ed and window.stage.start_box.isHidden()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Yes)
    assert ed.confirm_samples_placed()
    assert window.tabs.currentWidget() is window.stage and not window.stage.start_box.isHidden()
    # ST = ST0 - x, SZ = SZ0 - y, SN = SN_f + H
    assert "<td>A</td><td align=right>-1.000</td><td align=right>38.000</td><td align=right>0.400</td>" \
        in window.stage.start_label.text()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)


def test_optic_choice_loads_its_configuration(tmp_path, monkeypatch):
    from datetime import datetime

    from quickalignment.calibration import CalibrationRecord, CalibrationStore
    from quickalignment.stage import OpticsCalibration, StageConfig
    from quickalignment.ui.plate_choice import PlateChoiceDialog

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    store = CalibrationStore(tmp_path)
    assert store.latest("capillary").optics.optic_type == "capillary"  # nothing saved yet
    store.save(CalibrationRecord(comment="cap", optics=OpticsCalibration(optic_type="capillary", optic_position=3.0)),
               now=datetime(2026, 1, 1))
    store.save(CalibrationRecord(comment="zp", config=StageConfig(st0=0.2),
                                 optics=OpticsCalibration(optic_position=53.2)), now=datetime(2026, 2, 1))
    assert store.latest().comment == "zp"
    assert store.latest("capillary").comment == "cap"
    assert store.latest("zone plate + OSA").comment == "zp"
    store.save(CalibrationRecord(comment="zp2", config=StageConfig(st0=0.3)), now=datetime(2026, 3, 1))
    (tmp_path / "calibration_2026-01-01_000000_capillary.json").unlink()
    fallback = store.latest("capillary")  # no capillary file: stage constants of the newest, optic not calibrated
    assert fallback.config.st0 == 0.3 and fallback.optics.optic_type == "capillary"
    assert fallback.optics.optic_position == 0.0 and "not calibrated" in fallback.comment

    dlg = PlateChoiceDialog("standard", optic="capillary")
    assert dlg.optic() == "capillary"
    dlg.optic_group.button(0).setChecked(True)
    assert dlg.optic() == "zone plate + OSA"
    assert PlateChoiceDialog("standard").optic() is None

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)
    win = MainWindow(store=store, optic="capillary")
    assert win.stage.optic_type.currentText() == "capillary" and win.rotation.optic_label.text() == "Capillary position"
    win.close()


def test_motor_ranges(window, monkeypatch):
    from quickalignment.stage import MotorPositions
    from quickalignment.ui.stage_panel import out_of_range

    assert out_of_range(MotorPositions()) == []
    assert out_of_range(MotorPositions(st=7, sn=-1, sz=34)) == [
        "ST = 7.0000 (range -6 … 6)", "SN = -1.0000 (range -0.5 … 65)", "SZ = 34.0000 (range 35 … 45)"]

    # y = 6 needs SZ = SZ0 - 6 = 34 at SRn = 120: refused, positions unchanged
    ed, st = window.editor, window.stage
    ed.add_sample(Sample("high", u=0, v=6.0, length=1, width=1))
    st.refresh_targets()
    st.target_combo.setCurrentText("high")
    warned = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    st.bring_target_to_focus()
    assert warned and "SZ = 34.0000" in warned[0] and st.motors.value().sz == 40.0

    # the corrected rotation solution is clamped to the ranges: closest reachable position
    panel = window.rotation
    st.record = replace(st.record, config=replace(st.record.config, srn_axis_v=1.0))
    panel.measured.set_value(st.model().motors_for_target(0.0, -4.8, 5.0, srn=120, srz=0))  # SZ = 44.8
    panel.new_srn.setValue(300.0)  # half a turn about v = 1: the point goes to v = 6.8, i.e. SZ = 33.2
    panel.new_srz.setValue(0.0)
    panel.compute()
    assert "Out of range: SZ = 33.2000" in panel.result_label.text()
    c = panel.corrected
    assert out_of_range(c.new) == [] and c.new.sz == 35.0 and c.focus_distance == pytest.approx(1.8)
    assert "closest reachable position: 1800 µm" in panel.corrected_label.text()
    warned.clear()
    panel.correct_sn.setChecked(False)
    panel.send_to_stage()  # SN kept is not reachable
    assert warned and "SZ = 33.2000" in warned[0]


def test_found_device_corrects_its_sample(window, monkeypatch):
    ed, st = window.editor, window.stage
    sub = ed.add_sample(Sample("Sub", u=1.0, v=-1.0, length=4, width=4, height=0.5))
    ed.add_device(sub, Device("D1", "left", 1.0, "bottom", 1.0))
    d2 = ed.add_device(sub, Device("D2", "right", 1.0, "top", 1.0))
    other = ed.add_sample(Sample("B", u=-3.0, v=3.0, length=1, width=1, height=0.3))
    st.refresh_targets()
    # a substrate with devices is represented by its devices only
    assert st.target_labels() == ["Sub/D1", "Sub/D2", "B"]
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Yes)
    ed.confirm_samples_placed()
    text = st.start_label.text()
    assert "<td>Sub/D1</td>" in text and "<td>Sub</td>" not in text

    # D1 really is 0.2 mm further right, 0.1 mm lower and 0.05 mm higher than drawn
    assert sub.devices[0].position(sub) == (0.0, -2.0)
    found = st.model().motors_for_target(0.0 + 0.2, -2.0 - 0.1, 5.5 + 0.05, srn=120, srz=0)
    st.motors.set_value(found)
    record = st.record
    st.found_combo.setCurrentText("Sub/D1")
    du, dv, dw = st.correct_from_found()
    assert (du, dv, dw) == pytest.approx((0.2, -0.1, 0.05), abs=1e-4)
    # only that sample (with its devices) moved, and the editor shows it; no configuration change
    assert (sub.u, sub.v, sub.height) == pytest.approx((1.2, -1.1, 0.55), abs=1e-4)
    assert d2.position(sub) == pytest.approx((2.2, -0.1), abs=1e-4)
    assert (other.u, other.v, other.height) == (-3.0, 3.0, 0.3)
    assert ed.items[id(sub)].pos().x() == pytest.approx(1.2, abs=1e-4)
    assert ed.table.item(0, 2).text() == "1.200"
    assert st.record is record and not window.store.folder.exists()
    # the corrected list now predicts the found position for D1
    st.target_combo.setCurrentText("Sub/D1")
    st.bring_target_to_focus()
    m = st.motors.value()
    assert (m.st, m.sz, m.sn) == pytest.approx((found.st, found.sz, found.sn), abs=1e-4)
