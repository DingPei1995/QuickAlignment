"""Calibration configurations and the reference-sample check.

Files in the configuration folder (default: ``configs/`` next to the program):

* ``calibration_YYYY-MM-DD_HHMMSS_<optic>.json`` (optic: ``capillary`` or
  ``zone_plate``): one file per calibration made by beamline staff with
  InitialCalibration.py. QuickAlignment only reads them.

At start-up the newest of them (by its time stamp) made with the chosen optic
is loaded.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path

from .collision import CollisionGeometry, default_geometry
from .fileio import read_json, write_json
from .stage import MotorPositions, OpticsCalibration, StageConfig

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "configs"
LIMITS_FILE = "motor_limits.json"  # motor limits set by hand in the Configuration window
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _from_dict(cls, data: dict):
    """cls from the known keys of data, numbers converted (ValueError / TypeError for wrong values)."""
    if not isinstance(data, dict):
        raise ValueError(f"{cls.__name__}: expected a JSON object.")
    out = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value, default = data[f.name], f.default
        if isinstance(default, bool):
            value = bool(value)
        elif isinstance(default, (int, float)) or (default is None and value is not None and f.name != "check"):
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"{cls.__name__}.{f.name} is not finite.")
            if isinstance(default, int):
                value = int(value)
        out[f.name] = value
    return cls(**out)


@dataclass
class CalibrationRecord:
    created: str = ""  # TIME_FORMAT; empty for the built-in default
    comment: str = "built-in default (no configuration file)"
    config: StageConfig = field(default_factory=StageConfig)
    optics: OpticsCalibration = field(default_factory=OpticsCalibration)
    check: dict | None = None  # what the calibration measured, for the record
    path: Path | None = None
    collision: CollisionGeometry | None = None  # analyzer / optic solids; None: defaults for the optic

    def collision_geometry(self) -> CollisionGeometry:
        """Solid models for the anti-collision check: from the file, else the defaults for the optic in use."""
        return self.collision or default_geometry(self.optics.optic_type)

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
            "comment": self.comment,
            "stage_config": asdict(self.config),
            "optics": asdict(self.optics),
            "check": self.check,
            **({"collision": self.collision.to_dict()} if self.collision is not None else {}),
        }

    @classmethod
    def from_dict(cls, data: dict, path: Path | None = None) -> CalibrationRecord:
        optics = dict(data.get("optics", {}))
        motors = _from_dict(MotorPositions, optics.pop("motors", {}))
        optics = _from_dict(OpticsCalibration, {k: v for k, v in optics.items() if k != "optic_type"})
        optics.motors = motors
        optic_type = data.get("optics", {}).get("optic_type")
        if optic_type is not None:
            optics.optic_type = str(optic_type)
        return cls(
            created=str(data.get("created", "")),
            comment=str(data.get("comment", "")),
            config=_from_dict(StageConfig, data.get("stage_config", {})),
            optics=optics,
            check=data.get("check"),
            path=path,
            collision=(CollisionGeometry.from_dict(data["collision"], optics.optic_type)
                       if data.get("collision") is not None else None),
        )


class CalibrationStore:
    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder) if folder else DEFAULT_FOLDER

    def records(self) -> list[CalibrationRecord]:
        """All readable configurations, newest first."""
        out = []
        for path in self.folder.glob("calibration_*.json"):
            try:  # a damaged or foreign file is skipped, not fatal
                out.append(CalibrationRecord.from_dict(read_json(path), path))
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
        return sorted(out, key=lambda r: (r.created, r.path.name), reverse=True)

    def latest(self, optic: str | None = None) -> CalibrationRecord:
        """The most recently written configuration.

        With `optic` (one of OPTIC_TYPES), the newest configuration made with that
        optic; if there is none, the stage constants of the newest configuration
        with an uncalibrated optics reference for that optic.
        """
        records = self.records()
        if optic is None:
            return records[0] if records else CalibrationRecord()
        record = CalibrationRecord(optics=OpticsCalibration(optic_type=optic))
        for r in records:
            if r.optic_name == record.optic_name:
                return r
        if not records:
            return record
        base = records[0]
        return replace(base, optics=record.optics, collision=None,
                       comment=f"no {record.optic_name} configuration: stage constants from {base.label}, "
                               f"{record.optic_name} position not calibrated")

    def save(self, record: CalibrationRecord, now: datetime | None = None) -> CalibrationRecord:
        now = now or datetime.now()
        self.folder.mkdir(parents=True, exist_ok=True)
        record = replace(record, created=now.strftime(TIME_FORMAT))
        stem = f"calibration_{now:%Y-%m-%d_%H%M%S}_{record.optic_name.replace(' ', '_')}"
        path = self.folder / f"{stem}.json"
        i = 1
        while path.exists():
            path = self.folder / f"{stem}_{i}.json"
            i += 1
        write_json(path, record.to_dict())
        return replace(record, path=path)

    @property
    def limits_path(self) -> Path:
        return self.folder / LIMITS_FILE

    def motor_limits(self) -> dict[str, tuple[float, float]]:
        """Motor limits set in the Configuration window, {name: (min, max)}; {} if none (a damaged file is ignored)."""
        try:
            data = read_json(self.limits_path)
            out = {str(k): (float(v[0]), float(v[1])) for k, v in data.items()}
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return {}
        return {k: v for k, v in out.items() if v[0] < v[1]}

    def save_motor_limits(self, limits: dict[str, tuple[float, float]]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        write_json(self.limits_path, {k: [float(lo), float(hi)] for k, (lo, hi) in limits.items()})
