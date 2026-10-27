"""GoldFrameCalibration: simulate, fit and save a configuration from the gold-frame maps.

    python GoldFrameCalibration.py                      interactive simulator (sliders)
    python GoldFrameCalibration.py simulate [options]   the three maps for given imperfections (PNG + .nxs / .npz)
    python GoldFrameCalibration.py fit --step1 F [--step2 F ...] [--step3 F ...] [--save]

Measured maps: ANTARES .nxs (one 2-D map, or several 1-D lines, one per angle), or .npz written
by `simulate`. See docs/GOLD_FRAME_REPORT_*.md for the method.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .calibration import CalibrationStore
from .gold_frame import GoldFrame, Instrument, Scan, Setup, calibrate, record_for, standard_scans
from .stage import OPTIC_TYPES, MotorPositions, OpticsCalibration, StageConfig

FRAME_ARGS = ("u", "v", "rotation", "tilt_u", "tilt_v", "height")
CONFIG_ARGS = ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")
INSTRUMENT_ARGS = ("st_scale", "sz_scale", "analyzer_fwhm_h", "analyzer_fwhm_v", "analyzer_fwhm_axial",
                   "beam_x", "beam_z", "focus_y", "beam_fwhm", "beam_na", "counts")


def base_config(store: CalibrationStore | None = None) -> StageConfig:
    """The newest configuration's stage constants (the built-in default if there is none)."""
    return (store or CalibrationStore()).latest().config


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


def load_map(paths: list[str]) -> Scan:
    """A map from one .npz / .nxs file, or from several .nxs line scans."""
    if len(paths) == 1 and paths[0].lower().endswith(".npz"):
        return Scan.load_npz(paths[0])
    from .spem_nxs import read_lines, read_scan
    if len(paths) == 1:
        return read_scan(paths[0])
    return read_lines(paths)


def _save_scan(scan: Scan, stem: Path, optic: float | None = None) -> Path:
    try:
        from .spem_nxs import write_scan
        path = stem.with_suffix(".nxs")
        write_scan(path, scan, optic_position=optic)
    except ImportError:  # no h5py
        path = stem.with_suffix(".npz")
        scan.save(path)
    return path


# -- simulate --------------------------------------------------------------------------------------------
def cmd_simulate(args) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .gold_frame_plot import draw_steps

    config = base_config()
    truth = true_setup(args, config)
    nominal = nominal_setup(config, truth.frame.height)
    scans = standard_scans(nominal, step=args.step, surface=args.surface)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    for key, scan in scans.items():
        truth.simulate(scan, rng)
        print(f"{key}: {_save_scan(scan, out / key)}")
    fig = plt.figure(figsize=(15, 4.8), layout="constrained")
    draw_steps(fig, scans, {"perfect": nominal, "true": truth},
               {"step1": "1  ST x SZ (SRn 120, SRz 0)", "step2": "2  SZ line vs SRn",
                "step3": "3  ST line vs SRz" + (" (along the surface)" if args.surface else "")})
    fig.savefig(out / "maps.png", dpi=130)
    (out / "truth.json").write_text(json.dumps({"config": asdict(truth.config), "frame": asdict(truth.frame),
                                                "instrument": asdict(truth.instrument),
                                                "sn_gold": truth.frame_motors().sn}, indent=2), encoding="utf-8")
    print(f"figure: {out / 'maps.png'}; true values: {out / 'truth.json'}")
    return 0


