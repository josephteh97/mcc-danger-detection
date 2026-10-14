"""Real-time loop for the world container: frames to stdout, truth over UDP, control in."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog                                         # noqa: E402
from world import weather as wx                        # noqa: E402
from world.controls import ControlServer, apply_message, parse_addr   # noqa: E402
from world.scene import SCENARIO_NAMES                 # noqa: E402
from world.world import World                          # noqa: E402


class TruthSender:
    """Sends each frame's ground truth to host:port targets, re-resolving names every 10 s."""

    def __init__(self, targets):
        self.targets = [parse_addr(t, "127.0.0.1") for t in targets if t]
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._resolved, self._when = {}, 0.0

    def send(self, msg):
        now = time.monotonic()
        if now - self._when > 10.0:
            self._when = now
            for host, port in self.targets:
                try:
                    self._resolved[(host, port)] = (socket.gethostbyname(host), port)
                except OSError:
                    self._resolved.pop((host, port), None)
        data = json.dumps(msg, separators=(",", ":")).encode()
        for addr in self._resolved.values():
            try:
                self.sock.sendto(data, addr)
            except OSError:
                pass


class JsonlTail:
    """Follows a JSONL file (the arm emulator's state log), surviving rotation."""

    def __init__(self, path):
        self.path, self.f, self.last = path, None, None

    def poll(self):
        if self.f is None:
            try:
                self.f = open(self.path)
                self.f.seek(0, os.SEEK_END)
            except OSError:
                return self.last
        try:
            if os.path.getsize(self.path) < self.f.tell():
                self.f.close()
                self.f = open(self.path)
        except OSError:
            self.f = None
            return self.last
        for line in self.f.readlines():
            try:
                self.last = json.loads(line)
            except ValueError:
                pass
        return self.last


def main(argv=None):
    ap = argparse.ArgumentParser(description="World simulator: frames to stdout, truth over UDP")
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--truth", default="", help="comma-separated host:port targets for ground truth")
    ap.add_argument("--weather", default="clear", help=f"one of: {', '.join(wx.NAMES)}")
    ap.add_argument("--scenario", default="idle", help=f"one of: {', '.join(SCENARIO_NAMES)}")
    ap.add_argument("--npcs", type=int, default=0, help="random passers-by")
    ap.add_argument("--control", help="UDP control address, e.g. 0.0.0.0:9200")
    ap.add_argument("--arm-state", help="arm emulator JSONL state file to draw the laser dot from")
    ap.add_argument("--site", help="site.yaml path")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--frames", type=int, help="stop after this many frames")
    ap.add_argument("--snapshot", help="write the first frame to this image file and exit")
    a = ap.parse_args(argv)
    try:
        wx.get_preset(a.weather)
    except ValueError as e:
        ap.error(str(e))

    world = World(catalog.load_site(a.site), weather=a.weather, seed=a.seed, npcs=a.npcs,
                  scenario=a.scenario)
    if a.snapshot:
        import cv2
        world.step(0.0)
        cv2.imwrite(a.snapshot, world.render()[0])
        return
    truth = TruthSender(a.truth.split(","))
    control = ControlServer(a.control) if a.control else None
    arm = JsonlTail(a.arm_state) if a.arm_state else None
    out = sys.stdout.buffer
    period, n = 1.0 / a.fps, 0
    next_t = last = time.monotonic()
    print(f"world: {world.W}x{world.H} at {a.fps:g} fps, weather {a.weather}, scenario {a.scenario}",
          file=sys.stderr, flush=True)
    while a.frames is None or n < a.frames:
        now = time.monotonic()
        world.step(min(0.5, now - last))
        last = now
        if control:
            for msg in control.poll():
                err = apply_message(world, msg)
                if err:
                    print(f"world: control: {err}", file=sys.stderr, flush=True)
        if arm:
            s = arm.poll()
            if s:
                world.arm = (float(s["pan"]), float(s["tilt"]), bool(s["laser"]))
        frame, info = world.render()
        truth.send(world.truth(info, time.time()))
        try:
            out.write(np.ascontiguousarray(frame).tobytes())
            out.flush()
        except BrokenPipeError:
            return
        n += 1
        next_t += period
        delay = next_t - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_t = time.monotonic()


if __name__ == "__main__":
    main()
