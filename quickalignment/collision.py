"""Anti-collision check: the plate (with its samples) against the analyzer nose and the focusing optic.

Simple solid models, in the lab frame of stage.py (origin = analyzer focus,
+y along the beam):

* analyzer (MBS A1 lens): a truncated cone on the analyzer axis (-n, the
  normal of the analyzer focal plane through the focus); its front face is
  `distance` = 30 mm from the focus, the cone widens away from it;
* focusing optic, on the beam axis upstream of the optic focus. Zone plate:
  two thin square plates across the beam, the zone plate, which moves with the
  zone plate motor (upstream of the focus for the optic position in use), and
  the OSA, closer to the sample and the main limit, which is not moved when
  the zone plate refocuses: it stays upstream of the focus at the
  configuration's optics reference (≈ the analyzer focus). Capillary: a
  truncated cone, moving with the capillary motor.

The plate side is the plate, tab, riser, contact block, screws and samples as
boxes (`SampleLayout.boxes`), sampled on their faces. A point inside a body
(grown by `margin` and by the sampling allowance) is a collision. The sample holder below the plate and the
cryostat are not modelled.

`motor_limits` gives, for the current positions, the interval of each of ST,
SN, SZ (the others kept) that is free of collision and within the travel range.
SN moves along +n, away from the analyzer and downstream, so it is limited from
below only; for a flat plate ST and SZ slide the surface in its own plane and
only matter when SRz tilts the plate or something stands out of the surface.

The default dimensions are estimates (marked below) until checked on the
drawings; a configuration file can give its own under "collision".
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .geometry import SampleLayout
from .stage import N_HAT, T_HAT, Y_HAT, Z_HAT, MotorPositions, StageModel

MOTOR_DIRECTIONS = {"st": T_HAT, "sn": N_HAT, "sz": Z_HAT}  # lab direction per mm of motor


@dataclass(frozen=True)
class SolidBody:
    """Truncated cone, or square pyramid / thin plate, on an axis pointing away from its focus point.

    The front face (towards the sample) is `distance` mm from the focus point,
    with outer radius `tip_radius` (`square`: half width of a square across the
    axis, sides horizontal and vertical); the outer wall opens by `half_angle`
    (0: cylinder, or plate) over `length` mm behind the front face. A thin plate
    across the beam (zone plate, OSA) is square, half_angle 0 and a short
    length (its thickness). Optic bodies with
    `moves` follow the optic motor (their focus point is the optic focus);
    the others (the OSA, not moved when the zone plate refocuses) stay where
    they are for the configuration's optics reference.
    """

    name: str
    distance: float
    tip_radius: float
    half_angle: float = 0.0
    length: float = 50.0
    moves: bool = True
    square: bool = False

    def radius_at(self, s: float) -> float:
        """Outer radius at `s` mm from the focus point (s >= distance)."""
        return self.tip_radius + (s - self.distance) * math.tan(math.radians(self.half_angle))


# MBS A1: front face 30 mm from the focal plane (beamline). The front opening has to pass the ±15° lens acceptance
# (r >= 30 tan 15° = 8 mm), so the outer radius is taken as 10 mm; the 35° cone angle is an estimate.
ANALYZER_A1 = SolidBody("analyzer (MBS A1)", distance=30.0, tip_radius=10.0, half_angle=35.0, length=150.0)

# PLACEHOLDERS until measured on the beamline; the working distances can be entered in the Stage & Optics tab.
# Zone plate and OSA: thin square plates across the beam, farther from the sample than the capillary tip. Zone plate
# focal length f = D dr / lambda (lambda = 13.05 nm at 95 eV): D = 1.5 mm, outermost zone dr = 250 nm (a typical EUV
# zone plate for a ~1 µm spot) give f ≈ 29 mm. The OSA (diameter D/2) must pass the whole first-order cone, so it is
# at most f/2 ≈ 14 mm from the focus; it is closer to the sample than the zone plate, the main limit, and is not moved
# when the zone plate refocuses.
# Capillary (Sigray, 5 µm spot; Sigray publishes no single working distance, 2 mm to 10 cm): measured on the ANTARES
# design top view (scale from the plate, 18 mm wide and 5 mm thick there: 11 px/mm, ±5 %). From the focus: a square
# front plate 17.8 mm wide, 3 mm thick, from 17.4 mm; a conical nose, radius 8.2 mm at 17.4 mm opening by 16° to
# 10.6 mm at 25.6 mm; the cylindrical body, radius 11 mm, from 25.6 to 74 mm. Its front edge is 27° from the beam
# axis, just outside the ±15° analyzer acceptance (30°). The box on the body (40 to 65 mm, on the side away from the
# analyzer) is not modelled.
# At 45° incidence a front face of (half) width r at distance d from the focus clears the surface only if
# r + margin < d - margin, and a cone only if its half angle is below the angle between beam and surface.
DEFAULT_OPTIC_BODIES = {
    "zone plate + OSA": (
        SolidBody("OSA", distance=14.0, tip_radius=5.0, length=0.5, moves=False, square=True),
        SolidBody("zone plate", distance=29.0, tip_radius=5.0, length=0.5, square=True),
    ),
    "capillary": (
        SolidBody("capillary front plate", distance=17.4, tip_radius=8.9, length=3.0, square=True),
        SolidBody("capillary nose", distance=17.4, tip_radius=8.2, half_angle=16.0, length=8.2),
        SolidBody("capillary body", distance=25.6, tip_radius=11.0, length=48.4),
    ),
}
ACCEPTANCE_HALF_ANGLE = 15.0  # deg: MBS A1 lens acceptance about the analyzer axis (electrons from the focus)
DEFAULT_MARGIN = 0.1  # mm added around every body
SAMPLE_SPACING = 0.25  # mm between the points on the plate faces
# every point of a face is within SAMPLE_SPACING / sqrt2 of a sampled point: the bodies are grown by this as well,
# so a body cannot reach between the sampled points unnoticed (the limits are that much on the safe side)
SAMPLING_ALLOWANCE = SAMPLE_SPACING / math.sqrt(2)


@dataclass(frozen=True)
class CollisionGeometry:
    analyzer: SolidBody = ANALYZER_A1
    optics: tuple[SolidBody, ...] = DEFAULT_OPTIC_BODIES["zone plate + OSA"]
    margin: float = DEFAULT_MARGIN

    def to_dict(self) -> dict:
        return {"analyzer": asdict(self.analyzer), "optics": [asdict(b) for b in self.optics], "margin": self.margin}

    @classmethod
    def from_dict(cls, data: dict, optic_type: str = "zone plate + OSA") -> CollisionGeometry:
        """From a configuration's "collision" entry; missing parts take the defaults for the optic."""
        if not isinstance(data, dict):
            raise ValueError("collision: expected a JSON object.")
        base = default_geometry(optic_type)

        def body(raw) -> SolidBody:
            if not isinstance(raw, dict):
                raise ValueError("collision: every body must be a JSON object.")
            values = {"name": str(raw.get("name", "body"))}
            for key in ("moves", "square"):
                if key in raw:
                    values[key] = bool(raw[key])
            for key in ("distance", "tip_radius", "half_angle", "length"):
                if key in raw:
                    v = float(raw[key])
                    if not math.isfinite(v) or v < 0 or (key == "half_angle" and v >= 90):
                        raise ValueError(f"collision: {values['name']}.{key} = {raw[key]!r} is not valid.")
                    values[key] = v
            return SolidBody(**values)

        analyzer = body(data["analyzer"]) if "analyzer" in data else base.analyzer
        optics = tuple(body(b) for b in data["optics"]) if "optics" in data else base.optics
        margin = float(data.get("margin", base.margin))
        if not math.isfinite(margin) or margin < 0:
            raise ValueError("collision: margin must be >= 0.")
        return cls(analyzer, optics, margin)


