import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("quickalignment.ui._qt")
from quickalignment.geometry import Sample, SampleLayout  # noqa: E402
from quickalignment.ui.plate_editor import MainWindow  # noqa: E402

QtCore, QtGui, QtWidgets = qt.QtCore, qt.QtGui, qt.QtWidgets

Qt = QtCore.Qt


@pytest.fixture
def window():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow(SampleLayout())
    win.show()
    app.processEvents()
    yield win
    win.close()


def to_view(win, u, v):
    return win.editor.view.mapFromScene(QtCore.QPointF(u, -v))


def send(widget, kind, pos, button, buttons):
    # QGraphicsScene hit-tests with the screen position, so it must be consistent
    local = QtCore.QPointF(pos)
    screen = QtCore.QPointF(widget.mapToGlobal(pos))
    event = QtGui.QMouseEvent(kind, local, local, screen, button, buttons, Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(widget, event)


def drag(widget, p0, p1):
    send(widget, QtCore.QEvent.MouseButtonPress, p0, Qt.LeftButton, Qt.LeftButton)
    for t in (0.25, 0.5, 0.75, 1.0):
        p = QtCore.QPoint(int(p0.x() + (p1.x() - p0.x()) * t), int(p0.y() + (p1.y() - p0.y()) * t))
        send(widget, QtCore.QEvent.MouseMove, p, Qt.NoButton, Qt.LeftButton)
    send(widget, QtCore.QEvent.MouseButtonRelease, p1, Qt.LeftButton, Qt.NoButton)


def test_draw_move_resize_and_edit(window):
    ed = window.editor
    vp = ed.view.viewport()
    drag(vp, to_view(window, -4, 4), to_view(window, -1, 2))
    assert len(ed.layout_model.samples) == 1
    s = ed.layout_model.samples[0]
    assert abs(s.length - 3) < 0.15 and abs(s.width - 2) < 0.15
    assert abs(s.u + 2.5) < 0.15 and abs(s.v - 3) < 0.15

    # move by dragging the middle
    drag(vp, to_view(window, s.u, s.v), to_view(window, s.u + 4, s.v - 5))
    assert abs(s.u - 1.5) < 0.15 and abs(s.v + 2) < 0.15
    assert abs(s.length - 3) < 0.15

    # resize from the right edge
    right = s.u + s.length / 2
    drag(vp, to_view(window, right, s.v), to_view(window, right + 1, s.v))
    assert abs(s.length - 4) < 0.15

    # table edit updates the model and the item
    ed.table.item(0, 5).setText("1.25")
    ed.table.item(0, 1).setText("0")
    assert s.height == 1.25 and s.u == 0
    assert ed.items[id(s)].pos().x() == 0
    assert ed.table.item(0, 6).text() == "ok"

    # second, overlapping sample is flagged
    ed.add_sample(Sample("X", u=0, v=s.v, length=1, width=1))
    assert "overlaps X" in ed.table.item(0, 6).text()

    ed.view.setFocus()
    ed.scene.clearSelection()
    ed.items[id(s)].setSelected(True)
    ed.delete_selected()
    assert [x.name for x in ed.layout_model.samples] == ["X"]


def test_replace_layout_with_selection(window, tmp_path):
    ed = window.editor
    ed.add_sample(Sample("A", u=-2, v=0, length=1, width=1))  # selected after add
    path = tmp_path / "layout.json"
    ed.layout_model.save(path)
    ed.set_layout(SampleLayout.load(path))
    assert [s.name for s in ed.layout_model.samples] == ["A"]
    window.new_layout()
    assert ed.layout_model.samples == [] and ed.table.rowCount() == 0
