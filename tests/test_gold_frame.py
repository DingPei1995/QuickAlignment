"""Gold-frame calibration: simulated SZ lines over a frame with known faults must give back the constants."""

from dataclasses import replace

import numpy as np
import pytest

from quickalignment.calibration import CalibrationRecord, CalibrationStore
from quickalignment.gold_frame import (
    GoldFrame, Instrument, Scan, Setup, SNPoint, fit_global, plan_scan, profile_edges, record_for,
    simulated_measurement, sn_focus_error, sn_point_plan, survey_plan,
)
from quickalignment.stage import OpticsCalibration, StageConfig

TRUE = StageConfig(st0=-0.95, sz0=40.63, sn_f=-0.525, srn_axis_u=-0.26, srn_axis_v=-0.05,
                   srz_offset_t=-0.23, srz_offset_n=2.59)
# what the beamline believes before: the lines are placed with it, the fit starts from it
GUIDE = replace(TRUE, st0=-1.0, sz0=40.6, srn_axis_u=0.0, srn_axis_v=0.0, srz_offset_t=0.0, srz_offset_n=2.3)
WIDE = dict(analyzer_fwhm_h=50.0, analyzer_fwhm_v=50.0, analyzer_fwhm_axial=50.0)
H = 0.05


def truth(frame=None, **inst) -> Setup:
    m = Setup(TRUE, GoldFrame(height=H)).frame_motors()
    return Setup(TRUE, frame or GoldFrame(height=H),
                 Instrument(**{"counts": 3000, **WIDE, **inst}, scale_st_ref=m.st, scale_sz_ref=m.sz))


def measure(t: Setup, seed=0, **kw):
    return simulated_measurement(Setup(GUIDE, GoldFrame(height=H)), t, rng=np.random.default_rng(seed), **kw)


def fit(t: Setup, scans, **kw):
    return fit_global(list(scans.values()), t.frame_motors().sn, GoldFrame(height=H), GUIDE, **kw)


def expected(t: Setup) -> StageConfig:
    """The constants the fit should give: a mounting shift of the frame goes into ST0 / SZ0 and the axes."""
    du, dv, c = t.frame.u, t.frame.v, t.config
    return replace(c, st0=c.st0 - du, sz0=c.sz0 - dv, srn_axis_u=c.srn_axis_u - du, srn_axis_v=c.srn_axis_v - dv,
                   srz_offset_t=c.srz_offset_t - du)


TOL = {"st0": 0.005, "sz0": 0.005, "sn_f": 1e-9, "srn_axis_u": 0.005, "srn_axis_v": 0.005,
       "srz_offset_t": 0.025, "srz_offset_n": 0.025}


def check(result, t, tol=TOL):
    exp = expected(t)
    for name, limit in tol.items():
        assert getattr(result.setup.config, name) == pytest.approx(getattr(exp, name), abs=limit), name


def test_the_plan_crosses_the_frame():
    guide = Setup(GUIDE, GoldFrame(height=H))
    plan = survey_plan(guide)
    groups = [p.group for p in plan]
    assert groups.count("A") == 5 and groups.count("B") == 10 and groups.count("C") == 18
    assert {p.srn for p in plan if p.group == "B"} == {165.0, 75.0}
    assert all(p.srz == 0 for p in plan if p.group in "AB") and all(p.srz != 0 for p in plan if p.group == "C")
    scan = plan_scan(plan)
    for i, p in enumerate(plan):
        e = guide.edges(scan, i)
        assert e[0] < e[3], i  # every line crosses the frame
        if abs(p.du) < 0.3:
            assert e[1] < e[2], i  # and the hole near the centre
    # one SN per SRn / SRz setting: ST alone moves between the lines of a group
    for key in {(p.srn, p.srz) for p in plan}:
        assert len({round(p.sn, 9) for p in plan if (p.srn, p.srz) == key}) == 1


def test_perfect_frame_gives_back_every_constant():
    t = truth()
    result = fit(t, measure(t))
    check(result, t)
    assert result.values["frame.rotation"] == pytest.approx(0, abs=0.1)
    assert result.values["frame.tilt_u"] == pytest.approx(0, abs=0.1)
    assert result.rms < 0.005 and not result.notes and not result.kept


def test_a_shifted_turned_and_tilted_frame():
    t = truth(GoldFrame(height=H, u=0.3, v=-0.2, rotation=3.0, tilt_u=1.5))
    result = fit(t, measure(t, overview=True))
    check(result, t)
    assert result.values["frame.rotation"] == pytest.approx(3.0, abs=0.1)
    assert result.values["frame.tilt_u"] == pytest.approx(1.5, abs=0.15)
    assert result.overview is not None


