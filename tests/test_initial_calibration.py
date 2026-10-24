from dataclasses import replace

import numpy as np
import pytest

from quickalignment.calibration import CalibrationStore
from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE, Sample, SampleLayout
from quickalignment.initial_calibration import (
    CORRECTION_PARAMS, NotEnoughData, fit_initial_calibration, fit_optics, initial_record, protocol_sets,
)
from quickalignment.stage import OPTIC_TYPES, OpticsCalibration, StageConfig, StageModel, focus_correction

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
    rec = initial_record(res, STANDARD_PLATE, REF, optic_sign=-1, optic_type="capillary")
    assert rec.optics.enabled and rec.optics.optic_sign == -1 and rec.optics.optic_type == "capillary"
    assert rec.optics.optic_position == pytest.approx(8.25)
    assert rec.optics.motors.srn == 120 and rec.optics.surface_w == REF[2]
    assert rec.check["type"] == "initial calibration" and len(rec.check["sets"]) == 3
    assert rec.check["sets"][0]["optic"] == 8.25 and rec.optic_name == "capillary"
    for s in sets:
        s.optic = None
    assert not initial_record(res, STANDARD_PLATE, REF).optics.enabled


def test_optic_positions_of_all_sets_are_averaged():
    sets = measure(protocol_sets(), noise=0.001)
    for s, d in zip(sets, (0.003, -0.002, 0.001, -0.001, -0.001)):
        s.optic = 12.5 + d
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    fit = fit_optics(res, STANDARD_PLATE, REF)
    assert fit.optics.optic_position == pytest.approx(12.5, abs=1e-3)
    assert len(fit.residuals) == 5 and fit.sigma is not None and fit.rms < 0.005
    # the feature is at the analyzer focus in every set: the reference focus is there too
    assert fit.optics.reference_y(StageModel(res.config, STANDARD_PLATE)) == pytest.approx(0.0, abs=0.01)


def test_correction_of_an_existing_configuration():
    base = replace(TRUE, st0=0.0, sz0=40.0, sn_f=0.0)  # axes known, offsets lost (motors re-homed)
    sets = measure(protocol_sets()[:1])
    with pytest.raises(NotEnoughData):
        fit_initial_calibration(sets, STANDARD_PLATE, REF, base=base)
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF, base=base, params=CORRECTION_PARAMS)
    assert np.allclose(params(res.config), params(TRUE), atol=1e-7)
    kept = OpticsCalibration(enabled=True, optic_position=3.3, optic_type=OPTIC_TYPES[0], last_position=3.4)
    rec = initial_record(res, STANDARD_PLATE, REF, base_label="old", kept_optics=kept)
    assert rec.check["type"] == "configuration correction" and rec.check["base"] == "old"
    assert rec.optics.enabled and rec.optics.optic_position == 3.3 and rec.optics.last_position is None


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
