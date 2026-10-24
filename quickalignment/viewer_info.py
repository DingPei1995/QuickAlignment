"""Metadata from ARPES viewer's "Show information" window.

The viewer lists the metadata of a dataset (right-click -> Show information)
and writes it with "Export metadata (.csv)" as ``field,value`` rows. The
motor positions are the rows ``Motor.<label>`` (offset-corrected, as the
viewer computes them):

* ``Motor.roughY`` ST, ``Motor.roughX`` SZ, ``Motor.focus`` SN
* ``Motor.SRn``, ``Motor.SRz``
* ``Motor.fine_x`` PIX, ``Motor.fine_y`` PIY (um)
* ``Motor.ZP_ZS`` zone plate along the beam, ``Motor.OSA_S`` OSA along the beam

This module reads that CSV, or the same rows pasted as text (comma, tab,
``=`` or ``:`` separated), into a dict and picks the stage positions out of it.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .stage import MotorPositions

# MotorPositions field -> keys tried in this order (case-insensitive)
MOTOR_KEYS = {
    "st": ("Motor.roughY", "ST"),
    "sz": ("Motor.roughX", "SZ"),
    "sn": ("Motor.focus", "SN"),
    "srn": ("Motor.SRn", "SRn"),
    "srz": ("Motor.SRz", "SRz"),
    "pix": ("Motor.fine_x", "PIX"),
    "piy": ("Motor.fine_y", "PIY"),
}
OPTIC_KEYS = ("Motor.ZP_ZS", "Motor.OSA_S", "Motor.ZP_ZX", "Motor.ZP_ZT")
PHOTON_ENERGY_KEYS = ("PhotonEnergy", "Mono.energy")


def _number(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().strip("[]()")
    try:
        return float(text)
    except ValueError:
        match = re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?", text)
        return float(match.group(0)) if match else None


def parse_info_text(text: str) -> dict[str, str]:
    """Rows of ``field<sep>value``: a CSV export of the viewer, or pasted lines."""
    rows: dict[str, str] = {}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and all("," in ln for ln in lines[: min(len(lines), 5)]) and "\t" not in lines[0]:
        for row in csv.reader(io.StringIO("\n".join(lines))):
            if len(row) >= 2 and row[0].strip().lower() != "field":
                rows[row[0].strip()] = row[1].strip()
        return rows
    for ln in lines:
        parts = re.split(r"\t|\s*[=:,;]\s*|\s{2,}", ln.strip(), maxsplit=1)
        if len(parts) == 2 and parts[0].strip().lower() != "field":
            rows[parts[0].strip()] = parts[1].strip()
    return rows


@dataclass
class ViewerInfo:
    """What the rotation tool needs from one dataset's metadata."""

    rows: dict[str, str] = field(default_factory=dict)
    source: str = ""

    @classmethod
    def from_text(cls, text: str, source: str = "pasted text") -> ViewerInfo:
        return cls(parse_info_text(text), source)

    @classmethod
    def load(cls, path: str | Path) -> ViewerInfo:
        path = Path(path)
        return cls.from_text(path.read_text(encoding="utf-8-sig"), path.name)

    def get(self, *keys: str) -> float | None:
        lower = {k.lower(): v for k, v in self.rows.items()}
        for key in keys:
            value = _number(lower.get(key.lower()))
            if value is not None:
                return value
        return None

    def motors(self, default: MotorPositions | None = None) -> tuple[MotorPositions, list[str]]:
        """Stage positions from the metadata; missing ones are taken from `default` and listed."""
        default = default or MotorPositions()
        values, missing = {}, []
        for name, keys in MOTOR_KEYS.items():
            value = self.get(*keys)
            if value is None:
                missing.append(keys[0])
                value = getattr(default, name)
            values[name] = value
        return MotorPositions(**values), missing

    def optic_keys(self) -> list[str]:
        """Optic motors present in the metadata, the usual focusing motor first."""
        return [k for k in OPTIC_KEYS if self.get(k) is not None]

    @property
    def photon_energy(self) -> float | None:
        return self.get(*PHOTON_ENERGY_KEYS)
