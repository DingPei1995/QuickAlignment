# Configurations

- `calibration_YYYY-MM-DD_HHMMSS_<optic>.json` (`<optic>`: `capillary` or `zone_plate`): one file per calibration made by
  beamline staff with InitialCalibration.py. Older files are kept as history and can be selected again in
  the Configuration window.

QuickAlignment only reads configurations; it writes none.

At start-up QuickAlignment loads the newest of these files made with the chosen optic, by their time stamp.
