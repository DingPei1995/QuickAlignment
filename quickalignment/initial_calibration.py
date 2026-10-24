"""Initial calibration: fit the stage constants from a few measurement sets,
then check and correct them at test points until they are good enough.

Each measurement set: one reference feature (known plate position x, y and
height H) brought onto the beam at the analyzer focus, at a given SRn / SRz,
with the ST, SZ, SN read back (PIX = PIY = centre). Every set gives up to 3
equations; the unknowns are

    ST0, SZ0, SN_f              found from a set at SRn = ref, SRz = 0
    SRn axis (x, y)             need a set with SRn != ref (moves ST, SZ only)
    SRz axis offsets (ST, SN)   need a set with SRz != 0  (moves ST, SN only)

so the minimum is 3 sets (7 equations for 7 unknowns). More sets are fitted
by least squares and give residuals to judge the result. All 7 constants are
fitted every time.

The SRn reference angle (plate vertical) stays fixed: with a single reference
feature it cannot be separated from the SRn axis position (that would need a
second feature, i.e. the plate orientation).

Optics: the optic motor moves the optic downstream (towards the sample) when
increasing, so the optic focus is at y = optic - optic_focus along the beam,
where `optic_focus` is the optic position focusing on the analyzer focus. In a
set the feature is at the analyzer focus, so a noted optic position measures
`optic_focus` directly; it is fitted together with the stage constants.

Test points: after a fit, the feature is predicted at other rotations (ST, SZ,
SN and optic). Beamline staff go there; if the feature is not on the beam in
focus, they keep SRn, SRz and SN, bring it onto the beam with ST / SZ, focus
the optic and note ST, SZ, optic. Such a result puts the feature on the beam
at y = optic - optic_focus: 2 or 3 more equations, added to the next fit.
Found means within FOUND_TOLERANCE of the prediction: such a point only
confirms the configuration and is not fitted (it would pull the fit towards
the prediction with a 0.05 mm uncertainty). This is repeated until staff
find the feature at the predictions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

import numpy as np

from .calibration import CalibrationRecord
from .geometry import PlateGeometry
from .stage import OPTIC_TYPES, MotorPositions, OpticsCalibration, StageConfig, StageModel

FIT_PARAMS = ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")
FOUND_TOLERANCE = 0.05  # mm: the feature is "found" within this of the prediction
OPTIC_PARAM = "optic_focus"  # fitted as well when any optic position was noted
PARAM_LABELS = {
    "st0": "ST0",
    "sz0": "SZ0",
    "sn_f": "SN_f",
    "srn_axis_u": "SRn axis x",
    "srn_axis_v": "SRn axis y",
    "srz_offset_t": "SRz offset ST",
    "srz_offset_n": "SRz offset SN",
    OPTIC_PARAM: "Optic at analyzer focus",
}
# what to measure when a parameter is not determined by the data
MISSING_HINT = {
    "st0": "a set at SRn = ref, SRz = 0",
    "sz0": "a set at SRn = ref, SRz = 0",
    "sn_f": "a set at SRn = ref, SRz = 0",
    "srn_axis_u": "a set with SRn rotated (SRz = 0)",
    "srn_axis_v": "a set with SRn rotated (SRz = 0)",
    "srz_offset_t": "a set with SRz rotated (SRn = ref)",
    "srz_offset_n": "a set with SRz rotated (SRn = ref)",
    OPTIC_PARAM: "an optic position in a set",
}


@dataclass
class MeasurementSet:
    name: str
    srn: float
    srz: float
    st: float = 0.0
    sz: float = 0.0
    sn: float = 0.0
    pix: float = 150.0
    piy: float = 150.0
    use: bool = True
    optic: float | None = None  # optic position at best focus, if noted

    def motors(self) -> MotorPositions:
        return MotorPositions(st=self.st, sn=self.sn, sz=self.sz, srn=self.srn, srz=self.srz, pix=self.pix, piy=self.piy)


def protocol_sets(srn_ref: float = 120.0) -> list[MeasurementSet]:
    """The recommended sets: 1-3 are the minimum, 4-5 add redundancy."""
    return [
        MeasurementSet("1 reference", srn_ref, 0.0),
        MeasurementSet("2 SRn rotated", srn_ref + 20.0, 0.0),
        MeasurementSet("3 SRz rotated", srn_ref, -10.0),
        MeasurementSet("4 SRn rotated (check)", srn_ref - 20.0, 0.0),
        MeasurementSet("5 SRz rotated (check)", srn_ref, 10.0),
    ]


@dataclass
class TestPoint:
    """A rotation where the fitted configuration is tried out.

    `pred_*`: where the configuration puts the feature (on the beam at the
    analyzer focus, optic in focus). The answer: `found` at the prediction
    (within FOUND_TOLERANCE), or the real ST, SZ (and optic) with SRn, SRz, SN
    as given.
    """

    name: str
    srn: float
    srz: float
    round: int = 1
    sn: float = 0.0
    pix: float = 150.0
    piy: float = 150.0
    pred_st: float = 0.0
    pred_sz: float = 0.0
    pred_optic: float | None = None
    found: bool = False
    st: float | None = None
    sz: float | None = None
    optic: float | None = None

    __test__ = False  # not a pytest class

    @property
    def answered(self) -> bool:
        return self.found or self.measured

    @property
    def measured(self) -> bool:
        """Real ST, SZ entered: the point corrects the configuration."""
        return not self.found and self.st is not None and self.sz is not None

    @property
    def found_within_tolerance(self) -> bool:
        return self.found or (self.measured and max(abs(d) for d in self.deviation() if d is not None) <= FOUND_TOLERANCE)

    def real(self) -> tuple[float, float, float | None]:
        """Real (ST, SZ, optic) with the feature on the beam in focus."""
        if self.found:
            return self.pred_st, self.pred_sz, self.pred_optic
        return self.st, self.sz, self.optic

    def deviation(self) -> tuple[float, float, float | None]:
        """Real - predicted (ST, SZ, optic) at the time of the test."""
        st, sz, optic = self.real()
        d_optic = None if optic is None or self.pred_optic is None else optic - self.pred_optic
        return st - self.pred_st, sz - self.pred_sz, d_optic


def verification_angles(srn_ref: float = 120.0) -> list[tuple[str, float, float]]:
    """Rotations of the test points: other than the sets, and SRn and SRz combined."""
    return [
        ("SRn +30", srn_ref + 30.0, 0.0),
        ("SRn −30", srn_ref - 30.0, 0.0),
        ("SRz −15", srn_ref, -15.0),
        ("SRz +15", srn_ref, 15.0),
        ("SRn +20, SRz −10", srn_ref + 20.0, -10.0),
        ("SRn −20, SRz +10", srn_ref - 20.0, 10.0),
    ]


class NotEnoughData(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        hints = sorted({MISSING_HINT[p] for p in missing})
        super().__init__(
            "Not enough data to determine " + ", ".join(PARAM_LABELS[p] for p in missing) + ". Add " + "; ".join(hints) + "."
        )


def on_beam(
    model: StageModel, uvw, srn: float, srz: float, sn: float, pix: float, piy: float, optic_focus: float | None,
) -> tuple[float, float, float | None]:
    """(ST, SZ, optic) putting plate point uvw on the beam, in the optic focus, at the given SRn, SRz, SN."""
    c = model.config
    m = MotorPositions(st=c.st0, sz=c.sz0, sn=sn, srn=srn, srz=srz, pix=pix, piy=piy)
    p = model.plate_to_lab(m, *uvw)
    # +ST moves along (1, -1, 0)/sqrt2: cancel x with ST, z with SZ; the point then sits at y = p_y + p_x
    st = c.st0 - np.sqrt(2) * p[0]
    sz = c.sz0 - p[2]
    optic = None if optic_focus is None else optic_focus + float(p[1] + p[0])
    return float(st), float(sz), optic


def predict_test_point(model: StageModel, uvw, t: TestPoint, optic_focus: float | None) -> TestPoint:
    """The test point with the configuration's prediction (feature at the analyzer focus); answer cleared."""
    m = model.motors_for_target(*uvw, srn=t.srn, srz=t.srz, pix=t.pix, piy=t.piy)
    return replace(t, sn=m.sn, pred_st=m.st, pred_sz=m.sz, pred_optic=optic_focus, found=False, st=None, sz=None, optic=None)


