"""Drawing gold-frame data (matplotlib): maps and SZ lines with the edges a setup predicts drawn over them.

Orientation: the scanned position axes are drawn reversed, as ANTARES draws its
coarse maps, so that up / right are +v / +u on the plate (the view from the
analyzer): ST decreases to the right, SZ decreases upwards.
"""

from __future__ import annotations

import numpy as np

from .gold_frame import KINDS, Scan, Setup

EDGE_STYLES = {  # label -> (colour, line style)
    "perfect": ("#ff3fd2", (0, (4, 3))),
    "fit": ("#e8541c", "-"),
    "true": ("#1fb4e8", "-"),
}


def edge_curves(setup: Setup, scan: Scan) -> np.ndarray:
    """(len(x), 4) predicted edges [outer in, inner in, inner out, outer out]; NaN where the line
    misses the frame (outer) or the hole (inner)."""
    out = np.array([setup.edges(scan, i) for i in range(len(scan.x))], float)
    miss_o = ~(out[:, 0] < out[:, 3])
    miss_i = ~(out[:, 1] < out[:, 2]) | miss_o
    out[miss_o] = np.nan
    out[miss_i, 1:3] = np.nan
    return out


def frame_outline(setup: Setup, scan: Scan) -> list[np.ndarray]:
    """Outer and inner square of the frame in an ST x SZ map, as closed (5, 2) polylines in (ST, SZ)."""
    i1 = len(scan.x) - 1
    F00, F01 = setup.line_in_frame(scan, 0)
    F10, _ = setup.line_in_frame(scan, i1)
    st0, st1 = scan.base["st"][0], scan.base["st"][i1]
    # F = A (st, sz) + b, with SZ = y along every line (an overview map: base 0, slope 1)
    A = np.column_stack([(F10 - F00) / (st1 - st0), F01])
    b = F00 - A[:, 0] * st0
    out = []
    for h in (setup.frame.outer / 2, setup.frame.inner / 2):
        corners = np.array([(h, h), (-h, h), (-h, -h), (h, -h), (h, h)])
        out.append(np.linalg.solve(A, (corners - b).T).T)
    return out


def draw_map(ax, scan: Scan, overlays: dict | None = None, title: str = "", cmap: str = "gray",
             reverse: bool = True, legend: bool = True):
    """Intensity of `scan` on `ax`, with the edges of each setup in `overlays` ({label: Setup})."""
    x, y = scan.x, scan.y
    dx = (x[1] - x[0]) / 2 if len(x) > 1 else 0.5
    dy = (y[1] - y[0]) / 2 if len(y) > 1 else 0.5
    img = scan.intensity
    vmax = np.nanpercentile(img, 99.5) if np.isfinite(img).any() else 1.0
    ax.imshow(img, origin="lower", aspect="auto", cmap=cmap, vmin=0, vmax=vmax,
              extent=[x[0] - dx, x[-1] + dx, y[0] - dy, y[-1] + dy], interpolation="nearest")
    for label, setup in (overlays or {}).items():
        colour, style = EDGE_STYLES.get(label, ("#ffd400", "-"))
        if is_overview(scan, setup.config.srn_ref):
            for k, line in enumerate(frame_outline(setup, scan)):
                ax.plot(line[:, 0], line[:, 1], color=colour, ls=style, lw=1.0, label=label if k == 0 else None)
            continue
        e = edge_curves(setup, scan)
        for k in range(4):
            ax.plot(x, e[:, k], color=colour, ls=style, lw=1.0 if k in (0, 3) else 0.8,
                    label=label if k == 0 else None)
    xl, yl = KINDS[scan.kind]
    ax.set_xlabel(xl)
    ax.set_ylabel(yl)
    ax.set_xlim(x[0] - dx, x[-1] + dx)
    ax.set_ylim(y[0] - dy, y[-1] + dy)
    if reverse:
        ax.invert_yaxis()  # SZ / ST decreasing upwards: up = +v / +u
        if scan.kind == "st_sz":
            ax.invert_xaxis()  # ST decreasing to the right: right = +u
    if title:
        ax.set_title(title, fontsize=9)
    if overlays and legend:
        ax.legend(loc="lower right", fontsize=7, framealpha=0.6)


def is_overview(scan: Scan, srn_ref: float = 120.0) -> bool:
    """An ST x SZ map at SRn ref / SRz 0 (drawn as an image of the frame)."""
    return (scan.kind == "st_sz" and len(scan.x) >= 5 and np.allclose(scan.base["srn"], srn_ref)
            and np.allclose(scan.base["srz"], 0) and np.allclose(scan.slope["sz"], 1, atol=1e-6)
            and np.allclose(scan.base["sz"], 0, atol=1e-4))


def _sz_columns(scans):
    """Every SZ line of the scans as (sz values, intensity, scan, line index, srn, srz, st), sorted by SRn, SRz, ST."""
    out = []
    for scan in scans:
        for i in range(len(scan.x)):
            if abs(scan.slope["sz"][i]) < 1e-6 or any(abs(scan.slope[m][i]) > 1e-6 for m in ("st", "sn", "srn", "srz")):
                continue
            sz = scan.base["sz"][i] + scan.y * scan.slope["sz"][i]
            out.append((sz, scan.intensity[:, i], scan, i, scan.base["srn"][i], scan.base["srz"][i], scan.base["st"][i]))
    out.sort(key=lambda c: (round(c[4], 3), round(c[5], 3), c[6]))
    return out


