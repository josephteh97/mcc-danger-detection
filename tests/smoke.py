"""Quick checks: alarm logic and timing, zone geometry, foot accuracy, power (V01-V05, V10, V11, U01-U03)."""
import math
import random

from _check import check, main

import catalog
from app.alarm import AlarmFSM, Config, edge_distance, foot_pixel, ground_from_image
from devices.power_model import FLOOR_PCT, PowerConfig, describe, lowest_charge
from world.camera import image_to_ground_homography
from world.scene import Scene
from world.world import World

FPS = 15
FRAME = 1.0 / FPS
SITE = catalog.load_site(profile="phase1")
PIT = [tuple(p) for p in SITE["site"]["pit"]]


def scripted_run(scenario, seconds, miss_rate=0.0, seed=0):
    """Ground-truth distances from a scripted walk, fed to the state machine at 15 fps."""
    scene, fsm, rng = Scene(SITE["site"]["boundary"], PIT), AlarmFSM(Config()), random.Random(seed)
    scene.reset(scenario)
    events, inside_since, entries, exits = [], None, [], []
    for i in range(int(seconds * FPS)):
        scene.step(FRAME, (1, 0), (0, -1))
        t = round((i + 1) * FRAME, 6)
        dist = {w.id: edge_distance(w.x, w.y, PIT) for w in scene.workers if w.active(scene.t)}
        inside = any(d <= fsm.cfg.alarm_buffer_m for d in dist.values())
        if inside and inside_since is None:
            inside_since = t
            entries.append(t)
        elif not inside and inside_since is not None:
            inside_since = None
            exits.append(t)
        seen = {k: v for k, v in dist.items() if rng.random() >= miss_rate}
        events += [(t, kind) for kind, _ in fsm.update(t, seen)]
    return events, entries, exits


@check("V01", "Alarm sequence on a walk-in")
def v01():
    events, _, _ = scripted_run("single_walk_in", 25)
    kinds = [k for _, k in events]
    return kinds == ["caution", "warning", "alarm", "reset"], " -> ".join(kinds), "caution, warning, alarm, reset in that order"


@check("V02", "Warning timing")
def v02():
    events, entries, _ = scripted_run("single_walk_in", 25)
    dt = next(t for t, k in events if k == "warning") - entries[0]
    return abs(dt - 1.0) <= FRAME + 1e-6, f"{dt:.3f} s after entering the 1.5 m zone", "1.0 s within one frame (1/15 s)"


@check("V03", "Escalation timing")
def v03():
    events, entries, _ = scripted_run("single_walk_in", 25)
    dt = next(t for t, k in events if k == "alarm") - entries[0]
    return abs(dt - 3.0) <= FRAME + 1e-6, f"{dt:.3f} s after entering", "3.0 s within one frame"


@check("V04", "No false alarm at the edge")
def v04():
    events, _, _ = scripted_run("stops_1_6m", 40)
    kinds = [k for _, k in events]
    return kinds == ["caution"], f"events {kinds} while standing 1.6 m away for 20 s", "a caution only"


@check("V05", "Foot position accuracy")
def v05():
    world = World(SITE, scenario="idle")
    w = world.scene.add_controlled((0.6, -1.6))
    world.step(FRAME)
    _, info = world.render()
    H = world.homography()
    gx, gy = ground_from_image(H, *foot_pixel(info["boxes"][w.id]))
    err = math.dist((gx, gy), (w.x, w.y))
    rng = math.dist(world.cam.pos[:2], (w.x, w.y))
    return err < 0.35, f"{err:.2f} m off at {rng:.1f} m from the mast (toward the camera: box edge is the nearest bottom corner)", "error < 0.35 m at about 9 m"


@check("U01", "Homography round trip")
def u01():
    world = World(SITE)
    pts = SITE["calibration"]["points"]
    H, pix = image_to_ground_homography(world.cam, pts)
    err = max(math.dist(ground_from_image(H, *p), g) for p, g in zip(pix, pts))
    return err < 0.01, f"max error {err * 1000:.3f} mm over 4 points", "every point within 0.01 m"


@check("U02", "Distance to the pit edge")
def u02():
    inside = edge_distance(0.3, 0.2, PIT)
    beside = edge_distance(0.0, 1.8, PIT)
    corner = edge_distance(2.2, 1.8, PIT)
    ok = inside == 0.0 and abs(beside - 1.0) < 1e-3 and abs(corner - math.sqrt(2)) < 1e-3
    return ok, f"inside {inside:.3f}, beside {beside:.3f}, corner {corner:.4f}", "0 inside, 1.0 beside the long edge, sqrt(2) off the corner"


@check("U03", "Missed frames do not repeat the caution")
def u03():
    bad = []
    for seed in range(20):
        kinds = [k for _, k in scripted_run("single_walk_in", 25, miss_rate=0.1, seed=seed)[0]]
        if kinds != ["caution", "warning", "alarm", "reset"]:
            bad.append((seed, kinds))
    return not bad, f"{20 - len(bad)}/20 walk-ins with 10% missed frames gave one of each event", "every run gives exactly one caution, warning, alarm and reset"


def overcast_low(days):
    return lowest_charge(PowerConfig.from_site(SITE), 0.3, days)


@check("V10", "Power, 2 overcast days")
def v10():
    pct = overcast_low(2)
    return pct > FLOOR_PCT, f"lowest charge {describe(pct)} at 30% sun", f"battery stays above {FLOOR_PCT:.0f}%"


@check("V11", "Power, 3 overcast days")
def v11():
    pct = overcast_low(3)
    return pct > FLOOR_PCT, f"lowest charge {describe(pct)} at 30% sun", f"battery stays above {FLOOR_PCT:.0f}%"


if __name__ == "__main__":
    main("smoke.py")
