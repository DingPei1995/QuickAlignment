# Notes for Claude

## Numbers: always the standard format, never the system locale

The program runs on Windows machines set to other languages (e.g. French, where
the decimal separator is ","). Numbers must always be shown and read in the
standard format (`1234.5`, no group separator), unless a task explicitly asks
for the system format.

Whenever code shows, reads, parses or writes numbers, check whether it follows
the standard format or the system settings, and default to the standard one:

- Qt: `quickalignment/ui/_qt.py` sets `QLocale.c()` as the default locale on
  import (`use_standard_numbers()`). New windows/entry points must import Qt via
  `._qt`, and never call `setLocale(QLocale.system())` or a language locale on
  spin boxes, validators or `QLocale().toString()`.
- Python: use `float()`, `int()`, f-strings / `format()`; never `locale.atof`,
  `locale.format_string`, `locale.setlocale` or the `"n"` format spec.
- matplotlib: keep `axes.formatter.use_locale` False (the default).
- Files (sessions, configs, CSV): write and read with "." only.
