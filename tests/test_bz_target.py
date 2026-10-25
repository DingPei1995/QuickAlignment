import numpy as np
import pytest

from quickalignment import bz_target as bt
from quickalignment.rotation import AnalyzerGeometry, analyzer_angles, emission_in_plate, plate_to_lab_dir
from quickalignment.stage import MotorPositions, StageModel

MODEL, GEO = StageModel(), AnalyzerGeometry()


def make_target(a, hv, tilt=(0.0, 0.0), azimuth=20.0, m=MotorPositions(), **kw):
    """Map angles of Gamma and of a K point for a sample whose normal is tilted by (tilt_u, tilt_v) deg on the plate."""
    n = np.array([np.tan(np.radians(tilt[0])), np.tan(np.radians(tilt[1])), 1.0])
    n /= np.linalg.norm(n)
    e1 = np.array([np.cos(np.radians(azimuth)), np.sin(np.radians(azimuth)), 0.0])
    e1 -= (e1 @ n) * n
    e1 /= np.linalg.norm(e1)
    s = bt.gamma_k(a) / bt.k0(hv)
    lab = plate_to_lab_dir(MODEL, m.srn, m.srz)
    gamma = analyzer_angles(GEO, lab @ n)
    ref = analyzer_angles(GEO, lab @ (np.sqrt(1 - s * s) * n + s * e1))
    return bt.HexTarget(a, hv, gamma, "K", ref, m, **kw)


def feature_direction(t, cand, hv):
    frame = bt.SampleFrame(MODEL, GEO, t)
    return frame, frame.direction(*cand.k, bt.k0(hv, t.binding, t.work_function))


def test_frame_recovers_lattice():
    t = make_target(3.282, 95, tilt=(2.0, -1.5))
    frame = bt.SampleFrame(MODEL, GEO, t)
    assert frame.ref_k == pytest.approx(bt.gamma_k(3.282), rel=1e-9)
    assert frame.tilt == pytest.approx(np.degrees(np.arccos(1 / np.sqrt(1 + np.tan(np.radians(2)) ** 2
                                                                        + np.tan(np.radians(1.5)) ** 2))))


def test_wse2_k_radial_at_95ev():
    """Flat WSe2, 95 eV: K at the slit centre with the deflector at 0 needs SRz = -(emission angle), slit along Γ-K."""
    t = make_target(3.282, 95, feature="K (K or K′)", line=0)
    adv = bt.advise(MODEL, GEO, t, 95, "zone plate")
    assert adv.ok and not adv.hv_ok
    best = adv.best
    emission = np.degrees(np.arcsin(bt.gamma_k(3.282) / bt.k0(95)))
    assert best.srz == pytest.approx(-emission, abs=0.05)  # SRz < 0 preferred (beam closer to normal)
    assert bt.SRN_RANGE[0] <= best.srn <= bt.SRN_RANGE[1]
    _, d = feature_direction(t, best, 95)
    th, ph = analyzer_angles(GEO, plate_to_lab_dir(MODEL, best.srn, best.srz) @ d)
    assert abs(th) < 0.05 and abs(ph) < 0.05
    assert best.direction_error < 0.1


@pytest.mark.parametrize("feature, line", [("Γ", 0), ("Γ", 1), ("K only", 0), ("K′ only", 0), ("M", 0)])
@pytest.mark.parametrize("tilt", [(0.0, 0.0), (3.0, -2.0)])
def test_solutions_put_the_point_on_the_slit(feature, line, tilt):
    t = make_target(2.46, 120, tilt=tilt, m=MotorPositions(srn=131, srz=-4), feature=feature, line=line)
    cands = bt.candidates(MODEL, GEO, t, 120)
    assert cands
    for c in cands:
        if abs(c.ideal_srz - c.srz) > 1e-9 or abs(c.ideal_srn - c.srn) > 1e-9:
            continue  # clamped to the motor ranges
        frame, d = feature_direction(t, c, 120)
        th, ph = analyzer_angles(GEO, plate_to_lab_dir(MODEL, c.srn, c.srz) @ d)
        assert th == pytest.approx(c.ideal_theta, abs=0.05) and abs(ph) < 0.05
        assert c.direction_error < 0.1
    assert cands[0].ok
    if feature.startswith("K") and "only" in feature:
        assert all(c.label.split(" ")[0] == feature.split(" ")[0] for c in cands)


