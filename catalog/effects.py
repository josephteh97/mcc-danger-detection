"""What each product's specs change in the simulation, as numbers for the comparison table."""
from __future__ import annotations

import math

import numpy as np

from catalog import laser_class

DORI = [(250, "identify"), (125, "recognise"), (62, "observe"), (25, "detect")]
V_LAMBDA = {520: 0.710, 532: 0.885, 650: 0.107}
CLASS2_GREEN = 0.95 * 0.710               # the fitted Class 2 green module, for relative brightness
SPEAKER_HEIGHT_M, EAR_HEIGHT_M = 6.0, 1.6


def dori_level(ppm):
    for threshold, name in DORI:
        if ppm >= threshold:
            return name
    return "below detect"


def _camera(site, camera=None, mast=None):
    from world.camera import PinholeCamera
    camera = camera or site["fitted"]["camera"]
    w, h = camera["resolution_px"]
    return PinholeCamera.from_site(site, camera=camera, mast=mast, width=w, height=h)


def reference_point(site):
    r = site["reference_worker"]
    return np.array([r["xy"][0], r["xy"][1], r.get("chest_h_m", 1.2)])


def pixels_per_metre(site, camera=None, mast=None):
    """Horizontal pixels per metre on the worker at the reference position (native resolution)."""
    cam = _camera(site, camera, mast)
    d = cam.distance_to(reference_point(site))
    return cam.width / (2 * d * math.tan(math.radians(cam.hfov_deg) / 2)), d


def ring_points(site, buffer_m, n=360):
    """Points on the ring buffer_m from the pit edge (the pit polygon offset outward)."""
    from app.alarm import edge_distance
    pit = [tuple(p) for p in site["site"]["pit"]]
    pts = []
    for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
        d = np.array([math.cos(a), math.sin(a)])
        lo, hi = 0.0, 50.0                  # find the radius where the edge distance is buffer_m
        for _ in range(40):
            mid = (lo + hi) / 2
            if edge_distance(*(d * mid), pit) < buffer_m:
                lo = mid
            else:
                hi = mid
        pts.append(d * lo)
    return np.array(pts)


def ring_coverage(site, camera=None, mast=None, buffer_m=None):
    """Share of the warning ring that falls inside the camera picture."""
    buffer_m = buffer_m or site["zones"]["warn_buffer_m"]
    cam = _camera(site, camera, mast)
    ring = ring_points(site, buffer_m)
    uv, z = cam.project(np.hstack([ring, np.zeros((len(ring), 1))]))
    inside = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < cam.width) & (uv[:, 1] >= 0) & (uv[:, 1] < cam.height)
    return float(inside.mean())


def window_drops_pct(camera, preset):
    from world.weather import drop_coverage
    return 100.0 * drop_coverage(preset, camera)


def floodlight_lux(site, floodlight=None):
    """Lux on the worker: the lamp's lumens spread over the beam's footprint at the worker."""
    fl = floodlight or site["fitted"]["floodlight"]
    fd = site["floodlight"]
    lamp = np.array([fd["xy"][0], fd["xy"][1], fd["height_m"]])
    r = float(np.linalg.norm(reference_point(site) - lamp))
    return fl["lumens"] / (math.pi * (r * math.tan(math.radians(fl["beam_deg"] / 2))) ** 2)


def speaker_margin_db(site, speaker, preset):
    """Sound level at the worker above the weather's background noise."""
    xy = site["floodlight"]["xy"]
    ref = reference_point(site)
    r = math.dist((xy[0], xy[1], SPEAKER_HEIGHT_M), (ref[0], ref[1], EAR_HEIGHT_M))
    return speaker["spl_1m_db"] - 20 * math.log10(r) - preset.noise_db


def laser_brightness(laser):
    """Dot brightness relative to the fitted 0.95 mW green Class 2 module (eye-weighted)."""
    return laser["power_mw"] * V_LAMBDA.get(int(laser["wavelength_nm"]), 0.5) / CLASS2_GREEN


def laser_summary(laser):
    cls = laser_class(laser["power_mw"], laser["wavelength_nm"])
    return {"class": cls, "class2_ok": cls in ("1", "2"), "brightness": laser_brightness(laser)}


def with_product(site, category, name):
    """A copy of the site with one product swapped (everything else as fitted)."""
    import copy
    from catalog import load_product
    s = copy.copy(site)
    s["fitted"] = dict(site["fitted"])
    s["fitted"][category] = load_product(category, name)
    return s


def daily_energy_wh(site):
    from devices.power_model import PowerConfig
    return PowerConfig.from_site(site).daily_load_wh()


def pole_cost_sgd(site):
    return sum(p["price_sgd"] for p in site["fitted"].values()) + site.get("power", {}).get("other_hardware_sgd", 0)


def battery_low_pct(site, sun_factor, days=3):
    from devices.power_model import PowerConfig, lowest_charge
    return lowest_charge(PowerConfig.from_site(site), sun_factor, days)
