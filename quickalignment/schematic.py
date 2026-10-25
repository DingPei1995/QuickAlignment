"""Matplotlib schematic of the current stage / beam / optics state.

* Top view (lab x-y, from the full stage model): plate orientation (SRz),
  analyzer and its focal plane, beam, optic with its absolute position. The
  analyzer nose and the optic (OSA / zone plate, capillary) are the solids of
  the anti-collision check (collision.py), at scale, red when the plate
  touches them.
* Sample plane (front view along the surface normal, SRn rotation applied,
  SRz not shown): samples, devices and the beam spot. The axes are absolute
  ST / SZ: a point drawn at (ST, SZ) comes onto the beam with those motor
  values (current SRn and piezo, SRz = 0), so the beam spot sits at the
  current ST, SZ.

`draw_reference_feature` draws the reference feature of the initial
calibration on the plate alone (front and side view), to check the entered
position before measuring.
"""

from __future__ import annotations

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon

from .collision import ACCEPTANCE_HALF_ANGLE, CollisionGeometry, SheetBody, SolidBody, default_geometry
from .geometry import PlateGeometry, SampleLayout
from .stage import N_HAT, T_HAT, BeamResult, rot_z, MotorPositions, StageModel

X_HAT = np.array([1.0, 0.0, 0.0])
Y_HAT = np.array([0.0, 1.0, 0.0])

C_BASE, C_RISER, C_BLOCK, C_PAD, C_SCREW = "#bdbdbd", "#e3e3e3", "#d0d0d0", "#e8c400", "#4a3c36"
C_SAMPLE, C_DEVICE = "#ff9a2e", "#1f4fd6"
C_BEAM, C_ANALYZER, C_OPTIC, C_SRN_AXIS = "#d62728", "#1f77b4", "#8c564b", "tab:purple"
C_ACCEPTANCE = "#f2a65a"  # electrons accepted by the analyzer
OPTIC_DRAW_DISTANCE = 32.0  # mm upstream of the optic focus shown at most
ANALYZER_DRAW_LENGTH = 25.0  # mm of the analyzer cone drawn behind its front


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


COLOURS = {"base": C_BASE, "riser": C_RISER, "block": C_BLOCK, "screw": C_SCREW, "sample": C_SAMPLE}


def _solids(layout: SampleLayout):
    """(u0, v0, u1, v1, w0, w1, colour) boxes: plate, tab, riser, contact block, screws, samples."""
    return [(*box[:6], COLOURS[box[6]]) for box in layout.boxes()]


def _cone_outline(body: SolidBody, origin: np.ndarray, axis: np.ndarray, length: float | None = None) -> np.ndarray:
    """Top-view outline (x, y) of a cone body whose axis lies in the horizontal plane."""
    side = np.array([-axis[1], axis[0], 0.0])
    origin = origin - body.offset * side  # + offset: towards the analyzer side (collision.py)
    s0, s1 = body.distance, body.distance + (body.length if length is None else min(length, body.length))
    r0, r1 = body.tip_radius, body.radius_at(s1)
    pts = [origin + s0 * axis + r0 * side, origin + s1 * axis + r1 * side,
           origin + s1 * axis - r1 * side, origin + s0 * axis - r0 * side]
    return np.array([p[:2] for p in pts])


def _sheet_outlines(body: SheetBody, origin: np.ndarray) -> list[np.ndarray]:
    """Top-view outline (x, y) of each straight piece of a bent sheet on the beam axis (beam along +y)."""
    out = []
    for (s0, a0), (s1, a1) in body.segments():
        p0 = np.array([-a0, origin[1] - s0])  # + across: the analyzer side, -x
        p1 = np.array([-a1, origin[1] - s1])
        u = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-9)
        n = np.array([-u[1], u[0]]) * body.thickness / 2
        out.append(np.array([p0 + n, p1 + n, p1 - n, p0 - n]))
    return out


