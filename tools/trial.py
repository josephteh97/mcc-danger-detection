"""Human trial mode: walk a worker with the arrow keys through the tested code path.

Person boxes from the picture -> homography -> distance to the pit edge -> app/alarm.py ->
laser aim from app/links.py, with the arm emulator's slew, interlock and watchdog.

    python3 -m tools.trial                                         # clear day, products from site.yaml
    python3 -m tools.trial --weather night_rain --camera dome_4mp_2_8mm_generic --npcs 1
    python3 -m tools.trial --miss-rate 0.1 --delay-ms 200          # a weaker detector
    python3 -m tools.trial --send <twin-host>:9200                 # keypad for the full stack
    python3 -m tools.trial --headless                              # scripted walk-in, prints the scorecard
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import catalog                                                        # noqa: E402
from app.alarm import (WARNING, AlarmFSM, Config, edge_distance,      # noqa: E402
                       foot_pixel, ground_from_image)
from app.detect import OracleDetector                                 # noqa: E402
from app.links import aim_angles, beam_ground_point                   # noqa: E402
from app.track import IoUTracker, iou                                 # noqa: E402
from devices.arm_emulator import ArmModel                             # noqa: E402
from world.world import World                                         # noqa: E402



def app_config(profile=None):
    with open(catalog.app_config_path(profile)) as f:
        return yaml.safe_load(f)


class Scorecard:
    """Every entry into the zone: stay, warning/alarm after entering, reset after leaving,
    and how far the laser dot was from the feet."""

    def __init__(self, alarm_buffer_m):
        self.buffer, self.entries, self.open, self.counts = alarm_buffer_m, [], {}, {}

    def on_truth(self, t, truth):
        seen = set()
        for w in truth["workers"]:
            seen.add(w["id"])
            inside = w["edge_m"] <= self.buffer
            e = self.open.get(w["id"])
            if inside and e is None:
                e = {"worker": w["id"], "entered_t": t, "left_t": None, "warning_t": None,
                     "alarm_t": None, "reset_t": None, "dot_m": []}
                self.entries.append(e)
                self.open[w["id"]] = e
            elif not inside and e is not None:
                e["left_t"] = t
                del self.open[w["id"]]
        for wid in [i for i in self.open if i not in seen]:     # walked off the site
            self.open.pop(wid)["left_t"] = t

    def on_event(self, t, kind, worker_id):
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if kind in ("warning", "alarm"):
            for e in reversed(self.entries):
                if e["worker"] == worker_id and e[f"{kind}_t"] is None:
                    e[f"{kind}_t"] = t
                    break
        elif kind == "reset":
            for e in self.entries:
                if e["left_t"] is not None and e["reset_t"] is None:
                    e["reset_t"] = t

    def on_dot(self, worker_id, dist_m):
        e = self.open.get(worker_id)
        if e is not None:
            e["dot_m"].append(dist_m)

    def summary(self):
        out = []
        for e in self.entries:
            def rel(key, base):
                return None if e[key] is None or e[base] is None else round(e[key] - e[base], 3)
            out.append({"worker": e["worker"],
                        "stay_s": rel("left_t", "entered_t"),
                        "warning_after_entering_s": rel("warning_t", "entered_t"),
                        "alarm_after_entering_s": rel("alarm_t", "entered_t"),
                        "reset_after_leaving_s": rel("reset_t", "left_t"),
                        "dot_to_feet_median_m": round(statistics.median(e["dot_m"]), 3) if e["dot_m"] else None})
        return {"events": dict(self.counts), "entries": out}


class TrialSession:
    """One trial: the world plus the app's tested pipeline on a simulated clock."""

    def __init__(self, weather="clear", camera=None, npcs=0, miss_rate=0.0, delay_ms=120, seed=0,
                 scenario="idle", fps=15, profile=None):
        site = catalog.load_site(overrides={"camera": camera} if camera else None, profile=profile)
        app_cfg = app_config(site["profile"])
        self.world = World(site, weather=weather, seed=seed, npcs=npcs, scenario=scenario)
        self.H, self.pit = self.world.homography(), self.world.pit
        self.fsm = AlarmFSM(Config(**app_cfg["alarm"]))
        self.detector = OracleDetector(None, delay_ms=delay_ms, jitter_ms=20 if delay_ms else 0,
                                       miss_rate=miss_rate, seed=seed)
        self.tracker = IoUTracker(max_age_s=self.fsm.cfg.clear_s)
        self.arm, self.arm_cfg = ArmModel(0.0), app_cfg["arm"]
        self.dt, self.t = 1.0 / fps, 0.0
        self.events, self.feet, self.dist, self.boxes = [], {}, {}, {}
        self.outputs = {"horn": None, "strobe": False, "laser_power": False}
        self.score = Scorecard(self.fsm.cfg.alarm_buffer_m)
        self.frame, self.info, self.truth = None, None, None

    def add_worker(self, xy=None):
        return self.world.scene.add_controlled(xy).id

    def worker(self, wid):
        return next((w for w in self.world.scene.workers if w.id == wid), None)

    def dot(self):
        if not self.arm.laser_on:
            return None
        a = self.arm_cfg
        return beam_ground_point(a["xy"], a["heading_deg"], a["pivot_h_m"], self.arm.pan, self.arm.tilt)

    def _true_worker_for(self, pid):
        box = self.boxes.get(pid)
        if box is None or self.truth is None:
            return None
        best = max(((iou(box, w["box"]), w["id"]) for w in self.truth["workers"] if w["box"]), default=(0, None))
        return best[1] if best[0] > 0.2 else None

    def _act(self, kind):
        o = self.outputs
        if kind == "warning":
            o["horn"] = o["horn"] if o["horn"] == "siren" else "warning"
            o["laser_power"] = True
        elif kind == "alarm":
            o["horn"], o["strobe"] = "siren", True
        elif kind == "reset":
            o.update(horn=None, strobe=False, laser_power=False)

    def step(self, keys=(), run=False):
        scene = self.world.scene
        if keys or scene.active_controlled is not None:
            scene.set_keys(keys, run)
        self.world.step(self.dt)
        self.t += self.dt
        self.world.arm = (self.arm.pan, self.arm.tilt, self.arm.laser_on)
        self.frame, self.info = self.world.render()
        self.truth = self.world.truth(self.info, self.t)
        self.score.on_truth(self.t, self.truth)
        self.detector.feed(self.truth, self.t)
        self.boxes = self.tracker.update(self.detector.run(None, self.t), self.t)
        self.feet = {i: f for i, f in self.feet.items() if i in self.fsm.people}
        self.feet.update({i: ground_from_image(self.H, *foot_pixel(b)) for i, b in self.boxes.items()})
        self.dist = {i: edge_distance(*self.feet[i], self.pit) for i in self.boxes}
        for kind, pid in self.fsm.update(self.t, self.dist):
            self.events.append((round(self.t, 3), kind, pid))
            self._act(kind)
            self.score.on_event(self.t, kind, self._true_worker_for(pid))
        targets = [p for p in self.fsm.inside() if p in self.feet]
        if self.fsm.level >= WARNING and targets:
            pid = min(targets, key=lambda i: self.fsm.people[i].dist)
            a = self.arm_cfg
            pan, tilt = aim_angles(a["xy"], a["heading_deg"], a["pivot_h_m"], self.feet[pid], a.get("tilt_stops_deg"))
            for cmd in (f"AIM {pan:.2f} {tilt:.2f}", "LASER 1", "HB"):
                self.arm.command(cmd, self.t)
        else:
            self.arm.command("HB", self.t)
            self.arm.command("PARK", self.t)
        self.arm.step(self.t)
        d = self.dot()
        if d is not None:
            near = [w for w in self.truth["workers"] if w["edge_m"] <= self.fsm.cfg.alarm_buffer_m]
            if near:
                w = min(near, key=lambda w: math.dist((w["x"], w["y"]), d))
                self.score.on_dot(w["id"], math.dist((w["x"], w["y"]), d))
        return self.truth

    def hold(self, keys, seconds, run=False):
        for _ in range(int(round(seconds / self.dt))):
            self.step(keys, run)

    def scorecard(self):
        return self.score.summary()

    def save_scorecard(self, settings):
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        path = os.path.join(ROOT, "logs", time.strftime("trial-%Y%m%d-%H%M%S.json"))
        with open(path, "w") as f:
            json.dump({"settings": settings, **self.scorecard(), "event_log": self.events}, f, indent=2)
        return path


