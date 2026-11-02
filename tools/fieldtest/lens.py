"""The calibrated phone lens and the camera built from it.

`FieldLens` holds OpenCV's camera matrix and distortion; it moves points between the real
(distorted) image and an ideal pinhole image with one focal length f = fx and the same principal
point. `FieldCamera` is a `world.camera.PinholeCamera` in that ideal image with any pose (roll
included), so the overlay and the measurements use the twin's one projection.
"""
from __future__ import annotations

import json
import math
import os

import cv2
import numpy as np

from world.camera import PinholeCamera

_ITER = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 100, 1e-10)


class FieldLens:
    def __init__(self, size, fx, fy, cx, cy, dist=(), rms=None, views=0, source="nominal"):
        self.size = (int(size[0]), int(size[1]))
        self.fx, self.fy, self.cx, self.cy = float(fx), float(fy), float(cx), float(cy)
        self.dist = np.asarray(dist if len(dist) else np.zeros(5), dtype=np.float64).ravel()
        self.rms, self.views, self.source = rms, views, source
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

    def distort(self, pts):
        """Ideal pinhole pixels (N, 2) -> real image pixels."""
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        n = np.column_stack([(pts[:, 0] - self.cx) / self.fx, (pts[:, 1] - self.cy) / self.fx, np.ones(len(pts))])
        out, _ = cv2.projectPoints(n, np.zeros(3), np.zeros(3), self.K, self.dist)
        return out.reshape(-1, 2)

    def to_dict(self):
        return {"size": list(self.size), "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
                "dist": self.dist.tolist(), "rms": self.rms, "views": self.views, "source": self.source}

    @classmethod
    def from_dict(cls, d):
        return cls(d["size"], d["fx"], d["fy"], d["cx"], d["cy"], d.get("dist", ()), d.get("rms"),
                   d.get("views", 0), d.get("source", "calibrated"))


def calib_path(folder, size):
    return os.path.join(folder, f"calib_{size[0]}x{size[1]}.json")


def save(lens, folder):
    os.makedirs(folder, exist_ok=True)
    path = calib_path(folder, lens.size)
    with open(path, "w") as f:
        json.dump(lens.to_dict(), f, indent=1)
    return path


def load(folder, size):
    """The lens calibrated at this stream size, or None."""
    path = calib_path(folder, size)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return FieldLens.from_dict(json.load(f))


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

    def __init__(self, pos, R, lens):
        self.pos = np.asarray(pos, dtype=np.float64)
        self.R = np.asarray(R, dtype=np.float64)
        self.lens = lens
        self.width, self.height = lens.size
        self.fx, self.cx, self.cy = lens.fx, lens.cx, lens.cy
        self.hfov_deg = math.degrees(2 * math.atan((self.width / 2) / self.fx))
        self.look_at = self.pos + self.R[2]
        self.K = lens.K_ideal

    @classmethod
    def posed(cls, lens, height_m, pitch_deg=0.0, heading_deg=0.0, roll_deg=0.0, xy=(0.0, 0.0)):
        return cls([xy[0], xy[1], height_m], rotation(pitch_deg, heading_deg, roll_deg), lens)

    @property
    def pitch_deg(self):
        return angles(self.R)[0]

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
