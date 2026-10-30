"""The app that ships to the Orin: capture -> detect -> track -> alarm -> act -> upload.

    python3 -m app.main --config /opt/pole/app/config.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time

import numpy as np
import yaml

from app.alarm import LEVEL_NAMES, WARNING, AlarmFSM, Config, edge_distance, foot_pixel, ground_from_image
from app.detect import make_detector
from app.health import FrameSource, Health
from app.horn import Horn
from app.links import (FLOODLIGHT, LASER_POWER, STROBE, ArmLink, HexRelayAdapter, LineRelayAdapter,
                       MqttPublisher, Relays, SerialLine, Uplink, aim_angles)
from app.track import IoUTracker

log = logging.getLogger("main")


def load_homography(path, wait_s=120.0):
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return np.load(path)
        except (OSError, ValueError):
            if time.monotonic() > deadline:
                raise
            log.warning("waiting for calibration file %s", path)
            time.sleep(2)


def floodlight_due(hours, t=None):
    h, (a, b) = time.localtime(t).tm_hour, hours
    return (h >= a or h < b) if a > b else a <= h < b


def identity_provider(cfg):
    """The identify step's provider, or None when `identify.enabled` is false (v11). Phase 1 has
    no `identify` key and keeps identification on. When off, app.identify is never imported."""
    ident = cfg.get("identify", {"enabled": True})
    if not ident.get("enabled", True):
        return None
    from app.identify import make_provider
    return make_provider(ident)


class PoleApp:
    def __init__(self, cfg):
        self.cfg = cfg
        self.pole = str(cfg.get("pole_id", "00"))
        self.identity = identity_provider(cfg)
        self.H = load_homography(cfg["camera"]["homography"])
        self.pit = [tuple(p) for p in cfg["site"]["pit"]]
        self.fsm = AlarmFSM(Config(**cfg["alarm"]))
        dev = cfg["devices"]
        self.arm = ArmLink(SerialLine(dev["arm"]))
        adapter = HexRelayAdapter() if dev.get("relay_protocol") == "hex" else LineRelayAdapter()
        self.relays = Relays(SerialLine(dev["relay"]), adapter)
        self.horn = Horn(dev.get("audio_sink", "horn"))
        up = cfg["uplink"]
        self.mqtt = MqttPublisher(up["broker"], up["topic"], client_id=f"pole-{self.pole}")
        self.uplink = Uplink(up["queue"], self.mqtt)
        self.detector = make_detector(cfg["detector"])
        self.tracker = IoUTracker(max_age_s=cfg["alarm"]["clear_s"])
        self.source = FrameSource(cfg["camera"]["url"], cfg["camera"].get("lost_after_s", 3.0),
                                  cfg["camera"].get("size", (1280, 720)))
        self.health = Health(self.emit)
        self.feet, self.boxes, self.dist = {}, {}, {}
        self.started, self._status_t, self._seq = time.monotonic(), 0.0, 0
        self.h_sha = hashlib.sha1(np.ascontiguousarray(self.H).tobytes()).hexdigest()[:12]
        self.relays.set(STROBE, False)
        self.relays.set(LASER_POWER, False)
        self.relays.set(FLOODLIGHT, floodlight_due(cfg.get("floodlight_hours", (19, 7))))
        log.info("monitoring: pit %s, zone %.1f m, ring %.1f m", self.pit,
                 self.fsm.cfg.alarm_buffer_m, self.fsm.cfg.warn_buffer_m)

    # ------------------------------------------------------------------ outputs
    def emit(self, event):
        event = {"pole": self.pole, "ts": round(time.time(), 3), **event}
        self.uplink.put(event)
        log.info("event %s", json.dumps(event))

    def act(self, kind, pid, frame):
        level = self.fsm.level
        if kind == "caution":
            self.horn.chime()
        elif kind == "warning":
            if self.horn.on != "siren":
                self.horn.play("warning")
            self.relays.set(LASER_POWER, True)
        elif kind == "alarm":
            self.horn.play("siren")
            self.relays.set(STROBE, True)
        elif kind == "reset":
            self.horn.stop()
            self.relays.set(STROBE, False)
            self.relays.set(LASER_POWER, False)
            self.arm.park()
        event = {"kind": kind, "pid": pid, "level": level, "state": LEVEL_NAMES[level]}
        if pid is not None:
            person = self.fsm.people.get(pid)
            event["dist_m"] = round(self.dist.get(pid, person.dist if person else -1.0), 2)
            event["zone_s"] = round(self.fsm.zone_time(pid, time.monotonic()), 2)
        if kind == "alarm" and self.identity and frame is not None and pid in self.boxes:
            event["identity"] = self.identity.identify(frame, self.boxes[pid], pid)["result"]
        self.emit(event)

    def aim(self):
        targets = [pid for pid in self.fsm.inside() if pid in self.feet]
        if self.fsm.level >= WARNING and targets:
            pid = min(targets, key=lambda i: self.fsm.people[i].dist)
            a = self.cfg["arm"]
            pan, tilt = aim_angles(a["xy"], a["heading_deg"], a["pivot_h_m"], self.feet[pid])
            self.arm.point_at(pan, tilt, laser=True)
        else:
            self.arm.park()

    # ------------------------------------------------------------------ loop
    def step(self):
        frame, self._seq = self.source.get(self._seq, timeout=0.2)
        now = time.monotonic()
        camera_ok = self.health.check_camera(self.source, now)
        if frame is not None:
            boxes = self.detector.run(frame, now)
            self.boxes = self.tracker.update(boxes, now)
            self.feet = {**{i: f for i, f in self.feet.items() if i in self.fsm.people},
                         **{i: ground_from_image(self.H, *foot_pixel(b)) for i, b in self.boxes.items()}}
            self.dist = {i: edge_distance(*self.feet[i], self.pit) for i in self.boxes}
            for kind, pid in self.fsm.update(now, self.dist):
                self.act(kind, pid, frame)
        elif not camera_ok:
            self.dist = {}
            for kind, pid in self.fsm.update(now, {}):
                self.act(kind, pid, None)
        self.aim()
        self.arm.poll(now)
        self.relays.poll()
        self.uplink.flush(now)
        if now - self._status_t >= 1.0:
            self._status_t = now
            self.relays.set(FLOODLIGHT, floodlight_due(self.cfg.get("floodlight_hours", (19, 7))))
            self.write_status(now, camera_ok)

    def write_status(self, now, camera_ok):
        st = {"pole": self.pole, "ts": time.time(), "uptime_s": round(now - self.started, 1),
              "state": LEVEL_NAMES[self.fsm.level], "level": self.fsm.level,
              "people": [{"id": i, "dist_m": round(p.dist, 2), "zone_s": round(self.fsm.zone_time(i, now), 2)}
                         for i, p in self.fsm.people.items()],
              "camera_ok": camera_ok, "arm_online": self.arm.online(now), "arm_pos": self.arm.pos,
              "relays": {str(k): v for k, v in self.relays.state.items()}, "horn": self.horn.on,
              "queue": len(self.uplink), "zones": self.cfg["alarm"], "pit": self.pit, "homography_sha": self.h_sha}
        path = self.cfg.get("status_file")
        if path:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(st, f)
            os.replace(tmp, path)
        topic = self.cfg["uplink"].get("status_topic")
        if topic and self.mqtt.client.is_connected():
            self.mqtt.client.publish(topic, json.dumps(st), qos=0)

    def run(self):
        while True:
            self.step()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.yaml"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    PoleApp(cfg).run()


if __name__ == "__main__":
    main()
