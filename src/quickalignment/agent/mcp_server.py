"""MCP server (stdio) of QuickAlignment, RealSampleCalibration and GoldFrameCalibration.

    python Agent/quickalignment_mcp.py [--configs FOLDER]
    python -m quickalignment.agent.mcp_server [--configs FOLDER]     (with src/ on the Python path)

The Model Context Protocol over stdio is newline-delimited JSON-RPC 2.0. This module implements the part a
tool server needs (initialize, ping, tools/list, tools/call, prompts/list, prompts/get) with the standard
library only, so it runs on the beamline PC without the MCP SDK and does not break when the SDK changes.

It follows the MCP server of ARPES viewer (arpes_viewer/agent/protocol.py), the reference for Ding's programs:
the same protocol versions, `readOnlyHint` on every tool, a tool error (isError, with the text of the error)
for anything that goes wrong inside a tool and a protocol error only for a bad request, the same error
texts, JSON results written with indent=1, `python -m quickalignment.agent`, and a generated reference for
agents: src/quickalignment/agent/API.md (python -m quickalignment.agent.catalog --write; a test fails when it
is out of date). In addition to ARPES viewer: prompts (workflow.py).

Tools are grouped by prefix: `align_*` (find samples), `rsc_*` (real-sample calibration), `gfc_*` (gold-frame
calibration). The server keeps one session of each in memory while the client is connected.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import traceback

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # as ARPES viewer (agent/protocol.py)
SERVER_NAME = "quickalignment"
SERVER_VERSION = "2.0.0"

# -- JSON schema pieces -------------------------------------------------------------------------------------
NUM = {"type": "number"}
INT = {"type": "integer"}
STR = {"type": "string"}
BOOL = {"type": "boolean"}
PT = {"type": "array", "items": NUM, "minItems": 2, "maxItems": 2}
PTS = {"type": "array", "items": PT}
MOTORS = {"type": "object", "properties": {k: {"type": "number", "description": d} for k, d in (
              ("st", "ST (mm)"), ("sn", "SN (mm)"), ("sz", "SZ (mm)"), ("srn", "SRn (deg)"), ("srz", "SRz (deg)"),
              ("pix", "PIX (µm)"), ("piy", "PIY (µm)"))}, "additionalProperties": False}
MOTORS_ARG = dict(MOTORS, description="absolute motor positions, e.g. {\"st\": -1.2, \"sz\": 40.1, \"sn\": 0.5}; "
                                       "missing motors keep the current value")
REGION = {"type": "array", "items": NUM, "minItems": 4, "maxItems": 4,
          "description": "[x0, y0, x1, y1] photo pixels to zoom on"}
OPTIC = {"type": "string", "description": "focusing optic: 'capillary' or 'zone plate'"}


def d(description, **props):
    return dict(props, description=description)


def tool(name, target, method, description, properties=None, required=()):
    return {"name": name, "target": target, "method": method, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {}, "required": list(required)}}


TOOLS = [
    # -- general ----------------------------------------------------------------------------------------
    tool("workflow", "api", "workflow", "How to lead the user through alignment or calibration (read when unsure)."),
    tool("status", "api", "status", "What each tool (alignment, real-sample calibration, gold frame) is doing now."),
    # -- alignment ----------------------------------------------------------------------------------------
    tool("align_plates", "alignment", "plates", "The sample plates known (standard, gating, custom) and their sample area."),
    tool("align_configurations", "alignment", "configurations", "The calibration configurations in configs/ (newest first).",
         {"optic": OPTIC}),
    tool("align_start", "alignment", "start",
         "Start finding samples on a plate: plate type, optic and (default newest) configuration. Clears the samples.",
         {"plate": d("'standard', 'gating' or 'custom'", **STR), "optic": OPTIC,
          "custom_plate_mm": d("custom plate: {length, width, height, center_y} in mm", type="object"),
          "configuration": d("configuration label or file name (default: newest for the optic)", **STR)},
         ["plate", "optic"]),
    tool("align_status", "alignment", "status", "Plate, configuration, samples, photos and stage position of the session."),
    tool("align_photo_corners", "alignment", "photo_corners",
         "The four sample-area corners to read on a plate photo, in their order, with their plate coordinates."),
    tool("align_photo_info", "alignment", "photo_info", "Size in pixels of a photo file (after its EXIF rotation).",
         {"path": STR}, ["path"]),
    tool("align_photo_grid", "alignment", "photo_grid",
         "A photo (or a zoomed region of it) with a pixel grid labelled in photo pixels, to read positions precisely; "
         "optional marks to check points. Use a path, or photo_id of a registered photo.",
         {"path": STR, "photo_id": STR, "region": REGION, "step": d("grid step in px (default: automatic)", **NUM),
          "marks": d("points to draw: [{x, y, label, color}]", type="array", items={"type": "object"})}),
    tool("align_register_photo", "alignment", "register_photo",
         "Map a plate photo onto the plate from the 4 sample-area corners (photo px, order of align_photo_corners).",
         {"corners_px": d("4 points [x, y]: 1 top left (tab side), 2 top right, 3 bottom right, 4 bottom left", **PTS),
          "path": d("image file (needed for detection and overlays)", **STR),
          "image_size": d("[width, height] when there is no file", **PT), "photo_id": STR}, ["corners_px"]),
    tool("align_photo_points_3d", "alignment", "photo_points_3d",
         "OPTIONAL 3D correction: the plate points at several heights that can be read on an oblique photo."),
    tool("align_register_photo_3d", "alignment", "register_photo_3d",
         "OPTIONAL (off by default): register an oblique photo with a camera model from >= 6 points at 2+ heights "
         "(sample-area corners + back plate / tab corners). Use only when the photo is clearly not from straight above "
         "or the user asks for it.",
         {"points": d("[{name or number (align_photo_points_3d), px: [x, y]}] or [{plate_mm: [x, y, w], px: [x, y]}]",
                      type="array", items={"type": "object"}),
          "path": STR, "image_size": d("[width, height] when there is no file", **PT), "photo_id": STR}, ["points"]),
    tool("align_manual_annotation", "alignment", "manual_annotation",
         "Open the photo window on the user's screen (photo already registered) so the user marks the samples by hand. "
         "Use when the user is not satisfied with the samples found.", {"photo_id": STR}),
    tool("align_load_annotation", "alignment", "load_annotation",
         "Read the samples the user marked in the manual-annotation window (after they pressed OK).",
         {"path": STR, "wait": d("wait for the window to close", **BOOL)}),
    tool("align_photo_overlay", "alignment", "photo_overlay",
         "The registered plate photo with the model drawn on it (sample area, samples, devices): check it.",
         {"photo_id": STR, "region": REGION}),
    tool("align_plate_view", "alignment", "plate_view", "Drawing of the plate model with samples and devices (mm)."),
    tool("align_photo_to_plate", "alignment", "photo_to_plate", "Photo pixels -> plate mm.",
         {"points_px": d("[[x, y], ...] photo pixels", **PTS), "photo_id": STR,
          "height": d("surface height above the plate surface, mm (3D correction only; default 0)", **NUM)},
         ["points_px"]),
    tool("align_plate_to_photo", "alignment", "plate_to_photo", "Plate mm -> photo pixels.",
         {"points_mm": PTS, "photo_id": STR, "height": NUM}, ["points_mm"]),
    tool("align_detect_samples", "alignment", "detect_samples",
         "Samples found by colour on the registered plate photo (boxes in plate mm; nothing is added).",
         {"photo_id": STR, "threshold": d("colour difference ΔE (default 12)", **NUM),
          "min_area_mm2": d("smaller regions are dropped (default 0.2)", **NUM),
          "sample_colors_px": d("pixels on samples: keep only regions of these colours", **PTS),
          "background_px": d("a pixel of bare plate (default: estimated)", **PT)}),
    tool("align_add_sample", "alignment", "add_sample", "Add a rectangular sample (plate mm).",
         {"x": NUM, "y": NUM, "length": d("along x (mm)", **NUM), "width": d("along y (mm)", **NUM),
          "height": d("H above the plate surface (mm), default 0.525", **NUM), "name": STR},
         ["x", "y", "length", "width"]),
    tool("align_add_sample_from_photo", "alignment", "add_sample_from_photo",
         "Add a sample from its corners read on the plate photo (4 corners, or 2 opposite corners).",
         {"points_px": d("[[x, y], ...] photo pixels", **PTS), "height": d("H above the plate surface (mm), default 0.525", **NUM), "name": STR,
          "photo_id": STR}, ["points_px"]),
    tool("align_update_sample", "alignment", "update_sample", "Change a sample (centre, size, height, name).",
         {"name": STR, "x": NUM, "y": NUM, "length": NUM, "width": NUM, "height": NUM, "new_name": STR}, ["name"]),
    tool("align_remove_sample", "alignment", "remove_sample", "Remove a sample.", {"name": STR}, ["name"]),
    tool("align_clear_samples", "alignment", "clear_samples", "Remove all samples."),
    tool("align_add_device", "alignment", "add_device",
         "Add a device on a substrate at plate (x, y) mm or at a pixel of a registered photo (plate or microscope).",
         {"sample": STR, "name": STR, "x": NUM, "y": NUM, "photo_px": PT, "photo_id": STR,
          "x_edge": d("'left' or 'right': edge the device is measured from", **STR),
          "y_edge": d("'bottom' or 'top'", **STR), "size_mm": NUM}, ["sample"]),
    tool("align_remove_device", "alignment", "remove_device", "Remove a device ('sample/device').",
         {"target": STR}, ["target"]),
    tool("align_register_device_photo", "alignment", "register_device_photo",
         "Map a microscope photo of a substrate onto the plate from 2-4+ point pairs (same feature on both).",
         {"pairs": d("[{photo: [x, y], plate_photo_px: [x, y]} or {photo: [x, y], plate_mm: [x, y]}]", type="array",
                     items={"type": "object"}),
          "path": STR, "photo_id": STR, "plate_photo_id": STR}, ["pairs"]),
    tool("align_samples", "alignment", "samples", "The samples and devices with their warnings."),
    tool("align_sample_positions", "alignment", "sample_positions",
         "ST / SZ / SN of every sample and device at the start rotation (SRn ref, SRz 0, piezo centred)."),
    tool("align_set_position", "alignment", "set_position",
         "The stage as it is now (motor values read by the user) and the optic position; returns what the beam hits.",
         {"motors": MOTORS_ARG, "optic_position": NUM}, ["motors"]),
    tool("align_bring_to_beam", "alignment", "bring_to_beam",
         "ST / SZ putting a target on the beam with SN kept (correct_sn: also SN, onto the analyzer focus).",
         {"target": d("'sample', 'sample/device' or 'plate centre'", **STR), "motors": MOTORS_ARG, "correct_sn": BOOL},
         ["target"]),
    tool("align_beam_on", "alignment", "beam_on", "What the beam hits at these positions and the optic focus position.",
         {"motors": MOTORS_ARG, "optic_position": NUM}),
    tool("align_found_here", "alignment", "found_here",
         "A target was found on the beam in the analyzer focus at these positions: move its sample there.",
         {"target": STR, "motors": MOTORS_ARG, "apply": d("false: only report the shift", **BOOL)}, ["target", "motors"]),
    tool("align_rotate", "alignment", "rotate",
         "New ST / SZ / SN and optic position after turning SRn / SRz, keeping the point now on the beam.",
         {"srn": NUM, "srz": NUM, "motors": d("position with the point on the beam (default: current)", **MOTORS),
          "measured_optic": d("optic position in focus there (default: current)", **NUM),
          "target": d("use this target at the analyzer focus instead of a measured position", **STR)}, ["srn"]),
    tool("align_align_edge", "alignment", "align_edge",
         "SRn turning an edge (two points: photo px, or plate mm with plate_mm=true) along or across the slit.",
         {"p1": PT, "p2": PT, "along": d("'slit' (horizontal) or 'vertical'", **STR), "photo_id": STR,
          "plate_mm": BOOL, "current_srn": NUM}, ["p1", "p2"]),
    tool("align_bz_angles", "alignment", "bz_angles",
         "SRn / SRz putting a hexagonal Brillouin-zone point at the slit centre (from a measured map's angles).",
         {"lattice_a": d("in-plane lattice constant (Å)", **NUM), "hv_map": d("photon energy of the map (eV)", **NUM),
          "gamma": d("[θ, φ] of Γ on the map (deg)", **PT), "ref_point": d("[θ, φ] of a K or M point", **PT),
          "ref_label": d("'K' or 'M'", **STR), "feature": d("wanted point: Γ, K, K only, K′ only, M", **STR),
          "line": d("0: radial line (Γ–K / Γ–M), 1: zone edge (K–M / M–K)", **INT),
          "hv": d("photon energy of the new measurement (eV)", **NUM), "map_srn": NUM, "map_srz": NUM,
          "binding": d("E − E_F of the point (eV, ≤ 0)", **NUM)},
         ["lattice_a", "hv_map", "gamma", "ref_point"]),
    tool("align_collision_check", "alignment", "collision_check",
         "Does the plate touch the analyzer / optic at these positions; collision-free motor ranges.",
         {"motors": MOTORS_ARG, "optic_position": NUM}),
    tool("align_save_session", "alignment", "save_session", "Save the plate (samples, devices, stage) as a session file.",
         {"path": STR}, ["path"]),
    tool("align_load_session", "alignment", "load_session", "Load a QuickAlignment session file.",
         {"path": STR, "optic": OPTIC}, ["path"]),
    # -- real-sample calibration ------------------------------------------------------------------------------
    tool("rsc_guide", "real_sample", "guide", "Real-sample calibration: where it stands and what to do next."),
    tool("rsc_start", "real_sample", "start",
         "Start a real-sample calibration with one reference feature.",
         {"mode": d("'optics' (optic realigned, usual) or 'full' (optics + motors)", **STR), "optic": OPTIC,
          "plate": d("'standard' or 'gating'", **STR), "feature_x": d("plate x (mm)", **NUM),
          "feature_y": d("plate y (mm)", **NUM), "feature_height": d("H above the plate surface (mm)", **NUM),
          "sn_kept": d("full mode: rotated sets keep the SN of set 1 and refocus the optic (default true); "
                       "false: every set moved to the analyzer focus with SN", **BOOL)},
         ["mode", "optic", "plate", "feature_x", "feature_y", "feature_height"]),
    tool("rsc_status", "real_sample", "status", "The sets, what is measured, where the feature is expected."),
    tool("rsc_add_set", "real_sample", "add_set", "Another measurement set at other angles.",
         {"name": STR, "srn": NUM, "srz": NUM, "sn_kept": d("SN kept as in set 1 (default: as the session)", **BOOL)},
         ["name", "srn", "srz"]),
    tool("rsc_measure_set", "real_sample", "measure_set", "The values read for a set.",
         {"name": d("set name or number ('1')", **STR), "st": NUM, "sz": NUM, "sn": NUM,
          "optic": d("optic position at best focus", **NUM), "pix": NUM, "piy": NUM, "srn": NUM, "srz": NUM,
          "use": BOOL, "sn_kept": d("how this set was measured: true = SN kept, optic refocused; false = SN moved "
                                    "to the analyzer focus (default: as planned for the set)", **BOOL)},
         ["name", "st", "sz", "sn"]),
    tool("rsc_fit", "real_sample", "fit", "Fit the constants; predicts a round of test points."),
    tool("rsc_test_points", "real_sample", "test_points", "The open test points: where to go."),
    tool("rsc_answer_test", "real_sample", "answer_test",
         "A test point: found at the prediction, or the real ST, SZ (and optic).",
         {"name": STR, "found": BOOL, "st": NUM, "sz": NUM, "optic": NUM}, ["name"]),
    tool("rsc_change_test_angles", "real_sample", "change_test_angles", "Other SRn / SRz for an open test point.",
         {"name": STR, "srn": NUM, "srz": NUM}, ["name", "srn", "srz"]),
    tool("rsc_save", "real_sample", "save", "Save the configuration in configs/ (only when the user asks).",
         {"comment": STR}),
    # -- gold-frame calibration ---------------------------------------------------------------------------------
    tool("gfc_guide", "gold_frame", "guide", "Gold-frame calibration: where it stands and what to do next."),
    tool("gfc_start", "gold_frame", "start", "Start a gold-frame calibration.",
         {"optic": OPTIC, "gold_height": d("gold top above the riser top (mm, default 0.05)", **NUM),
          "frame_x": d("frame centre on the plate (mm, default 0)", **NUM), "frame_y": NUM,
          "outer": d("outer size (mm, default 2)", **NUM), "inner": d("hole size (mm, default 1)", **NUM)}, ["optic"]),
    tool("gfc_status", "gold_frame", "status", "Files loaded, SN points, fit state."),
    tool("gfc_plan", "gold_frame", "plan", "The SZ lines to measure (checked against ranges and collisions); CSV.",
         {"csv_path": STR}),
    tool("gfc_add_files", "gold_frame", "add_files", "Load measured .nxs (or simulated .npz) files.",
         {"paths": {"type": "array", "items": STR}, "normalize": d("divide by the diode", **BOOL)}, ["paths"]),
    tool("gfc_remove_file", "gold_frame", "remove_file", "Unload a file.", {"name": STR}, ["name"]),
    tool("gfc_set_sn_points", "gold_frame", "set_sn_points", "Optional SN points: [{srn, srz, st, sz, sn}] or a CSV.",
         {"points": {"type": "array", "items": {"type": "object"}}, "csv_path": STR}),
    tool("gfc_fit", "gold_frame", "fit", "Fit every edge of every line; constants, change, quality checks.",
         {"sn_gold": d("SN with the gold top at the analyzer focus (default: from a flat file)", **NUM),
          "fit_tilt": BOOL, "fit_scales": BOOL}),
    tool("gfc_plot", "gold_frame", "plot", "The data with the fitted edges (PNG)."),
    tool("gfc_save", "gold_frame", "save", "Save the configuration in configs/ (only when the user asks).",
         {"comment": STR, "optic_position": d("optic position focused on the gold (default: from the files)", **NUM)}),
    tool("gfc_simulate_example", "gold_frame", "simulate_example",
         "Write a simulated measurement (known faults) to try the steps without beam time.", {"folder": STR}),
]
TOOL_INDEX = {t["name"]: t for t in TOOLS}

#: tools that change something (the session, a file, a window on screen); every other tool only reads
#: (MCP readOnlyHint, as ARPES viewer)
ACTING = {
    "align_start", "align_register_photo", "align_register_photo_3d", "align_manual_annotation",
    "align_load_annotation", "align_add_sample", "align_add_sample_from_photo", "align_update_sample",
    "align_remove_sample", "align_clear_samples", "align_add_device", "align_remove_device",
    "align_register_device_photo", "align_set_position", "align_found_here", "align_save_session",
    "align_load_session",
    "rsc_start", "rsc_add_set", "rsc_measure_set", "rsc_fit", "rsc_answer_test", "rsc_change_test_angles", "rsc_save",
    "gfc_start", "gfc_plan", "gfc_add_files", "gfc_remove_file", "gfc_set_sn_points", "gfc_fit", "gfc_save",
    "gfc_simulate_example",
}


def tool_spec(t: dict) -> dict:
    """What tools/list sends for one tool (the same keys as ARPES viewer's Tool.spec())."""
    return {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"],
            "annotations": {"readOnlyHint": t["name"] not in ACTING}}


# -- the server --------------------------------------------------------------------------------------------
class Server:
    def __init__(self, configs=None):
        from .api import AgentAPI
        from .workflow import INSTRUCTIONS

        self.api = AgentAPI(configs)
        self.instructions = INSTRUCTIONS
        self.initialized = False

    def handle(self, msg: dict) -> dict | None:
        """One JSON-RPC message -> its response (None for notifications)."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method is None:  # a response from the client: nothing to do
            return None
        is_notification = "id" not in msg
        try:
            result = self.dispatch(method, params)
        except _RpcError as exc:
            return None if is_notification else _error(mid, exc.code, str(exc))
        except Exception as exc:  # never kill the server
            traceback.print_exc(file=sys.stderr)
            return None if is_notification else _error(mid, -32603, f"Internal error: {exc}")
        return None if is_notification else {"jsonrpc": "2.0", "id": mid, "result": result}

    def dispatch(self, method: str, params: dict):
        if method == "initialize":
            asked = params.get("protocolVersion")
            version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return {"protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "title": "ANTARES QuickAlignment", "version": SERVER_VERSION},
                    "instructions": self.instructions}
        if method in ("notifications/initialized", "initialized"):
            self.initialized = True
            return None
        if method.startswith("notifications/"):
            return None
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [tool_spec(t) for t in TOOLS]}
        if method == "tools/call":
            return self.call_tool(params.get("name"), params.get("arguments") or {})
        if method == "prompts/list":
            from .workflow import PROMPTS
            return {"prompts": [{"name": k, "description": p["description"], "arguments": p["arguments"]}
                                for k, p in PROMPTS.items()]}
        if method == "prompts/get":
            from .workflow import PROMPTS, render_prompt
            name = params.get("name")
            if name not in PROMPTS:
                raise _RpcError(-32602, f"Unknown prompt {name!r}")
            return {"description": PROMPTS[name]["description"],
                    "messages": [{"role": "user", "content": {"type": "text",
                                                              "text": render_prompt(name, params.get("arguments"))}}]}
        if method == "resources/list":
            return {"resources": []}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "logging/setLevel":
            return {}
        raise _RpcError(-32601, f"method not found: {method}")

    def call_tool(self, name: str, arguments: dict) -> dict:
        spec = TOOL_INDEX.get(name)
        if spec is None:
            raise _RpcError(-32602, f"no tool called {name!r}")
        if not isinstance(arguments, dict):
            raise _RpcError(-32602, "arguments must be an object")
        from .common import APIError

        target = self.api if spec["target"] == "api" else getattr(self.api, spec["target"])
        allowed = spec["inputSchema"]["properties"]
        unknown = [k for k in arguments if k not in allowed]
        missing = [k for k in spec["inputSchema"]["required"] if arguments.get(k) is None]
        if unknown or missing:  # as ARPES viewer: say what the tool takes
            text = (f"Unknown argument(s) {unknown}. " if unknown else "") + \
                   (f"Missing argument(s) {missing}. " if missing else "") + \
                   f"{name} takes: {', '.join(allowed) or 'nothing'}"
            return {"content": [{"type": "text", "text": text}], "isError": True}
        try:
            result = getattr(target, spec["method"])(**{k: v for k, v in arguments.items() if v is not None})
        except APIError as exc:  # a message for the user, as it is
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception as exc:  # noqa: BLE001 -- as ARPES viewer: every error inside a tool is a tool error
            traceback.print_exc(file=sys.stderr)
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            return {"content": [{"type": "text", "text": detail}], "isError": True}
        return tool_result(result)


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def tool_result(result) -> dict:
    """A tool's dict -> MCP content: images as image blocks, the rest as JSON text."""
    content = []
    if isinstance(result, dict) and isinstance(result.get("image_png"), (bytes, bytearray)):
        result = dict(result)
        png = result.pop("image_png")
        content.append({"type": "image", "data": base64.b64encode(png).decode("ascii"), "mimeType": "image/png"})
    text = json.dumps(result, ensure_ascii=False, indent=1, default=str)
    content.insert(0, {"type": "text", "text": text})
    return {"content": content, "isError": False}


def serve(configs=None, stdin=None, stdout=None) -> int:
    """Read JSON-RPC lines from stdin, answer on stdout. Anything printed by the library goes to stderr."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    stdin = stdin or sys.stdin.buffer
    out = stdout or sys.stdout.buffer
    sys.stdout = sys.stderr  # stray prints must not corrupt the protocol
    server = Server(configs)

    def send(obj):
        out.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        out.flush()

    for raw in stdin:
        line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            send(_error(None, -32700, f"parse error: {exc}"))
            continue
        if isinstance(msg, list):  # a batch (protocol 2025-03-26)
            replies = [r for r in (server.handle(m) for m in msg) if r is not None]
            if replies:
                send(replies)
            continue
        reply = server.handle(msg)
        if reply is not None:
            send(reply)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="quickalignment-mcp", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--configs", default=None, help="configuration folder (default: configs/ of the repository)")
    p.add_argument("--list-tools", action="store_true", help="print the tools and exit")
    args = p.parse_args(argv)
    if args.list_tools:
        for t in TOOLS:
            print(f"{t['name']:30s} {'ACT' if t['name'] in ACTING else '   '} {t['description']}")
        return 0
    return serve(args.configs)


if __name__ == "__main__":
    sys.exit(main())
