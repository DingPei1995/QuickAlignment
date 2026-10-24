"""Rotate the sample (SRn / SRz) and find it again: new ST / SN / SZ and optic.

Typical use (nano-ARPES): a sample was found at SRn = 120, SRz = 0 and
measured (Map), but its orientation is not the wanted one. ARPES viewer
gives the numbers:

* "Show information" (metadata): the stage positions of the measurement and
  the zone plate position at which it was in focus;
* the k-conversion window: the theta / phi offsets (the point picked as the
  k-space origin, e.g. Gamma or a Dirac cone) and the "Sample rotation"
  ("Set rotation from contour..."), which stands a picked direction upright
  (along the slit, ky).

From these this module computes the new SRn (and SRz) and the ST / SN / SZ
that put the same sample point back on the beam, plus the optic position.

Analyzer angles (as in ARPES viewer): theta = deflector angle (contour x),
phi = angle along the slit (contour y); the emission direction is

    d = sin(theta) cos(phi) p + sin(phi) s + cos(theta) cos(phi) a

with a the lens axis (sample -> analyzer, -n), s the slit direction and p the
deflector direction. Which lab directions s and p are, and their signs, is a
setting (`AnalyzerGeometry`) to be checked once on a real sample.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .geometry import SampleLayout
from .stage import (
    B, N_HAT, T_HAT, Z_HAT, MotorPositions, OpticsCalibration, StageConfig, StageModel, beam_on_layout, rot_2d, rot_z,
)

SLIT_ORIENTATIONS = ("horizontal", "vertical")  # ANTARES: horizontal slit


@dataclass
class AnalyzerGeometry:
    """How the analyzer angles sit in the lab, seen from the analyzer.

    slit: "horizontal" (along ST, ANTARES) or "vertical" (along Z).
    slit_sign: +1 if a positive slit angle (phi) points up (vertical slit) or
      to the right (horizontal slit), seen from the analyzer; -1 otherwise.
    deflector_sign: likewise for a positive deflector angle (theta): to the
      right (vertical slit) or up (horizontal slit).
    """

    slit: str = "horizontal"
    slit_sign: int = 1
    # -1: measured 2026-09-18 (SRn 120 -> 104, i.e. clockwise seen from the analyzer, looked clockwise in
    # ARPES viewer), so with the horizontal slit the contour must not be mirrored against the analyzer view
    deflector_sign: int = -1

    def axes(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(a, s, p): lens axis, slit and deflector directions in the lab. Right = +ST, up = +Z."""
        a = -N_HAT
        if self.slit == "horizontal":
            s, p = self.slit_sign * T_HAT, self.deflector_sign * Z_HAT
        else:
            s, p = self.slit_sign * Z_HAT, self.deflector_sign * T_HAT
        return a, s, p

    def display_handedness(self) -> int:
        """+1 if the contour (theta across, phi up) is the view from the analyzer, -1 if mirrored."""
        _, s, p = self.axes()
        # components on (right, up) = (T, Z)
        return int(np.sign((p @ T_HAT) * (s @ Z_HAT) - (p @ Z_HAT) * (s @ T_HAT)))


def wrap180(angle: float) -> float:
    return float((angle + 180.0) % 360.0 - 180.0)


def emission_lab(geo: AnalyzerGeometry, theta: float, phi: float) -> np.ndarray:
    a, s, p = geo.axes()
    t, f = np.radians(theta), np.radians(phi)
    return np.sin(t) * np.cos(f) * p + np.sin(f) * s + np.cos(t) * np.cos(f) * a


def analyzer_angles(geo: AnalyzerGeometry, d: np.ndarray) -> tuple[float, float]:
    """(theta, phi) of a lab direction."""
    a, s, p = geo.axes()
    d = d / np.linalg.norm(d)
    return float(np.degrees(np.arctan2(d @ p, d @ a))), float(np.degrees(np.arcsin(np.clip(d @ s, -1, 1))))


