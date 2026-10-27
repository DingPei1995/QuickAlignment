"""Gold-frame calibration: the stage constants from SPEM intensity maps of the gold reference frame.

The reference sample is a square gold frame (2 x 2 mm outside, 1 x 1 mm hole)
glued on the riser of the standard plate, in principle at its centre. Only the
total photoemission intensity is used (no angle or energy resolution). Three
maps are measured, SN kept at the gold focus found at SRn = 120, SRz = 0:

1. ``st_sz``: ST x SZ map (SRn = 120, SRz = 0): where the frame is (ST0, SZ0),
   its in-plane rotation, the ST / SZ scales (and shear);
2. ``srn_sz``: SZ line through the frame (ST at the frame centre) for each SRn
   (e.g. 120 +- 60): the SRn axis on the plate;
3. ``srz_st``: ST line through the hole (SZ at the frame centre) for each SRz
   (SRn back at 120): the SRz axis offsets (along ST and SN).
   ``srz_surface``: the same with ST and SN moved together along the turned
   surface, which keeps the illuminated spot at the analyzer focus.

Simulation: the beam (lab y axis, or offset from it) is traced onto the frame
with the stage kinematics of `StageModel`; the gold top face (height, tilts),
its side walls (which shadow the riser behind them) and the riser give the
material; the beam spot grows out of the optic focus, and the analyzer only
sees what lies near its focus (Gaussian acceptance). Motor scales are applied
around a reference position (the frame centre).

Fits: gold edges are taken from every line of a map (where the gold top face
begins and ends, which is where the beam crosses an edge, whatever the
analyzer sees), then fitted with the same geometry. The analyzer acceptance
only weights the intensity: it does not move a sharp edge.
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

# what each map scans: (outer axis = map x, scanned axis = map y)
KINDS = {
    "st_sz": ("ST (mm)", "SZ (mm)"),
    "srn_sz": ("SRn (deg)", "SZ (mm)"),
    "srz_st": ("SRz (deg)", "ST (mm)"),
    "srz_surface": ("SRz (deg)", "along the surface (mm)"),
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


def make_scan(kind: str, x, y, fixed: MotorPositions, surface_st=None, surface_sn=None) -> Scan:
    """A map of `kind` over x (outer) and y (scanned), the other motors at `fixed`.

    srz_surface: y is the distance along the turned surface from (surface_st[i],
    surface_sn[i]) (default: fixed.st / fixed.sn); ST and SN move as
    (cos a, sin a) * y with a = -SRz.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    base = {k: np.full(n, float(getattr(fixed, k))) for k in MOTORS}
    slope = {k: np.zeros(n) for k in MOTORS}
    if kind == "st_sz":
        base["st"], base["sz"], slope["sz"] = x.copy(), np.zeros(n), np.ones(n)
    elif kind == "srn_sz":
        base["srn"], base["sz"], slope["sz"] = x.copy(), np.zeros(n), np.ones(n)
    elif kind == "srz_st":
        base["srz"], base["st"], slope["st"] = x.copy(), np.zeros(n), np.ones(n)
    elif kind == "srz_surface":
        a = np.radians(-x)
        base["srz"] = x.copy()
        if surface_st is not None:
            base["st"] = np.asarray(surface_st, float).copy()
        if surface_sn is not None:
            base["sn"] = np.asarray(surface_sn, float).copy()
        slope["st"], slope["sn"] = np.cos(a), np.sin(a)
    else:
        raise ValueError(f"unknown map kind {kind!r} (one of {', '.join(KINDS)})")
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


def _edge_residuals(setup_for, measured, scan, use=None):
    """Residual function for steps 2 / 3: measured minus predicted edges, line by line
    (lines with use[i] False left out)."""
    def residual(p):
        s = setup_for(p)
        out = []
        for i, e in enumerate(measured):
            if e is None or (use is not None and not use[i]):
                continue
            pred = s.edges(scan, i)
            out.append(e - (pred if len(e) == 4 else pred[[0, 3]]))
        r = np.concatenate(out) if out else np.zeros(0)
        return np.where(np.isfinite(r), r, 10.0)
    return residual


