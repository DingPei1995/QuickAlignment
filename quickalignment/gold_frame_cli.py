"""GoldFrameCalibration: plan the SZ lines over the gold frame, fit them, save a configuration; simulate them.

    python GoldFrameCalibration.py                      calibration window (plan, load, fit, save)
    python GoldFrameSimulator.py                        interactive simulator (sliders); also: ... simulator
    python GoldFrameCalibration.py plan [--csv F]       the SZ lines to measure (from the newest configuration)
    python GoldFrameCalibration.py simulate [options]   simulated measurement for given imperfections
    python GoldFrameCalibration.py fit FILE... [--sn-gold] [--sn-points CSV] [--save]

Measured data: ANTARES .nxs files (any SZ lines: the survey, an ST x SZ overview, an SZ x SRn sweep; a
file is a 2-D map or one line), or .npz written by `simulate`. Every edge of every line is fitted at
once. See docs/GOLD_FRAME_REPORT_*.md for the method.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .calibration import CalibrationStore
from .gold_frame import (
    GoldFrame, Instrument, Scan, Setup, SNPoint, fit_global, record_for, simulated_measurement, sn_point_plan,
    survey_plan,
)
from .stage import OPTIC_TYPES, OpticsCalibration, StageConfig

FRAME_ARGS = ("u", "v", "rotation", "tilt_u", "tilt_v", "height")
CONFIG_ARGS = ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")
INSTRUMENT_ARGS = ("st_scale", "sz_scale", "analyzer_fwhm_h", "analyzer_fwhm_v", "analyzer_fwhm_axial",
                   "beam_x", "beam_z", "focus_y", "beam_fwhm", "beam_na", "counts")
PLAN_FIELDS = ("group", "srn", "srz", "du", "st", "sn", "sz_from", "sz_to")
SN_FIELDS = ("srn", "srz", "st", "sz", "sn")


def base_config(store: CalibrationStore | None = None, optic: str | None = None) -> StageConfig:
    """The newest configuration's stage constants (the built-in default if there is none)."""
    return (store or CalibrationStore()).latest(optic).config


def nominal_setup(config: StageConfig, height: float = 0.05) -> Setup:
    """What the beamline expects: this configuration, a perfect frame at the plate centre."""
    return Setup(config, GoldFrame(height=height))


def true_setup(args, config: StageConfig) -> Setup:
    frame = GoldFrame(**{k: getattr(args, f"frame_{k}") for k in FRAME_ARGS})
    cfg = replace(config, **{k: getattr(args, k) for k in CONFIG_ARGS if getattr(args, k) is not None})
    nominal = nominal_setup(config, frame.height)
    m = nominal.frame_motors()  # the motor scales act around where the frame should be
    inst = Instrument(**{k: getattr(args, k) for k in INSTRUMENT_ARGS}, scale_st_ref=m.st, scale_sz_ref=m.sz)
    return Setup(cfg, frame, inst)


def load_map(paths: list[str], normalize: bool = False) -> Scan:
    """A map from one .npz / .nxs file, or from several .nxs line scans (normalize: divide by the diode)."""
    paths = [str(p) for p in paths]
    if len(paths) == 1 and paths[0].lower().endswith(".npz"):
        return Scan.load_npz(paths[0])
    from .spem_nxs import read_lines, read_scan
    if len(paths) == 1:
        return read_scan(paths[0], normalize=normalize)
    return read_lines(paths, normalize=normalize)


def save_scan(scan: Scan, stem: Path, optic: float | None = None) -> Path:
    """A scan as an ANTARES .nxs file (.npz without h5py)."""
    try:
        from .spem_nxs import write_scan
        path = stem.with_suffix(".nxs")
        write_scan(path, scan, optic_position=optic)
    except ImportError:  # no h5py
        path = stem.with_suffix(".npz")
        scan.save(path)
    return path