def test_ignoring_the_tilt_biases_the_srz_axis():
    t = truth(GoldFrame(height=H, tilt_u=2.0))
    scans = measure(t)
    free = fit(t, scans)
    fixed = fit(t, scans, free_tilt=False)
    check(free, t)
    assert abs(fixed.setup.config.srz_offset_t - TRUE.srz_offset_t) > 0.04


def test_motor_scales_are_measured_and_reported():
    t = truth(st_scale=1.02, sz_scale=0.99)
    result = fit(t, measure(t))
    assert result.values["instrument.st_scale"] == pytest.approx(1.02, abs=0.003)
    assert result.values["instrument.sz_scale"] == pytest.approx(0.99, abs=0.002)
    assert any("ST scale" in n for n in result.notes) and any("SZ scale" in n for n in result.notes)
    check(result, t)


def test_a_narrow_analyzer_does_not_matter_for_sz_lines():
    """SZ runs along the turned surface (and the SRz axis): the lit point does not slide along the beam."""
    t = truth(analyzer_fwhm_h=0.5, analyzer_fwhm_v=0.5, analyzer_fwhm_axial=3.0)
    result = fit(t, measure(t))
    assert result.lines_used >= result.lines_total - 2  # at most a faint line or two left out
    check(result, t)


def test_what_the_data_cannot_fix_is_kept():
    t = truth()
    scans = {k: s for k, s in measure(t).items() if s.base["srz"][0] == 0}  # no SRz turned
    result = fit(t, scans)
    for name in ("srz_offset_t", "srz_offset_n", "frame.tilt_u"):
        assert name in result.kept
    assert result.setup.config.srz_offset_n == GUIDE.srz_offset_n
    assert any("SRz axis kept" in n for n in result.notes)
    check(result, t, {k: v for k, v in TOL.items() if not k.startswith("srz")})


def _sn_peak(t: Setup, p: SNPoint) -> SNPoint:
    """The SN (ST following) at which the gold under the beam is at the analyzer focus, as measured."""
    e0 = sn_focus_error(t, p)
    e1 = sn_focus_error(t, replace(p, sn=p.sn + 1.0, st=p.st - 1.0))
    d = -e0 / (e1 - e0)
    return replace(p, sn=p.sn + d, st=p.st - d)


def test_sn_points_give_the_srz_axis_without_srz_lines():
    t = truth()
    scans = {k: s for k, s in measure(t).items() if s.base["srz"][0] == 0}
    points = [_sn_peak(t, p) for p in sn_point_plan(Setup(GUIDE, GoldFrame(height=H)))]
    result = fit(t, scans, sn_points=points)
    assert "srz_offset_t" not in result.kept
    check(result, t, {"srz_offset_t": 0.01, "srz_offset_n": 0.01})
    assert max(abs(r) for r in result.sn_residuals) < 0.002


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
    t = truth()
    result = fit(t, measure(t))
    store = CalibrationStore(tmp_path)
    saved = store.save(record_for(result, OpticsCalibration(optic_type="capillary"), "gold frame test"))
    back = store.latest("capillary")
    assert back.path == saved.path
    assert back.config == replace(result.setup.config, **{k: float(getattr(result.setup.config, k))
                                                          for k in ("st0", "sz0", "sn_f")})
    assert back.check["type"].startswith("gold frame")
    assert isinstance(CalibrationRecord.from_dict(back.to_dict()), CalibrationRecord)


def test_spem_files_round_trip(tmp_path):
    pytest.importorskip("h5py")
    from quickalignment.spem_nxs import read_scan, stage_of, write_scan

    assert stage_of("i12-m-cx1/ex/sample-mt_srn/position") == "srn"
    assert stage_of("i12-m-cx1/ex/pi/x") == "pix"
    assert stage_of("i12-m-cx1/ex/heason/total_int") is None
    t = truth()
    scans = measure(t, overview=True, srn_sweep=True)
    for key, scan in scans.items():
        write_scan(tmp_path / f"{key}.nxs", scan, optic_position=60.3)
        back = read_scan(tmp_path / f"{key}.nxs")
        assert back.intensity == pytest.approx(scan.intensity)
        assert back.info["optic_position"] == pytest.approx(60.3)
        for m in ("st", "sn", "sz", "srn", "srz"):
            assert back.motor_grid(m) == pytest.approx(scan.motor_grid(m), abs=1e-9), (key, m)
    assert read_scan(tmp_path / "srn_sweep.nxs").kind == "srn_sz"
    # one line per file is a scan of its own
    s = scans["srn165_srz-25"]
    line = Scan("sz_lines", s.x[:1], s.y, {k: v[:1] for k, v in s.base.items()}, {k: v[:1] for k, v in s.slope.items()},
                s.intensity[:, :1])
    write_scan(tmp_path / "line.nxs", line)
    back = read_scan(tmp_path / "line.nxs")
    assert back.kind == "sz_lines" and len(back.x) == 1
    assert back.motor_grid("sz") == pytest.approx(line.motor_grid("sz"))
    assert back.base["srz"][0] == pytest.approx(-25.0)