# -- fit ------------------------------------------------------------------------------------------------------
def cmd_fit(args) -> int:
    store = CalibrationStore(args.configs) if args.configs else CalibrationStore()
    step1 = load_map(args.step1)
    step2 = load_map(args.step2) if args.step2 else None
    step3 = load_map(args.step3) if args.step3 else None
    sn_gold = args.sn_gold if args.sn_gold is not None else float(step1.base["sn"][0])
    frame = GoldFrame(outer=args.outer, inner=args.inner, height=args.height, u=args.frame_u, v=args.frame_v)
    newest = store.latest(args.optic)
    res = calibrate(step1, sn_gold, frame, step2, step3, base=newest.config, free_tilt=not args.no_tilt)
    c = res.setup.config
    print("Gold frame calibration")
    print(f"  step 1: frame centre ST {res.step1.values['st_c']:.4f}, SZ {res.step1.values['sz_c']:.4f}; "
          f"rotation {res.step1.values['rotation']:.2f} deg, scales ST {res.step1.values['scale_st']:.4f} / "
          f"SZ {res.step1.values['scale_sz']:.4f}, shear {res.step1.values['shear']:.2f} deg, rms {res.step1.rms * 1000:.1f} um")
    for name, r in (("step 2", res.step2), ("step 3", res.step3)):
        if r is None:
            print(f"  {name}: not measured (kept from {newest.label})")
            continue
        vals = ", ".join(f"{k} {v:.4f} +- {r.sigma[k]:.4f}" for k, v in r.values.items())
        print(f"  {name}: {vals}; rms {r.rms * 1000:.1f} um, {r.used_lines} lines")
        for note in r.notes:
            print(f"    {note}")
    for note in res.notes:
        print(f"  ! {note}")
    print("  configuration: " + ", ".join(f"{k} {getattr(c, k):.4f}" for k in CONFIG_ARGS))
    old = newest.config
    print("  change from " + newest.label + ": "
          + ", ".join(f"{k} {getattr(c, k) - getattr(old, k):+.4f}" for k in CONFIG_ARGS))

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from .gold_frame_plot import draw_steps
        scans = {k: s for k, s in (("step1", step1), ("step2", step2), ("step3", step3)) if s is not None}
        fig = plt.figure(figsize=(5 * len(scans), 4.8), layout="constrained")
        draw_steps(fig, scans, {"fit": res.setup})
        fig.savefig(args.plot, dpi=130)
        print(f"  figure: {args.plot}")

    if args.save:
        optic_type = "capillary" if args.optic == "capillary" else OPTIC_TYPES[0]
        optic_pos = args.optic_position if args.optic_position is not None else step1.info.get("optic_position")
        if optic_pos is not None:
            m = MotorPositions(st=res.step1.values["st_c"], sn=float(step1.base["sn"][0]), sz=res.step1.values["sz_c"],
                               srn=c.srn_ref, srz=0.0, pix=c.pi_center, piy=c.pi_center)
            optics = OpticsCalibration(enabled=True, motors=m, surface_w=res.setup.gold_w(), optic_position=float(optic_pos),
                                       optic_sign=1, optic_type=optic_type)
            optic_note = f"optic {optic_pos:.3f} at the gold frame centre"
        else:
            optics = replace(newest.optics, optic_type=optic_type)
            optic_note = f"optic reference kept from {newest.label}"
        sources = {k: [str(p) for p in v] for k, v in (("step1", args.step1), ("step2", args.step2),
                                                       ("step3", args.step3)) if v}
        comment = args.comment or f"Gold frame calibration (SPEM maps), SN gold {sn_gold:.4f}; {optic_note}."
        saved = store.save(record_for(res, optics, comment, sources))
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
    from .gold_frame_plot import draw_map

    config = base_config()
    nominal = nominal_setup(config)
    m = nominal.frame_motors()
    state = {"setup": Setup(config, GoldFrame(), Instrument(rays=1, fly=1, scale_st_ref=m.st, scale_sz_ref=m.sz)),
             "surface": False}
    fig = plt.figure(figsize=(15, 9))
    fig.canvas.manager.set_window_title("Gold frame SPEM simulator")
    map_axes = [fig.add_axes([0.05 + 0.32 * k, 0.47, 0.26, 0.47]) for k in range(3)]
    sliders = []
    for k, (target, name, label, lo, hi, init) in enumerate(SLIDERS):
        col, row = k % 3, k // 3
        ax = fig.add_axes([0.12 + 0.32 * col, 0.36 - 0.055 * row, 0.17, 0.025])
        value = getattr(config, name) if init is None else init
        sliders.append((target, name, Slider(ax, label, lo, hi, valinit=value)))
    check = CheckButtons(fig.add_axes([0.70, 0.02, 0.2, 0.06]), ["step 3 along the surface (ST + SN)"], [False])
    titles = ("1  ST x SZ (SRn 120, SRz 0)", "2  SZ line vs SRn", "3  ST line vs SRz")

    def redraw(_=None):
        s = state["setup"]
        values = {"frame": {}, "config": {}, "instrument": {}}
        for target, name, slider in sliders:
            values[target][name] = float(slider.val)
        s = Setup(replace(s.config, **values["config"]), replace(s.frame, **values["frame"]),
                  replace(s.instrument, **values["instrument"]))
        state["setup"] = s
        perfect = replace(nominal, frame=replace(nominal.frame, height=s.frame.height))
        scans = standard_scans(perfect, step=0.04, angle_step=4.0, surface=state["surface"])
        for ax, (key, scan), title in zip(map_axes, scans.items(), titles):
            s.simulate(scan)
            ax.clear()
            draw_map(ax, scan, {"perfect": perfect}, title)
        fig.canvas.draw_idle()

    def toggle(_):
        state["surface"] = not state["surface"]
        redraw()

    for _, _, slider in sliders:
        slider.on_changed(redraw)
    check.on_clicked(toggle)
    fig.text(0.05, 0.02, "Dashed magenta: edges of the perfect frame on the nominal configuration (the newest in configs/). "
             "Axes reversed as ANTARES draws them: up = +v (map 1, 2) or +u (map 3), right = +u (map 1).", fontsize=8)
    redraw()
    plt.show()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="GoldFrameCalibration", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("gui", help="interactive simulator (default)")

    sim = sub.add_parser("simulate", help="simulate the three maps for given imperfections")
    for k in FRAME_ARGS:
        sim.add_argument(f"--frame-{k.replace('_', '-')}", dest=f"frame_{k}", type=float,
                         default=GoldFrame.__dataclass_fields__[k].default)
    for k in CONFIG_ARGS:
        sim.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float, default=None,
                         help="true value (default: the newest configuration)")
    for k in INSTRUMENT_ARGS:
        sim.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float, default=Instrument.__dataclass_fields__[k].default)
    sim.add_argument("--surface", action="store_true", help="step 3 along the turned surface (ST + SN)")
    sim.add_argument("--step", type=float, default=0.02, help="pixel size (mm)")
    sim.add_argument("--seed", type=int, default=0)
    sim.add_argument("--out", default="gold_frame_simulation")

    fit = sub.add_parser("fit", help="fit measured maps, print (and save) the configuration")
    fit.add_argument("--step1", nargs="+", required=True, help="ST x SZ map (.nxs or .npz)")
    fit.add_argument("--step2", nargs="+", help="SZ x SRn map, or one SZ line per SRn (.nxs)")
    fit.add_argument("--step3", nargs="+", help="ST x SRz map, or one ST line per SRz (.nxs)")
    fit.add_argument("--sn-gold", type=float, default=None,
                     help="SN putting the gold top in the analyzer focus (default: the SN of the step-1 map)")
    fit.add_argument("--height", type=float, default=0.05, help="gold top above the riser top (mm)")
    fit.add_argument("--outer", type=float, default=2.0)
    fit.add_argument("--inner", type=float, default=1.0)
    fit.add_argument("--frame-u", type=float, default=0.0, help="where the frame is taken to be on the plate (mm)")
    fit.add_argument("--frame-v", type=float, default=0.0)
    fit.add_argument("--no-tilt", action="store_true", help="do not fit the tilt of the gold face about v")
    fit.add_argument("--optic", choices=("capillary", "zone_plate"), default="capillary")
    fit.add_argument("--optic-position", type=float, default=None,
                     help="optic position focused on the gold (default: the zone plate channel of step 1, else kept)")
    fit.add_argument("--configs", default=None, help="configuration folder (default: configs/)")
    fit.add_argument("--plot", default=None, help="write the maps with the fitted edges to this PNG")
    fit.add_argument("--comment", default=None)
    fit.add_argument("--save", action="store_true", help="save as a new configuration in configs/")

    args = p.parse_args(argv)
    if args.command == "simulate":
        return cmd_simulate(args)
    if args.command == "fit":
        return cmd_fit(args)
    return cmd_gui(args)


if __name__ == "__main__":
    sys.exit(main())
