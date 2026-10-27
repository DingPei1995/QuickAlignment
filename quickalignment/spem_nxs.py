"""Read ANTARES SPEM scans (.nxs) as gold-frame maps: total intensity against the scanned motors.

Layout (from a real SZ x SRn scan, ``Cp_2023-05-28_22-08-47.nxs``, h5info):

    /<entry>/scan_data/actuator_1_1      readback of the inner (fast) axis, one per point: (n2, n1)
    /<entry>/scan_data/actuator_2_1      readback of the outer axis, one per line: (n2,)
    /<entry>/scan_data/trajectory_1_1    nominal inner positions (n1,)
    /<entry>/scan_data/trajectory_2_1    nominal outer positions (n2,)
    /<entry>/scan_data/data_NN           sensors; which is which is told by their ``long_name``
                                         attribute, not by NN (``.../heason/total_int`` = vsum(mbsProj),
                                         ``.../mbs/image32``, ``.../dtc_diode.1/value``, ``.../zp-mt_zs/position``)
    /<entry>/ANTARES/i12-m-cx1-ex-sample-mt_<st|sn|sz|srn|srz>/position   motors not scanned

Datasets are in HDF5 (C) order: (outer, inner[, ...]) -- MATLAB's h5info shows them reversed.
Actuators carry ``long_name`` (the Tango attribute, e.g. ``i12-m-cx1/ex/sample-mt_srn/position``)
and ``axis`` (1 inner, 2 outer); several actuators may share an axis (actuator_1_2, ...).

Every line of the map becomes a straight path in motor space: each scanned motor's readback is
fitted against the nominal inner position (taking up a fly-scan lag or a zig-zag line), the
outer-axis motors are their readback for that line, the others their recorded position.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from .gold_frame import MOTORS, Scan
from .stage import MotorPositions

SAMPLE_GROUP = "i12-m-cx1-ex-sample-mt_{}"
INTENSITY_CHANNELS = ("total_int", "image32", "xproj")  # preferred first
DIODE = "diode"
OPTIC_CHANNEL = "zp-mt_zs"


def _h5py():
    try:
        import h5py
    except ImportError:
        raise ImportError("reading .nxs files needs h5py (pip install h5py)") from None
    return h5py


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.ndarray):
        return _text(value.reshape(-1)[0]) if value.size else ""
    return str(value)


def stage_of(name: str) -> str | None:
    """Sample stage of a Tango name: ``i12-m-cx1/ex/sample-mt_srn/position`` -> ``srn``, ``.../pi/x`` -> ``pix``."""
    tokens = [t for t in re.split(r"[/_\-. ]+", str(name or "").strip().lower()) if t]
    while tokens and tokens[-1] in ("position", "value", "pos"):
        tokens.pop()
    if not tokens:
        return None
    if tokens[-1] in ("st", "sn", "sz", "srn", "srz", "pix", "piy"):
        return tokens[-1]
    if tokens[-1] in ("x", "y") and len(tokens) > 1 and tokens[-2] == "pi":
        return "pi" + tokens[-1]
    return None


def entries(path) -> list[str]:
    """Top-level entries holding a scan_data group."""
    h5py = _h5py()
    with h5py.File(path, "r") as f:
        return [k for k in f.keys() if isinstance(f[k], h5py.Group) and "scan_data" in f[k]]


def _datasets(f, entry):
    """{dataset name: (long_name, axis attribute, dataset)} in scan_data."""
    sd = f[f"{entry}/scan_data"]
    out = {}
    for name, ds in sd.items():
        if not hasattr(ds, "shape"):
            continue
        out[name] = (_text(ds.attrs.get("long_name", name)), _text(ds.attrs.get("axis", "")), ds)
    return out


def _fixed_motors(f, entry) -> dict:
    out = {}
    for m in ("st", "sn", "sz", "srn", "srz"):
        path = f"{entry}/ANTARES/{SAMPLE_GROUP.format(m)}/position"
        if path in f:
            out[m] = float(np.asarray(f[path][()]).reshape(-1)[0])
    for m, name in (("pix", "PI_X"), ("piy", "PI_Y")):
        path = f"{entry}/ANTARES/PI/{name}"
        if path in f:
            out[m] = float(np.asarray(f[path][()]).reshape(-1)[0])
    return out


def _intensity(dsets, shape, channel: str | None):
    """(values with the spatial shape, long_name used) from the chosen or the best channel."""
    wanted = [channel] if channel else list(INTENSITY_CHANNELS)
    for key in wanted:
        for name, (long_name, _, ds) in sorted(dsets.items()):
            if key != name and key not in long_name:
                continue
            if name.startswith(("actuator", "trajectory")):
                continue
            dshape = tuple(ds.shape)
            if len(shape) == 1 and len(dshape) >= 2 and dshape[0] == 1:  # a line stored as one row
                dshape = dshape[1:]
                if dshape[:1] == tuple(shape):
                    return np.asarray(ds[()], float).reshape(dshape[0], -1).sum(axis=1), long_name
            if dshape[:len(shape)] != tuple(shape):
                continue
            if len(ds.shape) == len(shape):
                return np.asarray(ds[()], float), long_name
            # a spectrum / image per point: summed, one outer line at a time (image32 can be GBs)
            if len(shape) == 2:
                axes = tuple(range(1, len(ds.shape) - 1))
                return np.array([np.asarray(ds[i], float).sum(axis=axes) for i in range(shape[0])]), long_name
            return np.asarray(ds[()], float).reshape(shape[0], -1).sum(axis=1), long_name
    raise KeyError(f"no intensity channel {wanted} with the scan's shape {shape}; "
                   f"datasets: {', '.join(f'{n} ({v[0]})' for n, v in sorted(dsets.items()))}")


def read_scan(path, entry: str | None = None, channel: str | None = None, normalize: bool = False) -> Scan:
    """One 2-D map (or a single line) as a Scan: x = outer axis, y = inner (fast) axis, nominal positions.

    channel: a dataset name or part of its long_name (default: total_int, else image32 / xproj
    summed); normalize: divide by the diode current of every point.
    """
    h5py = _h5py()
    with h5py.File(path, "r") as f:
        entry = entry or next((k for k in f.keys() if isinstance(f[k], h5py.Group) and "scan_data" in f[k]), None)
        if entry is None:
            raise KeyError(f"{Path(path).name}: no entry with scan_data")
        dsets = _datasets(f, entry)
        axes = {1: [], 2: []}
        for name, (long_name, axis, ds) in sorted(dsets.items()):
            if name.startswith("actuator_") and axis in ("1", "2"):
                axes[int(axis)].append((stage_of(long_name), long_name, np.asarray(ds[()], float)))
        if not axes[1]:
            raise KeyError(f"{Path(path).name}: no scanned actuator (scan_data/actuator_* with axis = 1)")
        traj = {k: np.asarray(dsets[f"trajectory_{k}_1"][2][()], float).reshape(-1)
                for k in (1, 2) if f"trajectory_{k}_1" in dsets}
        n1 = len(traj[1]) if 1 in traj else axes[1][0][2].shape[-1]
        y = traj[1] if 1 in traj else np.asarray(axes[1][0][2], float).reshape(-1, n1)[0]
        two_d = bool(axes[2])
        n2 = (len(traj[2]) if 2 in traj else len(axes[2][0][2])) if two_d else 1
        shape = (n2, n1) if two_d else (n1,)
        values, used = _intensity(dsets, shape, channel)
        info = {"file": str(path), "entry": entry, "channel": used,
                "inner": [a[1] for a in axes[1]], "outer": [a[1] for a in axes[2]]}
        if normalize:
            diode = next(((ds, ln) for _, (ln, _, ds) in sorted(dsets.items()) if DIODE in ln and ds.shape == shape), None)
            if diode is None:
                raise KeyError("no diode channel to normalize by")
            values = values / np.where(np.abs(diode[0][()]) > 0, diode[0][()], np.nan)
            info["normalized_by"] = diode[1]
        optic = next((np.asarray(ds[()], float) for _, (ln, _, ds) in dsets.items() if OPTIC_CHANNEL in ln), None)
        if optic is not None and np.isfinite(optic).any():
            info["optic_position"] = float(np.nanmean(optic))
        fixed = _fixed_motors(f, entry)
    values = values.reshape(n2, n1)
    outer = (traj[2] if 2 in traj else np.asarray(axes[2][0][2], float)) if two_d else np.zeros(1)
    if two_d and axes[2][0][2].size == n2:  # the outer readback is better than the nominal value
        outer = np.where(np.isfinite(axes[2][0][2]), axes[2][0][2], outer)

    defaults = MotorPositions()
    base = {m: np.full(n2, fixed.get(m, getattr(defaults, m))) for m in MOTORS}
    slope = {m: np.zeros(n2) for m in MOTORS}
    for stage, _, rb in axes[2]:
        if stage:
            base[stage] = np.asarray(rb, float).reshape(n2)
    for stage, _, rb in axes[1]:
        if not stage:
            continue
        rb = np.asarray(rb, float).reshape(n2, n1)
        for i in range(n2):
            ok = np.isfinite(rb[i])
            if ok.sum() >= 2 and np.ptp(rb[i][ok]) > 0:
                slope[stage][i], base[stage][i] = np.polyfit(y[ok], rb[i][ok], 1)
            else:  # no usable readback: the nominal positions
                slope[stage][i], base[stage][i] = 1.0, 0.0
    stages = ([a[0] for a in axes[2]][:1] or [None]) + [a[0] for a in axes[1]]
    info["kind_from"] = stages
    scan = Scan(_kind(stages), outer, y, base, slope, values.T, info)
    return scan


def _kind(stages) -> str:
    outer, inner = stages[0], set(stages[1:])
    if outer == "srn":
        return "srn_sz"
    if outer == "srz":
        return "srz_surface" if {"st", "sn"} <= inner else "srz_st"
    return "st_sz"


def read_lines(paths, channel: str | None = None, normalize: bool = False, angle: str | None = None) -> Scan:
    """Several 1-D line scans, one per angle (the SRn or SRz of each file), as one map on the y grid
    of the first; `angle`: "srn" or "srz" (default: the one that changes between the files)."""
    lines = [read_scan(p, channel=channel, normalize=normalize) for p in paths]
    if not lines:
        raise ValueError("no files")
    if angle is None:
        spread = {a: np.ptp([s.base[a][0] for s in lines]) for a in ("srn", "srz")}
        angle = max(spread, key=spread.get)
    lines.sort(key=lambda s: s.base[angle][0])
    y = lines[0].y
    x = np.array([s.base[angle][0] for s in lines])
    base = {m: np.array([s.base[m][0] for s in lines]) for m in MOTORS}
    slope = {m: np.array([s.slope[m][0] for s in lines]) for m in MOTORS}
    # each line on the first line's nominal grid, through its own scanned motor
    inner = next(m for m in MOTORS if lines[0].slope[m][0] != 0)
    cols = []
    for s in lines:
        pos = s.base[inner][0] + s.y * s.slope[inner][0]
        want = base[inner][0] + y * slope[inner][0]
        order = np.argsort(pos)
        cols.append(np.interp(want, pos[order], s.intensity[order, 0]))
    for m in MOTORS:  # all lines now share the first line's scanned path, at their own fixed motors
        if m == inner:
            base[m][:], slope[m][:] = base[m][0], slope[m][0]
    kind = "srn_sz" if angle == "srn" else ("srz_surface" if lines[0].slope["sn"][0] else "srz_st")
    return Scan(kind, x, y, base, slope, np.column_stack(cols), {"files": [str(p) for p in paths], "angle": angle})


__all__ = ["read_scan", "read_lines", "entries", "stage_of"]


TANGO = {"st": "i12-m-cx1/ex/sample-mt_st/position", "sn": "i12-m-cx1/ex/sample-mt_sn/position",
         "sz": "i12-m-cx1/ex/sample-mt_sz/position", "srn": "i12-m-cx1/ex/sample-mt_srn/position",
         "srz": "i12-m-cx1/ex/sample-mt_srz/position", "pix": "i12-m-cx1/ex/pi/x", "piy": "i12-m-cx1/ex/pi/y"}


def write_scan(path, scan: Scan, entry: str = "img1_0001", optic_position: float | None = None) -> None:
    """Write a map in the ANTARES layout read by `read_scan` (inner axis = the map's y, outer = x):
    simulated maps can then go through exactly the path of measured ones."""
    h5py = _h5py()
    n2, n1 = len(scan.x), len(scan.y)
    moving_inner = [m for m in MOTORS if np.any(scan.slope[m] != 0)]
    moving_outer = [m for m in MOTORS if m not in moving_inner and np.ptp(scan.base[m]) > 0]
    with h5py.File(path, "w") as f:
        g = f.create_group(entry)
        g.attrs["NX_class"] = "NXentry"
        sd = g.create_group("scan_data")

        def put(name, data, long_name, axis=None):
            ds = sd.create_dataset(name, data=np.asarray(data, float))
            ds.attrs["long_name"] = long_name
            if axis:
                ds.attrs["axis"] = axis

        line = not moving_outer and n2 == 1  # a single line: 1-D datasets

        def grid(values):
            return values[0] if line else values

        for k, m in enumerate(moving_inner, 1):
            put(f"actuator_1_{k}", grid(scan.base[m][:, None] + scan.y[None, :] * scan.slope[m][:, None]), TANGO[m], "1")
        put("trajectory_1_1", scan.y, TANGO[moving_inner[0]] if moving_inner else "inner")
        for k, m in enumerate(moving_outer, 1):
            put(f"actuator_2_{k}", scan.base[m], TANGO[m], "2")
        if moving_outer:
            put("trajectory_2_1", scan.x, TANGO[moving_outer[0]])
        put("data_03", grid(scan.intensity.T), "i12-m-cx1/ex/heason/total_int")
        put("data_12", grid(np.full((n2, n1), 1e-9)), "i12-m-c08/dt/dtc_diode.1/value")
        if optic_position is not None:
            put("data_13", grid(np.full((n2, n1), optic_position)), "i12-m-cx1/op/zp-mt_zs/position")
        for m in ("st", "sn", "sz", "srn", "srz"):
            grp = g.create_group(f"ANTARES/{SAMPLE_GROUP.format(m)}")
            grp["position"] = [float(scan.base[m][0])]
            grp["offset"] = [0.0]
        pi = g.create_group("ANTARES/PI")
        pi["PI_X"], pi["PI_Y"] = [float(scan.base["pix"][0])], [float(scan.base["piy"][0])]


__all__ += ["write_scan"]
