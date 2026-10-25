"""Bad files and bad input must give a message, never a crash or a half-written file."""

import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from quickalignment import fileio  # noqa: E402
from quickalignment.calibration import CalibrationStore  # noqa: E402
from quickalignment.geometry import Sample, SampleLayout  # noqa: E402
from quickalignment.session import Session  # noqa: E402


def test_write_json_keeps_old_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "session.json"
    fileio.write_json(path, {"a": 1})

    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr(fileio.os, "replace", boom)
    with pytest.raises(OSError):
        fileio.write_json(path, {"a": 2})
    assert json.loads(path.read_text()) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["session.json"]  # no temporary file left


@pytest.mark.parametrize("data", [
    [],
    {"layout": {"samples": [{"name": "A", "u": "left"}]}},
    {"layout": {"samples": [{"name": "A", "height": float("nan")}]}},
    {"layout": {"samples": [{"u": 1.0}]}},
    {"layout": {"samples": [{"name": "A", "devices": [{"name": "D", "x_edge": "middle"}]}]}},
    {"layout": {"samples": []}, "motors": {"st": "abc"}},
    {"layout": {"samples": []}, "motors": [1, 2]},
    {"layout": {"plate_type": "custom", "custom_plate": {"length": 50, "width": 4, "height": 8}}},
])
def test_bad_session_raises_value_error(data):
    with pytest.raises(ValueError):
        Session.from_dict(data)


def test_session_roundtrip_and_unknown_keys(tmp_path):
    layout = SampleLayout(samples=[Sample("A", u=1.0, v=-2.0, height=0.3)])
    path = tmp_path / "s.json"
    Session(layout).save(path)
    data = json.loads(path.read_text())
    data["layout"]["samples"][0]["colour"] = "red"  # from a newer version: ignored
    data["motors"]["st"] = "1.5"  # numbers written as text are accepted
    s = Session.from_dict(data)
    assert s.layout.samples[0].u == 1.0 and s.motors.st == 1.5


def test_damaged_configuration_is_skipped(tmp_path):
    folder = tmp_path / "configs"
    store = CalibrationStore(folder)
    good = store.latest()
    store.save(good)
    (folder / "calibration_2099-01-01_000000_capillary.json").write_text("{not json")
    (folder / "calibration_2099-01-02_000000_capillary.json").write_text("[1, 2]")
    (folder / "calibration_2099-01-03_000000_capillary.json").write_text(
        json.dumps({"created": "2099-01-03 00:00:00", "stage_config": {"st0": "x"}}))
    records = store.records()
    assert len(records) == 1 and records[0].created == store.records()[0].created


def test_configuration_numbers_are_converted(tmp_path):
    folder = tmp_path / "configs"
    folder.mkdir()
    (folder / "calibration_2099-01-01_000000_capillary.json").write_text(json.dumps({
        "created": "2099-01-01 00:00:00", "stage_config": {"st0": "0.5"},
        "optics": {"optic_type": "capillary", "optic_sign": -1.0, "motors": {"srn": "121"}}}))
    r = CalibrationStore(folder).records()[0]
    assert r.config.st0 == 0.5 and r.optics.optic_sign == -1 and isinstance(r.optics.optic_sign, int)
    assert r.optics.motors.srn == 121.0 and r.optic_name == "capillary"


def test_excepthook_reports_and_keeps_running(monkeypatch):
    from quickalignment.ui._qt import QtWidgets, install_excepthook

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    shown = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: shown.append(self.text()), raising=False)
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec_", lambda self: shown.append(self.text()), raising=False)
    old = sys.excepthook
    try:
        install_excepthook("Test")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old
    assert shown and "boom" in shown[0]


def test_main_with_unreadable_session_starts_empty(tmp_path, monkeypatch):
    from quickalignment import app as app_module
    from quickalignment.geometry import STANDARD_PLATE
    from quickalignment.ui._qt import QtWidgets

    bad = tmp_path / "bad.json"
    bad.write_text("{")
    errors = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: errors.append(a[2]))
    monkeypatch.setattr(app_module, "ask_setup", lambda *a, **k: (STANDARD_PLATE, "capillary"))
    monkeypatch.setattr(app_module, "exec_app", lambda app: 0)
    old = sys.excepthook
    try:
        assert app_module.main(["QuickAlignment", str(bad)]) == 0
    finally:
        sys.excepthook = old
    assert errors and "could not be read" in errors[0]


def test_table_rejects_non_finite_values():
    from quickalignment.ui._qt import QtWidgets
    from quickalignment.ui.plate_editor import PlateEditor

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    editor = PlateEditor(SampleLayout(samples=[Sample("A", u=1.0)]))
    for text in ("nan", "inf", "-inf", "abc"):
        editor.table.item(0, 2).setText(text)
        assert editor.layout_model.samples[0].u == 1.0
