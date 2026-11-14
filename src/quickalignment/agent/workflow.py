"""How an agent leads a user through alignment and calibration: the MCP server instructions and prompts.

The text is written for the agent (an LLM with vision) that calls the tools of `mcp_server.py`. It is also
the reference for anyone driving `quickalignment.agent.AgentAPI` from Python.
"""

INSTRUCTIONS = """\
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
"""

PROMPTS = {
    "start": {
        "description": "Start a QuickAlignment conversation: alignment from photos, or a calibration.",
        "arguments": [{"name": "photos", "description": "Paths of the plate photos (optional)", "required": False}],
        "text": ("I want help at the ANTARES sample stage. {photos}Ask me first whether I want to find samples or to "
                 "calibrate, which sample plate is mounted and which optic is used, then guide me step by step with "
                 "the QuickAlignment tools."),
    },
    "find_samples": {
        "description": "Find the samples of a plate photo and give their stage positions.",
        "arguments": [{"name": "photo", "description": "Path of the plate photo", "required": True},
                      {"name": "plate", "description": "standard, gating or custom", "required": False},
                      {"name": "optic", "description": "capillary or zone plate", "required": False}],
        "text": ("Find the samples on the plate photo {photo} (plate: {plate}, optic: {optic}; ask me if unknown), "
                 "locate the four corners of the sample area, check the overlay with me, ask me the sample heights "
                 "and whether I am satisfied (else let me annotate by hand), then give me the ST / SZ / SN of every sample."),
    },
    "calibrate": {
        "description": "Calibrate the stage step by step (real sample or gold frame).",
        "arguments": [{"name": "method", "description": "real sample or gold frame", "required": False}],
        "text": ("I want to calibrate the stage ({method}). Ask me what is needed and guide me one step at a time; "
                 "tell me exactly what to set and what to read at each step."),
    },
}


def render_prompt(name: str, arguments: dict | None = None) -> str:
    p = PROMPTS[name]
    args = {a["name"]: "" for a in p["arguments"]}
    args.update({k: v for k, v in (arguments or {}).items() if v})
    if name == "start":
        args["photos"] = f"My photos: {args['photos']}. " if args.get("photos") else ""
    for key in ("plate", "optic", "method"):
        if key in args and not args[key]:
            args[key] = "not given"
    return p["text"].format(**args)


__all__ = ["INSTRUCTIONS", "PROMPTS", "render_prompt"]
