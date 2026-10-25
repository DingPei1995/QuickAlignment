import numpy as np
import pytest

from quickalignment.geometry import GATING_PLATE, STANDARD_PLATE
from quickalignment.photo import (
    apply_homography, check_corners, corner_points, detect_samples, homography, label_regions, plate_view_bounds,
    rectify, rgb_to_lab,
)

SAMPLES = [  # (u0, v0, u1, v1), RGB
    ((-4.0, 2.0, -1.0, 4.0), (60, 70, 110)),
    ((0.5, -1.0, 2.5, 1.5), (120, 118, 125)),
    ((3.0, -6.0, 5.5, -3.0), (150, 110, 60)),  # touches the right edge of the sample area
]

# plate -> photo: tilted, rotated, perspective (camera not exactly above)
PHOTO_CORNERS = [(410.0, 160.0), (980.0, 215.0), (930.0, 1010.0), (350.0, 940.0)]


def synthetic_photo(plate=STANDARD_PLATE, samples=SAMPLES, size=(1200, 1300), seed=1):
    plate_pts = [p for _, p in corner_points(plate)]
    h = homography(plate_pts, PHOTO_CORNERS)
    rows, cols = size
    yy, xx = np.mgrid[0:rows, 0:cols]
    uv = apply_homography(np.linalg.inv(h), np.c_[xx.ravel() + 0.5, yy.ravel() + 0.5])
    u, v = uv[:, 0].reshape(rows, cols), uv[:, 1].reshape(rows, cols)
    img = np.empty((rows, cols, 3), float)
    img[:] = (35, 35, 40)
    on_plate = (abs(u) <= plate.width / 2) & (abs(v) <= plate.height / 2)
    img[on_plate] = (150, 150, 150)
    a0, b0, a1, b1 = plate.riser_bounds()
    img[(u >= a0) & (u <= a1) & (v >= b0) & (v <= b1)] = (192, 190, 186)
    for (s0, t0, s1, t1), color in samples:
        img[(u >= s0) & (u <= s1) & (v >= t0) & (v <= t1)] = color
    img += np.random.default_rng(seed).normal(0, 4, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8), h


def test_homography_round_trip():
    src = [(0, 0), (10, 0), (10, 5), (0, 5), (3, 2)]
    h_true = np.array([[1.2, 0.1, 30], [-0.2, 0.9, 50], [1e-3, -2e-3, 1]])
    dst = apply_homography(h_true, src)
    h = homography(src, dst)
    assert np.allclose(apply_homography(h, src), dst, atol=1e-6)
    with pytest.raises(ValueError):
        homography([(0, 0), (1, 1), (2, 2), (3, 3)], [(0, 0), (1, 1), (2, 2), (3, 3)])


def test_detects_samples_on_perspective_photo():
    img, h = synthetic_photo()
    rect = rectify(img, h, plate_view_bounds(STANDARD_PLATE))
    result = detect_samples(rect, STANDARD_PLATE.riser_bounds())
    assert len(result.detections) == len(SAMPLES)
    for (box, _), d in zip(SAMPLES, result.detections):
        assert np.allclose((d.u0, d.v0, d.u1, d.v1), box, atol=0.1), (d, box)
    # bare plate colour found despite the samples
    assert np.linalg.norm(result.background - rgb_to_lab(np.array([192, 190, 186], np.uint8))) < 3


def test_gating_plate_and_given_background():
    samples = [((-2.0, 0.0, 1.0, 3.0), (90, 140, 90))]
    img, h = synthetic_photo(GATING_PLATE, samples)
    rect = rectify(img, h, plate_view_bounds(GATING_PLATE))
    bg = rgb_to_lab(np.array([192, 190, 186], np.uint8))
    result = detect_samples(rect, GATING_PLATE.riser_bounds(), background=bg)
    assert len(result.detections) == 1
    assert np.allclose((result.detections[0].u0, result.detections[0].v0, result.detections[0].u1,
                        result.detections[0].v1), samples[0][0], atol=0.1)


def test_dust_and_threshold():
    samples = SAMPLES[:1] + [((2.0, 2.0, 2.2, 2.2), (40, 40, 40))]  # 0.04 mm^2 speck
    img, h = synthetic_photo(samples=samples)
    rect = rectify(img, h, plate_view_bounds(STANDARD_PLATE))
    assert len(detect_samples(rect, STANDARD_PLATE.riser_bounds()).detections) == 1
    assert len(detect_samples(rect, STANDARD_PLATE.riser_bounds(), min_area=0.01, smooth=0).detections) == 2
    assert detect_samples(rect, STANDARD_PLATE.riser_bounds(), threshold=200).detections == []


REF = [p for _, p in corner_points(STANDARD_PLATE)]


def test_corner_order_checked():
    check_corners(REF, PHOTO_CORNERS)
    with pytest.raises(ValueError):
        check_corners(REF, [PHOTO_CORNERS[i] for i in (1, 0, 2, 3)])  # crossed
    with pytest.raises(ValueError):
        check_corners(REF, PHOTO_CORNERS[::-1])  # mirrored / wrong sense


def test_label_regions():
    m = np.zeros((5, 6), bool)
    m[0, 0] = m[1, 1] = True  # diagonal neighbours: one region
    m[3:5, 3:6] = True
    regions = sorted(label_regions(m), key=len)
    assert [len(r) for r in regions] == [2, 6]