def draw_lines(ax, scans, overlays: dict | None = None, title: str = "", step: float = 0.02, cmap: str = "gray"):
    """All SZ lines of the scans side by side (one column each, grouped by SRn / SRz, ST increasing in a group),
    with the edges each setup in `overlays` predicts (short marks). SZ decreases upwards, as ANTARES draws it."""
    cols = _sz_columns(scans)
    if not cols:
        ax.axis("off")
        ax.text(0.5, 0.5, "no SZ line", ha="center", va="center")
        return
    lo = min(c[0].min() for c in cols)
    hi = max(c[0].max() for c in cols)
    grid = np.arange(lo, hi + step / 2, step)
    img = np.full((len(grid), len(cols)), np.nan)
    tops = {id(scan): (np.nanpercentile(scan.intensity, 99.5) or 1.0) for scan in scans}  # per file
    for j, (sz, value, scan, *_rest) in enumerate(cols):
        order = np.argsort(sz)
        top = tops[id(scan)]
        inside = (grid >= sz.min()) & (grid <= sz.max())
        img[inside, j] = np.interp(grid[inside], sz[order], value[order]) / top
    ax.imshow(img, origin="lower", aspect="auto", cmap=cmap, vmin=0, vmax=1.05, interpolation="nearest",
              extent=[-0.5, len(cols) - 0.5, grid[0] - step / 2, grid[-1] + step / 2])
    for label, setup in (overlays or {}).items():
        colour, _ = EDGE_STYLES.get(label, ("#ffd400", "-"))
        xs, ys = [], []
        for j, (_, _, scan, i, *_r) in enumerate(cols):
            e = setup.edges(scan, i)
            keep = [0, 3] + ([1, 2] if e[1] < e[2] else []) if e[0] < e[3] else []
            for k in keep:
                xs.append(j)
                ys.append(scan.base["sz"][i] + e[k] * scan.slope["sz"][i])
        ax.plot(xs, ys, ls="none", marker="_", ms=7, mew=1.6, color=colour, label=label)
    # groups
    groups = []
    for j, c in enumerate(cols):
        key = (round(c[4], 2), round(c[5], 2))
        if not groups or groups[-1][0] != key:
            groups.append([key, j, j])
        groups[-1][2] = j
    for k, (key, j0, j1) in enumerate(groups):
        if k:
            ax.axvline(j0 - 0.5, color="#ffd400", lw=0.8)
        ax.text((j0 + j1) / 2, 1.0, f"{key[0]:g}\n{key[1]:g}", transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=6)
    ax.text(-0.01, 1.0, "SRn\nSRz", transform=ax.transAxes, ha="right", va="bottom", fontsize=6)
    ax.set_xlim(-0.5, len(cols) - 0.5)
    ax.set_ylim(grid[0], grid[-1])
    ax.invert_yaxis()
    ax.set_xlabel("SZ line (grouped by SRn / SRz, ST increasing)")
    ax.set_ylabel("SZ (mm)")
    if title:
        ax.set_title(title, fontsize=9, pad=22)
    if overlays:
        ax.legend(loc="lower right", fontsize=7, framealpha=0.6)


def draw_survey(fig, scans, overlays: dict | None = None, srn_ref: float = 120.0, stacked: bool = False):
    """The overview map(s) and SZ x SRn maps as images, every other line in one lines view (stacked: the
    images on a first row, the lines view below); returns the axes."""
    scans = [s for s in scans if s is not None and s.intensity is not None]
    images = [s for s in scans if is_overview(s, srn_ref) or (s.kind == "srn_sz" and len(s.x) >= 5)]
    rest = [s for s in scans if not any(s is t for t in images)]
    panels = len(images) + (1 if rest else 0)
    if not panels:
        ax = fig.add_subplot(111)
        ax.axis("off")
        return [ax]
    if stacked and images and rest:
        grid = fig.add_gridspec(2, len(images), height_ratios=[1, 1.2])
        spots = [grid[0, k] for k in range(len(images))] + [grid[1, :]]
    else:
        grid = fig.add_gridspec(1, panels, width_ratios=[1] * len(images) + ([2] if rest else []))
        spots = [grid[0, k] for k in range(panels)]
    axes = []
    for k, scan in enumerate(images):
        ax = fig.add_subplot(spots[k])
        title = "overview: ST × SZ (SRn 120, SRz 0)" if scan.kind == "st_sz" else "SZ × SRn sweep"
        try:
            draw_map(ax, scan, overlays, title)
        except (ValueError, np.linalg.LinAlgError):
            draw_map(ax, scan, None, title)
        axes.append(ax)
    if rest:
        ax = fig.add_subplot(spots[len(images)])
        draw_lines(ax, rest, overlays, "SZ lines (survey)")
        axes.append(ax)
    return axes


def draw_steps(fig, scans: dict, overlays: dict | None = None, titles: dict | None = None):
    """Maps side by side on `fig`; returns the axes."""
    axes = fig.subplots(1, len(scans))
    axes = np.atleast_1d(axes)
    for ax, (key, scan) in zip(axes, scans.items()):
        draw_map(ax, scan, overlays, (titles or {}).get(key, key))
    return axes


__all__ = ["draw_map", "draw_steps", "draw_lines", "draw_survey", "edge_curves", "frame_outline", "is_overview"]
