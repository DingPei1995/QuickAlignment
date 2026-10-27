"""Gold-frame calibration: simulated maps of a frame with known faults must give back the constants."""

from dataclasses import replace

import numpy as np
import pytest

from quickalignment.calibration import CalibrationRecord, CalibrationStore
from quickalignment.gold_frame import (
    GoldFrame, Instrument, Setup, calibrate, fit_st_sz, make_scan, profile_edges, record_for, standard_scans,
    tilt_width_factor,
)
from quickalignment.stage import OpticsCalibration, StageConfig

TRUE = StageConfig(st0=-0.95, sz0=40.63, sn_f=-0.525, srn_axis_u=-0.26, srn_axis_v=-0.05,
                   srz_offset_t=-0.23, srz_offset_n=2.59)
NOMINAL = Setup(StageConfig(st0=-1.0, sz0=40.6, sn_f=-0.5))  # what the beamline believes before
WIDE = dict(analyzer_fwhm_h=50.0, analyzer_fwhm_v=50.0, analyzer_fwhm_axial=50.0)


def measure(truth: Setup, surface=False, step=0.025, seed=0):
    scans = standard_scans(NOMINAL, step=step, surface=surface)
    rng = np.random.default_rng(seed)
    for s in scans.values():
        truth.simulate(s, rng)
    return scans


def run(truth: Setup, frame=None, **kw):
    scans = measure(truth, kw.pop("surface", False))
    return calibrate(scans["step1"], truth.frame_motors().sn, frame or GoldFrame(height=truth.frame.height),
                     scans["step2"], scans["step3"], **kw), scans


def test_perfect_frame_gives_back_every_constant():
    res, _ = run(Setup(TRUE, GoldFrame(), Instrument(counts=3000, **WIDE)))
    c = res.setup.config
    for name, tol in (("st0", 0.005), ("sz0", 0.005), ("sn_f", 1e-9), ("srn_axis_u", 0.008), ("srn_axis_v", 0.008),
                      ("srz_offset_t", 0.015), ("srz_offset_n", 0.015)):
        assert getattr(c, name) == pytest.approx(getattr(TRUE, name), abs=tol), name
    assert res.step1.values["rotation"] == pytest.approx(0, abs=0.05)
    assert res.step1.values["scale_st"] == pytest.approx(1, abs=0.003)
    assert not res.notes


def test_a_shifted_frame_moves_st0_sz0_and_the_axes_with_it():
    """The frame is taken to be at the plate centre: a mounting shift (du, dv) is indistinguishable
    from a shift of the whole plate, so ST0 / SZ0 and the axes (in plate coordinates) take it."""
    du, dv = 0.3, -0.2
    truth = Setup(TRUE, GoldFrame(u=du, v=dv, rotation=3.0), Instrument(counts=3000, **WIDE))
    res, _ = run(truth, surface=True)
    c = res.setup.config
    assert c.st0 == pytest.approx(TRUE.st0 - du, abs=0.003)
    assert c.sz0 == pytest.approx(TRUE.sz0 - dv, abs=0.003)
    assert c.srn_axis_u == pytest.approx(TRUE.srn_axis_u - du, abs=0.005)
    assert c.srn_axis_v == pytest.approx(TRUE.srn_axis_v - dv, abs=0.005)
    assert c.srz_offset_t == pytest.approx(TRUE.srz_offset_t - du, abs=0.015)
    assert c.srz_offset_n == pytest.approx(TRUE.srz_offset_n, abs=0.015)
    assert res.step1.values["rotation"] == pytest.approx(3.0, abs=0.1)


def test_motor_scales_are_measured_and_reported():
    truth = Setup(TRUE, GoldFrame(), Instrument(st_scale=1.02, sz_scale=0.99, counts=3000,
                                                scale_st_ref=-0.95, scale_sz_ref=40.63, **WIDE))
    scans = measure(truth)
    r = fit_st_sz(scans["step1"])
    # ST is the slow axis of the map (point by point): its edges are only known to a pixel (25 um on 2 mm)
    assert r.values["scale_st"] == pytest.approx(1.02, abs=0.008)
    assert r.values["scale_sz"] == pytest.approx(0.99, abs=0.003)
    res = calibrate(scans["step1"], truth.frame_motors().sn, GoldFrame(), None, None)
    assert any("ST scale" in n for n in res.notes) and any("SZ scale" in n for n in res.notes)


