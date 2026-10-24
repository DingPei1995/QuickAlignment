# Windows: double-click to start the initial calibration without a console window.
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "InitialCalibration.py"), run_name="__main__")
