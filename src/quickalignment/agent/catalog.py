"""The reference an agent reads instead of the source: ``API.md`` beside this module.

As the agent reference of ARPES viewer (arpes_viewer/agent/catalog.py -> API.md): part of the package, generated,
never written by hand, from the program itself:

1. how to lead the user (workflow.INSTRUCTIONS, the MCP server instructions) and the prompts;
2. the MCP tools (name, reads / acts, arguments, description);
3. the methods of the agent API (``AgentAPI``: alignment, real_sample, gold_frame), for scripts.

``tests/test_catalog.py`` regenerates it and fails when the file differs. After every change to the tools, the
API or the workflow::

    python -m quickalignment.agent.catalog --write
"""

from __future__ import annotations

import inspect
import os
import sys

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "API.md")

HEADER = """# QuickAlignment, RealSampleCalibration, GoldFrameCalibration -- the agent's reference

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
"""


def _args(schema: dict) -> str:
    props, required = schema.get("properties", {}), set(schema.get("required", []))
    parts = []
    for name, spec in props.items():
        kind = spec.get("type", "")
        parts.append(f"`{name}{'*' if name in required else ''}`" + (f" ({kind})" if kind else ""))
    return ", ".join(parts) or "-"


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def workflow_reference() -> list[str]:
    from .workflow import INSTRUCTIONS, PROMPTS
    lines = ["## 1. Workflow (the MCP server instructions)", "", "```", INSTRUCTIONS.strip(), "```", "",
             "Prompts: " + ", ".join(f"`{k}`" for k in PROMPTS), ""]
    return lines


def tools_reference() -> list[str]:
    from .mcp_server import ACTING, TOOLS
    lines = [f"## 2. MCP tools ({len(TOOLS)})", "",
             "`*` = required. **acts**: changes the session, a file or a window; the others only read.", "",
             "| Tool | | Arguments | What it does |", "|---|---|---|---|"]
    for t in TOOLS:
        lines.append(f"| `{t['name']}` | {'**acts**' if t['name'] in ACTING else 'reads'} | "
                     f"{_cell(_args(t['inputSchema']))} | {_cell(t['description'])} |")
    return lines + [""]


def api_reference() -> list[str]:
    from .alignment import AlignmentSession
    from .gold_frame import GoldFrameSession
    from .real_sample import RealSampleCalibrationSession
    lines = ["## 3. Agent API (Python)", ""]
    for attr, cls in (("alignment", AlignmentSession), ("real_sample", RealSampleCalibrationSession),
                      ("gold_frame", GoldFrameSession)):
        lines += [f"### `api.{attr}` ({cls.__name__})", "", "| Method | What it does |", "|---|---|"]
        for name, member in inspect.getmembers(cls, inspect.isfunction):
            if name.startswith("_"):
                continue
            signature = str(inspect.signature(member)).replace("(self, ", "(").replace("(self)", "()")
            doc = (inspect.getdoc(member) or "").split("\n\n")[0] or "-"
            lines.append(f"| `{name}{_cell(signature)}` | {_cell(doc)} |")
        lines.append("")
    return lines


def build() -> str:
    return "\n".join([HEADER] + workflow_reference() + tools_reference() + api_reference()).rstrip() + "\n"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    text = build()
    if "--write" in argv:
        with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print(f"written: {os.path.normpath(PATH)}")
        return 0
    try:
        with open(PATH, encoding="utf-8") as handle:
            current = handle.read()
    except OSError:
        current = ""
    if current != text:
        print("API.md is out of date: python -m quickalignment.agent.catalog --write")
        return 1
    print("API.md is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
