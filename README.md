# QuickAlignment (ANTARES)

Quick sample locator / optics positioner for the ANTARES beamline sample stage.

## Run

```bash
pip install -r requirements.txt     # PyQt5 (or PySide6), numpy, matplotlib
```

Double-click **`QuickAlignment.py`** (Windows: `QuickAlignment.pyw` starts without a console window),
or run `python QuickAlignment.py [session.json]` / `python -m quickalignment`.
At start-up the program asks which sample plate is mounted (standard Ta plate or gating plate;
*Change plate…* in the toolbar switches later) and loads the newest calibration configuration from `configs/`.
New / Open / Save store the experiment (plate, samples, devices, motor positions) in one JSON file.

### Samples tab (`docs/app_samples_tab.png`)

Positions here are **plate coordinates** (mm on the plate, origin = centre of the back plate, x right,
y up, seen from the analyzer, tab up), not motor positions; the plate dimensions are drawn.

- drag on empty plate → draw a sample; drag a sample → move; drag its edge/corner → resize
- type exact values in the table (x, y, L, W, H); red = outside the sample area or overlapping
- **substrate + devices**: select a sample, press *Add device*; in the device table choose the two
  reference edges (left/right, bottom/top) and the distances dx, dy from them to the device centre,
  or drag the blue marker. Devices follow their substrate when it is moved.
- gating plate: only the 11 × 10.5 mm area above the contact block takes samples

### Stage & Optics tab (`docs/app_stage_tab.png`)

Positions here are **absolute motor values** (ST, SZ, SN, …).

- enter the stage positions and press **Update schematic & optics** (the schematic is only redrawn on this button)
- *Bring target to focus*: computes ST/SN/SZ that put a sample/device on the analyzer focus, keeping SRn, SRz, PIX, PIY
- result: what the beam lands on (with the ST / SZ / SN of that point at SRn = 120, SRz = 0), and how far
  the optics focus must move along the beam, **towards** (downstream) or **away from** (upstream) the sample
- schematic: top view (plate orientation, analyzer, beam, optic and its required move) and the sample
  plane seen from the analyzer (SRn rotation, beam spot; axes in absolute ST / SZ)

### Calibration window (toolbar *Calibration…*, `docs/calibration_dialog.png`)

- calibrations are dated files in `configs/`; the newest is used, older ones can be selected
- **check with the reference sample**: choose it, enter the stage positions where it is on the beam at the
  analyzer focus (preferably SRn = 120, SRz = 0) and the optic position at best focus, press *Check*:
  predicted vs measured ST / SZ / SN / optic are shown. *Accept and save* writes a new dated configuration
  (ST0 / SZ0 / SN_f shifted by the deviations, this state as optics reference).
- the constants are shown greyed out; tick **Expert mode** to edit them and save them as a new configuration.

The optic (capillary or zone plate + OSA) is modelled only as a focus point that moves along the beam.
ST, SZ and SRn do not change the surface plane, so they need no optics move; SN, SRz and the sample
height do (moving the surface 1 mm along SN moves the beam spot √2 mm along the beam).

## Sample plates

Both plates share the same back plate (18 × 15.5 × 1.1 mm Ta with tab), which defines the common reference frame.

- **Standard** (SOLEIL drawing "Plaquette avec rehausse"): 11 mm wide riser, protruding surface 5.0 mm above the back face.
- **Gating** (drawing "Assemblage V7"): same riser; sample area = upper 10.5 mm of the riser;
  below it a 6 mm contact block (3 gold pads, 4 screws, top ≈ 5.2 mm, screw heads ≈ 6.0 mm), reaching 1 mm below the plate.

## Geometry conventions (confirmed)

See `docs/geometry_draft_v2.png` (regenerate with `python docs/draw_geometry.py`).

- Top view: beam along +y; analyzer plane runs upper-left → lower-right at 45°; analyzer sits lower-left of the sample.
- **SN** ⟂ analyzer plane; SN = SN_f (≈0, calibrated) puts the protruding plate surface (riser top) at the
  analyzer focus; SN = 65 is the transfer position. A sample of height H is in focus at `SN = SN_f + H`.
- **ST** ∥ analyzer plane; ST=ST0 (≈0, adjustable) is the plate centre; ST<0 moves the sample upper-left.
- **SZ** vertical; SZ=SZ0 (≈40, adjustable) is the centre; SZ=35 moves the stage 5 mm down.
- **SRn** azimuth about the sample normal; SRn=120 → plate vertical, tab up; increasing SRn = CCW seen from the analyzer.
  Internal angle θ = SRn − 120 (CCW positive). The SRn axis is offset from the plate centre (adjustable a_t, a_z).
- **SRz** about Z; SRz=0 → plate ∥ analyzer plane; SRz<0 = CCW seen from above.
  Axis: the centre line of the plate surface at SRn=120, plus a calibration offset.
- Stack (bottom → top): ST/SN/SZ → SRz → SRn → PIX/PIY → plate.
- **PIX/PIY** piezo stage riding on top of all the above (sample frame), 0–300 µm, centre 150/150.
  Seen from the analyzer: PIX 0→300 = left→right, PIY 0→300 = down→up.

Plate frame (x, y), mm: seen from the analyzer at SRn = 120, origin = centre of the 18 × 15.5 mm back
plate, x right, y up. At the reference orientation a plate point comes onto the beam at
`ST = ST0 − x`, `SZ = SZ0 − y`, `SN = SN_f + H`.