def _draw_top_content(ax, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult,
                      collision: CollisionGeometry, hits: tuple[str, ...], fixed_y: float) -> list[np.ndarray]:
    """Plate, analyzer and optic solids, focal plane, beam and spot; returns the plate outlines."""
    pts = []
    for box in _solids(layout):
        u0, v0, u1, v1, w0, w1, colour = box
        corners = np.array([model.plate_to_lab(m, u, v, ww)[:2] for u in (u0, u1) for v in (v0, v1) for ww in (w0, w1)])
        ax.add_patch(Polygon(convex_hull(corners), closed=True, fc=colour, ec="k", lw=0.7))
        pts.append(corners)

    L = 30
    ax.plot([-L / np.sqrt(2), L / np.sqrt(2)], [L / np.sqrt(2), -L / np.sqrt(2)], "--", color="tab:purple", lw=0.8)
    a = collision.analyzer
    # electron acceptance cone of the analyzer (from the focus to the analyzer front)
    reach = a.distance / np.cos(np.radians(ACCEPTANCE_HALF_ANGLE))
    edges = [rot_z(sign * ACCEPTANCE_HALF_ANGLE) @ (-N_HAT * reach) for sign in (1, -1)]
    ax.add_patch(Polygon([(0, 0), edges[0][:2], edges[1][:2]], closed=True, fc=C_ACCEPTANCE, ec="none", alpha=0.35,
                         zorder=0.5))
    bad = a.name in hits
    ax.add_patch(Polygon(_cone_outline(a, np.zeros(3), -N_HAT, ANALYZER_DRAW_LENGTH), closed=True,
                         fc="#f4b6b6" if bad else "#b8d4f0", ec=C_BEAM if bad else C_ANALYZER, lw=1.5 if bad else 1))
    ax.plot(0, 0, "+", color=C_ANALYZER, ms=12, mew=2)

    hit, fy = result.hit, result.focus_y
    far = max((b.distance + b.length for b in collision.optics), default=10.0)
    y_end = hit[1] if hit is not None else fy + 10
    ax.plot([0, 0], [fy - far - 8, y_end], color=C_BEAM, lw=1.0)
    ax.annotate("", (0, y_end), (0, y_end - 0.01), arrowprops=dict(arrowstyle="-|>", color=C_BEAM, lw=1.0))
    for b in sorted(collision.optics, key=lambda b: -b.distance):  # the part closest to the focus on top
        bad = b.assembly in hits
        origin = (fy if b.moves else fixed_y) * Y_HAT
        outlines = _sheet_outlines(b, origin) if isinstance(b, SheetBody) else [_cone_outline(b, origin, -Y_HAT)]
        for outline in outlines:
            ax.add_patch(Polygon(outline, closed=True, zorder=2.5,  # hides the beam inside it
                                 fc="#f4b6b6" if bad else "#d9c3b0",
                                 ec=C_BEAM if bad else C_OPTIC, lw=1.5 if bad else 0.8))
    ax.plot(0, fy, "o", mfc="none", mec=C_OPTIC, ms=7)
    if hit is not None:
        ax.plot(hit[0], hit[1], "x", color=C_BEAM, ms=9, mew=2)
    return pts


