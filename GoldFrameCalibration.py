#!/usr/bin/env python3
"""ANTARES QuickAlignment - gold-frame calibration from SPEM intensity maps.

Double-click to open the calibration window: load the three maps of the gold frame (ST x SZ,
SZ x SRn, ST x SRz), fit them and save the configuration that QuickAlignment loads.
On Windows you can also double-click GoldFrameCalibration.pyw (no console window).
The simulator is GoldFrameSimulator.py. From a console:

    python GoldFrameCalibration.py fit --step1 map1.nxs --step2 map2.nxs --step3 map3.nxs --save
    python GoldFrameCalibration.py simulate --frame-u 0.2 --srz-offset-n 3.0

See docs/GOLD_FRAME_REPORT_en.md (and the PDF in docs/pdf/) for the method.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from QuickAlignment import launch  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from quickalignment.gold_frame_cli import main

        sys.exit(main())
    sys.exit(launch("quickalignment.ui.gold_frame_window"))