def _srn_matrix(alpha: float) -> np.ndarray:
    m = np.eye(3)
    m[:2, :2] = rot_2d(alpha)
    return m


def plate_to_lab_dir(model: StageModel, srn: float, srz: float) -> np.ndarray:
    """Matrix taking plate-frame directions to the lab (SRn about the plate normal, then SRz)."""
    return rot_z(-srz) @ B @ _srn_matrix(srn - model.config.srn_ref)


def emission_in_plate(model: StageModel, geo: AnalyzerGeometry, m: MotorPositions, theta: float, phi: float) -> np.ndarray:
    """Emission direction seen at (theta, phi) with the stage at m, in the plate frame."""
    return plate_to_lab_dir(model, m.srn, m.srz).T @ emission_lab(geo, theta, phi)


def _solve_trig(a: float, b: float, c: float) -> list[float]:
    """Angles x (deg) with a cos x + b sin x + c = 0."""
    r = np.hypot(a, b)
    if r < 1e-12 or abs(c) > r * (1 + 1e-12):
        return []
    base = np.degrees(np.arctan2(b, a))
    half = np.degrees(np.arccos(np.clip(-c / r, -1, 1)))
    return [base + half, base - half] if half > 1e-9 else [base]


def _nearest(angle: float, to: float) -> float:
    return to + wrap180(angle - to)


@dataclass
class RotationCandidate:
    srn: float
    srz: float
    description: str
    theta: float  # where the picked direction appears afterwards
    phi: float

    def as_motors(self, m: MotorPositions) -> MotorPositions:
        return replace(m, srn=self.srn, srz=self.srz)


def _candidate(model, geo, d_plate, srn, srz, text) -> RotationCandidate:
    th, ph = analyzer_angles(geo, plate_to_lab_dir(model, srn, srz) @ d_plate)
    return RotationCandidate(srn, srz, text, th, ph)


def align_direction(
    model: StageModel, geo: AnalyzerGeometry, m: MotorPositions, rotation: float, along: str = "slit", sign: int = 1,
) -> list[RotationCandidate]:
    """SRn that turns a direction, picked with ARPES viewer's "Set rotation from contour...", along the slit.

    `rotation` is the viewer's "Sample rotation" (deg): turning the contour by
    it stands the picked direction along the slit (ky). The sample has to turn
    by the same amount in the view from the analyzer; `display_handedness`
    gives the sign between the two views and `sign` (+1/-1) flips it if the
    first real test shows the opposite sense. along="deflector" adds 90 deg.
    The line has no direction, so the turn 180 deg away is offered as well.
    """
    delta = sign * geo.display_handedness() * (rotation + (90.0 if along == "deflector" else 0.0))
    delta = wrap180(delta)
    out = []
    for d in sorted({round(wrap180(delta), 9), round(wrap180(delta + 180.0), 9)}, key=abs):
        out.append(RotationCandidate(m.srn + d, m.srz, f"ΔSRn = {d:+.3f}°", float("nan"), float("nan")))
    return out


def onto_line(
    model: StageModel, geo: AnalyzerGeometry, m: MotorPositions, theta: float, phi: float, line: str = "slit",
) -> list[RotationCandidate]:
    """SRn (SRz kept) that puts the direction seen at (theta, phi) on the slit (theta = 0) or on the deflector axis (phi = 0)."""
    d = emission_in_plate(model, geo, m, theta, phi)
    a, s, p = geo.axes()
    q = plate_to_lab_dir(model, model.config.srn_ref, m.srz).T @ (p if line == "slit" else s)
    # q . Rn(alpha) d = A cos(alpha) + B sin(alpha) + C
    A = q[0] * d[0] + q[1] * d[1]
    Bc = q[1] * d[0] - q[0] * d[1]
    C = q[2] * d[2]
    out = []
    for alpha in _solve_trig(A, Bc, C):
        srn = _nearest(model.config.srn_ref + alpha, m.srn)
        c = _candidate(model, geo, d, srn, m.srz, f"ΔSRn = {srn - m.srn:+.3f}°")
        if abs(c.theta) < 90:  # towards the analyzer
            out.append(c)
    return sorted(out, key=lambda c: abs(c.srn - m.srn))


