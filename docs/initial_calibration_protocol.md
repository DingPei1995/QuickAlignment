# Initial calibration – protocol for beamline staff

Run **`InitialCalibration.py`** (double-click; Windows: `InitialCalibration.pyw`) to create the calibration
configuration that QuickAlignment loads at start-up.

## When

- first use of QuickAlignment
- after re-homing / resetting the manipulator motors (ST, SN, SZ, SRn, SRz)
- after maintenance of the manipulator or the sample receptacle
- when the reference check in QuickAlignment (*Calibration… → Check*) shows large deviations

## What is determined

| constant | meaning | needs |
|---|---|---|
| ST0, SZ0 | ST / SZ putting the plate centre on the beam | set 1 |
| SN_f | SN putting the protruding plate surface in the analyzer focus | set 1 |
| SRn axis x, y | position of the SRn rotation axis on the plate | set 2 (SRn rotated) |
| SRz offset ST, SN | offset of the SRz axis from the plate-surface centre line | set 3 (SRz rotated) |
| optics reference | optic position at best focus | optic position in set 1 (better: in every set) |

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
(front view, with the SRn axis of the base configuration) and from the side (heights, analyzer to the
right), with the feature marked. A feature outside the sample area is flagged, and the ST / SZ / SN
where each set should find the feature with the base configuration are listed (motor travel ranges
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
   predicts the optics reference: their mean is saved, the scatter (optic residuals) shows how well the
   optic focus is reproduced.

## Correction of an existing configuration

After re-homing only ST / SZ / SN (the axes unchanged), choose **Fit: Correct ST0, SZ0, SN_f of the base
configuration**: one set (any SRn / SRz) is enough, more sets give a check. The SRn / SRz axes are kept
from the base configuration; without an optic position its optics reference is kept too (same optic).

## In the program

1. Choose the plate, enter x, y, H of the reference feature and check them with *Show front / side view*.
2. Choose the focusing optic (**zone plate + OSA** or **capillary**), the optic motor direction, the base
   configuration (default: the newest for this optic) and what to fit (new calibration / correction).
3. Enter ST, SZ, SN and the optic position of every set (untick sets that were not measured; the optic
   position may be left empty in some sets).
4. Press **Compute**: fitted constants with uncertainties and change from the base configuration,
   residuals per set, the optics reference with the optic residuals.
   With 5 sets the residuals should be ≲ 0.01–0.02 mm; one large residual usually means that set was
   measured on another point or out of focus – re-measure it.
5. Add a comment (date, reason) and press **Save as new configuration**. The file
   `configs/calibration_YYYY-MM-DD_HHMMSS_<optic>.json` (`zone_plate` or `capillary`) is loaded by
   QuickAlignment at the next start when that optic is chosen. A configuration for one optic does not
   replace the other optic's: QuickAlignment always loads the newest file of the chosen optic.