def _line_rms(setup, measured, scan, use):
    out = np.full(len(measured), np.nan)
    for i, e in enumerate(measured):
        if e is not None and use[i]:
            pred = setup.edges(scan, i)
            r = e - (pred if len(e) == 4 else pred[[0, 3]])
            out[i] = float(np.sqrt(np.mean(np.where(np.isfinite(r), r, 10.0) ** 2)))
    return out


def _grid_start(residual, grids):
    best, best_cost = None, np.inf
    for p in np.array(np.meshgrid(*grids, indexing="ij")).reshape(len(grids), -1).T:
        r = residual(p)
        cost = float(r @ r)
        if cost < best_cost:
            best, best_cost = p, cost
    return best


def fit_axis(setup: Setup, scan: Scan, names: tuple, grids: dict, steps: dict, adjust=None) -> FitResult:
    """Fit config / frame / instrument parameters `names` to the edges of a map (steps 2 and 3).

    A name is a StageConfig field, ``frame.<field>`` or ``instrument.<field>``.
    The parameters start from the best point of `grids` (values for the names
    found there; the others start at their value in `setup`). `adjust(setup)`,
    if given, is applied to every trial setup (parameters tied to the fitted ones).
    """
    measured = map_edges(scan)
    if sum(e is not None for e in measured) < len(names) + 1:
        raise ValueError(f"{scan.kind}: too few lines with clear gold edges ({sum(e is not None for e in measured)})")

    def setup_for(p):
        cfg, fr, inst = setup.config, setup.frame, setup.instrument
        for name, value in zip(names, p):
            if name.startswith("frame."):
                fr = replace(fr, **{name[6:]: float(value)})
            elif name.startswith("instrument."):
                inst = replace(inst, **{name[11:]: float(value)})
            else:
                cfg = replace(cfg, **{name: float(value)})
        out = replace(setup, config=cfg, frame=fr, instrument=inst)
        return adjust(out) if adjust else out

    use = np.array([e is not None for e in measured])
    residual = _edge_residuals(setup_for, measured, scan, use)
    start = [_get(setup, n) for n in names]
    grid_names = [n for n in names if n in grids]
    if grid_names:
        def partial(q):
            p = list(start)
            for n, v in zip(grid_names, q):
                p[names.index(n)] = v
            return _robust(residual(np.array(p)))
        q = _grid_start(partial, [grids[n] for n in grid_names])
        for n, v in zip(grid_names, q):
            start[names.index(n)] = v
    # start with the lines that agree with the start point (a line whose edges were taken wrongly
    # must not pull the first fit away)
    rms = _line_rms(setup_for(np.array(start)), measured, scan, use)
    near = use & (rms < 0.15)
    if near.sum() >= len(names) + 2:
        use = near
        residual = _edge_residuals(setup_for, measured, scan, use)
    steps_ = [steps.get(n, 1e-4) for n in names]
    x, r, J = _lm(residual, start, steps_)
    # lines whose edges were taken wrongly (part of the frame out of the map or not seen by the
    # analyzer): far off the fit; dropped and fitted again
    notes = []
    for _ in range(3):
        rms = _line_rms(setup_for(x), measured, scan, np.array([e is not None for e in measured]))
        limit = max(5.0 * float(np.nanmedian(rms[use])), 0.01)
        new_use = np.isfinite(rms) & (rms <= limit)
        if np.array_equal(new_use, use):
            break
        use = new_use
        residual = _edge_residuals(setup_for, measured, scan, use)
        x, r, J = _lm(residual, x, steps_)
    left = [i for i, e in enumerate(measured) if e is not None and not use[i]]
    if left:
        notes.append(f"{len(left)} line(s) left out (edges far off the fit: part of the frame outside the map "
                     f"or not seen by the analyzer) at {', '.join(f'{scan.x[i]:g}' for i in left)}")
    missing = [i for i, e in enumerate(measured) if e is None]
    if missing:
        notes.append(f"{len(missing)} line(s) without clear gold edges at {', '.join(f'{scan.x[i]:g}' for i in missing)}")
    sig = _uncertainty(r, J)
    return FitResult(names, dict(zip(names, map(float, x))), dict(zip(names, map(float, sig))),
                     float(np.sqrt(np.mean(r ** 2))) if len(r) else float("nan"), len(r), int(use.sum()), notes)


