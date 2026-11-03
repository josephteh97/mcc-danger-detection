"""The calibrated phone lens and the camera built from it.

`FieldLens` holds OpenCV's camera matrix and distortion; it moves points between the real
(distorted) image and an ideal pinhole image with one focal length f = fx and the same principal
point. `FieldCamera` is a `world.camera.PinholeCamera` in that ideal image with any pose (roll
included), so the overlay and the measurements use the twin's one projection.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re

import cv2
import numpy as np

from world.camera import PinholeCamera

LEGACY_FOCAL_MM = 23                 # files from before the focal length was recorded: the main camera's
SHORT_M = 0.05                       # a short pole, for the density at one point
_ITER = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 100, 1e-10)


class FieldLens:
    def __init__(self, size, fx, fy, cx, cy, dist=(), rms=None, views=0, source="nominal", focal_equiv_mm=None):
        self.size = (int(size[0]), int(size[1]))
        self.fx, self.fy, self.cx, self.cy = float(fx), float(fy), float(cx), float(cy)
        self.dist = np.asarray(dist if len(dist) else np.zeros(5), dtype=np.float64).ravel()
        self.rms, self.views, self.source, self.focal_equiv_mm = rms, views, source, focal_equiv_mm
        self.K = np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1.0]])
        self.K_ideal = np.array([[self.fx, 0, self.cx], [0, self.fx, self.cy], [0, 0, 1.0]])

    @classmethod
    def pinhole(cls, size, fp):
        """A distortion-free lens of centre ratio fp (the nominal lens before calibration)."""
        return cls(size, fp, fp, size[0] / 2, size[1] / 2)

    @property
    def calibrated(self):
        return self.source != "nominal"

    def undistort(self, pts):
        """Real image pixels (N, 2) -> ideal pinhole pixels."""
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        if not np.any(self.dist):
            out = pts.reshape(-1, 2).copy()
            out[:, 1] = (out[:, 1] - self.cy) * self.fx / self.fy + self.cy
            return out
        return cv2.undistortPoints(pts, self.K, self.dist, R=None, P=self.K_ideal, criteria=_ITER).reshape(-1, 2)

    def in_fit(self, uv):
        """Whether an ideal pixel is inside the frame's corners: the only part of the image the
        calibration saw. Beyond them the distortion polynomial means nothing."""
        if not np.any(self.dist):
            return True
        corner = max(abs(self.size[0] - self.cx), self.cx) ** 2 + max(abs(self.size[1] - self.cy), self.cy) ** 2
        return (uv[0] - self.cx) ** 2 + (uv[1] - self.cy) ** 2 <= corner

    def distort(self, pts):
        """Ideal pinhole pixels (N, 2) -> real image pixels."""
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        n = np.column_stack([(pts[:, 0] - self.cx) / self.fx, (pts[:, 1] - self.cy) / self.fx, np.ones(len(pts))])
        out, _ = cv2.projectPoints(n, np.zeros(3), np.zeros(3), self.K, self.dist)
        return out.reshape(-1, 2)

    def to_dict(self):
        return {"size": list(self.size), "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
                "dist": self.dist.tolist(), "rms": self.rms, "views": self.views, "source": self.source,
                "focal_equiv_mm": self.focal_equiv_mm}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def _stem(kind, folder, size):
    return os.path.join(folder, f"{kind}_{size[0]}x{size[1]}")


def focal_path(kind, folder, size, focal_equiv_mm):
    """Where a calibration ("calib") or captured views ("views") of this size and focal length are saved."""
    return f"{_stem(kind, folder, size)}_{float(focal_equiv_mm):g}mm.json"


def _old_focal(path):
    """The focal length of a file from when each size had one file."""
    with open(path) as f:
        data = json.load(f)
    return float((data.get("focal_equiv_mm") if isinstance(data, dict) else None) or LEGACY_FOCAL_MM)


def focal_file(kind, folder, size, focal_equiv_mm):
    """The saved file for this size and focal length, or None: its own, else an older one made at it."""
    path = focal_path(kind, folder, size, focal_equiv_mm)
    if os.path.exists(path):
        return path
    old = _stem(kind, folder, size) + ".json"
    return old if os.path.exists(old) and _old_focal(old) == float(focal_equiv_mm) else None


def saved_focals(folder, size):
    """The focal lengths with a saved lens at this size."""
    stem = _stem("calib", folder, size)
    found = {float(m[1]) for p in glob.glob(glob.escape(stem) + "_*mm.json") if (m := re.search(r"_([0-9.]+)mm\.json$", p))}
    return sorted(found | ({_old_focal(stem + ".json")} if os.path.exists(stem + ".json") else set()))


def save(lens, folder, focal_equiv_mm):
    """Save the lens under the focal length it was calibrated at: other focal lengths keep theirs."""
    lens.focal_equiv_mm = focal_equiv_mm
    os.makedirs(folder, exist_ok=True)
    path = focal_path("calib", folder, lens.size, focal_equiv_mm)
    with open(path, "w") as f:
        json.dump(lens.to_dict(), f, indent=1)
    return path


def load(folder, size, focal_equiv_mm):
    """The lens calibrated at this stream size and focal length, or None."""
    path = focal_file("calib", folder, size, focal_equiv_mm)
    if path is None:
        return None
    with open(path) as f:
        lens = FieldLens.from_dict(json.load(f))
    lens.focal_equiv_mm = focal_equiv_mm
    return lens


# --------------------------------------------------------------------------- camera

def rotation(pitch_deg, heading_deg=0.0, roll_deg=0.0):
    """Rows right, down, forward in the ground frame (as PinholeCamera.R) for a camera pitched
    down by pitch, turned right of straight ahead by heading and rolled right side down by roll."""
    p, h, r = (math.radians(a) for a in (pitch_deg, heading_deg, roll_deg))
    f = np.array([math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), -math.sin(p)])
    right = np.cross(f, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(f, right)
    return np.stack([right * math.cos(r) + down * math.sin(r), down * math.cos(r) - right * math.sin(r), f])


def angles(R):
    """(pitch down, heading right, roll right side down) in degrees from PinholeCamera.R rows."""
    f = R[2]
    right0 = np.cross(f, [0.0, 0.0, 1.0])
    right0 /= np.linalg.norm(right0)
    down0 = np.cross(f, right0)
    return (math.degrees(math.asin(-f[2])), math.degrees(math.atan2(f[0], f[1])),
            math.degrees(math.atan2(R[0] @ down0, R[0] @ right0)))


class FieldCamera(PinholeCamera):
    """A PinholeCamera in the lens's ideal image, at any position and rotation."""

    preview = False                              # an assumed camera, not one solved from the cones

    def __init__(self, pos, R, lens):
        self.pos = np.asarray(pos, dtype=np.float64)
        self.R = np.asarray(R, dtype=np.float64)
        self.lens = lens
        self.width, self.height = lens.size
        self.fx, self.cx, self.cy = lens.fx, lens.cx, lens.cy
        self.K = lens.K_ideal

    @classmethod
    def posed(cls, lens, height_m, pitch_deg=0.0, heading_deg=0.0, roll_deg=0.0):
        return cls([0.0, 0.0, height_m], rotation(pitch_deg, heading_deg, roll_deg), lens)

    @property
    def pitch_deg(self):
        return angles(self.R)[0]

    @property
    def heading_deg(self):
        return angles(self.R)[1]

    def ground_distance(self, xy):
        """Horizontal distance from the point under the camera to ground point xy."""
        return math.hypot(xy[0] - self.pos[0], xy[1] - self.pos[1])

    def image_points(self, pts):
        """Ground-frame points (N, 3) -> real image pixels (distortion applied), and depth."""
        uv, z = self.project(pts)
        return self.lens.distort(uv), z

    def ground_of_pixel(self, u, v):
        """The ground point (x, y) seen at a real image pixel, or None above the horizon."""
        iu, iv = self.lens.undistort([[u, v]])[0]
        return self.ground_point(iu, iv)

    def pole_px(self, xy, length_m=1.0):
        """Pixel length in the real image of a vertical object standing at ground point xy."""
        uv, z = self.image_points([[xy[0], xy[1], 0.0], [xy[0], xy[1], length_m]])
        return float(np.linalg.norm(uv[1] - uv[0])) if np.all(z > 0) else float("nan")

    def px_per_m(self, xy):
        """Density at ground point xy: a 1 m pole's pixels or, if its top leaves the calibrated part of
        the image, the density just above the ground. None if the point is behind the camera."""
        x, y = xy
        uv, z = self.project([[x, y, 0.0], [x, y, 1.0]])
        if np.all(z > 0) and self.lens.in_fit(uv[1]):
            return self.pole_px(xy)
        uv, z = self.project([[x, y, 0.0], [x, y, SHORT_M]])
        if not np.all(z > 0):
            return None
        if self.lens.in_fit(uv[0]):
            return self.pole_px(xy, SHORT_M) / SHORT_M
        return float(np.linalg.norm(uv[1] - uv[0])) / SHORT_M      # outside the fit: no distortion
