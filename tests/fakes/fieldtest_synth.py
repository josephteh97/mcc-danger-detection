"""Synthetic cameras, cones and checkerboards for the field-test quick checks (no phone needed)."""
from __future__ import annotations

import math

import cv2
import numpy as np

from tools.fieldtest.calib import board_points
from tools.fieldtest.lens import FieldCamera, FieldLens

STREAM = (1440, 1080)
FP = 957.0


def level_camera(height_m=1.5, pitch_deg=0.0, lens=None):
    return FieldCamera.posed(lens or FieldLens.pinhole(STREAM, FP), height_m, pitch_deg)


def wide_lens(hfov_deg=102.0, q=0.571, size=(1632, 1224)):
    """An OpenCV-model lens (k1, k2, k3) with this field of view and centre ratio q, so the twin's
    D = 3(1 − q) / tan²(θ/2) is 0.844 for the defaults; monotone out to the corners."""
    t = math.tan(math.radians(hfov_deg) / 2)
    k1, k3 = -0.4, 0.042
    k2 = (q - 1 - k1 * t ** 2 - k3 * t ** 6) / t ** 4      # the edge ray lands on the frame edge
    fx = (size[0] / 2) / (q * t)
    return FieldLens(size, fx, fx, size[0] / 2, size[1] / 2, [k1, k2, 0, 0, k3], source="synthetic")


def board_poses(n, rng, distance=(0.45, 0.8), tilt_deg=35, spread=0.12):
    """n board poses (rvec, tvec) in front of the camera, tilted and spread across the view."""
    poses = []
    for _ in range(n):
        r = np.radians(rng.uniform(-tilt_deg, tilt_deg, 3)) * [1, 1, 0.3]
        t = np.array([rng.uniform(-spread, spread) - 0.1, rng.uniform(-spread, spread) * 0.7 - 0.07, rng.uniform(*distance)])
        poses.append((r, t))
    return poses


def render_board(lens, rvec, tvec, pattern=(9, 6), square_m=0.025, ppm=4000):
    """A pinhole image of a printed checkerboard (white margin of one square) at a pose."""
    cols, rows = pattern
    sq = int(round(square_m * ppm))
    tex = np.full(((rows + 3) * sq, (cols + 3) * sq), 255, np.uint8)
    for j in range(rows + 1):
        for i in range(cols + 1):
            if (i + j) % 2 == 0:
                tex[(j + 1) * sq:(j + 2) * sq, (i + 1) * sq:(i + 2) * sq] = 0
    # texture pixel -> board plane metres (inner corner 0 at texture (2 sq, 2 sq)) -> image
    T = np.array([[1 / ppm, 0, -2 * square_m], [0, 1 / ppm, -2 * square_m], [0, 0, 1.0]])
    R = cv2.Rodrigues(np.asarray(rvec, np.float64))[0]
    H = lens.K @ np.column_stack([R[:, 0], R[:, 1], np.asarray(tvec, np.float64)]) @ T
    img = cv2.warpPerspective(tex, H, lens.size, flags=cv2.INTER_AREA, borderValue=128)
    return cv2.GaussianBlur(img, (3, 3), 0.6)


def board_corners(lens, rvec, tvec, pattern, square_m, rng=None, noise_px=0.0):
    """The board's inner corners through a (distorted) lens, with optional noise, or None if any
    falls outside the image."""
    pts, _ = cv2.projectPoints(board_points(pattern, square_m), np.asarray(rvec, np.float64),
                               np.asarray(tvec, np.float64), lens.K, lens.dist)
    pts = pts.reshape(-1, 2)
    if rng is not None and noise_px:
        pts = pts + rng.normal(0, noise_px, pts.shape)
    w, h = lens.size
    if np.any(pts < 0) or np.any(pts[:, 0] >= w) or np.any(pts[:, 1] >= h):
        return None
    return pts.astype(np.float32).reshape(-1, 1, 2)


def wide_board_views(lens, rng, n=40, pattern=(9, 6), square_m=0.1):
    """Corner sets of a large board seen across the whole wide field, out to the edges."""
    views, tries = [], 0
    while len(views) < n and tries < 5000:
        tries += 1
        z = rng.uniform(0.9, 1.8)
        ang = rng.uniform(-48, 48)                               # board centre direction across the view
        el = rng.uniform(-35, 35)
        c = np.array([math.tan(math.radians(ang)), math.tan(math.radians(el)), 1.0]) * z
        r = np.radians([rng.uniform(-30, 30), rng.uniform(-30, 30) + ang * 0.6, rng.uniform(-10, 10)])
        R = cv2.Rodrigues(r)[0]
        half = np.array([(pattern[0] - 1) * square_m / 2, (pattern[1] - 1) * square_m / 2, 0])
        t = c - R @ half
        if abs((R @ np.array([0, 0, 1.0]))[2]) < 0.5:           # not seen nearly edge-on
            continue
        pts = board_corners(lens, r, t, pattern, square_m, rng, 0.1)
        if pts is not None:
            views.append(pts)
    return views


def write_recording(path, cam, seconds=2.0, fps=10, cones=(), poles=(), size=None):
    """A short video of a grey car park seen by `cam`: a 1 m grid, orange cones at `cones` and
    1 m poles at `poles` (ground x, y)."""
    w, h = size or cam.lens.size
    G = np.array([[0.05, 0, -20.0], [0, -0.05, 40.0], [0, 0, 1.0]])            # texture px -> ground m
    tex = np.full((800, 800, 3), 110, np.uint8)
    for i in range(0, 800, 20):
        cv2.line(tex, (i, 0), (i, 799), (135, 135, 135), 1)
        cv2.line(tex, (0, i), (799, i), (135, 135, 135), 1)
    img = cv2.warpPerspective(tex, cam.ground_to_image_homography() @ G, (w, h), borderValue=(200, 190, 180))
    for x, y in cones:
        uv, _ = cam.image_points([[x, y, 0.0]])
        cv2.circle(img, tuple(int(c) for c in uv[0]), 6, (0, 120, 255), -1)
    for x, y in poles:
        uv, _ = cam.image_points([[x, y, 0.0], [x, y, 1.0]])
        cv2.line(img, tuple(int(c) for c in uv[0]), tuple(int(c) for c in uv[1]), (240, 240, 240), 3)
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for _ in range(int(seconds * fps)):
        out.write(img)
    out.release()
    return path
