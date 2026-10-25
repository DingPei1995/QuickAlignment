from dataclasses import replace

import numpy as np
import pytest

from quickalignment.calibration import CalibrationRecord
from quickalignment.collision import (
    SAMPLING_ALLOWANCE, CollisionGeometry, SheetBody, SolidBody, collisions, default_geometry, in_acceptance,
    motor_limits, placed_bodies, surface_points,
)
from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE, Sample, SampleLayout
from quickalignment.stage import MotorPositions, StageConfig, StageModel

TRAVEL = {"st": (-6.0, 6.0), "sn": (-30.0, 65.0), "sz": (35.0, 45.0)}
CAP = default_geometry("capillary")
# a small OSA close to the focus (round, fixed) and a zone plate holder: sharper limits than the default plates
ZP = CollisionGeometry(optics=(SolidBody("OSA", 1.5, 0.5, 30.0, 4.0, moves=False),
                               SolidBody("zone plate holder", 6.0, 1.5, 15.0, 20.0)))


def wide_sample(plate=STANDARD_PLATE, h=0.5):
    """A sample covering the whole riser: the plate side is a flat surface around the beam."""
    u0, v0, u1, v1 = plate.riser_bounds()
    return SampleLayout(plate, [Sample("big", (u0 + u1) / 2, (v0 + v1) / 2, u1 - u0, v1 - v0, h)])


def grown(geo):
    return geo.margin + SAMPLING_ALLOWANCE


def setup(layout, srn=120.0, srz=0.0, u=0.0, v=0.0):
    model = StageModel(StageConfig(), layout.plate)
    h = layout.samples[0].height if layout.samples else 0.0
    return model, model.motors_for_target(u, v, layout.plate.total_thickness + h, srn, srz)


def test_vectorised_transform_matches_plate_to_lab():
    model = StageModel(StageConfig(st0=0.3, srn_axis_u=1.2, srn_axis_v=-1.0, srz_offset_t=0.1, srz_offset_n=-0.2))
    m = MotorPositions(st=1.0, sn=2.0, sz=41.0, srn=150.0, srz=-12.0, pix=100.0, piy=210.0)
    pts = surface_points(wide_sample())[::97]
    assert np.allclose(model.plate_to_lab_many(m, pts), [model.plate_to_lab(m, *p) for p in pts])


def test_sn_lower_limit_from_the_osa_on_a_flat_surface():
    """At 45° incidence a surface moved by -dSN comes sqrt2 dSN closer to the OSA along the beam; it touches
    the front face (radius r, distance d, both grown by margin + sampling allowance g) when
    sqrt2 dSN = (d - g) - (r + g); between the sampled points it may go a little deeper (< 0.03 mm), still
    well on the safe side of the margin alone."""
    layout = wide_sample()
    model, m = setup(layout)
    assert collisions(model, m, layout, ZP, [0.0]) == []
    lim = motor_limits(model, m, layout, ZP, [0.0], TRAVEL)
    osa = ZP.optics[0]
    expect = ((osa.distance - grown(ZP)) - (osa.tip_radius + grown(ZP))) / np.sqrt(2)
    room = m.sn - lim["sn"].lo
    assert lim["sn"].lo_by == "OSA" and expect <= room < expect + 0.03
    assert room < ((osa.distance - ZP.margin) - (osa.tip_radius + ZP.margin)) / np.sqrt(2)
    assert lim["sn"].hi == 65.0 and lim["sn"].hi_by == "travel"
    # a flat plate parallel to the analyzer focal plane slides in its own plane with ST and SZ: no limit
    assert (lim["st"].lo, lim["st"].hi, lim["sz"].lo, lim["sz"].hi) == (-6.0, 6.0, 35.0, 45.0)
    # the limit is where the collision starts
    assert collisions(model, replace(m, sn=lim["sn"].lo + 0.01), layout, ZP, [0.0]) == []
    assert collisions(model, replace(m, sn=lim["sn"].lo - 0.01), layout, ZP, [0.0]) == ["OSA"]


