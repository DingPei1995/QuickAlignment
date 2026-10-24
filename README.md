# QuickAlignment (ANTARES)

Quick sample locator / optics positioner for the ANTARES beamline sample stage.

## Run

```bash
pip install -r requirements.txt     # PyQt5 (or PySide6), numpy, matplotlib
```

Double-click **`QuickAlignment.py`** (Windows: `QuickAlignment.pyw` starts without a console window),
or run `python QuickAlignment.py [session.json]` / `python -m quickalignment`.
At start-up the program asks which sample plate is mounted (standard Ta plate or gating plate;
*Change plate…* in the toolbar switches later) and loads the most recently written configuration from
`configs/` (user or beamline staff, see below). New / Open / Save store the experiment (plate, samples,
devices, motor positions) in one JSON file.

### Configuration files (`configs/`)

- `calibration_YYYY-MM-DD_HHMMSS_<optic>.json`: written by beamline staff, one file per calibration
  (initial calibration, accepted reference check, expert edit).
- `user_config.json`: one single file, overwritten when the user answers *Save* to the question asked on
  closing the program; its first entry is the save time. It holds the configuration in use with the optic
  type, the optic position and the optics reference.
- At start-up the newest of these files (by its time stamp) is loaded.

### Samples tab (`docs/app_samples_tab.png`)

Positions here are **plate coordinates** (mm on the plate, origin = centre of the back plate, x right,
y up, front view (sample side) with the tab up), not motor positions; the plate dimensions are drawn.

- drag on empty plate → draw a sample; drag a sample → move; drag its edge/corner → resize
- type exact values in the table (x, y, L, W, H); red = outside the sample area or overlapping
- **substrate + devices**: select a sample, press *Add device*; in the device table choose the two
  reference edges (left/right, bottom/top) and the distances dx, dy from them to the device centre,
  or drag the blue marker. Devices follow their substrate when it is moved.
- gating plate: only the 11 × 10.5 mm area above the contact block takes samples

### Stage & Optics tab (`docs/app_stage_tab.png`)

Positions here are **absolute motor values** (ST, SZ, SN, …, optic).

- enter the stage positions and press **Update schematic & optics** (the schematic is only redrawn on this button)
- *Bring target to focus*: computes ST/SN/SZ that put a sample/device on the beam at the analyzer focus,
  keeping SRn, SRz, PIX, PIY
- **focusing optic** (zone plate + OSA or capillary, only along the beam): its absolute position is read
  from the configuration and can be typed in. The result gives the **absolute optic position** for focus
  on the illuminated surface; *Use required position* copies it into the field. After focusing by hand,
  *Set as optics reference* takes the current state as the new optics reference.
- result: what the beam lands on (with the ST / SZ / SN of that point at SRn = 120, SRz = 0) and the
  optic position needed
- schematic: top view (plate orientation, analyzer and its focal plane, beam, optic with its position) and
  the sample plane in front view (SRn rotation, beam spot; axes in absolute ST / SZ)

### Rotate sample tab (`docs/app_rotate_tab.png`)

For a sample that was found and measured (Map) but has the wrong in-plane orientation: it gives the new
SRn (and SRz), the ST / SN / SZ that bring the same sample point back onto the beam, and the optic position.
All inputs come from ARPES viewer:

1. **Measurement**: the Map's metadata. In ARPES viewer, right-click the Map → *Show information* →
   *Export metadata (.csv)*, then *Load metadata CSV…* here (or *Paste metadata…* with the rows).
   Read: `Motor.roughY` (ST), `Motor.roughX` (SZ), `Motor.focus` (SN), `Motor.SRn`, `Motor.SRz`,
   `Motor.fine_x/y` (PIX/PIY) and `Motor.ZP_ZS` (optic in focus during the Map). These are the values
   ARPES viewer shows (position − offset); missing rows are taken from the Stage tab and listed in red.
2. **Angles**: from the k-conversion window: *Theta offset* (deflector) and *Phi offset* (slit) of the
   origin point, and the *Sample rotation* found with *Set rotation from contour…*.
3. **Goal**:
   - *Direction along the slit*: ΔSRn = the viewer's sample rotation (e.g. Γ–K or Γ–M along the slit).
     The line has no direction, so the turn 180° away is offered too (and ±60° are equivalent on a 6-fold lattice).
   - *Direction along the deflector*: the same + 90°.
   - *Origin point onto the slit (SRn)*: brings the point (θ, φ), e.g. a K point / Dirac cone, onto θ = 0.
   - *Origin point to the centre (SRn + SRz)*: brings the point (θ, φ) to the analyzer centre (θ = φ = 0).
   - *Manual ΔSRn / SRz*.
4. *Compute new position*, choose a solution, *Send to Stage & Optics tab*.

**Focus** (how the point is found again):
- *Keep the point where measured (SN adjusts)*, default: the point stays at the same place on the beam as
  during the Map (in the analyzer focus if it was there); ST / SZ / SN compensate, the optic does not move,
  and errors of ST0 / SZ0 / SN_f largely cancel.
- *Keep SN, refocus with the optic*: the usual practice. SRn alone keeps the surface plane, so nothing changes,
  but with SRz ≠ 0 the point slides along the beam and leaves the analyzer focus (on a non-standard plate with
  the SRz axis ≈ 10 mm behind the surface: ≈ 0.1 mm for 2° SRz, 0.2–0.3 mm for 5°). The result shows this shift
  and turns red above 50 µm.
- *Put the point on the analyzer focus*: like *Bring target to focus* (absolute).

