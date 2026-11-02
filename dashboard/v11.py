"""v11 numbers for the dashboard: the what-if panel (key in product values and site settings,
see every model's result), the HUD panels and the coverage heatmap. Plain functions, so they
are tested without the stack (tests/test_whatif.py).

What-if values never touch the catalogue files: they apply to one calculation only.
"""
from __future__ import annotations

import math
import time

import catalog
from catalog import effects as fx
from devices import poe_model
from devices.power_model import PLANS, V11PowerConfig, describe, simulate_v11
from tools import coverage as cov
from tools import network

# Product fields the panel lets you edit (when the product has them)
PRODUCT_FIELDS = ("price_sgd", "watts_typ", "watts_max", "poe_class", "power_w", "efficiency", "rated_w",
                  "capacity_ah", "voltage_v", "panel_w", "poe_budget_w", "hfov_deg", "dori_fp_px", "lumens")

# Site settings: key -> (label, unit, where, default, minimum). where: ("run",) for the what-if runs
# themselves (not part of the site), ("pose", <pose_check key>), or a path into the site; default
# fills a setting the site leaves out; a keyed-in value below minimum is refused (None: no limit).
POSITIVE = 1e-9
SITE_FIELDS = {
    "stand_distance_m": ("Stand distance from the pit centre", "m", ("pose", "distance"), None, POSITIVE),
    "camera_height_m": ("Camera height", "m", ("pose", "height_m"), None, POSITIVE),
    "tilt_deg": ("Camera tilt below horizontal", "°", ("camera", "tilt_deg"), None, POSITIVE),
    "switch_budget_w": ("Switch PoE budget", "W", ("fitted", "switch", "poe_budget_w"), None, 0),
    "tiles": ("Detector on full-resolution tiles (1 = yes)", "", ("detector", "tiles"), False, None),
    "input_px": ("Detector input width without tiles", "px", ("detector", "input_px"), None, 1),
    "density_px_per_m": ("Required density", "px/m", ("detector", "density_px_per_m"), None, POSITIVE),
    "sun_factor": ("Sun factor for the battery runs", "", ("run",), 0.3, 0),
    "days": ("Days in the battery runs", "", ("run",), 3, 1),
    "socket_off_h": ("Plan A: hours with the socket off", "h", ("run",), 60, 0),
    "events_per_day": ("Events a day", "", ("network", "events_per_day"), None, 0),
    "clip_mb": ("Clip size", "MB", ("network", "clip_mb"), None, 0),
    "view_hours_per_day": ("Live viewing a day", "h", ("network", "view_hours_per_day"), None, 0),
    "view_mbps": ("Live view bitrate", "Mbit/s", ("network", "view_mbps"), None, 0),
    "sim_plan_gb": ("SIM data plan", "GB", ("network", "sim_plan_gb"), None, 0),
    "cable_eff": ("PoE cable efficiency", "", ("power", "efficiency", "cable"), None, POSITIVE),
    "laser_controller_w": ("Laser controller typical power", "W", ("laser_controller", "watts_typ"), None, 0),
    "laser_controller_sgd": ("Laser controller price", "S$", ("laser_controller", "price_sgd"), None, 0),
}
# Product fields that divide (efficiencies, capacities, lens figures) must stay above zero
POSITIVE_PRODUCT_FIELDS = {"efficiency", "capacity_ah", "voltage_v", "hfov_deg", "dori_fp_px"}


def _tilt(site):
    """The camera's tilt below horizontal: the site's, else the one that aims it at look_at."""
    sc = site["camera"]
    if "tilt_deg" in sc:
        return sc["tilt_deg"]
    h = sc.get("height_m", site["fitted"]["mast"]["height_m"])
    return math.degrees(math.atan2(h, math.dist(sc["xy"], sc.get("look_at", [0.0, 0.0]))))


def _value(site, key, pose):
    where, default = SITE_FIELDS[key][2], SITE_FIELDS[key][3]
    if where[0] == "run":
        return default
    if where[0] == "pose":
        return pose[where[1]]
    if key == "tilt_deg":
        return _tilt(site)
    node = site
    for k in where[:-1]:
        node = node[k]
    return node.get(where[-1], default)


