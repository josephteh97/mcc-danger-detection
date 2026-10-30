"""v11 numbers for the dashboard: the what-if panel (key in product values and site settings,
see every model's result), the HUD panels and the coverage heatmap. Plain functions, so they
are tested without the stack (tests/test_whatif.py).

What-if values never touch the catalogue files: they apply to one calculation only.
"""
from __future__ import annotations

import copy
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

# Site settings: key -> (label, unit, getter)
SITE_FIELDS = {
    "stand_distance_m": ("Stand distance from the pit centre", "m", lambda s: cov.pose_check(s)["distance"]),
    "camera_height_m": ("Camera height", "m", lambda s: s["camera"].get("height_m", s["fitted"]["mast"]["height_m"])),
    "tilt_deg": ("Camera tilt below horizontal", "°", lambda s: s["camera"].get("tilt_deg", 30.0)),
    "switch_budget_w": ("Switch PoE budget", "W", lambda s: s["fitted"]["switch"]["poe_budget_w"]),
    "tiles": ("Detector on full-resolution tiles (1 = yes)", "", lambda s: 1 if s["detector"].get("tiles") else 0),
    "input_px": ("Detector input width without tiles", "px", lambda s: s["detector"]["input_px"]),
    "density_px_per_m": ("Required density", "px/m", lambda s: s["detector"]["density_px_per_m"]),
    "sun_factor": ("Sun factor for the battery runs", "", lambda s: 0.3),
    "days": ("Days in the battery runs", "", lambda s: 3),
    "socket_off_h": ("Plan A: hours with the socket off", "h", lambda s: 60),
    "events_per_day": ("Events a day", "", lambda s: s["network"]["events_per_day"]),
    "clip_mb": ("Clip size", "MB", lambda s: s["network"]["clip_mb"]),
    "view_hours_per_day": ("Live viewing a day", "h", lambda s: s["network"]["view_hours_per_day"]),
    "view_mbps": ("Live view bitrate", "Mbit/s", lambda s: s["network"]["view_mbps"]),
    "sim_plan_gb": ("SIM data plan", "GB", lambda s: s["network"]["sim_plan_gb"]),
    "cable_eff": ("PoE cable efficiency", "", lambda s: s["power"]["efficiency"]["cable"]),
    "laser_controller_w": ("Laser controller typical power", "W", lambda s: s["laser_controller"]["watts_typ"]),
    "laser_controller_sgd": ("Laser controller price", "S$", lambda s: s["laser_controller"]["price_sgd"]),
}


def _plan_products(site):
    names = {}
    for p in (site.get("power_plans") or {}).values():
        for cat, n in (("battery", p.get("battery")), ("solar", p.get("solar"))):
            if n:
                names[n] = cat
        for n in p.get("parts", []):
            names[n] = "power_conv"
    return names


def fields(profile="v11"):
    """Everything the panel can edit, with today's values."""
    site = catalog.load_site(profile=profile)
    seen, products = set(), []
    entries = catalog.fitted_products(site) + [catalog.load_product(cat, n) for n, cat in _plan_products(site).items()]
    for p in entries:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        products.append({"id": p["id"], "name": p["name"], "verified": p["verified"], "source": p["source"],
                         "fields": {f: p[f] for f in PRODUCT_FIELDS if isinstance(p.get(f), (int, float))
                                    and not isinstance(p.get(f), bool)}})
    return {"products": products,
            "site": {k: {"label": lab, "unit": unit, "value": round(float(get(site)), 3)}
                     for k, (lab, unit, get) in SITE_FIELDS.items()}}


def _apply_site(site, s):
    if "stand_distance_m" in s or "camera_height_m" in s:
        site = cov.moved(site, s.get("stand_distance_m"), s.get("camera_height_m"))
    site = copy.deepcopy(site)
    if "tilt_deg" in s:
        site["camera"]["tilt_deg"] = float(s["tilt_deg"])
    for key in ("tiles", "input_px", "density_px_per_m"):
        if key in s:
            site["detector"][key] = bool(s[key]) if key == "tiles" else float(s[key])
    for key in ("events_per_day", "clip_mb", "view_hours_per_day", "view_mbps", "sim_plan_gb"):
        if key in s:
            site["network"][key] = float(s[key])
    if "cable_eff" in s:
        site["power"]["efficiency"]["cable"] = float(s["cable_eff"])
    if "laser_controller_w" in s:
        site["laser_controller"]["watts_typ"] = float(s["laser_controller_w"])
    if "laser_controller_sgd" in s:
        site["laser_controller"]["price_sgd"] = float(s["laser_controller_sgd"])
    return site


def whatif(products=None, settings=None, profile="v11"):
    """Every v11 model's result for these product values and site settings."""
    settings = {k: v for k, v in (settings or {}).items() if k in SITE_FIELDS and v is not None and v != ""}
    products = {pid: {f: float(v) for f, v in vals.items() if f in PRODUCT_FIELDS}
                for pid, vals in (products or {}).items()}
    t0 = time.monotonic()
    with catalog.overriding(products):
        site = _apply_site(catalog.load_site(profile=profile), settings)
        budget = settings.get("switch_budget_w")
        poe = poe_model.check(site, float(budget) if budget is not None else None)
        sun, days = float(settings.get("sun_factor", 0.3)), int(settings.get("days", 3))
        plans = {}
        for plan in PLANS:
            cfg = V11PowerConfig.from_site(site, plan)
            r = simulate_v11(cfg, [sun] * days)
            plans[plan] = {"average_load_w": round(cfg.average_load_w(), 1), "battery_wh": cfg.battery_wh,
                           "panel_w": cfg.panel_w, "lowest_pct": round(r["lowest_pct"], 1),
                           "lowest": describe(r["lowest_pct"]), "stage2": r["stage2"],
                           "ok": r["lowest_pct"] > 10 and not r["stage2"]}
        off = float(settings.get("socket_off_h", 60))
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
    """The slow-changing HUD numbers: PoE, plan, battery size, 4G estimate."""
    poe = poe_model.check(site)
    plan = "A"
    cfg = V11PowerConfig.from_site(site, plan)
    net = network.report(site)
    day = time.localtime().tm_mday
    return {"poe": {"draw_w": round(poe["draw_typ_w"], 1), "reserved_w": poe["reserved_w"], "budget_w": poe["budget_w"]},
            "power": {"plan": plan, "average_load_w": round(cfg.average_load_w(), 1), "battery_wh": cfg.battery_wh,
                      "plans": {k: v["name"] for k, v in site["power_plans"].items()}},
            "data": {"month_estimate_gb": round(net["data"]["total_gb"], 1),
                     "month_to_date_gb": round(net["data"]["total_gb"] * day / 30, 1), "plan_gb": net["plan_gb"]}}