**Calibrate on the sample itself.** The beam spot after an optics alignment is only somewhere within the
analyzer's focal range, and the SRn axis on the plate moves with every mounting (0.5–1.5 mm between the plates
measured so far). So the tab works from the sample's own first real position (the Map), and section **4. Learn
this sample's SRn axis** takes the position where the same point was found after the first SRn turn (the next
Map's metadata): *Fit SRn axis*, then *Use for this sample* puts it into the configuration in use (kept in
`user_config.json` if saved on closing). Further turns of that sample are then predicted from both.
`configs/calibration_2026-10-24_170000_zone_plate.json` only gives a starting axis (standard plate, zone plate data
WWS2 2025-10-01/02: ΔSRn = −14°, ΔST = +0.496, ΔSZ = −0.301, 2.38 mm from the axis) and the zone plate
reference (ZP_ZS 53.21985 in focus at the first Map; ZP_ZS increasing moves the zone plate towards the sample).
The SRz axis is not calibrated yet for the standard plate.
**Analyzer geometry** (slit horizontal at ANTARES = default, signs of θ
and φ seen from the analyzer, rotation sense) is a setting remembered between sessions: check it once on a
known sample (e.g. turn by the computed ΔSRn and see whether the direction lands on the slit, else flip the sign).

### Initial calibration (`InitialCalibration.py`, `docs/initial_calibration.png`)

Separate program for the first start or after re-homing the motors: beamline staff measure one reference
feature in 3 (minimum) or 5 (recommended) stage orientations, the constants are fitted and saved as a new
configuration. Protocol: [`docs/initial_calibration_protocol.md`](docs/initial_calibration_protocol.md).

### Calibration window (toolbar *Calibration…*, `docs/calibration_dialog.png`)

- all configurations in `configs/` are listed; the newest is used, older ones can be selected
- **check with the reference sample**: choose it, enter the stage positions where it is on the beam at the
  analyzer focus (preferably SRn = 120, SRz = 0) and the optic position at best focus, press *Check*:
  predicted vs measured ST / SZ / SN / optic are shown. *Accept and save* writes a new dated configuration
  (ST0 / SZ0 / SN_f shifted by the deviations, this state as optics reference).
- the constants are shown greyed out; tick **Expert mode** to edit them and save them as a new configuration.

The optic (zone plate + OSA or capillary) is modelled only as a focus point that moves along the beam with
the optic motor. ST, SZ and SRn do not change the surface plane, so they need no optic move; SN, SRz and
the sample height do (moving the surface 1 mm along SN moves the beam spot √2 mm along the beam).

## Sample plates

Both plates share the same back plate (18 × 15.5 × 1.1 mm Ta with tab), which defines the common reference frame.

- **Standard** (SOLEIL drawing "Plaquette avec rehausse"): 11 mm wide raised part, height 5.0 mm (from the back face).
- **Gating** (drawing "Assemblage V7"): same raised part; sample area = upper 10.5 mm of it;
  below it a 6 mm contact block (3 gold pads, 4 screws, top ≈ 5.2 mm, screw heads ≈ 6.0 mm), reaching 1 mm below the plate.
- **Custom** (*Custom plate* in the plate dialog): the standard back plate without its raised part, carrying a
  block centred left–right; enter its length (x), width (y), centre y and height (measured from the back face of
  the plate, like the 5.0 mm of the standard plate). Samples go on the block; the block is saved with the session.
  SN keeps referring to the standard plate: the block top is in focus at `SN = SN_f + (h − 5.0)`, a sample on it at
  `SN = SN_f + (h − 5.0) + H`.

## Geometry conventions (confirmed)

See `docs/geometry_draft_v2.png` (regenerate with `python docs/draw_geometry.py`).

- Top view: beam along +y; the analyzer focal plane runs upper-left → lower-right at 45°; the analyzer sits
  lower-left of the sample.
- **SN** ⟂ analyzer focal plane; SN = SN_f (≈0, calibrated; e.g. −0.1 after maintenance) puts the top of the
  standard plate (height 5.0 mm from the back face) in the analyzer focal plane, whatever plate is mounted; SN = 65 is
  the transfer position. A sample of height H is in focus at `SN = SN_f + H` (custom plate: `SN_f + (h − 5.0) + H`).
  In practice the sample surface is moved onto the line drawn on the camera image ("SN = 0" line, = analyzer
  focal plane), so the SN read there differs from sample to sample; the Stage & Optics result shows which surface
  height H is on that plane at the entered positions.
- **ST** ∥ analyzer focal plane; ST=ST0 (≈0, adjustable) is the plate centre; ST<0 moves the sample upper-left.
- **SZ** vertical; SZ=SZ0 (≈40, adjustable) is the centre; SZ=35 moves the stage 5 mm down.
- **SRn** azimuth about the sample normal; SRn=120 → plate vertical, tab up; increasing SRn = CCW seen from the analyzer.
  Internal angle θ = SRn − 120 (CCW positive). The SRn axis is offset from the plate centre (adjustable a_t, a_z).
- **SRz** about Z; SRz=0 → plate ∥ analyzer focal plane; SRz<0 = CCW seen from above.
  Axis: the centre line of the plate surface at SRn=120, plus a calibration offset.
- Stack (bottom → top): ST/SN/SZ → SRz → SRn → PIX/PIY → plate.
- **PIX/PIY** piezo stage riding on top of all the above (sample frame), 0–300 µm, centre 150/150.
  Seen from the analyzer: PIX 0→300 = left→right, PIY 0→300 = down→up.

Plate frame (x, y), mm: front view (sample side) with the tab up, origin = centre of the 18 × 15.5 mm back
plate, x right, y up. At the reference orientation (SRn = 120, SRz = 0) a plate point comes onto the beam at
`ST = ST0 − x`, `SZ = SZ0 − y`, `SN = SN_f + H`.
