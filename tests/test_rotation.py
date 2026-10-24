import numpy as np
import pytest

from quickalignment.geometry import Sample, SampleLayout
from quickalignment.rotation import (
    AnalyzerGeometry, align_direction, analyzer_angles, emission_in_plate, onto_line, plate_to_lab_dir, relocate,
    to_center,
)
from quickalignment.stage import MotorPositions, OpticsCalibration, StageConfig, StageModel
from quickalignment.viewer_info import ViewerInfo

GEOMETRIES = [AnalyzerGeometry(), AnalyzerGeometry("horizontal", -1, 1), AnalyzerGeometry("vertical", 1, -1)]


@pytest.mark.parametrize("geo", GEOMETRIES)
def test_angles_roundtrip(geo):
    model = StageModel()
    m = MotorPositions(srn=133, srz=-4)
    d = emission_in_plate(model, geo, m, 7.0, -11.0)
    assert analyzer_angles(geo, plate_to_lab_dir(model, m.srn, m.srz) @ d) == pytest.approx((7.0, -11.0))
    # normal emission is the plate normal at the reference pose
    assert np.allclose(emission_in_plate(model, geo, MotorPositions(), 0, 0), [0, 0, 1])


@pytest.mark.parametrize("geo", GEOMETRIES)
@pytest.mark.parametrize("line", ["slit", "deflector"])
def test_onto_line(geo, line):
    model = StageModel()
    m = MotorPositions(srn=120, srz=-3)
    cands = onto_line(model, geo, m, 9.0, 5.0, line)
    assert cands
    for c in cands:
        assert abs(c.theta if line == "slit" else c.phi) < 1e-9


@pytest.mark.parametrize("geo", GEOMETRIES)
def test_to_center(geo):
    model = StageModel()
    m = MotorPositions(srn=120, srz=0)
    cands = to_center(model, geo, m, 12.0, -6.0)
    assert cands and abs(cands[0].theta) < 1e-6 and abs(cands[0].phi) < 1e-6
    # a point along the deflector axis only needs SRz when the slit is vertical
    if geo.slit == "vertical":
        c = to_center(model, geo, m, 10.0, 0.0)[0]
        assert c.srn == pytest.approx(120) and abs(c.srz) == pytest.approx(10)
    else:  # horizontal slit: a point along the slit only needs SRz
        c = to_center(model, geo, m, 0.0, 10.0)[0]
        assert c.srn == pytest.approx(120) and abs(c.srz) == pytest.approx(10)


def test_default_slit_is_horizontal():
    assert AnalyzerGeometry().slit == "horizontal"


@pytest.mark.parametrize("geo", GEOMETRIES)
def test_align_direction_matches_viewer_rotation(geo):
    """A direction at angle beta on the contour (from Gamma) needs viewer rotation 90 - beta;
    after the proposed SRn turn it must lie on the slit (theta = 0)."""
    model = StageModel()
    m = MotorPositions()
    beta = 30.0
    r = 2.0  # deg from normal emission, small-angle regime
    theta, phi = r * np.cos(np.radians(beta)), r * np.sin(np.radians(beta))
    d = emission_in_plate(model, geo, m, theta, phi)
    c = align_direction(model, geo, m, 90 - beta)[0]
    th, ph = analyzer_angles(geo, plate_to_lab_dir(model, c.srn, c.srz) @ d)
    assert abs(th) < 1e-3 and ph == pytest.approx(r, abs=1e-3)
    c = align_direction(model, geo, m, 90 - beta, along="deflector")[0]
    th, ph = analyzer_angles(geo, plate_to_lab_dir(model, c.srn, c.srz) @ d)
    assert abs(ph) < 1e-3 and abs(th) == pytest.approx(r, abs=1e-3)