def test_a_narrow_analyzer_loses_lines_of_the_plain_st_scan_but_not_the_result():
    truth = Setup(TRUE, GoldFrame(), Instrument(counts=3000, analyzer_fwhm_h=0.5, analyzer_fwhm_v=0.5))
    plain, _ = run(truth)
    along, _ = run(truth, surface=True)
    assert plain.step3.used_lines < len(_["step3"].x)  # part of the frame not seen at large SRz
    assert along.step3.used_lines == len(_["step3"].x)
    for res in (plain, along):
        assert res.setup.config.srz_offset_t == pytest.approx(TRUE.srz_offset_t, abs=0.03)
        assert res.setup.config.srz_offset_n == pytest.approx(TRUE.srz_offset_n, abs=0.03)


def test_a_tilted_gold_face_is_fitted_in_step_3():
    truth = Setup(TRUE, GoldFrame(tilt_u=2.0), Instrument(counts=3000, **WIDE))
    assert tilt_width_factor(truth) == pytest.approx(0.965, abs=0.003)
    scans = measure(truth, surface=True)
    sn = truth.frame_motors().sn
    fixed = calibrate(scans["step1"], sn, GoldFrame(), None, scans["step3"], free_tilt=False)
    free = calibrate(scans["step1"], sn, GoldFrame(), None, scans["step3"], free_tilt=True)
    assert abs(fixed.setup.config.srz_offset_t - TRUE.srz_offset_t) > 0.05  # ignoring the tilt biases the axis
    assert free.step3.values["frame.tilt_u"] == pytest.approx(2.0, abs=0.15)
    assert free.setup.config.srz_offset_t == pytest.approx(TRUE.srz_offset_t, abs=0.015)
    assert free.setup.instrument.st_scale == pytest.approx(1.0, abs=0.003)


def test_profile_edges():
    y = np.linspace(-3, 3, 601)
    gold = (np.abs(y) <= 1) & (np.abs(y) >= 0.5)
    e = profile_edges(y, np.where(gold, 1.0, 0.3))
    assert e == pytest.approx([-1, -0.5, 0.5, 1], abs=0.006)
    assert profile_edges(y[::-1], np.where(gold, 1.0, 0.3)[::-1]) == pytest.approx(e)
    assert profile_edges(y, np.where(np.abs(y) <= 1, 1.0, 0.3)) == pytest.approx([-1, 1], abs=0.006)
    rng = np.random.default_rng(1)
    assert profile_edges(y, 0.3 + 0.01 * rng.standard_normal(len(y))) is None  # no frame on this line
    # a dark wall strip next to an edge does not count as an edge
    wall = np.where(gold, 1.0, np.where((y > 1) & (y < 1.05), 0.05, 0.3))
    assert profile_edges(y, wall) == pytest.approx([-1, -0.5, 0.5, 1], abs=0.006)


def test_the_record_is_a_valid_configuration(tmp_path):
    res, _ = run(Setup(TRUE, GoldFrame(), Instrument(**WIDE)))
    store = CalibrationStore(tmp_path)
    saved = store.save(record_for(res, OpticsCalibration(optic_type="capillary"), "gold frame test"))
    back = store.latest("capillary")
    assert back.path == saved.path
    assert back.config == replace(res.setup.config, **{k: float(getattr(res.setup.config, k))
                                                       for k in ("st0", "sz0", "sn_f")})
    assert back.check["type"].startswith("gold frame")
    assert isinstance(CalibrationRecord.from_dict(back.to_dict()), CalibrationRecord)


