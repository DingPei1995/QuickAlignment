"""Manual annotation of a plate photo: the "Samples from a photo" window on its own, for the agent hand-off.

When the user is not satisfied with what the agent found on a photo, the agent opens this window with the photo
and the registration it used (the four sample-area corners, or the eight 3D points), the user draws / corrects the
samples and devices by hand and presses OK; the result is written to a JSON file that the agent reads back
(`align_load_annotation`).

    python -m quickalignment.ui.annotate --photo PHOTO --layout LAYOUT.json --out RESULT.json
           [--corners "x,y;x,y;x,y;x,y"] [--points-3d "x,y;...(8)"] [--height 0.525]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from ._qt import QtWidgets, install_excepthook  # standard number format on import
from ..core.fileio import read_json, write_json
from ..core.geometry import SampleLayout


def _points(text: str | None):
    if not text:
        return None
    return [tuple(float(c) for c in p.split(",")) for p in text.split(";") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="annotate", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--photo", required=True)
    p.add_argument("--layout", required=True, help="the plate and the samples so far (session layout JSON)")
    p.add_argument("--out", required=True, help="where the result is written")
    p.add_argument("--corners", default=None, help="the 4 sample-area corners on the photo: x,y;x,y;x,y;x,y")
    p.add_argument("--points-3d", default=None, help="the 8 points of the 3D correction (turns it on)")
    p.add_argument("--height", type=float, default=0.525, help="height H given to new samples (mm)")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    from .photo_dialog import PhotoImportDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])  # noqa: F841
    install_excepthook("QuickAlignment – manual annotation")
    layout = SampleLayout.from_dict(read_json(args.layout))
    dialog = PhotoImportDialog(layout.plate, args.height, [s.name for s in layout.samples])
    dialog.setWindowTitle("Samples from a photo — manual annotation (OK sends the result back to the assistant)")
    if not dialog.load_photo(args.photo):
        return 1
    pts3d = _points(args.points_3d)
    if pts3d:
        dialog.use_3d.setChecked(True)
        dialog.set_corners(pts3d)
    elif args.corners:
        dialog.set_corners(_points(args.corners))
    # started from a background process (the assistant's server): bring the window to the front
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    ok =dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()
    result = {"accepted": bool(ok)}
    if ok:
        result["replace"] = dialog.replace_existing()
        result["samples"] = [asdict(s) for s in dialog.samples()]
    write_json(args.out, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
