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
| optics reference | optic position at best focus | set 1 |

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
5. At set 1 only: optimise the optic focus and write down the optic position.

## In the program

1. Choose the plate, enter x, y, H of the reference feature.
2. Enter ST, SZ, SN of every set (untick sets that were not measured), the optic position and the optic
   motor direction.
3. Press **Compute**: fitted constants with uncertainties, and residuals per set.
   With 5 sets the residuals should be ≲ 0.01–0.02 mm; one large residual usually means that set was
   measured on another point or out of focus – re-measure it.
4. Add a comment (date, reason) and press **Save as new configuration**. The file
   `configs/calibration_YYYY-MM-DD_HHMMSS.json` is loaded by QuickAlignment at the next start.