def _number(name, v, minimum):
    """A keyed-in value as a finite float, refused (ValueError) below its minimum."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: '{v}' is not a number") from None
    if not math.isfinite(x) or (minimum is not None and x < minimum):
        raise ValueError(f"{name}: {v} is out of range" + ("" if minimum is None else
                         " (must be above 0)" if minimum == POSITIVE else f" (must be at least {minimum:g})"))
    return x


def _flag(v):
    """1/0, true/false, yes/no, as a number or text."""
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(v)


def fields(profile="v11"):
    """Everything the panel can edit, with today's values."""
    site = catalog.load_site(profile=profile)
    plan_parts = [p for pp in catalog.plan_products(site).values() for p in fx.plan_parts(pp)]
    products = {}
    for p in catalog.fitted_products(site) + plan_parts:
        products.setdefault(p["id"], {
            "id": p["id"], "name": p["name"], "verified": p["verified"], "source": p["source"],
            "fields": {f: p[f] for f in PRODUCT_FIELDS if isinstance(p.get(f), (int, float)) and not isinstance(p.get(f), bool)}})
    pose = cov.pose_check(site)
    return {"products": list(products.values()),
            "site": {k: {"label": lab, "unit": unit, "value": round(float(_value(site, k, pose)), 3)}
                     for k, (lab, unit, *_) in SITE_FIELDS.items()}}


def _apply_site(site, s):
    """A copy of the site with the keyed-in settings (the stand moved first, as one move)."""
    site = cov.moved(site, s.get("stand_distance_m"), s.get("camera_height_m"))
    for key, v in s.items():
        where = SITE_FIELDS[key][2]
        if where[0] in ("run", "pose"):
            continue
        node = site
        for k in where[:-1]:
            node = node.setdefault(k, {})
        node[where[-1]] = v
    return site


