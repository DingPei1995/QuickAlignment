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



def test_gating_capillary_configuration_reproduces_its_measurements():
    """configs/calibration_2026-10-24_235500_capillary.json (gating plate, capillary, SN kept, CPS refocused): each
    device of Data for config/ measured at one rotation is found again at the other one (Rotate tab) within the
    fit residuals: RG_GMC (position from the photos, session file) and Cav (position fitted)."""
    import pytest

    from quickalignment.calibration import DEFAULT_FOLDER
    from quickalignment.geometry import GATING_PLATE, Sample, SampleLayout
    from quickalignment.rotation import relocate
    from quickalignment.session import Session
    from quickalignment.stage import MotorPositions, StageModel

    record = CalibrationStore().latest("capillary")
    assert record.path.name == "calibration_2026-10-24_235500_capillary.json"
    rg = Session.load(DEFAULT_FOLDER.parent / "Data for config" / "RG_GMC_gating_session.json").layout
    cav = SampleLayout(GATING_PLATE, [Sample("Cav", *record.check["devices"]["Cav"]["uv"], length=0.2, width=0.2,
                                             height=0.525)])
    model = StageModel(record.config, GATING_PLATE)
    cases = [
        (rg, (-3.498671875, 37.796, 0.000446875, 119.999828184, -11.999708577, 60.3),
         (-6.047871875, 38.988, 0.001146875, 91.999192533, -24.000078618, 61.74)),
        (cav, (0.643128125, 38.591, -5.3125e-05, 120.00028374, -23.998825839, 58.75),
         (1.500528125, 39.593, 0.000346875, 141.999310758, -23.999053617, 58.48)),
    ]
    for layout, a, b in cases:
        first = MotorPositions(st=a[0], sz=a[1], sn=a[2], srn=a[3], srz=a[4])
        rel = relocate(model, layout, first, b[3], b[4], record.optics, a[5], keep_sn=True)
        assert rel.target.startswith(layout.samples[0].name)
        assert rel.new.st == pytest.approx(b[0], abs=0.06)
        assert rel.new.sz == pytest.approx(b[1], abs=0.06)
        assert rel.optic_new == pytest.approx(b[5], abs=0.1)
