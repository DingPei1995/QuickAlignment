# QuickAlignment — Beamline Staff Guide

ANTARES beamline (SOLEIL) · calibrating the stage model with InitialCalibration, and looking after the program

## Contents

1. [What the staff are responsible for](#what-the-staff-are-responsible-for)
2. [The stage model and its constants](#the-stage-model-and-its-constants)
3. [When to recalibrate](#when-to-recalibrate)
4. [Starting InitialCalibration](#starting-initialcalibration)
5. [Optics only (the usual case)](#optics-only-the-usual-case)
6. [Optics + motors (full calibration)](#optics--motors-full-calibration)
7. [Test points: checking and correcting](#test-points-checking-and-correcting)
8. [Saving and how QuickAlignment uses the file](#saving-and-how-quickalignment-uses-the-file)
9. [Looking after the program](#looking-after-the-program)
10. [Troubleshooting](#troubleshooting)

---

## What the staff are responsible for

Users only *read* the stage calibration: QuickAlignment loads the newest **configuration file** for the chosen optic
and has no way to change it. The configuration is made by beamline staff with the separate program
**InitialCalibration** and stored in `configs/`:

```
configs/calibration_YYYY-MM-DD_HHMMSS_<optic>.json      optic: zone_plate or capillary
```

One file per calibration, never overwritten. What remains for a user (mostly the error of drawing a sample on the
plate) is corrected by *Found here* in the Stage & Optics tab.

## The stage model and its constants

Stack, bottom to top: ST / SN / SZ translations → SRz → SRn → PIX / PIY piezo → plate. Top view: the beam runs
along +y, the analyzer focal plane at 45°, ST along it and SN perpendicular to it.

| constant | meaning | determined by |
|---|---|---|
| ST0, SZ0 | ST / SZ putting the plate centre on the beam (SRn 120°, SRz 0°) | set 1 |
| SN_f | SN putting the standard plate's raised surface (5.0 mm) in the analyzer focal plane | set 1 |
| SRn axis x, y | position of the SRn rotation axis on the plate | a set with SRn rotated |
| SRz offset ST, SN | offset of the SRz axis from the plate-surface centre line | a set with SRz rotated |
| optic reference | optic position putting the focus on the analyzer focus | optic position noted in the sets |

SRn = 120° (plate vertical, tab up) is the mechanical reference; PIX = PIY = 150 µm during calibration. The optic is
modelled as a focus point moving along the beam: ST, SZ and SRn do not change the surface plane, so they need no
optic move; SN, SRz and the sample height do (1 mm along SN moves the spot √2 mm along the beam).

## When to recalibrate

| situation | mode |
|---|---|
| capillary or zone plate realigned (beam meets the plate elsewhere, focus moved) | **optics only** |
| motors re-homed / reset, manipulator maintenance, receptacle changed | **optics + motors** |
| first use, or no configuration for this optic yet | **optics + motors** |
| users' *Found here* corrections above ~0.3 mm, same shift for several samples | check with optics only; full if the residuals stay large |

## Starting InitialCalibration

Double-click **`InitialCalibration.py`** (Windows: `InitialCalibration.pyw`). The first question is what was
recalibrated:

![Mode at start-up](images/guide/ic_mode.png)

*Optics only* is offered only when a configuration exists already (the mechanics are taken from it).

In both modes, first enter the **reference feature**: one small, sharp feature that can be found with the beam (the
corner of a reference sample, a mark), close to the plate centre so that it stays reachable when rotating. Enter its
plate coordinates x, y (mm, from the centre of the back plate, front view, tab up) and its height H above the plate
surface, and choose the **focusing optic**. **Show front / side view** draws the plate with the feature and lists
where each set should find it with the current configuration (motor ranges checked):

![Front and side view of the reference feature](images/guide/ic_feature.png)

Use the **same feature in every set**.

## Optics only (the usual case)

![Optics recalibration](images/guide/ic_optics.png)

Fitted: ST0, SZ0 and the optic reference. Kept from the newest configuration of the chosen optic: SN_f, the SRn axis
and the SRz axis offsets. For every set, as the stage is normally run:

1. Set SRn and SRz of the set; PIX = PIY = 150 µm.
2. **Leave SN as it is** (it does not have to be at the analyzer focus).
3. Bring the feature onto the beam with ST / SZ.
4. Refocus the optic on the feature.
5. Write down ST, SZ, SN and the optic position.

Set 1 (SRn 120°, SRz 0°) is enough. Sets 2–3 (SRn and SRz rotated) are recommended: they check the kept axes. If
their residuals stay above ~0.05 mm the mechanics have changed: restart the program and choose *optics + motors*.

## Optics + motors (full calibration)

All 7 constants and the optic reference are fitted. The feature is put **at the analyzer focus** in every set.

| set | SRn | SRz | purpose |
|---|---|---|---|
| 1 | 120 | 0 | ST0, SZ0, SN_f, optic reference |
| 2 | 140 | 0 | SRn axis |
| 3 | 120 | −10 | SRz axis |
| 4 | 100 | 0 | check (recommended) |
| 5 | 120 | +10 | check (recommended) |

**Minimum 3 sets** (each gives ST, SZ, SN); **5 recommended**, so that a wrong measurement shows up in the
residuals. Larger rotations give more precise axes (|SRn − 120| ≥ 20°, |SRz| ≥ 10° as far as the geometry allows).
Untick a set that was not measured; *Add set* adds one at other angles.

For every set:

1. Set SRn and SRz; PIX = PIY = 150 µm.
2. Bring the feature onto the beam with ST / SZ (scan across it, take the centre of the edge or feature).
3. Bring it to the analyzer focus with SN.
4. Repeat 2–3 until stable; write down ST, SZ, SN.
5. Optimise the optic focus on the feature and write down the optic position: at least in set 1, preferably in
   every set (+ moves the optic towards the sample).

Press **Compute**:

![Fit results](images/guide/ic_window.png)

- **Fitted constants** with their 1σ uncertainty, the value of the newest configuration and the change.
- **Residuals** per set (model − measured, mm) for ST, SZ, SN and the optic. With 5 sets they should be
  ≲ 0.01–0.02 mm. One large residual usually means that set was measured on another point or out of focus:
  re-measure it, or untick it.
- Warnings: *Not enough data* (which constants the sets cannot determine), *minimum data set* (mistakes cannot be
  detected), residuals above 0.05 mm, no optic position entered (optic reference not calibrated).
- A fit on impossible numbers (typing errors, NaN) is reported instead of being saved.

## Test points: checking and correcting

After *Compute*, the **Test points** tab predicts rotations not used in the sets (SRn ± 30°, SRz ± 15°, SRn and SRz
combined) with the ST, SZ, SN and optic position where the configuration puts the feature:

![Test points](images/guide/ic_tests.png)

For each test point:

1. Go to the predicted SRn, SRz, ST, SZ, SN and optic position.
2. If the feature is on the beam and in focus **within 0.05 mm**, tick **Found**.
3. If not: keep SRn, SRz and SN, bring the feature onto the beam with ST / SZ, focus the optic and enter the **real
   ST, SZ and optic position** (optic optional). Red predictions are outside a motor range: change the angles of
   that test point (it is predicted again).

**Correct the configuration with the test results → new test points** adds the real positions to the fit (found
points only confirm), fits all constants again and predicts a new round. Answered rounds stay in the table,
read-only, with their deviations. Repeat until all test points of a round are found, or the deviations are small
enough; a set that stays an outlier was probably measured wrongly: untick it and correct again.

## Saving and how QuickAlignment uses the file

Add a comment (date, reason, what was measured) and press **Save as new configuration**. The file is written
atomically (a failed write leaves no partial file) and contains the constants, the optics reference, the sets,
the test points and their residuals, for the record.

- QuickAlignment loads, at every start, the **newest file of the optic chosen** by the user. A zone-plate
  configuration does not replace the capillary one and vice versa.
- If there is no file for that optic, the stage constants of the newest file are used and the optic position is
  shown as uncalibrated.
- Damaged or foreign files in `configs/` are skipped. To withdraw a bad configuration, move its file out of
  `configs/` (do not edit it).
- Users can choose an older configuration for their session in *Configuration…* (read-only).
- The motor limits of ST, SZ, SN, SRn and SRz can be changed in *Configuration…* → *Motor limits*; they are saved in
  `configs/motor_limits.json` (delete the file to go back to the built-in limits).

### Anti-collision solids

The analyzer nose, the zone plate and OSA and the capillary are modelled as simple solids (README, *Anti-collision*).
The zone plate / OSA dimensions are **placeholders** and the capillary working distance an estimate: measure them
(distance of each front from the focus, width, thickness; for the OSA, the OSA_S position they belong to) and put
them in the configuration under `"collision"` (edit a copy, then save it as a new file). InitialCalibration keeps the
solids of the previous configuration of the same optic.

## Looking after the program

**Installation** (Python ≥ 3.9): `pip install -r requirements.txt` (PyQt5 or PySide6, numpy, matplotlib; pytest for the
tests). Start with `QuickAlignment.py` / `InitialCalibration.py` (`.pyw` on Windows without console).

**Tests**: `python -m pytest` in the QuickAlignment folder (about 120 tests, ~15 s; Qt runs off-screen). They cover
the stage model, rotations, calibration fits, file loading and the main windows.

**Limits that may need editing** (one place each):

| what | where |
|---|---|
| motor travel ranges ST, SN, SZ (input fields and warnings) | `MOTOR_SPECS` in `quickalignment/ui/stage_panel.py` |
| usable SRn / SRz, deflector limits, accepted offsets, photon energy range, zone-plate energy, work function | constants at the top of `quickalignment/bz_target.py` |
| analyzer slit orientation and the signs of slit / deflector angles | `AnalyzerGeometry` in `quickalignment/rotation.py` |
| plate drawings (standard, gating) | `quickalignment/geometry.py` |

**Robustness**: an unexpected error in the program is shown in a dialog (with details) and the program keeps
running, so that entered positions are not lost; please collect these details. Sessions and configurations are
written atomically; unreadable sessions give a message instead of a crash; impossible table entries (nan, inf, text)
are refused.

**Guides**: the screenshots are made by `python devtools/guide_screenshots.py`, the PDFs by
`python devtools/build_guides.py` (needs pandoc and Playwright with Chromium). Sources: `docs/USER_GUIDE_*.md`,
`docs/STAFF_GUIDE_*.md`.

## Troubleshooting

| symptom | likely cause / action |
|---|---|
| all samples found shifted by the same amount | ST0 / SZ0 changed (optic realigned): *optics only* |
| shift depends on the rotation | axes changed (motors re-homed): *optics + motors* |
| *Optics only* residuals of sets 2–3 above 0.05 mm | mechanics changed: *optics + motors* |
| one set with a large residual | wrong point, out of focus or typing error: re-measure or untick |
| *Not enough data: …* | the listed constants need a set with SRn and/or SRz rotated |
| a set needs SN below the collision limit | the feature is too low; use a feature on a higher sample |
| QuickAlignment shows *default* configuration | no readable file in `configs/` for any optic |
