"""Zone geometry and the alarm state machine.

Everything here is a pure function or a deterministic state machine driven by the caller's
clock, so it can be tested without hardware or wall-clock time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MONITORING, WARNING, ALARM = 0, 1, 2
LEVEL_NAMES = {MONITORING: "monitoring", WARNING: "warning", ALARM: "alarm"}


def foot_pixel(box):
    """Bottom-centre of a person box (x0, y0, x1, y1): the pixel taken as their feet."""
    x0, _, x1, y1 = box
    return (x0 + x1) / 2.0, float(y1)


def ground_from_image(H, u, v):
    """Map an image pixel to ground metres with the image-to-ground homography H (3x3)."""
    x = H[0][0] * u + H[0][1] * v + H[0][2]
    y = H[1][0] * u + H[1][1] * v + H[1][2]
    w = H[2][0] * u + H[2][1] * v + H[2][2]
    return x / w, y / w


def point_in_polygon(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                inside = not inside
    return inside


def _segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def edge_distance(x, y, pit):
    """Distance in metres from a ground point to the nearest pit edge; 0 inside the pit."""
    if point_in_polygon(x, y, pit):
        return 0.0
    n = len(pit)
    return min(_segment_distance(x, y, *pit[i], *pit[(i + 1) % n]) for i in range(n))


@dataclass
class Config:
    alarm_buffer_m: float = 1.5     # the zone
    warn_buffer_m: float = 3.0      # the caution ring
    dwell_s: float = 1.0            # in the zone this long -> warning
    escalate_s: float = 3.0         # in the zone this long (from entry) -> alarm
    clear_s: float = 2.0            # zone empty this long -> reset; also how long a person is kept


@dataclass
class _Person:
    last_seen: float
    inside: bool = False            # inside the zone at the last sighting
    in_ring: bool = False           # inside the caution ring at the last sighting
    cautioned: bool = False
    last_in_ring: float | None = None
    entered: float | None = None    # when this person entered the zone (kept through short gaps)
    last_inside: float | None = None
    warned: bool = False
    alarmed: bool = False
    dist: float = math.inf


@dataclass
class AlarmFSM:
    """Turns per-person edge distances into caution / warning / alarm / reset events.

    - caution: once per person when they come within warn_buffer_m (again only after they
      have been outside the ring for clear_s)
    - warning: a person has been in the zone (alarm_buffer_m) for dwell_s -> level >= 1
    - alarm:   a person has been in the zone for escalate_s since entering -> level 2
    - reset:   level >= 1 and nobody has been seen in the zone for clear_s -> level 0
    A person is kept for clear_s after their last sighting, so a missed detection neither
    repeats the caution nor restarts their dwell timer.
    """

    cfg: Config = field(default_factory=Config)
    level: int = MONITORING
    people: dict = field(default_factory=dict)
    _last_inside_t: float | None = None

    def update(self, now, dist):
        """dist: {person_id: edge distance in metres} for the people seen this frame."""
        cfg, events = self.cfg, []
        for pid, d in dist.items():
            p = self.people.get(pid)
            if p is None:
                p = self.people[pid] = _Person(last_seen=now)
            p.last_seen, p.dist = now, d
            p.in_ring = d <= cfg.warn_buffer_m
            p.inside = d <= cfg.alarm_buffer_m
            if p.in_ring:
                p.last_in_ring = now
                if not p.cautioned:
                    p.cautioned = True
                    events.append(("caution", pid))
            if p.inside:
                if p.entered is None:
                    p.entered = now
                p.last_inside = now
                self._last_inside_t = now

        for pid in list(self.people):
            p = self.people[pid]
            if now - p.last_seen > cfg.clear_s:          # not seen for clear_s: forget them
                del self.people[pid]
                continue
            if p.cautioned and not p.in_ring and now - (p.last_in_ring or now) >= cfg.clear_s:
                p.cautioned = False
            if p.entered is not None and not p.inside and now - p.last_inside >= cfg.clear_s:
                p.entered, p.warned, p.alarmed = None, False, False
            if p.entered is None or not p.inside:
                continue
            in_zone = now - p.entered
            if not p.warned and in_zone >= cfg.dwell_s - 1e-9:
                p.warned = True
                self.level = max(self.level, WARNING)
                events.append(("warning", pid))
            if not p.alarmed and in_zone >= cfg.escalate_s - 1e-9:
                p.alarmed = True
                self.level = ALARM
                events.append(("alarm", pid))

        if (self.level >= WARNING and self._last_inside_t is not None
                and now - self._last_inside_t >= cfg.clear_s - 1e-9):
            self.level = MONITORING
            for p in self.people.values():
                p.warned = p.alarmed = False
                if not p.inside:
                    p.entered = None
            events.append(("reset", None))
        return events

    def zone_time(self, pid, now):
        """Seconds the person has been in the zone, or 0 if they are not in it."""
        p = self.people.get(pid)
        if p is None or p.entered is None or not p.inside:
            return 0.0
        return now - p.entered

    def inside(self):
        """IDs of tracked people whose last sighting was inside the zone."""
        return [pid for pid, p in self.people.items() if p.inside]
