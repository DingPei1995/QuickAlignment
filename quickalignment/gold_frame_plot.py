"""Drawing gold-frame maps (matplotlib): intensity with the edges a setup predicts drawn over it.

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
    # F = A (st, sz) + b, with SZ = y along every line (base 0, slope 1)
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
        if scan.kind == "st_sz" and np.all(scan.slope["sz"] == 1) and np.all(scan.base["sz"] == 0):
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


def draw_steps(fig, scans: dict, overlays: dict | None = None, titles: dict | None = None):
    """The three maps side by side on `fig`; returns the axes."""
    axes = fig.subplots(1, len(scans))
    axes = np.atleast_1d(axes)
    for ax, (key, scan) in zip(axes, scans.items()):
        draw_map(ax, scan, overlays, (titles or {}).get(key, key))
    return axes


__all__ = ["draw_map", "draw_steps", "edge_curves", "frame_outline"]
