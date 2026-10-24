"""Stage kinematics (plate <-> lab) and optics focus tracking.

Lab frame, mm: origin = analyzer focus (= default optics focus),
+x right, +y along the beam, +z up (top view seen from +z).

Motor directions (top view):
* +ST  along t = (1, -1, 0)/sqrt2   (ST < 0 moves the sample upper-left)
* +SN  along n = (1,  1, 0)/sqrt2   (away from the analyzer, which sits at -n)
* +SZ  along z

Stack, bottom to top: ST/SN/SZ translations -> SRz -> SRn -> PIX/PIY -> plate.

Plate frame (u, v, w): see geometry.py; w is the height above the plate
back face, towards the analyzer. At SRn = 120, SRz = 0 the plate axes are
u -> t, v -> z, w -> -n, and at SN = SN_f the plate back face lies in the
analyzer focal plane, so a surface at height w is in focus for
SN = SN_f + w (e.g. SN_f + 5.0 + H for a sample of height H).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import PlateGeometry, SampleLayout

T_HAT = np.array([1.0, -1.0, 0.0]) / np.sqrt(2)
N_HAT = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
Z_HAT = np.array([0.0, 0.0, 1.0])
Y_HAT = np.array([0.0, 1.0, 0.0])
# columns: lab direction of plate u, v, w at SRn = 120, SRz = 0
B = np.column_stack([T_HAT, Z_HAT, -N_HAT])


@dataclass
class StageConfig:
    """Adjustable reference / calibration parameters of the stage."""

    st0: float = 0.0  # ST putting the plate centre on the focus
    sz0: float = 40.0  # SZ putting the plate centre on the focus
    sn_f: float = 0.0  # SN putting the plate back face in the focal plane
    srn_ref: float = 120.0  # SRn with the plate vertical, tab up
    pi_center: float = 150.0  # um
    srn_axis_u: float = 0.0  # SRn axis position on the plate (mm, plate frame, piezo centred)
    srn_axis_v: float = 0.0
    srz_offset_t: float = 0.0  # SRz axis offset from the plate-surface centre line, along +ST (mm)
    srz_offset_n: float = 0.0  # ... along +SN (mm)


@dataclass
class MotorPositions:
    st: float = 0.0
    sn: float = 0.0
    sz: float = 40.0
    srn: float = 120.0
    srz: float = 0.0
    pix: float = 150.0  # um
    piy: float = 150.0  # um


def rot_z(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rot_2d(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s], [s, c]])


class StageModel:
    def __init__(self, config: StageConfig | None = None, plate: PlateGeometry | None = None):
        self.config = config or StageConfig()
        self.plate = plate or PlateGeometry()

    # -- pieces of the transform -------------------------------------------
    def _translation(self, m: MotorPositions) -> np.ndarray:
        c = self.config
        return (m.st - c.st0) * T_HAT + (m.sn - c.sn_f) * N_HAT + (m.sz - c.sz0) * Z_HAT

    def _srz_axis_local(self) -> np.ndarray:
        """A point of the SRz axis in plate coordinates (SRn = 120, piezo centred)."""
        c = self.config
        return np.array([c.srz_offset_t, 0.0, self.plate.total_thickness - c.srz_offset_n])

    def _piezo(self, m: MotorPositions) -> np.ndarray:
        c = self.config
        return np.array([m.pix - c.pi_center, m.piy - c.pi_center]) / 1000.0

    def _srn_angle(self, m: MotorPositions) -> float:
        """CCW seen from the analyzer."""
        return m.srn - self.config.srn_ref

    @staticmethod
    def _srz_angle(m: MotorPositions) -> float:
        """Math angle about +z (SRz < 0 is CCW seen from above)."""
        return -m.srz

    # -- forward / inverse -----------------------------------------------------
    def plate_to_lab(self, m: MotorPositions, u: float, v: float, w: float) -> np.ndarray:
        c = self.config
        axis = np.array([c.srn_axis_u, c.srn_axis_v])
        q = np.array([u, v]) + self._piezo(m)
        q = rot_2d(self._srn_angle(m)) @ (q - axis) + axis
        local = np.array([q[0], q[1], w])
        a = self._srz_axis_local()
        return self._translation(m) + B @ a + rot_z(self._srz_angle(m)) @ (B @ (local - a))

    def lab_to_plate(self, m: MotorPositions, p) -> np.ndarray:
        c = self.config
        a = self._srz_axis_local()
        rel = np.asarray(p, float) - self._translation(m) - B @ a
        local = a + B.T @ (rot_z(-self._srz_angle(m)) @ rel)
        axis = np.array([c.srn_axis_u, c.srn_axis_v])
        q = rot_2d(-self._srn_angle(m)) @ (local[:2] - axis) + axis - self._piezo(m)
        return np.array([q[0], q[1], local[2]])

    def stage_frame(self, m: MotorPositions, u: float, v: float) -> np.ndarray:
        """Plate point (u, v) after piezo + SRn, in the SRz-stage frame (as seen from the analyzer at SRz = 0)."""
        c = self.config
        axis = np.array([c.srn_axis_u, c.srn_axis_v])
        q = np.array([u, v]) + self._piezo(m)
        return rot_2d(self._srn_angle(m)) @ (q - axis) + axis

    def reference_motors(self, u: float, v: float, w: float) -> tuple[float, float, float]:
        """(ST, SZ, SN) putting plate point (u, v, w) on the focus at SRn = ref, SRz = 0, piezo centred."""
        c = self.config
        return c.st0 - u, c.sz0 - v, c.sn_f + w

    def reference_to_plate(self, st: float, sz: float) -> tuple[float, float]:
        c = self.config
        return c.st0 - st, c.sz0 - sz

    def surface_normal(self, m: MotorPositions) -> np.ndarray:
        """Lab direction of the plate +w axis (towards the analyzer)."""
        return rot_z(self._srz_angle(m)) @ B[:, 2]

    def beam_hit(self, m: MotorPositions, w: float) -> np.ndarray | None:
        """Where the beam (the lab y axis) crosses the plane at plate height w."""
        normal = self.surface_normal(m)
        if abs(normal[1]) < 1e-9:
            return None
        p0 = self.plate_to_lab(m, 0.0, 0.0, w)
        s = normal @ p0 / normal[1]
        return s * Y_HAT

    def motors_for_target(
        self, u: float, v: float, w: float, srn: float, srz: float, pix: float | None = None, piy: float | None = None
    ) -> MotorPositions:
        """ST/SN/SZ putting plate point (u, v, w) on the analyzer focus for the given rotations."""
        c = self.config
        m = MotorPositions(
            st=c.st0, sn=c.sn_f, sz=c.sz0, srn=srn, srz=srz,
            pix=c.pi_center if pix is None else pix, piy=c.pi_center if piy is None else piy,
        )
        p = self.plate_to_lab(m, u, v, w)
        m.st -= p @ T_HAT
        m.sn -= p @ N_HAT
        m.sz -= p @ Z_HAT
        return m


@dataclass
class OpticsCalibration:
    """Reference state from a focusing experiment.

    At motor positions `motors`, with the beam on a surface at plate height
    `surface_w` (5.0 + H), the best focus was found at optic position
    `optic_position`. `optic_sign` is +1 if increasing the optic motor moves
    the optic downstream (towards the sample), -1 otherwise.
    """

    enabled: bool = False
    motors: MotorPositions = field(default_factory=MotorPositions)
    surface_w: float = 5.5
    optic_position: float = 0.0
    optic_sign: int = 1


@dataclass
class BeamResult:
    hit: np.ndarray | None  # lab point where the beam meets the illuminated surface
    plate_uv: tuple[float, float] | None
    surface_w: float | None
    target: str  # what the beam lands on
    focus_y: float  # y of the current optics focus (reference)
    delta: float | None  # required focus move along the beam, + = downstream (towards the sample)
    new_optic_position: float | None


def beam_on_layout(model: StageModel, m: MotorPositions, layout: SampleLayout) -> tuple[np.ndarray | None, tuple[float, float] | None, float | None, str]:
    """Find the first surface the beam meets: a sample/device, the riser, or the base plate."""
    plate = model.plate
    best = None
    for s in layout.samples:
        w = plate.total_thickness + s.height
        hit = model.beam_hit(m, w)
        if hit is None:
            continue
        u, v, _ = model.lab_to_plate(m, hit)
        u0, v0, u1, v1 = s.bounds()
        if u0 <= u <= u1 and v0 <= v <= v1 and (best is None or hit[1] < best[0][1]):
            name = s.name
            for d in s.devices:
                du, dv = d.position(s)
                if abs(u - du) <= d.length / 2 and abs(v - dv) <= d.width / 2:
                    name = f"{s.name}/{d.name}"
            best = (hit, (u, v), w, name)
    if best:
        return best
    r0, s0, r1, s1 = plate.riser_bounds()
    surfaces = []
    if plate.contact_block:
        surfaces.append((plate.contact_block_top, plate.contact_block, "contact block"))
    for w, bounds, name in surfaces + [
        (plate.total_thickness, (r0, s0, r1, s1), "riser (no sample)"),
        (plate.base_thickness, (-plate.width / 2, -plate.height / 2, plate.width / 2, plate.height / 2), "base plate"),
    ]:
        hit = model.beam_hit(m, w)
        if hit is None:
            continue
        u, v, _ = model.lab_to_plate(m, hit)
        if bounds[0] <= u <= bounds[2] and bounds[1] <= v <= bounds[3]:
            return hit, (u, v), w, name
    return None, None, None, "misses the plate"


def focus_correction(
    model: StageModel, m: MotorPositions, layout: SampleLayout, cal: OpticsCalibration
) -> BeamResult:
    """How far the optics focus must move along the beam to land on the illuminated surface."""
    hit, uv, w, target = beam_on_layout(model, m, layout)
    if cal.enabled:
        ref = model.beam_hit(cal.motors, cal.surface_w)
        focus_y = 0.0 if ref is None else float(ref[1])
    else:
        focus_y = 0.0  # optics focus at the analyzer focus
    if hit is None:
        return BeamResult(None, None, None, target, focus_y, None, None)
    delta = float(hit[1]) - focus_y
    new_pos = cal.optic_position + cal.optic_sign * delta if cal.enabled else None
    return BeamResult(hit, uv, w, target, focus_y, delta, new_pos)
