"""Checkerboard lens calibration per stream size (OpenCV), compared with the nominal 23 mm lens."""
from __future__ import annotations

import cv2
import numpy as np

from tools.fieldtest import nominal_fp
from tools.fieldtest.lens import FieldLens

_SUBPIX = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4)


def board_points(pattern, square_m):
    """Inner-corner positions of the board (cols × rows) on its own plane, metres."""
    cols, rows = pattern
    g = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2).astype(np.float32)
    return np.column_stack([g * square_m, np.zeros(len(g), np.float32)]).astype(np.float32)


def find_corners(img, pattern):
    """The board's inner corners in one view (sub-pixel), or None."""
    grey = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, corners = cv2.findChessboardCorners(grey, tuple(pattern),
                                            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        return None
    return cv2.cornerSubPix(grey, corners, (5, 5), (-1, -1), _SUBPIX)


def calibrate(corner_sets, pattern, square_m, size, min_views=12):
    """FieldLens from the corners of at least `min_views` views at one image size."""
    views = [c for c in corner_sets if c is not None]
    if len(views) < min_views:
        raise ValueError(f"{len(views)} checkerboard views found; at least {min_views} are needed")
    obj = [board_points(pattern, square_m)] * len(views)
    rms, K, dist, _, _ = cv2.calibrateCamera(obj, [np.asarray(v, np.float32).reshape(-1, 1, 2) for v in views],
                                             tuple(size), None, None)
    return FieldLens(size, K[0, 0], K[1, 1], K[0, 2], K[1, 2], dist.ravel(), float(rms), len(views), "checkerboard")


def calibrate_images(images, pattern, square_m, min_views=12):
    """Calibrate from images of one size; returns the lens and how many views showed the board."""
    sizes = {(im.shape[1], im.shape[0]) for im in images}
    if len(sizes) != 1:
        raise ValueError(f"views of several sizes {sorted(sizes)}: calibrate each size separately")
    corners = [find_corners(im, pattern) for im in images]
    return calibrate(corners, pattern, square_m, sizes.pop(), min_views)


def against_nominal(lens, focal_equiv_mm):
    """Measured fx against the nominal f/p at this width: {nominal_fp, fx, diff_pct}."""
    nom = nominal_fp(lens.size[0], focal_equiv_mm)
    return {"nominal_fp": nom, "fx": lens.fx, "fy": lens.fy, "diff_pct": 100.0 * (lens.fx - nom) / nom}
