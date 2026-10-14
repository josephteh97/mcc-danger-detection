"""World simulator: the site, its workers and what the pole camera sees.

    python3 world/world.py --fps 15 --truth dashboard:9100,192.168.10.2:9100 --weather clear \
        | ffmpeg -f rawvideo -pix_fmt bgr24 -s 1280x720 -r 15 -i - ... rtsp://192.168.10.20:8554/stream1

Writes raw 1280x720 BGR frames to stdout, sends per-frame ground truth (true positions and
boxes) as JSON over UDP, listens for control messages (keys, weather, scenarios) and draws
the laser dot where the arm's beam actually lands.
"""
from __future__ import annotations

import math
import os
import sys

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.alarm import edge_distance                                  # noqa: E402
from app.links import beam_ground_point                              # noqa: E402
from world import weather as wx                                      # noqa: E402
from world.camera import PinholeCamera, image_to_ground_homography   # noqa: E402
from world.scene import Scene                                        # noqa: E402

TEX_PPM, TEX_EXTENT = 32, 30.0          # ground texture: 32 px/m over +-30 m
MUD, OUTSIDE = (62, 88, 108), (78, 104, 92)
WALL_H = 2.4
# person: (z0, r0, z1, r1, BGR) stacked frustums; the footprint radius sets the foot-point bias
BODY = [(0.0, 0.28, 0.85, 0.20, (70, 45, 38)),        # legs, dark trousers
        (0.85, 0.24, 1.45, 0.26, (40, 230, 215)),     # hi-vis vest
        (1.47, 0.11, 1.64, 0.11, (120, 150, 190)),    # face
        (1.60, 0.15, 1.78, 0.13, (235, 240, 240))]    # white helmet
V_LAMBDA = {520: 0.710, 532: 0.885, 650: 0.107}       # eye sensitivity for the dot's brightness
NIGHT_GAIN, IR_GAIN = 0.022, 0.0052


def _clip_near(pc, near=0.2):
    """Clip a camera-space polygon against the plane z = near (Sutherland-Hodgman)."""
    out = []
    for i in range(len(pc)):
        a, b = pc[i], pc[(i + 1) % len(pc)]
        ina, inb = a[2] >= near, b[2] >= near
        if ina:
            out.append(a)
        if ina != inb:
            s = (near - a[2]) / (b[2] - a[2])
            out.append(a + s * (b - a))
    return np.array(out)


