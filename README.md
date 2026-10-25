# QuickAlignment (ANTARES)

Quick sample locator / optics positioner for the ANTARES beamline sample stage.

## Run

```bash
pip install -r requirements.txt     # PyQt5 (or PySide6), numpy, matplotlib
```

Double-click **`QuickAlignment.py`** (Windows: `QuickAlignment.pyw` starts without a console window),
or run `python QuickAlignment.py [session.json]` / `python -m quickalignment`.
At start-up the program asks which sample plate is mounted (standard Ta plate, gating plate or custom
plate; *Change plate…* in the toolbar switches later) and which focusing optic is used (zone plate + OSA or
capillary), then loads the most recently written configuration for that optic from `configs/` (see below). New / Open / Save store the experiment (plate, samples, devices, motor positions)
in one JSON file; the first *Save* asks for the file name.

### Configuration files (`configs/`)

- `calibration_YYYY-MM-DD_HHMMSS_<optic>.json`: written by beamline staff with InitialCalibration.py, one file
  per calibration.
- QuickAlignment only reads them: it asks nothing and writes no configuration.
- At start-up the newest of these files (by its time stamp) made with the chosen optic is loaded. If there is
  none for that optic, the stage constants of the newest file are used and the optic position is left
  uncalibrated.

### Samples tab (`docs/app_samples_tab.png`)

Positions here are **plate coordinates** (mm on the plate, origin = centre of the back plate, x right,
y up, front view (sample side) with the tab up), not motor positions; the plate dimensions are drawn.

- drag on empty plate → draw a sample; drag a sample → move; drag its edge/corner → resize
- type exact values in the table (x, y, L, W, H); red = outside the sample area or overlapping
- **substrate + devices**: select a sample, press *Add device*; in the device table choose the two
  reference edges (left/right, bottom/top) and the distances dx, dy from them to the device centre,
  or drag the blue marker. Devices follow their substrate when it is moved.
- gating plate: only the 11 × 10.5 mm area above the contact block takes samples
- mouse drawing / moving / resizing is rounded to 0.1 mm; typed values are not rounded.
  *Default H*: height given to new samples, by default a Si wafer substrate (0.525 mm, standard 100 mm wafer).
- *Status* column: `ok`, or what is wrong with the placement (outside the sample area / substrate, overlapping).
- wheel = zoom, middle drag = pan, right click = whole plate again
- **Samples placed → Stage**: asks whether all samples are marked on the plate; *Yes* opens the Stage & Optics tab
  with a list of the ST / SZ / SN that put each sample on the analyzer focus at the initial rotation
  (SRn = 120, SRz = 0, PIX = PIY = 150 µm). A substrate carrying devices is listed by its devices only (also in
  the target lists).
- **Found here: correct its sample** (in that list): once a device is found on the beam in the analyzer focus,
  enter its stage positions in the Stage tab, choose the device and press the button. Its sample (with all its
  devices) is moved on the plate to where it really is (Δx, Δy, ΔH: an error of the drawing); the other samples
  and the configuration stay. The list is recomputed and the sample keeps the corrected position from then on
  (saved with the session).

### Stage & Optics tab (`docs/app_stage_tab.png`)

Positions here are **absolute motor values** (ST, SZ, SN, …, optic).

- enter the stage positions and press **Update schematic & optics** (the schematic is only redrawn on this button)
- *Bring target to focus*: computes ST/SN/SZ that put a sample/device on the beam at the analyzer focus,
  keeping SRn, SRz, PIX, PIY
- **focusing optic** (zone plate + OSA or capillary, only along the beam): its absolute position is read
  from the configuration and can be typed in. The result gives the **absolute optic position** for focus
  on the illuminated surface; *Use required position* copies it into the field. After focusing by hand,
  *Set as optics reference* takes the current state as the optics reference for this session.
- schematic: top view (plate orientation, analyzer and its focal plane, beam, optic with its position and the
  position needed for focus) and the sample plane in front view (SRn rotation; beam spot, analyzer focus and
  SRn axis with a legend in the same colours; axes in absolute ST / SZ)