def _draw_top_view(ax, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult, optic_type: str,
                   collision: CollisionGeometry, hits: tuple[str, ...] = (), fixed_y: float = 0.0) -> None:
    pts = _draw_top_content(ax, model, m, layout, result, collision, hits, fixed_y)
    a = collision.analyzer
    front = -N_HAT * a.distance
    ax.text(*(front - N_HAT * 4)[:2], f"{a.name}\nfront {a.distance:g} mm\nfrom focus",  # inside the analyzer
            color=C_ANALYZER, fontsize=7, ha="center", va="center", clip_on=True)
    ax.text(9, -11, "analyzer focal plane", color="tab:purple", fontsize=7, rotation=-45, clip_on=True)
    fy = result.focus_y
    near = min((b.distance for b in collision.optics if b.moves), default=0.0)
    fixed = [b for b in collision.optics if not b.moves]
    far = max((b.distance + b.length for b in collision.optics), default=10.0)
    oy = fy - near + 3  # beside the front of the moving optic, clear of the plate
    gap = min((b.distance + (0.0 if b.moves else fy - fixed_y) for b in collision.optics), default=10.0)
    ax.text(0.5, fy - gap / 2, "beam", color=C_BEAM, fontsize=7, va="center")  # between the optic front and the spot
    for b in (collision.optics if fixed else ()):  # parts moving differently (zone plate, OSA): named
        y = (fy if b.moves else fixed_y) - b.distance - b.length / 2
        if b.distance + b.length / 2 <= OPTIC_DRAW_DISTANCE:
            ax.text(-b.tip_radius - 0.8, y, b.name, color=C_OPTIC, fontsize=7, ha="right", va="center", clip_on=True)
    x_label = max([4.0] + [b.tip_radius + 0.8 for b in collision.optics if b.moves and b.distance <= near + 1])
    ax.text(x_label, oy, f"{optic_type}\nat {result.optic_position:.4f}\nfront {near:g} mm\nfrom its focus"
            + "".join(f"\n{b.name} (fixed) {b.distance:g} mm\nbefore ref. focus" for b in fixed),
            color=C_OPTIC, fontsize=7, va="center")
    ax.text(-1.2, fy, "optic focus", color=C_OPTIC, fontsize=7, ha="right", va="center")
    required = result.required_optic_position
    if required is not None and abs(required - result.optic_position) >= 1e-3:
        ax.text(-4, oy, f"needed:\n{required:.4f}", color=C_OPTIC, fontsize=8, ha="right", va="center", weight="bold")

    front_pts = [(front + T_HAT * a.tip_radius)[:2], (front - T_HAT * a.tip_radius)[:2],
                 [0, fy - min(far, OPTIC_DRAW_DISTANCE)], [0, 0], [10, 10]]
    allp = np.vstack(pts + [np.array(front_pts)])
    lo, hi = allp.min(axis=0) - 3, allp.max(axis=0) + 3
    c, span = (lo + hi) / 2, max((hi - lo).max(), 45)
    ax.set_xlim(c[0] - span / 2, c[0] + span / 2)
    ax.set_ylim(c[1] - span / 2, c[1] + span / 2)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    title = f"Top view (beam ↑)\nST = {m.st:.4f}   SN = {m.sn:.4f}   SRz = {m.srz:g}°"
    if hits:
        title += f"\nCOLLISION: {', '.join(hits)}"
    ax.set_title(title, fontsize=9, color=C_BEAM if hits else "k")


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
    fig, model: StageModel, m: MotorPositions, layout: SampleLayout, result: BeamResult, optic_type: str = "optic",
    collision: CollisionGeometry | None = None, hits: tuple[str, ...] = (), fixed_y: float = 0.0,
):
    """Draw both views; returns (top view axes, sample plane axes).

    `collision`: the analyzer / optic solids drawn in the top view (default: those for `optic_type`);
    `hits`: names of the solids the plate collides with, drawn in red; `fixed_y`: focus at the optics
    reference along the beam, where the fixed solids (OSA) sit."""
    fig.clear()
    ax_top, ax_plane = fig.subplots(1, 2)
    _draw_top_view(ax_top, model, m, layout, result, optic_type, collision or default_geometry(optic_type), tuple(hits),
                   fixed_y)
    _draw_sample_plane(ax_plane, model, m, layout, result)
    fig.tight_layout()
    return ax_top, ax_plane


def feature_warnings(plate: PlateGeometry, u: float, v: float) -> list[str]:
    """Why a reference feature at (u, v) on the plate looks wrong."""
    r0, s0, r1, s1 = plate.riser_bounds()
    if not (r0 <= u <= r1 and s0 <= v <= s1):
        return [f"the feature is outside the sample area of the plate ({r0:g} … {r1:g} × {s0:g} … {s1:g} mm)"]
    return []


