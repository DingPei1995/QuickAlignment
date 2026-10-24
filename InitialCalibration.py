#!/usr/bin/env python3
"""ANTARES QuickAlignment - initial calibration (first start, after re-homing motors).

Double-click to start. Generates a calibration configuration in configs/ from a
few measurement sets of one reference feature; see the protocol in the window.
On Windows you can also double-click InitialCalibration.pyw (no console window).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from QuickAlignment import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch("quickalignment.ui.initial_calibration_window"))
