"""Writing JSON files safely: a failed or interrupted write never leaves a half-written file."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_json(path: str | Path, data) -> None:
    """Write `data` as JSON to a temporary file next to `path`, then replace `path` with it."""
    path = Path(path)
    text = json.dumps(data, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent if str(path.parent) else ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = ["read_json", "write_json"]