def write_plan_csv(path, plan, sn_points=()) -> None:
    """The plan (and the optional SN points) as CSV, numbers with a point."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(PLAN_FIELDS)
        for p in plan:
            w.writerow([p.group] + [f"{getattr(p, k):.4f}" for k in PLAN_FIELDS[1:]])
        if sn_points:
            w.writerow([])
            w.writerow(("sn_point", "srn", "srz", "st", "sz", "expected_sn"))  # not measured: not read back as points
            for p in sn_points:
                w.writerow(["SN"] + [f"{getattr(p, k):.4f}" for k in SN_FIELDS])


def read_sn_points(path) -> list[SNPoint]:
    """SN points from a CSV with the columns srn, srz, st, sz, sn (header line; numbers with a point)."""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if r and any(c.strip() for c in r)]
    start = next((k for k, r in enumerate(rows) if all(f in [c.strip().lower() for c in r] for f in SN_FIELDS)), None)
    if start is None:
        return out
    head = [c.strip().lower() for c in rows[start]]
    idx = [head.index(k) for k in SN_FIELDS]
    for r in rows[start + 1:]:
        try:
            out.append(SNPoint(*(float(r[i]) for i in idx)))
        except (ValueError, IndexError):
            continue
    return out


def optics_reference(result, scans, newest, optic: str = "capillary", optic_position: float | None = None):
    """The optic reference for the configuration: the optic position with the frame centre at the analyzer
    focus (given, else recorded in a file at SRn ref / SRz 0), else the newest configuration's."""
    optic_type = "capillary" if optic == "capillary" else OPTIC_TYPES[0]
    if optic_position is None:
        ref = result.setup.config.srn_ref
        for scan in scans:
            if scan.info.get("optic_position") is not None and np.allclose(scan.base["srn"], ref) \
                    and np.allclose(scan.base["srz"], 0):
                optic_position = scan.info["optic_position"]
                break
    if optic_position is None:
        return replace(newest.optics, optic_type=optic_type), f"optic reference kept from {newest.label}"
    m = result.setup.frame_motors()
    optics = OpticsCalibration(enabled=True, motors=m, surface_w=result.setup.gold_w(),
                               optic_position=float(optic_position), optic_sign=1, optic_type=optic_type)
    return optics, f"optic {optic_position:.3f} at the gold frame centre"


def calibration_record(result, scans, sn_gold: float, newest, optic: str = "capillary",
                       optic_position: float | None = None, comment: str | None = None, sources: dict | None = None,
                       sn_points=()):
    """The configuration to save from a global fit."""
    optics, optic_note = optics_reference(result, scans, newest, optic, optic_position)
    text = (f"Gold frame calibration (SPEM, {result.lines_used} SZ lines"
            + (f", {sum(p.use for p in sn_points)} SN points" if sn_points else "")
            + f"), SN gold {sn_gold:.4f}; {optic_note}.")
    return record_for(result, optics, f"{comment.strip()} -- {text}" if comment and comment.strip() else text,
                      sources, sn_points)


def result_text(result, newest) -> str:
    """The fit as plain text (console)."""
    from .gold_frame import PARAM_TEXT
    c, old = result.setup.config, newest.config
    lines = [f"Gold frame calibration: {result.lines_used}/{result.lines_total} lines, {result.edges} edges, "
             f"edge rms {result.rms * 1000:.1f} um"]
    for k in CONFIG_ARGS:
        sig = result.sigma.get(k)
        kept = "  (kept)" if k in result.kept else ""
        lines.append(f"  {k:13s} {getattr(c, k):10.4f}" + (f" +- {sig:.4f}" if sig is not None else " " * 10)
                     + f"   newest {getattr(old, k):10.4f}   change {getattr(c, k) - getattr(old, k):+.4f}{kept}")
    for k in ("frame.rotation", "frame.tilt_u", "instrument.st_scale", "instrument.sz_scale"):
        if k in result.values:
            lines.append(f"  {PARAM_TEXT[k]}: {result.values[k]:.4f} +- {result.sigma[k]:.4f}")
    for k, r in enumerate(result.sn_residuals):
        if r is not None:
            lines.append(f"  SN point {k + 1}: {r * 1000:+.1f} um from the analyzer focus")
    lines += [f"  ! {n}" for n in result.notes]
    return "\n".join(lines)


