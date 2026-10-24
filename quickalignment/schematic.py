"""Matplotlib schematic of the current stage / beam / optics state.

Three projections computed from the full stage model:
top view (lab x-y), view from the analyzer (t-z) and side view (n-z).
"""

from __future__ import annotations

import numpy as np
from matplotlib.patches import Polygon

from .geometry import SampleLayout
from .stage import N_HAT, T_HAT, Z_HAT, BeamResult, MotorPositions, StageModel

X_HAT = np.array([1.0, 0.0, 0.0])
Y_HAT = np.array([0.0, 1.0, 0.0])

C_BASE, C_RISER, C_SAMPLE, C_DEVICE = "#bdbdbd", "#e3e3e3", "#ff9a2e", "#1f4fd6"
C_BEAM, C_ANALYZER, C_OPTIC, C_AXES = "#d62728", "#1f77b4", "#8c564b", "#2ca02c"
OPTIC_DRAW_DISTANCE = 22.0  # mm upstream of the focus, schematic only


def convex_hull(points: np.ndarray) -> np.ndarray:
    pts = sorted(set(map(tuple, np.round(points, 9))))
    if len(pts) <= 2:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def _solids(layout: SampleLayout):
    """(u0, v0, u1, v1, w0, w1, colour) boxes of plate, tab, riser, samples."""
    p = layout.plate
    w, h = p.width / 2, p.height / 2
    r0, s0, r1, s1 = p.riser_bounds()
    out = [
        (-w, -h, w, h, 0.0, p.base_thickness, C_BASE),
        (-p.tab_width / 2, h, p.tab_width / 2, h + p.neck_height + p.tab_height, 0.0, p.base_thickness, C_BASE),
        (r0, s0, r1, s1, p.base_thickness, p.total_thickness, C_RISER),
    ]
    for s in layout.samples:
        u0, v0, u1, v1 = s.bounds()
        out.append((u0, v0, u1, v1, p.total_thickness, p.total_thickness + s.height, C_SAMPLE))
    return out


def _box_points(model, m, box) -> np.ndarray:
    u0, v0, u1, v1, w0, w1, _ = box
    return np.array([model.plate_to_lab(m, u, v, ww) for u in (u0, u1) for v in (v0, v1) for ww in (w0, w1)])


