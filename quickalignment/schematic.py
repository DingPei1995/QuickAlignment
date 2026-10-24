"""Matplotlib schematic of the current stage / beam / optics state.

* Top view (lab x-y, from the full stage model): plate orientation (SRz),
  analyzer and its focal plane, beam, optic with its absolute position.
* Sample plane (front view along the surface normal, SRn rotation applied,
  SRz not shown): samples, devices and the beam spot. The axes are absolute
  ST / SZ: a point drawn at (ST, SZ) comes onto the beam with those motor
  values (current SRn and piezo, SRz = 0), so the beam spot sits at the
  current ST, SZ.
"""

from __future__ import annotations

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon

from .geometry import SampleLayout
from .stage import N_HAT, T_HAT, BeamResult, MotorPositions, StageModel

X_HAT = np.array([1.0, 0.0, 0.0])
Y_HAT = np.array([0.0, 1.0, 0.0])

C_BASE, C_RISER, C_BLOCK, C_PAD, C_SCREW = "#bdbdbd", "#e3e3e3", "#d0d0d0", "#e8c400", "#4a3c36"
C_SAMPLE, C_DEVICE = "#ff9a2e", "#1f4fd6"
C_BEAM, C_ANALYZER, C_OPTIC, C_SRN_AXIS = "#d62728", "#1f77b4", "#8c564b", "tab:purple"
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
    """(u0, v0, u1, v1, w0, w1, colour) boxes: plate, tab, riser, contact block, screws, samples."""
    p = layout.plate
    w, h = p.width / 2, p.height / 2
    r0, s0, r1, s1 = p.riser_bounds()
    out = [
        (-w, -h, w, h, 0.0, p.base_thickness, C_BASE),
        (-p.tab_width / 2, h, p.tab_width / 2, h + p.neck_height + p.tab_height, 0.0, p.base_thickness, C_BASE),
        (r0, s0, r1, s1, p.base_thickness, p.total_thickness, C_RISER),
    ]
    if p.contact_block:
        b0, c0, b1, c1 = p.contact_block
        out.append((b0, c0, b1, c1, 0.0, p.contact_block_top, C_BLOCK))
        r = p.screw_diameter / 2
        out += [(u - r, v - r, u + r, v + r, p.contact_block_top, p.screw_top, C_SCREW) for u, v in p.screws]
    for s in layout.samples:
        u0, v0, u1, v1 = s.bounds()
        out.append((u0, v0, u1, v1, p.total_thickness, p.total_thickness + s.height, C_SAMPLE))
    return out


def _draw_top_view(ax, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult, optic_type: str) -> None:
    pts = []
    for box in _solids(layout):
        u0, v0, u1, v1, w0, w1, colour = box
        corners = np.array([model.plate_to_lab(m, u, v, ww)[:2] for u in (u0, u1) for v in (v0, v1) for ww in (w0, w1)])
        ax.add_patch(Polygon(convex_hull(corners), closed=True, fc=colour, ec="k", lw=0.7))
        pts.append(corners)

    L = 30
    ax.plot([-L / np.sqrt(2), L / np.sqrt(2)], [L / np.sqrt(2), -L / np.sqrt(2)], "--", color="tab:purple", lw=0.8)
    ax.text(9, -11, "analyzer focal plane", color="tab:purple", fontsize=7, rotation=-45, clip_on=True)
    tip, base = -N_HAT * 5, -N_HAT * 20
    cone = [tip + T_HAT * 1.2, tip - T_HAT * 1.2, base - T_HAT * 4.5, base + T_HAT * 4.5]
    ax.add_patch(Polygon([p[:2] for p in cone], closed=True, fc="#b8d4f0", ec=C_ANALYZER))
    ax.text(*(base[:2] + [-7, -4]), "analyzer", color=C_ANALYZER, fontsize=8)
    ax.plot(0, 0, "+", color=C_ANALYZER, ms=12, mew=2)

    hit, fy = result.hit, result.focus_y
    oy = fy - OPTIC_DRAW_DISTANCE
    y_end = hit[1] if hit is not None else fy + 10
    ax.annotate("", (0, y_end), (0, oy - 12), arrowprops=dict(arrowstyle="-|>", color=C_BEAM, lw=1.6))
    ax.text(0.8, oy - 11, "beam", color=C_BEAM, fontsize=8)
    ax.add_patch(Polygon([(-2.5, oy - 1), (2.5, oy - 1), (2.5, oy + 1), (-2.5, oy + 1)], closed=True, fc="#d9c3b0", ec=C_OPTIC))
    ax.text(3, oy, f"{optic_type}\nat {result.optic_position:.4f}", color=C_OPTIC, fontsize=8, va="center")
    ax.plot(0, fy, "o", mfc="none", mec=C_OPTIC, ms=7)
    ax.text(-1.2, fy, "optic focus", color=C_OPTIC, fontsize=7, ha="right", va="center")
    required = result.required_optic_position
    if required is not None and abs(required - result.optic_position) >= 1e-3:
        ax.text(-3.2, oy, f"needed:\n{required:.4f}", color=C_OPTIC, fontsize=8, ha="right", va="center", weight="bold")
    if hit is not None:
        ax.plot(hit[0], hit[1], "x", color=C_BEAM, ms=9, mew=2)

    allp = np.vstack(pts + [np.array([[0, oy - 12], [0, 0], [-20, -20], [10, 10]])])
    lo, hi = allp.min(axis=0) - 3, allp.max(axis=0) + 3
    c, span = (lo + hi) / 2, max((hi - lo).max(), 45)
    ax.set_xlim(c[0] - span / 2, c[0] + span / 2)
    ax.set_ylim(c[1] - span / 2, c[1] + span / 2)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"Top view (beam ↑)\nST = {m.st:.4f}   SN = {m.sn:.4f}   SRz = {m.srz:g}°", fontsize=9)


