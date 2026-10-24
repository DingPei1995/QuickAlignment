# QuickAlignment (ANTARES)

Quick sample locator / optics positioner for the ANTARES beamline sample stage.

## Run

```bash
pip install -r requirements.txt
python -m quickalignment            # empty plate
python -m quickalignment layout.json
```

Sample plate editor (`docs/plate_editor_screenshot.png`):

- drag on empty plate → draw a new sample; drag a sample → move; drag its edge/corner → resize
- type exact values in the table (u, v, L, W, H); both views stay in sync
- red = outside the riser or overlapping another sample
- wheel = zoom, middle-drag = pan, Del = delete; layouts are saved as JSON

## Geometry conventions (confirmed)

See `docs/geometry_draft_v2.png` (regenerate with `python docs/draw_geometry.py`).

- Top view: beam along +y; analyzer plane runs upper-left → lower-right at 45°; analyzer sits lower-left of the sample.
- **SN** ⟂ analyzer plane; SN=SN_f (≈0, adjustable) puts the reference at the analyzer focus; SN=65 is the transfer position.
  The sample surface is brought to focus at `SN = SN_f + 5.0 + H` (plate total thickness 5.0 mm + sample height H).
- **ST** ∥ analyzer plane; ST=ST0 (≈0, adjustable) is the plate centre; ST<0 moves the sample upper-left.
- **SZ** vertical; SZ=SZ0 (≈40, adjustable) is the centre; SZ=35 moves the stage 5 mm down.
- **SRn** azimuth about the sample normal; SRn=120 → plate vertical, tab up; increasing SRn = CCW seen from the analyzer.
  Internal angle θ = SRn − 120 (CCW positive). The SRn axis is offset from the plate centre (adjustable a_t, a_z).
- **SRz** about Z; SRz=0 → plate ∥ analyzer plane; SRz<0 = CCW seen from above.
  Axis: the centre line of the plate surface at SRn=120, plus a calibration offset.
- **PIX/PIY** piezo stage riding on top of all the above (sample frame), 0–300 µm, centre 150/150.
  Seen from the analyzer: PIX 0→300 = left→right, PIY 0→300 = down→up.

Plate frame used by the editor (u, v), mm: seen from the analyzer at SRn=120, origin = centre of the
18 × 15.5 mm plate body, +u right (+ST, PIX), +v up (+SZ, PIY). Samples sit on the 11 mm wide riser.