def _robust(r):
    """Residuals with large ones capped, for the coarse grid start (a few wrong lines must not win it)."""
    return np.clip(r, -0.2, 0.2)


def _get(setup: Setup, name: str) -> float:
    if name.startswith("frame."):
        return float(getattr(setup.frame, name[6:]))
    if name.startswith("instrument."):
        return float(getattr(setup.instrument, name[11:]))
    return float(getattr(setup.config, name))


# -- the whole calibration ----------------------------------------------------------------------------------
@dataclass
class StepResults:
    setup: Setup
    step1: FitResult | None = None
    step2: FitResult | None = None
    step3: FitResult | None = None
    notes: list = field(default_factory=list)


def setup_from_step1(fit: FitResult, sn_gold: float, frame: GoldFrame, base: StageConfig | None = None,
                     instrument: Instrument | None = None, plate: PlateGeometry = STANDARD_PLATE,
                     beam_x: float = 0.0, beam_z: float = 0.0, sn_map: float | None = None) -> Setup:
    """Stage constants from the frame centre of step 1: ST0, SZ0 such that the model puts the frame
    centre (frame.u, frame.v, at its nominal place) on the beam at (st_c, sz_c) with SN = sn_map (the SN
    of the map, default sn_gold), and SN_f such that the gold top is in the analyzer focus at
    SN = sn_gold. The ST / SZ scales of step 1 are applied around the frame centre. Axes start from
    `base` (or zero)."""
    base = base or StageConfig()
    v = fit.values
    inst = replace(instrument or Instrument(), st_scale=v["scale_st"], sz_scale=v["scale_sz"],
                   scale_st_ref=v["st_c"], scale_sz_ref=v["sz_c"], beam_x=beam_x, beam_z=beam_z)
    frame = replace(frame, rotation=v["rotation"])
    sn_f = sn_gold - (plate.total_thickness + frame.height - STANDARD_PLATE.total_thickness)
    cfg = replace(base, st0=0.0, sz0=0.0, sn_f=float(sn_f))
    m = MotorPositions(st=v["st_c"], sn=sn_gold if sn_map is None else sn_map, sz=v["sz_c"], srn=cfg.srn_ref, srz=0.0,
                       pix=cfg.pi_center, piy=cfg.pi_center)

    def hit(st0, sz0):
        s = Setup(replace(cfg, st0=st0, sz0=sz0), frame, inst, plate)
        P, D, _, _ = s.beam_in_plate(m)
        H = P + s._gold_s(P[None, :], D)[0] * D
        return H[:2]

    h0 = hit(0.0, 0.0)
    M = np.column_stack([hit(1.0, 0.0) - h0, hit(0.0, 1.0) - h0])
    st0, sz0 = np.linalg.solve(M, np.array([frame.u, frame.v]) - h0)
    return Setup(replace(cfg, st0=float(st0), sz0=float(sz0)), frame, inst, plate)


SRN_GRID = np.arange(-1.5, 1.51, 0.25)
SRZ_T_GRID = np.arange(-3.0, 3.01, 0.5)
SRZ_N_GRID = np.arange(-2.0, 8.01, 0.5)


def fit_step2(setup: Setup, scan: Scan, free_rotation: bool = True) -> FitResult:
    names = ("srn_axis_u", "srn_axis_v") + (("frame.rotation",) if free_rotation else ())
    return fit_axis(setup, scan, names, {"srn_axis_u": SRN_GRID, "srn_axis_v": SRN_GRID},
                    {"frame.rotation": 1e-3})


