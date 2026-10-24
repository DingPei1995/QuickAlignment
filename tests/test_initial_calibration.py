import numpy as np
import pytest

from quickalignment.calibration import CalibrationStore
from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE, Sample, SampleLayout
from quickalignment.initial_calibration import (
    FOUND_TOLERANCE, NotEnoughData, TestPoint, fit_initial_calibration, initial_record, on_beam, optic_focus_of, predict_test_point,
    protocol_sets, verification_angles,
)
from quickalignment.stage import OPTIC_TYPES, MotorPositions, StageConfig, StageModel, focus_correction

FOCUS = 12.5  # true optic position focusing on the analyzer focus (optic + = towards the sample)

TRUE = StageConfig(st0=0.31, sz0=40.27, sn_f=-0.12, srn_axis_u=0.45, srn_axis_v=-0.6, srz_offset_t=0.2, srz_offset_n=-0.35)
REF = (1.5, 2.0, 5.0 + 0.4)  # feature at x=1.5, y=2.0 on a 0.4 mm sample


def measure(sets, truth=TRUE, plate=STANDARD_PLATE, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    model = StageModel(truth, plate)
    for s in sets:
        m = model.motors_for_target(*REF, srn=s.srn, srz=s.srz)
        s.st, s.sz, s.sn = (m.st + rng.normal(0, noise), m.sz + rng.normal(0, noise), m.sn + rng.normal(0, noise))
    return sets


def params(cfg):
    return np.array([cfg.st0, cfg.sz0, cfg.sn_f, cfg.srn_axis_u, cfg.srn_axis_v, cfg.srz_offset_t, cfg.srz_offset_n])


def test_three_sets_are_enough_and_exact():
    sets = measure(protocol_sets()[:3])
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    assert np.allclose(params(res.config), params(TRUE), atol=1e-7)
    assert res.dof == 2  # SN of the SRn set and SZ of the SRz set are pure checks
    assert res.rms < 1e-8


@pytest.mark.parametrize("drop, missing", [(1, "SRn"), (2, "SRz"), (0, None)])
def test_missing_sets_are_reported(drop, missing):
    sets = measure(protocol_sets()[:3])
    del sets[drop]
    if missing is None:  # without the reference set the offsets and axes are coupled
        with pytest.raises(NotEnoughData):
            fit_initial_calibration(sets, STANDARD_PLATE, REF)
        return
    with pytest.raises(NotEnoughData) as err:
        fit_initial_calibration(sets, STANDARD_PLATE, REF)
    assert missing in str(err.value)


def test_redundant_sets_give_uncertainties():
    sets = measure(protocol_sets(), noise=0.002)
    res = fit_initial_calibration(sets, GATING_PLATE, REF)
    assert res.dof == 15 - 7 and res.sigma is not None
    assert np.allclose(params(res.config), params(TRUE), atol=0.02)
    assert res.rms < 0.005


def test_record_from_fit():
    sets = measure(protocol_sets()[:3])
    for s, optic in zip(sets, (8.25, 8.25, None)):
        s.optic = optic
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    assert res.optic_focus == pytest.approx(8.25) and "optic_focus" in res.params
    rec = initial_record(res, STANDARD_PLATE, REF, optic_type="capillary")
    assert rec.optics.enabled and rec.optics.optic_sign == 1 and rec.optics.optic_type == "capillary"
    assert rec.optics.motors.srn == 120 and rec.optics.surface_w == REF[2]
    assert optic_focus_of(rec, STANDARD_PLATE) == pytest.approx(8.25)
    assert rec.check["type"] == "initial calibration" and len(rec.check["sets"]) == 3
    assert rec.check["sets"][0]["optic"] == 8.25 and rec.optic_name == "capillary"
    for s in sets:
        s.optic = None
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    assert res.optic_focus is None and not initial_record(res, STANDARD_PLATE, REF).optics.enabled


def test_optic_positions_of_all_sets_are_fitted():
    sets = measure(protocol_sets(), noise=0.001)
    for s, d in zip(sets, (0.003, -0.002, 0.001, -0.001, -0.001)):
        s.optic = FOCUS + d
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    assert res.optic_focus == pytest.approx(FOCUS, abs=1e-3)
    assert len(res.optic_residuals) == 5 and res.sigma["optic_focus"] < 0.005


def answer(t: TestPoint, truth=TRUE, plate=STANDARD_PLATE) -> TestPoint:
    """What staff find at a test point: the real ST, SZ, optic with SRn, SRz, SN as given."""
    st, sz, optic = on_beam(StageModel(truth, plate), REF, t.srn, t.srz, t.sn, t.pix, t.piy, FOCUS)
    if max(abs(st - t.pred_st), abs(sz - t.pred_sz), abs(optic - t.pred_optic)) <= FOUND_TOLERANCE:
        t.found = True
    else:
        t.st, t.sz, t.optic = st, sz, optic
    return t


def test_on_beam_puts_the_feature_on_the_beam_in_the_optic_focus():
    model = StageModel(TRUE, STANDARD_PLATE)
    st, sz, optic = on_beam(model, REF, 150.0, -12.0, 0.3, 150.0, 150.0, FOCUS)
    p = model.plate_to_lab(MotorPositions(st=st, sz=sz, sn=0.3, srn=150.0, srz=-12.0), *REF)
    assert p[0] == pytest.approx(0, abs=1e-12) and p[2] == pytest.approx(0, abs=1e-12)
    assert optic - FOCUS == pytest.approx(p[1])  # focus moved along the beam onto the feature
    # at the analyzer focus the prediction of a test point is exact
    t = predict_test_point(model, REF, TestPoint("t", 150.0, -12.0), FOCUS)
    assert answer(t).found


def test_test_points_correct_the_configuration_until_found():
    """The SRz set was measured wrongly: the test points reveal it, and without it the next round is found."""
    sets = measure(protocol_sets()[:3])
    sets[2].st += 0.3  # a mistake the minimum data set cannot detect
    sets[0].optic = FOCUS
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)

    def new_round(res, n):
        model = StageModel(res.config, STANDARD_PLATE)
        return [answer(predict_test_point(model, REF, TestPoint(name, srn, srz, round=n), res.optic_focus))
                for name, srn, srz in verification_angles()]

    tests = new_round(res, 1)
    measured = [t for t in tests if t.measured]
    assert measured and max(abs(t.deviation()[0]) for t in measured) > FOUND_TOLERANCE
    res2 = fit_initial_calibration(sets, STANDARD_PLATE, REF, base=res.config, tests=tests)
    assert len(res2.test_residuals) == len(measured)  # found points only confirm
    worst = max(res2.residuals, key=lambda r: max(map(abs, r[1:])))
    assert worst[0] == "3 SRz rotated"  # the wrong set is now an outlier
    # predictions are better already
    second = new_round(res2, 2)
    assert max(max(abs(d) for d in t.deviation()) for t in second) < 0.5 * max(
        max(abs(d) for d in t.deviation()) for t in tests)
    assert sum(t.found for t in second) > sum(t.found for t in tests)

    sets[2].use = False  # untick the outlier: the test points replace it
    res3 = fit_initial_calibration(sets, STANDARD_PLATE, REF, base=res2.config, tests=tests + second)
    assert np.allclose(params(res3.config), params(TRUE), atol=1e-6) and res3.optic_focus == pytest.approx(FOCUS)
    assert not any(t.found for t in res3.tests)
    final = new_round(res3, 3)
    assert all(t.found for t in final)
    rec = initial_record(res3, STANDARD_PLATE, REF, tests=tests + second + final)
    assert rec.check["test_rounds"] == 3 and len(rec.check["test_points"]) == 18
    assert rec.check["test_points_fitted"] == sum(t.measured for t in tests + second)


