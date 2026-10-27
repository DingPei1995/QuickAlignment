"""Figures and numbers of the gold-frame report (docs/GOLD_FRAME_REPORT_<lang>.md).

Writes docs/images/gold_frame/*.png and docs/images/gold_frame/results.json, and fills the results
table of each report (between its RESULTS TABLE markers); the PDFs are then
built with ``python devtools/build_guides.py gold``.

Usage:  python devtools/gold_frame_report.py          (everything, a few minutes)
        python devtools/gold_frame_report.py tables   (only the tables in the reports, from results.json)
"""

from __future__ import annotations

import json
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
    GoldFrame, Instrument, Setup, calibrate, make_scan, sn_scan, standard_scans,
)
from quickalignment.gold_frame_plot import draw_map  # noqa: E402
from quickalignment.stage import N_HAT, T_HAT, StageConfig  # noqa: E402

OUT = HERE / "docs" / "images" / "gold_frame"
H = 0.05  # gold top above the riser top
# perfect: frame at the plate centre, SRn axis through it, SRz axis in the gold surface through it
PERFECT = StageConfig(st0=-0.95, sz0=40.63, sn_f=-0.525, srn_axis_u=0.0, srn_axis_v=0.0,
                      srz_offset_t=0.0, srz_offset_n=-H)
# the newest configuration (2026-10-24 23:55, capillary): SRz axis 2.59 mm behind the riser top
REAL = replace(PERFECT, srn_axis_u=-0.26, srn_axis_v=-0.05, srz_offset_t=-0.23, srz_offset_n=2.59)
WIDE = dict(analyzer_fwhm_h=50.0, analyzer_fwhm_v=50.0, analyzer_fwhm_axial=50.0)
TITLES = {"step1": "1  ST x SZ  (SRn 120, SRz 0)", "step2": "2  SZ line vs SRn  (ST at the centre)",
          "step3": "3  ST line vs SRz  (SRn 120, SZ at the centre)"}


def setup(config=PERFECT, frame=None, **inst) -> Setup:
    frame = frame or GoldFrame(height=H)
    nominal = Setup(config, GoldFrame(height=H))
    m = nominal.frame_motors()
    return Setup(config, frame, Instrument(**{"counts": 3000, **WIDE, **inst}, scale_st_ref=m.st, scale_sz_ref=m.sz))


def maps(truth: Setup, surface=False, step=0.02, seed=0):
    scans = standard_scans(Setup(PERFECT, GoldFrame(height=H)), step=step, surface=surface)
    rng = np.random.default_rng(seed)
    for s in scans.values():
        truth.simulate(s, rng)
    return scans


def figure(name, truth, perfect=None, surface=False, keys=("step1", "step2", "step3"), suptitle=""):
    scans = maps(truth, surface)
    perfect = perfect or Setup(PERFECT, GoldFrame(height=H))
    fig, axes = plt.subplots(1, len(keys), figsize=(5.2 * len(keys), 4.6), layout="constrained")
    for ax, key in zip(np.atleast_1d(axes), keys):
        title = TITLES[key] + ("\n(ST + SN along the surface)" if key == "step3" and surface else "")
        draw_map(ax, scans[key], {"perfect": perfect, "true": truth}, title)
    if suptitle:
        fig.suptitle(suptitle, fontsize=10)
    fig.savefig(OUT / name, dpi=110)
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


