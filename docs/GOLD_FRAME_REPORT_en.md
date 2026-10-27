# Gold-frame calibration from SPEM intensity maps

Report on the method proposed by the beamline team: ST, SZ, SN, the SRn axis and the SRz axis from three
total-intensity maps of the gold reference frame. Simulations, answers to the open questions, and the
program that turns the measured maps into a QuickAlignment configuration (`GoldFrameCalibration.py`).

## Contents

1. [Summary](#summary)
2. [The sample and the three maps](#the-sample-and-the-three-maps)
3. [Geometry: what each map measures](#geometry-what-each-map-measures)
4. [Perfect case and imperfect cases](#perfect-case-and-imperfect-cases)
5. [Is step 3 valid?](#is-step-3-valid)
6. [Analyzer focus and beam position](#analyzer-focus-and-beam-position)
7. [Accuracy: simulated measurements fitted](#accuracy-simulated-measurements-fitted)
8. [Recommended protocol](#recommended-protocol)
9. [The program](#the-program)
10. [Limits](#limits)

## Summary

- **Steps 1 and 2 are sound** and need no correction for the analyzer: with SN fixed, a ST/SZ translation at
  SRz = 0 and an SRn rotation about the plate normal keep the illuminated point at the same place along the beam.
- **Step 3 is valid**: the frame edges, seen against SRz, give the SRz axis (its offset along ST and its depth
  behind the surface), but only if:
  1. ST0 is fitted again in step 3. The depth enters only through (1 − cos SRz), at most 0.09 over SRz −25…+10°,
     so a 5 µm error in ST0 from step 1 becomes a ~50 µm error in the depth.
  2. The tilt of the gold face about the vertical is fitted. A 2° tilt left out moves the SRz offset along ST by about
     0.09 mm; the frame width against SRz shows the tilt.
  3. The ST range follows the frame. With the SRz axis 2.6 mm behind the surface (present configuration), the frame
     moves by about 1.4 mm in ST between SRz 0 and −25°.
- **Analyzer focus and beam position:** every map locates the gold edges where the *beam* crosses them, whatever
  the analyzer sees, so the fitted positions need no correction. Two points matter:
  1. In step 3 with SN fixed, the illuminated point slides along the beam during each ST line, up to about 1.5 mm
     here.
     With a narrow analyzer acceptance, part of the frame then disappears. Better: move SN with ST along the turned
     surface (ΔSN = ΔST · tan(−SRz)), or set SN line by line.
  2. SN_f must come from an SN scan on the gold (maximum intensity). If the beam passes beside the analyzer focus,
     that maximum is where the beam crosses the analyzer axis, and SN_f takes it up (Δ = √2 × the offset). Nothing
     else changes.
- **Accuracy (simulation):** a few µm for ST0, SZ0 and the SRn axis, about 10–20 µm for the SRz axis.
- **Limit of the method:** the frame is taken as the plate centre. Any error in where it is mounted goes into ST0,
  SZ0 and the axes, and so into every other sample's predicted position.

## The sample and the three maps

The reference: a square gold frame, 2 × 2 mm outside with a 1 × 1 mm hole, glued in principle at the centre of the
standard plate's riser. The glue may leave it shifted (u, v), turned in its plane, raised (gold + glue above the
riser top, *h*) and tilted. Only the total photoemission intensity is used (`heason/total_int`, or `image32`
summed): gold is bright, the Ta riser and the hole floor are darker.

| map | scanned | fixed | gives |
|---|---|---|---|
| 1 | ST × SZ, about ±2 mm | SRn 120, SRz 0, SN at the gold focus | frame centre (ST0, SZ0), in-plane rotation, ST / SZ scales, shear |
| 2 | SZ (±2.5 mm) for each SRn (120 ± 60°) | ST at the frame centre | SRn axis (u, v) on the plate |
| 3 | ST (±3.5 mm) for each SRz (−25…+10°) | SRn 120, SZ at the frame centre (through the hole) | SRz axis: offset along ST, depth behind the surface (and ST0 again) |

Before the maps: an **SN scan on the gold** (ST following, ΔST = −ΔSN, so the point stays on the beam) gives
SN_gold (maximum) and, from its width, the analyzer acceptance (section 6). Then focus the optic there.

Coordinates as in QuickAlignment. Plate frame (u, v): front view, tab up. Lab: origin = analyzer focus, beam along +y,
+ST along t = (1, −1, 0)/√2, +SN along n = (1, 1, 0)/√2 (away from the analyzer). The maps are drawn as ANTARES
draws them: ST decreasing to the right and SZ decreasing upwards, so right = +u and up = +v, the view from the
analyzer.

![Top view](images/gold_frame/geometry.png)

## Geometry: what each map measures

At SRn 120, SRz 0, with the gold top at the analyzer focus, the beam meets the plate at

  u = ST0 − ST − d,  v = SZ0 − SZ,  d = SN − SN_gold

(the beam meets the surface at 45°, so a surface out of focus by d moves the point by d along −u).

**Map 1.** A 1:1 image of the frame (mirrored like the motors). Its centre gives ST0 and SZ0. Its widths give the ST
and SZ scales. The angle of its edges gives the in-plane rotation, and a different angle for the vertical and the
horizontal edges is a shear. Two out-of-plane effects show up here:
- A gold face tilted by β about the vertical (v) makes the frame look (cos β + sin β) times as wide in ST. A 2° tilt
  reads as an "ST scale" of 1.036. Map 3 tells the two apart.
- A tilt about the horizontal (u) shears the image.

**Map 2.** SRn turns the plate about its normal, around the axis A = (A_u, A_v) on the plate. With Δ = c − A (frame
centre minus axis) and α = SRn − 120, the frame centre seen at a fixed ST lies at

  SZ_c(α) = SZ_c(0) − [Δ_u sin α + Δ_v (cos α − 1)]

and the SZ line misses the centre by p(α) = Δ_u (cos α − 1) − Δ_v sin α. In the perfect case (A = c) the pattern is
symmetric about SRn 120. The frame's own corners make the cusps at α = ±45°. An axis offset makes the bands wave
(sin α: Δ_u, 1 − cos α: Δ_v) and makes the pattern asymmetric (p(α) shifts the cusps and changes the band widths).

**Map 3.** SRz turns the stage about a vertical axis. Its offset along ST (o_t, plate frame) and its depth D behind the
gold surface (D = h + `srz_offset_n`) set where the frame is found. With a = −SRz, Y = o_t − u_c and SN fixed:

  ST_c(a) − ST_c(0) = (D + Y)(cos a − 1) − (D − Y) sin a

  width in ST = W (cos a + sin a) (W = 2 mm or 1 mm; a tilt β of the face adds β to a)

The sin a term gives D − Y well. The cos a − 1 term (≤ 0.094 here) gives D + Y about ten times less precisely.

![Frame centre and width against SRz](images/gold_frame/srz_curves.png)

## Perfect case and imperfect cases

All maps simulated with the program: the beam traced through the stage model of QuickAlignment, the frame's
walls and their shadows (the dark strip on the +u side of each edge is the beam hitting a side wall), Poisson noise.
Magenta dashed: the perfect frame on the perfect stage. Cyan: the true edges.

**Perfect.** Frame at the plate centre, SRn axis through it, SRz axis in its surface:
- map 1: a square centred on (ST0, SZ0);
- map 2: symmetric about SRn 120;
- map 3: the frame stays at the same ST, only its width changes.

![Perfect](images/gold_frame/perfect.png)

**Horizontal offset of the frame (0.3 mm along +u, 0.2 mm down).**
- Map 1 moves rigidly: ΔST = −0.3, ΔSZ = +0.2.
- Map 2 changes shape. For the SRn axis (still at the plate centre) the frame is now off-axis, so its centre waves
  with SRn and the pattern is no longer symmetric.
- Map 3 moves by −0.3 in ST and the frame's track changes slope: Y = −0.3 enters both terms.

The fit cannot tell this offset from an offset of the whole plate. It goes into ST0/SZ0 and into the axes.

![Frame offset](images/gold_frame/frame_offset.png)

**SRn axis offset (0.4 mm, 0.3 mm from the frame centre).** Map 1 is unchanged. In map 2 the bands follow
SZ_c(α) above and the cusps move off ±45°.

![SRn axis offset](images/gold_frame/srn_axis.png)

**SRz axis offset (0.5 mm along +ST, 1.0 mm behind the surface).** Map 1 is unchanged. In map 3 the frame drifts
in ST with SRz, as in the formula above.

![SRz axis offset](images/gold_frame/srz_axis.png)

**The axes of the present configuration** (SRn axis (−0.26, −0.05), SRz axis 2.59 mm behind the riser top, −0.23 mm
along ST). The frame moves about 1.4 mm in ST over the SRz range: the ST range of map 3 must allow for it.

![Present configuration](images/gold_frame/real_axes.png)

**In-plane rotation (3°) and tilt of the face (2° about v).**
- Map 1 shows the rotation directly, and the tilt as an ST scale of 1.036.
- Map 2 is shifted by the rotation along SRn.
- In map 3 the tilt changes the width against SRz.

![Rotation and tilt](images/gold_frame/rotation_tilt.png)

## Is step 3 valid?

Yes. It measures the SRz axis relative to the beam, which is what QuickAlignment needs. In the simulations, fitted
as below, it gives the axis to about 10–20 µm (table in section 7). Conditions:

1. **SRn back at 120**, exactly as in map 1 (the same SRn reference), and SZ through the hole, so that every line
   shows four edges.
2. **Fit ST0 together with the SRz axis.** In a real ANTARES map the inner axis is the fly axis, so in map 1 (SZ
   inner) ST is sampled point by point. Its edges are then only known to ± half a step, the same for every row.
   With 20 µm steps that leaves an error of a few µm in ST0. Step 3 amplifies it about 10× in the depth, because the
   depth enters only through 1 − cos a. In map 3 ST is the fast axis, so ST0 is fitted there (the program does).
3. **Fit the tilt of the gold face about v.** Glue easily leaves 1–2°. Not fitted, a 2° tilt biases the SRz offset
   along ST by about 0.09 mm. The width W (cos(a + β) + sin(a + β)) against SRz makes β measurable. The program fits
   it, keeping the apparent width of map 1, and so separates the ST motor scale from the tilt.
4. **ST range:** the frame centre moves by (D + Y)(cos a − 1) − (D − Y) sin a. With D ≈ 2.6 mm that is about 1.4 mm
   at −25°. Take ±3.5 mm around the centre, or follow the frame line by line.
5. **Use the edges, not the intensity.** The analyzer weights the intensity (next section), but a sharp edge stays
   where it is. Lines where part of the frame is lost (outside the range or not seen) are recognised and left out.

The gold height *h* enters only the conversion D → `srz_offset_n` = D − h, and SN_f = SN_gold − h. Measure it from
the SN-scan peaks on the gold and on the riser.

## Analyzer focus and beam position

**Steps 1 and 2: no correction.** With SN fixed, an ST/SZ translation at SRz 0 and an SRn rotation keep the
illuminated point at the same place along the beam. Its distance from the analyzer focus does not change, so the
analyzer only scales the whole map.

**Step 3 with SN fixed: the point slides along the beam.** The turned surface is no longer parallel to ST. Along
one ST line the illuminated point moves along the beam by

  Δy = −√2 ΔST sin a / (cos a + sin a)

that is ±0.7 mm for ΔST = ±1.5 mm at a = 25°, of which Δy/√2 is across the analyzer axis and Δy/√2 along it.
Over the whole map 3 below (ST ±3.5 mm) it ranges from −1.7 to +1.5 mm. With an analyzer acceptance of 0.5 mm (FWHM, a placeholder:
measure it, see below), part of the frame then gets no signal (left).

The edges that remain are still right: the fit leaves out the lines that lost an edge and finds the same axis.
To keep the whole frame visible:
- move **SN with ST along the turned surface**, ΔSN = ΔST · tan(−SRz) (right): two actuators on the fast axis,
  which the file format allows (`actuator_1_1`, `actuator_1_2`); or
- take **one ST line per SRz with SN set** so that the frame centre is in focus (the program reads a series of line
  files).

The defocus of the beam itself (±1 mm out of the optic focus) widens the spot by only 2 NA Δy ≈ 10 µm.

![Analyzer acceptance in step 3](images/gold_frame/analyzer.png)

**Beam beside the analyzer focus.** If the beam line passes a distance b beside the analyzer focus (horizontally,
across the beam), the SN scan on the gold peaks where the beam crosses the analyzer axis. That is √2 b further along
it, so SN_f changes by √2 b (0.14 mm for b = 0.1 mm, below). All positions stay those of the beam, so ST, SZ and the
axes are unchanged (table, last line).

What remains: the found sample is on the beam where it crosses the analyzer axis, √2 b from the true analyzer focus
along that axis (lab y = b: the "beam" column of the table). No stage constant can remove that; it is the beam
alignment. A vertical offset only lowers the intensity and goes into SZ0.

The width of the SN scan (here 0.29 mm) is the analyzer acceptance across its axis. Measure it once: it tells how
far the illuminated point may slide in step 3.

![SN scan on the gold](images/gold_frame/sn_scan.png)

## Accuracy: simulated measurements fitted

Every case below was simulated (20 µm pixels, Poisson noise at 3000 counts on gold) on the axes of the present
configuration. The maps were fitted by the program as it fits measured maps.

Two kinds of numbers:
- **Error:** fitted minus true constant, after removing what the method cannot see (a frame shift goes into ST0, SZ0
  and the axes).
- **Test point:** where the fitted configuration really sends the beam on the true stage, for the plate point
  (1.5, 1.0) at SRn 100, SRz −15. "Plate" is the miss on the plate; "beam" is the distance from the analyzer focus
  along the beam.

<!-- RESULTS TABLE -->
Errors in µm (fitted − true).

| case | map 3 lines | ST0 | SZ0 | SN_f | SRn axis u, v | SRz offset ST, SN (± σ) | test point: plate / beam |
|---|---|---|---|---|---|---|---|
| perfect frame | 36/36 | 0 | 0 | 0 | +1, 0 | 0 ± 9, -10 ± 8 | 2 / -1 |
| frame shifted (0.3, −0.2) mm, turned 3° | 36/36 | 0 | 0 | 0 | 0, 0 | -5 ± 4, -6 ± 3 | 360 / -2 |
| ST scale 1.02, SZ scale 0.99 | 36/36 | 0 | 0 | 0 | +1, 0 | +3 ± 3, +2 ± 3 | 38 / +15 |
| face tilted 2° about v, tilt not fitted | 36/36 | 0 | 0 | 0 | +8, -2 | -89 ± 19, -3 ± 15 | 17 / -27 |
| face tilted 2° about v, tilt fitted | 36/36 | 0 | 0 | 0 | +8, -2 | -19 ± 15, -6 ± 11 | 4 / -6 |
| analyzer 0.5 mm, plain ST lines | 23/36 | 0 | 0 | 0 | +1, 0 | +1 ± 30, -2 ± 30 | 1 / 0 |
| analyzer 0.5 mm, ST + SN along the surface | 36/36 | 0 | 0 | 0 | +1, 0 | +6 ± 11, -2 ± 8 | 2 / +2 |
| beam 0.1 mm beside the analyzer focus | 30/36 | +2 | 0 | +140 | +5, 0 | +15 ± 9, +3 ± 6 | 2 / +102 |
<!-- /RESULTS TABLE -->

Reading the table:
- **Mounting offset of the frame:** the fit is right for the frame, but every other sample is then off by that offset
  (0.36 mm here), as with any single reference feature.
- **ST / SZ scales:** QuickAlignment assumes 1, so a scale of 1.02 costs a few tens of µm away from the centre.
  The program reports the scales.
- **Tilt:** ignoring it moves the SRz offset along ST by about 0.09 mm; fitting it removes most of that.
- **Narrow analyzer:** the plain ST lines lose part of map 3 but give the same axis.
- **Beam beside the focus:** SN_f takes up √2 b; the point is found on the beam, √2 b from the analyzer focus along
  the analyzer axis.

## Recommended protocol

1. SRn 120, SRz 0, PIX = PIY = 150. Find the gold, then run the **SN scan** (ST following) on a gold bar:
   SN_gold, and the analyzer acceptance from its width. Run the same scan on the riser for the gold height *h*
   (difference of the peaks). Focus the optic on the gold.
2. **Map 1:** ST × SZ, ±2 mm around the frame, SN = SN_gold. SZ is the fast axis (as usual). ST steps of 10–20 µm
   (ST0 and the ST scale are refined in map 3).
3. **Map 2:** ST at the frame centre of map 1, SZ ±2.5 mm (fast, 10 µm), SRn 60…180° in steps of 2°.
4. **Map 3:** SRn 120, SZ at the frame centre (through the hole), SRz −25…+10° in steps of 1°, ST ±3.5 mm (fast,
   10 µm). Best with SN following ST along the surface (ΔSN = ΔST · tan(−SRz)), or SN set line by line. With SN
   fixed it still works if the analyzer acceptance is wide enough (SN scan width ≳ 1 mm).
5. Open `GoldFrameCalibration.py`, load the three maps, set SN gold and the gold height, press *Fit*. Check:
   - the residuals: a few µm;
   - the lines left out: only where the frame is lost;
   - the fitted tilt: ≲ 2°;
   - the shear: ≲ 0.5°;
   - the change from the previous configuration.

   Then `--save`.
6. As with InitialCalibration: try the new configuration on a sample of known position at another rotation
   (QuickAlignment, *Found here*).

## The program

**`GoldFrameCalibration.py`** (double-click; Windows: `GoldFrameCalibration.pyw`) opens the calibration window:

1. **Load** the three maps (*Load…*): one 2-D `.nxs` file, or several line files (one per SRn / SRz) selected
   together. Maps 2 and 3 are optional; an axis without its map is kept from the newest configuration. Under each
   map: what was read (kind, size, ranges, fixed motors, intensity channel, optic position).
2. **Settings:**
   - SN gold (default: the SN of map 1);
   - gold height;
   - where the frame is taken to be on the plate (default the centre), its outer size and hole;
   - fit the tilt of the gold face;
   - divide by the diode;
   - the optic and its position at the gold focus (default: the zone-plate channel of map 1, else the newest
     configuration's reference).
3. **Fit:**
   - *Results* tab: the seven constants with their uncertainty, the newest configuration and the change;
     the details of each map (rms, lines used and left out, rotation, scales, shear, tilt) and warnings.
   - *Maps* tab: the maps with the fitted edges (orange).
4. **Save as new configuration** (with a comment): `configs/calibration_<time>_<optic>.json`, which QuickAlignment
   loads at its next start. What was measured and fitted (scales, rotation, tilt, residuals, files) goes into its
   `check` record.

*Load a simulated example* simulates the three maps of a frame with small known faults and loads them, with the
true values in the status bar, to try the window.

![Calibration window: results](images/gold_frame/calibration_results.png)

![Calibration window: maps with the fitted edges](images/gold_frame/calibration_maps.png)

**`GoldFrameSimulator.py`** (double-click; `GoldFrameSimulator.pyw`; also *Open the simulator…* in the window) is the
interactive simulator. Sliders for:
- the frame: offset, rotation, tilts, height;
- the stage: SRn axis, SRz offsets, ST scale;
- the beam and analyzer: acceptance, beam offset;
- a switch for step 3 along the surface.

The three maps are drawn with the edges of the perfect frame (magenta).

![Simulator](images/gold_frame/simulator.png)

From a console, the same without windows:
- `python GoldFrameCalibration.py simulate [--frame-u … --srz-offset-n … --analyzer-fwhm-h … --surface]`: the three
  maps for the given faults, as ANTARES `.nxs` files (or `.npz` without h5py), a figure and the true values.
- `python GoldFrameCalibration.py fit --step1 F --step2 F… --step3 F… [--sn-gold] [--height] [--no-tilt]
  [--optic capillary|zone_plate] [--optic-position] [--plot PNG] [--save]`.

**Reading the files** (`quickalignment/spem_nxs.py`) follows a real SZ × SRn scan (`Cp_2023-05-28_22-08-47.nxs`).
- *Channels:* the `scan_data/data_NN` are recognised by their `long_name` (the NN numbers change between scan
  configurations).
- *Intensity:* `heason/total_int` (= vsum(mbsProj)); else `mbs/image32` (or `xproj`) summed per point, one line at a
  time.
- *Positions:* the motor readbacks of every point (`actuator_1_1`, (outer, inner)) are fitted line by line, which
  takes up a fly-scan lag or a zig-zag. The fixed motors come from `ANTARES/i12-m-cx1-ex-sample-mt_*/position`.
- *Normalisation:* `normalize` divides by the diode (`dtc_diode`).
- *Several actuators* on the fast axis (ST + SN) are supported, and so are series of 1-D line files, one per angle.

ARPES viewer's own SPEM loader would take this layout for a deflector map: `scan_data/actuator_1_1` exists and
the trajectory groups are `actuator_1_2` / `actuator_2_20`, not `actuator_*_1`. The gold-frame program therefore
reads the files itself.

## Limits

- **The frame is the plate reference.** Its mounting offset cannot be seen; it goes into ST0/SZ0 and the axes. To
  check it, measure a plate feature (riser edge) or a sample of known position.
- **SRn reference:** the frame's rotation and the SRn zero cannot be separated. QuickAlignment keeps SRn 120 = plate
  vertical, and the rotation found is reported.
- **ST / SZ scales and shear** are reported, not used by QuickAlignment.
- **The simulator's intensities and analyzer acceptance** (Gaussian, 0.5 mm) are placeholders. The fit does not
  depend on them, only the simulated pictures do. Measure the acceptance with the SN scan.
- **The gold height *h*** shifts SN_f and `srz_offset_n` together. Measure it.
