"""Checkerboard lens calibration per stream size (OpenCV), compared with the nominal 23 mm lens."""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

from tools.fieldtest import nominal_fp
from tools.fieldtest.lens import FieldLens

_SUBPIX = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4)
# The phone corrects its main camera's distortion, so only k1 and k2 are left to fit: with k3 and
# the tangential terms free, k2 and k3 trade off and bend the corners the views don't pin down.
# The ultra-wide (distortion off) needs the full model.
MODELS = {"main": cv2.CALIB_FIX_K3 | cv2.CALIB_ZERO_TANGENT_DIST, "wide": 0}


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


def calibrate(corner_sets, pattern, square_m, size, min_views=12, model="main"):
    """FieldLens from the corners of at least `min_views` views at one image size; `model` is
    "main" (k1, k2) or "wide" (k1, k2, k3 and tangential)."""
    views = [c for c in corner_sets if c is not None]
    if len(views) < min_views:
        raise ValueError(f"{len(views)} checkerboard views found; at least {min_views} are needed")
    obj = [board_points(pattern, square_m)] * len(views)
    rms, K, dist, _, _ = cv2.calibrateCamera(obj, [np.asarray(v, np.float32).reshape(-1, 1, 2) for v in views],
                                             tuple(size), None, None, flags=MODELS[model])
    return FieldLens(size, K[0, 0], K[1, 1], K[0, 2], K[1, 2], dist.ravel(), float(rms), len(views), "checkerboard")


def calibrate_images(images, pattern, square_m, min_views=12, model="main"):
    """Calibrate from images of one size; returns the lens and how many views showed the board."""
    sizes = {(im.shape[1], im.shape[0]) for im in images}
    if len(sizes) != 1:
        raise ValueError(f"views of several sizes {sorted(sizes)}: calibrate each size separately")
    corners = [find_corners(im, pattern) for im in images]
    return calibrate(corners, pattern, square_m, sizes.pop(), min_views, model)


def against_nominal(lens, focal_equiv_mm):
    """Measured fx against the nominal f/p at this width: {nominal_fp, fx, diff_pct}."""
    nom = nominal_fp(lens.size[0], focal_equiv_mm)
    return {"nominal_fp": nom, "fx": lens.fx, "fy": lens.fy, "diff_pct": 100.0 * (lens.fx - nom) / nom}


def views_path(folder, size):
    return os.path.join(folder, f"views_{size[0]}x{size[1]}.json")


def save_views(views, folder, size):
    """The captured corner sets, so a restarted page (or a refit) keeps them."""
    os.makedirs(folder, exist_ok=True)
    with open(views_path(folder, size), "w") as f:
        json.dump([np.asarray(v, np.float64).reshape(-1, 2).tolist() for v in views], f)


def load_views(folder, size):
    path = views_path(folder, size)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [np.asarray(v, np.float32).reshape(-1, 1, 2) for v in json.load(f)]
