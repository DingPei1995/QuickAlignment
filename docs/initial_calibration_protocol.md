# Initial calibration – protocol for beamline staff

Run **`InitialCalibration.py`** (double-click; Windows: `InitialCalibration.pyw`) to create the calibration
configuration that QuickAlignment loads at start-up.

## Optics only or optics + motors

At start-up the program asks what was recalibrated:

- **Optics only** (default): the focusing optic was realigned, the motors were not re-homed. The beam meets the plate
  elsewhere and the optic focus moves, but the mechanics stay: only ST0, SZ0 and the optic reference are fitted;
  SN_f, the SRn axis and the SRz axis offsets are kept from the newest configuration of the chosen optic.
  For every set: set SRn / SRz (PIX = PIY = 150 µm), **leave SN as it is**, bring the feature onto the beam with
  ST / SZ, refocus the optic, write down ST, SZ, SN and the optic position. Set 1 (SRn 120, SRz 0) is enough;
  set 2 (SRn 140) and set 3 (SRz −20) check the kept axes. If their residuals stay above ~0.05 mm the mechanics
  have changed: start again with *optics + motors*. The test points work as below.
- **Optics + motors**: the rest of this protocol (all constants, the feature at the analyzer focus in every set).

## When

- first use of QuickAlignment
- after re-homing / resetting the manipulator motors (ST, SN, SZ, SRn, SRz)
- after maintenance of the manipulator or the sample receptacle
- when samples are found far (≳ 0.3 mm, the same shift for several samples) from where QuickAlignment predicts them
  (*Found here* in QuickAlignment warns about it)

## What is determined

| constant | meaning | needs |
|---|---|---|
| ST0, SZ0 | ST / SZ putting the plate centre on the beam | set 1 |
| SN_f | SN putting the protruding plate surface in the analyzer focus | set 1 |
| SRn axis x, y | position of the SRn rotation axis on the plate | set 2 (SRn rotated) |
| SRz offset ST, SN | offset of the SRz axis from the plate-surface centre line | set 3 (SRz rotated) |
| optics reference | optic position focusing on the analyzer focus | optic position in set 1 (better: in every set) |

PIX / PIY are kept at 150 µm and not calibrated. SRn = 120 (plate vertical, tab up) is taken as the
mechanical reference.

**Minimum: 3 sets** (7 constants, each set gives ST, SZ, SN = 3 numbers; an SRn rotation only moves
ST, SZ and an SRz rotation only moves ST, SN). **Recommended: 5 sets**, so that a wrong measurement shows
up in the residuals.

## Reference feature

One small, sharp feature that can be found with the beam (corner of a reference sample, a mark),
close to the plate centre so that it stays reachable when rotating. Note its plate coordinates
x, y (mm, from the centre of the back plate, front view with the tab up) and its height H
above the plate surface. **Use the same feature in every set.**

Press **Show front / side view** to check the entered position: the plate is drawn from the analyzer
(front view, with the SRn axis of the newest configuration, or of the fit once computed) and from the side (heights, analyzer to the
right), with the feature marked. A feature outside the sample area is flagged, and the ST / SZ / SN
where each set should find the feature with that configuration are listed (motor travel ranges
checked).

## Sets

| set | SRn | SRz | purpose |
|---|---|---|---|
| 1 | 120 | 0 | ST0, SZ0, SN_f, optics reference |
| 2 | 140 | 0 | SRn axis |
| 3 | 120 | −10 | SRz axis |
| 4 | 100 | 0 | check (recommended) |
| 5 | 120 | +10 | check (recommended) |

Larger rotations give a more precise axis: |SRn − 120| ≥ 20°, |SRz| as large as the geometry allows (≥ 10°).

## For every set

1. Set SRn and SRz; PIX = PIY = 150 µm.
2. Bring the feature onto the beam with ST / SZ (scan across it, take the centre of the edge / feature).
3. Bring it to the analyzer focus with SN.
4. Repeat 2–3 until stable; write down ST, SZ, SN.
5. Optimise the optic focus on the feature and write down the optic position: at least in set 1,
   preferably in every set. The feature is at the analyzer focus every time, so every position
   measures the optics reference; it is fitted with the stage constants, and the optic residuals show how
   well the optic focus is reproduced. Increasing the optic motor moves the optic towards the sample.

## Test points: check and correct the configuration

After *Compute*, the **Test points** tab lists rotations not used in the sets (SRn ± 30°, SRz ± 15°,
and SRn / SRz combined) with the ST, SZ, SN and optic position where the configuration puts the feature.
For each test point:

1. Move to the *Go to* SRn, SRz, ST, SZ, SN and optic position.
2. If the feature is on the beam and in focus there **within 0.05 mm**, tick **Found**.
3. If not: keep SRn, SRz and SN, bring the feature onto the beam with ST / SZ, focus the optic, and enter
   the **real ST, SZ and optic position** (optic optional).

Press **Correct the configuration with the test results**: the real positions are added to the fit (2–3
equations each: the feature on the beam, in the optic focus), all constants are fitted again, and a new
round of test points is predicted. Found points only confirm the configuration and are not fitted.
Answered rounds stay in the table (read-only) with their deviations; the angles of a new test point may be
changed if a position is out of the travel range. Repeat until all test points of a round are found, or the
deviations are small enough for you, then save. A set that stays an outlier in the residuals after the
test points were added was probably measured wrongly: untick it and correct again.

## In the program

1. Choose the plate, enter x, y, H of the reference feature and check them with *Show front / side view*.
2. Choose the focusing optic (**zone plate + OSA** or **capillary**). Results are compared with the newest
   configuration; all 7 constants (and the optics reference) are fitted every time.
3. Enter ST, SZ, SN and the optic position of every set (untick sets that were not measured; the optic
   position may be left empty in some sets).
4. Press **Compute**: fitted constants with uncertainties and change from the newest configuration,
   residuals per set (ST, SZ, SN, optic).
5. Work through the test points (above) until the configuration is good enough.
   With 5 sets the residuals should be ≲ 0.01–0.02 mm; one large residual usually means that set was
   measured on another point or out of focus – re-measure it.
6. Add a comment (date, reason) and press **Save as new configuration**. The file
   `configs/calibration_YYYY-MM-DD_HHMMSS_<optic>.json` (`zone_plate` or `capillary`) is loaded by
   QuickAlignment at the next start when that optic is chosen. A configuration for one optic does not
   replace the other optic's: QuickAlignment always loads the newest file of the chosen optic.
