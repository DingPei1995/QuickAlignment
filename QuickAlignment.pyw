# Windows: double-click to start QuickAlignment without a console window.
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "QuickAlignment.py"), run_name="__main__")