def test_relocate_exact_with_true_model():
    cfg = StageConfig(st0=0.37, sz0=40.6, sn_f=-0.21, srn_axis_u=0.8, srn_axis_v=-1.2, srz_offset_t=0.3, srz_offset_n=0.4)
    model = StageModel(cfg)
    layout = SampleLayout(samples=[Sample("A", u=2.0, v=1.0, length=4, width=4, height=0.4)])
    point = (2.6, 1.7, 5.4)
    measured = model.motors_for_target(*point, srn=120, srz=0, pix=180, piy=90)
    rel = relocate(model, layout, measured, 157.0, -6.0, OpticsCalibration(optic_sign=-1), measured_optic=3.21)
    expected = model.motors_for_target(*point, srn=157.0, srz=-6.0, pix=180, piy=90)
    assert rel.target == "A"
    for k in ("st", "sn", "sz"):
        assert getattr(rel.new, k) == pytest.approx(getattr(expected, k), abs=1e-9)
    assert rel.optic_new == pytest.approx(3.21) and rel.optic_measured == pytest.approx(3.21)
    # put it on the analyzer focus instead: the optic follows the beam spot
    measured.sn += 0.3  # measured 0.3 mm behind the analyzer focus
    rel = relocate(model, layout, measured, 157.0, -6.0, OpticsCalibration(optic_sign=-1), 3.21, to_analyzer_focus=True)
    assert np.allclose(model.plate_to_lab(rel.new, *rel.uvw), 0, atol=1e-9)
    dy = model.beam_hit(rel.new, 5.4)[1] - model.beam_hit(measured, 5.4)[1]
    assert rel.optic_new == pytest.approx(3.21 - dy)


def test_relocate_tolerates_offset_errors():
    """ST0 / SZ0 / SN_f errors: keeping the point where it was measured beats the absolute prediction."""
    axes = dict(srn_axis_u=0.8, srn_axis_v=-1.2, srz_offset_t=0.3, srz_offset_n=0.4)
    truth = StageModel(StageConfig(st0=0.37, sz0=40.6, sn_f=-0.21, **axes))
    model = StageModel(StageConfig(**axes))
    layout = SampleLayout(samples=[Sample("A", u=2.0, v=1.0, length=6, width=6, height=0.4)])
    point = (2.6, 1.7, 5.4)
    measured = truth.motors_for_target(*point, srn=120, srz=0)
    expected = truth.motors_for_target(*point, srn=135.0, srz=0)
    rel = relocate(model, layout, measured, 135.0, 0.0, OpticsCalibration())
    absolute = relocate(model, layout, measured, 135.0, 0.0, OpticsCalibration(), to_analyzer_focus=True)

    def err(m):
        return np.linalg.norm([m.st - expected.st, m.sn - expected.sn, m.sz - expected.sz])

    assert err(rel.new) < 0.5 * err(absolute.new)
    assert err(rel.new) < 0.2  # (rotation 15 deg) x (0.5 mm lever arm error)


def test_relocate_recentre_piezo():
    model = StageModel(StageConfig(srn_axis_u=0.5))
    layout = SampleLayout(samples=[Sample("A", length=6, width=6, height=0.5)])
    measured = model.motors_for_target(0.3, 0.2, 5.5, srn=120, srz=0, pix=60, piy=240)
    rel = relocate(model, layout, measured, 150.0, 0.0, OpticsCalibration(), recentre_piezo=True)
    assert (rel.new.pix, rel.new.piy) == (150, 150)
    assert np.allclose(model.plate_to_lab(rel.new, 0.3, 0.2, 5.5), model.plate_to_lab(measured, 0.3, 0.2, 5.5))


def test_viewer_info_csv_and_paste():
    csv_text = "field,value\nPhotonEnergy,95.0\nMotor.focus,0.512\nMotor.roughY,-0.35\nMotor.roughX,40.1\n" \
               "Motor.SRn,120.0\nMotor.SRz,0.0\nMotor.fine_x,150.0\nMotor.fine_y,148.5\nMotor.ZP_ZS,-12.345\n"
    info = ViewerInfo.from_text(csv_text)
    m, missing = info.motors()
    assert not missing
    assert (m.st, m.sz, m.sn, m.srn, m.piy) == (-0.35, 40.1, 0.512, 120.0, 148.5)
    assert info.get("Motor.ZP_ZS") == -12.345 and info.photon_energy == 95.0
    pasted = ViewerInfo.from_text("Motor.SRn\t130\nMotor.roughY\t1.5\nMotor.ZP_ZS = [2.5]")
    m, missing = pasted.motors(MotorPositions(sz=39))
    assert m.srn == 130 and m.st == 1.5 and m.sz == 39 and "Motor.roughX" in missing
    assert pasted.optic_keys() == ["Motor.ZP_ZS"]