@dataclass
class FitResult:
    config: StageConfig
    optic_focus: float | None  # optic position focusing on the analyzer focus; None: no optic position noted
    params: tuple[str, ...]
    sigma: dict[str, float] | None  # 1-sigma uncertainties, only with redundant data
    residuals: list[tuple[str, float, float, float]]  # per set: model - measured (ST, SZ, SN)
    rms: float
    dof: int
    sets: list[MeasurementSet] = field(default_factory=list)
    optic_residuals: list[tuple[str, float]] = field(default_factory=list)  # sets with an optic position
    tests: list[TestPoint] = field(default_factory=list)  # test points with real positions, fitted
    test_residuals: list[tuple[str, float, float, float | None]] = field(default_factory=list)  # ST, SZ, optic


def _residual_vector(config, optic_focus, plate, uvw, sets, tests) -> np.ndarray:
    model = StageModel(config, plate)
    out = []
    for s in sets:
        m = model.motors_for_target(*uvw, srn=s.srn, srz=s.srz, pix=s.pix, piy=s.piy)
        out += [m.st - s.st, m.sz - s.sz, m.sn - s.sn]
    for s in sets:
        if optic_focus is not None and s.optic is not None:
            out.append(optic_focus - s.optic)
    for t in tests:
        st, sz, optic = on_beam(model, uvw, t.srn, t.srz, t.sn, t.pix, t.piy, optic_focus)
        real_st, real_sz, real_optic = t.real()
        out += [st - real_st, sz - real_sz]
        if optic is not None and real_optic is not None:
            out.append(optic - real_optic)
    return np.array(out)