def test_test_points_without_optic_give_st_sz_only():
    sets = measure(protocol_sets())
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    t = predict_test_point(StageModel(res.config, STANDARD_PLATE), REF, TestPoint("t", 150.0, 0.0), None)
    t.st, t.sz = t.pred_st + 0.01, t.pred_sz
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF, tests=[t])
    assert res.optic_focus is None and res.test_residuals[0][3] is None and res.dof == 15 + 2 - 7


@pytest.mark.parametrize("optic", OPTIC_TYPES)
def test_saved_configuration_is_used_by_quickalignment(tmp_path, optic):
    """What InitialCalibration writes is what QuickAlignment loads at start-up, for the chosen optic."""
    sets = measure(protocol_sets(), plate=GATING_PLATE)
    for s in sets:
        s.optic = 20.0
    res = fit_initial_calibration(sets, GATING_PLATE, REF)
    store = CalibrationStore(tmp_path)
    saved = store.save(initial_record(res, GATING_PLATE, REF, optic_type=optic))
    assert optic.split()[0] in saved.path.name.replace("_", " ")

    loaded = store.latest(optic)
    assert loaded.path == saved.path and loaded.optics.optic_type == optic
    assert loaded.config == res.config and loaded.optics == saved.optics
    other = next(o for o in OPTIC_TYPES if o != optic)
    assert not store.latest(other).optics.enabled  # the other optic: stage constants only

    # the main program puts the feature on the analyzer focus where it was measured, and the optic in focus there
    model = StageModel(loaded.config, GATING_PLATE)
    layout = SampleLayout(plate=GATING_PLATE, samples=[Sample("ref", 1.5, 2.0, 2.0, 2.0, REF[2] - GATING_PLATE.total_thickness)])
    for s in sets:
        m = model.motors_for_target(*REF, srn=s.srn, srz=s.srz)
        assert (m.st, m.sz, m.sn) == pytest.approx((s.st, s.sz, s.sn), abs=1e-6)
        beam = focus_correction(model, s.motors(), layout, loaded.optics)
        assert beam.target == "ref" and beam.required_optic_position == pytest.approx(20.0, abs=1e-6)