### Rotate sample tab (`docs/app_rotate_tab.png`)

Gives the stage positions that keep a sample point on the beam when the sample is turned.

1. **Current position**: ST, SN, SZ, SRn, SRz, PIX, PIY with the point of interest on the beam and in focus, and
   the zone plate / capillary position (*From Stage tab* copies them).
2. **Wanted angles**: the new SRn and SRz.
3. **New position**: *Compute new position* gives ST and SZ for these angles with the piezo centred
   (PIX = PIY = 150 µm) and SN unchanged (default), and the optic position that refocuses. Below, it says how far
   the point then is from the analyzer focus (model; red above 50 µm, where the data would be distorted: SRn alone
   keeps the surface plane, SRz does not). Ticking *Correct SN* shows the SN, ST, SZ and optic position that put the
   point on the analyzer focus (absolute: relies on ST0 / SZ0 / SN_f and the rotation axes of the configuration).
   If a motor range does not allow it, the closest reachable position is given with its distance from the focus.
   *Send to Stage & Optics tab* takes the shown solution (refused if it is out of range).

**Find angles for a BZ point…** (under *Wanted angles*, `docs/bz_target_dialog.png`; 2-D hexagonal crystals such as
graphene, WSe2): which SRn / SRz bring Γ, K (or only K / only K′) or M to the slit centre with the deflector at 0
and the slit along a high-symmetry line (Γ–K, K–M, Γ–M, M–K). Entered by hand, from a map in ARPES viewer
(θ = deflector, contour x; φ = angle along the slit, contour y): SRn / SRz and photon energy of the map, the angles
of Γ and of one K or M point, the lattice constant (presets), the wanted point and line, the photon energy of the
new measurement and E − E_F of the point (work function 4.5 eV). The sample may be mounted tilted: the Γ angles take
care of it.

- Accepted when, with the deflector at 0, the point is within |θ| ≤ 5° and |φ| ≤ 5° of the slit centre, the slit
  within 2° of the line, with SRn 60 … 180° and SRz −25 … +10° (`bz_target.py`). All equivalent points and both
  SRz senses are listed; SRz ≤ 0 is preferred (beam closer to the surface normal: 45° + SRz), then the smallest turn.
- No tilt axis: with the point at the slit centre and the deflector at 0 the slit always runs along Γ–point
  (Γ–K for K). A slit across it (K–M, M–K) needs the deflector at about the emission angle of the point; the window
  then proposes the radial geometry, where the deflector runs along K–M, and a short deflector map (|θ| ≤ 5°).
- Not reachable: the photon energies (30 … 180 eV, capillary only; the zone plate works at 95 eV only) at which it
  is, or that the sample has to be remounted (turned on the plate by a given angle when SRn is the limit).
- A check of the input: Γ–K (or Γ–M) on the map against the lattice constant, and the tilt of the sample.
- Preview: the map at the proposed angles (BZ, deflector ranges: gaps beyond ±8°, max ±12°) and the 2-D zone in k
  with the analyzer window, oriented like the current map.
- *Use these angles* puts SRn / SRz into *Wanted angles* and computes the new position.

The sign conventions between the stage and the ARPES viewer contour (`AnalyzerGeometry`) are to be checked on the
first real use: after turning, the point should appear where the preview shows it.

Motor travel ranges (`MOTOR_SPECS` in `quickalignment/ui/stage_panel.py`): ST −6 … 6, SN −0.5 … 65, SZ 35 … 45 mm.
The motor fields do not accept values outside them; *Bring target to focus* and the Rotate tab warn when a
position would be out of range (e.g. at SRn = 120 a point more than 5 mm above or below the plate centre needs
SZ outside 35 … 45).

The SRn axis position on the plate comes from the configuration (`configs/calibration_2026-10-24_170000_zone_plate.json`:
standard plate, zone plate data WWS2 2025-10-01/02, 2.38 mm from the axis). The SRz axis is not calibrated yet for
the standard plate.

