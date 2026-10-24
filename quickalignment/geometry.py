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


Rect = tuple[float, float, float, float]  # (u_min, v_min, u_max, v_max)


@dataclass(frozen=True)
class PlateGeometry:
    """Sample plate geometry. Defaults: Ta plate with 4 mm riser
    (SOLEIL drawing "Plaquette avec rehausse")."""

    key: str = "standard"
    name: str = "Standard Ta plate (4 mm riser)"
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
    # lower edge of the sample area on the riser (None: plate bottom)
    sample_area_bottom: float | None = None
    # electrical contact block below the sample area: rect and top height w
    contact_block: Rect | None = None
    contact_block_top: float = 0.0
    contact_pads: tuple[Rect, ...] = ()
    screws: tuple[tuple[float, float], ...] = ()  # (u, v) centres
    screw_diameter: float = 2.0
    screw_top: float = 0.0

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

    def riser_bounds(self) -> Rect:
        """(u_min, v_min, u_max, v_max) of the sample area on the riser top face."""
        bottom = -self.height / 2 if self.sample_area_bottom is None else self.sample_area_bottom
        return (-self.riser_width / 2, bottom, self.riser_width / 2, self.height / 2)

    def lowest_v(self) -> float:
        bottom = -self.height / 2
        return min(bottom, self.contact_block[1]) if self.contact_block else bottom


STANDARD_PLATE = PlateGeometry()

# Gating plate (drawing "Assemblage V7"): same Ta plate and riser, but only the
# upper 10.5 mm of the riser is free for samples; below it a 6 mm contact block
# with 3 gold pads and 4 clamping screws, reaching 1 mm below the plate.
GATING_PLATE = PlateGeometry(
    key="gating",
    name="Gating plate (contact block, 3 pads, 4 screws)",
    sample_area_bottom=-2.75,
    contact_block=(-5.5, -8.75, 5.5, -2.75),
    contact_block_top=5.2,
    contact_pads=((-3.55, -4.65, -2.45, -2.75), (-0.55, -4.65, 0.55, -2.75), (2.45, -4.65, 3.55, -2.75)),
    screws=((-4.5, -6.3), (-1.5, -6.3), (1.5, -6.3), (4.5, -6.3)),
    screw_diameter=2.0,
    screw_top=6.0,
)

PLATES = {p.key: p for p in (STANDARD_PLATE, GATING_PLATE)}


X_EDGES = ("left", "right")
Y_EDGES = ("bottom", "top")


@dataclass
class Device:
    """A small device on a substrate, located from two substrate edges.

    Edges are named as seen from the analyzer at SRn = 120: dx is the
    distance from the chosen left/right edge, dy from the chosen bottom/top
    edge, both to the device centre. length/width are only for display.
    """

    name: str
    x_edge: str = "left"
    dx: float = 0.0
    y_edge: str = "bottom"
    dy: float = 0.0
    length: float = 0.2
    width: float = 0.2

    def position(self, substrate: Sample) -> Point:
        u0, v0, u1, v1 = substrate.bounds()
        u = u0 + self.dx if self.x_edge == "left" else u1 - self.dx
        v = v0 + self.dy if self.y_edge == "bottom" else v1 - self.dy
        return u, v

    def set_position(self, substrate: Sample, u: float, v: float) -> None:
        """Update dx, dy (keeping the chosen edges) so the centre is at (u, v)."""
        u0, v0, u1, v1 = substrate.bounds()
        self.dx = u - u0 if self.x_edge == "left" else u1 - u
        self.dy = v - v0 if self.y_edge == "bottom" else v1 - v


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
    devices: list[Device] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "substrate" if self.devices else "sample"

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

    def device_warnings(self, sample: Sample, device: Device) -> list[str]:
        out = []
        if device.x_edge not in X_EDGES or device.y_edge not in Y_EDGES:
            out.append("invalid edge")
        u, v = device.position(sample)
        u0, v0, u1, v1 = sample.bounds()
        if not (u0 <= u <= u1 and v0 <= v <= v1):
            out.append("outside substrate")
        return out

    def targets(self) -> list[tuple[str, float, float, float]]:
        """All selectable targets: (label, u, v, sample height H)."""
        out = []
        for s in self.samples:
            out.append((s.name, s.u, s.v, s.height))
            for d in s.devices:
                u, v = d.position(s)
                out.append((f"{s.name}/{d.name}", u, v, s.height))
        return out

    def unique_device_name(self, prefix: str = "D") -> str:
        names = {d.name for s in self.samples for d in s.devices}
        i = 1
        while f"{prefix}{i}" in names:
            i += 1
        return f"{prefix}{i}"

    def unique_name(self, prefix: str = "S") -> str:
        names = {s.name for s in self.samples}
        i = 1
        while f"{prefix}{i}" in names:
            i += 1
        return f"{prefix}{i}"

    def to_dict(self) -> dict:
        return {
            "frame": "plate frame seen from analyzer at SRn=120: origin = plate body centre, "
            "+u right (PIX), +v up (PIY), mm; ST = ST0 - u, SZ = SZ0 - v, SN = SN_f + 5.0 + H",
            "plate_type": self.plate.key,
            "samples": [asdict(s) for s in self.samples],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SampleLayout:
        plate = PLATES.get(data.get("plate_type", "standard"), STANDARD_PLATE)
        samples = []
        for raw in data.get("samples", []):
            raw = dict(raw)
            devices = [Device(**d) for d in raw.pop("devices", [])]
            samples.append(Sample(**raw, devices=devices))
        return cls(plate=plate, samples=samples)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> SampleLayout:
        return cls.from_dict(json.loads(Path(path).read_text()))