def test_a_second_motor_that_does_not_move_on_a_line_is_read_as_fixed(tmp_path):
    pytest.importorskip("h5py")
    from quickalignment.spem_nxs import read_scan, write_scan

    y = np.linspace(-1, 1, 51)
    base = {k: np.zeros(2) for k in ("st", "sn", "sz", "srn", "srz", "pix", "piy")}
    slope = {k: np.zeros(2) for k in base}
    base.update(st=np.array([-1.0, -1.2]), sn=np.array([0.3, -0.4]), sz=np.array([40.0, 40.0]),
                srn=np.full(2, 120.0), pix=np.full(2, 150.0), piy=np.full(2, 150.0))
    slope.update(sz=np.ones(2), sn=np.array([0.2, 0.0]))  # SN moves with SZ on line 1 only
    scan = Scan("lines", np.arange(2.0), y, base, slope, np.ones((len(y), 2)))
    write_scan(tmp_path / "two.nxs", scan)
    back = read_scan(tmp_path / "two.nxs")
    for m in ("sz", "sn"):
        assert back.motor_grid(m) == pytest.approx(scan.motor_grid(m), abs=1e-9), m


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


def test_command_line_plan_and_fit(tmp_path, capsys):
    pytest.importorskip("h5py")
    from quickalignment.gold_frame_cli import main, read_sn_points, save_scan

    configs = tmp_path / "configs"
    configs.mkdir()
    assert main(["plan", "--configs", str(configs), "--csv", str(tmp_path / "plan.csv")]) == 0
    text = (tmp_path / "plan.csv").read_text(encoding="utf-8")
    assert text.startswith("group,srn,srz,du,st,sn,sz_from,sz_to") and "," in text and ";" not in text
    assert len(read_sn_points(tmp_path / "plan.csv")) == 0  # the SN rows come after the plan, not read as points

    t = truth()
    files = [str(save_scan(scan, tmp_path / key, optic=60.3)) for key, scan in measure(t, overview=True).items()]
    points = tmp_path / "sn.csv"
    points.write_text("srn,srz,st,sz,sn\n120,-20,-2.5,40.6,-0.7\n", encoding="utf-8")
    assert main(["fit", *files, "--sn-gold", str(t.frame_motors().sn), "--configs", str(configs), "--save"]) == 0
    out = capsys.readouterr().out
    assert "saved:" in out
    record = CalibrationStore(configs).latest("capillary")
    assert record.config.srz_offset_n == pytest.approx(TRUE.srz_offset_n, abs=0.025)
    assert record.optics.enabled and record.optics.optic_position == pytest.approx(60.3)
    assert len(read_sn_points(points)) == 1


def test_calibration_window_loads_fits_and_saves(tmp_path, monkeypatch):
    pytest.importorskip("h5py")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt = pytest.importorskip("quickalignment.ui._qt")
    from quickalignment.ui.gold_frame_window import GoldFrameWindow, PlanDialog, SNPointsDialog

    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    monkeypatch.setattr(qt.QtWidgets.QMessageBox, "information", staticmethod(lambda *a, **k: 0))
    monkeypatch.setattr(qt.QtWidgets.QMessageBox, "warning", staticmethod(lambda *a, **k: 0))
    store = CalibrationStore(tmp_path)
    win = GoldFrameWindow(store)
    plan = PlanDialog(win.guide(), win.newest_record(), win)
    assert len(plan.plan) == 33
    assert not win.save_button.isEnabled()
    win.load_example()  # the planned lines simulated, written as .nxs files and loaded
    assert len(win.files) >= 9
    # optional SN points: only in their dialog, rows without a measured SN are not used
    dialog = SNPointsDialog(win.guide(), [], None, win)
    dialog.fill_planned()
    assert dialog.table.rowCount() == 6 and dialog.points() == []
    dialog.table.item(0, 5).setText(dialog.table.item(0, 6).text())  # "measured" = expected
    assert len(dialog.points()) == 1
    win.fit()
    app.processEvents()
    assert win.result is not None and win.save_button.isEnabled()
    assert win.table.rowCount() >= 7
    win.comment.setText("window test")
    win.save()
    record = store.latest("capillary")
    assert record.path is not None and record.comment.startswith("window test")
    assert record.optics.enabled
    win.remove_selected()  # nothing selected: nothing removed
    win.clear_files()
    assert win.result is None and not win.save_button.isEnabled()
    win.close()
