from datetime import datetime

import pytest

from quickalignment.calibration import CalibrationRecord, CalibrationStore, check_reference
from quickalignment.geometry import STANDARD_PLATE
from quickalignment.stage import MotorPositions, OpticsCalibration, StageConfig, StageModel


def test_store_latest_and_roundtrip(tmp_path):
    store = CalibrationStore(tmp_path)
    assert store.latest().created == ""  # built-in default
    a = store.save(CalibrationRecord(comment="a", config=StageConfig(st0=0.1)), now=datetime(2026, 1, 2, 3, 4, 5))
    b = store.save(CalibrationRecord(comment="b", config=StageConfig(st0=0.2)), now=datetime(2026, 3, 1, 0, 0, 0))
    assert a.path.name == "calibration_2026-01-02_030405.json"
    latest = store.latest()
    assert latest.comment == "b" and latest.config.st0 == 0.2 and latest.created == "2026-03-01 00:00:00"
    assert [r.comment for r in store.records()] == ["b", "a"]
    (tmp_path / "calibration_broken.json").write_text("{not json")
    assert len(store.records()) == 2


def test_check_reference_updates_offsets_and_optics():
    old = CalibrationRecord(
        config=StageConfig(st0=0.0, sz0=40.0, sn_f=0.0),
        optics=OpticsCalibration(enabled=True, motors=MotorPositions(sn=0.5), surface_w=5.5, optic_position=10.0, optic_sign=1),
    )
    # the reference really sits 0.2 mm off in ST, -0.1 in SZ, +0.05 in SN
    true_model = StageModel(StageConfig(st0=0.2, sz0=39.9, sn_f=0.05), STANDARD_PLATE)
    uvw = (1.0, 2.0, 5.5)
    measured = true_model.motors_for_target(*uvw, srn=120, srz=0)
    res = check_reference(old, STANDARD_PLATE, "ref", uvw, measured, measured_optic=10.1)
    assert (res.delta_st, res.delta_sz, res.delta_sn) == pytest.approx((0.2, -0.1, 0.05))
    new = res.new_record.config
    assert (new.st0, new.sz0, new.sn_f) == pytest.approx((0.2, 39.9, 0.05))
    # old optics calibration predicts the move from the SN change: 0.05 * sqrt(2)
    assert res.predicted_optic == pytest.approx(10.0 + 0.05 * 2 ** 0.5)
    assert res.delta_optic == pytest.approx(0.1 - 0.05 * 2 ** 0.5)
    assert res.new_record.optics.enabled and res.new_record.optics.optic_position == 10.1
    # with the new record the measured state is exactly predicted
    again = check_reference(res.new_record, STANDARD_PLATE, "ref", uvw, measured, 10.1)
    assert (again.delta_st, again.delta_sz, again.delta_sn) == pytest.approx((0, 0, 0), abs=1e-9)
    assert again.delta_optic == pytest.approx(0, abs=1e-9)
