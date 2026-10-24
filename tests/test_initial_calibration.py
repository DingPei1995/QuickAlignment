import numpy as np
import pytest

from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE
from quickalignment.initial_calibration import (
    NotEnoughData, fit_initial_calibration, initial_record, protocol_sets,
)
from quickalignment.stage import StageConfig, StageModel

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
    res = fit_initial_calibration(sets, STANDARD_PLATE, REF)
    rec = initial_record(res, STANDARD_PLATE, REF, optic_position=8.25, optic_sign=-1)
    assert rec.optics.enabled and rec.optics.optic_position == 8.25 and rec.optics.optic_sign == -1
    assert rec.optics.motors.srn == 120 and rec.optics.surface_w == REF[2]
    assert rec.check["type"] == "initial calibration" and len(rec.check["sets"]) == 3
    assert not initial_record(res, STANDARD_PLATE, REF, optic_position=None).optics.enabled