def default_geometry(optic_type: str) -> CollisionGeometry:
    key = "capillary" if "capillary" in optic_type else "zone plate + OSA"
    return CollisionGeometry(optics=DEFAULT_OPTIC_BODIES[key])


# -- plate points -------------------------------------------------------------------------
def _grid(a0: float, a1: float, b0: float, b1: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    a = np.linspace(a0, a1, max(int(math.ceil((a1 - a0) / h)) + 1, 2))
    b = np.linspace(b0, b1, max(int(math.ceil((b1 - b0) / h)) + 1, 2))
    aa, bb = np.meshgrid(a, b)
    return aa.ravel(), bb.ravel()


def surface_points(layout: SampleLayout, spacing: float = SAMPLE_SPACING) -> np.ndarray:
    """(N, 3) plate points (u, v, w) on the faces of every solid part of the plate."""
    out = []
    for u0, v0, u1, v1, w0, w1, _ in layout.boxes():
        for w in (w0, w1):  # bottom and top faces
            a, b = _grid(u0, u1, v0, v1, spacing)
            out.append(np.column_stack([a, b, np.full_like(a, w)]))
        for u in (u0, u1):
            a, b = _grid(v0, v1, w0, w1, spacing)
            out.append(np.column_stack([np.full_like(a, u), a, b]))
        for v in (v0, v1):
            a, b = _grid(u0, u1, w0, w1, spacing)
            out.append(np.column_stack([a, np.full_like(a, v), b]))
    return np.vstack(out)


# -- bodies in the lab ----------------------------------------------------------------------
@dataclass
class _Placed:
    body: SolidBody
    origin: np.ndarray  # focus point of the body
    axis: np.ndarray  # unit, from the focus point into the body
    distance: float = field(init=False)  # grown by the margin
    end: float = field(init=False)
    r0: float = field(init=False)
    k: float = field(init=False)
    sides: np.ndarray = field(init=False)  # (2, 3): across the axis, horizontal and vertical (square bodies)

    def grow(self, margin: float) -> _Placed:
        self.distance = max(self.body.distance - margin, 0.0)
        self.end = self.body.distance + self.body.length + margin
        self.r0 = self.body.tip_radius + margin
        self.k = math.tan(math.radians(self.body.half_angle))
        side = np.cross(self.axis, Z_HAT)
        side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-9 else np.array([1.0, 0.0, 0.0])
        self.sides = np.array([side, np.cross(side, self.axis)])
        return self

    def _across(self, rel: np.ndarray, s: np.ndarray) -> np.ndarray:
        """Distance from the axis: Euclidean (round) or the larger side component (square)."""
        if self.body.square:
            return np.abs(rel @ self.sides.T).max(axis=-1)
        return np.sqrt(np.maximum(np.einsum("...i,...i->...", rel, rel) - s * s, 0.0))

    def inside(self, p: np.ndarray) -> np.ndarray:
        """Boolean mask of the points p (..., 3) inside the grown body."""
        rel = p - self.origin
        s = rel @ self.axis
        r = self.r0 + (s - self.distance) * self.k
        return (s >= self.distance) & (s <= self.end) & (self._across(rel, s) <= r)

    def clearance(self, p: np.ndarray) -> np.ndarray:
        """Lower bound of the distance of each point p (N, 3) to the grown body (<= 0: maybe inside).

        The body is convex and lies within the slab between its two faces and on the inner side of
        the plane touching its wall along the generator (or the side) facing the point; the largest
        distance to these is never more than the distance to the body."""
        rel = p - self.origin
        s = rel @ self.axis
        wall = (self._across(rel, s) - self.r0 - (s - self.distance) * self.k) / math.sqrt(1 + self.k * self.k)
        return np.maximum.reduce([self.distance - s, s - self.end, wall])


def placed_bodies(geo: CollisionGeometry, focus_ys, fixed_y: float = 0.0) -> list[_Placed]:
    """The analyzer, the fixed optic bodies (at the reference focus `fixed_y` along the beam) and the moving
    ones for every optic focus position in focus_ys."""
    grow = geo.margin + SAMPLING_ALLOWANCE
    out = [_Placed(geo.analyzer, np.zeros(3), -N_HAT).grow(grow)]
    out += [_Placed(b, fixed_y * Y_HAT, -Y_HAT).grow(grow) for b in geo.optics if not b.moves]
    for y in focus_ys:
        out += [_Placed(b, float(y) * Y_HAT, -Y_HAT).grow(grow) for b in geo.optics if b.moves]
    return out


def _body_surface(b: _Placed, n_s: int = 12, n_around: int = 48) -> np.ndarray:
    """Points on the outer surface of a placed (not grown) body."""
    s = np.linspace(b.body.distance, b.body.distance + b.body.length, n_s)
    r = np.array([b.body.radius_at(x) for x in s])
    t = np.linspace(0, 2 * np.pi, n_around, endpoint=False)
    across = np.column_stack([np.cos(t), np.sin(t)])
    if b.body.square:  # the square outline: scale the circle onto it
        across = across / np.abs(across).max(axis=1, keepdims=True)
    pts = (s[:, None, None] * b.axis + r[:, None, None] * (across[None, :, :1] * b.sides[0]
                                                           + across[None, :, 1:] * b.sides[1]))
    return b.origin + pts.reshape(-1, 3)


def in_acceptance(geo: CollisionGeometry, focus_ys, fixed_y: float = 0.0,
                  half_angle: float = ACCEPTANCE_HALF_ANGLE) -> list[str]:
    """Optic solids reaching into the analyzer acceptance cone (from the analyzer focus, `half_angle` about the
    analyzer axis, up to the analyzer front): they would shadow the electrons. Empty: none."""
    cos_max = math.cos(math.radians(half_angle))
    names = []
    for b in placed_bodies(geo, focus_ys, fixed_y)[1:]:
        p = _body_surface(b)
        d = np.linalg.norm(p, axis=1)
        along = p @ -N_HAT
        inside = (along > 0) & (along <= geo.analyzer.distance) & (along >= cos_max * d)
        if inside.any() and b.body.name not in names:
            names.append(b.body.name)
    return names


def collisions(model: StageModel, m: MotorPositions, layout: SampleLayout, geo: CollisionGeometry,
               focus_ys, fixed_y: float = 0.0) -> list[str]:
    """Names of the bodies the plate is in (with the margin) at m; empty: no collision.

    focus_ys: optic focus positions along the beam (moving bodies); fixed_y: focus at the
    configuration's optics reference (fixed bodies, the OSA)."""
    pts = model.plate_to_lab_many(m, surface_points(layout))
    names = []
    for b in placed_bodies(geo, focus_ys, fixed_y):
        if b.body.name not in names and b.inside(pts).any():
            names.append(b.body.name)
    return names


@dataclass
class Limit:
    lo: float
    hi: float
    lo_by: str  # what sets the limit: a body name or "travel"
    hi_by: str


def _first_hit(pts: np.ndarray, e: np.ndarray, bodies: list[_Placed], limit: float, step: float,
               tol: float) -> tuple[float, str]:
    """Largest free move (mm, >= 0) of the points along e, up to `limit`, and what stops it.

    Each point moves by at most the move, so the plate can move by its smallest clearance
    without touching a body; within `step` of a body it goes on in steps of `step`."""
    best, by = max(limit, 0.0), "travel"
    for b in bodies:
        moved = 0.0
        while moved < best:
            gap = float(b.clearance(pts + moved * e).min())
            nxt = min(moved + max(gap, step), best)
            if gap >= step or not b.inside(pts + nxt * e).any():
                if nxt >= best:
                    break
                moved = nxt
                continue
            lo, hi = moved, nxt  # free at lo, hit at hi
            while hi - lo > tol:
                mid = (lo + hi) / 2
                if b.inside(pts + mid * e).any():
                    hi = mid
                else:
                    lo = mid
            best, by = lo, b.body.name
            break
    return best, by


def motor_limits(model: StageModel, m: MotorPositions, layout: SampleLayout, geo: CollisionGeometry, focus_ys,
                 travel: dict[str, tuple[float, float]], fixed_y: float = 0.0, step: float = 0.02,
                 tol: float = 0.002) -> dict[str, Limit] | None:
    """Collision-free range of ST, SN, SZ around m (one motor moved, the others kept), within `travel`.

    None if the plate already collides at m. The optic stays at the given focus
    position(s) while the motor moves (see `collisions` for focus_ys, fixed_y).
    """
    pts = model.plate_to_lab_many(m, surface_points(layout))
    bodies = placed_bodies(geo, focus_ys, fixed_y)
    if any(b.inside(pts).any() for b in bodies):
        return None
    out = {}
    for name, (t_lo, t_hi) in travel.items():
        x0, e = getattr(m, name), MOTOR_DIRECTIONS[name]
        up, up_by = _first_hit(pts, e, bodies, t_hi - x0, step, tol)
        down, down_by = _first_hit(pts, -e, bodies, x0 - t_lo, step, tol)
        out[name] = Limit(x0 - down, x0 + up, down_by, up_by)
    return out


__all__ = [
    "ACCEPTANCE_HALF_ANGLE", "ANALYZER_A1", "SAMPLING_ALLOWANCE", "in_acceptance", "CollisionGeometry", "SolidBody", "DEFAULT_OPTIC_BODIES", "Limit", "MOTOR_DIRECTIONS",
    "collisions", "default_geometry", "motor_limits", "placed_bodies", "surface_points",
]