Capillary: `configs/calibration_2026-10-24_235500_capillary.json` (gating plate, data in `Data for config/`), a joint
fit of two devices on Si (H = 0.525 mm), each measured at two rotations with SN kept at ≈ 0 and the capillary refocused:
RG_GMC (x 1.51, y 2.82 mm from the photos, `RG_GMC_position_on_plate.png`, session `RG_GMC_gating_session.json`) at
SRn 120 / SRz −12 (CPS 60.30) and SRn 92 / SRz −24 (CPS 61.74); Cav (another gating plate, no photo: its position is
fitted) at SRn 120 / SRz −24 (CPS 58.75) and SRn 142 / SRz −24 (CPS 58.48). 12 equations for 9 unknowns, rms 22 µm.
SRz axis 2.59 ± 0.39 mm behind the standard riser top and −0.23 ± 0.23 mm along ST; SRn axis (−0.26, −0.05);
ST0 −0.950, SZ0 40.630; capillary CPS 59.69 on the analyzer focus. ST0 and SN_f cannot be told apart by these data
(no measurement on the analyzer focus): SN_f = −0.525 is taken so that the measured surfaces (SN ≈ 0) were in the
analyzer focal plane. The first configuration from RG_GMC alone (`…_234000_capillary.json`, ST0 fixed at 0) is
1.3 mm off in ST for Cav. ST0 agrees with experience (plate centre at ST ≈ −1 without rotation). SZ0 and the
CPS reference probably depend on the capillary alignment (pitch): all four measurements were made after the same
alignment. After realigning the capillary, run InitialCalibration with *optics only* (one set at SRn 120 / SRz 0;
SN_f and the axes are kept).

### Initial calibration (`InitialCalibration.py`, `docs/initial_calibration.png`)

At start-up the program asks what was recalibrated (`docs/initial_calibration_mode.png`):

- **Optics only** (default, the usual case: capillary / zone plate realigned): ST0, SZ0 and the optic reference are
  fitted; SN_f, the SRn axis and the SRz axis offsets are kept from the newest configuration of the chosen optic. The
  sets are measured as the stage is run: SN left as it is, feature onto the beam with ST / SZ, optic refocused. One set
  (SRn 120, SRz 0) is enough; sets with SRn / SRz rotated check the kept axes (warning above 0.02 mm rms: the mechanics
  have changed, use optics + motors). Not offered when there is no configuration yet.
- **Optics + motors** (re-homing, maintenance, first use): all constants, as below.

Separate program for the first start or after re-homing the motors: beamline staff measure one reference
feature in 3 (minimum) or 5 (recommended) stage orientations, the constants are fitted and saved as a new
configuration for the chosen optic (zone plate + OSA or capillary). *Show front / side view*
(`docs/initial_calibration_feature_view.png`) draws the plate with the entered feature to check its position.
The optic position at best focus can be noted in every set (optic + = towards the sample); all constants and
the optics reference are fitted every time and compared with the newest configuration. After *Compute*, test
points at other rotations are predicted: staff tick *Found* (within 0.05 mm) or enter the real ST, SZ and
optic position, and the configuration is corrected with them, round after round, until it is good enough.
Protocol: [`docs/initial_calibration_protocol.md`](docs/initial_calibration_protocol.md).

### Configuration window (toolbar *Configuration…*, `docs/calibration_dialog.png`)

Read-only: the configuration in use (time stamp, optic, comment), its constants and optics reference. An
older configuration can be selected for the session. There is no calibration in QuickAlignment: the
configuration comes from InitialCalibration (all constants fitted and checked at test points within
0.05 mm), and what remains for a sample – mostly the error of drawing it on the plate – is corrected with
*Found here* in the Stage & Optics tab. A configuration error of 0.05 mm, absorbed that way, leaves a few
10 µm at other rotations (tested). If *Found here* has to move a sample by more than 0.3 mm, the program
suggests checking whether the configuration is outdated (motors re-homed): then beamline staff run
InitialCalibration.

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
