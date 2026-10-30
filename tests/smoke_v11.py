"""Quick checks for hardware list version 11: coverage, PoE, 4G data, power plans, identification
off, watchdog and laser reach (U11-U26). They load the v11 profile whatever site.yaml selects."""
import math

from _check import check, main

import catalog
from catalog import effects as fx
from tools import coverage as cov

SITE = catalog.load_site(profile="v11")
CAMERA = SITE["fitted"]["camera"]
RHO = SITE["detector"]["density_px_per_m"]


def near(value, target, tol):
    return abs(value - target) <= tol


# --------------------------------------------------------------------------- coverage (U11-U16)

@check("U11", "Distortion q and D")
def u11():
    fp, q, d = fx.lens(CAMERA)
    # a point on the optical axis at depth 10 m: 284 px/m at the image centre
    from world.camera import PinholeCamera
    cam = PinholeCamera.from_site(SITE)
    centre = cam.pos + 10.0 * cam.R[2]
    dens = float(fx.native_density(SITE, [centre])[0][0])
    ok = near(q, 0.571, 0.005) and near(d, 0.844, 0.01) and near(dens, 284, 1)
    return ok, f"q {q:.3f}, D {d:.3f}, centre density at 10 m {dens:.1f} px/m", \
        "q = 0.571 ± 0.005, D = 0.844 ± 0.01, centre 284 ± 1 px/m"


@check("U12", "Ring density with tiles")
def u12():
    r = cov.ring_check(SITE, {**SITE["detector"], "tiles": True})
    return r["ok"], f"lowest {r['min_ppm']:.0f} px/m over {r['points']} ring points (full-resolution tiles)", \
        f"every warning-ring point ≥ {RHO} px/m in the processed image"


@check("U13", "Shrunken detector input fails as expected")
def u13():
    r = cov.ring_check(SITE, {**SITE["detector"], "tiles": False, "input_px": 1280})
    return not r["ok"] and r["below"], \
        f"input 1280 px, no tiles: lowest {r['min_ppm']:.0f} px/m, {len(r['below'])} of {r['points']} points below {RHO}", \
        "the check reports ring points below 100 px/m and fails"


@check("U14", "Largest-zone solver")
def u14():
    z = cov.largest_zone(CAMERA, RHO)
    (s, d), (s2, d2) = z["fov"], z["distortion"]
    ok = near(s, 11.5, 0.1) and near(d, 10.4, 0.1) and near(s2, 11.2, 0.1) and near(d2, 17.1, 0.2)
    return ok, f"field of view {s:.2f} m at {d:.2f} m; distortion {s2:.2f} m at {d2:.2f} m", \
        "11.5 ± 0.1 m at 10.4 ± 0.1 m, and 11.2 ± 0.1 m at 17.1 ± 0.2 m"


@check("U15", "Pose inside windows")
def u15():
    p = cov.pose_check(SITE, RHO)
    lo, hi = p["height_window"]
    ok = p["ok"] and near(p["far_edge_ppm"], 122, 3) and near(lo, 2.7, 0.05) and near(hi, 5.7, 0.05)
    return ok, (f"stand {p['distance']:.1f} m, camera {p['height_m']:.2f} m (window {lo:.2f}-{hi:.2f} m), "
                f"far edge {p['far_edge_ppm']:.0f} px/m"), \
        "inside both windows, far edge 122 ± 3 px/m, height window 2.7-5.7 m"


@check("U16", "Stand too close is flagged")
def u16():
    p = cov.pose_check(cov.moved(SITE, 5.0), RHO)
    flagged = not p["ok"] and any("outside the image" in m for m in p["problems"])
    return flagged, "; ".join(p["problems"]) or "no problem found", \
        "at 5 m the warning ring's near corners fall outside the image and the pose is flagged"


# --------------------------------------------------------------------------- network and power (U17-U23)

@check("U17", "PoE budget")
def u17():
    from devices.poe_model import check as poe_check
    r = poe_check(SITE)
    ok = r["ok"] and near(r["reserved_w"], 135.4, 0.05) and near(r["draw_w"], 88, 5)
    return ok, f"reserved {r['reserved_w']:.1f} W, draw up to {r['draw_w']:.1f} W of {r['budget_w']:.0f} W", \
        "reserved 135.4 W, draw 88 ± 5 W, within the 240 W budget"


@check("U18", "Undersized switch fails as expected")
def u18():
    from devices.poe_model import check as poe_check
    r = poe_check(SITE, budget_w=90)
    return not r["ok"] and r["refused"], f"90 W switch: refused {'; '.join(r['refused']) or 'nothing'}", \
        "the check fails on reserved power and names the refused ports"


