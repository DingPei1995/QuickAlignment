# Configurations

- `calibration_YYYY-MM-DD_HHMMSS_<optic>.json` (`<optic>`: `capillary` or `zone_plate`): one file per calibration made by beamline staff, written by
  InitialCalibration.py or by the Calibration window (*Accept and save as new configuration* after a
  reference-sample check, *Save edited constants* in expert mode). Older files are kept as history and can
  be selected again in the Calibration window.

Only beamline staff change configurations (with the reference sample); QuickAlignment writes none on closing.

At start-up QuickAlignment loads the newest of these files made with the chosen optic, by their time stamp.
