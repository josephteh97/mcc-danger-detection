"""Quick checks: human trial mode, keyboard walk-in, keys over the network (V29-V34, U10)."""
import math
import threading
import time

from _check import check, main

from app.alarm import foot_pixel
from tools.trial import TrialSession, scripted_walk_in
from world.controls import ControlServer, apply_message, send_keys

_walk = {}


def walk_in():
    """One clear-day keyboard walk-in (default detector: 120 ms delay, 2% misses), shared by V30-V32."""
    if not _walk:
        s = TrialSession(miss_rate=0.02, delay_ms=120, seed=1, profile="phase1")
        scripted_walk_in(s)
        _walk["session"], _walk["card"] = s, s.scorecard()
    return _walk["session"], _walk["card"]


def foot_px(session, wid):
    w = next(t for t in session.truth["workers"] if t["id"] == wid)
    return foot_pixel(w["box"]), (w["x"], w["y"])


@check("V29", "Trial keys")
def v29():
    out, ok = [], True
    for keys, run, want_speed in (({"up"}, False, 1.4), ({"right"}, False, 1.4), ({"right"}, True, 3.0)):
        s = TrialSession(delay_ms=0, profile="phase1")
        wid = s.add_worker((-2.0, -2.5))
        s.step()
        (u0, v0), g0 = foot_px(s, wid)
        s.hold(keys, 2.0, run)
        (u1, v1), g1 = foot_px(s, wid)
        speed = math.dist(g0, g1) / 2.0
        moved_right_way = (v1 < v0) if "up" in keys else (u1 > u0)
        ok &= moved_right_way and abs(speed - want_speed) <= 0.02 * want_speed
        out.append(f"{'+'.join(sorted(keys))}{'+Shift' if run else ''}: {'up' if v1 < v0 else 'down'} "
                   f"{abs(v1 - v0):.0f} px / {'right' if u1 > u0 else 'left'} {abs(u1 - u0):.0f} px, {speed:.2f} m/s")
    return ok, "; ".join(out), "Up moves up the picture, Right moves right; walk 1.4 m/s, Shift 3.0 m/s (within 2%)"


@check("V30", "Keyboard walk-in")
def v30():
    _, card = walk_in()
    e, n = card["entries"][0], card["events"]
    one_each = all(n.get(k) == 1 for k in ("caution", "warning", "alarm", "reset")) and len(card["entries"]) == 1
    w, a = e["warning_after_entering_s"], e["alarm_after_entering_s"]
    ok = one_each and w is not None and a is not None and 0.9 <= w <= 1.4 and 2.9 <= a <= 3.4
    return ok, f"events {n}; warning {w:.2f} s and alarm {a:.2f} s after entering (guide 1.13 s; 3.2 s)", "one of each; warning about 1 s, alarm about 3 s after entering, plus detector delay"


@check("V31", "Laser on the feet")
def v31():
    _, card = walk_in()
    d = card["entries"][0]["dot_to_feet_median_m"]
    return d is not None and d <= 0.5, f"laser dot {d:.2f} m from the feet (median; guide 0.27 m)", "dot within 0.5 m of the feet"


@check("V32", "Walk out")
def v32():
    s, card = walk_in()
    r = card["entries"][0]["reset_after_leaving_s"]
    parked = (not s.arm.laser_on) and abs(s.arm.tilt - 90) < 1.0
    ok = r is not None and 1.9 <= r <= 2.5 and parked
    return ok, f"reset {r:.2f} s after leaving (guide 2.2 s); laser {'on' if s.arm.laser_on else 'off'}, arm tilt {s.arm.tilt:.0f} deg", "reset about 2 s after leaving; laser parked and off"


@check("V33", "Site boundary")
def v33():
    s = TrialSession(delay_ms=0, profile="phase1")
    wid = s.add_worker((-2.0, -2.5))
    s.hold({"up"}, 40.0)
    w = s.worker(wid)
    (x0, y0), (x1, y1) = s.world.scene.boundary.min(axis=0), s.world.scene.boundary.max(axis=0)
    gap = min(w.x - x0, x1 - w.x, w.y - y0, y1 - w.y)
    inside = x0 < w.x < x1 and y0 < w.y < y1
    return inside and gap <= 0.35, f"after 40 s of Up the worker stopped at ({w.x:.2f}, {w.y:.2f}), {gap:.2f} m from the hoarding", "worker stops at the site hoarding"


@check("V34", "Keys over the network")
def v34():
    from world.world import World
    import catalog
    world = World(catalog.load_site(profile="phase1"))
    server = ControlServer("127.0.0.1:0")
    addr = f"127.0.0.1:{server.port}"
    sender = threading.Thread(target=send_keys, args=(addr, ["up"]), kwargs={"duration_s": 1.5})
    track, start = [], time.monotonic()
    sender.start()
    last_msg, prev = None, time.monotonic()
    while time.monotonic() - start < 3.0:
        now = time.monotonic()
        world.step(now - prev)
        prev = now
        for msg in server.poll():
            apply_message(world, msg)
            last_msg = now
        w = next((w for w in world.scene.workers if w.controlled), None)
        if w:
            track.append((now, w.x, w.y))
        time.sleep(1 / 15)
    sender.join()
    server.close()
    if not track or last_msg is None:
        return False, "no keys arrived", "UDP keys move the worker"
    moved = math.dist(track[0][1:], track[-1][1:])
    stop_t = next(t for t, x, y in reversed(track[:-1]) if math.dist((x, y), track[-1][1:]) > 1e-6)
    stopped_after = stop_t - last_msg
    ok = moved > 1.0 and stopped_after <= 0.5 + 1 / 15 + 0.02
    return ok, f"worker walked {moved:.2f} m on UDP keys and stopped {stopped_after:.2f} s after the last message", "keys move the worker; 0.5 s of silence stops it"


@check("U10", "Two workers: laser follows the one inside")
def u10():
    s = TrialSession(delay_ms=120, miss_rate=0.0, scenario="two_workers", profile="phase1")
    exits, follow_bad, follow_n, resets = {}, 0, 0, []
    last_inside, stable_since, lasing_since = None, 0.0, None
    for _ in range(int(26 * 15)):
        truth = s.step()
        inside = {w["id"] for w in truth["workers"] if w["edge_m"] <= 1.5}
        if inside != last_inside:              # allow 0.5 s for detector delay and arm slew
            last_inside, stable_since = inside, s.t
        for w in truth["workers"]:
            if w["edge_m"] <= 1.5:
                exits.pop(w["id"], None)
            elif w["id"] not in exits:
                exits[w["id"]] = s.t
        d = s.dot()
        lasing_since = (lasing_since or s.t) if d is not None else None
        settled = d is not None and s.t - stable_since >= 0.5 and s.t - lasing_since >= 0.6   # swing from park
        if settled and len(truth["workers"]) == 2 and len(inside) == 1:
            follow_n += 1
            near = min(truth["workers"], key=lambda w: math.dist((w["x"], w["y"]), d))
            follow_bad += near["id"] not in inside
    resets = [t for t, k, _ in s.events if k == "reset"]
    last_exit = max(exits.values()) if exits else None
    ok = follow_n > 15 and follow_bad == 0 and len(resets) == 1 and last_exit is not None and resets[0] >= last_exit + 1.9
    return ok, (f"laser on the worker inside in {follow_n - follow_bad}/{follow_n} frames with one inside; "
                f"one reset at {resets[0] if resets else float('nan'):.1f} s, last worker left at {last_exit:.1f} s"), \
        "laser follows the worker inside; reset only when both are clear"


if __name__ == "__main__":
    main("smoke_trial.py")