def fig_srz_curves():
    """Frame centre in ST against SRz for some SRz axis positions (perfect frame, no tilt)."""
    fig, ax = plt.subplots(1, 2, figsize=(10.4, 4.2), layout="constrained")
    srz = np.linspace(-25, 10, 71)
    for (o_t, D), colour in zip(((0.0, 0.0), (0.5, 0.0), (0.0, 1.0), (0.0, 2.6), (-0.23, 2.64)),
                                ("k", "#1f77b4", "#2ca02c", "#d62728", "#9467bd")):
        s = setup(replace(PERFECT, srz_offset_t=o_t, srz_offset_n=D - H))
        scan = make_scan("srz_st", srz, np.zeros(1), s.frame_motors())
        e = np.array([s.edges(scan, i) for i in range(len(srz))])
        centre, width = (e[:, 0] + e[:, 3]) / 2, e[:, 3] - e[:, 0]
        label = f"o_t = {o_t:+.2f}, D = {D:.2f} mm"
        ax[0].plot(srz, centre - centre[np.argmin(abs(srz))], color=colour, label=label)
        ax[1].plot(srz, width, color=colour, label=label)
    ax[0].set_xlabel("SRz (deg)")
    ax[0].set_ylabel("frame centre: ST - ST(SRz 0) (mm)")
    ax[0].set_title("centre of the frame in ST (fixed SN)", fontsize=9)
    ax[0].legend(fontsize=7)
    ax[1].set_xlabel("SRz (deg)")
    ax[1].set_ylabel("outer width in ST (mm)")
    ax[1].set_title("width in ST: 2 (cos a + sin a), a = -SRz; same for every axis", fontsize=9)
    for a in ax:
        a.grid(alpha=0.3)
    fig.savefig(OUT / "srz_curves.png", dpi=110)
    plt.close(fig)


def fig_analyzer(results):
    truth = setup(REAL, analyzer_fwhm_h=0.5, analyzer_fwhm_v=0.5, analyzer_fwhm_axial=3.0)
    plain, along = maps(truth), maps(truth, surface=True)
    fig, ax = plt.subplots(1, 3, figsize=(15.6, 4.6), layout="constrained")
    draw_map(ax[0], plain["step3"], {"true": truth}, "3  plain ST line (SN fixed), analyzer FWHM 0.5 mm")
    y = truth.spot_y(plain["step3"])
    x = plain["step3"]
    im = ax[1].imshow(y, origin="lower", aspect="auto", cmap="RdBu_r", vmin=-1.5, vmax=1.5,
                      extent=[x.x[0], x.x[-1], x.y[0], x.y[-1]])
    ax[1].invert_yaxis()
    ax[1].set_xlabel("SRz (deg)")
    ax[1].set_ylabel("ST (mm)")
    ax[1].set_title("illuminated point along the beam from the analyzer focus (mm)", fontsize=9)
    fig.colorbar(im, ax=ax[1])
    draw_map(ax[2], along["step3"], {"true": truth}, "3  ST + SN along the surface, analyzer FWHM 0.5 mm")
    fig.savefig(OUT / "analyzer.png", dpi=110)
    plt.close(fig)
    results["spot_y_plain_range_mm"] = [round(float(np.nanmin(y)), 3), round(float(np.nanmax(y)), 3)]
    results["spot_y_surface_range_mm"] = [round(float(v), 3) for v in
                                          (np.nanmin(truth.spot_y(along["step3"])), np.nanmax(truth.spot_y(along["step3"])))]


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


