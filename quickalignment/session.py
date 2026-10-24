"""Save / load everything the user entered: layout, stage constants, calibration, motors."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .geometry import SampleLayout
from .stage import MotorPositions, OpticsCalibration, StageConfig


def _from_dict(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Session:
    layout: SampleLayout = field(default_factory=SampleLayout)
    config: StageConfig = field(default_factory=StageConfig)
    calibration: OpticsCalibration = field(default_factory=OpticsCalibration)
    motors: MotorPositions = field(default_factory=MotorPositions)

    def to_dict(self) -> dict:
        return {
            "layout": self.layout.to_dict(),
            "stage_config": asdict(self.config),
            "calibration": asdict(self.calibration),
            "motors": asdict(self.motors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        if "layout" not in data:  # plain layout file
            return cls(layout=SampleLayout.from_dict(data))
        cal = dict(data.get("calibration", {}))
        cal_motors = _from_dict(MotorPositions, cal.pop("motors", {}))
        return cls(
            layout=SampleLayout.from_dict(data["layout"]),
            config=_from_dict(StageConfig, data.get("stage_config", {})),
            calibration=_from_dict(OpticsCalibration, {**cal, "motors": cal_motors}),
            motors=_from_dict(MotorPositions, data.get("motors", {})),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> Session:
        return cls.from_dict(json.loads(Path(path).read_text()))