def fit_initial_calibration(
    sets: list[MeasurementSet],
    plate: PlateGeometry,
    ref_uvw: tuple[float, float, float],
    base: StageConfig | None = None,
    tests: list[TestPoint] | None = None,
) -> FitResult:
    """Least-squares fit of the 7 stage constants (and the optic focus position, if any optic
    position was noted) to the sets and the answered test points (Gauss-Newton, numerical
    Jacobian); `base` gives the start values and the constants that are not fitted."""
    base = base or StageConfig()
    sets = [s for s in sets if s.use]
    tests = [t for t in tests or [] if t.measured]  # found points only confirm
    optics = [s.optic for s in sets if s.optic is not None] + [t.real()[2] for t in tests if t.real()[2] is not None]
    with_optic = bool(optics)
    params = FIT_PARAMS + ((OPTIC_PARAM,) if with_optic else ())
    x = np.array([getattr(base, p) for p in FIT_PARAMS] + ([float(np.mean(optics))] if with_optic else []), float)

    def unpack(xv):
        config = replace(base, **{p: float(v) for p, v in zip(FIT_PARAMS, xv)})
        return config, (float(xv[len(FIT_PARAMS)]) if with_optic else None)

    def res(xv):
        return _residual_vector(*unpack(xv), plate, ref_uvw, sets, tests)

    def jacobian(xv):
        r0 = res(xv)
        jac = np.empty((len(r0), len(xv)))
        for i in range(len(xv)):
            step = np.zeros_like(xv)
            step[i] = 1e-6
            jac[:, i] = (res(xv + step) - r0) / 1e-6
        return jac

    if not sets:
        raise NotEnoughData(list(FIT_PARAMS))
    for _ in range(30):
        r, jac = res(x), jacobian(x)
        _, sv, vt = np.linalg.svd(jac, full_matrices=True)
        rank = int(np.sum(sv > 1e-6 * max(sv[0], 1.0)))
        if rank < len(params):
            null = vt[rank:]  # directions the data cannot see
            missing = [p for i, p in enumerate(params) if np.max(np.abs(null[:, i])) > 1e-3]
            raise NotEnoughData(missing)
        dx = np.linalg.lstsq(jac, -r, rcond=None)[0]
        x = x + dx
        if np.max(np.abs(dx)) < 1e-12:
            break

    r, jac = res(x), jacobian(x)
    dof = len(r) - len(params)
    sigma = None
    if dof > 0:
        cov = np.linalg.inv(jac.T @ jac) * float(r @ r) / dof
        sigma = {p: float(np.sqrt(max(cov[i, i], 0.0))) for i, p in enumerate(params)}
    config, optic_focus = unpack(x)

    # per-measurement residuals, in the order of _residual_vector
    per_set = [(s.name, *map(float, r[3 * i: 3 * i + 3])) for i, s in enumerate(sets)]
    k = 3 * len(sets)
    optic_res = []
    for s in sets:
        if optic_focus is not None and s.optic is not None:
            optic_res.append((s.name, float(r[k])))
            k += 1
    test_res = []
    for t in tests:
        d_st, d_sz = float(r[k]), float(r[k + 1])
        k += 2
        d_optic = None
        if optic_focus is not None and t.real()[2] is not None:
            d_optic = float(r[k])
            k += 1
        test_res.append((t.name, d_st, d_sz, d_optic))
    rms = float(np.sqrt(np.mean(r**2))) if len(r) else 0.0
    return FitResult(config, optic_focus, params, sigma, per_set, rms, dof, sets, optic_res, tests, test_res)


