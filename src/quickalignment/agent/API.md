# QuickAlignment, RealSampleCalibration, GoldFrameCalibration -- the agent's reference

*Generated from the program by `python -m quickalignment.agent.catalog --write`; do not edit by hand. A test
fails when it is out of date.*

Read this before anything else: it is everything an agent can do, by name.

## How to use it

- **MCP** (stdio, no window needed): `python Agent/quickalignment_mcp.py`, `python -m quickalignment.agent`
  (with `src/` on the path) or `quickalignment-mcp`. Same protocol as ARPES viewer: `readOnlyHint` is true
  for every tool that only reads; an error inside a tool comes back as a tool error with its text -- read it.
- **Python**: `from quickalignment.agent import AgentAPI; api = AgentAPI()`, then `api.alignment.*`,
  `api.real_sample.*`, `api.gold_frame.*` (section 3). Every method returns a JSON-friendly dict or raises
  `APIError` with a message for the user.
- Numbers always in the standard format (`1234.5`), never the system locale.

## 1. Workflow (the MCP server instructions)

```
QuickAlignment tools for the ANTARES beamline (SOLEIL) sample stage: find samples on a plate from photos
(alignment), and calibrate the stage (real-sample calibration or gold-frame calibration). Talk to the user in
their language; keep the tool names and numbers as they are. Numbers always use "." as decimal separator.

START OF A CONVERSATION (also when the user just sends photos of a sample plate):
1. Ask what they want to do: (a) find samples / align (QuickAlignment), or (b) calibrate the stage.
2. Ask which sample plate is mounted: standard Ta plate, gating plate (contact block, 4 screws), or a custom plate
   (block length, width, height above the back face, centre y). Ask which focusing optic: capillary or zone
   plate (+ OSA). Do not guess these: they change every position.

(a) FIND SAMPLES
1. align_start(plate, optic). It returns the four sample-area corners to read on a photo and their order:
   1 top left (tab side), 2 top right, 3 bottom right, 4 bottom left (front view: sample side, tab up).
2. The photo must be a file the server can read: ask for its path if you only see it in the chat. Call
   align_photo_grid(path) to see it with a pixel grid, read the 4 corners approximately, then zoom on each corner
   (align_photo_grid with region=[x0, y0, x1, y1], ~60-150 px wide) and read it to a few pixels. Corners are those of
   the sample area (standard plate: the 11 mm wide raised riser; gating plate: the riser above the contact block).
   If the photo is rotated, the order follows the plate (tab = top), not the image edges.
   (No file at all: read the corners on the image you see and pass image_size=[width, height] instead of path;
   say that this is less precise and that detect_samples / overlays are not available.)
   OPTIONAL 3D correction (off by default; only when the photo is clearly oblique, or the user asks): read also
   corners at another height (back plate top corners, tab top corners: align_photo_points_3d) and use
   align_register_photo_3d with >= 6 points instead of align_register_photo. It corrects the perspective for thick
   samples and devices; check its rms_px and residuals.
3. align_register_photo(corners_px, path). Then align_photo_overlay and LOOK at it: the green outline must lie on
   the sample-area edges. Show it to the user and ask them to confirm; fix the corners if it is off.
4. Samples: align_detect_samples (colour; pick a pixel on a sample with sample_colors_px to leave out silver paint)
   and/or read each sample's corners on the photo yourself -> align_add_sample_from_photo(points_px, height, name).
   The height H (sample thickness above the plate surface) is NOT visible from above: ask the user (default
   0.525 mm, a Si wafer). Name the samples as the user calls them. Check with align_photo_overlay.
5. Devices (small structures on a substrate): read them on the plate photo (align_add_device with photo_px), or on a
   microscope photo of the substrate registered with align_register_device_photo (2-4 point pairs: the same
   substrate corners / marks on the microscope photo and on the plate photo). Show align_photo_overlay again.
5b. ALWAYS ASK whether the user is satisfied with the samples found (show the overlay). If not, offer:
   (i) they tell you what to change (which sample, where, its size or height) -> align_update_sample /
   align_remove_sample / align_add_sample; (ii) MANUAL ANNOTATION: align_manual_annotation opens the photo window on
   their screen with the photo already registered; they draw the samples / devices themselves and press OK; then
   align_load_annotation. Use only what the user confirms; mark only the samples they want.
6. align_sample_positions: ST / SZ / SN of every sample and device at the start rotation (SRn 120, SRz 0, piezo
   150 / 150). Give the user this table.
7. Feedback from the beamline:
   - The user is at some position and wants another target: align_bring_to_beam(target, motors) (SN kept; if the
     result says the target is too far from the analyzer focus, call again with correct_sn=true).
   - "Found S1 at ST=…, SZ=…, SN=…" (on the beam, in focus): align_found_here(target, motors). It moves that sample on
     the plate (an error of the photo / drawing) and recomputes the positions. More than 0.3 mm for several samples:
     suggest a calibration.
   - The user says a sample is elsewhere / bigger / has another height: align_update_sample.
   - Rotation: align_rotate(srn, srz, motors=position with the point on the beam) gives ST, SZ, SN and the optic
     position (two answers: SN kept, and SN corrected; follow "recommended"). To turn an edge seen on the photo
     along the slit: align_align_edge(p1, p2) then align_rotate. For a Brillouin-zone point: align_bz_angles.
   - Before sending the user to a new position, mention any out_of_range or collisions in the result.
8. align_save_session(path) so the user can open the plate in the QuickAlignment program.

(b) CALIBRATION: ask real-sample calibration or gold-frame calibration.
- Real sample (RealSampleCalibration): ask whether only the focusing optic was realigned (mode "optics", the usual
  case) or the motors were re-homed / maintenance / first use (mode "full"), the optic, the plate, and a small sharp
  reference feature near the plate centre (plate x, y; height H). rsc_start(...), then follow rsc_guide: for every
  set tell the user exactly what to set and measure (the result says where the feature is expected), collect the
  numbers they read, rsc_measure_set, then rsc_fit; go through the test points one by one (rsc_answer_test), fit
  again, until a round is all found. rsc_save only after the user confirms.
  Full mode, how each set is measured matters: set 1 goes to the analyzer focus with SN (it fixes SN_f); the
  rotated sets keep that SN and refocus the optic (sn_kept, the default). If the user measured a set the other way,
  say so in rsc_measure_set(sn_kept=...): a set read with SN kept but fitted as "at the analyzer focus" gives a wrong
  SRz axis. Always ask for the optic position. Each measured set updates the expected positions of the others
  (expected_from): give the user the new ones. If they want other angles (e.g. no positive SRz), rsc_add_set
  (it returns the expected position; a planned set left unmeasured is not fitted) instead of predicting by hand.
- Gold frame (GoldFrameCalibration, SPEM total-intensity SZ lines over the 2 x 2 mm gold frame): gfc_start(optic,
  gold_height, frame position), give the protocol step by step (gfc_guide), gfc_plan (33 SZ lines, CSV), then
  gfc_add_files(paths of the .nxs files), gfc_fit, show gfc_plot and the quality checks, gfc_save after the user
  agrees. gfc_simulate_example makes test files for a dry run.

RULES
- Never invent measured values (motor positions, optic positions, SN gold): ask the user.
- Positions are absolute motor values: ST, SN, SZ in mm, SRn, SRz in degrees, PIX, PIY in µm. Plate coordinates are
  mm in the front view (tab up, origin at the centre of the back plate, x right, y up).
- Writing a configuration (rsc_save, gfc_save) changes what QuickAlignment uses for everyone: only on the user's
  explicit request.
- Photo reading is approximate: say so when it matters, and prefer the user's beamline feedback (found_here).
```