def tilt_width_factor(setup: Setup) -> float:
    """How much wider the frame looks in ST at SRn = ref, SRz = 0 because of its tilt about v
    (frame width in ST with the tilt / without, motor scale 1)."""
    m = setup.frame_motors()
    line = make_scan("srz_st", [0.0], [0.0], m)
    flat = replace(setup, frame=replace(setup.frame, tilt_u=0.0, tilt_v=0.0),
                   instrument=replace(setup.instrument, st_scale=1.0))
    tilted = replace(flat, frame=replace(flat.frame, tilt_u=setup.frame.tilt_u))
    a, b = tilted.edges(line, 0), flat.edges(line, 0)
    return float((a[3] - a[0]) / (b[3] - b[0]))


def fit_step3(setup: Setup, scan: Scan, free_tilt: bool = False) -> FitResult:
    """SRz axis offsets (and ST0 again: with ST along the fast axis it is better known here than from
    the point-by-point ST of step 1, and it must not bias the offsets). free_tilt: also the tilt of the
    gold face about v, the ST scale following it so that the frame keeps its apparent width of step 1."""
    names = ("st0", "srz_offset_t", "srz_offset_n") + (("frame.tilt_u",) if free_tilt else ())
    # step 1 saw the scale st_scale / factor (a frame looking `factor` times as wide)
    apparent = setup.instrument.st_scale / tilt_width_factor(setup)

    def keep_apparent_width(s):
        return replace(s, instrument=replace(s.instrument, st_scale=apparent * tilt_width_factor(s)))
    return fit_axis(setup, scan, names, {"srz_offset_t": SRZ_T_GRID, "srz_offset_n": SRZ_N_GRID},
                    {"st0": 1e-4, "frame.tilt_u": 1e-3}, keep_apparent_width if free_tilt else None)


def calibrate(step1: Scan, sn_gold: float, frame: GoldFrame | None = None, step2: Scan | None = None,
              step3: Scan | None = None, base: StageConfig | None = None, free_tilt: bool = False,
              plate: PlateGeometry = STANDARD_PLATE, instrument: Instrument | None = None) -> StepResults:
    """All three steps: step 1 gives ST0, SZ0, SN_f (and the scales), step 2 the SRn axis, step 3 the SRz
    axis offsets. Steps 2 / 3 may be missing: those constants then stay as in `base`."""
    frame = frame or GoldFrame()
    r1 = fit_st_sz(step1, frame)
    setup = setup_from_step1(r1, sn_gold, frame, base, instrument, plate, sn_map=float(step1.base["sn"][0]))
    out = StepResults(setup, r1)
    if step2 is not None:
        out.step2 = fit_step2(setup, step2)
        v = out.step2.values
        setup = replace(setup, config=replace(setup.config, srn_axis_u=v["srn_axis_u"], srn_axis_v=v["srn_axis_v"]))
    if step3 is not None:
        out.step3 = fit_step3(setup, step3, free_tilt)
        v = out.step3.values
        setup = replace(setup, config=replace(setup.config, st0=v["st0"], srz_offset_t=v["srz_offset_t"],
                                              srz_offset_n=v["srz_offset_n"]))
        if free_tilt:
            apparent = setup.instrument.st_scale / tilt_width_factor(setup)
            tilted = replace(setup, frame=replace(setup.frame, tilt_u=v["frame.tilt_u"]))
            setup = replace(tilted, instrument=replace(setup.instrument,
                                                       st_scale=apparent * tilt_width_factor(tilted)))
    out.setup = setup
    for name, k in (("ST", "scale_st"), ("SZ", "scale_sz")):
        if abs(r1.values[k] - 1) > 0.01:
            out.notes.append(f"{name} scale {r1.values[k]:.4f}: more than 1 % from 1 (motor scale, or the gold "
                             f"face tilted{' about the vertical' if name == 'ST' else ''}); QuickAlignment assumes 1")
    if abs(r1.values["shear"]) > 0.5:
        out.notes.append(f"shear {r1.values['shear']:.2f} deg between the ST and SZ edges (gold face tilted about the "
                         "horizontal, or ST / SZ not at right angles)")
    return out


