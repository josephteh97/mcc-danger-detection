"""Sixteen weather and lighting presets and the image effects that model them.

The visibilities, light levels, sun factors and sway values are assumptions; calibrate
them against Meteorological Service Singapore records and a week of site footage.
Sun factors are solved from the guide's 3-day battery table (see devices/power_model.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

KOSCHMIEDER = 3.912          # ln(1/0.02): visibility is where contrast drops to 2%


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    visibility_m: float = 20000.0
    airlight: tuple = (205, 205, 200)    # BGR colour of scattered light
    light: float = 1.0                   # scene light relative to a sunny day
    sun_factor: float = 1.0              # solar input for the power model
    wind_ms: float = 2.0
    rain_mm_h: float = 0.0
    window_drops_pct: float = 0.0        # share of an unhooded (dome) window hidden by drops
    window_fog: float = 0.0              # 0..1 condensation on the window
    wet_ground: bool = False
    night: bool = False
    floodlight: bool = True              # night only: floodlight on (else camera IR only)
    lightning: bool = False
    glare: float = 0.0                   # 0..1 low sun near the lens
    mud: bool = False
    noise: float = 0.0                   # sensor noise, grey levels
    noise_db: float = 65.0               # background sound level at the worker
    events: tuple = ()                   # storm events for the scenario runner


PRESETS = {p.name: p for p in [
    Preset("clear", "Sunny, visibility 20 km"),
    Preset("overcast", "Thick cloud", visibility_m=10000, light=0.6, sun_factor=0.44, wind_ms=4),
    Preset("light_rain", "2.5 mm/h, a few window drops", visibility_m=4000, light=0.5,
           sun_factor=0.33, wind_ms=4, rain_mm_h=2.5, window_drops_pct=0.3, wet_ground=True,
           noise_db=68),
    Preset("tropical_downpour", "80 mm/h, visibility 400 m, many drops", visibility_m=400,
           light=0.36, sun_factor=0.2, wind_ms=6, rain_mm_h=80, window_drops_pct=2.5,
           wet_ground=True, noise_db=80),
    Preset("thunderstorm", "50 mm/h, lightning, 12 m/s wind, surge and 4G drop",
           visibility_m=600, light=0.31, sun_factor=0.25, wind_ms=12, rain_mm_h=50,
           window_drops_pct=2.0, wet_ground=True, lightning=True, noise_db=83,
           events=("power_surge", "4g_drop_30s")),
    Preset("regional_haze", "Transboundary smoke haze, visibility 1.5 km", visibility_m=1500,
           airlight=(150, 172, 190), light=0.69, sun_factor=0.594),
    Preset("dust_or_smoke", "Earthworks dust or nearby burning, visibility 120 m",
           visibility_m=120, airlight=(120, 150, 178), light=0.78, sun_factor=0.69),
    Preset("morning_mist", "Visibility 200 m, slightly fogged window", visibility_m=200,
           light=0.95, sun_factor=0.5, window_fog=0.02),
    Preset("dense_fog", "Visibility 50 m", visibility_m=50, light=0.76, sun_factor=0.35),
    Preset("humid_lens", "Fogged window only", window_fog=0.2, sun_factor=0.8),
    Preset("night_clear", "Night with floodlight", night=True, noise=5.0),
    Preset("night_no_floodlight", "Night, camera infrared only", night=True, floodlight=False,
           noise=7.0),
    Preset("night_rain", "Night, 25 mm/h, drops, sensor noise", night=True, light=0.8, rain_mm_h=25,
           window_drops_pct=1.0, wet_ground=True, noise=7.0, wind_ms=5, noise_db=74),
    Preset("low_sun_glare", "Morning or evening sun near the lens", glare=1.0),
    Preset("mud_splash", "Mud over the window's lower-left corner", mud=True),
    Preset("strong_wind", "15 m/s gusts swaying the mast", wind_ms=15, sun_factor=0.69,
           noise_db=72),
]}

NAMES = list(PRESETS)


def get_preset(name):
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(f"unknown weather preset '{name}'; valid presets: {', '.join(NAMES)}") from None


# --------------------------------------------------------------------------- effects

def miss_factor(preset):
    """How much the weather multiplies the detector's pixel-height miss rate (1.0 on a clear day):
    fog and haze, rain, a fogged or wet window, and night without the floodlight."""
    f = 1.0 + max(0.0, (500.0 - preset.visibility_m) / 500.0) + preset.rain_mm_h / 50.0
    f += 0.5 * preset.window_fog + preset.window_drops_pct / 100.0 + 0.5 * preset.glare
    if preset.night and not preset.floodlight:
        f += 0.5
    return round(f, 3)


def transmission(dist_m, visibility_m):
    """Koschmieder: fraction of scene light that survives the path through the air."""
    return np.exp(-KOSCHMIEDER * np.asarray(dist_m, dtype=np.float32) / float(visibility_m))


def scatter(img, dist_m, preset):
    """Blend toward the airlight with distance (fog, mist, haze, dust, smoke, rain)."""
    t = transmission(np.minimum(dist_m, 1e5), preset.visibility_m)[..., None]
    air = np.array(preset.airlight, dtype=np.float32) * (0.35 if preset.night else min(1.0, preset.light + 0.15))
    return img * t + air * (1.0 - t)


def drop_coverage(preset, camera):
    """Share of the window hidden by drops for this camera (a hood keeps ~56% of drops off)."""
    hooded = camera.get("sun_hood", False) and camera.get("form") != "dome"
    return preset.window_drops_pct * (0.44 if hooded else 1.0) / 100.0


def make_drop_mask(h, w, coverage, rng):
    """Static drops stuck on the housing window, covering `coverage` of the image."""
    mask = np.zeros((h, w), np.float32)
    if coverage <= 0:
        return mask
    target = coverage * h * w
    area = 0.0
    while area < target:
        r = int(rng.uniform(4, 14))
        cx, cy = int(rng.uniform(0, w)), int(rng.uniform(0, h))
        cv2.circle(mask, (cx, cy), r, 1.0, -1, lineType=cv2.LINE_AA)
        area = float((mask > 0.5).sum())
    return cv2.GaussianBlur(mask, (5, 5), 1.5)


def apply_drops(img, mask):
    if not mask.any():
        return img
    blurred = cv2.GaussianBlur(img, (0, 0), 6)
    m = mask[..., None]
    return img * (1 - m) + (blurred * 0.8 + 35) * m


def make_rain_layers(h, w, preset, rng, count=6):
    """Pre-drawn falling-streak layers slanted by the wind, cycled frame to frame."""
    if preset.rain_mm_h <= 0:
        return []
    n = int(min(2500, 60 + preset.rain_mm_h * 22))
    slant = min(0.6, preset.wind_ms / 25.0)
    layers = []
    for _ in range(count):
        layer = np.zeros((h, w), np.float32)
        for _ in range(n):
            x, y = rng.uniform(-60, w), rng.uniform(-40, h)
            length = rng.uniform(12, 30)
            cv2.line(layer, (int(x), int(y)), (int(x + slant * length), int(y + length)),
                     float(rng.uniform(0.25, 0.6)), 1, lineType=cv2.LINE_AA)
        layers.append(layer)
    return layers


def apply_rain(img, layer, preset):
    if layer is None:
        return img
    level = 150.0 if preset.night else 215.0
    a = layer[..., None]
    return img * (1 - a) + level * a


def apply_window_fog(img, strength):
    """Condensation on the window: blurs and whitens the whole image."""
    if strength <= 0:
        return img
    blurred = cv2.GaussianBlur(img, (0, 0), 3 + 12 * strength)
    return blurred * (1 - strength) + 235.0 * strength


def make_glare(h, w, rng):
    """Low sun just outside the top-right of the picture: veiling glare plus flare spots."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sx, sy = w * 1.02, -h * 0.08
    d = np.hypot(xx - sx, yy - sy) / w
    veil = 150.0 * np.exp(-d * 2.2)
    flare = np.zeros((h, w), np.float32)
    for k, frac in enumerate((0.35, 0.55, 0.8)):
        cx, cy = int(sx + (w / 2 - sx) * frac * 2), int(sy + (h / 2 - sy) * frac * 2)
        cv2.circle(flare, (cx, cy), int(18 + 14 * k), 70.0, -1, lineType=cv2.LINE_AA)
    flare = cv2.GaussianBlur(flare, (0, 0), 4)
    return (veil + flare)[..., None]


