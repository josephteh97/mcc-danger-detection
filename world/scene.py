"""Workers and scripted scenarios on the site (ground metres, simulated seconds)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

WALK_MS, RUN_MS = 1.4, 3.0
POSTURE_H = {"walk": 1.78, "stand": 1.78, "squat": 1.0, "kneel": 1.2}   # height in metres
DOWN = ("squat", "kneel")                  # postures that do not move until the worker stands up
KEY_TIMEOUT_S = 0.5
BODY_RADIUS_M = 0.28          # footprint radius used to keep workers inside the hoarding


@dataclass
class Worker:
    id: int
    x: float
    y: float
    path: list = field(default_factory=list)   # [(x, y, wait_s), ...] still to walk
    speed: float = WALK_MS
    start_at: float = 0.0                      # scripted workers appear at this time
    controlled: bool = False
    npc: bool = False
    keys: frozenset = frozenset()
    run: bool = False
    keys_t: float = -1e9                       # when the last key message arrived
    wait_until: float = 0.0
    gone: bool = False
    heading: float = 0.0
    down: str = None                           # "squat" or "kneel" while down, else None
    moving: bool = False

    def active(self, t):
        return not self.gone and t >= self.start_at

    @property
    def posture(self):
        return self.down or ("walk" if self.moving else "stand")

    @property
    def height_m(self):
        return POSTURE_H[self.posture]


def _walk(pts, wait=None, posture=None):
    """Waypoints [(x, y, wait_s, posture while waiting)]."""
    wait, posture = wait or {}, posture or {}
    return [(x, y, wait.get(i, 0.0), posture.get(i)) for i, (x, y) in enumerate(pts)]


# Scripted scenarios. Pit spans x -1.2..1.2, y -0.8..0.8; the camera stands at (-6.9, 4.0)
# looking south-east, so (0.6, -1.6) is 0.8 m from the pit edge and about 9 m from the mast.
SCENARIOS = {
    "single_walk_in": lambda: [
        dict(start=(6.0, -6.0), path=_walk([(0.6, -1.6), (6.0, -6.0), (10.0, -8.2)], {0: 6.0}))],
    "two_workers": lambda: [
        dict(start=(6.0, -6.0), path=_walk([(0.6, -1.6), (6.0, -6.0), (10.0, -8.2)], {0: 8.0})),
        dict(start=(-3.0, -7.0), start_at=3.0,
             path=_walk([(-1.6, -1.8), (-3.0, -7.0), (-6.0, -8.2)], {0: 10.0}))],
    "passer_by_ring_edge": lambda: [
        dict(start=(-8.0, -3.7), path=_walk([(8.0, -3.7), (11.0, -3.7)]))],
    "stops_1_6m": lambda: [
        dict(start=(6.0, -6.0), path=_walk([(0.0, -2.4), (6.0, -6.0), (10.0, -8.2)], {0: 20.0}))],
    "hidden_behind_another": lambda: [
        dict(start=(6.0, -6.0), path=_walk([(0.6, -1.6), (6.0, -6.0), (10.0, -8.2)], {0: 10.0})),
        dict(start=(6.5, -5.2), start_at=1.0,
             path=_walk([(1.32, -2.14), (6.5, -5.2), (10.0, -7.0)], {0: 8.0}))],
    # A worker who squats at the far edge of the warning ring (north of the pit, the far side
    # from the v11 stand), then steps into the 1.5 m zone and squats again until the alarm.
    "squat_far_edge": lambda: [
        dict(start=(6.0, 6.0), path=_walk([(0.0, 3.6), (0.0, 2.1), (6.0, 6.0), (10.0, 8.2)],
                                          {0: 4.0, 1: 8.0}, {0: "squat", 1: "squat"}))],
}
SCENARIO_NAMES = list(SCENARIOS) + ["demo_loop", "idle"]


class Scene:
    def __init__(self, boundary, pit, seed=0):
        self.boundary = np.asarray(boundary, dtype=np.float64)
        self.pit = pit
        self.workers, self.t, self._next_id = [], 0.0, 1
        self.rng = np.random.default_rng(seed)
        self.scenario, self._loop_next, self.npcs = "idle", None, 0
        self.active_controlled = None

    # ------------------------------------------------------------------ setup
    def _new_id(self):
        self._next_id += 1
        return self._next_id - 1

    def reset(self, scenario=None):
        """Clear the site and start `scenario` (or restart the current one)."""
        scenario = scenario or self.scenario
        if scenario not in SCENARIO_NAMES:
            raise ValueError(f"unknown scenario '{scenario}'; valid: {', '.join(SCENARIO_NAMES)}")
        self.workers, self.scenario, self.active_controlled = [], scenario, None
        self._loop_next = None
        if scenario == "demo_loop":
            self._loop_next = self.t
        elif scenario in SCENARIOS:
            self._spawn(SCENARIOS[scenario]())

    def _spawn(self, specs):
        for s in specs:
            self.workers.append(Worker(self._new_id(), *s["start"], path=list(s["path"]),
                                       start_at=self.t + s.get("start_at", 0.0)))

    def add_controlled(self, xy=None):
        x, y = xy if xy is not None else (6.0, -6.0)
        w = Worker(self._new_id(), x, y, controlled=True)
        self.workers.append(w)
        self.active_controlled = w.id
        return w

    def switch_controlled(self):
        ids = [w.id for w in self.workers if w.controlled and not w.gone]
        if not ids:
            return None
        i = ids.index(self.active_controlled) if self.active_controlled in ids else -1
        self.active_controlled = ids[(i + 1) % len(ids)]
        return self.active_controlled

    def toggle_posture(self, posture, worker_id=None):
        """C (squat) or K (kneel): go down, or stand up if already in that posture."""
        if posture not in DOWN:
            raise ValueError(f"unknown posture {posture!r} (squat or kneel)")
        wid = worker_id if worker_id is not None else self.active_controlled
        for w in self.workers:
            if w.id == wid and w.controlled:
                w.down = None if w.down == posture else posture
                w.moving = False
                return w
        return None

    def set_keys(self, keys, run=False, worker_id=None):
        wid = worker_id if worker_id is not None else self.active_controlled
        if wid is None:
            wid = self.add_controlled().id
        for w in self.workers:
            if w.id == wid and w.controlled:
                w.keys, w.run, w.keys_t = frozenset(keys), bool(run), self.t
                return w
        return None

    # ------------------------------------------------------------------ motion
    def inside_site(self, x, y):
        (x0, y0), (x1, y1) = self.boundary.min(axis=0), self.boundary.max(axis=0)
        return (x0 + BODY_RADIUS_M <= x <= x1 - BODY_RADIUS_M) and (y0 + BODY_RADIUS_M <= y <= y1 - BODY_RADIUS_M)

    def clamp_to_site(self, x, y):
        (x0, y0), (x1, y1) = self.boundary.min(axis=0), self.boundary.max(axis=0)
        r = BODY_RADIUS_M
        return min(max(x, x0 + r), x1 - r), min(max(y, y0 + r), y1 - r)

    def step(self, dt, up_vec, right_vec):
        """Advance time by dt. up_vec/right_vec: ground directions of the picture's up/right."""
        self.t += dt
        if self._loop_next is not None and self.t >= self._loop_next:
            self._spawn(SCENARIOS["single_walk_in"]())
            self._loop_next = self.t + 40.0
        self._spawn_npcs()
        for w in self.workers:
            if not w.active(self.t):
                continue
            if w.controlled:
                self._step_controlled(w, dt, up_vec, right_vec)
            else:
                self._step_scripted(w, dt)
        self.workers = [w for w in self.workers if not w.gone]

    def _step_controlled(self, w, dt, up_vec, right_vec):
        if self.t - w.keys_t > KEY_TIMEOUT_S:      # dropped link: stop walking
            w.keys = frozenset()
        k = w.keys
        vy = (1 if "up" in k else 0) - (1 if "down" in k else 0)
        vx = (1 if "right" in k else 0) - (1 if "left" in k else 0)
        w.moving = False
        if (vx == 0 and vy == 0) or w.down:            # squatting or kneeling: no movement
            return
        w.moving = True
        v = vy * np.asarray(up_vec) + vx * np.asarray(right_vec)
        v = v / np.linalg.norm(v)
        speed = RUN_MS if w.run else WALK_MS
        w.heading = math.atan2(v[1], v[0])
        w.x, w.y = self.clamp_to_site(w.x + v[0] * speed * dt, w.y + v[1] * speed * dt)

    def _step_scripted(self, w, dt):
        if self.t < w.wait_until:
            w.moving = False
            return
        w.down, w.moving = None, True
        while dt > 0 and w.path:
            tx, ty, wait, *posture = w.path[0]
            dx, dy = tx - w.x, ty - w.y
            dist = math.hypot(dx, dy)
            step = w.speed * dt
            if dist <= step:
                w.x, w.y = tx, ty
                dt -= dist / w.speed
                w.path.pop(0)
                if wait > 0:
                    w.wait_until = self.t + wait
                    w.down = posture[0] if posture and posture[0] in DOWN else None
                    w.moving = False
                    return
            else:
                w.heading = math.atan2(dy, dx)
                w.x, w.y = w.x + dx / dist * step, w.y + dy / dist * step
                return
        if not w.path:
            w.gone = True

    def _spawn_npcs(self):
        alive = sum(1 for w in self.workers if w.npc)
        while alive < self.npcs:
            (x0, y0), (x1, y1) = self.boundary.min(axis=0) + 0.5, self.boundary.max(axis=0) - 0.5
            side = self.rng.integers(4)
            a = [(x0, self.rng.uniform(y0, y1)), (x1, self.rng.uniform(y0, y1)),
                 (self.rng.uniform(x0, x1), y0), (self.rng.uniform(x0, x1), y1)][side]
            b = [(x1, self.rng.uniform(y0, y1)), (x0, self.rng.uniform(y0, y1)),
                 (self.rng.uniform(x0, x1), y1), (self.rng.uniform(x0, x1), y0)][side]
            w = Worker(self._new_id(), *a, path=[(b[0], b[1], 0.0, None)], npc=True,
                       speed=float(self.rng.uniform(1.0, 1.6)), start_at=self.t + float(self.rng.uniform(0, 8)))
            self.workers.append(w)
            alive += 1
