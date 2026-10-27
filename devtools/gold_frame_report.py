"""Figures and numbers of the gold-frame report (docs/GOLD_FRAME_REPORT_<lang>.md).

Writes docs/images/gold_frame/*.png and docs/images/gold_frame/results.json, and fills the tables of each
report (between its RESULTS TABLE / EFFORT TABLE markers); the PDFs are then built with
``python devtools/build_guides.py gold``.

Usage:  python devtools/gold_frame_report.py          (everything, a few minutes)
        python devtools/gold_frame_report.py tables   (only the tables in the reports, from results.json)
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from quickalignment.gold_frame import (  # noqa: E402
    GoldFrame, Instrument, Setup, fit_global, simulated_measurement, sn_focus_error, sn_point_plan, sn_scan,
    survey_plan,
)
from quickalignment.gold_frame_plot import draw_survey  # noqa: E402
from quickalignment.stage import N_HAT, T_HAT, StageConfig  # noqa: E402

OUT = HERE / "docs" / "images" / "gold_frame"
H = 0.05  # gold top above the riser top
# perfect: frame at the plate centre, SRn axis through it, SRz axis in the gold surface through it
PERFECT = StageConfig(st0=-0.95, sz0=40.63, sn_f=-0.525, srn_axis_u=0.0, srn_axis_v=0.0,
                      srz_offset_t=0.0, srz_offset_n=-H)
# the newest configuration (2026-10-24 23:55, capillary): SRz axis 2.59 mm behind the riser top
REAL = replace(PERFECT, srn_axis_u=-0.26, srn_axis_v=-0.05, srz_offset_t=-0.23, srz_offset_n=2.59)
# what the beamline believes before the calibration: the lines are placed with it (0.2 ... 0.3 mm off)
GUIDE = replace(REAL, st0=-1.0, sz0=40.6, srn_axis_u=0.0, srn_axis_v=0.0, srz_offset_t=0.0, srz_offset_n=2.3)
WIDE = dict(analyzer_fwhm_h=50.0, analyzer_fwhm_v=50.0, analyzer_fwhm_axial=50.0)
GROUP_COLOURS = {"A": "#1f77b4", "B": "#d62728", "C": "#2ca02c"}


def setup(config=PERFECT, frame=None, **inst) -> Setup:
    frame = frame or GoldFrame(height=H)
    nominal = Setup(config, GoldFrame(height=H))
    m = nominal.frame_motors()
    return Setup(config, frame, Instrument(**{"counts": 3000, **WIDE, **inst}, scale_st_ref=m.st, scale_sz_ref=m.sz))


def figure(name, truth, guide_config=PERFECT, suptitle="", **kw):
    """The measurement (overview + survey lines) simulated on `truth`, placed with `guide_config`, drawn with
    the edges of the perfect frame on the guide and the true edges."""
    guide = Setup(guide_config, GoldFrame(height=H))
    scans = simulated_measurement(guide, truth, rng=np.random.default_rng(0), **kw)
    fig = plt.figure(figsize=(15.5, 5.4), layout="constrained")
    draw_survey(fig, list(scans.values()), {"perfect": guide, "true": truth})
    if suptitle:
        fig.suptitle(suptitle, fontsize=10)
    fig.savefig(OUT / name, dpi=105)
    plt.close(fig)
    return scans


def fig_geometry():
    """Top view: beam, analyzer axis, the gold surface at SRz = 0 and turned, the SRz axis behind it."""
    fig, ax = plt.subplots(figsize=(7.4, 5.6), layout="constrained")
    t, n = T_HAT[:2], N_HAT[:2]
    ax.annotate("", xy=(0, 2.2), xytext=(0, -3.2), arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=2))
    ax.text(0.08, -3.1, "beam (+y)", color="#1f77b4")
    a = -n * 3.0
    ax.annotate("", xy=a, xytext=(0, 0), arrowprops=dict(arrowstyle="<-", color="#2ca02c", lw=2))
    ax.text(*(a + np.array([-0.3, -0.25])), "analyzer (-n)", color="#2ca02c")
    D, o_t, theta = 2.6, 0.0, np.radians(20)
    axis = n * D + t * o_t
    for ang, style, label in ((0.0, "-", "gold surface, SRz = 0"), (theta, "--", "SRz = -20 deg (turned)")):
        c, s = np.cos(ang), np.sin(ang)
        R = np.array([[c, -s], [s, c]])
        e = R @ t
        p0 = axis + R @ (-n * D)
        seg = np.array([p0 - 1.6 * e, p0 + 1.6 * e])
        ax.plot(seg[:, 0], seg[:, 1], style, color="#d4a017", lw=3, label=label)
        # where the beam meets it
        lam = -(p0[0]) / e[0]
        hit = p0 + lam * e
        ax.plot(*hit, "o", color="#d62728" if ang else "#ff7f0e", ms=6)
    ax.plot(*axis, "kx", ms=10, mew=2)
    ax.text(axis[0] - 0.15, axis[1] - 0.15, "SRz axis\n(D behind the surface,\no_t along ST)", fontsize=8,
            ha="right", va="top")
    ax.annotate("", xy=t * 1.5 + np.array([-2.6, -1.9]), xytext=np.array([-2.6, -1.9]),
                arrowprops=dict(arrowstyle="->", color="k"))
    ax.text(*(t * 1.6 + np.array([-2.6, -1.9])), "+ST (t)", fontsize=8)
    ax.annotate("", xy=n * 1.5 + np.array([-2.6, -1.9]), xytext=np.array([-2.6, -1.9]),
                arrowprops=dict(arrowstyle="->", color="k"))
    ax.text(*(n * 1.6 + np.array([-2.6, -1.9])), "+SN (n)", fontsize=8)
    ax.plot(0, 0, "+", color="#2ca02c", ms=14, mew=2)
    ax.text(0.1, 0.1, "analyzer focus", color="#2ca02c", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlim(-3.4, 3.4)
    ax.set_ylim(-3.4, 2.6)
    ax.set_xlabel("lab x (mm)")
    ax.set_ylabel("lab y, along the beam (mm)")
    ax.set_title("Top view at SRn 120: turning SRz about an axis behind the surface moves\n"
                 "the point the beam meets (orange: SRz 0, red: turned) along the beam", fontsize=9)
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig(OUT / "geometry.png", dpi=110)
    plt.close(fig)




def fig_plan():
    """Where the planned lines cross the frame, on the plate (front view, frame at the centre)."""
    guide = Setup(PERFECT, GoldFrame(height=H))
    plan = survey_plan(guide)
    panels = [("A", 120.0, "A: SRn 120, SRz 0"), ("B", 165.0, "B: SRn 165 (+45°), SRz 0"),
              ("B", 75.0, "B: SRn 75 (−45°), SRz 0"), ("C", 165.0, "C: SRn 165, SRz −25 … +10")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.2), layout="constrained")
    for ax, (group, srn, title) in zip(axes, panels):
        for h in (1.0, 0.5):  # the frame, fixed to the plate
            sq = np.array([(h, h), (-h, h), (-h, -h), (h, -h), (h, h)])
            ax.fill(sq[:, 0], sq[:, 1], color="#d4a017" if h == 1.0 else "white", zorder=1)
        a = math.radians(srn - 120.0)
        rows = [p for p in plan if p.group == group and p.srn == srn]
        for p in rows:
            # an SZ line is vertical in the stage frame; on the plate it runs along R(-a) (0, 1)
            c = np.array([p.du * math.cos(a), -p.du * math.sin(a)])
            d = np.array([math.sin(a), math.cos(a)])
            seg = np.array([c - 2.2 * d, c + 2.2 * d])
            ax.plot(seg[:, 0], seg[:, 1], color=GROUP_COLOURS[group], lw=1.2, zorder=2)
        ax.set_title(title + f"  ({len(rows)} lines)", fontsize=9)
        ax.set_aspect("equal")
        ax.set_xlim(-2.2, 2.2)
        ax.set_ylim(-2.2, 2.2)
        ax.set_xlabel("plate x (mm)")
        ax.set_ylabel("plate y (mm)")
    fig.suptitle("SZ lines on the plate (front view): turning the frame by ±45° makes its edges diagonal, "
                 "so where a line crosses them gives the horizontal position too", fontsize=10)
    fig.savefig(OUT / "survey_plan.png", dpi=105)
    plt.close(fig)


def fig_srz_curves():
    """ST that keeps the frame centre on the beam (SN kept) against SRz, for some SRz axes."""
    fig, ax = plt.subplots(figsize=(6.6, 4.2), layout="constrained")
    srz = np.linspace(-25, 10, 71)
    for (o_t, D), colour in zip(((0.0, 0.0), (0.5, 0.0), (0.0, 1.0), (0.0, 2.6), (-0.23, 2.64)),
                                ("k", "#1f77b4", "#2ca02c", "#d62728", "#9467bd")):
        s = setup(replace(PERFECT, srz_offset_t=o_t, srz_offset_n=D - H))
        sn = s.frame_motors().sn
        st = np.array([s.frame_motors(srz=a, sn=sn).st for a in srz])
        ax.plot(srz, st - st[np.argmin(abs(srz))], color=colour, label=f"o_t = {o_t:+.2f}, D = {D:.2f} mm")
    ax.set_xlabel("SRz (deg)")
    ax.set_ylabel("ST of the frame centre − ST at SRz 0 (mm)")
    ax.set_title("where the frame is found against SRz (SN kept)", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.savefig(OUT / "srz_curves.png", dpi=110)
    plt.close(fig)


def fig_sn_scan(results):
    fig, ax = plt.subplots(figsize=(6.4, 4.0), layout="constrained")
    sn = np.linspace(-1.4, 0.4, 361)
    for bx, colour in ((0.0, "k"), (0.1, "#d62728")):
        s = setup(REAL, beam_x=bx, analyzer_fwhm_h=0.3, analyzer_fwhm_v=0.3, analyzer_fwhm_axial=3.0, counts=0)
        s = replace(s, instrument=replace(s.instrument, rays=1, fly=1))
        intensity = sn_scan(s, sn)
        peak = float(sn[np.argmax(intensity)])
        half = sn[intensity > intensity.max() / 2]
        ax.plot(sn, intensity, color=colour, label=f"beam {bx:.1f} mm beside the focus: peak SN {peak:.3f}, "
                                                    f"FWHM {half[-1] - half[0]:.2f}")
        results[f"sn_scan_beam_{bx:.1f}"] = {"peak": round(peak, 4), "fwhm": round(float(half[-1] - half[0]), 3)}
    ax.set_xlabel("SN (mm), ST following (dST = -dSN)")
    ax.set_ylabel("intensity on the gold")
    ax.set_title("SN scan on the gold (analyzer FWHM 0.3 mm across, 3 mm along its axis)", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.savefig(OUT / "sn_scan.png", dpi=110)
    plt.close(fig)


def miss_at_test_point(fitted: Setup, truth: Setup, u=1.5, v=1.0, srn=100.0, srz=-15.0) -> dict:
    """Where the fitted configuration sends the beam on the true stage: distance from the wanted
    plate point (on the gold top) and from the analyzer focus along the beam."""
    m = fitted.model.motors_for_target(u, v, truth.gold_w(), srn, srz)
    truth = replace(truth, frame=replace(truth.frame, tilt_u=0.0, tilt_v=0.0))  # a flat sample: the stage only
    P, D, _, _ = truth.beam_in_plate(m)
    s = float(truth._gold_s(P[None, :], D)[0])
    hit = P + s * D
    return {"plate_mm": round(float(np.hypot(hit[0] - u, hit[1] - v)), 4), "along_beam_mm": round(s, 4)}


def sn_peak(truth: Setup, p, noise=0.0, rng=None):
    """The SN (ST following) of the intensity peak at an SN point, as measured (exact + noise)."""
    e0 = sn_focus_error(truth, p)
    e1 = sn_focus_error(truth, replace(p, sn=p.sn + 1.0, st=p.st - 1.0))
    d = -e0 / (e1 - e0) + (rng.normal(0, noise) if rng is not None and noise else 0.0)
    return replace(p, sn=p.sn + d, st=p.st - d)


def run_cases(results):
    """Fit simulated measurements of known faults; how close the constants and the predictions come."""
    narrow = dict(analyzer_fwhm_h=0.5, analyzer_fwhm_v=0.5, analyzer_fwhm_axial=3.0)
    cases = [  # (label, truth, measurement options, fit options, special)
        ("perfect frame", setup(REAL), {}, {}, None),
        ("frame shifted, turned", setup(REAL, GoldFrame(height=H, u=0.3, v=-0.2, rotation=3.0)), {"overview": True}, {}, None),
        ("scales", setup(REAL, st_scale=1.02, sz_scale=0.99), {}, {}, None),
        ("tilt, not fitted", setup(REAL, GoldFrame(height=H, tilt_u=2.0)), {}, {"free_tilt": False}, None),
        ("tilt, fitted", setup(REAL, GoldFrame(height=H, tilt_u=2.0)), {}, {}, None),
        ("narrow analyzer", setup(REAL, **narrow), {}, {}, None),
        ("beam offset", setup(REAL, beam_x=0.1, analyzer_fwhm_h=0.3, analyzer_fwhm_v=0.3, analyzer_fwhm_axial=3.0),
         {}, {}, "sn_scan"),
        ("more data", setup(REAL, GoldFrame(height=H, u=0.15, v=-0.1, rotation=1.5, tilt_u=1.0), **narrow),
         {"overview": True, "srn_sweep": True}, {}, None),
        ("sn points", setup(REAL), {}, {}, "sn_points"),
    ]
    guide = Setup(GUIDE, GoldFrame(height=H))
    rows = []
    for label, truth, meas, opts, special in cases:
        rng = np.random.default_rng(1)
        scans = simulated_measurement(guide, truth, rng=rng, **{"overview": False, **meas})
        if special == "sn_points":  # no SRz lines: the SN points instead
            scans = {k: s for k, s in scans.items() if s.base["srz"][0] == 0}
            opts = {**opts, "sn_points": [sn_peak(truth, p, 0.005, rng) for p in sn_point_plan(guide)]}
        sn_gold = truth.frame_motors().sn
        if special == "sn_scan":  # SN gold from an SN scan: where the intensity peaks
            sn = np.linspace(sn_gold - 0.6, sn_gold + 0.6, 601)
            probe = replace(truth, instrument=replace(truth.instrument, counts=0, rays=1, fly=1))
            sn_gold = float(sn[np.argmax(sn_scan(probe, sn))])
        res = fit_global(list(scans.values()), sn_gold, GoldFrame(height=H), GUIDE, **opts)
        c = res.setup.config
        du, dv = truth.frame.u, truth.frame.v  # the frame shift goes into ST0 / SZ0 and the axes
        expect = replace(truth.config, st0=truth.config.st0 - du, sz0=truth.config.sz0 - dv,
                         srn_axis_u=truth.config.srn_axis_u - du, srn_axis_v=truth.config.srn_axis_v - dv,
                         srz_offset_t=truth.config.srz_offset_t - du)
        row = {"case": label, "lines": f"{res.lines_used}/{res.lines_total}",
               "error": {k: round(float(getattr(c, k) - getattr(expect, k)), 4) for k in
                         ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")},
               "sigma_srz": [round(res.sigma.get("srz_offset_t", float("nan")), 4),
                             round(res.sigma.get("srz_offset_n", float("nan")), 4)],
               "fitted": {k: round(v, 4) for k, v in res.values.items() if "." in k},
               "test_point": miss_at_test_point(res.setup, truth), "notes": res.notes}
        rows.append(row)
        print(label, row["lines"], row["error"], row["sigma_srz"], row["fitted"], row["test_point"])
    results["cases"] = rows


def effort(results):
    """Slow moves of the old scheme (three maps) and of the survey."""
    guide = Setup(GUIDE, GoldFrame(height=H))
    plan = survey_plan(guide)
    settings = list(dict.fromkeys((p.srn, p.srz) for p in plan))
    st_travel = sum(abs(b.st - a.st) for a, b in zip(plan, plan[1:]))
    results["effort"] = {
        "old": {"sz_lines": 201 + 61, "st_scan_mm": 36 * 7.0, "st_steps": 201 + 36, "srn_settings": 61,
                "srz_settings": 36},
        "new": {"sz_lines": len(plan), "st_scan_mm": 0.0, "st_steps": len(plan), "st_travel_mm": round(st_travel, 1),
                "srn_settings": len({s[0] for s in settings}) + 1, "srz_settings": len({s[1] for s in settings}) - 1},
    }


CASE_NAMES = {
    "en": {"perfect frame": "perfect frame", "frame shifted, turned": "frame shifted (0.3, −0.2) mm, turned 3°",
           "scales": "ST scale 1.02, SZ scale 0.99", "tilt, not fitted": "face tilted 2° about v, tilt not fitted",
           "tilt, fitted": "face tilted 2° about v, tilt fitted", "narrow analyzer": "analyzer acceptance 0.5 mm",
           "beam offset": "beam 0.1 mm beside the analyzer focus",
           "more data": "+ overview map + SRn sweep, frame shifted / turned / tilted, analyzer 0.5 mm",
           "sn points": "no SRz lines: 6 SN points instead (5 µm noise)"},
    "zh": {"perfect frame": "完美金框", "frame shifted, turned": "金框偏移 (0.3, −0.2) mm、面内转 3°",
           "scales": "ST 比例 1.02、SZ 比例 0.99", "tilt, not fitted": "金面绕 v 倾斜 2°，不拟合倾斜",
           "tilt, fitted": "金面绕 v 倾斜 2°，拟合倾斜", "narrow analyzer": "分析器接收范围 0.5 mm",
           "beam offset": "光束偏离分析器焦点 0.1 mm",
           "more data": "加概览图和 SRn 扫描；金框偏移、转动、倾斜；分析器 0.5 mm",
           "sn points": "无 SRz 线，改用 6 个 SN 点（噪声 5 µm）"},
    "fr": {"perfect frame": "cadre parfait", "frame shifted, turned": "cadre décalé (0,3 ; −0,2) mm, tourné de 3°",
           "scales": "échelle ST 1,02, SZ 0,99", "tilt, not fitted": "face inclinée de 2° autour de v, non ajustée",
           "tilt, fitted": "face inclinée de 2° autour de v, ajustée", "narrow analyzer": "acceptance de l'analyseur 0,5 mm",
           "beam offset": "faisceau à 0,1 mm du foyer de l'analyseur",
           "more data": "+ carte d'ensemble + balayage SRn ; cadre décalé, tourné, incliné ; analyseur 0,5 mm",
           "sn points": "sans lignes SRz : 6 points SN à la place (bruit 5 µm)"},
}
TABLE_HEAD = {
    "en": ("Errors in µm (fitted − true).",
           "| case | lines used | ST0 | SZ0 | SN_f | SRn axis x, y | SRz offset ST, SN (± σ) | test point: plate / beam |"),
    "zh": ("误差单位 µm（拟合值 − 真值）。",
           "| 情形 | 使用的线 | ST0 | SZ0 | SN_f | SRn 轴 x, y | SRz 偏移 ST, SN (± σ) | 测试点：样品板 / 沿光束 |"),
    "fr": ("Écarts en µm (ajusté − vrai).",
           "| cas | lignes utilisées | ST0 | SZ0 | SN_f | axe SRn x, y | décalage SRz ST, SN (± σ) | point test : plaque / faisceau |"),
}
EFFORT_HEAD = {
    "en": ("| | SZ lines | ST scanned | ST moves between lines | SRn settings | SRz settings |",
           ("three maps (old, ST × SRz map 3)", "SZ-line survey (new)"), "{:.0f} mm"),
    "zh": ("| | SZ 线数 | ST 扫描行程 | 线间 ST 移动次数 | SRn 角度数 | SRz 角度数 |",
           ("三张图（旧，第 3 图 ST × SRz）", "SZ 线测量（新）"), "{:.0f} mm"),
    "fr": ("| | lignes SZ | ST balayé | déplacements ST entre lignes | réglages SRn | réglages SRz |",
           ("trois cartes (ancien, carte 3 ST × SRz)", "relevé de lignes SZ (nouveau)"), "{:.0f} mm"),
}


def _between(text, start, end, new):
    a, b = text.index(start) + len(start), text.index(end)
    return text[:a] + "\n" + new + "\n" + text[b:]


def fill_tables(results):
    """The results and effort tables of each report, between their markers."""
    def um(x):
        v = int(round(x * 1000))
        return "0" if v == 0 else f"{v:+d}"

    for lang, (unit, head) in TABLE_HEAD.items():
        rows = [head, "|" + "---|" * 8]
        for c in results["cases"]:
            e, s, t = c["error"], c["sigma_srz"], c["test_point"]
            srz = (f"{um(e['srz_offset_t'])} ± {s[0] * 1000:.0f}, {um(e['srz_offset_n'])} ± {s[1] * 1000:.0f}"
                   if np.isfinite(s[0]) else "kept")
            rows.append("| " + " | ".join([
                CASE_NAMES[lang][c["case"]], c["lines"], um(e["st0"]), um(e["sz0"]), um(e["sn_f"]),
                f"{um(e['srn_axis_u'])}, {um(e['srn_axis_v'])}", srz,
                f"{t['plate_mm'] * 1000:.0f} / {um(t['along_beam_mm'])}"]) + " |")
        head_e, names, mm = EFFORT_HEAD[lang]
        old, new = results["effort"]["old"], results["effort"]["new"]
        effort_rows = [head_e, "|" + "---|" * 6,
                       f"| {names[0]} | {old['sz_lines']} | {mm.format(old['st_scan_mm'])} | {old['st_steps']} | "
                       f"{old['srn_settings']} | {old['srz_settings']} |",
                       f"| {names[1]} | {new['sz_lines']} | 0 | {new['st_steps']} ({mm.format(new['st_travel_mm'])}) | "
                       f"{new['srn_settings']} | {new['srz_settings']} |"]
        path = HERE / "docs" / f"GOLD_FRAME_REPORT_{lang}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = _between(text, "<!-- RESULTS TABLE -->", "<!-- /RESULTS TABLE -->", unit + "\n\n" + "\n".join(rows))
        if "<!-- EFFORT TABLE -->" in text:
            text = _between(text, "<!-- EFFORT TABLE -->", "<!-- /EFFORT TABLE -->", "\n".join(effort_rows))
        path.write_text(text, encoding="utf-8")


def main():
    if sys.argv[1:] == ["tables"]:  # only the tables, from the saved results
        fill_tables(json.loads((OUT / "results.json").read_text(encoding="utf-8")))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for old in ("perfect.png", "analyzer.png", "real_axes.png"):
        (OUT / old).unlink(missing_ok=True)
    results = {"perfect": {k: getattr(PERFECT, k) for k in ("st0", "sz0", "sn_f")}, "height": H}
    fig_geometry()
    fig_plan()
    fig_srz_curves()
    figure("perfect.png", setup(PERFECT), overview=True,
           suptitle="Perfect: frame at the plate centre, SRn axis through it, SRz axis in its surface")
    figure("frame_offset.png", setup(PERFECT, GoldFrame(height=H, u=0.3, v=-0.2)), overview=True,
           suptitle="Frame 0.3 mm off along +u (right, seen from the analyzer) and 0.2 mm down; axes at the plate centre")
    figure("srn_axis.png", setup(replace(PERFECT, srn_axis_u=0.4, srn_axis_v=0.3)),
           suptitle="SRn axis 0.4 mm right of and 0.3 mm above the frame centre")
    figure("srz_axis.png", setup(replace(PERFECT, srz_offset_t=0.5, srz_offset_n=1.0 - H)),
           suptitle="SRz axis 0.5 mm along +ST and 1.0 mm behind the gold surface")
    figure("real_axes.png", setup(REAL), guide_config=REAL, overview=True,
           suptitle="Axes of the newest configuration, lines placed with it")
    figure("rotation_tilt.png", setup(PERFECT, GoldFrame(height=H, rotation=3.0, tilt_u=2.0)),
           suptitle="Frame turned 3° in plane and its face tilted 2° about v")
    fig_sn_scan(results)
    effort(results)
    run_cases(results)
    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    fill_tables(results)
    print(OUT / "results.json")


if __name__ == "__main__":
    main()