def test_zone_edge_needs_the_deflector_and_offers_the_radial_cut():
    t = make_target(3.282, 95, feature="K (K or K′)", line=1)
    adv = bt.advise(MODEL, GEO, t, 95, "zone plate")
    assert not adv.ok
    emission = np.degrees(np.arcsin(bt.gamma_k(3.282) / bt.k0(95)))
    assert abs(adv.best.ideal_theta) == pytest.approx(emission, abs=0.1)
    assert adv.alternative is not None and adv.alternative.ok
    assert any("deflector map" in m for m in adv.messages)


def test_graphene_k_at_low_energy_needs_more_photon_energy():
    t = make_target(2.46, 30, feature="K (K or K′)", line=0)
    adv = bt.advise(MODEL, GEO, t, 30, "capillary")
    assert not adv.ok
    assert any("SRz" in p for p in adv.best.problems)
    (lo, hi), = adv.hv_ok
    assert hi == bt.HV_RANGE[1]
    # the lowest photon energy works, one eV less does not
    assert bt.candidates(MODEL, GEO, t, lo)[0].ok and not bt.candidates(MODEL, GEO, t, lo - 1)[0].ok
    assert any(f"{lo:g} … 180 eV" in m for m in adv.messages)


def test_zone_plate_is_told_to_change_optic():
    t = make_target(2.46, 95, feature="M", line=0)
    adv = bt.advise(MODEL, GEO, t, 140, "zone plate")
    assert any("95 eV only" in m for m in adv.messages)


def test_wrong_lattice_is_flagged():
    t = make_target(3.282, 95, feature="K (K or K′)")
    t.a = 2.46
    adv = bt.advise(MODEL, GEO, t, 95)
    assert any(m.startswith("Check the input") for m in adv.messages)


def test_remount_text_for_srn():
    c = bt.Candidate("K", 180.0, -10.0, 0.0, 0.0, 0.0, 195.0, -10.0, 0.0, (1.0, 0.0),
                     problems=["needs SRn = 195.0° (range 60 … 180°)"])
    text = bt._remount_text(c)
    assert "15° counter-clockwise" in text and "75°" in text


def test_map_axes_match_the_contour():
    m = MotorPositions(srn=137, srz=-6)
    t = make_target(3.282, 95, tilt=(1.0, 0.5), m=m)
    frame = bt.SampleFrame(MODEL, GEO, t)
    view = bt.map_axes(MODEL, GEO, frame, m)
    kp = bt.k0(95)
    g = bt.angles_to_k(MODEL, GEO, frame, kp, m.srn, m.srz, *t.gamma)
    for th, ph, sx, sy in ((4.0, 0.0, 1, 0), (0.0, 4.0, 0, 1)):
        x, y = view @ (bt.angles_to_k(MODEL, GEO, frame, kp, m.srn, m.srz, t.gamma[0] + th, t.gamma[1] + ph) - g)
        assert np.sign(x) == sx or abs(x) < 0.01 * abs(y)
        assert np.sign(y) == sy or abs(y) < 0.01 * abs(x)


def test_k_angles_roundtrip():
    m = MotorPositions(srn=110, srz=-12)
    t = make_target(3.282, 95, tilt=(2.0, 1.0))
    frame = bt.SampleFrame(MODEL, GEO, t)
    kp = bt.k0(95)
    k = bt.angles_to_k(MODEL, GEO, frame, kp, m.srn, m.srz, np.array([3.0, -7.0]), np.array([5.0, 1.0]))
    th, ph = bt.k_to_angles(MODEL, GEO, frame, kp, m.srn, m.srz, k)
    assert th == pytest.approx([3.0, -7.0], abs=1e-9) and ph == pytest.approx([5.0, 1.0], abs=1e-9)


def test_preview_draws():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    t = make_target(2.46, 95, feature="K (K or K′)")
    adv = bt.advise(MODEL, GEO, t, 95)
    fig = Figure()
    bt.draw_preview(fig, MODEL, GEO, t, 95, adv.best, adv.frame)
    assert len(fig.axes) == 2
    bt.draw_preview(fig, MODEL, GEO, t, 95, None, adv.frame)


def test_emission_in_plate_matches_target_inputs():
    t = make_target(3.282, 95, m=MotorPositions(srn=120, srz=0))
    assert np.allclose(emission_in_plate(MODEL, GEO, t.measured, *t.gamma), [0, 0, 1])
