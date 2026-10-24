import numpy as np
import pytest

from quickalignment.geometry import Sample, SampleLayout
from quickalignment.rotation import (
    AnalyzerGeometry, align_direction, analyzer_angles, emission_in_plate, fit_srn_axis, onto_line, plate_to_lab_dir,
    relocate, to_center,
)
from quickalignment.stage import MotorPositions, OpticsCalibration, StageConfig, StageModel

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


# Measured: the same sample point found again after an SRn turn (ARPES viewer metadata / notes)
WWS2_ZONE_PLATE = [  # standard plate, zone plate, 2025-10-01 / 2025-10-02
    MotorPositions(st=-0.24994375, sz=43.202, sn=0.34838125, srn=132.000539892, srz=0.003053133),
    MotorPositions(st=0.24625625, sz=42.901, sn=0.34788125, srn=118.000279011, srz=0.002939244),
]
WS_2026_09_18 = [  # non-standard plate, capillary
    MotorPositions(st=-0.6017718749999971, sz=39.243, sn=6.499146875, srn=119.997322626, srz=0.000661464),
    MotorPositions(st=-1.001471874999997, sz=39.345, sn=6.498646875, srn=103.999790352, srz=0.000775353),
]


@pytest.mark.parametrize("pair", [WWS2_ZONE_PLATE, WS_2026_09_18])
def test_fit_srn_axis_reproduces_measured_pairs(pair):
    model = StageModel()
    fit = fit_srn_axis(model, pair, 5.0)
    assert max(abs(v) for r in fit.residuals for v in r) < 1e-9  # two positions: exact
    first, second = pair
    for mode in ("keep_point", "keep_sn"):
        rel = relocate(StageModel(fit.config), SampleLayout(), first, second.srn, second.srz, OpticsCalibration(),
                       keep_sn=mode == "keep_sn")
        assert rel.new.st == pytest.approx(second.st, abs=2e-3)
        assert rel.new.sz == pytest.approx(second.sz, abs=2e-3)
        assert rel.new.sn == pytest.approx(second.sn, abs=2e-3)


def test_fit_srn_axis_values():
    # surface in the focal plane: H = SN - SN_f = 0.348 (with SN_f = 0)
    fit = fit_srn_axis(StageModel(), WWS2_ZONE_PLATE, 5.348)
    assert (fit.config.srn_axis_u, fit.config.srn_axis_v) == pytest.approx((1.228, -1.033), abs=2e-3)
    assert fit.lever_arm == pytest.approx(2.379, abs=1e-3)


def test_fit_srn_axis_recovers_truth_from_several_positions():
    truth = StageModel(StageConfig(srn_axis_u=0.7, srn_axis_v=-1.1))
    positions = [truth.motors_for_target(1.5, 2.0, 5.3, srn=a, srz=0) for a in (120, 105, 140, 160)]
    fit = fit_srn_axis(StageModel(), positions, 5.3)
    assert (fit.config.srn_axis_u, fit.config.srn_axis_v) == pytest.approx((0.7, -1.1), abs=1e-9)
    assert fit.point == pytest.approx((1.5, 2.0), abs=1e-9)
    with pytest.raises(ValueError):
        fit_srn_axis(StageModel(), positions[:1] * 2, 5.3)


def test_keep_sn_slides_along_the_beam_with_srz():
    """Manual notes (non-standard plate, SN fixed at 7.8): SRz turns need an SRz axis ~10 mm behind the surface."""
    cfg = StageConfig(sn_f=6.499, srn_axis_u=0.439, srn_axis_v=-0.716, srz_offset_t=0.321, srz_offset_n=10.331)
    model = StageModel(cfg)
    start = MotorPositions(st=-1.8, sz=38.75, sn=7.8, srn=92, srz=0)
    ref = OpticsCalibration(optic_type="capillary")
    for srn, srz, st, cps in ((91, 2.5, -1.3, 59.65), (92, -1.7, -2.2, 59.79)):
        rel = relocate(model, SampleLayout(), start, srn, srz, ref, 59.68, default_height=1.301, keep_sn=True)
        assert rel.new.sn == 7.8 and rel.new.st == pytest.approx(st, abs=0.1)
        assert rel.optic_new == pytest.approx(cps, abs=0.1)


def test_starting_configuration_zone_plate_reference():
    """configs/calibration_2026-10-24_170000_zone_plate.json: ZP_ZS 53.21985 focuses on the first WWS2 Map (+ = towards the sample)."""
    from pathlib import Path

    from quickalignment.calibration import CalibrationStore

    root = Path(__file__).resolve().parent.parent
    record = next(r for r in CalibrationStore(root / "configs").records() if r.created == "2026-10-24 17:00:00")
    assert record.optics.enabled and record.optics.optic_sign == 1
    model = StageModel(record.config)
    first, second = WWS2_ZONE_PLATE
    layout = SampleLayout(samples=[Sample("WWS2", u=-0.2, v=-3.0, length=3, width=3, height=0.348)])
    rel = relocate(model, layout, first, second.srn, second.srz, record.optics)  # optic from the configuration
    assert rel.optic_measured == pytest.approx(53.21985, abs=1e-3)
    assert rel.optic_new == pytest.approx(53.21985, abs=1e-3)  # SRn keeps the surface plane
    assert rel.new.st == pytest.approx(second.st, abs=2e-3) and rel.new.sz == pytest.approx(second.sz, abs=2e-3)