def scripted_walk_in(session, stay_s=5.0):
    """The keyboard walk-in used by the checks: from 5 m south-west of the pit, walk 'left'
    (toward the pit, across the camera's view) into the zone, stand, then walk back out."""
    up, right = session.world.cam.ground_axes()
    start = right * 5.0                     # pit centre is the origin
    wid = session.add_worker((float(start[0]), float(start[1])))
    session.hold({"left"}, 3.4)
    session.hold(set(), stay_s)
    session.hold({"right"}, 3.4)
    session.hold(set(), 3.0)
    return wid


def main(argv=None):
    ap = argparse.ArgumentParser(description="Human trial mode: walk the worker with the arrow keys")
    ap.add_argument("--weather", default="clear")
    ap.add_argument("--camera", help="camera product to fit instead of site.yaml's")
    ap.add_argument("--npcs", type=int, default=0)
    ap.add_argument("--miss-rate", type=float, default=0.02)
    ap.add_argument("--delay-ms", type=float, default=120)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--send", metavar="HOST:PORT", help="keypad mode: send keys to a world's control port")
    ap.add_argument("--headless", action="store_true", help="run a scripted walk-in and print the scorecard")
    a = ap.parse_args(argv)
    if a.send:
        from tools.trial_ui import run_sender
        return run_sender(a.send)
    session = TrialSession(a.weather, a.camera, a.npcs, a.miss_rate, a.delay_ms, a.seed)
    settings = {k: getattr(a, k) for k in ("weather", "camera", "npcs", "miss_rate", "delay_ms", "seed")}
    if a.headless:
        scripted_walk_in(session)
    else:
        from tools.trial_ui import run_window
        run_window(session)
    path = session.save_scorecard(settings)
    print(json.dumps(session.scorecard(), indent=2))
    print(f"scorecard saved to {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
