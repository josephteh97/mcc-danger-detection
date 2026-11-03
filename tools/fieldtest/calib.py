"""Checkerboard lens calibration per stream size (OpenCV), compared with the nominal 23 mm lens."""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

from tools.fieldtest import nominal_fp
from tools.fieldtest.lens import FieldLens, focal_file, focal_path

_SUBPIX = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4)
# The phone corrects its main camera's distortion, so only k1 and k2 are left to fit: with k3 and
# the tangential terms free, k2 and k3 trade off and bend the corners the views don't pin down.
# The ultra-wide (distortion off) needs the full model.
MODELS = {"main": cv2.CALIB_FIX_K3 | cv2.CALIB_ZERO_TANGENT_DIST, "wide": 0}
REPEAT_PX = 0.5                     # corners this close (mean) to an earlier view add nothing: a frozen stream, a still board
FOCAL_OFF_PCT = 15.0                # more than this from nominal is another focal length (23 to 28 mm is 22%)


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


def is_repeat(corners, views):
    """Whether these corners are the same view as one already kept."""
    c = np.asarray(corners, np.float64).reshape(-1, 2)
    return any(np.linalg.norm(c - np.asarray(v, np.float64).reshape(-1, 2), axis=1).mean() < REPEAT_PX for v in views)


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


def board_settings(phone):
    """(pattern, square size in metres, minimum views) from the phone settings."""
    b = phone["checkerboard"]
    return b["inner_corners"], b["square_mm"] / 1000, b["min_views"]


def calibrate_images(images, pattern, square_m, min_views=12, model="main"):
    """The lens from images of one size. `images` can be any iterable: only their corners are kept."""
    size, corners = None, []
    for im in images:
        if im is None:                  # a file that isn't an image
            continue
        shape = (im.shape[1], im.shape[0])
        if size not in (None, shape):
            raise ValueError(f"views of several sizes {size} and {shape}: calibrate each size separately")
        size = shape
        c = find_corners(im, pattern)
        if c is not None and not is_repeat(c, corners):
            corners.append(c)
    if size is None:
        raise ValueError("no images to calibrate from")
    return calibrate(corners, pattern, square_m, size, min_views, model)


def check_fit(lens, focal_equiv_mm, rms_limit):
    """Raise ValueError if this fit must not replace a saved lens: too rough, or fx not of this focal length."""
    if lens.rms > rms_limit:
        raise ValueError(f"reprojection {lens.rms:.3f} px is over {rms_limit} px: not saved, the previous calibration stays. "
                         "Capture again: board flatter, held stiller, more views in the corners")
    n = against_nominal(lens, focal_equiv_mm)
    if abs(n["diff_pct"]) > FOCAL_OFF_PCT:
        raise ValueError(f"fx {n['fx']:.1f} px is {n['diff_pct']:+.1f}% from the nominal {n['nominal_fp']:.1f} px at "
                         f"{float(focal_equiv_mm):g} mm: not saved. If this was filmed at another focal length, set it and calibrate again")


def against_nominal(lens, focal_equiv_mm):
    """Measured fx against the nominal f/p at this width: {nominal_fp, fx, fy, diff_pct}."""
    nom = nominal_fp(lens.size[0], focal_equiv_mm)
    return {"nominal_fp": nom, "fx": lens.fx, "fy": lens.fy, "diff_pct": 100.0 * (lens.fx - nom) / nom}


def save_views(views, folder, size, focal_equiv_mm):
    """The captured corner sets, so a restarted page (or a refit) keeps them. Each focal length has its own."""
    os.makedirs(folder, exist_ok=True)
    with open(focal_path("views", folder, size, focal_equiv_mm), "w") as f:
        json.dump({"focal_equiv_mm": focal_equiv_mm,
                   "views": [np.asarray(v, np.float64).reshape(-1, 2).tolist() for v in views]}, f)


def load_views(folder, size, focal_equiv_mm):
    """The views captured at this size and focal length (a plain list: a file from before focal was recorded)."""
    path = focal_file("views", folder, size, focal_equiv_mm)
    if path is None:
        return []
    with open(path) as f:
        data = json.load(f)
    views = data if isinstance(data, list) else data["views"]
    return [np.asarray(v, np.float32).reshape(-1, 1, 2) for v in views]
