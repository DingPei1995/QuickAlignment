"""Gold-frame calibration: the stage constants from SPEM intensity lines over the gold reference frame.

The reference sample is a square gold frame (2 x 2 mm outside, 1 x 1 mm hole)
glued on the riser of the standard plate, in principle at its centre. Only the
total photoemission intensity is used (no angle or energy resolution).

SZ is the only fast motor (fly scans), ST, SRn and SRz are slow: every
measurement is an SZ line, the slow motors only move between lines. Turning
the frame by 45 deg with SRn makes its edges diagonal (a diamond): where an SZ
line crosses them moves 1:1 with where the line passes across the frame, so
the horizontal position (ST0, the SRn axis, the SRz axis) is read on the fast
axis too. The survey (`survey_plan`):

A. SRn ref, SRz 0, a few ST: SZ0, in-plane rotation;
B. SRn ref +- 45 (diamond), SRz 0, a few ST: ST0, SRn axis, ST scale;
C. diamond, SRz turned (e.g. -25 ... +10), two ST each: SRz axis offsets
   (along ST, depth) and the tilt of the gold face.

An ST x SZ overview map (coarse ST steps) and an SZ x SRn sweep may be added:
`fit_global` fits every edge of every line of every scan at once (plus, as an
option, SN focus points measured at other SRz), so no constant is passed from
one step to the next.

Simulation: the beam (lab y axis, or offset from it) is traced onto the frame
with the stage kinematics of `StageModel`; the gold top face (height, tilts),
its side walls (which shadow the riser behind them) and the riser give the
material; the beam spot grows out of the optic focus, and the analyzer only
sees what lies near its focus (Gaussian acceptance). Motor scales are applied
around a reference position (the frame centre).

Fits: gold edges are taken from every line (where the gold top face begins and
ends, which is where the beam crosses an edge, whatever the analyzer sees),
then fitted with the same geometry. The analyzer acceptance only weights the
intensity: it does not move a sharp edge.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from .geometry import STANDARD_PLATE, PlateGeometry
from .stage import N_HAT, T_HAT, Z_HAT, MotorPositions, StageConfig, StageModel

X_HAT = np.array([1.0, 0.0, 0.0])
Y_HAT = np.array([0.0, 1.0, 0.0])
FWHM_TO_SIGMA = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))

# what each scan steps and scans: (outer axis = map x, scanned axis = map y)
KINDS = {
    "st_sz": ("ST (mm)", "SZ (mm)"),
    "srn_sz": ("SRn (deg)", "SZ (mm)"),
    "sz_lines": ("ST (mm)", "SZ (mm)"),  # SZ lines at given SRn / SRz (the survey), ST stepped
    "lines": ("line", "scanned (mm)"),
}
MOTORS = ("st", "sn", "sz", "srn", "srz", "pix", "piy")


@dataclass
class GoldFrame:
    """The gold frame as mounted: nominal size, and where it really is on the plate.

    (u, v): centre in the plate frame (mm, front view, tab up); rotation: in-plane
    (deg, counter-clockwise in the front view); height: top face above the riser
    top (gold + glue, mm); tilt_u / tilt_v: slope of the top face (deg) along u
    (the face turned about the v axis) and along v (about the u axis).
    """

    outer: float = 2.0
    inner: float = 1.0
    height: float = 0.05
    u: float = 0.0
    v: float = 0.0
    rotation: float = 0.0
    tilt_u: float = 0.0
    tilt_v: float = 0.0

    def to_frame(self, u, v):
        """Plate (u, v) -> frame coordinates (along the frame's own edges, from its centre)."""
        a = math.radians(self.rotation)
        du, dv = np.asarray(u) - self.u, np.asarray(v) - self.v
        return math.cos(a) * du + math.sin(a) * dv, -math.sin(a) * du + math.cos(a) * dv

    def is_gold(self, fu, fv):
        r = np.maximum(np.abs(fu), np.abs(fv))
        return (r <= self.outer / 2) & (r >= self.inner / 2)


@dataclass
class Instrument:
    """Beam, analyzer and motor scales.

    Lab frame of `StageModel`: origin = analyzer focus, beam along +y.
    beam_x / beam_z: the beam line passes (beam_x, ., beam_z) instead of the
    analyzer focus (mm). focus_y: optic focus along the beam. The beam spot
    FWHM grows as sqrt(fwhm^2 + (2 NA dy)^2) at dy from the optic focus.
    The analyzer accepts a Gaussian region around its focus: FWHM across its
    axis, horizontally (along ST) and vertically, and along its axis.
    st_scale / sz_scale: real motion / read-back, around (scale_st_ref, scale_sz_ref).
    """

    beam_fwhm: float = 0.002
    beam_na: float = 0.005
    focus_y: float = 0.0
    beam_x: float = 0.0
    beam_z: float = 0.0
    analyzer_fwhm_h: float = 0.5
    analyzer_fwhm_v: float = 0.5
    analyzer_fwhm_axial: float = 3.0
    st_scale: float = 1.0
    sz_scale: float = 1.0
    scale_st_ref: float = 0.0
    scale_sz_ref: float = 40.0
    gold: float = 1.0
    riser: float = 0.3  # Ta riser (and the hole floor)
    wall: float = 0.05  # side wall of the frame hit by the beam (seen edge-on by the analyzer)
    counts: float = 0.0  # gold counts per pixel for Poisson noise (0: no noise)
    rays: int = 7  # rays across the beam spot
    fly: int = 5  # positions averaged over each pixel along the scanned axis (fly scan); 1: point by point

    def true_motors(self, m: MotorPositions) -> MotorPositions:
        return replace(m, st=self.scale_st_ref + self.st_scale * (m.st - self.scale_st_ref),
                       sz=self.scale_sz_ref + self.sz_scale * (m.sz - self.scale_sz_ref))


@dataclass
class Scan:
    """One map: x = outer axis (one line per value), y = scanned axis.

    For line i the motors are base[name][i] + y * slope[name][i] (all lines are
    straight in motor space). `intensity` is (len(y), len(x)) once measured or
    simulated.
    """

    kind: str
    x: np.ndarray
    y: np.ndarray
    base: dict
    slope: dict
    intensity: np.ndarray | None = None
    info: dict = field(default_factory=dict)

    def motors(self, i: int, y: float) -> MotorPositions:
        return MotorPositions(**{k: float(self.base[k][i] + y * self.slope[k][i]) for k in MOTORS})

    def motor_grid(self, name: str) -> np.ndarray:
        """(len(y), len(x)) values of one motor over the map."""
        return self.base[name][None, :] + self.y[:, None] * self.slope[name][None, :]

    def save(self, path) -> None:
        np.savez(path, kind=self.kind, x=self.x, y=self.y, intensity=self.intensity,
                 **{f"base_{k}": v for k, v in self.base.items()}, **{f"slope_{k}": v for k, v in self.slope.items()})

    @classmethod
    def load_npz(cls, path) -> Scan:
        with np.load(path, allow_pickle=False) as d:
            return cls(kind=str(d["kind"]), x=d["x"].astype(float), y=d["y"].astype(float),
                       base={k: d[f"base_{k}"].astype(float) for k in MOTORS},
                       slope={k: d[f"slope_{k}"].astype(float) for k in MOTORS},
                       intensity=d["intensity"].astype(float))


def make_scan(kind: str, x, y, fixed: MotorPositions) -> Scan:
    """A map of `kind` over x (outer, stepped) and y (scanned SZ), the other motors at `fixed`:
    st_sz and sz_lines step ST, srn_sz steps SRn."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    base = {k: np.full(n, float(getattr(fixed, k))) for k in MOTORS}
    slope = {k: np.zeros(n) for k in MOTORS}
    if kind in ("st_sz", "sz_lines"):
        base["st"], base["sz"], slope["sz"] = x.copy(), np.zeros(n), np.ones(n)
    elif kind == "srn_sz":
        base["srn"], base["sz"], slope["sz"] = x.copy(), np.zeros(n), np.ones(n)
    else:
        raise ValueError(f"unknown map kind {kind!r} (one of st_sz, srn_sz, sz_lines)")
    return Scan(kind, x, y, base, slope)


# -- the beam on the plate -----------------------------------------------------------------------
@dataclass
class Setup:
    """Everything the beam meets: stage constants, plate, frame, instrument."""

    config: StageConfig = field(default_factory=StageConfig)
    frame: GoldFrame = field(default_factory=GoldFrame)
    instrument: Instrument = field(default_factory=Instrument)
    plate: PlateGeometry = STANDARD_PLATE

    @property
    def model(self) -> StageModel:
        return StageModel(self.config, self.plate)

    @property
    def riser_w(self) -> float:
        return self.plate.total_thickness

    def gold_w(self) -> float:
        return self.riser_w + self.frame.height

    def frame_motors(self, srn: float | None = None, srz: float = 0.0, sn: float | None = None) -> MotorPositions:
        """Motors putting the frame centre on the beam at the analyzer focus (SN given: kept, ST compensating)."""
        c = self.config
        m = self.model.motors_for_target(self.frame.u, self.frame.v, self.gold_w(), c.srn_ref if srn is None else srn, srz)
        if sn is not None:
            m = replace(m, sn=sn, st=m.st - (sn - m.sn))
        return m

    def beam_in_plate(self, m: MotorPositions):
        """(P, D, X, Z): the beam line point at lab y = 0, the plate directions of lab y, x and z,
        for commanded motors m (motor scales applied). A point P + s D is at lab y = s."""
        model, inst = self.model, self.instrument
        t = inst.true_motors(m)
        p0 = np.array([inst.beam_x, 0.0, inst.beam_z])
        P = model.lab_to_plate(t, p0)
        return P, model.lab_to_plate(t, p0 + Y_HAT) - P, model.lab_to_plate(t, p0 + X_HAT) - P, \
            model.lab_to_plate(t, p0 + Z_HAT) - P

    def _gold_s(self, P, D):
        """Lab y where the beam lines P + s D meet the (tilted) gold top plane; P: (N, 3)."""
        f = self.frame
        au, av = math.tan(math.radians(f.tilt_u)), math.tan(math.radians(f.tilt_v))
        num = self.gold_w() + au * (P[..., 0] - f.u) + av * (P[..., 1] - f.v) - P[..., 2]
        return num / (D[2] - au * D[0] - av * D[1])

    def line_in_frame(self, scan: Scan, i: int):
        """Frame coordinates of the gold-top hit along line i: (F0, F1) with F(y) = F0 + y F1."""
        P0, D, _, _ = self.beam_in_plate(scan.motors(i, 0.0))
        P1, _, _, _ = self.beam_in_plate(scan.motors(i, 1.0))
        P = np.stack([P0, P1])
        H = P + self._gold_s(P, D)[:, None] * D
        fu, fv = self.frame.to_frame(H[:, 0], H[:, 1])
        F0 = np.array([fu[0], fv[0]])
        return F0, np.array([fu[1], fv[1]]) - F0

    # -- intensity ---------------------------------------------------------------------------------
    def _material(self, P, D):
        """Intensity factor of the material hit by beam lines P + s D (P: (N, 3)) and the lab y of the hit."""
        f, inst = self.frame, self.instrument
        s_gold = self._gold_s(P, D)
        H = P + s_gold[:, None] * D
        gold = f.is_gold(*f.to_frame(H[:, 0], H[:, 1]))
        s_riser = (self.riser_w - P[:, 2]) / D[2]
        # between the gold plane and the riser the beam may cross the frame's side wall
        wall = np.zeros(len(P), bool)
        for k in np.linspace(0.05, 0.95, 8):
            Q = P + (s_gold + k * (s_riser - s_gold))[:, None] * D
            wall |= f.is_gold(*f.to_frame(Q[:, 0], Q[:, 1]))
        wall &= ~gold
        value = np.where(gold, inst.gold, np.where(wall, inst.wall, inst.riser))
        return value, np.where(gold | wall, s_gold, s_riser)

    def _analyzer(self, lab):
        inst = self.instrument
        r = ((lab @ T_HAT) / inst.analyzer_fwhm_h) ** 2 + ((lab @ Z_HAT) / inst.analyzer_fwhm_v) ** 2 \
            + ((lab @ N_HAT) / inst.analyzer_fwhm_axial) ** 2
        return np.exp(-4.0 * math.log(2.0) * r)

    def simulate(self, scan: Scan, rng: np.random.Generator | None = None) -> np.ndarray:
        """Intensity map (len(y), len(x)) of the scan, also stored in scan.intensity."""
        inst = self.instrument
        rays = _ray_pattern(max(1, int(inst.rays)))
        fly = max(1, int(inst.fly))
        dy = float(np.mean(np.abs(np.diff(scan.y)))) if len(scan.y) > 1 else 0.0
        sub = (np.arange(fly) + 0.5) / fly - 0.5 if fly > 1 else np.zeros(1)
        out = np.empty((len(scan.y), len(scan.x)))
        for i in range(len(scan.x)):
            P0, D, X, Z = self.beam_in_plate(scan.motors(i, 0.0))
            P1, _, _, _ = self.beam_in_plate(scan.motors(i, 1.0))
            total = np.zeros(len(scan.y))
            for f in sub:
                P = P0 + (scan.y + f * dy)[:, None] * (P1 - P0)
                _, s = self._material(P, D)  # where the beam centre lands: spot size there
                fwhm = np.hypot(inst.beam_fwhm, 2.0 * inst.beam_na * (s - inst.focus_y))
                for ox, oz in rays:
                    dx, dz = ox * fwhm * FWHM_TO_SIGMA, oz * fwhm * FWHM_TO_SIGMA
                    Q = P + dx[:, None] * X + dz[:, None] * Z
                    value, sq = self._material(Q, D)
                    lab = np.column_stack([inst.beam_x + dx, sq, inst.beam_z + dz])
                    total += value * self._analyzer(lab)
            out[:, i] = total / (len(rays) * len(sub))
        if inst.counts > 0:
            rng = rng or np.random.default_rng(0)
            out = rng.poisson(np.clip(out, 0, None) * inst.counts) / inst.counts
        scan.intensity = out
        return out

    def spot_y(self, scan: Scan) -> np.ndarray:
        """Lab y (along the beam, from the analyzer focus) of the illuminated point over the map."""
        out = np.empty((len(scan.y), len(scan.x)))
        for i in range(len(scan.x)):
            P0, D, _, _ = self.beam_in_plate(scan.motors(i, 0.0))
            P1, _, _, _ = self.beam_in_plate(scan.motors(i, 1.0))
            out[:, i] = self._material(P0 + scan.y[:, None] * (P1 - P0), D)[1]
        return out

    # -- edges -------------------------------------------------------------------------------------
    def edges(self, scan: Scan, i: int) -> np.ndarray:
        """Where line i crosses the gold edges: [outer in, inner in, inner out, outer out] in y
        (continuous in the parameters even where the line misses the hole: then inner in > inner out)."""
        F0, F1 = self.line_in_frame(scan, i)
        f = self.frame
        lo_o, hi_o = _slab(F0, F1, f.outer / 2)
        lo_i, hi_i = _slab(F0, F1, f.inner / 2)
        return np.array([lo_o, lo_i, hi_i, hi_o])


def _ray_pattern(n: int) -> np.ndarray:
    """n points (in units of sigma) across a round Gaussian spot: the centre and rings."""
    if n == 1:
        return np.zeros((1, 2))
    pts = [(0.0, 0.0)]
    ring = n - 1
    for k in range(ring):
        a = 2 * math.pi * k / ring
        pts.append((1.2 * math.cos(a), 1.2 * math.sin(a)))
    return np.array(pts)


def _slab(F0, F1, h):
    """y interval where max(|F0 + y F1|) <= h (lo > hi when the line misses the square)."""
    lo, hi = -np.inf, np.inf
    for j in range(2):
        if abs(F1[j]) < 1e-12:
            if abs(F0[j]) > h:
                return np.inf, -np.inf
            continue
        a, b = (-h - F0[j]) / F1[j], (h - F0[j]) / F1[j]
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    return lo, hi


# -- edges in a measured line ----------------------------------------------------------------------
def profile_edges(y, profile, smooth: float = 1.0, rel: float = 0.3, min_sep: float = 0.04) -> np.ndarray | None:
    """Gold edges in one line: [outer in, outer out] or [outer in, inner in, inner out, outer out]
    (ascending y), from the steepest rises and falls of the smoothed profile; None if the line
    does not show that pattern (the weakest steps, e.g. the dark shadow strip next to an edge,
    are dropped until it does)."""
    y, p = np.asarray(y, float), np.asarray(profile, float)
    if len(y) < 5 or not np.all(np.isfinite(p)):
        return None
    if y[-1] < y[0]:
        y, p = y[::-1], p[::-1]
    raw = p
    step = float(np.mean(np.diff(y)))
    if smooth > 0:
        k = np.arange(-int(4 * smooth) - 1, int(4 * smooth) + 2)
        g = np.exp(-0.5 * (k / smooth) ** 2)
        p = np.convolve(np.pad(p, len(k) // 2, mode="edge"), g / g.sum(), mode="valid")
    d = np.gradient(p)
    # an edge: among the steepest of the line, well above the noise (MAD), and not a slow drift
    noise = 1.4826 * float(np.median(np.abs(d - np.median(d))))
    big = max(rel * np.max(np.abs(d)), 8.0 * noise, 0.02 * float(np.max(np.abs(p))))
    if big <= 0 or np.max(np.abs(d)) < big:
        return None
    cand = []
    for j in range(1, len(d) - 1):
        if abs(d[j]) >= big and abs(d[j]) >= abs(d[j - 1]) and abs(d[j]) > abs(d[j + 1]):
            a, b, c = abs(d[j - 1]), abs(d[j]), abs(d[j + 1])
            den = a - 2 * b + c
            off = 0.5 * (a - c) / den if den != 0 else 0.0
            cand.append((_crossing(y, raw, j, y[j] + off * step), np.sign(d[j]), b))
    # keep the strongest of edges closer than min_sep (a noise wiggle next to an edge)
    cand.sort(key=lambda e: -e[2])
    kept = []
    for e in cand:
        if all(abs(e[0] - k[0]) >= min_sep for k in kept):
            kept.append(e)
    while len(kept) >= 2:
        kept.sort(key=lambda e: e[0])
        signs = [e[1] for e in kept]
        if signs == [1, -1] or signs == [1, -1, 1, -1]:
            return np.array([e[0] for e in kept])
        kept.remove(min(kept, key=lambda e: e[2]))
    return None


def _crossing(y, p, j, guess, near: int = 2, far: int = 6):
    """Edge at index j refined: where the raw profile crosses half-way between its levels
    just before and just after (unbiased for a step blurred over a pixel); the gradient
    peak `guess` if that fails."""
    n = len(p)
    if j - far < 0 or j + far >= n:
        return guess
    lo, hi = float(np.median(p[j - far:j - near + 1])), float(np.median(p[j + near:j + far + 1]))
    mid = 0.5 * (lo + hi)
    for k in range(j - near, j + near):
        a, b = p[k] - mid, p[k + 1] - mid
        if a == 0:
            return float(y[k])
        if a * b < 0:
            return float(y[k] + (y[k + 1] - y[k]) * a / (a - b))
    return guess


def map_edges(scan: Scan, **kw) -> list[np.ndarray | None]:
    """profile_edges of every line (column) of a map."""
    return [profile_edges(scan.y, scan.intensity[:, i], **kw) for i in range(len(scan.x))]


# -- fits -----------------------------------------------------------------------------------------------
@dataclass
class FitResult:
    names: tuple
    values: dict
    sigma: dict
    rms: float
    n: int
    used_lines: int
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"values": {k: round(float(v), 5) for k, v in self.values.items()},
                "sigma": {k: round(float(v), 5) for k, v in self.sigma.items()},
                "rms_mm": round(float(self.rms), 5), "equations": int(self.n), "lines": int(self.used_lines),
                **({"notes": list(self.notes)} if self.notes else {})}


def _lm(residual, x0, steps, iterations: int = 40):
    """Levenberg-Marquardt with a numerical Jacobian; returns (x, residuals, Jacobian)."""
    x = np.array(x0, float)
    r = residual(x)
    lam = 1e-3
    for _ in range(iterations):
        J = np.empty((len(r), len(x)))
        for k in range(len(x)):
            dx = np.zeros(len(x))
            dx[k] = steps[k]
            J[:, k] = (residual(x + dx) - r) / steps[k]
        A, g = J.T @ J, J.T @ r
        improved = False
        for _ in range(10):
            try:
                delta = -np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            r_new = residual(x + delta)
            if r_new @ r_new < r @ r:
                x, r, lam, improved = x + delta, r_new, lam / 3, True
                break
            lam *= 10
        if not improved or np.max(np.abs(delta)) < 1e-7:
            break
    J = np.empty((len(r), len(x)))
    for k in range(len(x)):
        dx = np.zeros(len(x))
        dx[k] = steps[k]
        J[:, k] = (residual(x + dx) - r) / steps[k]
    return x, r, J


def _uncertainty(r, J):
    dof = max(1, len(r) - J.shape[1])
    s2 = float(r @ r) / dof
    try:
        cov = np.linalg.inv(J.T @ J) * s2
        return np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        return np.full(J.shape[1], np.nan)


def fit_st_sz(scan: Scan, frame: GoldFrame | None = None, core: float = 0.6) -> FitResult:
    """Step 1: the frame in the ST x SZ map.

    Edges are taken along both directions of the map (along SZ: horizontal
    edges, along ST: vertical edges), only in the middle `core` of the frame
    (away from the corners), and placed at their motor positions (the map's
    per-line motor paths). Every edge point lies on a known frame edge (frame
    coordinate +-outer/2 or +-inner/2), so (fu, fv) = H (ST_c - ST, SZ_c - SZ)
    is a linear fit. G = H^-1 maps frame mm to motor mm: its columns give the
    scales, the rotation and the shear.
    """
    frame = frame or GoldFrame()
    st, sz, img = scan.motor_grid("st"), scan.motor_grid("sz"), scan.intensity
    # profiles along both array axes; each runs along ST or along SZ
    found = {0: [], 1: []}  # 0: along ST (vertical edges), 1: along SZ (horizontal edges)
    for axis in (0, 1):
        n = img.shape[1 - axis]
        for k in range(n):
            sl = (slice(None), k) if axis == 0 else (k, slice(None))
            p, a, b = img[sl], st[sl], sz[sl]
            along = 0 if np.ptp(a) > np.ptp(b) else 1
            coord = (a, b)[along]
            e = profile_edges(coord, p)
            if e is None:
                continue
            order = np.argsort(coord)
            other = (b, a)[along]
            pts = [(c, np.interp(c, coord[order], other[order])) for c in e]
            found[along].append([(c, o) if along == 0 else (o, c) for c, o in pts])
    if not found[0] or not found[1]:
        raise ValueError("step 1: no gold frame found in the ST x SZ map")
    # rough centre and extent from the outer edges
    st_c = float(np.median([(e[0][0] + e[-1][0]) / 2 for e in found[0]]))
    sz_c = float(np.median([(e[0][1] + e[-1][1]) / 2 for e in found[1]]))
    half = {0: float(np.max([e[-1][1] - e[0][1] for e in found[1]])) / 2,  # SZ extent, for lines along ST
            1: float(np.max([e[-1][0] - e[0][0] for e in found[0]])) / 2}
    ratio = frame.inner / frame.outer
    vals = {2: (frame.outer / 2, -frame.outer / 2), 4: (frame.outer / 2, frame.inner / 2, -frame.inner / 2, -frame.outer / 2)}
    eqs = {0: [], 1: []}
    for along in (0, 1):
        for e in found[along]:
            off = abs(np.mean([q[1 - along] for q in e]) - (sz_c if along == 0 else st_c))
            if off > core * half[along]:
                continue
            if len(e) == 4 and off > core * half[along] * ratio:
                e = [e[0], e[3]]
            # ascending ST (SZ) is descending u (v): the first edge is at +outer/2
            for (m_st, m_sz), f in zip(e, vals[len(e)]):
                eqs[along].append((m_st, m_sz, f))
    H, c = np.zeros((2, 2)), np.zeros(2)
    res = []
    for axis in (0, 1):
        a = np.array(eqs[axis])
        if len(a) < 6:
            raise ValueError("step 1: too few edge points for the frame fit")
        A = np.column_stack([-a[:, 0], -a[:, 1], np.ones(len(a))])
        keep = np.ones(len(a), bool)
        for _ in range(5):  # edges taken wrongly (a line grazing a corner of the hole) are left out
            sol, *_ = np.linalg.lstsq(A[keep], a[keep, 2], rcond=None)
            r_all = A @ sol - a[:, 2]
            limit = max(5.0 * 1.4826 * float(np.median(np.abs(r_all[keep]))), 0.01)
            new = np.abs(r_all) <= limit
            if np.array_equal(new, keep) or new.sum() < 6:
                break
            keep = new
        H[axis], c[axis] = sol[:2], sol[2]
        res.append(r_all[keep])
    G = np.linalg.inv(H)
    centre = G @ c
    r = np.concatenate(res)
    # uncertainties of the centre: from the residual scatter of each edge family
    sig_c = [float(np.std(res[k]) / math.sqrt(len(res[k]) / 2)) for k in (0, 1)]
    rot_u = math.degrees(math.atan2(G[1, 0], G[0, 0]))
    rot_v = math.degrees(math.atan2(-G[0, 1], G[1, 1]))
    values = {
        "st_c": float(centre[0]), "sz_c": float(centre[1]),
        "scale_st": float(1 / np.hypot(*G[:, 0])), "scale_sz": float(1 / np.hypot(*G[:, 1])),
        "rotation": (rot_u + rot_v) / 2, "shear": rot_v - rot_u,
    }
    sigma = {"st_c": sig_c[0], "sz_c": sig_c[1]}
    return FitResult(tuple(values), values, sigma, float(np.sqrt(np.mean(r ** 2))), len(r),
                     len(found[0]) + len(found[1]))


def _grid_start(residual, grids):
    best, best_cost = None, np.inf
    for p in np.array(np.meshgrid(*grids, indexing="ij")).reshape(len(grids), -1).T:
        r = residual(p)
        cost = float(r @ r)
        if cost < best_cost:
            best, best_cost = p, cost
    return best


def _robust(r):
    """Residuals with large ones capped, for the coarse grid start (a few wrong lines must not win it)."""
    return np.clip(r, -0.2, 0.2)


def _get(setup: Setup, name: str) -> float:
    if name.startswith("frame."):
        return float(getattr(setup.frame, name[6:]))
    if name.startswith("instrument."):
        return float(getattr(setup.instrument, name[11:]))
    return float(getattr(setup.config, name))




def _set(setup: Setup, name: str, value: float) -> Setup:
    if name.startswith("frame."):
        return replace(setup, frame=replace(setup.frame, **{name[6:]: float(value)}))
    if name.startswith("instrument."):
        return replace(setup, instrument=replace(setup.instrument, **{name[11:]: float(value)}))
    return replace(setup, config=replace(setup.config, **{name: float(value)}))


# -- the measurement plan: SZ fly lines ---------------------------------------------------------------------
@dataclass
class PlanLine:
    """One SZ fly line of the survey: SRn, SRz, ST and SN set before it (slow motors), SZ scanned (fast).

    group: "A" (SRn ref, SRz 0), "B" (frame turned by +-45 deg: a diamond, SRz 0), "C" (diamond, SRz turned).
    du: where the line passes, across it, from the frame centre (mm on the plate, along the line normal).
    """

    group: str
    srn: float
    srz: float
    du: float
    st: float
    sn: float
    sz_from: float
    sz_to: float

    def motors(self, pi_center: float = 150.0) -> MotorPositions:
        return MotorPositions(st=self.st, sn=self.sn, sz=(self.sz_from + self.sz_to) / 2, srn=self.srn,
                              srz=self.srz, pix=pi_center, piy=pi_center)


GROUP_TEXT = {
    "A": "SRn ref, SRz 0: SZ0, in-plane rotation, SZ scale",
    "B": "frame turned 45 deg (diamond), SRz 0: ST0, SRn axis, ST scale",
    "C": "diamond, SRz turned: SRz axis (offset along ST, depth), tilt of the gold face",
}


SURVEY_SRZ = (-25.0, -18.0, -11.0, -4.0, 3.0, 10.0)


def survey_plan(guide: Setup, srn_diag=(165.0, 75.0), srz_angles=SURVEY_SRZ,
                du_flat=(-0.8, -0.4, 0.0, 0.4, 0.8), du_diag=(-1.0, -0.5, 0.0, 0.5, 1.0), du_srz=(-0.4, 0.0, 0.4),
                sz_half: float = 2.2) -> list[PlanLine]:
    """The SZ lines of the survey, placed with the `guide` setup (the newest configuration, frame at its
    nominal place): ST so that the line passes du from the frame centre, SN so that the frame centre is at
    the analyzer focus (one SN per SRn / SRz), SZ +-sz_half around the frame centre.

    With the frame turned by 45 deg its edges are diagonal: an SZ line crosses them at SZ positions that
    move 1:1 with where the line passes across the frame, so ST0, the SRn axis and the SRz axis are read
    on the fast SZ axis; ST, SRn and SRz only move between lines.
    """
    c = guide.config
    f = guide.frame
    out = []
    groups = [("A", c.srn_ref, 0.0, du_flat)] + [("B", srn, 0.0, du_diag) for srn in srn_diag]
    groups += [("C", srn_diag[0], srz, du_srz) for srz in srz_angles if abs(srz) > 1e-9]
    for group, srn, srz, dus in groups:
        centre = guide.model.motors_for_target(f.u, f.v, guide.gold_w(), srn, srz)
        a = math.radians(srn - c.srn_ref)
        for du in dus:
            # across the line in the stage frame = the plate direction R(-a) (1, 0)
            u, v = f.u + du * math.cos(a), f.v - du * math.sin(a)
            m = guide.model.motors_for_target(u, v, guide.gold_w(), srn, srz)
            m = replace(m, st=m.st - (centre.sn - m.sn), sn=centre.sn)  # SN kept for the group: ST slides along
            out.append(PlanLine(group, float(srn), float(srz), float(du), float(m.st), float(m.sn),
                                float(m.sz - sz_half), float(m.sz + sz_half)))
    return out


def plan_scan(lines: list[PlanLine], step: float = 0.02, pi_center: float = 150.0) -> Scan:
    """The plan as one Scan of SZ lines (for simulation): line i at its motors, SZ = base + y."""
    n = len(lines)
    half = max((p.sz_to - p.sz_from) / 2 for p in lines)
    y = np.arange(-half, half + step / 2, step)
    base = {k: np.zeros(n) for k in MOTORS}
    slope = {k: np.zeros(n) for k in MOTORS}
    for i, p in enumerate(lines):
        m = p.motors(pi_center)
        for k in MOTORS:
            base[k][i] = getattr(m, k)
        slope["sz"][i] = 1.0
    return Scan("sz_lines", np.arange(n, dtype=float), y, base, slope,
                info={"plan": [asdict(p) for p in lines]})


def split_by_angles(scan: Scan) -> dict[str, Scan]:
    """A plan scan cut into one Scan per (SRn, SRz): the files a beamline scan would write (ST stepped
    between lines, SZ fast)."""
    out = {}
    keys = list(dict.fromkeys(zip(scan.base["srn"], scan.base["srz"])))
    for srn, srz in keys:
        idx = np.flatnonzero((scan.base["srn"] == srn) & (scan.base["srz"] == srz))
        part = Scan("sz_lines", scan.base["st"][idx].copy(), scan.y.copy(),
                    {k: v[idx].copy() for k, v in scan.base.items()}, {k: v[idx].copy() for k, v in scan.slope.items()},
                    None if scan.intensity is None else scan.intensity[:, idx].copy())
        out[f"srn{srn:g}_srz{srz:g}"] = part
    return out


# -- optional: SN focus at other SRz ----------------------------------------------------------------------------
@dataclass
class SNPoint:
    """SN (ST following, dST = -dSN) at which the gold under the beam was in the analyzer focus, measured
    at another SRz (and SRn): ST, SZ, SN read at the intensity peak. Optional data of the global fit."""

    srn: float
    srz: float
    st: float
    sz: float
    sn: float
    use: bool = True

    def motors(self, pi_center: float = 150.0) -> MotorPositions:
        return MotorPositions(st=self.st, sn=self.sn, sz=self.sz, srn=self.srn, srz=self.srz, pix=pi_center,
                              piy=pi_center)


def sn_point_plan(guide: Setup, srz_angles=SURVEY_SRZ, srn: float | None = None) -> list[SNPoint]:
    """Where to measure the optional SN points: the middle of the frame's right bar (seen at the given SRn,
    default the reference), at the analyzer focus according to `guide` (SN is the expected peak)."""
    f = guide.frame
    srn = guide.config.srn_ref if srn is None else srn
    u = f.u + (f.outer + f.inner) / 4
    out = []
    for srz in srz_angles:
        m = guide.model.motors_for_target(u, f.v, guide.gold_w(), srn, srz)
        out.append(SNPoint(float(srn), float(srz), float(m.st), float(m.sz), float(m.sn)))
    return out


def sn_focus_error(setup: Setup, point: SNPoint) -> float:
    """How far (in SN) the gold under the beam is from the analyzer focus at the point's motors (0 if the
    setup is right): its distance along the beam / sqrt 2."""
    P, D, _, _ = setup.beam_in_plate(point.motors(setup.config.pi_center))
    return float(setup._gold_s(P[None, :], D)[0]) / math.sqrt(2.0)


# -- the global fit -------------------------------------------------------------------------------------------
GLOBAL_PARAMS = ("st0", "sz0", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n", "frame.rotation",
                 "frame.tilt_u", "instrument.st_scale", "instrument.sz_scale")
PARAM_STEPS = {"frame.rotation": 1e-3, "frame.tilt_u": 1e-3, "instrument.st_scale": 1e-5, "instrument.sz_scale": 1e-5}
PARAM_TEXT = {
    "st0": "ST0", "sz0": "SZ0", "srn_axis_u": "SRn axis x", "srn_axis_v": "SRn axis y",
    "srz_offset_t": "SRz offset ST", "srz_offset_n": "SRz offset SN", "frame.rotation": "frame rotation (deg)",
    "frame.tilt_u": "tilt of the gold face about v (deg)", "instrument.st_scale": "ST scale",
    "instrument.sz_scale": "SZ scale",
}


@dataclass
class GlobalResult:
    setup: Setup
    values: dict
    sigma: dict
    rms: float  # edges, mm
    edges: int
    lines_used: int
    lines_total: int
    per_scan: list  # (used lines, lines, rms mm) per scan
    left_out: list  # (scan index, line index)
    sn_residuals: list  # SN focus error per SN point (mm), None where not used
    kept: dict  # parameter -> why it was not fitted
    overview: FitResult | None = None
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"values": {k: round(float(v), 5) for k, v in self.values.items()},
                "sigma": {k: round(float(v), 5) for k, v in self.sigma.items()},
                "edge_rms_mm": round(self.rms, 5), "edges": self.edges,
                "lines": f"{self.lines_used}/{self.lines_total}",
                "sn_points_residual_mm": [None if r is None else round(r, 4) for r in self.sn_residuals],
                "kept": dict(self.kept), "notes": list(self.notes),
                **({"overview_map": self.overview.to_dict()} if self.overview else {})}


def _sz_lines(scans) -> list:
    """(scan index, line index, measured edges or None) of every line of every scan."""
    out = []
    for k, scan in enumerate(scans):
        for i, e in enumerate(map_edges(scan)):
            out.append((k, i, e))
    return out


def fit_global(scans: list, sn_gold: float, frame: GoldFrame | None = None, base: StageConfig | None = None,
               free_tilt: bool = True, free_scales: bool = True, sn_points=(), edge_sigma: float = 0.003,
               sn_sigma: float = 0.01, plate: PlateGeometry = STANDARD_PLATE,
               instrument: Instrument | None = None) -> GlobalResult:
    """Every edge of every line of every scan, and the optional SN points, fitted at once.

    scans: any lines (SZ lines of the survey, an ST x SZ overview map, an SZ x SRn map...). A parameter the
    data cannot fix (no line with SRn turned: the SRn axis; none with SRz turned: the SRz axis and the tilt)
    is kept from `base` (the newest configuration). SN_f comes from sn_gold (SN with the gold top at the
    analyzer focus at SRn ref, SRz 0) and the gold height. The frame is taken to be at (frame.u, frame.v).
    """
    frame = frame or GoldFrame()
    base = base or StageConfig()
    sn_f = sn_gold - (plate.total_thickness + frame.height - STANDARD_PLATE.total_thickness)
    setup = Setup(replace(base, sn_f=float(sn_f)), frame, instrument or Instrument(), plate)
    m0 = setup.frame_motors()
    setup = replace(setup, instrument=replace(setup.instrument, scale_st_ref=m0.st, scale_sz_ref=m0.sz))
    scans = list(scans)
    notes = []

    # an ST x SZ map at SRn ref / SRz 0 gives a good start for ST0, SZ0 and the rotation
    overview = None
    for scan in scans:
        if (scan.kind == "st_sz" and np.allclose(scan.base["srn"], base.srn_ref) and np.allclose(scan.base["srz"], 0)
                and len(scan.x) >= 5):
            try:
                overview = fit_st_sz(scan, frame)
            except ValueError:
                continue
            st0, sz0 = _centre_constants(setup, overview, float(scan.base["sn"][0]))
            # rotation from the horizontal edges (found along SZ, the fast axis): with coarse ST steps the
            # vertical ones are only known to a step
            rotation = overview.values["rotation"] + overview.values["shear"] / 2
            setup = _set(_set(_set(setup, "st0", st0), "sz0", sz0), "frame.rotation", rotation)
            break

    items = _sz_lines(scans)
    srn_turned = any(abs(scans[k].motors(i, 0.0).srn - base.srn_ref) > 5 for k, i, e in items if e is not None)
    srz_turned = any(abs(scans[k].motors(i, 0.0).srz) > 2 for k, i, e in items if e is not None)
    sn_used = [p for p in sn_points if p.use]
    names, kept = [], {}
    for name in GLOBAL_PARAMS:
        if name in ("srn_axis_u", "srn_axis_v") and not srn_turned:
            kept[name] = "no line with SRn turned"
        elif name in ("srz_offset_t", "srz_offset_n") and not (srz_turned or any(abs(p.srz) > 2 for p in sn_used)):
            kept[name] = "no line with SRz turned"
        elif name == "frame.tilt_u" and not (free_tilt and srz_turned):
            kept[name] = "not fitted" if not free_tilt else "no line with SRz turned"
        elif name.startswith("instrument.") and not free_scales:
            kept[name] = "not fitted"
        else:
            names.append(name)
    weight = edge_sigma / sn_sigma

    def residual(p, use, points=sn_used):
        s = setup
        for n, v in zip(names, p):
            s = _set(s, n, v)
        out = []
        for (k, i, e), ok in zip(items, use):
            if ok:
                pred = s.edges(scans[k], i)
                out.append(e - (pred if len(e) == 4 else pred[[0, 3]]))
        for pt in points:
            out.append(np.array([weight * sn_focus_error(s, pt)]))
        r = np.concatenate(out) if out else np.zeros(0)
        return np.where(np.isfinite(r), r, 10.0)

    def line_rms(p):
        s = setup
        for n, v in zip(names, p):
            s = _set(s, n, v)
        out = np.full(len(items), np.nan)
        for j, (k, i, e) in enumerate(items):
            if e is not None:
                pred = s.edges(scans[k], i)
                d = e - (pred if len(e) == 4 else pred[[0, 3]])
                out[j] = float(np.sqrt(np.mean(np.where(np.isfinite(d), d, 10.0) ** 2)))
        return out

    have = np.array([e is not None for _, _, e in items])
    if have.sum() < len(names) + 1:
        raise ValueError(f"too few lines with clear gold edges ({int(have.sum())}) for {len(names)} parameters")
    flat = np.array([e is not None and abs(scans[k].motors(i, 0.0).srz) <= 2 for k, i, e in items])
    x = np.array([_get(setup, n) for n in names])
    steps = [PARAM_STEPS.get(n, 1e-4) for n in names]

    # 1. lines at SRz 0: where the frame is (coarse grid on ST0 / SZ0 unless an overview map gave them)
    if flat.sum() >= 3:
        i0, i1 = names.index("st0"), names.index("sz0")
        if overview is None:
            def shifted(q):
                p = x.copy()
                p[i0], p[i1] = x[i0] + q[0], x[i1] + q[1]
                return _robust(residual(p, flat, ()))
            grid = np.arange(-0.8, 0.81, 0.1)
            q = _grid_start(shifted, [grid, grid])
            x[i0], x[i1] = x[i0] + q[0], x[i1] + q[1]
        srz_names = [n for n in names if n.startswith("srz_") or n == "frame.tilt_u"]
        sub = [j for j, n in enumerate(names) if n not in srz_names]

        def flat_res(q):
            p = x.copy()
            p[sub] = q
            return residual(p, flat, ())
        q, _, _ = _lm(flat_res, x[sub], [steps[j] for j in sub])
        x[sub] = q
    # 2. the SRz axis: coarse grid on its offsets with the rest kept, then everything together
    if "srz_offset_t" in names:
        jt, jn = names.index("srz_offset_t"), names.index("srz_offset_n")

        def srz_res(q):
            p = x.copy()
            p[jt], p[jn] = q
            return _robust(residual(p, have))
        q = _grid_start(srz_res, [x[jt] + np.arange(-2.5, 2.51, 0.25), x[jn] + np.arange(-3.0, 3.01, 0.25)])
        x[jt], x[jn] = q
    use = have.copy()
    near = have & (line_rms(x) < 0.15)
    if near.sum() >= len(names) + 1:
        use = near
    x, r, J = _lm(lambda p: residual(p, use), x, steps)
    for _ in range(4):  # lines whose edges were taken wrongly are left out
        rms = line_rms(x)
        limit = max(5.0 * float(np.nanmedian(rms[use])), 0.01)
        new = have & (rms <= limit)
        if np.array_equal(new, use):
            break
        use = new
        x, r, J = _lm(lambda p: residual(p, use), x, steps)
    sig = _uncertainty(r, J)
    final = setup
    for n, v in zip(names, x):
        final = _set(final, n, v)
    rms = line_rms(x)
    per_scan = []
    for k in range(len(scans)):
        idx = [j for j, it in enumerate(items) if it[0] == k and have[j]]  # lines across the frame
        u = [j for j in idx if use[j]]
        per_scan.append((len(u), len(idx), float(np.sqrt(np.nanmean(rms[u] ** 2))) if u else float("nan")))
    left = [(items[j][0], items[j][1]) for j in range(len(items)) if have[j] and not use[j]]
    sn_res = [sn_focus_error(final, p) if p.use else None for p in sn_points]
    edge_r = r[:len(r) - len(sn_used)] if sn_used else r
    for name, key in (("ST", "instrument.st_scale"), ("SZ", "instrument.sz_scale")):
        if key in names and abs(_get(final, key) - 1) > 0.005:
            notes.append(f"{name} scale {_get(final, key):.4f}: more than 0.5 % from 1; QuickAlignment assumes 1")
    if "frame.tilt_u" in names and abs(_get(final, "frame.tilt_u")) > 2:
        notes.append(f"gold face tilted {_get(final, 'frame.tilt_u'):.2f} deg about v: check the mounting")
    for n, why in kept.items():
        if n in ("srn_axis_u", "srz_offset_t"):
            notes.append(f"{PARAM_TEXT[n].split(' ')[0]} axis kept from the newest configuration: {why}")
    return GlobalResult(final, dict(zip(names, map(float, x))), dict(zip(names, map(float, sig))),
                        float(np.sqrt(np.mean(edge_r ** 2))) if len(edge_r) else float("nan"), len(edge_r),
                        int(use.sum()), int(have.sum()), per_scan, left, sn_res, kept, overview, notes)


def _centre_constants(setup: Setup, overview: FitResult, sn_map: float) -> tuple[float, float]:
    """ST0, SZ0 putting the frame centre on the beam where the overview map found it."""
    v = overview.values
    m = MotorPositions(st=v["st_c"], sn=sn_map, sz=v["sz_c"], srn=setup.config.srn_ref, srz=0.0,
                       pix=setup.config.pi_center, piy=setup.config.pi_center)

    def hit(st0, sz0):
        s = _set(_set(setup, "st0", st0), "sz0", sz0)
        P, D, _, _ = s.beam_in_plate(m)
        return (P + s._gold_s(P[None, :], D)[0] * D)[:2]

    h0 = hit(0.0, 0.0)
    M = np.column_stack([hit(1.0, 0.0) - h0, hit(0.0, 1.0) - h0])
    st0, sz0 = np.linalg.solve(M, np.array([setup.frame.u, setup.frame.v]) - h0)
    return float(st0), float(sz0)


# -- simulated measurements --------------------------------------------------------------------------------------
def simulated_measurement(guide: Setup, truth: Setup, overview: bool = True, srn_sweep: bool = False,
                          step: float = 0.02, overview_st_step: float = 0.1, rng=None, **plan) -> dict[str, Scan]:
    """What the beamline would measure with the protocol, placed with `guide`, simulated on `truth`:
    an ST x SZ overview (coarse ST steps, optional), the SZ x SRn sweep (optional) and the survey,
    one Scan per (SRn, SRz) as the beamline writes them."""
    rng = rng or np.random.default_rng(0)
    nominal = replace(guide, frame=GoldFrame(outer=guide.frame.outer, inner=guide.frame.inner,
                                              height=guide.frame.height), instrument=Instrument())
    m = nominal.frame_motors()
    out = {}
    if overview:
        out["overview"] = make_scan("st_sz", m.st + np.arange(-2.0, 2.0 + overview_st_step / 2, overview_st_step),
                                    m.sz + np.arange(-2.0, 2.0 + step / 2, step), m)
    if srn_sweep:
        out["srn_sweep"] = make_scan("srn_sz", np.arange(60.0, 180.1, 2.0), m.sz + np.arange(-2.5, 2.5 + step / 2, step), m)
    survey = plan_scan(survey_plan(nominal, **plan), step)
    out.update(split_by_angles(survey))
    for scan in out.values():
        truth.simulate(scan, rng)
    return out


def sn_scan(setup: Setup, sn_values, u: float | None = None, v: float | None = None, srz: float = 0.0,
            srn: float | None = None) -> np.ndarray:
    """Intensity on the gold (default: the middle of the frame's right bar) against SN, ST following SN
    (dST = -dSN) so that the point stays on the beam and slides along it: the peak is the SN with the gold
    at the analyzer focus (SN_gold at SRz 0), the width the analyzer acceptance across its axis."""
    f = setup.frame
    u = f.u + (f.outer + f.inner) / 4 if u is None else u
    v = f.v if v is None else v
    m = setup.model.motors_for_target(u, v, setup.gold_w(), setup.config.srn_ref if srn is None else srn, srz)
    sn = np.asarray(sn_values, float)
    scan = make_scan("sz_lines", np.zeros(len(sn)), np.zeros(1), m)
    scan.base["sn"] = sn.copy()
    scan.base["st"] = m.st - (sn - m.sn)
    scan.slope["sz"][:] = 0.0
    scan.base["sz"][:] = m.sz
    return setup.simulate(scan)[0]


def record_for(result: GlobalResult, optics, comment: str, sources: dict | None = None, sn_points=()):
    """A CalibrationRecord (not yet saved) with the fitted constants and what was measured."""
    from .calibration import CalibrationRecord

    s = result.setup
    check = {
        "type": "gold frame (SPEM intensity, SZ fly lines), one global fit of every edge",
        "plate": s.plate.key,
        "frame": {k: v for k, v in asdict(s.frame).items()},
        "fit": result.to_dict(),
        "motor_scales": {"st": round(s.instrument.st_scale, 5), "sz": round(s.instrument.sz_scale, 5),
                         "note": "fitted, not used by QuickAlignment (it assumes 1)"},
        **({"sn_points": [asdict(p) for p in sn_points]} if sn_points else {}),
        **({"sources": sources} if sources else {}),
    }
    return CalibrationRecord(comment=comment, config=s.config, optics=optics, check=check)


__all__ = [
    "GoldFrame", "Instrument", "Scan", "Setup", "FitResult", "GlobalResult", "PlanLine", "SNPoint", "KINDS",
    "GROUP_TEXT", "GLOBAL_PARAMS", "SURVEY_SRZ", "PARAM_TEXT", "make_scan", "profile_edges", "map_edges", "fit_st_sz",
    "survey_plan", "plan_scan", "split_by_angles", "sn_point_plan", "sn_focus_error", "fit_global",
    "simulated_measurement", "sn_scan", "record_for",
]
