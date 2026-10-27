#!/usr/bin/env python3
"""ANTARES QuickAlignment - gold-frame calibration from SPEM intensity maps.

Double-click to start the interactive simulator. From a console:

    python GoldFrameCalibration.py simulate --frame-u 0.2 --srz-offset-n 3.0
    python GoldFrameCalibration.py fit --step1 map1.nxs --step2 map2.nxs --step3 map3.nxs --save

See docs/GOLD_FRAME_REPORT_en.md (and the PDF in docs/pdf/) for the method.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quickalignment.gold_frame_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
