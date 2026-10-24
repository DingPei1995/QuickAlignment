"""Calibration configurations and the reference-sample check.

Files in the configuration folder (default: ``configs/`` next to the program):

* ``calibration_YYYY-MM-DD_HHMMSS_<optic>.json`` (optic: ``capillary`` or
  ``zone_plate``): one file per calibration made by beamline staff with
  InitialCalibration.py. QuickAlignment only reads them.

At start-up the newest of them (by its time stamp) made with the chosen optic
is loaded.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path

from .stage import MotorPositions, OpticsCalibration, StageConfig

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "configs"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _from_dict(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class CalibrationRecord:
    created: str = ""  # TIME_FORMAT; empty for the built-in default
    comment: str = "built-in default (no configuration file)"
    config: StageConfig = field(default_factory=StageConfig)
    optics: OpticsCalibration = field(default_factory=OpticsCalibration)
    check: dict | None = None  # what the calibration measured, for the record
    path: Path | None = None

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
        )


class CalibrationStore:
    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder) if folder else DEFAULT_FOLDER

    def records(self) -> list[CalibrationRecord]:
        """All readable configurations, newest first."""
        out = []
        for path in self.folder.glob("calibration_*.json"):
            try:
                out.append(CalibrationRecord.from_dict(json.loads(path.read_text()), path))
            except (OSError, ValueError, TypeError):
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
        return replace(base, optics=record.optics,
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
        path.write_text(json.dumps(record.to_dict(), indent=2))
        return replace(record, path=path)