def apply_glare(img, overlay, camera):
    """The sun in view darkens the scene; true WDR recovers most of it."""
    wdr = camera.get("true_wdr_db", 0) >= 100
    exposure = 0.9 if wdr else 0.6
    return img * exposure + overlay * (0.5 if wdr else 1.0)


def make_mud(h, w, rng):
    """A mud splash over the window's lower-left corner (alpha mask)."""
    mask = np.zeros((h, w), np.float32)
    for _ in range(40):
        cx = int(abs(rng.normal(0, w * 0.12)))
        cy = int(h - abs(rng.normal(0, h * 0.18)))
        cv2.circle(mask, (cx, cy), int(rng.uniform(8, 40)), float(rng.uniform(0.6, 1.0)), -1)
    return np.clip(cv2.GaussianBlur(mask, (0, 0), 6), 0, 0.95)


def apply_mud(img, mask):
    m = mask[..., None]
    return img * (1 - m) + np.array([40, 62, 82], np.float32) * m


def sway_matrix(t, preset, mast, w, h, fx):
    """Mast sway in wind: small pitch/yaw/roll oscillation of the whole image."""
    amp_deg = mast.get("sway_deg_per_ms2", 0.0011) * preset.wind_ms ** 2
    if amp_deg < 0.01:
        return None
    gust = 0.6 + 0.4 * np.sin(2 * np.pi * 0.11 * t)
    yaw = amp_deg * gust * np.sin(2 * np.pi * 0.9 * t)
    pitch = amp_deg * gust * np.sin(2 * np.pi * 0.7 * t + 1.3)
    roll = 0.3 * amp_deg * np.sin(2 * np.pi * 0.5 * t)
    dx = fx * np.tan(np.radians(yaw))
    dy = fx * np.tan(np.radians(pitch))
    M = cv2.getRotationMatrix2D((w / 2, h / 2), roll, 1.0)
    M[0, 2] += dx
    M[1, 2] += dy
    return M


def apply_sway(img, M):
    if M is None:
        return img
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def wind_blur(img, preset):
    """Gust shake during the exposure smears the picture a little."""
    k = int(preset.wind_ms / 3)
    if k < 2:
        return img
    kernel = np.zeros((k * 2 + 1, k * 2 + 1), np.float32)
    kernel[k, :] = 1.0
    kernel[:, k] = 0.5
    return cv2.filter2D(img, -1, kernel / kernel.sum())
