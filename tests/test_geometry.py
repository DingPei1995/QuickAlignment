from quickalignment.geometry import PlateGeometry, Sample, SampleLayout


def test_plate_dimensions():
    plate = PlateGeometry()
    assert abs(plate.riser_thickness - 3.9) < 1e-9
    assert plate.riser_bounds() == (-5.5, -7.75, 5.5, 7.75)
    us = [p[0] for p in plate.outline()]
    vs = [p[1] for p in plate.outline()]
    assert (min(us), max(us)) == (-9.0, 9.0)
    assert (min(vs), max(vs)) == (-7.75, 7.75 + 6.0)


def test_warnings_and_surface_height():
    layout = SampleLayout()
    a = Sample("A", u=0, v=0, length=2, width=2, height=0.5)
    b = Sample("B", u=1.5, v=0, length=2, width=2)
    c = Sample("C", u=5.0, v=0, length=2, width=2)
    layout.samples += [a, b, c]
    assert layout.warnings(a) == ["overlaps B"]
    assert "outside riser" in layout.warnings(c)
    assert a.surface_height(layout.plate) == 5.5
    assert layout.unique_name() == "S1"


def test_roundtrip(tmp_path):
    layout = SampleLayout(samples=[Sample("A", u=1.0, v=-2.0, length=3, width=1, height=0.2)])
    path = tmp_path / "layout.json"
    layout.save(path)
    loaded = SampleLayout.load(path)
    assert loaded.samples == layout.samples
    assert loaded.plate == layout.plate