def whatif(products=None, settings=None, profile="v11"):
    """Every v11 model's result for these product values and site settings."""
    settings = {k: _flag(v) if k == "tiles" else _number(SITE_FIELDS[k][0], v, SITE_FIELDS[k][4])
                for k, v in (settings or {}).items() if k in SITE_FIELDS and v is not None and v != ""}
    products = {pid: {f: _number(f"{pid} {f}", v, POSITIVE if f in POSITIVE_PRODUCT_FIELDS else 0)
                      for f, v in vals.items() if f in PRODUCT_FIELDS}
                for pid, vals in (products or {}).items()}
    t0 = time.monotonic()
    run = {k: settings.get(k, f[3]) for k, f in SITE_FIELDS.items() if f[2] == ("run",)}
    site = _apply_site(catalog.load_site(profile=profile, product_overrides=products), settings)
    poe = poe_model.check(site)
    sun, days = float(run["sun_factor"]), int(run["days"])
    plans = {}
    for plan in PLANS:
        cfg = V11PowerConfig.from_site(site, plan)
        r = simulate_v11(cfg, [sun] * days)
        plans[plan] = {"average_load_w": round(cfg.average_load_w(), 1), "battery_wh": cfg.battery_wh,
                       "panel_w": cfg.panel_w, "lowest_pct": round(r["lowest_pct"], 1),
                       "lowest": describe(r["lowest_pct"]), "stage2": r["stage2"],
                       "ok": r["lowest_pct"] > 10 and not r["stage2"]}
    off = float(run["socket_off_h"])
    wk = simulate_v11(V11PowerConfig.from_site(site, "A"), [1.0] * max(1, int(off // 24) + 1), socket_off=[(0, off)])
    costs = {k: v["total_sgd"] for k, v in fx.plan_totals(site).items()}
    net = network.report(site)
    rho = site["detector"]["density_px_per_m"]
    pose = cov.pose_check(site, rho)
    ring = cov.ring_check(site, rho=rho)
    reach = cov.laser_reach(site)
    zone = cov.largest_zone(site["fitted"]["camera"], rho)
    _, q, d = fx.lens(site["fitted"]["camera"])
    checks = [
        ("PoE budget", poe["ok"], f"reserved {poe['reserved_w']:.1f} W, draw up to {poe['draw_w']:.1f} W of {poe['budget_w']:.0f} W"
         + (f"; refused {'; '.join(poe['refused'])}" if poe["refused"] else "")),
        ("Warning ring density", ring["ok"], f"lowest {ring['min_ppm']:.0f} px/m (needs {rho:.0f})"),
        ("Stand pose", pose["ok"], "; ".join(pose["problems"]) or
         f"far edge {pose['far_edge_ppm']:.0f} px/m, height window {pose['height_window'][0]:.2f}-{pose['height_window'][1]:.2f} m"),
        ("Laser reach", reach["ok"], f"far corner {reach['far_m']:.2f} m, reach {reach['reach_m']:.2f} m"
         + (f", short by {reach['shortfall_m']:.2f} m" if not reach["ok"] else "")),
        ("4G data", net["within_plan"], f"{net['data']['total_gb']:.1f} GB a month of {net['plan_gb']:.0f} GB"),
        *[(f"Plan {k} battery", v["ok"], f"lowest {v['lowest']} over {days} days at sun {sun:g}"
           + (", Stage 2 triggered" if v["stage2"] else "")) for k, v in plans.items()],
    ]
    return {
        "checks": [{"name": n, "ok": bool(ok), "detail": det} for n, ok, det in checks],
        "poe": {k: poe[k] for k in ("ok", "budget_w", "reserved_w", "draw_w", "draw_typ_w", "refused")},
        "plans": plans, "costs_sgd": costs,
        "plan_a_socket_off": {"hours": off, "hours_without_alarm": round(wk["hours_without_alarm"], 1),
                              "router_hours_after_stage2": round(wk["router_hours_after_stage2"], 1),
                              "events": wk["events"]},
        "network": {"total_gb": round(net["data"]["total_gb"], 2), "plan_gb": net["plan_gb"],
                    "max_link_pct": round(net["max_link_pct"], 2)},
        "coverage": {"q": round(q, 3), "D": round(d, 3), "ring_min_ppm": round(ring["min_ppm"], 1),
                     "far_edge_ppm": round(pose["far_edge_ppm"], 1), "height_window": [round(v, 2) for v in pose["height_window"]],
                     "largest_zone": {m: [round(a, 2), round(b, 2)] for m, (a, b) in zone.items()}},
        "laser": {k: round(v, 3) if isinstance(v, float) else v for k, v in reach.items()},
        "edited": {"products": sorted(products), "settings": sorted(settings)},
        "elapsed_s": round(time.monotonic() - t0, 2),
    }


# --------------------------------------------------------------------------- HUD and heatmap

def coverage(site, step=0.5):
    """The px/m heatmap and the band at each warning-ring corner (for the 3D view)."""
    hm = cov.heatmap(site, step=step)
    ring = cov.warn_ring(site, 8)
    dens, _ = fx.processed_density(site, ring)
    hm["corners"] = [{"x": round(float(x), 2), "y": round(float(y), 2), "ppm": round(float(v), 1), "band": cov.band(v)}
                     for (x, y), v in zip(ring, dens)]
    return hm


def hud_static(site):
    """The HUD numbers that depend only on the site: PoE, plan, battery size, 4G estimate (the server
    adds month-to-date data per request, and rounds both)."""
    poe = poe_model.check(site)
    plan = "A"
    cfg = V11PowerConfig.from_site(site, plan)
    net = network.report(site)
    return {"poe": {"draw_w": round(poe["draw_typ_w"], 1), "reserved_w": poe["reserved_w"], "budget_w": poe["budget_w"]},
            "power": {"plan": plan, "average_load_w": round(cfg.average_load_w(), 1), "battery_wh": cfg.battery_wh,
                      "plans": {k: v["name"] for k, v in site["power_plans"].items()}},
            "data": {"month_estimate_gb": net["data"]["total_gb"], "plan_gb": net["plan_gb"]}}