# -- plan ---------------------------------------------------------------------------------------------------
def cmd_plan(args) -> int:
    store = CalibrationStore(args.configs) if args.configs else CalibrationStore()
    newest = store.latest(args.optic)
    guide = Setup(newest.config, GoldFrame(height=args.height, u=args.frame_u, v=args.frame_v))
    plan = survey_plan(guide)
    points = sn_point_plan(guide)
    print(f"SZ lines over the gold frame, placed with {newest.label} (frame at {args.frame_u:g}, {args.frame_v:g}):")
    print("  group   SRn     SRz      ST        SN       SZ from   SZ to")
    for p in plan:
        print(f"  {p.group:5s} {p.srn:6.1f} {p.srz:7.1f} {p.st:9.4f} {p.sn:9.4f} {p.sz_from:9.4f} {p.sz_to:9.4f}")
    print("Optional SN points (SN scan, ST following, on the right bar): SRn, SRz, ST, SZ, expected SN")
    for p in points:
        print(f"  SN    {p.srn:6.1f} {p.srz:7.1f} {p.st:9.4f} {p.sn:9.4f} sz {p.sz:9.4f}")
    if args.csv:
        write_plan_csv(args.csv, plan, points)
        print(f"written: {args.csv}")
    return 0


# -- simulate --------------------------------------------------------------------------------------------
def cmd_simulate(args) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .gold_frame_plot import draw_survey

    config = base_config()
    truth = true_setup(args, config)
    nominal = nominal_setup(config, truth.frame.height)
    scans = simulated_measurement(nominal, truth, overview=not args.no_overview, srn_sweep=args.srn_sweep,
                                  step=args.step, rng=np.random.default_rng(args.seed))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for key, scan in scans.items():
        print(f"{key}: {save_scan(scan, out / key, optic=60.0)}")
    write_plan_csv(out / "plan.csv", survey_plan(nominal), sn_point_plan(nominal))
    fig = plt.figure(figsize=(16, 5.2), layout="constrained")
    draw_survey(fig, list(scans.values()), {"perfect": nominal, "true": truth})
    fig.savefig(out / "measurement.png", dpi=120)
    (out / "truth.json").write_text(json.dumps({"config": asdict(truth.config), "frame": asdict(truth.frame),
                                                "instrument": asdict(truth.instrument),
                                                "sn_gold": truth.frame_motors().sn}, indent=2), encoding="utf-8")
    print(f"figure: {out / 'measurement.png'}; plan: {out / 'plan.csv'}; true values: {out / 'truth.json'}")
    return 0


# -- fit ------------------------------------------------------------------------------------------------------
def cmd_fit(args) -> int:
    store = CalibrationStore(args.configs) if args.configs else CalibrationStore()
    scans = [load_map([f]) for f in args.files]
    newest = store.latest(args.optic)
    ref = newest.config.srn_ref
    if args.sn_gold is not None:
        sn_gold = args.sn_gold
    else:
        flat = [s for s in scans if np.allclose(s.base["srn"], ref) and np.allclose(s.base["srz"], 0)]
        sn_gold = float((flat or scans)[0].base["sn"][0])
    points = read_sn_points(args.sn_points) if args.sn_points else []
    frame = GoldFrame(outer=args.outer, inner=args.inner, height=args.height, u=args.frame_u, v=args.frame_v)
    result = fit_global(scans, sn_gold, frame, newest.config, free_tilt=not args.no_tilt,
                        free_scales=not args.no_scales, sn_points=points)
    print(result_text(result, newest))
    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from .gold_frame_plot import draw_survey
        fig = plt.figure(figsize=(16, 5.2), layout="constrained")
        draw_survey(fig, scans, {"fit": result.setup}, ref)
        fig.savefig(args.plot, dpi=120)
        print(f"  figure: {args.plot}")
    if args.save:
        record = calibration_record(result, scans, sn_gold, newest, args.optic, args.optic_position, args.comment,
                                    {"files": [str(f) for f in args.files]}, points)
        saved = store.save(record)
        print(f"  saved: {saved.path}")
    return 0