def _proj(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    pts = np.atleast_2d(pts)
    return np.column_stack([pts @ a, pts @ b])


def _draw_hulls(ax, model, m, layout, a, b) -> list[np.ndarray]:
    drawn = []
    for box in _solids(layout):
        xy = _proj(_box_points(model, m, box), a, b)
        ax.add_patch(Polygon(convex_hull(xy), closed=True, fc=box[6], ec="k", lw=0.8))
        drawn.append(xy)
    return drawn


def _device_points(model, m, layout):
    out = []
    t = layout.plate.total_thickness
    for s in layout.samples:
        for d in s.devices:
            u, v = d.position(s)
            out.append((d.name, model.plate_to_lab(m, u, v, t + s.height)))
    return out


def _fit(ax, pts: list[np.ndarray], min_span: float, pad: float = 3.0) -> None:
    allp = np.vstack(pts)
    lo, hi = allp.min(axis=0) - pad, allp.max(axis=0) + pad
    c, span = (lo + hi) / 2, max((hi - lo).max(), min_span)
    ax.set_xlim(c[0] - span / 2, c[0] + span / 2)
    ax.set_ylim(c[1] - span / 2, c[1] + span / 2)
    ax.set_aspect("equal")


def draw_schematic(fig, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult) -> None:
    fig.clear()
    gs = fig.add_gridspec(2, 2, width_ratios=[1.35, 1])
    ax_top, ax_front, ax_side = fig.add_subplot(gs[:, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, 1])
    hit = result.hit

    # ---------------- top view ----------------
    ax = ax_top
    pts = _draw_hulls(ax, model, m, layout, X_HAT, Y_HAT)
    L = 30
    ax.plot([-L / np.sqrt(2), L / np.sqrt(2)], [L / np.sqrt(2), -L / np.sqrt(2)], "--", color="tab:purple", lw=0.8)
    tip, base = -N_HAT * 5, -N_HAT * 20
    cone = [tip + T_HAT * 1.2, tip - T_HAT * 1.2, base - T_HAT * 4.5, base + T_HAT * 4.5]
    ax.add_patch(Polygon([p[:2] for p in cone], closed=True, fc="#b8d4f0", ec=C_ANALYZER))
    ax.text(*(base[:2] + [-6, -4]), "analyzer", color=C_ANALYZER, fontsize=8)
    ax.plot(0, 0, "+", color=C_ANALYZER, ms=12, mew=2)

    fy = result.focus_y
    oy = fy - OPTIC_DRAW_DISTANCE
    y_end = hit[1] if hit is not None else fy + 10
    ax.annotate("", (0, y_end), (0, oy - 12), arrowprops=dict(arrowstyle="-|>", color=C_BEAM, lw=1.6))
    ax.add_patch(Polygon([(-2.5, oy - 1), (2.5, oy - 1), (2.5, oy + 1), (-2.5, oy + 1)], closed=True, fc="#d9c3b0", ec=C_OPTIC))
    ax.text(3, oy - 0.5, "optic\n(not to scale)", color=C_OPTIC, fontsize=7, va="center")
    ax.plot(0, fy, "o", mfc="none", mec=C_OPTIC, ms=7, label="optics focus (ref)")
    if result.delta is not None and abs(result.delta) > 1e-6:
        ax.annotate("", (-4, oy + result.delta), (-4, oy), arrowprops=dict(arrowstyle="-|>", color=C_OPTIC, lw=1.5))
        ax.text(-4.5, oy + result.delta / 2, f"{result.delta:+.3f}", color=C_OPTIC, fontsize=8, ha="right", va="center")
    if hit is not None:
        ax.plot(hit[0], hit[1], "x", color=C_BEAM, ms=9, mew=2)
    pts += [np.array([[0, oy - 12], [0, 0], [-20, -20], [10, 10]])]
    _fit(ax, pts, 45)
    ax.set_title(f"Top view (beam +y)\nSRz = {m.srz:g}°   SN = {m.sn:.4g}   ST = {m.st:.4g}", fontsize=9)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y = beam (mm)")
    ax.grid(alpha=0.2)

    # ---------------- view from analyzer ----------------
    ax = ax_front
    t = layout.plate.total_thickness
    outline = np.array([model.plate_to_lab(m, u, v, layout.plate.base_thickness) for u, v in layout.plate.outline()])
    ax.add_patch(Polygon(_proj(outline, T_HAT, Z_HAT), closed=True, fc=C_BASE, ec="k", lw=0.8))
    r0, s0, r1, s1 = layout.plate.riser_bounds()
    riser = np.array([model.plate_to_lab(m, u, v, t) for u, v in ((r0, s0), (r1, s0), (r1, s1), (r0, s1))])
    ax.add_patch(Polygon(_proj(riser, T_HAT, Z_HAT), closed=True, fc=C_RISER, ec="k", lw=0.8))
    for s in layout.samples:
        u0, v0, u1, v1 = s.bounds()
        rect = np.array([model.plate_to_lab(m, u, v, t + s.height) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))])
        xy = _proj(rect, T_HAT, Z_HAT)
        ax.add_patch(Polygon(xy, closed=True, fc=C_SAMPLE, ec="k", lw=0.8, alpha=0.85))
        ax.text(*xy.mean(axis=0), s.name, fontsize=7, ha="center", va="center")
    for name, p in _device_points(model, m, layout):
        q = _proj(p, T_HAT, Z_HAT)[0]
        ax.plot(*q, "o", mfc="white", mec=C_DEVICE, ms=5)
        ax.text(q[0] + 0.3, q[1] + 0.3, name, color=C_DEVICE, fontsize=7)
    ax.plot(0, 0, "+", color=C_ANALYZER, ms=14, mew=2)
    if hit is not None:
        q = _proj(hit, T_HAT, Z_HAT)[0]
        ax.plot(*q, "x", color=C_BEAM, ms=10, mew=2)
    _fit(ax, [_proj(outline, T_HAT, Z_HAT), np.zeros((1, 2))], 20, pad=1.5)
    ax.set_title(f"View from analyzer\nSRn = {m.srn:g}°   SZ = {m.sz:.4g}", fontsize=9)
    ax.set_xlabel("along +ST (mm)")
    ax.set_ylabel("z (mm)")
    ax.grid(alpha=0.2)

    # ---------------- side view ----------------
    ax = ax_side
    pts = _draw_hulls(ax, model, m, layout, N_HAT, Z_HAT)
    ax.axvline(0, ls="--", color=C_ANALYZER, lw=1)
    ax.axhline(0, color=C_BEAM, lw=1, alpha=0.6)
    ax.annotate("", (-0.5, 1.5), (-8, 1.5), arrowprops=dict(arrowstyle="-|>", color=C_ANALYZER))
    ax.text(-8, 2.0, "analyzer", color=C_ANALYZER, fontsize=8)
    if hit is not None:
        q = _proj(hit, N_HAT, Z_HAT)[0]
        ax.plot(*q, "x", color=C_BEAM, ms=10, mew=2)
    _fit(ax, pts + [np.array([[-9, 0], [0, 0]])], 25)
    ax.set_title("Side view (along ST)\ndashed = analyzer focal plane, red = beam", fontsize=9)
    ax.set_xlabel("along +SN (mm)")
    ax.set_ylabel("z (mm)")
    ax.grid(alpha=0.2)

    fig.tight_layout()
