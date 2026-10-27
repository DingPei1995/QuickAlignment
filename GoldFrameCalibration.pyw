# Windows: double-click to open the gold-frame calibration window without a console window.
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "GoldFrameCalibration.py"), run_name="__main__")
