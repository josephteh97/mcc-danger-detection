"""Live state for the dashboard: ground truth (UDP), arm and relay logs, the app's MQTT events,
plus the run recorder that keeps every run in /logs/run-<time>/ for frame-by-frame replay."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import threading
import time

from app.links import beam_ground_point

RUN_MAX_S, RUNS_KEPT = 15 * 60, 20


class Recorder:
    def __init__(self, logs):
        self.logs, self.dir, self.started, self._files = logs, None, 0.0, {}
        self._lock = threading.Lock()

    def new_run(self, label):
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files = {}
            name = time.strftime("run-%Y%m%d-%H%M%S-") + "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
            self.dir = os.path.join(self.logs, name)
            os.makedirs(self.dir, exist_ok=True)
            with open(os.path.join(self.dir, "meta.json"), "w") as f:
                json.dump({"label": label, "started": time.time()}, f)
            self.started = time.monotonic()
            runs = sorted(d for d in os.listdir(self.logs) if d.startswith("run-"))
            for old in runs[:-RUNS_KEPT]:
                shutil.rmtree(os.path.join(self.logs, old), ignore_errors=True)
            return name

    def write(self, kind, obj):
        if self.dir is None:
            return
        if time.monotonic() - self.started > RUN_MAX_S:
            self.new_run("continued")
        with self._lock:
            f = self._files.get(kind)
            if f is None:
                f = self._files[kind] = open(os.path.join(self.dir, f"{kind}.jsonl"), "a", buffering=1)
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def list_runs(self):
        out = []
        for d in sorted((d for d in os.listdir(self.logs) if d.startswith("run-")), reverse=True):
            meta = {}
            try:
                with open(os.path.join(self.logs, d, "meta.json")) as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                pass
            out.append({"id": d, **meta})
        return out

    def load_run(self, run_id, max_frames=4000):
        path = os.path.join(self.logs, os.path.basename(run_id))
        if not run_id.startswith("run-") or not os.path.isdir(path):
            raise FileNotFoundError(run_id)

        def read(kind):
            try:
                with open(os.path.join(path, f"{kind}.jsonl")) as f:
                    return [json.loads(line) for line in f if line.strip()]
            except OSError:
                return []
        truth = read("truth")
        step = max(1, len(truth) // max_frames)
        return {"id": run_id, "truth": truth[::step], "events": read("events"), "arm": read("arm"), "relay": read("relay")}


class Tail:
    def __init__(self, path):
        self.path, self.f = path, None

    def lines(self):
        if self.f is None:
            try:
                self.f = open(self.path)
                self.f.seek(0, os.SEEK_END)
            except OSError:
                return []
        try:
            if os.path.getsize(self.path) < self.f.tell():
                self.f.close()
                self.f = open(self.path)
        except OSError:
            self.f = None
            return []
        out = []
        for line in self.f.readlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out


class Live:
    def __init__(self, site, logs="/logs", broker="172.30.4.10", pole_id="07", world_control="world:9200"):
        self.site, self.logs, self.broker, self.pole = site, logs, broker, pole_id
        host, _, port = world_control.rpartition(":")
        self.control_addr = (host, int(port))
        self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.state = {"truth": None, "arm": None, "relay": None, "dot": None, "events": [], "status": None,
                      "mqtt": False, "run": None, "weather": None, "scenario": None}
        self.recorder = Recorder(logs)
        self._mqtt = None

    # -------------------------------------------------------------- inputs
    def on_truth(self, msg):
        self.state["truth"] = msg
        self.state["weather"], self.state["scenario"] = msg.get("weather"), msg.get("scenario")
        self.recorder.write("truth", msg)

    def on_arm(self, s):
        self.state["arm"] = s
        a = self.site["arm"]
        self.state["dot"] = (beam_ground_point(a["xy"], a["heading_deg"], a["pivot_h_m"], s["pan"], s["tilt"])
                             if s.get("laser") else None)
        self.recorder.write("arm", s)

    def on_relay(self, s):
        self.state["relay"] = s
        self.recorder.write("relay", s)

    def on_event(self, ev):
        self.state["events"] = (self.state["events"] + [ev])[-50:]
        self.recorder.write("events", ev)

    # -------------------------------------------------------------- tasks
    async def run_truth(self, port=9100):
        loop = asyncio.get_running_loop()
        live = self

        class Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                try:
                    live.on_truth(json.loads(data))
                except ValueError:
                    pass
        await loop.create_datagram_endpoint(Proto, local_addr=("0.0.0.0", port))

    async def run_tails(self):
        arm, relay = Tail(os.path.join(self.logs, "arm.jsonl")), Tail(os.path.join(self.logs, "relay.jsonl"))
        while True:
            for s in arm.lines():
                self.on_arm(s)
            for s in relay.lines():
                self.on_relay(s)
            await asyncio.sleep(0.05)

    def start_mqtt(self):
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twin-dashboard")
        live = self

        def on_connect(client, userdata, flags, rc, props=None):
            live.state["mqtt"] = True
            client.subscribe("pole/+/event", qos=1)
            client.subscribe("pole/+/status", qos=0)

        def on_disconnect(client, userdata, flags, rc, props=None):
            live.state["mqtt"] = False

        def on_message(client, userdata, msg):
            try:
                body = json.loads(msg.payload)
            except ValueError:
                return
            if msg.topic.endswith("/status"):
                live.state["status"] = body
            else:
                body["received"] = time.time()
                live.on_event(body)
        c.on_connect, c.on_disconnect, c.on_message = on_connect, on_disconnect, on_message
        c.reconnect_delay_set(1, 10)
        c.connect_async(self.broker, 1883, keepalive=10)
        c.loop_start()
        self._mqtt = c

    def control(self, msg):
        try:
            self.ctrl_sock.sendto(json.dumps(msg).encode(), self.control_addr)
            return True
        except OSError:
            return False

    def snapshot(self):
        return self.state