def run_cases(results):
    """Fit simulated measurements of known faults; how close the constants and the predictions come."""
    cases = [
        ("perfect frame, real axes", setup(REAL), False, True),
        ("frame shifted (0.3, -0.2) mm, turned 3 deg", setup(REAL, GoldFrame(height=H, u=0.3, v=-0.2, rotation=3.0)),
         False, True),
        ("ST scale 1.02, SZ scale 0.99", setup(REAL, st_scale=1.02, sz_scale=0.99), False, True),
        ("gold face tilted 2 deg about v, tilt not fitted", setup(REAL, GoldFrame(height=H, tilt_u=2.0)), True, False),
        ("gold face tilted 2 deg about v, tilt fitted", setup(REAL, GoldFrame(height=H, tilt_u=2.0)), True, True),
        ("analyzer FWHM 0.5 mm, plain ST lines", setup(REAL, analyzer_fwhm_h=0.5, analyzer_fwhm_v=0.5,
                                                       analyzer_fwhm_axial=3.0), False, True),
        ("analyzer FWHM 0.5 mm, ST + SN along the surface", setup(REAL, analyzer_fwhm_h=0.5, analyzer_fwhm_v=0.5,
                                                                  analyzer_fwhm_axial=3.0), True, True),
        ("beam 0.1 mm beside the analyzer focus (SN_gold from an SN scan)",
         setup(REAL, beam_x=0.1, analyzer_fwhm_h=0.3, analyzer_fwhm_v=0.3, analyzer_fwhm_axial=3.0), True, True),
    ]
    rows = []
    for label, truth, surface, free_tilt in cases:
        scans = maps(truth, surface)
        sn_gold = truth.frame_motors().sn
        if truth.instrument.beam_x:
            sn = np.linspace(sn_gold - 0.6, sn_gold + 0.6, 601)
            probe = replace(truth, instrument=replace(truth.instrument, counts=0, rays=1, fly=1))
            sn_gold = float(sn[np.argmax(sn_scan(probe, sn))])
        res = calibrate(scans["step1"], sn_gold, GoldFrame(height=H), scans["step2"], scans["step3"],
                        free_tilt=free_tilt)
        c = res.setup.config
        # what the fitted constants should be: the frame shift is absorbed by ST0 / SZ0 and the axes
        du, dv = truth.frame.u, truth.frame.v
        expect = replace(truth.config, st0=truth.config.st0 - du, sz0=truth.config.sz0 - dv,
                         srn_axis_u=truth.config.srn_axis_u - du, srn_axis_v=truth.config.srn_axis_v - dv,
                         srz_offset_t=truth.config.srz_offset_t - du)
        row = {"case": label, "surface": surface, "free_tilt": free_tilt,
               "lines_step3": f"{res.step3.used_lines}/{len(scans['step3'].x)}",
               "error": {k: round(float(getattr(c, k) - getattr(expect, k)), 4) for k in
                         ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")},
               "sigma_srz": [round(res.step3.sigma["srz_offset_t"], 4), round(res.step3.sigma["srz_offset_n"], 4)],
               "step1": {k: round(v, 4) for k, v in res.step1.values.items()},
               "test_point": miss_at_test_point(res.setup, truth),
               "notes": res.notes + res.step3.notes}
        if free_tilt:
            row["tilt_fitted"] = round(res.step3.values.get("frame.tilt_u", 0.0), 3)
        rows.append(row)
        print(label, row["error"], row["test_point"])
    results["cases"] = rows


CASE_NAMES = {
    "en": ["perfect frame", "frame shifted (0.3, −0.2) mm, turned 3°", "ST scale 1.02, SZ scale 0.99",
           "face tilted 2° about v, tilt not fitted", "face tilted 2° about v, tilt fitted",
           "analyzer 0.5 mm, plain ST lines", "analyzer 0.5 mm, ST + SN along the surface",
           "beam 0.1 mm beside the analyzer focus"],
    "zh": ["完美金框", "金框偏移 (0.3, −0.2) mm、面内转 3°", "ST 比例 1.02、SZ 比例 0.99", "金面绕 v 倾斜 2°，不拟合倾斜",
           "金面绕 v 倾斜 2°，拟合倾斜", "分析器 0.5 mm，普通 ST 线扫", "分析器 0.5 mm，ST + SN 沿表面扫",
           "光束偏离分析器焦点 0.1 mm"],
    "fr": ["cadre parfait", "cadre décalé (0,3 ; −0,2) mm, tourné de 3°", "échelle ST 1,02, SZ 0,99",
           "face inclinée de 2° autour de v, inclinaison non ajustée",
           "face inclinée de 2° autour de v, inclinaison ajustée", "analyseur 0,5 mm, lignes ST simples",
           "analyseur 0,5 mm, ST + SN le long de la surface", "faisceau à 0,1 mm du foyer de l'analyseur"],
}
TABLE_HEAD = {
    "en": ("Errors in µm (fitted − true).",
           "| case | map 3 lines | ST0 | SZ0 | SN_f | SRn axis u, v | SRz offset ST, SN (± σ) | test point: plate / beam |"),
    "zh": ("误差单位 µm（拟合值 − 真值）。",
           "| 情形 | 第 3 图可用线数 | ST0 | SZ0 | SN_f | SRn 轴 u, v | SRz 偏移 ST, SN (± σ) | 测试点：样品板 / 沿光束 |"),
    "fr": ("Écarts en µm (ajusté − vrai).",
           "| cas | lignes carte 3 | ST0 | SZ0 | SN_f | axe SRn u, v | décalage SRz ST, SN (± σ) | point test : plaque / faisceau |"),
}


def fill_tables(results):
    """The results table of each report, between its <!-- RESULTS TABLE --> markers."""
    def um(x):
        v = int(round(x * 1000))
        return "0" if v == 0 else f"{v:+d}"

    for lang, (unit, head) in TABLE_HEAD.items():
        rows = [head, "|" + "---|" * 8]
        for name, c in zip(CASE_NAMES[lang], results["cases"]):
            e, s, t = c["error"], c["sigma_srz"], c["test_point"]
            rows.append("| " + " | ".join([
                name, c["lines_step3"], um(e["st0"]), um(e["sz0"]), um(e["sn_f"]),
                f"{um(e['srn_axis_u'])}, {um(e['srn_axis_v'])}",
                f"{um(e['srz_offset_t'])} ± {s[0] * 1000:.0f}, {um(e['srz_offset_n'])} ± {s[1] * 1000:.0f}",
                f"{t['plate_mm'] * 1000:.0f} / {um(t['along_beam_mm'])}"]) + " |")
        path = HERE / "docs" / f"GOLD_FRAME_REPORT_{lang}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        start, end = "<!-- RESULTS TABLE -->", "<!-- /RESULTS TABLE -->"
        a, b = text.index(start) + len(start), text.index(end)
        path.write_text(text[:a] + "\n" + unit + "\n\n" + "\n".join(rows) + "\n" + text[b:], encoding="utf-8")


def main():
    if sys.argv[1:] == ["tables"]:  # only the tables, from the saved results
        fill_tables(json.loads((OUT / "results.json").read_text(encoding="utf-8")))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    results = {"perfect": {k: getattr(PERFECT, k) for k in ("st0", "sz0", "sn_f")}, "height": H}
    fig_geometry()
    fig_srz_curves()
    figure("perfect.png", setup(PERFECT), suptitle="Perfect: frame at the plate centre, SRn axis through it, "
           "SRz axis in its surface (analyzer accepts everything)")
    figure("frame_offset.png", setup(PERFECT, GoldFrame(height=H, u=0.3, v=-0.2)),
           suptitle="Frame 0.3 mm off along +u (right, seen from the analyzer) and 0.2 mm down; axes at the plate centre")
    figure("srn_axis.png", setup(replace(PERFECT, srn_axis_u=0.4, srn_axis_v=0.3)), keys=("step1", "step2"),
           suptitle="SRn axis 0.4 mm right of and 0.3 mm above the frame centre")
    figure("srz_axis.png", setup(replace(PERFECT, srz_offset_t=0.5, srz_offset_n=1.0 - H)), keys=("step1", "step3"),
           suptitle="SRz axis 0.5 mm along +ST and 1.0 mm behind the gold surface")
    figure("real_axes.png", setup(REAL), suptitle="Axes of the newest configuration (SRn axis (-0.26, -0.05), "
           "SRz axis 2.59 mm behind the riser top, -0.23 mm along ST)")
    figure("rotation_tilt.png", setup(PERFECT, GoldFrame(height=H, rotation=3.0, tilt_u=2.0)),
           suptitle="Frame turned 3 deg in plane and its face tilted 2 deg about v")
    fig_analyzer(results)
    fig_sn_scan(results)
    run_cases(results)
    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    fill_tables(results)
    print(OUT / "results.json")


if __name__ == "__main__":
    main()