def to_center(model: StageModel, geo: AnalyzerGeometry, m: MotorPositions, theta: float, phi: float) -> list[RotationCandidate]:
    """SRn and SRz that bring the direction seen at (theta, phi) onto the lens axis (theta = phi = 0)."""
    d = emission_in_plate(model, geo, m, theta, phi)
    a = geo.axes()[0]
    out = []
    # the lab z component does not depend on SRz: (Rn d)_v = d_u sin + d_v cos = 0
    for alpha in _solve_trig(d[1], d[0], 0.0):
        srn = _nearest(model.config.srn_ref + alpha, m.srn)
        h = plate_to_lab_dir(model, srn, 0.0) @ d
        psi = np.degrees(np.arctan2(a[1], a[0]) - np.arctan2(h[1], h[0]))
        srz = wrap180(-psi)
        c = _candidate(model, geo, d, srn, srz, f"ΔSRn = {srn - m.srn:+.3f}°, SRz = {srz:.3f}°")
        if abs(c.theta) < 1e-6 and abs(c.phi) < 1e-6:
            out.append(c)
    return sorted(out, key=lambda c: abs(c.srz - m.srz) + abs(c.srn - m.srn))


@dataclass
class Relocation:
    measured: MotorPositions
    new: MotorPositions
    uvw: tuple[float, float, float]
    target: str
    optic_measured: float
    optic_new: float | None
    optic_source: str
    focus_distance: float = 0.0  # mm, model distance of the point from the analyzer focus at the new position
    measured_focus_distance: float = 0.0  # ... at the measured position


def focus_distance(model: StageModel, m: MotorPositions, u: float, v: float, w: float) -> float:
    """Distance (mm) of plate point (u, v, w) from the analyzer focus (lab origin)."""
    return float(np.linalg.norm(model.plate_to_lab(m, u, v, w)))


def relocate(
    model: StageModel,
    layout: SampleLayout,
    measured: MotorPositions,
    srn: float,
    srz: float,
    optics: OpticsCalibration,
    measured_optic: float | None = None,
    recentre_piezo: bool = False,
    to_analyzer_focus: bool = False,
    default_height: float = 0.0,
    keep_sn: bool = False,
    limits: dict[str, tuple[float, float]] | None = None,
) -> Relocation:
    """Stage positions putting the measured sample point back on the beam after rotating to (srn, srz).

    `measured`: the stage positions of the measurement (the point of interest
    on the beam). By default the point is kept where it was measured, so the
    calibration offsets (ST0, SZ0, SN_f) cancel and only the rotation axes
    matter; with `to_analyzer_focus` it is put on the analyzer focus instead.
    With `keep_sn` SN stays as measured and ST compensates: the point slides
    along the beam (sqrt2 per mm of SN) and the optic refocuses on it, which
    is how the stage is usually run (SN fixed in the analyzer focal plane).
    `measured_optic`: the optic position at which the measurement was in
    focus (e.g. Motor.ZP_ZS); None uses the configuration's optics reference.
    `limits`: travel ranges {"st"|"sn"|"sz": (lo, hi)}. ST, SN, SZ move along
    orthonormal directions, so clamping each one gives the reachable position
    closest to the wanted one (with `to_analyzer_focus`: closest to the focus);
    `focus_distance` tells what is left.
    """
    hit, uv, w, target = beam_on_layout(model, measured, layout)
    if hit is None or not any(target.split("/")[0] == s.name for s in layout.samples):
        # not on a sample of the layout: plane at the given sample height
        w = model.plate.total_thickness + default_height
        hit = model.beam_hit(measured, w)
        if hit is None:
            raise ValueError("The beam runs parallel to the plate at the measured position.")
        u, v, _ = model.lab_to_plate(measured, hit)
        uv, target = (float(u), float(v)), f"surface at H = {default_height:g} mm (no sample in the layout)"
    u, v = uv
    pix = model.config.pi_center if recentre_piezo else measured.pix
    piy = model.config.pi_center if recentre_piezo else measured.piy
    new = model.motors_for_target(u, v, w, srn, srz, pix, piy)
    if not to_analyzer_focus:
        old = model.motors_for_target(u, v, w, measured.srn, measured.srz, measured.pix, measured.piy)
        new.st += measured.st - old.st
        new.sn += measured.sn - old.sn
        new.sz += measured.sz - old.sz
    if keep_sn:
        # SN and ST move the point by (N + T)/sqrt2 per mm: x unchanged when dST = -dSN
        d_sn = measured.sn - new.sn
        new.sn += d_sn
        new.st -= d_sn
    for name, (lo, hi) in (limits or {}).items():
        setattr(new, name, float(min(max(getattr(new, name), lo), hi)))

    if measured_optic is not None:
        ref = replace(optics, enabled=True, motors=measured, surface_w=w, optic_position=measured_optic)
        source = "measurement"
    else:
        ref, source = optics, "configuration"
    optic_measured = ref.position_for_focus(model, float(hit[1]))
    new_hit = model.beam_hit(new, w)
    optic_new = None if new_hit is None else ref.position_for_focus(model, float(new_hit[1]))
    return Relocation(measured, new, (u, v, w), target, optic_measured, optic_new, source,
                      focus_distance(model, new, u, v, w), focus_distance(model, measured, u, v, w))


