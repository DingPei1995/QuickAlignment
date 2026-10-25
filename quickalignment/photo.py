"""Find samples on a photo of the plate taken from above (sample side).

The user clicks the four corners of the sample area on the photo; a
perspective transform (homography) maps the photo onto the plate frame, so
the photo is resampled on a regular grid in plate mm ("rectified") and laid
over the plate model. Samples are the parts of the sample area whose colour
differs from the bare plate (CIELAB colour difference ΔE): the mask is
cleaned up, split into connected regions and each region gives a rectangle
(its bounding box) in plate coordinates.

Only numpy; images are (rows, cols, 3) uint8 RGB arrays. The photo shows
positions only: the sample height H is entered by the user.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .geometry import PlateGeometry, Rect

PX_PER_MM = 20  # rectified grid: 0.05 mm per pixel


def corner_points(plate: PlateGeometry) -> list[tuple[str, tuple[float, float]]]:
    """The four reference points clicked on the photo: the sample area corners, in click order."""
    u0, v0, u1, v1 = plate.riser_bounds()
    return [
        ("top left (tab side)", (u0, v1)),
        ("top right (tab side)", (u1, v1)),
        ("bottom right", (u1, v0)),
        ("bottom left", (u0, v0)),
    ]


def homography(src, dst) -> np.ndarray:
    """3 x 3 matrix H with dst ~ H @ src (normalised DLT, at least 4 point pairs)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 2 or len(src) < 4:
        raise ValueError("At least 4 point pairs are needed.")

    def normalise(p):
        c = p.mean(axis=0)
        d = np.sqrt(((p - c) ** 2).sum(axis=1)).mean()
        if d < 1e-12:
            raise ValueError("The points coincide.")
        s = np.sqrt(2) / d
        t = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
        return t, (p - c) * s

    ts, ps = normalise(src)
    td, pd = normalise(dst)
    rows = []
    for (x, y), (u, v) in zip(ps, pd):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, sv, vt = np.linalg.svd(np.asarray(rows))
    if sv[-2] < 1e-9 * sv[0]:
        raise ValueError("The points are degenerate (three of them on a line?).")
    h = np.linalg.inv(td) @ vt[-1].reshape(3, 3) @ ts
    return h / h[2, 2]


def apply_homography(h: np.ndarray, pts) -> np.ndarray:
    pts = np.asarray(pts, float)
    q = np.c_[pts, np.ones(len(pts))] @ h.T
    return q[:, :2] / q[:, 2:3]


def check_corners(plate: PlateGeometry, photo_pts) -> None:
    """Raise ValueError if the clicked corners cannot be the sample area seen from the sample side."""
    p = np.asarray(photo_pts, float)
    if len(p) != 4:
        raise ValueError("Click the four corners of the sample area.")
    # convex, in the same turning sense as the plate corners (image y points down: a front view keeps
    # the sense; a mirrored photo, or corners clicked in the wrong order, reverse it or cross over)
    q = np.array([pt for _, pt in corner_points(plate)])
    q[:, 1] *= -1
    cross = []
    for i in range(4):
        a, b, c = p[i], p[(i + 1) % 4], p[(i + 2) % 4]
        cross.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    ref = (q[1, 0] - q[0, 0]) * (q[2, 1] - q[1, 1]) - (q[1, 1] - q[0, 1]) * (q[2, 0] - q[1, 0])
    if not all(np.sign(c) == np.sign(ref) and abs(c) > 1e-9 for c in cross):
        raise ValueError("The corners must be clicked in the order shown (top left, top right, bottom right, "
                         "bottom left, with the tab at the top) and must not cross over.")


@dataclass
class Rectified:
    """A photo resampled on the plate grid: pixel (row, col) has its centre at
    u = u0 + (col + 0.5) / px_per_mm, v = v1 - (row + 0.5) / px_per_mm."""

    pixels: np.ndarray  # (rows, cols, 3) uint8
    valid: np.ndarray  # (rows, cols) bool: inside the photo
    u0: float
    v1: float
    px_per_mm: float

    def plate_bounds(self) -> Rect:
        rows, cols = self.valid.shape
        return (self.u0, self.v1 - rows / self.px_per_mm, self.u0 + cols / self.px_per_mm, self.v1)

    def index(self, u: float, v: float) -> tuple[int, int]:
        """(row, col) of the pixel holding the plate point (u, v)."""
        return int(np.floor((self.v1 - v) * self.px_per_mm)), int(np.floor((u - self.u0) * self.px_per_mm))

    def mask_of(self, rect: Rect) -> np.ndarray:
        """Pixels whose centre lies in the plate rectangle (u0, v0, u1, v1)."""
        rows, cols = self.valid.shape
        u = self.u0 + (np.arange(cols) + 0.5) / self.px_per_mm
        v = self.v1 - (np.arange(rows) + 0.5) / self.px_per_mm
        return ((v >= rect[1]) & (v <= rect[3]))[:, None] & ((u >= rect[0]) & (u <= rect[2]))[None, :]


