"""UDP control channel for the world: held keys for a controlled worker, plus weather,
scenario and worker commands. One JSON object per datagram.

    {"cmd": "keys", "keys": ["up", "left"], "run": false}   # repeat ~10 times a second
    {"cmd": "add_worker"} | {"cmd": "switch"} | {"cmd": "reset"}
    {"cmd": "posture", "posture": "squat"|"kneel"}            # C / K: go down or stand up
    {"cmd": "weather", "name": "night_rain"} | {"cmd": "scenario", "name": "single_walk_in"}
    {"cmd": "npcs", "n": 2}

A controlled worker stops if no key message has arrived for 0.5 s.
"""
from __future__ import annotations

import json
import socket
import time

VALID_KEYS = {"up", "down", "left", "right"}


def parse_addr(addr, default_host="0.0.0.0"):
    host, _, port = addr.rpartition(":")
    return (host or default_host), int(port)


class ControlServer:
    def __init__(self, addr):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(parse_addr(addr))
        self.sock.setblocking(False)

    @property
    def port(self):
        return self.sock.getsockname()[1]

    def poll(self):
        msgs = []
        while True:
            try:
                data, _ = self.sock.recvfrom(4096)
            except (BlockingIOError, InterruptedError):
                break
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and "cmd" in msg:
                    msgs.append(msg)
            except ValueError:
                pass
        return msgs

    def close(self):
        self.sock.close()


def apply_message(world, msg):
    """Apply one control message to a World. Returns an error string or None."""
    cmd = msg.get("cmd")
    try:
        if cmd == "keys":
            keys = [k for k in msg.get("keys", []) if k in VALID_KEYS]
            world.scene.set_keys(keys, run=bool(msg.get("run")), worker_id=msg.get("worker"))
        elif cmd == "posture":
            world.scene.toggle_posture(str(msg.get("posture")), worker_id=msg.get("worker"))
        elif cmd == "add_worker":
            world.scene.add_controlled()
        elif cmd == "switch":
            world.scene.switch_controlled()
        elif cmd == "reset":
            world.scene.reset()
        elif cmd == "weather":
            world.set_weather(str(msg.get("name")))
        elif cmd == "scenario":
            world.scene.reset(str(msg.get("name")))
        elif cmd == "npcs":
            world.scene.npcs = max(0, min(10, int(msg.get("n", 0))))
        else:
            return f"unknown command {cmd!r}"
    except ValueError as e:
        return str(e)
    return None


def send(addr, msg, sock=None):
    own = sock is None
    sock = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(json.dumps(msg).encode(), parse_addr(addr, "127.0.0.1"))
    finally:
        if own:
            sock.close()


def send_keys(addr, keys, run=False, duration_s=1.0, rate_hz=10.0, worker=None):
    """Hold `keys` for duration_s, sending them rate_hz times a second (like the keypad)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg = {"cmd": "keys", "keys": list(keys), "run": run}
    if worker is not None:
        msg["worker"] = worker
    end = time.monotonic() + duration_s
    try:
        while time.monotonic() < end:
            send(addr, msg, sock)
            time.sleep(1.0 / rate_hz)
    finally:
        sock.close()
