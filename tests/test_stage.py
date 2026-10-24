import numpy as np
import pytest

from quickalignment.geometry import Device, Sample, SampleLayout
from quickalignment.stage import (
    N_HAT, T_HAT, MotorPositions, OpticsCalibration, StageConfig, StageModel, focus_correction,
)


def close(a, b, tol=1e-9):
    return np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol)


def test_reference_pose():
    model = StageModel()
    m = MotorPositions()
    # plate back face centre on the focus, surface towards the analyzer (-n)
    assert close(model.plate_to_lab(m, 0, 0, 0), [0, 0, 0])
    assert close(model.plate_to_lab(m, 1, 0, 0), T_HAT)
    assert close(model.plate_to_lab(m, 0, 1, 0), [0, 0, 1])
    assert close(model.surface_normal(m), -N_HAT)


def test_sn_focus_rule():
    model = StageModel(StageConfig(sn_f=0.3))
    h = 0.5
    m = MotorPositions(sn=0.3 + 5.0 + h)
    assert close(model.plate_to_lab(m, 0, 0, 5.0 + h), [0, 0, 0])


def test_translation_directions():
    model = StageModel()
    p0 = model.plate_to_lab(MotorPositions(), 0, 0, 5)
    assert close(model.plate_to_lab(MotorPositions(st=-1), 0, 0, 5) - p0, -T_HAT)  # upper-left
    assert close(model.plate_to_lab(MotorPositions(sn=1), 0, 0, 5) - p0, N_HAT)
    assert close(model.plate_to_lab(MotorPositions(sz=35), 0, 0, 5) - p0, [0, 0, -5])


def test_piezo_directions():
    model = StageModel()
    p0 = model.plate_to_lab(MotorPositions(), 0, 0, 5)
    # PIX 0 -> 300 moves the sample left -> right (seen from the analyzer)
    assert close(model.plate_to_lab(MotorPositions(pix=250), 0, 0, 5) - p0, 0.1 * T_HAT)
    assert close(model.plate_to_lab(MotorPositions(piy=50), 0, 0, 5) - p0, [0, 0, -0.1])


def test_srn_rotation_ccw_from_analyzer_about_offset_axis():
    model = StageModel(StageConfig(srn_axis_u=1.0, srn_axis_v=-2.0))
    m = MotorPositions(srn=210)  # +90 deg
    # the axis itself does not move
    assert close(model.plate_to_lab(m, 1.0, -2.0, 5), model.plate_to_lab(MotorPositions(), 1.0, -2.0, 5))
    # a point to the right of the axis goes above it (CCW seen from the analyzer)
    assert close(model.plate_to_lab(m, 2.0, -2.0, 5), model.plate_to_lab(MotorPositions(), 1.0, -1.0, 5))


def test_srz_rotation_axis_and_sense():
    cfg = StageConfig(srz_offset_t=0.7, srz_offset_n=0.2)
    model = StageModel(cfg)
    # points on the axis (plate surface centre line + offset) stay fixed
    w_axis = 5.0 - 0.2
    for v in (-3.0, 0.0, 4.0):
        assert close(model.plate_to_lab(MotorPositions(srz=-17), 0.7, v, w_axis), model.plate_to_lab(MotorPositions(), 0.7, v, w_axis))
    # SRz < 0 turns the plate CCW seen from above
    n = StageModel().surface_normal(MotorPositions(srz=-10))
    ang = np.degrees(np.arctan2(n[1], n[0]))
    assert ang == pytest.approx(-135 + 10)


@pytest.mark.parametrize("m", [MotorPositions(st=1.2, sn=3.4, sz=37, srn=133, srz=-8, pix=40, piy=260), MotorPositions(srz=12, srn=95)])
def test_inverse_roundtrip(m):
    model = StageModel(StageConfig(st0=0.1, sz0=40.2, sn_f=-0.3, srn_axis_u=0.5, srn_axis_v=-1, srz_offset_t=0.3, srz_offset_n=-0.4))
    for pt in ([0, 0, 0], [3.1, -2.2, 5.5], [-4, 6, 1.1]):
        assert close(model.lab_to_plate(m, model.plate_to_lab(m, *pt)), pt)


def test_motors_for_target_puts_point_on_focus():
    model = StageModel(StageConfig(srn_axis_u=0.5, srz_offset_t=0.3, srz_offset_n=0.5))
    m = model.motors_for_target(2.0, -3.0, 5.4, srn=127, srz=-6)
    assert close(model.plate_to_lab(m, 2.0, -3.0, 5.4), [0, 0, 0])
    assert (m.srn, m.srz, m.pix, m.piy) == (127, -6, 150, 150)


def test_beam_hit_and_focus_shift():
    model = StageModel()
    layout = SampleLayout(samples=[Sample("A", u=0, v=0, length=4, width=4, height=0.5)])
    m = MotorPositions(sn=5.5)
    res = focus_correction(model, m, layout, OpticsCalibration())
    assert res.target == "A" and close(res.hit, [0, 0, 0]) and res.delta == pytest.approx(0)
    # moving the sample 1 mm away from the analyzer -> focus 1.414 mm downstream
    res = focus_correction(model, MotorPositions(sn=6.5), layout, OpticsCalibration())
    assert res.delta == pytest.approx(np.sqrt(2))
    # ST / SZ / SRn keep the surface plane -> no optics move
    for mm in (MotorPositions(sn=5.5, st=1), MotorPositions(sn=5.5, sz=41), MotorPositions(sn=5.5, srn=130)):
        assert focus_correction(model, mm, layout, OpticsCalibration()).delta == pytest.approx(0, abs=1e-9)


def test_calibrated_prediction():
    model = StageModel()
    layout = SampleLayout(samples=[Sample("A", u=0, v=0, length=6, width=6, height=0.5)])
    cal = OpticsCalibration(enabled=True, motors=MotorPositions(sn=5.6), surface_w=5.5, optic_position=12.0, optic_sign=-1)
    res = focus_correction(model, MotorPositions(sn=5.6), layout, cal)
    assert res.delta == pytest.approx(0) and res.new_optic_position == pytest.approx(12.0)
    res = focus_correction(model, MotorPositions(sn=6.6), layout, cal)
    assert res.delta == pytest.approx(np.sqrt(2))
    assert res.new_optic_position == pytest.approx(12.0 - np.sqrt(2))


def test_srz_rotation_changes_focus():
    model = StageModel()
    layout = SampleLayout(samples=[Sample("A", u=2, v=0, length=2, width=2, height=0.5)])
    m = model.motors_for_target(2, 0, 5.5, srn=120, srz=0)
    assert focus_correction(model, m, layout, OpticsCalibration()).delta == pytest.approx(0, abs=1e-9)
    m.srz = -10  # sample centre is off the SRz axis -> surface moves along the beam
    res = focus_correction(model, m, layout, OpticsCalibration())
    assert res.delta is not None and abs(res.delta) > 0.05


def test_device_target_detected():
    model = StageModel()
    s = Sample("Sub", u=0, v=0, length=6, width=6, height=0.3, devices=[Device("D1", "left", 1.0, "top", 2.0, 0.4, 0.4)])
    layout = SampleLayout(samples=[s])
    du, dv = s.devices[0].position(s)
    assert (du, dv) == (-2.0, 1.0)
    m = model.motors_for_target(du, dv, 5.3, srn=120, srz=0)
    assert focus_correction(model, m, layout, OpticsCalibration()).target == "Sub/D1"