def plate_view_bounds(plate: PlateGeometry, margin: float = 0.5) -> Rect:
    top = plate.height / 2 + plate.neck_height + plate.tab_height
    return (-plate.width / 2 - margin, plate.lowest_v() - margin, plate.width / 2 + margin, top + margin)


def rectify(image: np.ndarray, h_plate_to_photo: np.ndarray, bounds: Rect, px_per_mm: float = PX_PER_MM) -> Rectified:
    """Resample the photo on a plate grid covering `bounds` (bilinear)."""
    u0, v0, u1, v1 = bounds
    cols, rows = int(round((u1 - u0) * px_per_mm)), int(round((v1 - v0) * px_per_mm))
    u = u0 + (np.arange(cols) + 0.5) / px_per_mm
    v = v1 - (np.arange(rows) + 0.5) / px_per_mm
    uu, vv = np.meshgrid(u, v)
    xy = apply_homography(h_plate_to_photo, np.c_[uu.ravel(), vv.ravel()])
    # photo pixel (r, c) has its centre at x = c + 0.5, y = r + 0.5
    x, y = xy[:, 0] - 0.5, xy[:, 1] - 0.5
    hgt, wid = image.shape[:2]
    valid = (x >= 0) & (y >= 0) & (x <= wid - 1) & (y <= hgt - 1)
    x, y = np.clip(x, 0, wid - 1), np.clip(y, 0, hgt - 1)
    c0, r0 = np.minimum(x.astype(int), wid - 2 if wid > 1 else 0), np.minimum(y.astype(int), hgt - 2 if hgt > 1 else 0)
    c1, r1 = np.minimum(c0 + 1, wid - 1), np.minimum(r0 + 1, hgt - 1)
    fx, fy = (x - c0)[:, None], (y - r0)[:, None]
    img = image.astype(np.float32)
    out = (img[r0, c0] * (1 - fx) * (1 - fy) + img[r0, c1] * fx * (1 - fy)
           + img[r1, c0] * (1 - fx) * fy + img[r1, c1] * fx * fy)
    out[~valid] = 0
    pixels = np.clip(out + 0.5, 0, 255).astype(np.uint8).reshape(rows, cols, 3)
    return Rectified(pixels, valid.reshape(rows, cols), u0, v1, px_per_mm)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (uint8) -> CIELAB (D65), float32, same leading shape."""
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]], np.float32)
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    lab = np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)
    return lab.astype(np.float32)


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1)^2 window (edges replicated), along the first two axes."""
    if r <= 0:
        return a
    pad = [(r, r), (r, r)] + [(0, 0)] * (a.ndim - 2)
    p = np.pad(a, pad, mode="edge").astype(np.float64)
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, [(1, 0), (1, 0)] + [(0, 0)] * (a.ndim - 2))
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / (k * k)).astype(a.dtype)


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return m
    return _box_blur(m.astype(np.float32), r) > 1e-6