def optics_calibration(result: FitResult, plate: PlateGeometry, ref_uvw, optic_type: str = OPTIC_TYPES[0]) -> OpticsCalibration:
    """The optics reference of the main program: the stage as in the first set, the beam on the
    feature's surface, and the optic position focusing there (optic + = towards the sample)."""
    if result.optic_focus is None or not result.sets:
        return OpticsCalibration(optic_type=optic_type)
    cal = OpticsCalibration(enabled=True, motors=result.sets[0].motors(), surface_w=ref_uvw[2], optic_type=optic_type)
    y_ref = cal.reference_y(StageModel(result.config, plate))
    return replace(cal, optic_position=result.optic_focus + y_ref)


def optic_focus_of(record: CalibrationRecord, plate: PlateGeometry) -> float | None:
    """Optic position focusing on the analyzer focus in a configuration (None: not calibrated)."""
    if not record.optics.enabled:
        return None
    return record.optics.position_for_focus(StageModel(record.config, plate), 0.0)


def initial_record(
    result: FitResult,
    plate: PlateGeometry,
    ref_uvw: tuple[float, float, float],
    optic_type: str = OPTIC_TYPES[0],
    comment: str = "",
    tests: list[TestPoint] | None = None,
    previous: str | None = None,
) -> CalibrationRecord:
    """Configuration record from a fit. `tests`: all test points of the iteration, for the record."""
    tests = result.tests if tests is None else tests
    rounds = max((t.round for t in tests if t.answered), default=0)
    check = {
        "type": "initial calibration",
        "plate": plate.key,
        "reference_uvw": list(ref_uvw),
        "sets": [asdict(s) for s in result.sets],
        "fitted": list(result.params),
        "optic_focus": result.optic_focus,
        "rms_mm": result.rms,
        "test_rounds": rounds,
        "test_points": [asdict(t) for t in tests if t.answered],
        "test_points_fitted": len(result.tests),  # the others (last round) only checked the result
    }
    if previous is not None:
        check["previous"] = previous
    extra = f", {rounds} test round(s)" if rounds else ""
    return CalibrationRecord(
        comment=comment or f"initial calibration ({len(result.sets)} sets{extra}, rms {result.rms * 1000:.1f} um)",
        config=result.config,
        optics=optics_calibration(result, plate, ref_uvw, optic_type),
        check=check,
    )
