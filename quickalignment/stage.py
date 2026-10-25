"""Stage kinematics (plate <-> lab) and optics focus tracking.

Lab frame, mm: origin = analyzer focus (= default optics focus),
+x right, +y along the beam, +z up (top view seen from +z).

Motor directions (top view):
* +ST  along t = (1, -1, 0)/sqrt2   (ST < 0 moves the sample upper-left)
* +SN  along n = (1,  1, 0)/sqrt2   (away from the analyzer, which sits at -n)
* +SZ  along z

Stack, bottom to top: ST/SN/SZ translations -> SRz -> SRn -> PIX/PIY -> plate.

Plate frame (u, v, w): see geometry.py. It is fixed to the back plate,
which is identical for all plate types: w is the height above the back
face, towards the analyzer. At SRn = 120, SRz = 0 the plate axes are
u -> t, v -> z, w -> -n. At SN = SN_f the riser top of the standard plate
(w = SN_REFERENCE_W = 5.0) lies in the analyzer focal plane, whatever plate is
mounted, so a surface at height w is in focus for SN = SN_f + (w - 5.0):
SN = SN_f + H for a sample of height H on a 5.0 mm plate, and
SN = SN_f + (h - 5.0) + H on a custom plate whose block top is at h.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import SN_REFERENCE_W, PlateGeometry, SampleLayout

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
    sn_f: float = 0.0  # SN putting the standard plate's riser top (w = 5.0) in the focal plane
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
        # + SN_REFERENCE_W: SN_f refers to the standard riser top, not the back face
        return (m.st - c.st0) * T_HAT + (m.sn - c.sn_f + SN_REFERENCE_W) * N_HAT + (m.sz - c.sz0) * Z_HAT

    def _srz_axis_local(self) -> np.ndarray:
        """A point of the SRz axis in plate coordinates (SRn = 120, piezo centred)."""
        c = self.config
        return np.array([c.srz_offset_t, 0.0, SN_REFERENCE_W - c.srz_offset_n])  # fixed to the stage

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

    def plate_from_stage_frame(self, m: MotorPositions, q) -> np.ndarray:
        """Inverse of stage_frame: plate point (u, v) seen at stage-frame point q."""
        c = self.config
        axis = np.array([c.srn_axis_u, c.srn_axis_v])
        return rot_2d(-self._srn_angle(m)) @ (np.asarray(q, float) - axis) + axis - self._piezo(m)

    def reference_motors(self, u: float, v: float, w: float) -> tuple[float, float, float]:
        """(ST, SZ, SN) putting plate point (u, v, w) on the focus at SRn = ref, SRz = 0, piezo centred."""
        c = self.config
        return c.st0 - u, c.sz0 - v, c.sn_f + w - SN_REFERENCE_W

    def focal_plane_height(self, m: MotorPositions) -> float:
        """Plate height w of the surface that lies in the analyzer focal plane at these positions
        (the camera "SN = 0" line), measured along the plate normal through the analyzer focus."""
        return float(self.lab_to_plate(m, np.zeros(3))[2])

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
            st=c.st0, sn=c.sn_f - SN_REFERENCE_W, sz=c.sz0, srn=srn, srz=srz,
            pix=c.pi_center if pix is None else pix, piy=c.pi_center if piy is None else piy,
        )
        p = self.plate_to_lab(m, u, v, w)
        m.st -= p @ T_HAT
        m.sn -= p @ N_HAT
        m.sz -= p @ Z_HAT
        return m


def found_offset(model: StageModel, m: MotorPositions, u: float, v: float, w: float) -> tuple[float, float, float]:
    """(du, dv, dw) from the expected plate point (u, v, w) to the one really on the analyzer focus at m.

    Use when the target was found on the beam, in the analyzer focus, at the
    stage positions m: moving its sample by (du, dv) and its height by dw makes
    the model put it there (and the sample's other devices with it).
    """
    pu, pv, pw = model.lab_to_plate(m, np.zeros(3))
    return float(pu - u), float(pv - v), float(pw - w)


OPTIC_TYPES = ("zone plate + OSA", "capillary")


@dataclass
class OpticsCalibration:
    """Focusing optic (zone plate + OSA or capillary), only along the beam.

    `optic_position` is the absolute optic motor position that puts the focus
    on the reference point: the analyzer focus, or, when `enabled`, the point
    where the beam met a surface at plate height `surface_w` with the stage at
    `motors` (a measured reference). `optic_sign` is +1 if increasing the optic
    motor moves the optic downstream (towards the sample), -1 otherwise.
    """

    enabled: bool = False
    motors: MotorPositions = field(default_factory=MotorPositions)
    surface_w: float = 5.5
    optic_position: float = 0.0
    optic_sign: int = 1
    optic_type: str = OPTIC_TYPES[0]
    last_position: float | None = None  # optic position when the configuration was saved

    @property
    def current_position(self) -> float:
        return self.optic_position if self.last_position is None else self.last_position

    def reference_y(self, model: StageModel) -> float:
        """Position along the beam of the focus when the optic is at `optic_position`."""
        if not self.enabled:
            return 0.0  # the analyzer focus
        ref = model.beam_hit(self.motors, self.surface_w)
        return 0.0 if ref is None else float(ref[1])

    def position_for_focus(self, model: StageModel, y: float) -> float:
        """Absolute optic position putting the focus at y along the beam."""
        return self.optic_position + self.optic_sign * (y - self.reference_y(model))

    def focus_for_position(self, model: StageModel, position: float) -> float:
        """Focus position along the beam for an absolute optic position."""
        return self.reference_y(model) + self.optic_sign * (position - self.optic_position)


@dataclass
class BeamResult:
    hit: np.ndarray | None  # lab point where the beam meets the illuminated surface
    plate_uv: tuple[float, float] | None
    surface_w: float | None
    target: str  # what the beam lands on
    optic_position: float  # absolute optic position used (entered, or the configuration's)
    focus_y: float  # focus position along the beam for that optic position
    required_optic_position: float | None  # absolute optic position for focus on the illuminated surface

    @property
    def delta(self) -> float | None:
        """Distance from the focus to the illuminated surface along the beam (+ = surface downstream)."""
        return None if self.hit is None else float(self.hit[1]) - self.focus_y


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
        (plate.total_thickness, (r0, s0, r1, s1), "plate surface (no sample)"),
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
    model: StageModel,
    m: MotorPositions,
    layout: SampleLayout,
    cal: OpticsCalibration,
    optic_position: float | None = None,
) -> BeamResult:
    """Where the beam lands and the absolute optic position that focuses there.

    `optic_position` is the current absolute optic position (default: the
    configuration's reference position).
    """
    position = cal.optic_position if optic_position is None else optic_position
    focus_y = cal.focus_for_position(model, position)
    hit, uv, w, target = beam_on_layout(model, m, layout)
    required = None if hit is None else cal.position_for_focus(model, float(hit[1]))
    return BeamResult(hit, uv, w, target, position, focus_y, required)