def test_osa_stays_when_the_zone_plate_refocuses():
    layout = wide_sample()
    model, m = setup(layout)
    a = motor_limits(model, m, layout, ZP, [0.0], TRAVEL, fixed_y=0.0)["sn"]
    b = motor_limits(model, m, layout, ZP, [-2.0], TRAVEL, fixed_y=0.0)["sn"]  # zone plate moved upstream
    assert a.lo == pytest.approx(b.lo, abs=0.003) and b.lo_by == "OSA"
    # a fixed OSA farther upstream (another optics reference) gives more room
    c = motor_limits(model, m, layout, ZP, [0.0], TRAVEL, fixed_y=-1.0)["sn"]
    assert c.lo == pytest.approx(a.lo - 1.0 / np.sqrt(2), abs=0.03)
    # the zone plate holder moves with the zone plate: focused 5 mm downstream, it collides
    assert collisions(model, m, layout, ZP, [5.0]) == ["zone plate holder"]  # its front 1 mm upstream of the spot


def test_capillary_limit_and_analyzer():
    """The capillary (design views): nose, chamfered head, body, ring. On a flat surface the part with the
    smallest (d - a) comes first: the front of the head. Lowering SN also slides the beam crossing along the plate, so a
    (made-up) 40 mm wide sample keeps the contact point on it."""
    layout = SampleLayout(STANDARD_PLATE, [Sample("big", 0, 0, 40, 15.5, 0.5)])
    model, m = setup(layout)
    rooms = {b.name: ((b.distance - grown(CAP)) - (b.tip_radius + grown(CAP))) / np.sqrt(2) for b in CAP.optics}
    first = min(rooms, key=rooms.get)
    assert first == "capillary head"
    lim = motor_limits(model, m, layout, CAP, [0.0], TRAVEL)["sn"]
    assert lim.lo_by == first and rooms[first] <= m.sn - lim.lo < rooms[first] + SAMPLING_ALLOWANCE
    # without the optic the analyzer nose, 30 mm from the focal plane, is the limit
    bare = replace(CAP, optics=())
    lim = motor_limits(model, m, layout, bare, [0.0], TRAVEL)["sn"]
    assert lim.lo_by == "analyzer (MBS A1)"
    assert lim.lo == pytest.approx(m.sn - (bare.analyzer.distance - grown(bare)), abs=0.03)


def test_tilted_plate_limits_st():
    """With SRz the surface is no longer parallel to ST: moving along ST brings it towards the OSA."""
    layout = wide_sample()
    for srz in (10.0, -25.0):
        model, m = setup(layout, srz=srz)
        lim = motor_limits(model, m, layout, ZP, [0.0], TRAVEL)
        assert "OSA" in (lim["st"].lo_by, lim["st"].hi_by)
        for x in (lim["st"].lo, lim["st"].hi):
            assert TRAVEL["st"][0] <= x <= TRAVEL["st"][1]
    # beam closer to the surface normal (SRz < 0) leaves more room below in SN than SRz > 0
    lo = {srz: motor_limits(*setup(layout, srz=srz), layout, ZP, [0.0], TRAVEL)["sn"] for srz in (10.0, 0.0, -25.0)}
    gaps = {k: setup(layout, srz=k)[1].sn - v.lo for k, v in lo.items()}
    assert gaps[10.0] < gaps[0.0] < gaps[-25.0]


def test_gating_plate_screws_stand_out():
    """The screws (1 mm above the riser top) come against the OSA before the riser surface does."""
    plate = GATING_PLATE
    layout = SampleLayout(plate, [])
    model, m = setup(layout, u=0.0, v=-2.0)
    lim = motor_limits(model, m, layout, ZP, [0.0], TRAVEL)
    assert lim["sz"].hi < 45.0 and lim["sz"].hi_by == "OSA"  # moving up brings the screws onto the beam
    assert collisions(model, replace(m, sz=lim["sz"].hi + 0.02), layout, ZP, [0.0]) == ["OSA"]


def test_collision_now_returns_none():
    layout = wide_sample()
    model, m = setup(layout)
    m = replace(m, sn=m.sn - 1.0)
    assert collisions(model, m, layout, ZP, [0.0]) == ["OSA"]
    assert motor_limits(model, m, layout, ZP, [0.0], TRAVEL) is None


