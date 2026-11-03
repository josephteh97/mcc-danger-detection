"""The phone's pose from 4-8 taped cones: clicked cone bases and their ground positions ->
cv2.solvePnP with the calibrated lens -> height, pitch, roll, heading (as in tools/calibrate.py's
four markers, but solving the full pose)."""
from __future__ import annotations

import cv2
import numpy as np

from tools.fieldtest.lens import FieldCamera, angles

MIN_CONES = 4


def solve(cones_xy, pixels, lens):
    """Cones at ground (x, y) metres, clicked at real image pixels. -> dict with the FieldCamera,
    height_m, pitch_deg, heading_deg, roll_deg and each cone's reprojection error (px)."""
    g = np.asarray(cones_xy, dtype=np.float64).reshape(-1, 2)
    px = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    if len(g) < MIN_CONES or len(g) != len(px):
        raise ValueError(f"pose needs {MIN_CONES} to 8 cones with a click each ({len(g)} cones, {len(px)} clicks)")
    obj = np.column_stack([g, np.zeros(len(g))])
    ideal = lens.undistort(px)
    ok, rvec, tvec = cv2.solvePnP(obj, ideal, lens.K_ideal, None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        raise ValueError("solvePnP found no pose for these cones")
    rvec, tvec = cv2.solvePnPRefineLM(obj, ideal, lens.K_ideal, None, rvec, tvec)
    R = cv2.Rodrigues(rvec)[0]
    pos = (-R.T @ tvec).ravel()
    if pos[2] < 0:                               # the mirror solution under the ground
        raise ValueError("the pose came out below the ground: check the cone order and clicks")
    cam = FieldCamera(pos, R, lens)
    reproj = np.linalg.norm(cam.image_points(obj)[0] - px, axis=1)
    pitch, heading, roll = angles(R)
    return {"camera": cam, "solved": True, "height_m": float(pos[2]), "xy": [float(pos[0]), float(pos[1])],
            "pitch_deg": pitch, "heading_deg": heading, "roll_deg": roll,
            "reproj_px": [float(e) for e in reproj], "max_reproj_px": float(reproj.max())}


def summary(p):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items() if k != "camera"}
