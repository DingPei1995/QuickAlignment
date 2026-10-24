"""Save / load what belongs to an experiment: the plate layout and the motor positions.

Calibration constants are beamline state and live in dated configuration
files (see calibration.py), not in sessions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .geometry import SampleLayout
from .stage import MotorPositions


@dataclass
class Session:
    layout: SampleLayout = field(default_factory=SampleLayout)
    motors: MotorPositions = field(default_factory=MotorPositions)

    def to_dict(self) -> dict:
        return {"layout": self.layout.to_dict(), "motors": asdict(self.motors)}

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        if "layout" not in data:  # plain layout file
            return cls(layout=SampleLayout.from_dict(data))
        names = {f.name for f in fields(MotorPositions)}
        motors = MotorPositions(**{k: v for k, v in data.get("motors", {}).items() if k in names})
        return cls(layout=SampleLayout.from_dict(data["layout"]), motors=motors)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> Session:
        return cls.from_dict(json.loads(Path(path).read_text()))
