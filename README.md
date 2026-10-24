# QuickAlignment (ANTARES)

Quick sample locator / optics positioner for the ANTARES beamline sample stage.

## Run

```bash
pip install -r requirements.txt     # PyQt5 (or PySide6), numpy, matplotlib
```

Double-click **`QuickAlignment.py`** (Windows: `QuickAlignment.pyw` starts without a console window),
or run `python QuickAlignment.py [session.json]` / `python -m quickalignment`.
New / Open / Save store everything (samples, devices, stage constants, calibration, motors) in one JSON file.

### Samples tab (`docs/app_samples_tab.png`)

- drag on empty plate → draw a sample; drag a sample → move; drag its edge/corner → resize
- type exact values in the table (u, v, L, W, H); red = outside the riser or overlapping
- **substrate + devices**: select a sample, press *Add device*; in the device table choose the two
  reference edges (left/right, bottom/top as seen from the analyzer) and the distances dx, dy from them
  to the device centre, or drag the blue marker. Devices follow their substrate when it is moved.

### Stage & Optics tab (`docs/app_stage_tab.png`)

- enter the stage positions (ST, SN, SZ, SRn, SRz, PIX, PIY) and press **Update schematic & optics**
  (the schematic is only redrawn on this button)
- *Bring target to focus*: computes ST/SN/SZ that put a sample/device on the analyzer focus, keeping SRn, SRz, PIX, PIY
- result: what the beam lands on, and how far the optics focus must move along the beam,
  **towards** (downstream) or **away from** (upstream) the sample
- optics calibration: after the first focusing, enter the stage positions, the illuminated sample (H),
  the optic position at best focus and the optic motor direction, then tick *Use calibration*:
  the new optic motor position is then given directly. Without calibration the optics focus is the
  analyzer focus.

The optic (capillary or zone plate + OSA) is modelled only as a focus point that moves along the beam.
ST, SZ and SRn do not change the surface plane, so they need no optics move; SN, SRz and the sample
height do (moving the surface 1 mm along SN moves the beam spot √2 mm along the beam).

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
- Stack (bottom → top): ST/SN/SZ → SRz → SRn → PIX/PIY → plate.
- **PIX/PIY** piezo stage riding on top of all the above (sample frame), 0–300 µm, centre 150/150.
  Seen from the analyzer: PIX 0→300 = left→right, PIY 0→300 = down→up.

Plate frame used by the editor (u, v), mm: seen from the analyzer at SRn=120, origin = centre of the
18 × 15.5 mm plate body, +u right (+ST, PIX), +v up (+SZ, PIY). Samples sit on the 11 mm wide riser.
