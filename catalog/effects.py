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
    from catalog import fitted_products
    return sum(p["price_sgd"] for p in fitted_products(site)) + site.get("power", {}).get("other_hardware_sgd", 0)


def battery_low_pct(site, sun_factor, days=3):
    from devices.power_model import PowerConfig, lowest_charge
    return lowest_charge(PowerConfig.from_site(site), sun_factor, days)


# --------------------------------------------------------------------------- v11 plan totals

def plan_totals(site, include_legacy=False):
    """Cost of the v11 pole per power plan: the common parts, plus each plan's battery, panels and
    own parts, the laser controller and other hardware. Legacy products are left out unless
    `include_legacy` (identification switched back on). -> {plan: {"total_sgd", "items"}}"""
    from catalog import fitted_products, load_product
    plans = site.get("power_plans") or {}
    plan_ids = {n for p in plans.values() for n in [p.get("battery"), p.get("solar"), *p.get("parts", [])] if n}
    common = [(p["id"], p["price_sgd"]) for p in fitted_products(site)
              if p["id"] not in plan_ids and p["id"] not in (site["fitted"]["battery"]["id"], site["fitted"]["solar"]["id"])
              and (include_legacy or not p.get("legacy"))]
    lc = site.get("laser_controller") or {}
    if lc.get("price_sgd"):
        common.append(("laser_controller", lc["price_sgd"]))
    other = site.get("power", {}).get("other_hardware_sgd", 0)
    out = {}
    for name, plan in plans.items():
        items = list(common)
        for cat in ("battery", "solar"):
            if plan.get(cat):
                items.append((plan[cat], load_product(cat, plan[cat])["price_sgd"]))
        items += [(n, load_product("power_conv", n)["price_sgd"]) for n in plan.get("parts", [])]
        if plan.get("other_sgd"):
            items.append(("plan extras", plan["other_sgd"]))
        items.append(("other hardware", other))
        out[name] = {"total_sgd": round(sum(v for _, v in items), 2), "items": items}
    return out


# --------------------------------------------------------------------------- v11 detection coverage
# Lens model: the image radius is r = (f/p)·u·(1 − D·u²/3) for a ray at tangent u from the optical
# axis, so the local scale is (f/p)·g with g = 1 − D·u². q = (N/2) / ((f/p)·tan(θ/2)) is how much
# narrower the image is than a pinhole with the centre's f/p. Without a DORI figure D = 0 and
# f/p = (N/2) / tan(θ/2) (the field-of-view method).

def native_size(camera):
    return tuple(camera["resolution_px"])


def lens(camera):
    """(f/p, q, D) from the native width N, field of view θ and the DORI centre ratio."""
    n = native_size(camera)[0]
    t = math.tan(math.radians(camera["hfov_deg"]) / 2)
    fp = camera.get("dori_fp_px")
    if not fp:
        return (n / 2) / t, 1.0, 0.0
    q = (n / 2) / (fp * t)
    return float(fp), q, 3 * (1 - q) / t ** 2


def lens_for(camera, method):
    """(f/p, D) for the 'distortion' method (the DORI ratio and D) or the 'fov' method (pinhole)."""
    fp, _, d = lens(camera)
    if method == "fov" or not d:
        return (native_size(camera)[0] / 2) / math.tan(math.radians(camera["hfov_deg"]) / 2), 0.0
    return fp, d


def camera_frame(site, pts, camera=None, mast=None):
    """Ground points (N, 2) or (N, 3) in the camera frame: x right, y down, z along the optical axis."""
    from world.camera import PinholeCamera
    cam = PinholeCamera.from_site(site, camera=camera, mast=mast)
    p = np.atleast_2d(np.asarray(pts, dtype=np.float64))
    if p.shape[1] == 2:
        p = np.hstack([p, np.zeros((len(p), 1))])
    return (p - cam.pos) @ cam.R.T


def native_density(site, pts, method="distortion", camera=None, mast=None):
    """Native px/m at ground points: (f/p)·g / z, z the exact depth along the optical axis
    (not the slant range), g = 1 − D·u². Also returns whether each point is inside the native
    image. -> (density, inside)"""
    camera = camera or site["fitted"]["camera"]
    pc = camera_frame(site, pts, camera, mast)
    fp, d = lens_for(camera, method)
    z = pc[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        ux, uy = pc[:, 0] / z, pc[:, 1] / z
        u2 = ux ** 2 + uy ** 2
        scale = fp * (1 - d * u2 / 3)                     # image radius / u
        n_w, n_h = native_size(camera)
        inside = (z > 0) & (np.abs(ux * scale) <= n_w / 2) & (np.abs(uy * scale) <= n_h / 2)
        dens = np.where(z > 0, fp * (1 - d * u2) / z, 0.0)
    return dens, inside


def downsample(camera, detector):
    """How many native pixels make one processed pixel: 1 on full-resolution tiles, else the
    native width over the detector's input width."""
    if not detector or detector.get("tiles"):
        return 1.0
    return native_size(camera)[0] / float(detector["input_px"])


def processed_density(site, pts, detector=None, method="worst", camera=None, mast=None):
    """px/m in the image the detector processes. method: 'fov', 'distortion' or 'worst' (the lower
    of the two at each point). -> (density, inside)"""
    camera = camera or site["fitted"]["camera"]
    detector = site.get("detector") if detector is None else detector
    if method == "worst":
        a, ia = native_density(site, pts, "fov", camera, mast)
        b, ib = native_density(site, pts, "distortion", camera, mast)
        dens, inside = np.minimum(a, b), ia & ib
    else:
        dens, inside = native_density(site, pts, method, camera, mast)
    return dens / downsample(camera, detector), inside
