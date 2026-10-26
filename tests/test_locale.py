import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")

QtCore, QtWidgets = qt.QtCore, qt.QtWidgets


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_numbers_use_a_point_on_a_french_system(app):
    QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.French, QtCore.QLocale.France))
    try:
        qt.use_standard_numbers()
        box = QtWidgets.QDoubleSpinBox()
        box.setRange(-10000, 10000)
        box.setDecimals(3)
        box.setValue(1234.5)
        assert box.text() == "1234.500"
        assert box.valueFromText("-12.25") == -12.25
        assert QtCore.QLocale().toString(0.5) == "0.5"
    finally:
        qt.use_standard_numbers()
