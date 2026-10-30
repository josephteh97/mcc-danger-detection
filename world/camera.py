"""Pinhole camera on the mast: projection, ground rays and the calibration homography.

Ground frame: metres, x east, y north, z up. Camera frame (OpenCV): x right, y down, z forward.
"""
from __future__ import annotations

import math

import cv2
import numpy as np


class PinholeCamera:
    def __init__(self, pos, look_at, hfov_deg, width, height):
        self.pos = np.asarray(pos, dtype=np.float64)
        self.look_at = np.asarray(look_at, dtype=np.float64)
        self.hfov_deg, self.width, self.height = float(hfov_deg), int(width), int(height)
        f = self.look_at - self.pos
        f /= np.linalg.norm(f)
        r = np.cross(f, [0.0, 0.0, 1.0])
        r /= np.linalg.norm(r)
        d = np.cross(f, r)
        self.R = np.stack([r, d, f])                      # rows: right, down, forward
        self.fx = (self.width / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)
        self.cx, self.cy = self.width / 2.0, self.height / 2.0
        self.K = np.array([[self.fx, 0, self.cx], [0, self.fx, self.cy], [0, 0, 1.0]])

    @classmethod
    def from_site(cls, site, camera=None, mast=None, width=None, height=None):
        """Camera at the fitted mast's height on the site's mast position, aimed at the pit. A site
        may set the camera's own `height_m` (a stand set to a height) and `tilt_deg` (the optical
        axis's angle below horizontal, along the bearing to `look_at`)."""
        camera = camera or site["fitted"]["camera"]
        mast = mast or site["fitted"]["mast"]
        sc = site["camera"]
        xy = np.asarray(sc["xy"], dtype=np.float64)
        look = np.asarray(sc.get("look_at", [0.0, 0.0]), dtype=np.float64)
        h = sc.get("height_m", mast["height_m"])
        if mast["id"] != site["products"]["mast"]:       # a swapped mast stands at its own standoff
            bearing = (xy - look) / np.linalg.norm(xy - look)
            xy = look + bearing * mast["standoff_m"]
            h = mast["height_m"]
        if "tilt_deg" in sc:                             # aim point on the ground set by the tilt
            fwd = (look - xy) / np.linalg.norm(look - xy)
            look = xy + fwd * h / math.tan(math.radians(sc["tilt_deg"]))
        render = sc.get("render", {})
        return cls([xy[0], xy[1], h], [look[0], look[1], 0.0], camera["hfov_deg"],
                   width or render.get("width", 1280), height or render.get("height", 720))

    @property
    def vfov_deg(self):
        return math.degrees(2 * math.atan((self.height / 2.0) / self.fx))

    def project(self, pts):
        """Project ground-frame points (N, 3) to pixels (N, 2); also returns camera depth."""
        pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
        pc = (pts - self.pos) @ self.R.T
        z = pc[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.fx * pc[:, 0] / z + self.cx
            v = self.fx * pc[:, 1] / z + self.cy
        return np.stack([u, v], axis=1), z

    def rays(self, u, v):
        """Unit ray directions in the ground frame for pixel arrays u, v."""
        dc = np.stack([(u - self.cx) / self.fx, (v - self.cy) / self.fx, np.ones_like(u)], axis=-1)
        dw = dc @ self.R
        return dw / np.linalg.norm(dw, axis=-1, keepdims=True)

    def ground_point(self, u, v):
        """Where the ray through pixel (u, v) meets the ground, or None above the horizon."""
        d = self.rays(np.array([u], dtype=np.float64), np.array([v], dtype=np.float64))[0]
        if d[2] >= -1e-9:
            return None
        s = -self.pos[2] / d[2]
        return float(self.pos[0] + s * d[0]), float(self.pos[1] + s * d[1])

    def ground_maps(self):
        """Per-pixel ground x, y and slant distance (inf where the ray misses the ground)."""
        vv, uu = np.mgrid[0:self.height, 0:self.width].astype(np.float64)
        d = self.rays(uu + 0.5, vv + 0.5)
        hit = d[..., 2] < -1e-6
        s = np.where(hit, -self.pos[2] / np.where(hit, d[..., 2], -1.0), np.inf)
        gx = self.pos[0] + s * d[..., 0]
        gy = self.pos[1] + s * d[..., 1]
        return gx.astype(np.float32), gy.astype(np.float32), s.astype(np.float32)

    def ground_to_image_homography(self):
        """3x3 H mapping ground (x, y, 1) to pixels, for warping a top-down texture."""
        P = self.K @ np.hstack([self.R, (-self.R @ self.pos)[:, None]])
        return P[:, [0, 1, 3]]

    def ground_axes(self):
        """Unit ground vectors for 'up the picture' (away from the camera) and 'right'."""
        fwd = self.R[2, :2] / np.linalg.norm(self.R[2, :2])
        right = self.R[0, :2] / np.linalg.norm(self.R[0, :2])
        return fwd, right

    def distance_to(self, xyz):
        return float(np.linalg.norm(np.asarray(xyz, dtype=np.float64) - self.pos))


def image_to_ground_homography(camera, ground_points):
    """Calibrate as on site: four ground points with known positions, their pixels in the
    camera image, and the fitted image-to-ground homography the app uses."""
    g = np.asarray(ground_points, dtype=np.float64)
    pix, depth = camera.project(np.hstack([g, np.zeros((len(g), 1))]))
    if np.any(depth <= 0) or np.any(pix[:, 0] < 0) or np.any(pix[:, 0] >= camera.width) \
            or np.any(pix[:, 1] < 0) or np.any(pix[:, 1] >= camera.height):
        raise ValueError("a calibration point is outside the camera image")
    H, _ = cv2.findHomography(pix.astype(np.float32), g.astype(np.float32), 0)
    return H, pix