Prompts: `start`, `find_samples`, `calibrate`

## 2. MCP tools (60)

`*` = required. **acts**: changes the session, a file or a window; the others only read.

| Tool | | Arguments | What it does |
|---|---|---|---|
| `workflow` | reads | - | How to lead the user through alignment or calibration (read when unsure). |
| `status` | reads | - | What each tool (alignment, real-sample calibration, gold frame) is doing now. |
| `align_plates` | reads | - | The sample plates known (standard, gating, custom) and their sample area. |
| `align_configurations` | reads | `optic` (string) | The calibration configurations in configs/ (newest first). |
| `align_start` | **acts** | `plate*` (string), `optic*` (string), `custom_plate_mm` (object), `configuration` (string) | Start finding samples on a plate: plate type, optic and (default newest) configuration. Clears the samples. |
| `align_status` | reads | - | Plate, configuration, samples, photos and stage position of the session. |
| `align_photo_corners` | reads | - | The four sample-area corners to read on a plate photo, in their order, with their plate coordinates. |
| `align_photo_info` | reads | `path*` (string) | Size in pixels of a photo file (after its EXIF rotation). |
| `align_photo_grid` | reads | `path` (string), `photo_id` (string), `region` (array), `step` (number), `marks` (array) | A photo (or a zoomed region of it) with a pixel grid labelled in photo pixels, to read positions precisely; optional marks to check points. Use a path, or photo_id of a registered photo. |
| `align_register_photo` | **acts** | `corners_px*` (array), `path` (string), `image_size` (array), `photo_id` (string) | Map a plate photo onto the plate from the 4 sample-area corners (photo px, order of align_photo_corners). |
| `align_photo_points_3d` | reads | - | OPTIONAL 3D correction: the plate points at several heights that can be read on an oblique photo. |
| `align_register_photo_3d` | **acts** | `points*` (array), `path` (string), `image_size` (array), `photo_id` (string) | OPTIONAL (off by default): register an oblique photo with a camera model from >= 6 points at 2+ heights (sample-area corners + back plate / tab corners). Use only when the photo is clearly not from straight above or the user asks for it. |
| `align_manual_annotation` | **acts** | `photo_id` (string) | Open the photo window on the user's screen (photo already registered) so the user marks the samples by hand. Use when the user is not satisfied with the samples found. |
| `align_load_annotation` | **acts** | `path` (string), `wait` (boolean) | Read the samples the user marked in the manual-annotation window (after they pressed OK). |
| `align_photo_overlay` | reads | `photo_id` (string), `region` (array) | The registered plate photo with the model drawn on it (sample area, samples, devices): check it. |
| `align_plate_view` | reads | - | Drawing of the plate model with samples and devices (mm). |
| `align_photo_to_plate` | reads | `points_px*` (array), `photo_id` (string), `height` (number) | Photo pixels -> plate mm. |
| `align_plate_to_photo` | reads | `points_mm*` (array), `photo_id` (string), `height` (number) | Plate mm -> photo pixels. |
| `align_detect_samples` | reads | `photo_id` (string), `threshold` (number), `min_area_mm2` (number), `sample_colors_px` (array), `background_px` (array) | Samples found by colour on the registered plate photo (boxes in plate mm; nothing is added). |
| `align_add_sample` | **acts** | `x*` (number), `y*` (number), `length*` (number), `width*` (number), `height` (number), `name` (string) | Add a rectangular sample (plate mm). |
| `align_add_sample_from_photo` | **acts** | `points_px*` (array), `height` (number), `name` (string), `photo_id` (string) | Add a sample from its corners read on the plate photo (4 corners, or 2 opposite corners). |
| `align_update_sample` | **acts** | `name*` (string), `x` (number), `y` (number), `length` (number), `width` (number), `height` (number), `new_name` (string) | Change a sample (centre, size, height, name). |
| `align_remove_sample` | **acts** | `name*` (string) | Remove a sample. |
| `align_clear_samples` | **acts** | - | Remove all samples. |
| `align_add_device` | **acts** | `sample*` (string), `name` (string), `x` (number), `y` (number), `photo_px` (array), `photo_id` (string), `x_edge` (string), `y_edge` (string), `size_mm` (number) | Add a device on a substrate at plate (x, y) mm or at a pixel of a registered photo (plate or microscope). |
| `align_remove_device` | **acts** | `target*` (string) | Remove a device ('sample/device'). |
| `align_register_device_photo` | **acts** | `pairs*` (array), `path` (string), `photo_id` (string), `plate_photo_id` (string) | Map a microscope photo of a substrate onto the plate from 2-4+ point pairs (same feature on both). |
| `align_samples` | reads | - | The samples and devices with their warnings. |
| `align_sample_positions` | reads | - | ST / SZ / SN of every sample and device at the start rotation (SRn ref, SRz 0, piezo centred). |
| `align_set_position` | **acts** | `motors*` (object), `optic_position` (number) | The stage as it is now (motor values read by the user) and the optic position; returns what the beam hits. |
| `align_bring_to_beam` | reads | `target*` (string), `motors` (object), `correct_sn` (boolean) | ST / SZ putting a target on the beam with SN kept (correct_sn: also SN, onto the analyzer focus). |
| `align_beam_on` | reads | `motors` (object), `optic_position` (number) | What the beam hits at these positions and the optic focus position. |
| `align_found_here` | **acts** | `target*` (string), `motors*` (object), `apply` (boolean) | A target was found on the beam in the analyzer focus at these positions: move its sample there. |
| `align_rotate` | reads | `srn*` (number), `srz` (number), `motors` (object), `measured_optic` (number), `target` (string) | New ST / SZ / SN and optic position after turning SRn / SRz, keeping the point now on the beam. |
| `align_align_edge` | reads | `p1*` (array), `p2*` (array), `along` (string), `photo_id` (string), `plate_mm` (boolean), `current_srn` (number) | SRn turning an edge (two points: photo px, or plate mm with plate_mm=true) along or across the slit. |
| `align_bz_angles` | reads | `lattice_a*` (number), `hv_map*` (number), `gamma*` (array), `ref_point*` (array), `ref_label` (string), `feature` (string), `line` (integer), `hv` (number), `map_srn` (number), `map_srz` (number), `binding` (number) | SRn / SRz putting a hexagonal Brillouin-zone point at the slit centre (from a measured map's angles). |
| `align_collision_check` | reads | `motors` (object), `optic_position` (number) | Does the plate touch the analyzer / optic at these positions; collision-free motor ranges. |
| `align_save_session` | **acts** | `path*` (string) | Save the plate (samples, devices, stage) as a session file. |
| `align_load_session` | **acts** | `path*` (string), `optic` (string) | Load a QuickAlignment session file. |
| `rsc_guide` | reads | - | Real-sample calibration: where it stands and what to do next. |
| `rsc_start` | **acts** | `mode*` (string), `optic*` (string), `plate*` (string), `feature_x*` (number), `feature_y*` (number), `feature_height*` (number), `sn_kept` (boolean) | Start a real-sample calibration with one reference feature. |
| `rsc_status` | reads | - | The sets, what is measured, where the feature is expected. |
| `rsc_add_set` | **acts** | `name*` (string), `srn*` (number), `srz*` (number), `sn_kept` (boolean) | Another measurement set at other angles. |
| `rsc_measure_set` | **acts** | `name*` (string), `st*` (number), `sz*` (number), `sn*` (number), `optic` (number), `pix` (number), `piy` (number), `srn` (number), `srz` (number), `use` (boolean), `sn_kept` (boolean) | The values read for a set. |
| `rsc_fit` | **acts** | - | Fit the constants; predicts a round of test points. |
| `rsc_test_points` | reads | - | The open test points: where to go. |
| `rsc_answer_test` | **acts** | `name*` (string), `found` (boolean), `st` (number), `sz` (number), `optic` (number) | A test point: found at the prediction, or the real ST, SZ (and optic). |
| `rsc_change_test_angles` | **acts** | `name*` (string), `srn*` (number), `srz*` (number) | Other SRn / SRz for an open test point. |
| `rsc_save` | **acts** | `comment` (string) | Save the configuration in configs/ (only when the user asks). |
| `gfc_guide` | reads | - | Gold-frame calibration: where it stands and what to do next. |
| `gfc_start` | **acts** | `optic*` (string), `gold_height` (number), `frame_x` (number), `frame_y` (number), `outer` (number), `inner` (number) | Start a gold-frame calibration. |
| `gfc_status` | reads | - | Files loaded, SN points, fit state. |
| `gfc_plan` | **acts** | `csv_path` (string) | The SZ lines to measure (checked against ranges and collisions); CSV. |
| `gfc_add_files` | **acts** | `paths*` (array), `normalize` (boolean) | Load measured .nxs (or simulated .npz) files. |
| `gfc_remove_file` | **acts** | `name*` (string) | Unload a file. |
| `gfc_set_sn_points` | **acts** | `points` (array), `csv_path` (string) | Optional SN points: [{srn, srz, st, sz, sn}] or a CSV. |
| `gfc_fit` | **acts** | `sn_gold` (number), `fit_tilt` (boolean), `fit_scales` (boolean) | Fit every edge of every line; constants, change, quality checks. |
| `gfc_plot` | reads | - | The data with the fitted edges (PNG). |
| `gfc_save` | **acts** | `comment` (string), `optic_position` (number) | Save the configuration in configs/ (only when the user asks). |
| `gfc_simulate_example` | **acts** | `folder` (string) | Write a simulated measurement (known faults) to try the steps without beam time. |

## 3. Agent API (Python)

### `api.alignment` (AlignmentSession)

| Method | What it does |
|---|---|
| `add_device(sample: 'str', name: 'str \| None' = None, x: 'float \| None' = None, y: 'float \| None' = None, photo_px=None, photo_id: 'str \| None' = None, x_edge: 'str' = 'left', y_edge: 'str' = 'bottom', size_mm: 'float' = 0.2) -> 'dict'` | A device on a substrate: at plate (x, y) mm, or at a pixel of a registered photo (plate or microscope). It is stored relative to the substrate edges (x_edge left/right, y_edge bottom/top), so it moves with it. |
| `add_sample(x: 'float', y: 'float', length: 'float', width: 'float', height: 'float \| None' = None, name: 'str \| None' = None) -> 'dict'` | A rectangular sample: centre (x, y), length along x, width along y (plate mm), height H (mm). |
| `add_sample_from_photo(points_px, height: 'float \| None' = None, name: 'str \| None' = None, photo_id: 'str \| None' = None) -> 'dict'` | A sample from points read on the plate photo: its 4 corners (any order), or 2 opposite corners of its box. The sample is the plate rectangle around them; its in-plane angle is reported. |
| `align_edge(p1, p2, along: 'str' = 'slit', photo_id: 'str \| None' = None, plate_mm: 'bool' = False, current_srn: 'float \| None' = None) -> 'dict'` | SRn turning a straight edge (two points on it: photo pixels of a registered photo, or plate mm with plate_mm=true) along the analyzer slit (horizontal at ANTARES) or across it ('vertical'). |
| `beam_on(motors: 'dict \| None' = None, optic_position: 'float \| None' = None) -> 'dict'` | What the beam hits at these (or the current) positions, and the optic position focusing there. |
| `bring_to_beam(target: 'str', motors: 'dict \| None' = None, correct_sn: 'bool' = False) -> 'dict'` | ST / SZ putting a target on the beam with SN kept (how the stage is run), at the given (or current) SRn, SRz, piezo; with correct_sn also SN, so that it is on the analyzer focus. |
| `bz_angles(lattice_a: 'float', hv_map: 'float', gamma: 'list', ref_point: 'list', ref_label: 'str' = 'K', feature: 'str' = 'K', line: 'int' = 0, hv: 'float \| None' = None, map_srn: 'float \| None' = None, map_srz: 'float \| None' = None, binding: 'float' = 0.0) -> 'dict'` | SRn / SRz putting a 2-D hexagonal Brillouin-zone point (Γ, K, K', M) at the slit centre with the slit along a high-symmetry line, from a measured map (ARPES viewer angles θ = deflector, φ = along the slit). |
| `clear_samples() -> 'dict'` | - |
| `collision_check(motors: 'dict \| None' = None, optic_position: 'float \| None' = None) -> 'dict'` | Does the plate touch the analyzer / optic at these positions, and how far can each motor go. |
| `configurations(optic: 'str \| None' = None) -> 'dict'` | - |
| `current_optic() -> 'float'` | - |
| `detect_samples(photo_id: 'str \| None' = None, threshold: 'float' = 12.0, min_area_mm2: 'float' = 0.2, sample_colors_px=None, background_px=None) -> 'dict'` | Samples found by colour on the registered plate photo (nothing is added): boxes in plate mm. |
| `found_here(target: 'str', motors: 'dict', apply: 'bool' = True) -> 'dict'` | The target was found on the beam, in the analyzer focus, at these stage positions: its sample (with its devices) is moved on the plate to where that puts it; the other samples and the configuration stay. |
| `load_annotation(path: 'str \| None' = None, wait: 'bool' = False) -> 'dict'` | Read the result of the manual-annotation window into the plate (replacing the samples if the user chose so in the window, else adding them). |
| `load_session(path: 'str', optic: 'str \| None' = None) -> 'dict'` | - |
| `manual_annotation(photo_id: 'str \| None' = None) -> 'dict'` | Open the "Samples from a photo" window on the user's screen with this photo and its registration, so the user marks / corrects the samples and devices by hand (when they are not satisfied with what was found). Returns at once; call load_annotation when the user has pressed OK. |
| `photo_corners() -> 'dict'` | The four points to read on a plate photo, in this order (plate mm). |
| `photo_grid(path: 'str \| None' = None, photo_id: 'str \| None' = None, region=None, step: 'float \| None' = None, marks=None) -> 'dict'` | The photo (or a zoomed region [x0, y0, x1, y1]) with a pixel grid, to read coordinates precisely. |
| `photo_info(path: 'str') -> 'dict'` | - |
| `photo_overlay(photo_id: 'str \| None' = None, region=None) -> 'dict'` | The registered plate photo with the model drawn on it, to check the corners and the samples. |
| `photo_points_3d() -> 'dict'` | Points that can be used for the optional 3D correction of an oblique photo, with their plate (x, y) and height w above the back face (mm). |
| `photo_to_plate(points_px, photo_id: 'str \| None' = None, height: 'float \| None' = None) -> 'dict'` | Photo pixels -> plate mm, in the plane `height` mm above the plate surface (only with the 3D correction; default 0: the sample-area plane). |
| `plate_to_photo(points_mm, photo_id: 'str \| None' = None, height: 'float \| None' = None) -> 'dict'` | - |
| `plate_view() -> 'dict'` | The plate model (front view, tab up) with the samples and devices, axes in plate mm. |
| `plates() -> 'dict'` | The sample plates the program knows, with their sample area and the photo corners. |
| `register_device_photo(pairs, path: 'str \| None' = None, photo_id: 'str \| None' = None, plate_photo_id: 'str \| None' = None) -> 'dict'` | A close-up (microscope) photo of a substrate, mapped onto the plate from point pairs: the same feature (substrate corner, mark) seen on this photo (`photo` px) and on the plate (`plate_mm`, or `plate_photo_px` on the registered plate photo). 2 pairs: similarity, 3: affine, >= 4: perspective. |
| `register_photo(corners_px, path: 'str \| None' = None, image_size=None, photo_id: 'str \| None' = None) -> 'dict'` | Map a plate photo onto the plate from the four sample-area corners read on it (photo pixels, in the order of photo_corners). `path`: the image file (needed for detect_samples and the overlays); without it give `image_size` [width, height] of the image the corners were read on. |
| `register_photo_3d(points, path: 'str \| None' = None, image_size=None, photo_id: 'str \| None' = None) -> 'dict'` | OPTIONAL 3D correction for an oblique photo: a camera model from >= 6 points at several heights ([{"name" or "number" from photo_points_3d, "px": [x, y]}] or [{"plate_mm": [x, y, w], "px": [x, y]}]). Positions at any height (thick samples, devices) are then corrected for the perspective. |
| `remove_device(target: 'str') -> 'dict'` | - |
| `remove_sample(name: 'str') -> 'dict'` | - |
| `rotate(srn: 'float', srz: 'float \| None' = None, motors: 'dict \| None' = None, measured_optic: 'float \| None' = None, target: 'str \| None' = None) -> 'dict'` | New ST / SZ (/ SN) and optic position keeping the point now on the beam there after turning to (srn, srz). |
| `sample_positions() -> 'dict'` | ST / SZ / SN putting each sample / device centre on the beam at the analyzer focus at the start rotation (SRn ref, SRz 0, piezo centred). |
| `samples() -> 'dict'` | - |
| `save_session(path: 'str') -> 'dict'` | - |
| `set_position(motors: 'dict', optic_position: 'float \| None' = None) -> 'dict'` | The stage as it is now (absolute motor values read at the beamline); missing motors keep their value. |
| `start(plate: 'str' = 'standard', optic: 'str \| None' = 'capillary', custom_plate_mm: 'dict \| None' = None, configuration: 'str \| None' = None) -> 'dict'` | Begin with an empty plate: plate type, optic and configuration (default: the newest for the optic). |
| `status() -> 'dict'` | - |
| `update_sample(name: 'str', x=None, y=None, length=None, width=None, height=None, new_name=None) -> 'dict'` | - |

### `api.real_sample` (RealSampleCalibrationSession)

| Method | What it does |
|---|---|
| `add_set(name: 'str', srn: 'float', srz: 'float', sn_kept: 'bool \| None' = None) -> 'dict'` | Another set at other angles (more redundancy); `sn_kept` default: as the session (start). |
| `answer_test(name: 'str', found: 'bool' = False, st: 'float \| None' = None, sz: 'float \| None' = None, optic: 'float \| None' = None) -> 'dict'` | A test point: found at the prediction (within 0.05 mm), or the real ST, SZ (and optic) with the feature on the beam in focus, SRn / SRz / SN as given. |
| `change_test_angles(name: 'str', srn: 'float', srz: 'float') -> 'dict'` | Other angles for an open test point (e.g. out of range), predicted again. |
| `fit() -> 'dict'` | Fit the sets and the measured test points; predict a new round of test points. |
| `guide() -> 'dict'` | Where the calibration stands and the next thing to do. |
| `measure_set(name: 'str', st: 'float', sz: 'float', sn: 'float', optic: 'float \| None' = None, pix: 'float' = 150.0, piy: 'float' = 150.0, srn: 'float \| None' = None, srz: 'float \| None' = None, use: 'bool' = True, sn_kept: 'bool \| None' = None) -> 'dict'` | The values read for a set (the feature on the beam; in mode 'full' at the analyzer focus, or with SN kept and the optic refocused when the set is sn_kept). `sn_kept` overrides how this set was measured. |
| `previous()` | - |
| `save(comment: 'str' = '') -> 'dict'` | Save the fitted configuration in configs/ (only after the user agreed). |
| `sets_table() -> 'list[dict]'` | The sets with where the feature is expected (a start for the search): from the newest configuration, from set 1 once it is measured, from the fit once there is one. |
| `start(mode: 'str' = 'optics', optic: 'str \| None' = None, plate: 'str' = 'standard', feature_x: 'float' = 0.0, feature_y: 'float' = 0.0, feature_height: 'float' = 0.0, sn_kept: 'bool' = True) -> 'dict'` | Begin a calibration: mode "optics" (optic realigned: ST0, SZ0, optic reference; the mechanics are kept from the newest configuration) or "full" (optics + motors: all constants), the optic, the plate and the reference feature (plate x, y in mm and its height H above the plate surface). `sn_kept` (full mode): the rotated sets keep the SN of set 1 and refocus the optic (usual); false: every set is moved to the analyzer focus with SN. |
| `status() -> 'dict'` | - |
| `test_points() -> 'dict'` | The test points of the open round: where to go (SRn, SRz, ST, SZ, SN, optic). |

### `api.gold_frame` (GoldFrameSession)

| Method | What it does |
|---|---|
| `add_files(paths, normalize: 'bool' = False) -> 'dict'` | Measured files (.nxs; .npz from the simulator): survey lines, overview map, SRn sweep, single lines. |
| `file_list() -> 'dict'` | - |
| `fit(sn_gold: 'float \| None' = None, fit_tilt: 'bool' = True, fit_scales: 'bool' = True) -> 'dict'` | Fit every edge of every line; the constants, their change and a quality check. |
| `guide() -> 'dict'` | - |
| `guide_setup() -> 'Setup'` | - |
| `newest()` | - |
| `plan(csv_path: 'str \| None' = None) -> 'dict'` | The SZ lines to measure, placed with the newest configuration, each checked (motor range, collision). |
| `plot() -> 'dict'` | The loaded data with the fitted edges (after fit) as a PNG. |
| `remove_file(name: 'str') -> 'dict'` | - |
| `save(comment: 'str' = '', optic_position: 'float \| None' = None) -> 'dict'` | Save the fit as a new configuration in configs/ (only after the user agreed). |
| `set_sn_points(points=None, csv_path: 'str \| None' = None) -> 'dict'` | Optional SN points: [{srn, srz, st, sz, sn}] (sn: SN at the intensity peak), or a CSV with those columns. |
| `simulate_example(folder: 'str \| None' = None) -> 'dict'` | A simulated measurement of the planned lines over a frame with known faults, written as files (to try the steps). Returns the files and the true values. |
| `start(optic: 'str \| None' = 'capillary', gold_height: 'float' = 0.05, frame_x: 'float' = 0.0, frame_y: 'float' = 0.0, outer: 'float' = 2.0, inner: 'float' = 1.0) -> 'dict'` | Begin: optic, gold height above the riser top (mm, measured with SN scans), where the frame centre is taken to be on the plate (mm), its outer size and hole (mm). |
| `status() -> 'dict'` | - |
