import pytest

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
    assert "outside sample area" in layout.warnings(c)
    assert a.surface_height(layout.plate) == 5.5
    assert layout.unique_name() == "S1"


def test_roundtrip(tmp_path):
    layout = SampleLayout(samples=[Sample("A", u=1.0, v=-2.0, length=3, width=1, height=0.2)])
    path = tmp_path / "layout.json"
    layout.save(path)
    loaded = SampleLayout.load(path)
    assert loaded.samples == layout.samples
    assert loaded.plate == layout.plate


def test_plate_types_roundtrip(tmp_path):
    from quickalignment.geometry import GATING_PLATE, PLATES

    assert set(PLATES) == {"standard", "gating"}
    assert GATING_PLATE.riser_bounds() == (-5.5, -2.75, 5.5, 7.75)
    assert GATING_PLATE.lowest_v() == -8.75
    layout = SampleLayout(plate=GATING_PLATE, samples=[Sample("A")])
    path = tmp_path / "g.json"
    layout.save(path)
    assert SampleLayout.load(path).plate is GATING_PLATE


def test_custom_plate(tmp_path):
    from quickalignment.geometry import custom_plate

    plate = custom_plate(6.0, 4.0, 8.2)
    assert plate.riser_bounds() == (-3.0, -2.0, 3.0, 2.0)  # centred on the plate
    assert plate.total_thickness == 8.2 and plate.base_thickness == 1.1
    layout = SampleLayout(plate=plate, samples=[Sample("A", 0, 0, 2, 2, 0.3), Sample("B", 3.5, 0)])
    assert layout.warnings(layout.samples[0]) == []
    assert "outside sample area" in layout.warnings(layout.samples[1])
    path = tmp_path / "c.json"
    layout.save(path)
    assert SampleLayout.load(path).plate == plate
    with pytest.raises(ValueError):
        custom_plate(20.0, 4.0, 8.0)  # wider than the back plate
    with pytest.raises(ValueError):
        custom_plate(6.0, 4.0, 1.0)  # below the back plate
    shifted = custom_plate(6.0, 4.0, 8.2, center_y=-5.75)  # flush with the bottom edge
    assert shifted.riser_bounds() == (-3.0, -7.75, 3.0, -3.75)
    assert SampleLayout.from_dict(SampleLayout(plate=shifted).to_dict()).plate == shifted
    with pytest.raises(ValueError):
        custom_plate(6.0, 4.0, 8.2, center_y=6.0)  # sticks out at the top