def _erode(m: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return m
    return _box_blur(m.astype(np.float32), r) > 1 - 1e-6


def label_regions(mask: np.ndarray) -> list[np.ndarray]:
    """Connected (8-neighbour) regions of a boolean mask, each as an (n, 2) array of (row, col)."""
    rows, cols = mask.shape
    seen = np.zeros_like(mask, bool)
    regions = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        seen[r0, c0] = True
        queue, pts = deque([(r0, c0)]), []
        while queue:
            r, c = queue.popleft()
            pts.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols and mask[rr, cc] and not seen[rr, cc]:
                        seen[rr, cc] = True
                        queue.append((rr, cc))
        regions.append(np.asarray(pts))
    return regions


@dataclass
class Detection:
    """A sample found on the photo: bounding box in plate mm and its mean colour difference
    (from the bare plate, or from the nearest picked sample colour)."""

    u0: float
    v0: float
    u1: float
    v1: float
    area: float  # mm^2 of the region (not of the box)
    delta_e: float

    @classmethod
    def merged(cls, parts: list[Detection]) -> Detection:
        """One box around several pieces (a sample broken up by paint or wires)."""
        area = sum(d.area for d in parts)
        return cls(min(d.u0 for d in parts), min(d.v0 for d in parts), max(d.u1 for d in parts),
                   max(d.v1 for d in parts), area, sum(d.delta_e * d.area for d in parts) / area)

    @property
    def center(self) -> tuple[float, float]:
        return (self.u0 + self.u1) / 2, (self.v0 + self.v1) / 2

    @property
    def size(self) -> tuple[float, float]:
        return self.u1 - self.u0, self.v1 - self.v0


@dataclass
class DetectionResult:
    detections: list[Detection]
    mask: np.ndarray  # final foreground mask on the rectified grid
    background: np.ndarray  # Lab colour of the bare plate used (NaN in sample colour mode without one)
    delta_e: np.ndarray  # colour difference used, rectified grid


def background_lab(lab: np.ndarray, area: np.ndarray, threshold: float) -> np.ndarray:
    """Colour of the bare sample area: median, refined over the pixels close to it.

    Works while the bare plate is the largest uniform part of the area;
    otherwise the user picks the background on the photo."""
    pts = lab[area]
    if len(pts) == 0:
        raise ValueError("The sample area is not on the photo.")
    bg = np.median(pts, axis=0)
    for _ in range(4):
        close = pts[np.linalg.norm(pts - bg, axis=1) < threshold]
        if len(close) < 0.05 * len(pts):
            break
        bg = np.median(close, axis=0)
    return bg


def detect_samples(rect: Rectified, area_rect: Rect, threshold: float = 12.0, min_area: float = 0.2,
                   margin: float = 0.15, smooth: float = 0.1, background: np.ndarray | None = None,
                   sample_colors=None) -> DetectionResult:
    """Samples in the plate rectangle `area_rect` (the sample area).

    Two modes: without `sample_colors` a sample is what differs from the bare
    plate by more than `threshold`; with them (Lab colours picked on samples)
    it is what is within `threshold` of one of them, which leaves out other
    things on the plate (silver paint, glue, wires).

    threshold: ΔE (CIELAB) above which a pixel is not bare plate / not a sample colour;
    min_area: smaller regions (mm^2) are dropped (dust, scratches);
    margin: mm left out along the sample area border (its edge on the photo);
    smooth: mm, radius of the noise filter and of the clean-up of the mask;
    background: Lab colour of the bare plate (None: estimated)."""
    s = rect.px_per_mm
    u0, v0, u1, v1 = area_rect
    area = rect.mask_of((u0 + margin, v0 + margin, u1 - margin, v1 - margin)) & _erode(rect.valid, 1)
    r = max(0, int(round(smooth * s)))
    lab = rgb_to_lab(_box_blur(rect.pixels.astype(np.float32), max(1, r // 2)).clip(0, 255))
    if sample_colors is not None and len(sample_colors):
        bg = np.asarray(background, np.float32) if background is not None else np.full(3, np.nan, np.float32)
        de = np.min([np.linalg.norm(lab - np.asarray(c, np.float32), axis=-1) for c in sample_colors], axis=0)
        de[~area] = np.inf
        fg = de < threshold
    else:
        bg = np.asarray(background, np.float32) if background is not None else background_lab(lab, area, threshold)
        de = np.linalg.norm(lab - bg, axis=-1)
        de[~area] = 0
        fg = de > threshold
    # opening removes specks, closing fills small gaps (glare, grain) inside a sample
    fg = _dilate(_erode(fg, r), r)
    fg = _erode(_dilate(fg, r), r) & area
    detections = []
    for pts in label_regions(fg):
        n_mm2 = len(pts) / s ** 2
        if n_mm2 < min_area:
            continue
        rows, cols = pts[:, 0], pts[:, 1]
        d = Detection(
            u0=rect.u0 + cols.min() / s, u1=rect.u0 + (cols.max() + 1) / s,
            v0=rect.v1 - (rows.max() + 1) / s, v1=rect.v1 - rows.min() / s,
            area=n_mm2, delta_e=float(de[rows, cols].mean()),
        )
        # a sample cut by the left-out border reaches the sample area edge
        tol = 1.5 / s
        if d.u0 < u0 + margin + tol:
            d.u0 = u0
        if d.u1 > u1 - margin - tol:
            d.u1 = u1
        if d.v0 < v0 + margin + tol:
            d.v0 = v0
        if d.v1 > v1 - margin - tol:
            d.v1 = v1
        detections.append(d)
    # reading order: top to bottom, then left to right
    detections.sort(key=lambda d: (-round(d.center[1]), d.center[0]))
    return DetectionResult(detections, fg, bg, de)