# -- interactive simulator -----------------------------------------------------------------------------------
SLIDERS = [  # (target, field, label, min, max, initial)
    ("frame", "u", "frame u (mm)", -1.0, 1.0, 0.0),
    ("frame", "v", "frame v (mm)", -1.0, 1.0, 0.0),
    ("frame", "rotation", "frame rotation (deg)", -10.0, 10.0, 0.0),
    ("frame", "tilt_u", "tilt about v (deg)", -5.0, 5.0, 0.0),
    ("frame", "tilt_v", "tilt about u (deg)", -5.0, 5.0, 0.0),
    ("frame", "height", "frame height (mm)", 0.0, 0.3, 0.05),
    ("config", "srn_axis_u", "SRn axis u (mm)", -1.5, 1.5, None),
    ("config", "srn_axis_v", "SRn axis v (mm)", -1.5, 1.5, None),
    ("config", "srz_offset_t", "SRz offset ST (mm)", -3.0, 3.0, None),
    ("config", "srz_offset_n", "SRz offset SN (mm)", -2.0, 6.0, None),
    ("instrument", "st_scale", "ST scale", 0.95, 1.05, 1.0),
    ("instrument", "analyzer_fwhm_h", "analyzer FWHM (mm)", 0.05, 5.0, 0.5),
    ("instrument", "beam_x", "beam offset x (mm)", -0.5, 0.5, 0.0),
]