@check("U19", "4G data a month")
def u19():
    from tools.network import report
    r = report(SITE, events_per_day=50, clip_mb=1.3, view_hours_per_day=1.0, view_mbps=1.0)
    ok = near(r["data"]["total_gb"], 15, 1) and r["within_plan"] and r["max_link_pct"] < 5
    return ok, (f"{r['data']['total_gb']:.1f} GB a month of {r['plan_gb']:.0f} GB, "
                f"busiest wired link {r['max_link_pct']:.1f}% at cap"), \
        "15 ± 1 GB a month within the plan, every wired link below 5% load"


@check("U20", "PoE++ losses")
def u20():
    from devices.poe_model import efficiencies
    from devices.power_model import bus_watts
    w = bus_watts(25.0, efficiencies(SITE), via_splitter=True)
    return near(w, 30.5, 0.5), f"25 W at the AI box takes {w:.2f} W from the bus", "30.5 ± 0.5 W"


@check("U21", "Continuous load")
def u21():
    from devices.power_model import V11PowerConfig
    w = V11PowerConfig.from_site(SITE, "B").average_load_w()
    return 65 <= w <= 75, f"average bus load {w:.1f} W with no alarms", "between 65 and 75 W"


@check("U22", "Plan B, three heavily overcast days")
def u22():
    from devices.power_model import V11PowerConfig, describe, simulate_v11
    r = simulate_v11(V11PowerConfig.from_site(SITE, "B"), [0.3] * 3)
    ok = r["lowest_pct"] > 10 and not r["stage2"]
    return ok, f"lowest charge {describe(r['lowest_pct'])}, Stage 2 {'triggered' if r['stage2'] else 'never'}", \
        "stays above 10% and Stage 2 never triggers"


@check("U23", "Plan A weekend shutdown order")
def u23():
    from devices.power_model import V11PowerConfig, simulate_v11
    r = simulate_v11(V11PowerConfig.from_site(SITE, "A"), [1.0] * 3, socket_off=[(0, 60)])
    order = [e for _, e in r["events"] if e.startswith(("Stage 1:", "Stage 2:"))]
    ok = len(order) >= 2 and order[0].startswith("Stage 1") and order[1].startswith("Stage 2") \
        and r["router_hours_after_stage2"] >= 10
    return ok, (f"socket off 60 h: {' then '.join(o.split(':')[0] for o in order) or 'no stage'}, router on "
                f"{r['router_hours_after_stage2']:.1f} h after Stage 2, {r['hours_without_alarm']:.1f} h without an alarm"), \
        "Stage 1 then Stage 2, router on at least 10 h after Stage 2, hours without an alarm reported"


# --------------------------------------------------------------------------- identification, watchdog (U24, U25)

@check("U24", "No identity in v11")
def u24():
    from app_harness import alarm_event
    event, loaded = alarm_event("app/config.v11.yaml")
    ok = event["kind"] == "alarm" and "identity" not in event and not loaded
    return ok, (f"alarm event keys {sorted(event)}; app.identify "
                f"{'imported' if loaded else 'not imported'}"), \
        "the v11 alarm event has no identity field and app.identify is not loaded"


@check("U25", "Watchdog restart (model)")
def u25():
    from devices.poe_watchdog import simulate_hang
    worst = [simulate_hang(hang_t=h, phase=0.0) for h in (0.0, 0.01, 5.0, 9.99)]
    restart = max(r for r, _ in worst)
    back = max(m - r for r, m in worst)
    return restart <= 40 and back <= 60, \
        f"power cycle at most {restart:.0f} s after the hang, Monitoring {back:.0f} s after the cycle", \
        "3 missed pings 10 s apart: restart within 40 s, Monitoring within 60 s after that"


# --------------------------------------------------------------------------- laser reach (U26)

@check("U26", "Laser reach")
def u26():
    r = cov.laser_reach(SITE)
    at10 = cov.laser_reach(cov.moved(SITE, 10.0))
    ok = r["ok"] and near(r["far_m"], 12.1, 0.05) and near(r["reach_m"], 12.57, 0.01) \
        and not at10["ok"] and near(at10["shortfall_m"], 0.02, 0.005)
    msg = (f"far corner {r['far_m']:.2f} m, 5° stop reaches {r['reach_m']:.2f} m"
           + ("" if r["ok"] else f": SHORT by {r['shortfall_m']:.2f} m (design finding)")
           + f"; at 10 m short by {at10['shortfall_m']:.2f} m")
    return ok, msg, "the 1.5 m zone's far corner is within the 5° stop's reach (1.1 / tan 5° = 12.57 m); 10 m is 0.02 m short"


if __name__ == "__main__":
    main("smoke_v11.py")