def test_spem_files_round_trip(tmp_path):
    pytest.importorskip("h5py")
    from quickalignment.spem_nxs import read_lines, read_scan, stage_of, write_scan

    assert stage_of("i12-m-cx1/ex/sample-mt_srn/position") == "srn"
    assert stage_of("i12-m-cx1/ex/pi/x") == "pix"
    assert stage_of("i12-m-cx1/ex/heason/total_int") is None
    truth = Setup(TRUE, GoldFrame(), Instrument(counts=3000, **WIDE))
    scans = measure(truth)
    for key, scan in scans.items():
        write_scan(tmp_path / f"{key}.nxs", scan, optic_position=60.3)
        back = read_scan(tmp_path / f"{key}.nxs")
        assert back.kind == scan.kind
        assert back.intensity == pytest.approx(scan.intensity)
        assert back.info["optic_position"] == pytest.approx(60.3)
        for m in ("st", "sn", "sz", "srn", "srz"):
            assert back.motor_grid(m) == pytest.approx(scan.motor_grid(m), abs=1e-9), (key, m)
    # step 2 as one SZ line per SRn
    s2, paths = scans["step2"], []
    for i in range(0, len(s2.x), 2):
        line = make_scan("srn_sz", [s2.x[i]], s2.y, s2.motors(i, 0.0))
        line.base["sz"][:], line.slope["sz"][:] = 0.0, 1.0
        line.intensity = s2.intensity[:, i:i + 1]
        write_scan(tmp_path / f"line{i}.nxs", line)
        paths.append(tmp_path / f"line{i}.nxs")
    lines = read_lines(paths[::-1])
    assert lines.kind == "srn_sz" and lines.x == pytest.approx(s2.x[::2])
    assert lines.intensity == pytest.approx(s2.intensity[:, ::2])


def test_image32_is_summed_when_there_is_no_total_intensity(tmp_path):
    h5py = pytest.importorskip("h5py")
    from quickalignment.spem_nxs import read_scan

    n2, n1 = 3, 4
    with h5py.File(tmp_path / "map.nxs", "w") as f:  # the real layout: (outer, inner, slices, energy)
        sd = f.create_group("img1_0001/scan_data")
        a = sd.create_dataset("actuator_1_1", data=np.tile(np.linspace(40, 41, n1), (n2, 1)))
        a.attrs["long_name"], a.attrs["axis"] = "i12-m-cx1/ex/sample-mt_sz/position", "1"
        b = sd.create_dataset("actuator_2_1", data=np.array([100.0, 110.0, 120.0]))
        b.attrs["long_name"], b.attrs["axis"] = "i12-m-cx1/ex/sample-mt_srn/position", "2"
        sd.create_dataset("trajectory_1_1", data=np.linspace(40, 41, n1))
        sd.create_dataset("trajectory_2_1", data=np.array([100.0, 110.0, 120.0]))
        img = sd.create_dataset("data_11", data=np.ones((n2, n1, 5, 7), np.int32))
        img.attrs["long_name"] = "i12-m-cx1/ex/mbs/image32"
    scan = read_scan(tmp_path / "map.nxs")
    assert scan.kind == "srn_sz"
    assert scan.intensity.shape == (n1, n2) and np.all(scan.intensity == 35)
    assert scan.info["channel"].endswith("image32")


def test_command_line_fit_saves_a_configuration(tmp_path, capsys):
    pytest.importorskip("h5py")
    from quickalignment.gold_frame_cli import main
    from quickalignment.spem_nxs import write_scan

    truth = Setup(TRUE, GoldFrame(), Instrument(counts=3000, **WIDE))
    scans = measure(truth)
    files = {}
    for key, scan in scans.items():
        files[key] = str(tmp_path / f"{key}.nxs")
        write_scan(files[key], scan, optic_position=60.3)
    configs = tmp_path / "configs"
    configs.mkdir()
    assert main(["fit", "--step1", files["step1"], "--step2", files["step2"], "--step3", files["step3"],
                 "--sn-gold", str(truth.frame_motors().sn), "--configs", str(configs), "--save"]) == 0
    out = capsys.readouterr().out
    assert "saved:" in out
    record = CalibrationStore(configs).latest("capillary")
    assert record.config.srz_offset_n == pytest.approx(TRUE.srz_offset_n, abs=0.015)
    assert record.optics.enabled and record.optics.optic_position == pytest.approx(60.3)