def standard_scans(setup: Setup, step: float = 0.02, angle_step: float = 2.0, srz_range=(-25.0, 10.0),
                   srn_range=(60.0, 180.0), st_half: float = 2.0, sz_half: float = 2.5, srz_st_half: float = 3.5,
                   surface: bool = False) -> dict[str, Scan]:
    """The three maps around where `setup` expects the frame (its nominal config, frame at its nominal place)."""
    nominal = replace(setup, frame=GoldFrame(outer=setup.frame.outer, inner=setup.frame.inner,
                                              height=setup.frame.height), instrument=Instrument())
    m = nominal.frame_motors()
    ax = lambda c, h, d: c + np.arange(-h, h + d / 2, d)  # noqa: E731
    step1 = make_scan("st_sz", ax(m.st, st_half, step), ax(m.sz, st_half, step), m)
    step2 = make_scan("srn_sz", np.arange(srn_range[0], srn_range[1] + angle_step / 2, angle_step),
                      ax(m.sz, sz_half, step / 2), m)
    srz = np.arange(srz_range[0], srz_range[1] + angle_step / 4, angle_step / 2)
    if surface:
        ms = [nominal.frame_motors(srz=a) for a in srz]
        step3 = make_scan("srz_surface", srz, np.arange(-srz_st_half, srz_st_half + step / 4, step / 2), m,
                          [q.st for q in ms], [q.sn for q in ms])
    else:
        step3 = make_scan("srz_st", srz, ax(m.st, srz_st_half, step / 2), m)
    return {"step1": step1, "step2": step2, "step3": step3}


def sn_scan(setup: Setup, sn_values, u: float | None = None, v: float | None = None) -> np.ndarray:
    """Intensity on the gold (default: the middle of the frame's right bar) against SN at SRn = ref,
    SRz = 0, ST following SN (dST = -dSN) so that the point stays on the beam and slides along it:
    the peak is SN_gold, the width the analyzer acceptance across its axis (the spot moves dSN
    across it and dSN along it)."""
    f = setup.frame
    u = f.u + (f.outer + f.inner) / 4 if u is None else u
    v = f.v if v is None else v
    m = setup.model.motors_for_target(u, v, setup.gold_w(), setup.config.srn_ref, 0.0)
    sn = np.asarray(sn_values, float)
    scan = make_scan("srz_st", np.zeros(len(sn)), np.zeros(1), m)
    scan.base["sn"] = sn.copy()
    scan.base["st"] = m.st - (sn - m.sn)
    scan.x = sn
    return setup.simulate(scan)[0]


def record_for(results: StepResults, optics, comment: str, sources: dict | None = None):
    """A CalibrationRecord (not yet saved) with the fitted constants and what was measured."""
    from .calibration import CalibrationRecord

    s = results.setup
    check = {
        "type": "gold frame (SPEM intensity maps): ST x SZ map, SZ line vs SRn, ST line vs SRz",
        "plate": s.plate.key,
        "frame": {k: v for k, v in asdict(s.frame).items()},
        "step1_st_sz": results.step1.to_dict() if results.step1 else None,
        "step2_srn_sz": results.step2.to_dict() if results.step2 else None,
        "step3_srz_st": results.step3.to_dict() if results.step3 else None,
        "motor_scales": {"st": round(s.instrument.st_scale, 5), "sz": round(s.instrument.sz_scale, 5),
                         "note": "fitted, not used by QuickAlignment (it assumes 1)"},
        "notes": list(results.notes),
        **({"sources": sources} if sources else {}),
    }
    return CalibrationRecord(comment=comment, config=s.config, optics=optics, check=check)


__all__ = [
    "GoldFrame", "Instrument", "Scan", "Setup", "FitResult", "StepResults", "KINDS",
    "make_scan", "standard_scans", "profile_edges", "map_edges", "sn_scan", "tilt_width_factor",
    "fit_st_sz", "fit_step2", "fit_step3", "setup_from_step1", "calibrate", "record_for",
]
