"""Sample plate geometry and sample layout for the ANTARES sample stage.

Plate frame (u, v), in mm, as seen from the analyzer with SRn = 120 (plate
vertical, tab up) and SRz = 0:

* origin: centre of the 18 x 15.5 mm plate body
* +u: to the right (same direction as +ST, and as PIX 0 -> 300)
* +v: up (same direction as +SZ, and as PIY 0 -> 300)

Heights are measured along the plate normal, towards the analyzer, from the
back face of the plate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

Point = tuple[float, float]


@dataclass(frozen=True)
class PlateGeometry:
    """Ta sample plate with 4 mm riser (SOLEIL drawing "Plaquette avec rehausse")."""

    width: float = 18.0
    height: float = 15.5
    riser_width: float = 11.0
    base_thickness: float = 1.1
    total_thickness: float = 5.0
    neck_width: float = 1.8
    neck_height: float = 2.0
    tab_width: float = 4.0
    tab_height: float = 4.0
    chamfer_height: float = 2.0
    chamfer_width: float = 0.5

    @property
    def riser_thickness(self) -> float:
        return self.total_thickness - self.base_thickness

    def outline(self) -> list[Point]:
        """Plate body + tab outline in plate coordinates, counter-clockwise."""
        w, h = self.width / 2, self.height / 2
        nw, tw = self.neck_width / 2, self.tab_width / 2
        neck_top = h + self.neck_height
        tab_top = neck_top + self.tab_height
        return [
            (-w, h),
            (-w, -h + self.chamfer_height),
            (-w + self.chamfer_width, -h),
            (w - self.chamfer_width, -h),
            (w, -h + self.chamfer_height),
            (w, h),
            (nw, h),
            (nw, neck_top),
            (tw, neck_top),
            (tw, tab_top),
            (-tw, tab_top),
            (-tw, neck_top),
            (-nw, neck_top),
            (-nw, h),
        ]

    def riser_bounds(self) -> tuple[float, float, float, float]:
        """(u_min, v_min, u_max, v_max) of the riser top face, where samples sit."""
        return (-self.riser_width / 2, -self.height / 2, self.riser_width / 2, self.height / 2)


@dataclass
class Sample:
    """A rectangular sample on the riser face.

    (u, v) is the sample centre in the plate frame; length runs along u,
    width along v, height along the plate normal (towards the analyzer).
    """

    name: str
    u: float = 0.0
    v: float = 0.0
    length: float = 2.0
    width: float = 2.0
    height: float = 0.5

    def bounds(self) -> tuple[float, float, float, float]:
        return (
            self.u - self.length / 2,
            self.v - self.width / 2,
            self.u + self.length / 2,
            self.v + self.width / 2,
        )

    def surface_height(self, plate: PlateGeometry) -> float:
        """Distance from the plate back face to the sample surface (5.0 + H)."""
        return plate.total_thickness + self.height

    def overlaps(self, other: Sample) -> bool:
        a, b = self.bounds(), other.bounds()
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@dataclass
class SampleLayout:
    plate: PlateGeometry = field(default_factory=PlateGeometry)
    samples: list[Sample] = field(default_factory=list)

    def warnings(self, sample: Sample) -> list[str]:
        """Problems with one sample's placement (empty list if it is fine)."""
        out = []
        u0, v0, u1, v1 = sample.bounds()
        r0, s0, r1, s1 = self.plate.riser_bounds()
        eps = 1e-9
        if u0 < r0 - eps or v0 < s0 - eps or u1 > r1 + eps or v1 > s1 + eps:
            out.append("outside riser")
        if sample.length <= 0 or sample.width <= 0 or sample.height < 0:
            out.append("invalid size")
        for other in self.samples:
            if other is not sample and sample.overlaps(other):
                out.append(f"overlaps {other.name}")
        return out

    def unique_name(self, prefix: str = "S") -> str:
        names = {s.name for s in self.samples}
        i = 1
        while f"{prefix}{i}" in names:
            i += 1
        return f"{prefix}{i}"

    def to_dict(self) -> dict:
        return {
            "frame": "plate frame seen from analyzer at SRn=120: origin = plate body centre, "
            "+u right (+ST, PIX), +v up (+SZ, PIY), mm",
            "plate": asdict(self.plate),
            "samples": [asdict(s) for s in self.samples],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SampleLayout:
        plate = PlateGeometry(**data.get("plate", {}))
        return cls(plate=plate, samples=[Sample(**s) for s in data.get("samples", [])])

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> SampleLayout:
        return cls.from_dict(json.loads(Path(path).read_text()))