def test_default_zone_plate_and_osa_shield():
    """Zone plate (placeholder) a thin square plate across the beam, moving with its motor; the OSA, fixed and
    closer, a bent sheet: (1) parallel to the plate surface, (2) across the beam, (3), (4) bent away upstream on the
    analyzer side."""
    zp = default_geometry("zone plate + OSA")
    osa, plate = zp.optics
    assert isinstance(osa, SheetBody) and not osa.moves and plate.square and plate.moves
    assert osa.distance < plate.distance
    pieces = osa.segments()
    assert len(pieces) == 4
    (s0, a0), (s1, a1) = pieces[0]
    assert (s1 - s0) == pytest.approx(-(a1 - a0)) and a0 < a1 < 0  # parallel to the surface (a = -s), plate side
    (s1, a1), (s2, a2) = pieces[1]
    assert s1 == s2 == osa.distance and a1 == pytest.approx(-a2) and a2 > 0  # across the beam, centred on it
    lengths = [np.hypot(q[0] - p[0], q[1] - p[1]) for p, q in pieces]
    assert lengths[0] == min(lengths)
    for (p, q) in pieces[2:]:
        assert q[0] > p[0] and q[1] > p[1] and (q[1] - p[1]) < np.tan(np.radians(30)) * (q[0] - p[0])

    # flat surface in focus: the plate-side end comes against it first; the limit is where the collision starts
    layout = SampleLayout(STANDARD_PLATE, [Sample("big", 0, 0, 40, 15.5, 0.5)])
    model, m = setup(layout)
    lim = motor_limits(model, m, layout, zp, [0.0], TRAVEL)["sn"]
    gap = min((s + a) for (s, a) in [p for piece in pieces for p in piece]) / np.sqrt(2)  # to the surface, mm
    room = m.sn - lim.lo
    assert lim.lo_by == "OSA" and gap - grown(zp) - 0.2 < room < gap
    assert collisions(model, replace(m, sn=lim.lo + 0.01), layout, zp, [0.0]) == []
    assert collisions(model, replace(m, sn=lim.lo - 0.02), layout, zp, [0.0]) == ["OSA"]


def test_optics_stay_out_of_the_analyzer_acceptance():
    """The analyzer takes electrons within ±15° of its axis (45° from the beam): the optic solids must stay within
    30° of the beam axis seen from the focus."""
    for optic in ("zone plate + OSA", "capillary"):
        assert in_acceptance(default_geometry(optic), [0.0]) == []
    wide = replace(CAP, optics=(SolidBody("wide head", 6.0, 4.5, 0.0, 5.0, square=True),))
    assert in_acceptance(wide, [0.0]) == ["wide head"]  # its edge 37° from the beam axis at the front
    assert in_acceptance(wide, [-6.0]) == []  # pulled back 6 mm: 21°


def test_configuration_roundtrip():
    rec = CalibrationRecord()
    assert rec.collision_geometry() == default_geometry("zone plate + OSA")
    geo = CollisionGeometry(optics=(SolidBody("OSA", 2.0, 0.4, 25.0, 3.0, moves=False, square=True),), margin=0.1)
    data = replace(rec, collision=geo).to_dict()
    back = CalibrationRecord.from_dict(data)
    assert back.collision == geo
    # partial entry: missing parts from the optic's defaults
    data["optics"]["optic_type"] = "capillary"
    data["collision"] = {"margin": 0.5}
    back = CalibrationRecord.from_dict(data)
    assert back.collision_geometry().optics == CAP.optics and back.collision_geometry().margin == 0.5
    data["collision"] = {"optics": [{"name": "x", "distance": -1}]}
    with pytest.raises(ValueError):
        CalibrationRecord.from_dict(data)


def test_sheet_inside_and_roundtrip():
    """A bent sheet is one thin upright box per piece."""
    sheet = SheetBody("S", distance=4.0, points=((0.0, -1.0), (0.0, 1.0), (3.0, 2.0)), thickness=0.2, height=10.0,
                      moves=False)
    geo = CollisionGeometry(optics=(sheet,), margin=0.0)
    body = placed_bodies(geo, [0.0])[1]
    g = SAMPLING_ALLOWANCE
    inside = lambda x, s, z=0.0: bool(body.inside(np.array([[x, -s, z]]))[0])  # noqa: E731  (lab x = -across)
    assert inside(0.0, 4.0) and inside(0.0, 4.0, 4.9) and not inside(0.0, 4.0, 5.0 + g + 0.05)
    assert not inside(0.0, 4.0 + 0.1 + g + 0.05) and not inside(0.0, 5.0)
    assert inside(-1.5, 5.5)  # on the bent piece, half way: across 1.5 (analyzer side, -x), 1.5 upstream
    assert in_acceptance(geo, [0.0]) == []
    data = geo.to_dict()
    assert CollisionGeometry.from_dict(data).optics[0] == sheet
    with pytest.raises(ValueError):
        CollisionGeometry.from_dict({"optics": [{"name": "S", "points": [[0, 1]]}]})
