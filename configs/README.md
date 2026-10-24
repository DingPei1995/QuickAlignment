# Configurations

- `calibration_YYYY-MM-DD_HHMMSS_<optic>.json` (`<optic>`: `capillary` or `zone_plate`): one file per calibration made by beamline staff, written by
  InitialCalibration.py or by the Calibration window (*Accept and save as new configuration* after a
  reference-sample check, *Save edited constants* in expert mode). Older files are kept as history and can
  be selected again in the Calibration window.
- `user_config.json`: the single user configuration, overwritten when the user answers *Save* on closing
  QuickAlignment; its first entry (`created`) is the save time.

At start-up QuickAlignment loads the newest of all these files, by their time stamp.
