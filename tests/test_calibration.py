from datetime import datetime

from quickalignment.calibration import CalibrationRecord, CalibrationStore
from quickalignment.stage import StageConfig


def test_store_latest_and_roundtrip(tmp_path):
    store = CalibrationStore(tmp_path)
    assert store.latest().created == ""  # built-in default
    a = store.save(CalibrationRecord(comment="a", config=StageConfig(st0=0.1)), now=datetime(2026, 1, 2, 3, 4, 5))
    b = store.save(CalibrationRecord(comment="b", config=StageConfig(st0=0.2)), now=datetime(2026, 3, 1, 0, 0, 0))
    assert a.path.name == "calibration_2026-01-02_030405_zone_plate.json"
    latest = store.latest()
    assert latest.comment == "b" and latest.config.st0 == 0.2 and latest.created == "2026-03-01 00:00:00"
    assert [r.comment for r in store.records()] == ["b", "a"]
    (tmp_path / "calibration_broken.json").write_text("{not json")
    assert len(store.records()) == 2


def test_found_here_absorbs_a_small_configuration_error():
    """Why QuickAlignment needs no calibration of its own: with a configuration from InitialCalibration
    (test points found within 0.05 mm), correcting the first found sample with "Found here" leaves
    errors of a few 10 um at the other rotations (an offset in the lab frame, taken as a position on
    the rotating plate, is off by 2 * error * sin(rotation / 2))."""
    import numpy as np

    from quickalignment.geometry import STANDARD_PLATE
    from quickalignment.stage import StageModel, found_offset

    truth = StageModel(StageConfig(st0=0.2, sz0=40.1, sn_f=0.3, srn_axis_u=1.2, srn_axis_v=-1.0,
                                   srz_offset_t=0.1, srz_offset_n=-0.2), STANDARD_PLATE)
    err = 0.05 / np.sqrt(3)  # every constant off, 0.05 mm in total for the offsets
    config = StageConfig(st0=0.2 + err, sz0=40.1 - err, sn_f=0.3 + err, srn_axis_u=1.2 + err, srn_axis_v=-1.0 - err,
                         srz_offset_t=0.1 + err, srz_offset_n=-0.2 - err)
    model = StageModel(config, STANDARD_PLATE)
    drawn = np.array([2.0, 1.5, 5.5])
    real = drawn + [0.3, -0.4, 0.1]  # drawing error: much larger than the configuration error
    found = truth.motors_for_target(*real, srn=120.0, srz=0.0)
    du, dv, dw = found_offset(model, found, *drawn)
    corrected = drawn + [du, dv, dw]
    for srn, srz in ((150.0, 0.0), (90.0, 0.0), (120.0, -15.0), (140.0, 10.0)):
        p, t = model.motors_for_target(*corrected, srn=srn, srz=srz), truth.motors_for_target(*real, srn=srn, srz=srz)
        assert max(abs(p.st - t.st), abs(p.sz - t.sz), abs(p.sn - t.sn)) < 0.05
