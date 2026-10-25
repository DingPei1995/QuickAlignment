"""Which SRn / SRz bring a point of a hexagonal 2-D Brillouin zone to the slit centre.

Typical use (WSe2, graphene): a map was measured at some SRn / SRz and photon
energy; on its contour (ARPES viewer, theta = deflector across, phi = slit
angle up) the user reads the angles of Gamma and of one K or M point. The
wanted geometry is a high-symmetry point (Gamma, K, M) at the centre of the
slit with the deflector near 0, and the slit along a high-symmetry line
(Gamma-K, K-M, Gamma-M, M-K), so that the analyzer distorts the data as little
as possible.

The stage has no tilt axis: SRn turns about the plate normal, SRz about the
vertical, and the plate normal always stays horizontal. With the slit
horizontal (ANTARES) a point at the slit centre with the deflector at 0
therefore always has the slit along the line through Gamma (Gamma-K for K,
Gamma-M for M); a slit across that line (K-M, M-K) needs the deflector at the
point's emission angle. In general cos(emission angle) = cos(deflector)
cos(SRz - SRz of normal emission).

For each equivalent point and each slit direction this module finds the SRn,
SRz and deflector angle that put the point at phi = 0 with the slit along the
wanted line (a 1-D root search over the deflector angle), maps them into the
SRn / SRz ranges and checks how far the point then is from the slit centre
with the deflector at 0. When nothing is reachable it says what would help:
another photon energy (capillary only), measuring the zone-edge cut with the
deflector, or remounting the sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .rotation import AnalyzerGeometry, analyzer_angles, emission_in_plate, plate_to_lab_dir, wrap180
from .stage import B, MotorPositions, StageModel

SRN_RANGE = (60.0, 180.0)  # deg, usable SRn (120 +- 60)
SRZ_RANGE = (-25.0, 10.0)  # deg, usable SRz
DEFLECTOR_OK = 5.0  # deg: |theta| of the point with the deflector at 0
SLIT_OK = 5.0  # deg: |phi| of the point (distance from the slit centre)
DEFLECTOR_GAP = 8.0  # deg: beyond this the deflector data have gaps
DEFLECTOR_MAX = 12.0  # deg
SLIT_HALF_ANGLE = 15.0  # deg, slit acceptance (preview only)
DIRECTION_TOL = 2.0  # deg: slit direction against the wanted line
HV_RANGE = (30.0, 180.0)  # eV, ANTARES (capillary)
HV_STEP = 5.0  # eV, photon energies tried when the wanted one does not work (boundaries refined to 1 eV)
ZONE_PLATE_HV = 95.0  # eV, the only photon energy of the zone plate
WORK_FUNCTION = 4.5  # eV
K0_PER_SQRT_EV = 0.5123167  # A^-1 per sqrt(eV), free-electron final state

MATERIALS = {  # in-plane lattice constant a (A)
    "Graphene": 2.46,
    "WSe2": 3.282,
    "WS2": 3.153,
    "MoSe2": 3.288,
    "MoS2": 3.160,
    "hBN": 2.504,
}

FEATURES = ("Γ", "K (K or K′)", "K only", "K′ only", "M")
LINES = {  # slit direction at the feature: (label, along the radial line Gamma -> point?)
    "Γ": (("Γ–K", None), ("Γ–M", None)),
    "K": (("Γ–K (radial)", True), ("K–M (zone edge)", False)),
    "M": (("Γ–M (radial)", True), ("M–K (zone edge)", False)),
}


def feature_kind(feature: str) -> str:
    return feature[0]


def k0(hv: float, binding: float = 0.0, work_function: float = WORK_FUNCTION) -> float:
    """|k| of the photoelectron (A^-1); binding = E - E_F of the feature (<= 0 below E_F)."""
    e_kin = hv - work_function + binding
    if e_kin <= 0:
        raise ValueError(f"No photoemission at hν = {hv:g} eV (E_kin = {e_kin:g} eV).")
    return K0_PER_SQRT_EV * np.sqrt(e_kin)


def gamma_k(a: float) -> float:
    return 4 * np.pi / (3 * a)


def gamma_m(a: float) -> float:
    return 2 * np.pi / (np.sqrt(3) * a)


@dataclass
class HexTarget:
    """What was measured, and what is wanted.

    measured: the stage at which the map was measured (only SRn, SRz matter).
    gamma, ref: (theta, phi) of Gamma and of the reference point (ref_label K
      or M) on the map, at photon energy hv_map.
    feature: one of FEATURES; line: index into LINES[kind].
    """

    a: float
    hv_map: float
    gamma: tuple[float, float]
    ref_label: str
    ref: tuple[float, float]
    measured: MotorPositions
    feature: str = "K (K or K′)"
    line: int = 0
    binding: float = 0.0
    work_function: float = WORK_FUNCTION


class SampleFrame:
    """Surface normal n and in-plane axes e1 (towards the reference point), e2 = n x e1, in the plate frame."""

    def __init__(self, model: StageModel, geo: AnalyzerGeometry, t: HexTarget):
        self.n = emission_in_plate(model, geo, t.measured, *t.gamma)
        d = emission_in_plate(model, geo, t.measured, *t.ref)
        inplane = d - (d @ self.n) * self.n
        if np.linalg.norm(inplane) < 1e-6:
            raise ValueError(f"The {t.ref_label} point and Γ are at the same angles.")
        self.e1 = inplane / np.linalg.norm(inplane)
        self.e2 = np.cross(self.n, self.e1)
        self.ref_k = k0(t.hv_map, 0.0, t.work_function) * float(np.linalg.norm(inplane))  # measured |Gamma-ref|
        self.ref_k_expected = gamma_k(t.a) if t.ref_label == "K" else gamma_m(t.a)
        self.tilt = float(np.degrees(np.arccos(np.clip(self.n[2], -1, 1))))  # from the plate normal

    def vec(self, kx, ky) -> np.ndarray:
        return np.multiply.outer(kx, self.e1) + np.multiply.outer(ky, self.e2)

    def direction(self, kx: float, ky: float, k_photo: float) -> np.ndarray:
        s = np.hypot(kx, ky) / k_photo
        if s >= 1:
            raise ValueError("The point is outside the photoemission horizon at this photon energy.")
        return np.sqrt(1 - s * s) * self.n + self.vec(kx, ky) / k_photo


def k_angle(ref_label: str) -> float:
    """In-plane angle (deg, from e1) of a K point: 0 with a K reference, 30 with an M reference."""
    return 0.0 if ref_label == "K" else 30.0


def zone_points(t: HexTarget) -> list[tuple[str, float, float]]:
    """(label, kx, ky) of the named points of the first zone (Gamma, 6 corners, 6 edge centres)."""
    ak, kk, km = k_angle(t.ref_label), gamma_k(t.a), gamma_m(t.a)
    out = [("Γ", 0.0, 0.0)]
    for i in range(6):
        a = np.radians(ak + 60 * i)
        out.append(("K" if i % 2 == 0 else "K′", kk * np.cos(a), kk * np.sin(a)))
        a = np.radians(ak + 30 + 60 * i)
        out.append(("M", km * np.cos(a), km * np.sin(a)))
    return out


def targets(t: HexTarget) -> list[tuple[str, float, float, float]]:
    """(label, kx, ky, slit direction angle in deg) of every equivalent choice of the wanted feature."""
    kind = feature_kind(t.feature)
    label, radial = LINES[kind][t.line]
    ak = k_angle(t.ref_label)
    if kind == "Γ":
        base = ak if label == "Γ–K" else ak + 30
        return [(f"Γ, slit at {wrap180(base + 60 * i):+.0f}°", 0.0, 0.0, base + 60 * i) for i in range(3)]
    out = []
    for name, kx, ky in zone_points(t):
        if name[0] != kind or (t.feature == "K only" and name != "K") or (t.feature == "K′ only" and name != "K′"):
            continue
        alpha = float(np.degrees(np.arctan2(ky, kx)))
        out.append((f"{name} at {wrap180(alpha):+.0f}°", kx, ky, alpha + (0.0 if radial else 90.0)))
    return out


# -- the slit through a direction ----------------------------------------------------------------------------
def _slit_tangent(geo: AnalyzerGeometry, theta: float, phi: float) -> np.ndarray:
    """d/dphi of the emission direction at (theta, phi), lab frame."""
    a, s, p = geo.axes()
    t, f = np.radians(theta), np.radians(phi)
    return -np.sin(t) * np.sin(f) * p + np.cos(f) * s - np.cos(t) * np.sin(f) * a


def _line_error(tangent_plate: np.ndarray, n: np.ndarray, u: np.ndarray) -> float:
    """Angle (deg, 0 ... 90) between the in-plane part of the slit tangent and the line u."""
    tin = tangent_plate - (tangent_plate @ n) * n
    c = abs(tin @ u) / max(np.linalg.norm(tin), 1e-15)
    return float(np.degrees(np.arccos(np.clip(c, 0, 1))))


def _scan(model, geo, d, n, u, alpha):
    """For SRn turns alpha (deg from SRn ref, array): deflector angle and SRz putting d at phi = 0, and the
    line misfit f (zero when the slit tangent at d is along u). Every SRn has exactly one such pose: SRn sets
    the height of d (the deflector angle), SRz turns it onto the lens axis."""
    a, s, p = geo.axes()
    al = np.radians(alpha)
    c, sn = np.cos(al), np.sin(al)
    rn = np.zeros(alpha.shape + (3, 3))
    rn[..., 0, 0], rn[..., 0, 1], rn[..., 1, 0], rn[..., 1, 1], rn[..., 2, 2] = c, -sn, sn, c, 1.0
    m0 = np.einsum("ij,njk->nik", B, rn)
    h = m0 @ d
    theta = np.degrees(np.arcsin(np.clip(h[:, 2] * p[2], -1, 1)))
    psi = np.arctan2(a[1], a[0]) - np.arctan2(h[:, 1], h[:, 0])
    cz, sz = np.cos(psi), np.sin(psi)
    back = np.stack([cz * s[0] + sz * s[1], -sz * s[0] + cz * s[1], np.full_like(psi, s[2])], axis=1)  # rot_z(psi)^T s,
    # the slit tangent at phi = 0
    t = np.einsum("nji,nj->ni", m0, back)  # m0^T: lab -> plate
    tin = t - np.outer(t @ n, n)
    f = np.cross(tin, u) @ n
    srz = (-np.degrees(psi) + 180.0) % 360.0 - 180.0
    return f, theta, srz


def solve(model, geo, d, n, u, step: float = 0.05):
    """(SRn, SRz, deflector) putting direction d at phi = 0 with the slit tangent along u.

    Only poses facing the analyzer with the deflector within 45 deg are returned."""
    if geo.slit != "horizontal":
        raise ValueError("Only the horizontal slit (ANTARES) is handled.")
    alpha = np.arange(-180.0, 180.0 + step / 2, step)
    f, theta, srz = _scan(model, geo, d, n, u, alpha)
    f0, f1 = f[:-1], f[1:]
    idx = np.nonzero((np.sign(f0) != np.sign(f1)) & (np.abs(srz[1:] - srz[:-1]) < 10))[0]
    out = []
    for i in idx:
        w = f0[i] / (f0[i] - f1[i]) if f0[i] != f1[i] else 0.0
        th = theta[i] + w * (theta[i + 1] - theta[i])
        if abs(th) < 45:
            out.append((model.config.srn_ref + alpha[i] + w * step, srz[i] + w * (srz[i + 1] - srz[i]), th))
    return out


# -- candidates --------------------------------------------------------------------------------------------
@dataclass
class Candidate:
    label: str
    srn: float  # within SRN_RANGE / SRZ_RANGE
    srz: float
    theta: float  # where the point appears with the deflector at 0
    phi: float
    direction_error: float  # deg between the slit and the wanted line
    ideal_srn: float  # without the range limits
    ideal_srz: float
    ideal_theta: float  # deflector angle needed for phi = 0 exactly
    k: tuple[float, float]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def incidence(self) -> float:
        """Beam angle from the surface normal (deg): 45 at SRz = 0, smaller for SRz < 0."""
        return abs(45.0 + self.srz)

    def offset(self) -> float:
        return max(abs(self.theta), abs(self.phi))


def _clamp(x, lo_hi):
    return float(min(max(x, lo_hi[0]), lo_hi[1]))


def _into_srn_range(srn: float) -> float:
    centre = 0.5 * sum(SRN_RANGE)
    return centre + wrap180(srn - centre)


def candidates(model: StageModel, geo: AnalyzerGeometry, t: HexTarget, hv: float,
               frame: SampleFrame | None = None) -> list[Candidate]:
    """All ways to bring the wanted feature to the slit centre at photon energy hv, best first."""
    frame = frame or SampleFrame(model, geo, t)
    kp = k0(hv, t.binding, t.work_function)
    out = []
    for label, kx, ky, beta in targets(t):
        try:
            d = frame.direction(kx, ky, kp)
        except ValueError:
            continue
        b = np.radians(beta)
        u = np.cos(b) * frame.e1 + np.sin(b) * frame.e2
        for srn, srz, theta in solve(model, geo, d, frame.n, u):
            srn = _into_srn_range(srn)
            real_srn, real_srz = _clamp(srn, SRN_RANGE), _clamp(srz, SRZ_RANGE)
            lab = plate_to_lab_dir(model, real_srn, real_srz)
            th, ph = analyzer_angles(geo, lab @ d)
            err = _line_error(lab.T @ _slit_tangent(geo, th, ph), frame.n, u)
            problems = []
            if abs(srn - real_srn) > 1e-6:
                problems.append(f"needs SRn = {srn:.1f}° (range {SRN_RANGE[0]:g} … {SRN_RANGE[1]:g}°)")
            if abs(srz - real_srz) > 1e-6:
                problems.append(f"needs SRz = {srz:.1f}° (range {SRZ_RANGE[0]:g} … {SRZ_RANGE[1]:+g}°)")
            if abs(th) > DEFLECTOR_OK:
                problems.append(f"the point is at θ = {th:.1f}° (deflector direction, wanted |θ| ≤ {DEFLECTOR_OK:g}°)")
            if abs(ph) > SLIT_OK:
                problems.append(f"the point is at φ = {ph:.1f}° along the slit (wanted |φ| ≤ {SLIT_OK:g}°)")
            if err > DIRECTION_TOL:
                problems.append(f"the slit is {err:.1f}° off the wanted line")
            out.append(Candidate(label, real_srn, real_srz, th, ph, err, srn, srz, theta, (kx, ky), problems))
    m = t.measured
    # reachable first; among those SRz <= 0 (beam closer to the normal), then the smallest turn from the map;
    # among the others the fewest problems
    out.sort(key=lambda c: (not c.ok, c.srz > 0 if c.ok else len(c.problems),
                            abs(c.srn - m.srn) + abs(c.srz - m.srz)))
    return out


# -- advice ------------------------------------------------------------------------------------------------
@dataclass
class Advice:
    hv: float
    frame: SampleFrame
    candidates: list[Candidate]
    hv_ok: list[tuple[float, float]]  # photon energy intervals (eV, within HV_RANGE) where the feature is reachable
    messages: list[str]  # what to do when it is not reachable (or remarks)
    alternative: Candidate | None = None  # zone-edge line: the radial geometry with a deflector map

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def ok(self) -> bool:
        return bool(self.candidates) and self.candidates[0].ok


def _reachable_hv(model, geo, t: HexTarget, frame: SampleFrame) -> list[tuple[float, float]]:
    """Photon energy intervals where the best candidate is reachable: HV_STEP grid, boundaries to 1 eV."""
    done = {}

    def ok(h):
        if h not in done:
            try:
                c = candidates(model, geo, t, h, frame)
            except ValueError:
                c = []
            done[h] = bool(c) and c[0].ok
        return done[h]

    grid = [float(h) for h in np.arange(HV_RANGE[0], HV_RANGE[1] + 0.5, HV_STEP)]
    for lo, hi in zip(grid, grid[1:]):
        if ok(lo) != ok(hi):
            for h in np.arange(lo + 1, hi):
                ok(float(h))
    out, start, prev = [], None, None
    for h in sorted(done):
        if done[h] and start is None:
            start = h
        if not done[h] and start is not None:
            out.append((start, prev))
            start = None
        prev = h
    if start is not None:
        out.append((start, prev))
    return out


def _hv_text(hv_ok: list[tuple[float, float]], hv: float, zone_plate: bool) -> str:
    near = min((min(max(hv, lo), hi) for lo, hi in hv_ok), key=lambda h: abs(h - hv))
    ranges = ", ".join(f"{lo:g}" if lo == hi else f"{lo:g} … {hi:g}" for lo, hi in hv_ok)
    text = f"Reachable at hν = {ranges} eV (closest: {near:g} eV)."
    if not (zone_plate and any(lo <= ZONE_PLATE_HV <= hi for lo, hi in hv_ok)):
        text += (" Other photon energies need the capillary"
                 + (" (you use the zone plate, 95 eV only: change the optic, realign it and load the capillary "
                    "configuration)." if zone_plate else "."))
    return text


def _remount_text(best: Candidate) -> str:
    if any("SRn" in p for p in best.problems) and not any("SRz" in p for p in best.problems):
        delta = best.ideal_srn - best.srn
        turn = "counter-clockwise" if delta > 0 else "clockwise"
        return (f"Not reachable at any photon energy within the SRn range: remount the sample turned by at least "
                f"{abs(delta):.0f}° {turn} on the plate (seen from the sample side, tab up); "
                f"{abs(best.ideal_srn - 120):.0f}° {turn} would bring it to SRn ≈ 120°.")
    return (f"Not reachable at any photon energy {HV_RANGE[0]:g} … {HV_RANGE[1]:g} eV within SRz "
            f"{SRZ_RANGE[0]:g} … {SRZ_RANGE[1]:+g}° and SRn {SRN_RANGE[0]:g} … {SRN_RANGE[1]:g}°: the sample has to be "
            "remounted (another orientation or a flatter mount), or another, equivalent point chosen.")


def advise(model: StageModel, geo: AnalyzerGeometry, t: HexTarget, hv: float, optic: str = "capillary") -> Advice:
    frame = SampleFrame(model, geo, t)
    cands = candidates(model, geo, t, hv, frame)
    kind = feature_kind(t.feature)
    zone_plate = "zone" in optic
    msgs = []
    if zone_plate and abs(hv - ZONE_PLATE_HV) > 0.01:
        msgs.append(f"The zone plate works at {ZONE_PLATE_HV:g} eV only: another photon energy needs the capillary.")
    if not HV_RANGE[0] <= hv <= HV_RANGE[1]:
        msgs.append(f"ANTARES photon energy range: {HV_RANGE[0]:g} … {HV_RANGE[1]:g} eV (capillary).")
    ok_here = bool(cands) and cands[0].ok
    hv_ok = _reachable_hv(model, geo, t, frame) if not ok_here and kind != "Γ" else []
    alternative = None
    radial = LINES[kind][t.line][1]
    if not ok_here:
        if radial is False:
            point, edge = LINES[kind][0][0].split(" ")[0], LINES[kind][1][0].split(" ")[0]
            msgs.append(f"With the point at the slit centre and the deflector near 0 the slit runs along {point} "
                        "(no tilt axis); across it needs the deflector at about the emission angle of the point.")
        if hv_ok:
            msgs.append(_hv_text(hv_ok, hv, zone_plate))
        if radial is False:
            alt = advise(model, geo, HexTarget(**{**t.__dict__, "line": 0}), hv, optic)
            how = (f"the deflector then runs along {edge}, and a short deflector map (|θ| ≤ {DEFLECTOR_OK:g}°) "
                   "gives that cut through the point with little distortion.")
            if alt.ok:
                alternative = alt.best
                msgs.append(f"Alternative: put the point at the centre with the slit along {point} (SRn = "
                            f"{alternative.srn:.2f}°, SRz = {alternative.srz:.2f}°): {how}")
            elif alt.hv_ok:
                msgs.append(f"Alternative: the point at the centre with the slit along {point}, {how} "
                            f"{_hv_text(alt.hv_ok, hv, zone_plate)}")
            elif not hv_ok:
                msgs += [m for m in alt.messages if m.startswith("Not reachable")]
        elif not hv_ok and cands:
            msgs.append(_remount_text(cands[0]))
    if frame.tilt > 3.0:
        msgs.append(f"Γ is {frame.tilt:.1f}° from the plate normal: the sample is mounted tilted (no tilt axis to "
                    "correct it; the solutions above include it).")
    ratio = frame.ref_k / frame.ref_k_expected
    if abs(ratio - 1) > 0.1:
        msgs.append(f"Check the input: Γ–{t.ref_label} on the map is {frame.ref_k:.3f} Å⁻¹, the lattice gives "
                    f"{frame.ref_k_expected:.3f} Å⁻¹ ({(ratio - 1) * 100:+.0f}%: lattice constant, point or "
                    "photon energy wrong?).")
    return Advice(hv, frame, cands, hv_ok, msgs, alternative)


# -- preview ------------------------------------------------------------------------------------------------
def k_to_angles(model, geo, frame: SampleFrame, kp: float, srn: float, srz: float, kxy: np.ndarray):
    """(theta, phi) arrays of in-plane momenta kxy (N, 2) at the stage angles; NaN where not seen."""
    kxy = np.atleast_2d(kxy)
    s2 = (kxy ** 2).sum(axis=1) / kp ** 2
    with np.errstate(invalid="ignore"):
        d = np.sqrt(1 - s2)[:, None] * frame.n + frame.vec(kxy[:, 0], kxy[:, 1]) / kp
    lab = d @ plate_to_lab_dir(model, srn, srz).T
    a, s, p = geo.axes()
    th = np.degrees(np.arctan2(lab @ p, lab @ a))
    ph = np.degrees(np.arcsin(np.clip(lab @ s, -1, 1)))
    bad = (s2 >= 1) | (lab @ a <= 0)
    th[bad] = ph[bad] = np.nan
    return th, ph


def angles_to_k(model, geo, frame: SampleFrame, kp: float, srn: float, srz: float, theta, phi) -> np.ndarray:
    """In-plane momenta (N, 2) seen at analyzer angles (theta, phi)."""
    a, s, p = geo.axes()
    t, f = np.radians(np.asarray(theta, float)), np.radians(np.asarray(phi, float))
    e = (np.multiply.outer(np.sin(t) * np.cos(f), p) + np.multiply.outer(np.sin(f), s)
         + np.multiply.outer(np.cos(t) * np.cos(f), a))
    d = e @ plate_to_lab_dir(model, srn, srz)
    return kp * np.stack([d @ frame.e1, d @ frame.e2], axis=-1)


def map_axes(model, geo, frame: SampleFrame, m: MotorPositions) -> np.ndarray:
    """2 x 2 matrix taking (kx, ky) of the sample frame to the axes of a map measured at m: k along the
    deflector across, k along the slit up (as on ARPES viewer's contour)."""
    _, s, p = geo.axes()
    lab = plate_to_lab_dir(model, m.srn, m.srz)
    rows = []
    for v in (p, s):
        v = lab.T @ v
        rows.append([v @ frame.e1, v @ frame.e2])
    q, r = np.linalg.qr(np.array(rows).T)  # orthonormalise, keeping the deflector axis
    return (q * np.sign(np.diag(r))).T


def zone_edges(t: HexTarget, rings: int = 2, n: int = 40) -> list[np.ndarray]:
    """Edges (polylines of (n, 2) in-plane momenta) of the first zone and its neighbours."""
    ak, kk = np.radians(k_angle(t.ref_label)), gamma_k(t.a)
    corners = np.array([[kk * np.cos(ak + i * np.pi / 3), kk * np.sin(ak + i * np.pi / 3)] for i in range(7)])
    g = 2 * gamma_m(t.a)
    g1 = g * np.array([np.cos(ak + np.pi / 6), np.sin(ak + np.pi / 6)])
    g2 = g * np.array([np.cos(ak + np.pi / 2), np.sin(ak + np.pi / 2)])
    s = np.linspace(0, 1, n)[:, None]
    out = []
    for i in range(-rings, rings + 1):
        for j in range(-rings, rings + 1):
            if abs(i + j) > rings and abs(i) + abs(j) > rings:
                continue
            c = i * g1 + j * g2
            out += [c + corners[q] + s * (corners[q + 1] - corners[q]) for q in range(6)]
    return out


def draw_preview(fig, model, geo, t: HexTarget, hv: float, cand: Candidate | None, frame: SampleFrame) -> None:
    """Left: the map at the candidate's SRn / SRz (deflector across, slit angle up). Right: the same in k."""
    fig.clear()
    left, right = fig.subplots(1, 2)
    kp = k0(hv, t.binding, t.work_function)
    srn, srz = (cand.srn, cand.srz) if cand else (t.measured.srn, t.measured.srz)
    edges = zone_edges(t)
    points = zone_points(t)
    # -- angles
    for e in edges:
        th, ph = k_to_angles(model, geo, frame, kp, srn, srz, e)
        left.plot(th, ph, color="0.35", lw=0.9)
    for name, kx, ky in points:
        th, ph = k_to_angles(model, geo, frame, kp, srn, srz, np.array([[kx, ky]]))
        if np.isfinite(th[0]) and abs(ph[0]) < SLIT_HALF_ANGLE + 3:
            left.plot(th, ph, "o", ms=3, color="#1f4e9c")
            left.annotate(name, (th[0], ph[0]), xytext=(3, 3), textcoords="offset points", fontsize=9, color="#1f4e9c")
    for lo, hi, color in ((DEFLECTOR_GAP, DEFLECTOR_MAX, "#f3c9c9"), (DEFLECTOR_MAX, 30, "#dddddd")):
        for sgn in (1, -1):
            left.axvspan(sgn * lo, sgn * hi, color=color, zorder=0, lw=0)
    left.add_patch(_rect(-DEFLECTOR_OK, -SLIT_OK, 2 * DEFLECTOR_OK, 2 * SLIT_OK, "#2a9d4b"))
    left.axvline(0, color="#e07b00", lw=1.5, label="slit (deflector 0)")
    left.axhline(0, color="0.6", lw=0.6, ls=":")
    if cand:
        left.plot([cand.theta], [cand.phi], "*", ms=13, color="#d62728", label=cand.label.split(" ")[0])
    xlim = max(18.0, abs(cand.theta) + 3 if cand else 0.0)
    left.set_xlim(-xlim, xlim)
    left.set_ylim(-SLIT_HALF_ANGLE - 3, SLIT_HALF_ANGLE + 3)
    left.set_xlabel("θ, deflector (°)")
    left.set_ylabel("φ, along the slit (°)")
    left.set_title(f"Map at SRn = {srn:.1f}°, SRz = {srz:.1f}°", fontsize=10)
    left.set_aspect("equal")
    left.legend(fontsize=8, loc="lower right")
    # -- momentum, drawn like the current map (deflector across, slit up)
    view = map_axes(model, geo, frame, t.measured)
    for e in edges:
        e = e @ view.T
        right.plot(e[:, 0], e[:, 1], color="0.35", lw=0.9)
    for name, kx, ky in points:
        x, y = view @ (kx, ky)
        right.plot([x], [y], "o", ms=3, color="#1f4e9c")
        right.annotate(name, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=9, color="#1f4e9c")
    phis = np.linspace(-SLIT_HALF_ANGLE, SLIT_HALF_ANGLE, 61)

    def window(th_max, m_srn, m_srz):
        ths = np.linspace(-th_max, th_max, 41)
        th = np.concatenate([ths, np.full_like(phis, th_max), ths[::-1], np.full_like(phis, -th_max)])
        ph = np.concatenate([np.full_like(ths, -SLIT_HALF_ANGLE), phis, np.full_like(ths, SLIT_HALF_ANGLE), phis[::-1]])
        return angles_to_k(model, geo, frame, kp, m_srn, m_srz, th, ph) @ view.T

    m = t.measured
    w = window(DEFLECTOR_MAX, m.srn, m.srz)
    right.plot(w[:, 0], w[:, 1], color="0.55", ls="--", lw=1, label=f"map now (SRn {m.srn:g}, SRz {m.srz:g})")
    if cand:
        w = window(DEFLECTOR_MAX, srn, srz)
        right.plot(w[:, 0], w[:, 1], color="#e07b00", lw=1, label=f"new, |θ| ≤ {DEFLECTOR_MAX:g}°")
        w = window(DEFLECTOR_GAP, srn, srz)
        right.fill(w[:, 0], w[:, 1], color="#e07b00", alpha=0.12, lw=0, label=f"new, |θ| ≤ {DEFLECTOR_GAP:g}°")
        slit = angles_to_k(model, geo, frame, kp, srn, srz, np.zeros_like(phis), phis) @ view.T
        right.plot(slit[:, 0], slit[:, 1], color="#e07b00", lw=2.2, label="slit, deflector 0")
        x, y = view @ cand.k
        right.plot([x], [y], "*", ms=13, color="#d62728")
    lim = max(2.2 * gamma_k(t.a), 1.15 * kp * np.sin(np.radians(25)))
    right.set_xlim(-lim, lim)
    right.set_ylim(-lim, lim)
    right.set_aspect("equal")
    right.set_xlabel("k along the deflector of the current map (Å⁻¹)")
    right.set_ylabel("k along its slit (Å⁻¹)")
    right.set_title(f"2D BZ at hν = {hv:g} eV", fontsize=10)
    right.legend(fontsize=7, loc="lower right")
    fig.tight_layout()


def _rect(x, y, w, h, color):
    from matplotlib.patches import Rectangle

    return Rectangle((x, y), w, h, fill=False, ls="--", lw=1.2, color=color)


__all__ = [
    "Advice", "Candidate", "DEFLECTOR_GAP", "DEFLECTOR_MAX", "DEFLECTOR_OK", "FEATURES", "HV_RANGE", "HexTarget",
    "LINES", "MATERIALS", "SLIT_OK", "SRN_RANGE", "SRZ_RANGE", "SampleFrame", "WORK_FUNCTION", "ZONE_PLATE_HV",
    "advise", "angles_to_k", "candidates", "draw_preview", "feature_kind", "gamma_k", "gamma_m", "k0", "k_to_angles",
    "solve", "targets", "zone_points",
]
