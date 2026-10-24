"""Calibration configurations and the reference-sample check.

Files in the configuration folder (default: ``configs/`` next to the program):

* ``calibration_YYYY-MM-DD_HHMMSS_<optic>.json`` (optic: ``capillary`` or
  ``zone_plate``): one file per calibration made by
  beamline staff (initial calibration, accepted reference check, expert edit).
* ``user_config.json``: the single user configuration, overwritten each time
  the user saves on closing the program; its first entry is the save time.

At start-up the newest of all of them (by its time stamp) is loaded. A check
with the reference sample compares where the sample was actually found with
where the current calibration predicts it; accepting it writes a new dated file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path

from .geometry import PlateGeometry
from .stage import MotorPositions, OpticsCalibration, StageConfig, StageModel

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "configs"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
USER_FILE = "user_config.json"


def _from_dict(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class CalibrationRecord:
    created: str = ""  # TIME_FORMAT; empty for the built-in default
    comment: str = "built-in default (no configuration file)"
    config: StageConfig = field(default_factory=StageConfig)
    optics: OpticsCalibration = field(default_factory=OpticsCalibration)
    check: dict | None = None  # what the reference check measured, for the record
    path: Path | None = None
    kind: str = "staff"  # "staff" (dated calibration file) or "user" (user_config.json)

    @property
    def label(self) -> str:
        """Name shown in the program: save time and optic type only."""
        if not self.created:
            return "default"
        return f"{self.created} {self.optic_name}"

    @property
    def optic_name(self) -> str:
        return "capillary" if "capillary" in self.optics.optic_type else "zone plate"

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "kind": self.kind,
            "comment": self.comment,
            "stage_config": asdict(self.config),
            "optics": asdict(self.optics),
            "check": self.check,
        }

    @classmethod
    def from_dict(cls, data: dict, path: Path | None = None) -> CalibrationRecord:
        optics = dict(data.get("optics", {}))
        optics["motors"] = _from_dict(MotorPositions, optics.get("motors", {}))
        return cls(
            created=data.get("created", ""),
            comment=data.get("comment", ""),
            config=_from_dict(StageConfig, data.get("stage_config", {})),
            optics=_from_dict(OpticsCalibration, optics),
            check=data.get("check"),
            path=path,
            kind=data.get("kind", "staff"),
        )


class CalibrationStore:
    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder) if folder else DEFAULT_FOLDER

    def records(self) -> list[CalibrationRecord]:
        """All readable configurations, newest first."""
        out = []
        for path in [*self.folder.glob("calibration_*.json"), self.folder / USER_FILE]:
            if not path.exists():
                continue
            try:
                out.append(CalibrationRecord.from_dict(json.loads(path.read_text()), path))
            except (OSError, ValueError, TypeError):
                continue
        return sorted(out, key=lambda r: (r.created, r.path.name), reverse=True)

    def latest(self) -> CalibrationRecord:
        """The most recently written configuration, user or staff."""
        records = self.records()
        return records[0] if records else CalibrationRecord()

    def save_user(self, record: CalibrationRecord, now: datetime | None = None) -> CalibrationRecord:
        """Overwrite user_config.json with `record`, time-stamped at the top of the file."""
        now = now or datetime.now()
        self.folder.mkdir(parents=True, exist_ok=True)
        based_on = record.label if record.kind == "staff" else (record.check or {}).get("based_on", record.label)
        record = replace(
            record, created=now.strftime(TIME_FORMAT), kind="user",
            comment=f"user configuration (based on {based_on})", check={"based_on": based_on},
        )
        path = self.folder / USER_FILE
        path.write_text(json.dumps(record.to_dict(), indent=2))
        return replace(record, path=path)

    def save(self, record: CalibrationRecord, now: datetime | None = None) -> CalibrationRecord:
        now = now or datetime.now()
        self.folder.mkdir(parents=True, exist_ok=True)
        record = replace(record, created=now.strftime(TIME_FORMAT), kind="staff")
        stem = f"calibration_{now:%Y-%m-%d_%H%M%S}_{record.optic_name.replace(' ', '_')}"
        path = self.folder / f"{stem}.json"
        i = 1
        while path.exists():
            path = self.folder / f"{stem}_{i}.json"
            i += 1
        path.write_text(json.dumps(record.to_dict(), indent=2))
        return replace(record, path=path)


@dataclass
class CheckResult:
    target: str
    measured: MotorPositions
    predicted: MotorPositions
    delta_st: float
    delta_sz: float
    delta_sn: float
    measured_optic: float
    predicted_optic: float | None
    new_record: CalibrationRecord

    @property
    def delta_optic(self) -> float | None:
        return None if self.predicted_optic is None else self.measured_optic - self.predicted_optic


def check_reference(
    record: CalibrationRecord,
    plate: PlateGeometry,
    target: str,
    uvw: tuple[float, float, float],
    measured: MotorPositions,
    measured_optic: float,
    comment: str = "",
) -> CheckResult:
    """Compare a measured reference position with the current calibration.

    `measured` are the stage positions with the reference point `uvw` (plate
    frame) on the beam at the analyzer focus, `measured_optic` the optic
    position at best focus there. The proposed new record shifts ST0 / SZ0 /
    SN_f by the measured deviations and takes this state as optics reference.
    """
    model = StageModel(record.config, plate)
    u, v, w = uvw
    predicted = model.motors_for_target(u, v, w, measured.srn, measured.srz, measured.pix, measured.piy)
    d_st, d_sz, d_sn = measured.st - predicted.st, measured.sz - predicted.sz, measured.sn - predicted.sn

    cal = record.optics
    hit = model.beam_hit(measured, w)
    predicted_optic = None if hit is None else cal.position_for_focus(model, float(hit[1]))

    c = record.config
    new_record = CalibrationRecord(
        comment=comment or f"reference check on {target}",
        config=replace(c, st0=c.st0 + d_st, sz0=c.sz0 + d_sz, sn_f=c.sn_f + d_sn),
        optics=replace(cal, enabled=True, motors=measured, surface_w=w, optic_position=measured_optic),
        check={
            "target": target,
            "plate": plate.key,
            "uvw": list(uvw),
            "measured": asdict(measured),
            "measured_optic": measured_optic,
            "previous": record.label,
            "deltas": {"st": d_st, "sz": d_sz, "sn": d_sn},
        },
    )
    return CheckResult(target, measured, predicted, d_st, d_sz, d_sn, measured_optic, predicted_optic, new_record)