@dataclass
class AxisFit:
    config: StageConfig  # the input configuration with the fitted SRn axis
    point: tuple[float, float]  # the measured point, plate frame
    residuals: list[tuple[float, float]]  # per position: lab x, z of the point (mm), 0 = on the beam
    lever_arm: float  # distance point - SRn axis (mm)


def fit_srn_axis(model: StageModel, positions: list[MotorPositions], w: float) -> AxisFit:
    """SRn axis position (plate frame) from positions where the same sample point was on the beam.

    Needs at least two positions with different SRn. The model is affine in
    the plate point and the axis, so this is a linear least-squares fit of
    "the point is on the beam" (lab x = z = 0) at every position; the point's
    place along the beam is free (it may sit in front of or behind the focus).
    ST0 / SZ0 / SN_f are kept: the axis comes out relative to them, which is
    all the predictions need. The SRz axis offsets are taken from `model`.
    """
    if len({round(m.srn, 3) for m in positions}) < 2:
        raise ValueError("Need positions at two different SRn.")
    c = model.config

    def residuals(x):
        cfg = replace(c, srn_axis_u=x[2], srn_axis_v=x[3])
        mod = StageModel(cfg, model.plate)
        out = []
        for m in positions:
            p = mod.plate_to_lab(m, x[0], x[1], w)
            out += [p[0], p[2]]
        return np.array(out)

    x0 = np.array([c.st0 - positions[0].st, c.sz0 - positions[0].sz, c.srn_axis_u, c.srn_axis_v])
    r0 = residuals(x0)
    jac = np.column_stack([residuals(x0 + e) - r0 for e in np.eye(4)])  # exact: the model is affine in x
    x = x0 - np.linalg.lstsq(jac, r0, rcond=None)[0]
    cfg = replace(c, srn_axis_u=float(x[2]), srn_axis_v=float(x[3]))
    res = residuals(x).reshape(-1, 2)
    return AxisFit(cfg, (float(x[0]), float(x[1])), [tuple(map(float, r)) for r in res],
                   float(np.hypot(x[0] - x[2], x[1] - x[3])))


__all__ = [
    "AnalyzerGeometry", "AxisFit", "RotationCandidate", "fit_srn_axis", "Relocation", "SLIT_ORIENTATIONS", "align_direction",
    "analyzer_angles", "emission_in_plate", "emission_lab", "focus_distance", "onto_line", "relocate", "to_center", "wrap180",
]