def _draw_sample_plane(ax, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult) -> None:
    c = model.config
    plate = layout.plate

    def to_xy(u, v):
        q = model.stage_frame(m, u, v)
        return c.st0 - q[0], c.sz0 - q[1]

    def poly(points, **kw):
        xy = np.array([to_xy(u, v) for u, v in points])
        ax.add_patch(Polygon(xy, closed=True, **kw))
        return xy

    def rect(r, **kw):
        u0, v0, u1, v1 = r
        return poly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], **kw)

    outline = poly(plate.outline(), fc=C_BASE, ec="k", lw=0.8)
    rect(plate.riser_bounds(), fc=C_RISER, ec="k", lw=0.8)
    extra = [outline]
    if plate.contact_block:
        extra.append(rect(plate.contact_block, fc=C_BLOCK, ec="k", lw=0.8))
        for pad in plate.contact_pads:
            rect(pad, fc=C_PAD, ec="#8a7400", lw=0.6)
        for u, v in plate.screws:
            ax.add_patch(Circle(to_xy(u, v), plate.screw_diameter / 2, fc=C_SCREW, ec="k", lw=0.6))
    for s in layout.samples:
        xy = rect(s.bounds(), fc=C_SAMPLE, ec="k", lw=0.8, alpha=0.9)
        ax.text(*xy.mean(axis=0), s.name, fontsize=7, ha="center", va="center")
        for d in s.devices:
            p = to_xy(*d.position(s))
            ax.plot(*p, "o", mfc="white", mec=C_DEVICE, ms=5, mew=1.5)
            ax.text(p[0], p[1], f"  {d.name}", color=C_DEVICE, fontsize=7, va="bottom")

    # SRn axis, analyzer focus (projected along the surface normal) and beam spot
    ax.plot(*to_xy(c.srn_axis_u, c.srn_axis_v), "o", mfc="none", mec=C_SRN_AXIS, ms=9, mew=1.5)
    focus_uv = model.lab_to_plate(m, np.zeros(3))[:2]
    ax.plot(*to_xy(*focus_uv), "+", color=C_ANALYZER, ms=14, mew=2)
    if result.plate_uv is not None:
        p = to_xy(*result.plate_uv)
        ax.plot(*p, "x", color=C_BEAM, ms=11, mew=2.5)
        ax.add_patch(Circle(p, 0.6, fc="none", ec=C_BEAM, lw=1.2))

    allp = np.vstack(extra)
    lo, hi = allp.min(axis=0) - 1.5, allp.max(axis=0) + 1.5
    ctr, span = (lo + hi) / 2, (hi - lo).max()
    # front view: larger ST / SZ values are to the left / below
    ax.set_xlim(ctr[0] + span / 2, ctr[0] - span / 2)
    ax.set_ylim(ctr[1] + span / 2, ctr[1] - span / 2)
    ax.set_aspect("equal")
    ax.set_xlabel("ST (mm) that brings a point onto the beam (SRz = 0)")
    ax.set_ylabel("SZ (mm)")
    ax.grid(alpha=0.25)
    ax.set_title(
        f"Sample plane, front view   SRn = {m.srn:g}°\nSZ = {m.sz:.4f}   PIX = {m.pix:g}   PIY = {m.piy:g}",
        fontsize=9,
    )
    # legend with the same markers and colours as drawn
    handles = [
        Line2D([], [], ls="none", marker="x", color=C_BEAM, ms=8, mew=2, label="beam spot"),
        Line2D([], [], ls="none", marker="+", color=C_ANALYZER, ms=10, mew=2, label="analyzer focus (projected)"),
        Line2D([], [], ls="none", marker="o", mfc="none", mec=C_SRN_AXIS, ms=8, mew=1.5, label="SRn axis"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=7, frameon=False,
              handletextpad=0.3, columnspacing=1.0)


def draw_schematic(
    fig, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult, optic_type: str = "optic"
) -> None:
    fig.clear()
    ax_top, ax_plane = fig.subplots(1, 2)
    _draw_top_view(ax_top, model, m, layout, result, optic_type)
    _draw_sample_plane(ax_plane, model, m, layout, result)
    fig.tight_layout()
