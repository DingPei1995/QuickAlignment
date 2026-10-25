# QuickAlignment — User Guide

ANTARES beamline (SOLEIL) · finding samples on the plate, keeping them on the beam when rotating, and choosing the
rotation for a Brillouin-zone point

## Contents

1. [What QuickAlignment does](#what-quickalignment-does)
2. [Starting the program](#starting-the-program)
3. [Coordinates and motors](#coordinates-and-motors)
4. [Samples tab: drawing the plate](#samples-tab-drawing-the-plate)
5. [Stage & Optics tab: going to a sample](#stage--optics-tab-going-to-a-sample)
6. [Rotate sample tab: turning without losing the sample](#rotate-sample-tab-turning-without-losing-the-sample)
7. [Finding the angles for a Brillouin-zone point](#finding-the-angles-for-a-brillouin-zone-point)
8. [Sessions, plate and configuration](#sessions-plate-and-configuration)
9. [A typical beamtime](#a-typical-beamtime)
10. [Messages and what to do](#messages-and-what-to-do)

---

## What QuickAlignment does

On ANTARES the beam spot is at the micrometre scale or below, while the
sample plate is 18 × 15.5 mm. QuickAlignment turns the plate and sample geometry into **motor positions**:

- where each sample or device is at the start orientation (ST, SZ, SN at SRn = 120°, SRz = 0°);
- the ST / SN / SZ and the optic position that put a sample on the beam, in the analyzer focus;
- after a rotation (SRn, SRz), the positions that bring the same point back onto the beam;
- for a 2-D hexagonal crystal (graphene, WSe2, …), the SRn / SRz that bring Γ, K or M to the slit centre, and what to
  do when the stage cannot reach them.

The program never moves a motor. It computes numbers; you enter them on the beamline control system.

## Starting the program

Install once: `pip install PyQt5 numpy matplotlib`. Then double-click **`QuickAlignment.py`** (Windows:
`QuickAlignment.pyw`, no console window), or run `python QuickAlignment.py [session.json]`.

At every start the program asks which **sample plate** is mounted and which **focusing optic** is used:

![Plate and optic at start-up](images/guide/setup_dialog.png)

- **Standard Ta plate**: 18 × 15.5 mm back plate with an 11 mm wide raised part, 5.0 mm high.
- **Gating plate**: the same, with a contact block (3 gold pads, 4 screws); samples go only on the 11 × 10.5 mm above
  the block.
- **Custom plate**: the back plate with your own block (length, width, centre y and height from the back face).
- **Optic**: *zone plate + OSA* (95 eV only) or *capillary* (30–180 eV). The newest configuration made by the
  beamline staff for that optic is loaded (shown in the toolbar).

## Coordinates and motors

| name | meaning | range |
|---|---|---|
| x, y | position on the plate (mm), front view with the tab up, origin = centre of the back plate | – |
| H | sample height above the plate surface (mm) | – |
| ST | along the analyzer focal plane; ST < 0 moves the sample upper-left (top view) | −6 … 6 mm |
| SN | perpendicular to the analyzer focal plane; SN = 65 is the transfer position | −0.5 … 65 mm |
| SZ | vertical | 35 … 45 mm |
| SRn | azimuth about the sample normal; SRn = 120°: plate vertical, tab up | usable 60 … 180° |
| SRz | rotation about the vertical; SRz = 0: plate parallel to the analyzer focal plane | usable −25 … +10° |
| PIX, PIY | piezo stage, 0 … 300 µm, centre 150 µm | – |

At the start orientation a plate point (x, y) comes onto the beam at **ST = ST0 − x, SZ = SZ0 − y**, and a sample of
height H is in the analyzer focus at **SN = SN_f + H** (ST0, SZ0, SN_f come from the configuration). The motor fields
refuse values outside the travel ranges.

## Samples tab: drawing the plate

![Samples tab](images/guide/samples_tab.png)

- **Draw a sample**: drag on an empty part of the plate. **Move** it by dragging it, **resize** it by dragging an edge
  or corner (mouse positions are rounded to 0.1 mm). Or press *Add sample* and type the values.
- **Table**: name, x, y, length L, width W and height H can be typed exactly (typed values are not rounded).
  *Default H* is the height of new samples (0.525 mm: a standard Si wafer).
- **Devices on a substrate**: select the substrate, press *Add device*, choose the two reference edges (left/right,
  bottom/top) and the distances dx, dy to the device centre, or drag the blue marker. Devices move with their
  substrate. A substrate with devices is listed by its devices only in the target lists.
- **Status**: `ok`, or what is wrong (outside the sample area, overlapping, device outside its substrate). Red items
  on the drawing have a problem.
- Wheel = zoom, middle drag = pan, right click = whole plate, Del = delete the selection.

When all samples are drawn, press **Samples placed → Stage**.

## Stage & Optics tab: going to a sample

![Stage & Optics tab](images/guide/stage_tab.png)

The green box lists, for every sample and device, the **ST / SZ / SN at the start orientation** (SRn = 120°,
SRz = 0°, PIX = PIY = 150 µm) that put its centre on the beam in the analyzer focus.

1. Enter the current motor positions (absolute values, as on the control system).
2. Choose a **Target** and press **Bring target to focus**: ST, SN, SZ are computed for the entered SRn, SRz, PIX,
   PIY. If a motor would leave its range, nothing is changed and you are told which one.
3. **Focusing optic**: enter the optic position; press **Update schematic & optics**. The schematic shows the beam,
   the analyzer focus, the optic and the position **needed** for focus on the illuminated surface.
   *Use required position* copies it into the field.
4. After focusing by hand, **Set as optics reference** takes the current state as the optics reference for this
   session.
5. **Found here: correct its sample**: once a device is really on the beam and in focus, enter the positions, choose
   the device and press the button. Its sample (with all its devices) is moved on the drawing by Δx, Δy, ΔH: the
   error of the drawing. All other predictions then use the corrected position (saved with the session). A
   correction above 0.3 mm suggests that the configuration is outdated: tell the beamline staff.

The schematic is redrawn only with *Update schematic & optics*. Moving the mouse over the sample plane view shows
the ST, SZ that bring that point onto the beam and what lies there.

## Rotate sample tab: turning without losing the sample

![Rotate sample tab](images/guide/rotate_tab.png)

1. **Current position**: the positions with the point of interest on the beam and in focus, and the optic position
   (*From Stage tab* copies them).
2. **Wanted angles**: the new SRn and SRz (or use *Find angles for a BZ point…*, next section).
3. **Compute new position**: ST and SZ with the piezo centred and **SN kept**, and the optic position that refocuses.
   The text says how far the point then is from the analyzer focus (red above 50 µm: the spectra would be
   distorted). SRn alone keeps the surface plane; SRz does not.
4. Tick **Correct SN** to see SN, ST, SZ and the optic position that put the point **on the analyzer focus**. If a
   motor range does not allow it, the closest reachable position is given with its distance from the focus.
5. **Send to Stage & Optics tab** takes the shown solution (refused if it is out of range).

## Finding the angles for a Brillouin-zone point

Under *Wanted angles*, **Find angles for a BZ point…** answers the question *"how much do I turn SRn and SRz so that
K is at the centre of the slit, the slit runs along Γ–K and the deflector stays near 0?"* for 2-D hexagonal crystals.

![BZ point: reachable](images/guide/bz_reachable.png)

**What to enter** (read on the contour of a map in ARPES viewer; θ = deflector angle, contour x; φ = angle along the
slit, contour y):

1. **The map**: SRn and SRz at which it was measured (*From current position* takes them from the Rotate tab), its
   photon energy, the angles of **Γ** and of **one K or M point**.
2. **Crystal**: the in-plane lattice constant a (presets: graphene 2.46 Å, WSe2 3.282 Å, WS2, MoSe2, MoS2, hBN).
3. **Wanted**: the point (Γ, K or K′, only K, only K′, M), the **slit direction** (Γ–K, K–M, Γ–M, M–K), the photon
   energy of the new measurement, E − E_F of the point (e.g. −1.0 for the valence band top of WSe2 at K) and the work
   function (4.5 eV).

Press **Compute**. Below the inputs, *Γ–K on the map* compares the measured distance with the lattice constant (a
difference above 10 % means a wrong number, point or photon energy) and gives the tilt of the sample on the plate
(taken into account in the result).

**Result**: *Reachable* when, with the deflector at 0, the point is within |θ| ≤ 5° and |φ| ≤ 5° of the slit centre,
the slit within 2° of the wanted line, with SRn 60 … 180° and SRz −25 … +10°. The table lists every equivalent
point and both turning senses; the first row is the recommended one (SRz ≤ 0 first: the beam is then closer to the
surface normal and the spot smaller; then the smallest turn). *Beam to normal* is the incidence angle, 45° + SRz.

**Preview**: left, the map you will measure at the proposed angles (deflector across, slit angle up; the deflector
has gaps beyond ±8° and stops at ±12°; the green box is the accepted ±5°). Right, the 2-D zone in momentum,
oriented like your current map, with the current map (dashed) and the new analyzer window and slit (orange).

**Use these angles** writes SRn / SRz into *Wanted angles* and computes the new position. Set the deflector to 0
(and the photon energy, if it changed).

### When it cannot be reached

The manipulator has **no tilt axis**. A consequence: with a point at the slit centre and the deflector at 0, the
slit always runs along the line from Γ to that point (Γ–K for K). A slit *across* it (K–M, M–K) needs the deflector
at the emission angle of the point (15–20° at 95 eV), which the analyzer cannot do well:

![BZ point: zone-edge cut](images/guide/bz_zone_edge.png)

The window then proposes the **radial alternative**: K at the centre with the slit along Γ–K; the deflector
direction then runs along K–M, so a short **deflector map** (|θ| ≤ 5°) gives the K–M cut through K with little
distortion. *Show the radial alternative* switches to it.

When the emission angle is too large for the SRz range, the window gives the **photon energies** at which the point
is reachable:

![BZ point: more photon energy needed](images/guide/bz_photon_energy.png)

- ANTARES: 30–180 eV with the **capillary**; the **zone plate works at 95 eV only**. Changing the photon energy with
  the zone plate means changing to the capillary (realignment, capillary configuration).
- If SRn is the limit, the window says by how much to **turn the sample on the plate** when remounting it.
- If nothing works, the sample has to be remounted, or another, equivalent point chosen.

| example (E_F, work function 4.5 eV) | emission angle of K at 30 / 95 / 180 eV | K, slit along Γ–K |
|---|---|---|
| WSe2, a = 3.282 Å, Γ–K = 1.28 Å⁻¹ | 29.6° / 15.2° / 10.8° | reachable at 95 eV with SRz ≈ −15° |
| graphene, a = 2.46 Å, Γ–K = 1.70 Å⁻¹ | 41.2° / 20.4° / 14.5° | 95 eV: SRz ≈ −20°; 30 eV: not reachable (needs ≥ ~61 eV) |

The signs between the stage and the ARPES viewer contour have been checked once (deflector sign, 2026-09); on the
first use of a new kind of measurement, check that the point appears where the preview shows it.

## Sessions, plate and configuration

- **New / Open… / Save** (toolbar): a session holds the plate, the samples and devices (with their corrections) and
  the motor positions, in one JSON file. The first *Save* asks for the file name. Files are written safely: if
  saving fails (disk full, no permission), the previous file stays intact and a message tells you why.
- **Change plate…**: another plate; the samples are kept and misplaced ones are flagged.
- **Configuration…**: read-only view of the configuration in use (stage constants and optics reference), made by
  the beamline staff. An older configuration can be chosen for this session.

![Configuration window](images/guide/configuration_dialog.png)

## A typical beamtime

1. Start QuickAlignment, confirm plate and optic.
2. Draw the samples from your mounting photo (or open the session prepared before the beamtime); press
   *Samples placed → Stage*.
3. Go to the first sample with the listed ST / SZ / SN; find it with the beam (camera, photoemission map).
4. *Found here*: correct its position. The others now come out right too.
5. Measure a map at SRn = 120°, SRz = 0°; read Γ and one K / M point in ARPES viewer.
6. *Find angles for a BZ point…* → *Use these angles* → *Compute new position* (tick *Correct SN* if the point is
   more than 50 µm from the analyzer focus) → *Send to Stage & Optics tab*.
7. Save the session.

## Messages and what to do

| message | meaning / what to do |
|---|---|
| *Out of range: ST = … (range …)* | the point cannot be reached at these angles; choose other angles or use the corrected solution |
| *… µm from the analyzer focus* (red) | after an SRz turn the point left the focal plane: tick *Correct SN* |
| *Found here* moves a sample by > 0.3 mm | the drawing was off, or the configuration is outdated (motors re-homed): ask the staff |
| *The beam misses the plate* | ST / SZ do not put the beam on the plate |
| *Check the input: Γ–K on the map is …* | lattice constant, point or photon energy does not match the map |
| *An unexpected error occurred* | the program keeps running; check the last result, save the session and send the details to the staff |