def cmd_gui(args) -> int:
    import matplotlib.pyplot as plt
    from matplotlib.widgets import CheckButtons, Slider
    from .gold_frame_plot import draw_lines, draw_map

    config = base_config()
    nominal = nominal_setup(config)
    m = nominal.frame_motors()
    state = {"setup": Setup(config, GoldFrame(), Instrument(rays=1, fly=1, scale_st_ref=m.st, scale_sz_ref=m.sz)),
             "sweep": False}
    fig = plt.figure(figsize=(16, 9.5))
    fig.canvas.manager.set_window_title("Gold frame SPEM simulator")
    ax_overview = fig.add_axes([0.04, 0.47, 0.22, 0.45])
    ax_sweep = fig.add_axes([0.30, 0.47, 0.22, 0.45])
    ax_lines = fig.add_axes([0.56, 0.47, 0.42, 0.45])
    sliders = []
    for k, (target, name, label, lo, hi, init) in enumerate(SLIDERS):
        col, row = k % 3, k // 3
        ax = fig.add_axes([0.12 + 0.32 * col, 0.34 - 0.055 * row, 0.17, 0.025])
        value = getattr(config, name) if init is None else init
        sliders.append((target, name, Slider(ax, label, lo, hi, valinit=value)))
    check = CheckButtons(fig.add_axes([0.72, 0.02, 0.22, 0.05]), ["show the SZ × SRn sweep (optional data)"], [False])

    def redraw(_=None):
        s = state["setup"]
        values = {"frame": {}, "config": {}, "instrument": {}}
        for target, name, slider in sliders:
            values[target][name] = float(slider.val)
        s = Setup(replace(s.config, **values["config"]), replace(s.frame, **values["frame"]),
                  replace(s.instrument, **values["instrument"]))
        state["setup"] = s
        perfect = replace(nominal, frame=replace(nominal.frame, height=s.frame.height))
        scans = simulated_measurement(perfect, s, overview=True, srn_sweep=state["sweep"], step=0.04,
                                      overview_st_step=0.1)
        overlay = {"perfect": perfect}
        ax_overview.clear()
        draw_map(ax_overview, scans.pop("overview"), overlay, "overview: ST × SZ (SRn 120, SRz 0)")
        ax_sweep.clear()
        if "srn_sweep" in scans:
            draw_map(ax_sweep, scans.pop("srn_sweep"), overlay, "SZ × SRn sweep (optional)")
        else:
            ax_sweep.axis("off")
            ax_sweep.text(0.5, 0.5, "SZ × SRn sweep: optional\n(tick the box below)", ha="center", va="center")
        ax_lines.clear()
        draw_lines(ax_lines, list(scans.values()), overlay, "SZ lines of the survey (A: SRn 120, B: ±45°, C: SRz)")
        fig.canvas.draw_idle()

    def toggle(_):
        state["sweep"] = not state["sweep"]
        redraw()

    for _, _, slider in sliders:
        slider.on_changed(redraw)
    check.on_clicked(toggle)
    fig.text(0.04, 0.02, "Magenta: edges of the perfect frame on the nominal configuration (the newest in configs/); the "
             "lines are placed with it. Axes as ANTARES draws them: SZ decreasing upwards, ST decreasing to the right.",
             fontsize=8)
    redraw()
    plt.show()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="GoldFrameCalibration", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("window", help="calibration window (default)")
    sub.add_parser("simulator", aliases=["gui"], help="interactive simulator")

    def frame_args(q):
        q.add_argument("--height", type=float, default=0.05, help="gold top above the riser top (mm)")
        q.add_argument("--frame-u", type=float, default=0.0, help="where the frame is taken to be on the plate (mm)")
        q.add_argument("--frame-v", type=float, default=0.0)
        q.add_argument("--optic", choices=("capillary", "zone_plate"), default="capillary")
        q.add_argument("--configs", default=None, help="configuration folder (default: configs/)")

    plan = sub.add_parser("plan", help="the SZ lines to measure, from the newest configuration")
    frame_args(plan)
    plan.add_argument("--csv", default=None, help="write the plan to this CSV file")

    sim = sub.add_parser("simulate", help="simulate the measurement for given imperfections")
    for k in FRAME_ARGS:
        sim.add_argument(f"--frame-{k.replace('_', '-')}", dest=f"frame_{k}", type=float,
                         default=GoldFrame.__dataclass_fields__[k].default)
    for k in CONFIG_ARGS:
        sim.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float, default=None,
                         help="true value (default: the newest configuration)")
    for k in INSTRUMENT_ARGS:
        sim.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float, default=Instrument.__dataclass_fields__[k].default)
    sim.add_argument("--no-overview", action="store_true", help="without the ST x SZ overview map")
    sim.add_argument("--srn-sweep", action="store_true", help="with the SZ x SRn sweep (optional data)")
    sim.add_argument("--step", type=float, default=0.02, help="SZ step (mm)")
    sim.add_argument("--seed", type=int, default=0)
    sim.add_argument("--out", default="gold_frame_simulation")

    fit = sub.add_parser("fit", help="fit measured lines, print (and save) the configuration")
    fit.add_argument("files", nargs="+", help=".nxs / .npz files: survey lines, overview map, SRn sweep...")
    frame_args(fit)
    fit.add_argument("--sn-gold", type=float, default=None,
                     help="SN with the gold top at the analyzer focus (default: the SN of a file at SRn 120 / SRz 0)")
    fit.add_argument("--sn-points", default=None, help="CSV of optional SN points (srn, srz, st, sz, sn)")
    fit.add_argument("--outer", type=float, default=2.0)
    fit.add_argument("--inner", type=float, default=1.0)
    fit.add_argument("--no-tilt", action="store_true", help="do not fit the tilt of the gold face about v")
    fit.add_argument("--no-scales", action="store_true", help="do not fit the ST / SZ scales")
    fit.add_argument("--optic-position", type=float, default=None,
                     help="optic position focused on the gold (default: recorded in a file at SRn 120 / SRz 0)")
    fit.add_argument("--plot", default=None, help="write the data with the fitted edges to this PNG")
    fit.add_argument("--comment", default=None)
    fit.add_argument("--save", action="store_true", help="save as a new configuration in configs/")

    args = p.parse_args(argv)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "simulate":
        return cmd_simulate(args)
    if args.command == "fit":
        return cmd_fit(args)
    if args.command in ("simulator", "gui"):
        return cmd_gui(args)
    from .ui.gold_frame_window import main as window
    return window()


if __name__ == "__main__":
    sys.exit(main())
