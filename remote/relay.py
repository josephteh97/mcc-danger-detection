"""The cloud relay, emulated: the superior's view of alarms, events and live video. The pole
only ever connects out to it: the AI box posts live-view snapshots here, and the relay reads
events from the cloud broker. The superior reads GET /events and GET /live.jpg."""
import json
import os
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLOUD = os.environ.get("CLOUD_BROKER", "172.30.4.10")
EVENTS, LIVE = deque(maxlen=200), {"jpg": None, "ts": None}


def follow_events():
    while True:
        p = subprocess.Popen(["mosquitto_sub", "-h", CLOUD, "-t", "pole/+/event", "-t", "pole/+/router"],
                             stdout=subprocess.PIPE, text=True)
        for line in p.stdout:
            try:
                EVENTS.append(json.loads(line))
            except ValueError:
                pass
        time.sleep(2)


class Relay(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/events":
            return self._send(200, json.dumps(list(EVENTS)[-50:]).encode(), "application/json")
        if self.path == "/live.jpg" and LIVE["jpg"]:
            return self._send(200, LIVE["jpg"], "image/jpeg")
        if self.path == "/status":
            return self._send(200, json.dumps({"events": len(EVENTS), "live_ts": LIVE["ts"]}).encode(), "application/json")
        self._send(404, b"", "text/plain")

    def do_POST(self):
        if self.path != "/live":
            return self._send(404, b"", "text/plain")
        LIVE["jpg"] = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        LIVE["ts"] = time.time()
        self._send(204, b"", "text/plain")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=follow_events, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Relay).serve_forever()