def draw_reference_feature(
    fig, plate: PlateGeometry, u: float, v: float, h: float, srn_axis: tuple[float, float] | None = None
) -> None:
    """Front view (from the analyzer, tab up) and side view (analyzer to the right) of the plate with the feature."""
    fig.clear()
    ax_front, ax_side = fig.subplots(1, 2, gridspec_kw={"width_ratios": [3, 2]})
    w_top = plate.total_thickness + h
    bad = bool(feature_warnings(plate, u, v))
    c_feature = "#c00000" if bad else C_BEAM

    def rect(ax, x0, y0, x1, y1, **kw):
        ax.add_patch(Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True, **kw))

    # front view, plate coordinates
    ax = ax_front
    ax.add_patch(Polygon(plate.outline(), closed=True, fc=C_BASE, ec="k", lw=0.8))
    rect(ax, *plate.riser_bounds(), fc=C_RISER, ec="k", lw=0.8)
    if plate.contact_block:
        rect(ax, *plate.contact_block, fc=C_BLOCK, ec="k", lw=0.8)
        for pad in plate.contact_pads:
            rect(ax, *pad, fc=C_PAD, ec="#8a7400", lw=0.6)
        for su, sv in plate.screws:
            ax.add_patch(Circle((su, sv), plate.screw_diameter / 2, fc=C_SCREW, ec="k", lw=0.6))
    ax.axhline(0, color="k", lw=0.5, ls=":")
    ax.axvline(0, color="k", lw=0.5, ls=":")
    ax.axhline(v, color=c_feature, lw=0.8, ls="--")
    ax.axvline(u, color=c_feature, lw=0.8, ls="--")
    ax.plot(u, v, "x", color=c_feature, ms=12, mew=2.5)
    ax.add_patch(Circle((u, v), 0.6, fc="none", ec=c_feature, lw=1.2))
    if srn_axis is not None:
        ax.plot(*srn_axis, "o", mfc="none", mec=C_SRN_AXIS, ms=9, mew=1.5)
    hw, top = plate.width / 2, plate.height / 2 + plate.neck_height + plate.tab_height
    ax.set_xlim(-hw - 1.5, hw + 1.5)
    ax.set_ylim(plate.lowest_v() - 1.5, top + 1.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.grid(alpha=0.25)
    ax.set_title(f"{plate.name}\nFront view (from the analyzer, tab up): x = {u:g} mm, y = {v:g} mm", fontsize=9)
    handles = [
        Line2D([], [], ls="none", marker="x", color=c_feature, ms=8, mew=2, label="reference feature"),
        Line2D([], [], ls=":", color="k", lw=0.8, label="plate centre"),
    ]
    if srn_axis is not None:
        handles.append(Line2D([], [], ls="none", marker="o", mfc="none", mec=C_SRN_AXIS, ms=8, mew=1.5,
                              label="SRn axis (configuration)"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, fontsize=7, frameon=False)

    # side view: height w to the right (towards the analyzer), y up
    ax = ax_side
    half = plate.height / 2
    rect(ax, 0, -half, plate.base_thickness, half, fc=C_BASE, ec="k", lw=0.8)
    rect(ax, 0, half, plate.base_thickness, top, fc=C_BASE, ec="k", lw=0.8)
    _, s0, _, s1 = plate.riser_bounds()
    rect(ax, plate.base_thickness, s0, plate.total_thickness, s1, fc=C_RISER, ec="k", lw=0.8)
    if plate.contact_block:
        _, c0, _, c1 = plate.contact_block
        rect(ax, 0, c0, plate.contact_block_top, c1, fc=C_BLOCK, ec="k", lw=0.8)
        r = plate.screw_diameter / 2
        for sv in sorted({sv for _, sv in plate.screws}):
            rect(ax, plate.contact_block_top, sv - r, plate.screw_top, sv + r, fc=C_SCREW, ec="k", lw=0.6)
    if h > 0:  # the sample carrying the feature, drawn 1 mm high
        rect(ax, plate.total_thickness, v - 0.5, w_top, v + 0.5, fc=C_SAMPLE, ec="k", lw=0.8)
    ax.axvline(plate.total_thickness, color="k", lw=0.5, ls=":")
    ax.axhline(v, color=c_feature, lw=0.8, ls="--")
    ax.plot(w_top, v, "x", color=c_feature, ms=12, mew=2.5)
    x_max = max(plate.total_thickness, plate.screw_top, w_top) + 4
    ax.annotate("", (x_max, top - 0.5), (x_max - 2.5, top - 0.5), arrowprops=dict(arrowstyle="-|>", color=C_ANALYZER))
    ax.text(x_max - 0.2, top + 0.2, "analyzer", color=C_ANALYZER, fontsize=7, ha="right", va="bottom")
    ax.set_xlim(-1, x_max + 0.5)
    ax.set_ylim(plate.lowest_v() - 1.5, top + 1.5)
    ax.set_aspect("equal")
    ax.set_xlabel("height above the back face (mm)")
    ax.set_ylabel("y (mm)")
    ax.grid(alpha=0.25)
    ax.set_title(
        f"Side view\nH = {h:g} mm above the plate surface ({plate.total_thickness:g}) → w = {w_top:g} mm", fontsize=9,
    )
    fig.tight_layout()
