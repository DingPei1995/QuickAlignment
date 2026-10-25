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
    length (its thickness); `height` (square only, 0: as wide as it is) makes
    it a rectangle, `height` tall, e.g. a narrow upright shield; `offset` shifts the
    body across the axis horizontally (mm, + towards the analyzer side), e.g. a
    thin arm beside the beam (a square body with a small `tip_radius`, half its
    thickness, and a long `length`). Optic bodies with
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
    height: float = 0.0
    offset: float = 0.0
    group: str = ""  # the assembly it belongs to (one working distance, moved as one); "": itself

    @property
    def assembly(self) -> str:
        return self.group or self.name

    @property
    def extra_height(self) -> float:
        """How much farther the (square) body reaches vertically than horizontally, from the axis."""
        return self.height / 2 - self.tip_radius if self.square and self.height > 0 else 0.0

    def radius_at(self, s: float) -> float:
        """Outer radius at `s` mm from the focus point (s >= distance)."""
        return self.tip_radius + (s - self.distance) * math.tan(math.radians(self.half_angle))


@dataclass(frozen=True)
class SheetBody:
    """Thin bent sheet standing upright at the beam (the OSA shield).

    Its top view is the polyline `points` of (along, across) in mm: along =
    upstream from where the sheet crosses the beam, which is `distance` mm
    from its focus point; across = from the beam, + towards the analyzer side
    (as SolidBody.offset). `thickness` across the sheet, `height` vertical,
    centred on the beam. `moves` as for SolidBody.
    """

    name: str
    distance: float
    points: tuple[tuple[float, float], ...]
    thickness: float = 0.2
    height: float = 20.0
    moves: bool = True
    group: str = ""

    @property
    def assembly(self) -> str:
        return self.group or self.name

    @property
    def length(self) -> float:
        """How far the sheet reaches upstream behind `distance`."""
        return max(a for a, _ in self.points)

    @property
    def tip_radius(self) -> float:
        """Largest distance from the beam (top view)."""
        return max(abs(x) for _, x in self.points)

    def segments(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """((s, across), (s, across)) of each straight piece, s from the focus point."""
        pts = [(self.distance + a, x) for a, x in self.points]
        return list(zip(pts[:-1], pts[1:]))


# MBS A1: front face 30 mm from the focal plane (beamline). The front opening has to pass the ±15° lens acceptance
# (r >= 30 tan 15° = 8 mm), so the outer radius is taken as 10 mm; the 35° cone angle is an estimate.
ANALYZER_A1 = SolidBody("analyzer (MBS A1)", distance=30.0, tip_radius=10.0, half_angle=35.0, length=150.0)

# The working distances can be entered in the Stage & Optics tab.
# Zone plate and OSA: thin plates across the beam. Zone plate (10 × 10 mm, 0.5 mm: placeholder): working
# distance 26.613 mm at 100 eV (beamline data); the focal length f = D dr / lambda grows with the photon energy, so at
# 95 eV it is 26.613 * 95 / 100 = 25.28 mm. OSA: the copper shield just in front of the plate, estimated on the
# design view at 100 eV (no scale: plate and zone plate distance as references, 1.3 ... 5.4 mm): 3.5 mm before the
# focus where its tab crosses the beam; not moved when the zone plate refocuses (so the same at 95 eV); the main
# limit. Top view from a photo of the shield in use (four pieces, three bends; lengths estimated, no scale), from the
# sample side: (1) the shortest piece, parallel to the plate surface, about 1.7 mm in front of it; (2) parallel to
# the zone plate, across the beam (with the aperture), the beam through its middle, 2.3 mm long;
# (3) bent upstream on the analyzer side, 20° off the beam axis, so that it stays out of the analyzer acceptance
# cone (30° from the beam axis seen from the focus); (4) bent again, 15° off the beam axis. 0.2 mm thick, 20 mm tall
# (estimates).
# Capillary (Sigray, 5 µm spot): working distance 10 mm (beamline). Shape from the design top and side views of the
# capillary, sizes from the chamber top view (scale from the plate, 18 × 5 mm there: 4.4 px/mm, ±10 %). From the
# focus: a round nose 3.7 mm wide, 0.7 mm long, front at 10 mm; the head, chamfered on both sides from 5.4 mm wide at
# 10.7 mm to 10 mm wide at 14.2 mm; the body, 10 mm wide and 8 mm tall, to 21.1 mm; a ring 6.8 mm wide, 2.6 mm long.
# The post and base plate below it (about 20 mm under the beam) are out of reach of the plate and not modelled.
# One assembly: a single working distance (its front), all parts move together.
# At 45° incidence a front face of (half) width r at distance d from the focus clears the surface only if
# r + margin < d - margin, and a cone only if its half angle is below the angle between beam and surface.
DEFAULT_OPTIC_BODIES = {
    "zone plate + OSA": (
        SheetBody("OSA", distance=3.5, points=((0.71, -1.86), (0.0, -1.15), (0.0, 1.15), (4.13, 2.65), (6.74, 3.35)),
                  thickness=0.2, height=20.0, moves=False),
        SolidBody("zone plate", distance=25.28, tip_radius=5.0, length=0.5, square=True),
    ),
    "capillary": (
        SolidBody("capillary nose", distance=10.0, tip_radius=1.85, length=0.7, group="capillary"),
        SolidBody("capillary head", distance=10.7, tip_radius=2.7, half_angle=33.0, length=3.5, square=True,
                  group="capillary"),
        SolidBody("capillary body", distance=14.2, tip_radius=5.0, length=6.9, square=True, height=8.0,
                  group="capillary"),
        SolidBody("capillary ring", distance=21.1, tip_radius=3.4, length=2.6, group="capillary"),
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
    optics: tuple[SolidBody | SheetBody, ...] = DEFAULT_OPTIC_BODIES["zone plate + OSA"]
    margin: float = DEFAULT_MARGIN

    def to_dict(self) -> dict:
        return {"analyzer": asdict(self.analyzer), "optics": [asdict(b) for b in self.optics], "margin": self.margin}

    @classmethod
    def from_dict(cls, data: dict, optic_type: str = "zone plate + OSA") -> CollisionGeometry:
        """From a configuration's "collision" entry; missing parts take the defaults for the optic."""
        if not isinstance(data, dict):
            raise ValueError("collision: expected a JSON object.")
        base = default_geometry(optic_type)

        def body(raw) -> SolidBody | SheetBody:
            if not isinstance(raw, dict):
                raise ValueError("collision: every body must be a JSON object.")
            values = {"name": str(raw.get("name", "body"))}
            if "group" in raw:
                values["group"] = str(raw["group"])
            if "points" in raw:  # a bent sheet
                try:
                    points = tuple((float(a), float(x)) for a, x in raw["points"])
                    numbers = [float(raw.get(k, d)) for k, d in (("distance", 0.0), ("thickness", 0.2),
                                                                 ("height", 20.0))]
                except (TypeError, ValueError):
                    raise ValueError(f"collision: {values['name']}: points must be [along, across] pairs.") from None
                if len(points) < 2 or not all(map(math.isfinite, [v for p in points for v in p] + numbers)) \
                        or min(numbers) < 0:
                    raise ValueError(f"collision: {values['name']}: not a valid sheet.")
                return SheetBody(values["name"], numbers[0], points, numbers[1], numbers[2],
                                 bool(raw.get("moves", True)), values.get("group", ""))
            for key in ("moves", "square"):
                if key in raw:
                    values[key] = bool(raw[key])
            for key in ("distance", "tip_radius", "half_angle", "length", "height", "offset"):
                if key in raw:
                    v = float(raw[key])
                    if not math.isfinite(v) or (v < 0 and key != "offset") or (key == "half_angle" and v >= 90):
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
        self.origin = self.origin + self.body.offset * side  # sides[0] points to the analyzer side of the beam
        return self

    def _across(self, rel: np.ndarray, s: np.ndarray) -> np.ndarray:
        """Distance from the axis: Euclidean (round) or the larger side component (square; the vertical one less
        the extra height of a rectangle)."""
        if self.body.square:
            c = np.abs(rel @ self.sides.T)
            return np.maximum(c[..., 0], c[..., 1] - self.body.extra_height)
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


@dataclass
class _PlacedSheet:
    """A SheetBody in the lab: one box per straight piece."""

    body: SheetBody
    origin: np.ndarray
    axis: np.ndarray
    boxes: list = field(init=False)  # (centre, unit vectors (3, 3), half sizes (3,))
    margin: float = field(init=False)

    def grow(self, margin: float) -> _PlacedSheet:
        self.margin = margin
        side = np.cross(self.axis, Z_HAT)
        side = side / np.linalg.norm(side)  # towards the analyzer side of the beam
        self.boxes = []
        for (s0, x0), (s1, x1) in self.body.segments():
            p0 = self.origin + s0 * self.axis + x0 * side
            p1 = self.origin + s1 * self.axis + x1 * side
            u = p1 - p0
            n = np.linalg.norm(u)
            if n < 1e-9:
                continue
            u = u / n
            units = np.array([u, np.cross(Z_HAT, u), Z_HAT])
            half = np.array([n / 2 + margin, self.body.thickness / 2 + margin, self.body.height / 2 + margin])
            self.boxes.append(((p0 + p1) / 2, units, half))
        return self

    def _excess(self, p: np.ndarray) -> np.ndarray:
        """(boxes, ...) of the largest excess over the half sizes: <= 0 inside, else a lower bound of the distance."""
        return np.array([(np.abs((p - c) @ units.T) - half).max(axis=-1) for c, units, half in self.boxes])

    def inside(self, p: np.ndarray) -> np.ndarray:
        return (self._excess(p) <= 0).any(axis=0)

    def clearance(self, p: np.ndarray) -> np.ndarray:
        return self._excess(p).min(axis=0)

    def surface(self) -> np.ndarray:
        """Points on the (not grown) sheet, for the acceptance check."""
        out = []
        for c, units, half in self.boxes:
            h = half - self.margin
            for a in np.linspace(-1, 1, 15):
                for t in (-1, 1):
                    for z in np.linspace(-1, 1, 9):
                        out.append(c + units.T @ (np.array([a, t, z]) * h))
        return np.array(out)


def placed_bodies(geo: CollisionGeometry, focus_ys, fixed_y: float = 0.0) -> list:
    """The analyzer, the fixed optic bodies (at the reference focus `fixed_y` along the beam) and the moving
    ones for every optic focus position in focus_ys."""
    grow = geo.margin + SAMPLING_ALLOWANCE

    def place(b, y):
        return (_PlacedSheet if isinstance(b, SheetBody) else _Placed)(b, y * Y_HAT, -Y_HAT).grow(grow)

    out = [_Placed(geo.analyzer, np.zeros(3), -N_HAT).grow(grow)]
    out += [place(b, fixed_y) for b in geo.optics if not b.moves]
    for y in focus_ys:
        out += [place(b, float(y)) for b in geo.optics if b.moves]
    return out


def _body_surface(b: _Placed, n_s: int = 12, n_around: int = 48) -> np.ndarray:
    """Points on the outer surface of a placed (not grown) body."""
    s = np.linspace(b.body.distance, b.body.distance + b.body.length, n_s)
    r = np.array([b.body.radius_at(x) for x in s])
    t = np.linspace(0, 2 * np.pi, n_around, endpoint=False)
    across = np.column_stack([np.cos(t), np.sin(t)])
    if b.body.square:  # the square outline: scale the circle onto it
        across = across / np.abs(across).max(axis=1, keepdims=True)
    pts = (s[:, None, None] * b.axis + r[:, None, None] * across[None, :, :1] * b.sides[0]
           + (r[:, None, None] + b.body.extra_height) * across[None, :, 1:] * b.sides[1])
    return b.origin + pts.reshape(-1, 3)


def in_acceptance(geo: CollisionGeometry, focus_ys, fixed_y: float = 0.0,
                  half_angle: float = ACCEPTANCE_HALF_ANGLE) -> list[str]:
    """Optic solids reaching into the analyzer acceptance cone (from the analyzer focus, `half_angle` about the
    analyzer axis, up to the analyzer front): they would shadow the electrons. Empty: none."""
    cos_max = math.cos(math.radians(half_angle))
    names = []
    for b in placed_bodies(geo, focus_ys, fixed_y)[1:]:
        p = b.surface() if isinstance(b, _PlacedSheet) else _body_surface(b)
        d = np.linalg.norm(p, axis=1)
        along = p @ -N_HAT
        inside = (along > 0) & (along <= geo.analyzer.distance) & (along >= cos_max * d)
        if inside.any() and b.body.assembly not in names:
            names.append(b.body.assembly)
    return names


def collisions(model: StageModel, m: MotorPositions, layout: SampleLayout, geo: CollisionGeometry,
               focus_ys, fixed_y: float = 0.0) -> list[str]:
    """Names of the bodies the plate is in (with the margin) at m; empty: no collision.

    focus_ys: optic focus positions along the beam (moving bodies); fixed_y: focus at the
    configuration's optics reference (fixed bodies, the OSA)."""
    pts = model.plate_to_lab_many(m, surface_points(layout))
    names = []
    for b in placed_bodies(geo, focus_ys, fixed_y):
        if b.body.assembly not in names and b.inside(pts).any():
            names.append(b.body.assembly)
    return names


@dataclass
class Limit:
    lo: float
    hi: float
    lo_by: str  # what sets the limit: a body (its assembly) or "travel"
    hi_by: str


def _first_hit(pts: np.ndarray, e: np.ndarray, bodies: list[_Placed], limit: float, step: float,
               tol: float) -> tuple[float, str]:
    """Largest free move (mm, >= 0) of the points along e, up to `limit`, and what stops it.

    Each point moves by at most the move, so the plate can move by its smallest clearance
    without touching a body; within `step` of a body it goes on in steps of `step`."""
    best, by = max(limit, 0.0), "travel"
    for b in bodies:
        # a point farther from the body than the whole move can never reach it
        p = pts[b.clearance(pts) <= best]
        moved = 0.0
        hit = None
        while moved < best and len(p):
            c = b.clearance(p + moved * e)
            gap = float(c.min())
            if gap >= step:
                moved = min(moved + gap, best)
                continue
            # close to the body: the next steps at once, for the points they can bring into it
            nxt = np.minimum(moved + step * np.arange(1, 26), best)
            near = p[c <= nxt[-1] - moved]
            inside = b.inside(near[None, :, :] + nxt[:, None, None] * e).any(axis=1)
            if inside.any():
                k = int(np.argmax(inside))
                hit = (nxt[k - 1] if k else moved, nxt[k])
                break
            moved = float(nxt[-1])
        if hit is not None:
            lo, hi = hit  # free at lo, hit at hi
            while hi - lo > tol:
                mid = (lo + hi) / 2
                if b.inside(p + mid * e).any():
                    hi = mid
                else:
                    lo = mid
            best, by = lo, b.body.assembly
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
    "ACCEPTANCE_HALF_ANGLE", "ANALYZER_A1", "SAMPLING_ALLOWANCE", "SheetBody", "in_acceptance", "CollisionGeometry", "SolidBody", "DEFAULT_OPTIC_BODIES", "Limit", "MOTOR_DIRECTIONS",
    "collisions", "default_geometry", "motor_limits", "placed_bodies", "surface_points",
]
