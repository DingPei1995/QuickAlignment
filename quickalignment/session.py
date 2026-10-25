"""Save / load what belongs to an experiment: the plate layout and the motor positions.

Calibration constants are beamline state and live in dated configuration
files (see calibration.py), not in sessions.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .fileio import read_json, write_json
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
        """Session from a file's dictionary; wrong values raise ValueError."""
        if not isinstance(data, dict):
            raise ValueError("Not a session: expected a JSON object.")
        if "layout" not in data:  # plain layout file
            return cls(layout=SampleLayout.from_dict(data))
        raw = data.get("motors", {})
        if not isinstance(raw, dict):
            raise ValueError("motors: expected a JSON object.")
        motors = {}
        for f in fields(MotorPositions):
            if f.name in raw:
                try:
                    value = float(raw[f.name])
                except (TypeError, ValueError):
                    value = math.nan
                if not math.isfinite(value) or isinstance(raw[f.name], bool):
                    raise ValueError(f"motors: {f.name} = {raw[f.name]!r} is not a number.")
                motors[f.name] = value
        return cls(layout=SampleLayout.from_dict(data["layout"]), motors=MotorPositions(**motors))

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> Session:
        return cls.from_dict(read_json(path))