class World:
    def __init__(self, site, weather="clear", seed=0, npcs=0, scenario="idle"):
        self.site, self.seed = site, seed
        self.rng = np.random.default_rng(seed)
        s = site["site"]
        self.pit = [tuple(p) for p in s["pit"]]
        self.scene = Scene(s["boundary"], self.pit, seed=seed)
        self.scene.npcs = npcs
        self.cam = PinholeCamera.from_site(site)
        self.W, self.H = self.cam.width, self.cam.height
        self.arm_cfg = site["arm"]
        self.arm = (0.0, 90.0, False)          # pan, tilt, laser on: fed from the arm state
        self._cache, self._frame = {}, 0
        self._flash_until = -1.0
        self.set_weather(weather)
        self.scene.reset(scenario)

    # ------------------------------------------------------------------ controls
    def set_weather(self, name):
        self.preset = wx.get_preset(name)

    def homography(self):
        H, _ = image_to_ground_homography(self.cam, self.site["calibration"]["points"])
        return H

    def step(self, dt):
        up, right = self.cam.ground_axes()
        self.scene.step(dt, up, right)
        self._frame += 1

    @property
    def t(self):
        return self.scene.t

    # ------------------------------------------------------------------ static layers
    def _cached(self, key, make):
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def _maps(self):
        return self._cached(("maps",), self.cam.ground_maps)

    def _texture(self):
        def make():
            n = int(2 * TEX_EXTENT * TEX_PPM)
            rng = np.random.default_rng(self.seed + 7)
            tex = np.empty((n, n, 3), np.float32)
            tex[:] = MUD
            noise = cv2.GaussianBlur(rng.normal(0, 1, (n // 8, n // 8)).astype(np.float32), (0, 0), 2)
            tex *= (1 + 0.12 * cv2.resize(noise, (n, n)))[..., None]
            tex += rng.normal(0, 4, (n, n, 1)).astype(np.float32)

            def px(x, y):
                return int((x + TEX_EXTENT) * TEX_PPM), int((TEX_EXTENT - y) * TEX_PPM)
            for k in range(6):                         # tyre tracks
                y0 = rng.uniform(-8, 8)
                cv2.line(tex, px(-12, y0), px(12, y0 + rng.uniform(-3, 3)), (48, 70, 88), 9)
            (bx0, by0), (bx1, by1) = np.min(self.site["site"]["boundary"], 0), np.max(self.site["site"]["boundary"], 0)
            outside = np.ones((n, n), np.uint8)
            cv2.rectangle(outside, px(bx0, by1), px(bx1, by0), 0, -1)
            tex[outside.astype(bool)] = OUTSIDE
            pit = np.array([px(x, y) for x, y in self.pit], np.int32)
            cv2.fillPoly(tex, [pit], (52, 66, 80))
            inner = np.array([px(x * 0.9, y * 0.85) for x, y in self.pit], np.int32)
            cv2.fillPoly(tex, [inner], (22, 26, 30))
            return tex
        return self._cached(("tex",), make)

    def _light_map(self, preset):
        """Scene light per pixel relative to a sunny day (and the same for the workers)."""
        f = self.site["fitted"]
        if not preset.night:
            return None
        gx, gy, dist = self._maps()
        ground = np.isfinite(dist)
        if preset.floodlight:
            with np.errstate(invalid="ignore", over="ignore"):
                lux = np.nan_to_num(self.lux_at(gx, gy, 0.0), nan=0.0, posinf=0.0)
            return np.where(ground, np.clip(0.035 + NIGHT_GAIN * lux, 0, 1.2), 0.035).astype(np.float32)
        rng_m = np.where(ground, np.maximum(dist, 1.0), 1e4)
        return np.clip(0.012 + IR_GAIN * (f["camera"]["ir_range_m"] / rng_m) ** 2, 0, 1.0).astype(np.float32)

    def lux_at(self, x, y, z):
        """Floodlight illuminance (lux) at ground points: lumens spread over the beam footprint."""
        fl, fd = self.site["fitted"]["floodlight"], self.site["floodlight"]
        lx, ly, lh = fd["xy"][0], fd["xy"][1], fd["height_m"]
        ax, ay = fd.get("aim", [0.0, 0.0])
        vx, vy, vz = np.asarray(x) - lx, np.asarray(y) - ly, np.asarray(z) - lh
        r = np.sqrt(vx * vx + vy * vy + vz * vz)
        axis = np.array([ax - lx, ay - ly, -lh])
        axis /= np.linalg.norm(axis)
        cosang = (vx * axis[0] + vy * axis[1] + vz * axis[2]) / np.maximum(r, 1e-6)
        half = math.radians(fl["beam_deg"] / 2)
        ang = np.arccos(np.clip(cosang, -1, 1))
        profile = np.clip((half * 1.15 - ang) / (half * 0.3), 0, 1)
        return fl["lumens"] / (math.pi * (r * math.tan(half)) ** 2) * profile

    def _background(self, preset):
        f = self.site["fitted"]
        key = ("bg", preset.name, f["camera"]["id"], f["mast"]["id"], f["floodlight"]["id"])

        def make():
            gx, gy, dist = self._maps()
            G = np.array([[1 / TEX_PPM, 0, -TEX_EXTENT], [0, -1 / TEX_PPM, TEX_EXTENT], [0, 0, 1]])
            M = self.cam.ground_to_image_homography() @ G
            img = cv2.warpPerspective(self._texture(), M, (self.W, self.H), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_REPLICATE)
            sky = ~np.isfinite(dist)
            img[sky] = (215, 200, 185)
            self._draw_walls(img)
            if preset.wet_ground:
                img[~sky] = img[~sky] * 0.8 + np.array([22, 18, 14], np.float32)   # wet sheen
            L = self._light_map(preset)
            if L is not None:
                img = img * (L * preset.light)[..., None]
                if not preset.floodlight:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[..., None].repeat(3, axis=2)
            else:
                img = img * preset.light
            return wx.scatter(img, np.minimum(dist, 60.0), preset).astype(np.float32)
        return self._cached(key, make)

    def _draw_walls(self, img):
        (x0, y0), (x1, y1) = np.min(self.site["site"]["boundary"], 0), np.max(self.site["site"]["boundary"], 0)
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for i in range(4):
            (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
            quad = np.array([[ax, ay, 0], [bx, by, 0], [bx, by, WALL_H], [ax, ay, WALL_H]], float)
            pc = _clip_near((quad - self.cam.pos) @ self.cam.R.T)
            if len(pc) < 3:
                continue
            uv = np.stack([self.cam.fx * pc[:, 0] / pc[:, 2] + self.cam.cx,
                           self.cam.fx * pc[:, 1] / pc[:, 2] + self.cam.cy], 1)
            cv2.fillPoly(img, [np.round(uv).astype(np.int32)], (170, 150, 120), lineType=cv2.LINE_AA)

    # ------------------------------------------------------------------ dynamic layers
    def _person_polys(self, w):
        polys = []
        for z0, r0, z1, r1, colour in BODY:
            a = np.linspace(0, 2 * np.pi, 16, endpoint=False)
            ring0 = np.stack([w.x + r0 * np.cos(a), w.y + r0 * np.sin(a), np.full_like(a, z0)], 1)
            ring1 = np.stack([w.x + r1 * np.cos(a), w.y + r1 * np.sin(a), np.full_like(a, z1)], 1)
            uv, z = self.cam.project(np.vstack([ring0, ring1]))
            if np.any(z <= 0.2):
                return None
            polys.append((cv2.convexHull(np.round(uv * 4).astype(np.int32)), colour))
        return polys

    def _worker_light(self, w, preset):
        if not preset.night:
            return preset.light
        if preset.floodlight:
            return preset.light * float(np.clip(0.035 + NIGHT_GAIN * self.lux_at(w.x, w.y, 1.2), 0, 1.2))
        d = self.cam.distance_to([w.x, w.y, 1.2])
        return float(np.clip(0.012 + IR_GAIN * (self.site["fitted"]["camera"]["ir_range_m"] / d) ** 2, 0, 1.0))

    def _dot_pixel(self):
        pan, tilt, on = self.arm
        if not on:
            return None
        a = self.arm_cfg
        g = beam_ground_point(a["xy"], a["heading_deg"], a["pivot_h_m"], pan, tilt)
        if g is None:
            return None
        uv, z = self.cam.project([[g[0], g[1], 0.0]])
        if z[0] <= 0:
            return None
        return int(round(uv[0, 0])), int(round(uv[0, 1]))

    def render(self, measure=False):
        """Render the camera frame. Returns (frame uint8 BGR, info) where info has the
        ground-truth boxes, visibility and (if measure) each worker's pixel mask."""
        preset, cam, f = self.preset, self.cam, self.site["fitted"]
        img = self._background(preset).copy()
        label = np.zeros((self.H, self.W), np.uint8)
        active = [w for w in self.scene.workers if w.active(self.t)]
        active.sort(key=lambda w: -cam.distance_to([w.x, w.y, 1.0]))
        boxes, areas = {}, {}
        for idx, w in enumerate(active, start=1):
            polys = self._person_polys(w)
            if polys is None:
                continue
            d = cam.distance_to([w.x, w.y, 1.0])
            t = float(wx.transmission(d, preset.visibility_m))
            air = np.array(preset.airlight, np.float32) * (0.35 if preset.night else min(1.0, preset.light + 0.15))
            light = self._worker_light(w, preset)
            mask = np.zeros((self.H, self.W), np.uint8)
            for hull, colour in polys:
                c = np.array(colour, np.float32)
                if preset.night and not preset.floodlight:
                    c = np.full(3, c @ np.array([0.114, 0.587, 0.299], np.float32))
                c = c * light * t + air * (1 - t)
                cv2.fillConvexPoly(img, hull, c.tolist(), lineType=cv2.LINE_AA, shift=2)
                cv2.fillConvexPoly(mask, hull, 1, shift=2)
            label[mask > 0] = idx
            ys, xs = np.nonzero(mask)
            if len(xs):
                boxes[w.id] = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                areas[w.id] = (idx, len(xs))
        dot = self._dot_pixel()
        if dot is not None:
            laser = f["laser"]
            strength = laser["power_mw"] * V_LAMBDA.get(int(laser["wavelength_nm"]), 0.5) / (0.95 * 0.71)
            alpha = min(1.0, (0.55 if not preset.night else 1.0) * strength)
            colour = (60, 255, 60) if laser["wavelength_nm"] < 600 else (60, 60, 255)
            glow = img.copy()
            cv2.circle(glow, dot, 4, colour, -1, lineType=cv2.LINE_AA)
            cv2.circle(glow, dot, 2, (230, 255, 230), -1, lineType=cv2.LINE_AA)
            img = img * (1 - alpha) + glow * alpha
        img = self._effects(img)
        M = wx.sway_matrix(self.t, preset, f["mast"], self.W, self.H, cam.fx)
        img = wx.apply_sway(img, M)
        if M is not None:
            img = wx.wind_blur(img, preset)
        frame = np.clip(img, 0, 255).astype(np.uint8)
        if M is not None:
            label = cv2.warpAffine(label, M, (self.W, self.H), flags=cv2.INTER_NEAREST)
        info = {"boxes": {}, "visible": {}, "masks": {}}
        for wid, (idx, area) in areas.items():
            vis = float(np.count_nonzero(label == idx)) / area
            box = boxes[wid]
            if M is not None:
                pts = np.array([[box[0], box[1], 1], [box[2], box[3], 1]], float) @ M.T
                box = [int(round(pts[0, 0])), int(round(pts[0, 1])), int(round(pts[1, 0])), int(round(pts[1, 1]))]
            info["boxes"][wid] = box
            info["visible"][wid] = vis
            if measure:
                info["masks"][wid] = label == idx
        return frame, info

    def _effects(self, img):
        p, cam = self.preset, self.site["fitted"]["camera"]
        key = (p.name, cam["id"])
        rain = self._cached(("rain",) + key, lambda: wx.make_rain_layers(self.H, self.W, p, np.random.default_rng(self.seed + 1)))
        if rain:
            img = wx.apply_rain(img, rain[self._frame % len(rain)], p)
        if p.lightning:
            if self.t >= self._flash_until and self.rng.random() < 0.004:
                self._flash_until = self.t + 0.12
            if self.t < self._flash_until:
                img = img * 0.35 + 255 * 0.65
        if p.glare > 0:
            img = wx.apply_glare(img, self._cached(("glare",), lambda: wx.make_glare(self.H, self.W, self.rng)), cam)
        img = wx.apply_window_fog(img, p.window_fog)
        drops = self._cached(("drops",) + key, lambda: wx.make_drop_mask(
            self.H, self.W, wx.drop_coverage(p, cam), np.random.default_rng(self.seed + 2)))
        img = wx.apply_drops(img, drops)
        if p.mud:
            img = wx.apply_mud(img, self._cached(("mud",), lambda: wx.make_mud(self.H, self.W, np.random.default_rng(self.seed + 3))))
        if p.noise > 0:
            noise = self._cached(("noise",), lambda: [np.random.default_rng(self.seed + 4 + i).normal(
                0, 1, (self.H, self.W, 1)).astype(np.float32) for i in range(4)])
            img = img + noise[self._frame % 4] * p.noise
        return img

    # ------------------------------------------------------------------ ground truth
    def truth(self, info, wall_t):
        f = self.site["fitted"]
        workers = []
        for w in self.scene.workers:
            if not w.active(self.t):
                continue
            workers.append({"id": w.id, "x": round(w.x, 3), "y": round(w.y, 3),
                            "edge_m": round(edge_distance(w.x, w.y, self.pit), 3),
                            "box": info["boxes"].get(w.id), "visible": round(info["visible"].get(w.id, 0.0), 3),
                            "controlled": w.controlled})
        return {"t": wall_t, "sim_t": round(self.t, 3), "frame": self._frame, "weather": self.preset.name,
                "scenario": self.scene.scenario, "workers": workers,
                "arm": {"pan": self.arm[0], "tilt": self.arm[1], "laser": self.arm[2]},
                "camera": f["camera"]["id"], "size": [self.W, self.H]}

    def contrast(self, info, frame, wid):
        """Worker contrast: grey-level difference between the worker and the ground around them."""
        mask = info["masks"].get(wid)
        if mask is None or not mask.any():
            return 0.0
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        ring = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~mask
        for other, m in info["masks"].items():
            if other != wid:
                ring &= ~m
        return abs(float(grey[mask].mean()) - float(grey[ring].mean()))


if __name__ == "__main__":
    from world.stream import main
    main()
