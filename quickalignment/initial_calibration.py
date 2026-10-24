"""Initial calibration: fit the stage constants from a few measurement sets.

Each measurement set: one reference feature (known plate position x, y and
height H) brought onto the beam at the analyzer focus, at a given SRn / SRz,
with the ST, SZ, SN read back (PIX = PIY = centre). Every set gives up to 3
equations; the unknowns are

    ST0, SZ0, SN_f              found from a set at SRn = ref, SRz = 0
    SRn axis (x, y)             need a set with SRn != ref (moves ST, SZ only)
    SRz axis offsets (ST, SN)   need a set with SRz != 0  (moves ST, SN only)

so the minimum is 3 sets (7 equations for 7 unknowns). More sets are fitted
by least squares and give residuals to judge the result.

The SRn reference angle (plate vertical) stays fixed: with a single reference
feature it cannot be separated from the SRn axis position (that would need a
second feature, i.e. the plate orientation).

A correction of an existing configuration fits only ST0, SZ0, SN_f (the axes
are kept from it): one set is enough.

The optic position at best focus may be noted in every set. The feature is on
the beam at the analyzer focus each time, so every noted position predicts the
optics reference; their mean is taken and the scatter shows how well the optic
focus can be reproduced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

import numpy as np

from .calibration import CalibrationRecord
from .geometry import PlateGeometry
from .stage import OPTIC_TYPES, MotorPositions, OpticsCalibration, StageConfig, StageModel

FIT_PARAMS = ("st0", "sz0", "sn_f", "srn_axis_u", "srn_axis_v", "srz_offset_t", "srz_offset_n")
CORRECTION_PARAMS = ("st0", "sz0", "sn_f")  # correction of an existing configuration: axes kept
PARAM_LABELS = {
    "st0": "ST0",
    "sz0": "SZ0",
    "sn_f": "SN_f",
    "srn_axis_u": "SRn axis x",
    "srn_axis_v": "SRn axis y",
    "srz_offset_t": "SRz offset ST",
    "srz_offset_n": "SRz offset SN",
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


class NotEnoughData(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        hints = sorted({MISSING_HINT[p] for p in missing})
        super().__init__(
            "Not enough data to determine " + ", ".join(PARAM_LABELS[p] for p in missing) + ". Add " + "; ".join(hints) + "."
        )


@dataclass
class FitResult:
    config: StageConfig
    params: tuple[str, ...]
    sigma: dict[str, float] | None  # 1-sigma uncertainties, only with redundant data
    residuals: list[tuple[str, float, float, float]]  # per set: model - measured (ST, SZ, SN)
    rms: float
    dof: int
    sets: list[MeasurementSet] = field(default_factory=list)


def _residuals(config: StageConfig, plate: PlateGeometry, ref_uvw, sets) -> np.ndarray:
    model = StageModel(config, plate)
    out = []
    for s in sets:
        m = model.motors_for_target(*ref_uvw, srn=s.srn, srz=s.srz, pix=s.pix, piy=s.piy)
        out += [m.st - s.st, m.sz - s.sz, m.sn - s.sn]
    return np.array(out)


def fit_initial_calibration(
    sets: list[MeasurementSet],
    plate: PlateGeometry,
    ref_uvw: tuple[float, float, float],
    base: StageConfig | None = None,
    params: tuple[str, ...] = FIT_PARAMS,
) -> FitResult:
    """Least-squares fit of the stage constants `params` (Gauss-Newton, numerical
    Jacobian); the other constants are kept from `base`."""
    base = base or StageConfig()
    sets = [s for s in sets if s.use]
    x = np.array([getattr(base, p) for p in params], float)

    def res(xv):
        return _residuals(replace(base, **dict(zip(params, xv))), plate, ref_uvw, sets)

    def jacobian(xv):
        r0 = res(xv)
        jac = np.empty((len(r0), len(xv)))
        for i in range(len(xv)):
            step = np.zeros_like(xv)
            step[i] = 1e-6
            jac[:, i] = (res(xv + step) - r0) / 1e-6
        return jac

    if not sets:
        raise NotEnoughData(list(params))
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
    per_set = [(s.name, *map(float, r[3 * i: 3 * i + 3])) for i, s in enumerate(sets)]
    rms = float(np.sqrt(np.mean(r**2))) if len(r) else 0.0
    config = replace(base, **{p: float(v) for p, v in zip(params, x)})
    return FitResult(config, params, sigma, per_set, rms, dof, sets)


@dataclass
class OpticsFit:
    optics: OpticsCalibration
    residuals: list[tuple[str, float]]  # per set with an optic position: model - measured
    rms: float
    sigma: float | None  # 1-sigma of the reference position, with 2 or more positions


def fit_optics(
    result: FitResult,
    plate: PlateGeometry,
    ref_uvw: tuple[float, float, float],
    optic_sign: int = 1,
    optic_type: str = OPTIC_TYPES[0],
) -> OpticsFit:
    """Optics reference from the optic positions noted in the sets.

    The reference state is the first set with an optic position. Each noted
    position, moved along the beam by the fitted model from where the beam met
    the feature in its set to where it met it in the reference set, predicts
    the reference position; the mean is used. Without any optic position the
    reference stays at the analyzer focus (not calibrated).
    """
    noted = [s for s in result.sets if s.optic is not None]
    if not noted:
        return OpticsFit(OpticsCalibration(optic_sign=optic_sign, optic_type=optic_type), [], 0.0, None)
    model = StageModel(result.config, plate)
    w = ref_uvw[2]
    cal = OpticsCalibration(
        enabled=True, motors=noted[0].motors(), surface_w=w, optic_sign=optic_sign, optic_type=optic_type,
    )
    y_ref = cal.reference_y(model)
    hits = [model.beam_hit(s.motors(), w) for s in noted]
    ys = [y_ref if h is None else float(h[1]) for h in hits]
    predicted = np.array([s.optic - optic_sign * (y - y_ref) for s, y in zip(noted, ys)])
    cal = replace(cal, optic_position=float(predicted.mean()))
    residuals = [(s.name, cal.position_for_focus(model, y) - s.optic) for s, y in zip(noted, ys)]
    r = np.array([d for _, d in residuals])
    sigma = float(predicted.std(ddof=1) / np.sqrt(len(noted))) if len(noted) > 1 else None
    return OpticsFit(cal, residuals, float(np.sqrt(np.mean(r**2))), sigma)


def initial_record(
    result: FitResult,
    plate: PlateGeometry,
    ref_uvw: tuple[float, float, float],
    optic_sign: int = 1,
    optic_type: str = OPTIC_TYPES[0],
    comment: str = "",
    base_label: str | None = None,
    kept_optics: OpticsCalibration | None = None,
) -> CalibrationRecord:
    """Configuration record from a fit, with the optics reference from the sets' optic positions.

    `base_label`: the configuration that was corrected (correction fit), for the record.
    `kept_optics`: optics reference used when no set has an optic position
    (e.g. the corrected configuration's).
    """
    optics = fit_optics(result, plate, ref_uvw, optic_sign, optic_type)
    if not optics.residuals and kept_optics is not None:
        optics = replace(optics, optics=replace(kept_optics, optic_type=optic_type, last_position=None))
    kind = "initial calibration" if set(result.params) >= set(FIT_PARAMS) else "configuration correction"
    check = {
        "type": kind,
        "plate": plate.key,
        "reference_uvw": list(ref_uvw),
        "sets": [asdict(s) for s in result.sets],
        "fitted": list(result.params),
        "rms_mm": result.rms,
        "optic_residuals": [d for _, d in optics.residuals],
    }
    if base_label is not None:
        check["base"] = base_label
    return CalibrationRecord(
        comment=comment or f"{kind} ({len(result.sets)} sets, rms {result.rms * 1000:.1f} um)",
        config=result.config,
        optics=optics.optics,
        check=check,
    )
