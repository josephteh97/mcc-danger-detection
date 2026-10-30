"""The v11 4G router with its Tailscale node, emulated.

- Subnet route: engineers in the tailnet's access list reach poe_lan (192.168.10.0/24) through
  this node (SNAT, as a Tailscale subnet router does). Nobody else is forwarded.
- Carrier-grade NAT: nothing answers on the 4G side; both remote paths are outbound.
- Its own PoE injector, so it stays up when the switch or the AI box hangs. It publishes its
  status to the cloud every few seconds, and its digital output drives the switch-restart relay
  (in the twin: a call to the dashboard, which plays the switch).
- Control endpoint on the tailnet only: POST /switch/restart, GET /status.
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TAILNET_IP = os.environ.get("TAILNET_IP", "100.64.0.1")
ACL = [ip.strip() for ip in os.environ.get("TAILNET_ACL", "100.64.0.10").split(",") if ip.strip()]
LAN = os.environ.get("LAN_SUBNET", "192.168.10.0/24")
TAILNET = os.environ.get("TAILNET_SUBNET", "100.64.0.0/24")
CLOUD = os.environ.get("CLOUD_BROKER", "172.30.4.10")
TOPIC = os.environ.get("STATUS_TOPIC", "pole/07/router")
RELAY_WIRE = os.environ.get("SWITCH_RELAY_URL", "http://172.29.10.5:8080/api/v11/router/switch_restart")
STARTED = time.time()
STATE = {"switch_restarts": 0, "last_restart": None}


def iface(prefix):
    out = subprocess.run(["ip", "-o", "-4", "addr"], capture_output=True, text=True).stdout
    return next(line.split()[1] for line in out.splitlines() if f" {prefix}" in line)


def ipt(*args):
    subprocess.run(["iptables", *args], check=True)


def firewall():
    wan, lan, ts = iface("172.30.4."), iface("192.168.10."), iface(TAILNET_IP.rsplit(".", 1)[0] + ".")
    ipt("-P", "FORWARD", "DROP")
    ipt("-A", "FORWARD", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT")
    for ip in ACL:
        ipt("-A", "FORWARD", "-i", ts, "-o", lan, "-s", ip, "-d", LAN, "-j", "ACCEPT")
    ipt("-t", "nat", "-A", "POSTROUTING", "-o", lan, "-s", TAILNET, "-j", "MASQUERADE")
    ipt("-A", "INPUT", "-i", wan, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT")
    ipt("-A", "INPUT", "-i", wan, "-j", "DROP")          # CGNAT: no inbound port on 4G
    print(f"router: wan {wan}, lan {lan}, tailnet {ts}; subnet route {LAN} for {', '.join(ACL)}", flush=True)


def publish_status():
    while True:
        st = {"ts": round(time.time(), 3), "uptime_s": round(time.time() - STARTED, 1), **STATE}
        subprocess.run(["mosquitto_pub", "-h", CLOUD, "-t", TOPIC, "-q", "0", "-m", json.dumps(st)],
                       capture_output=True, timeout=5)
        time.sleep(3)


class Control(BaseHTTPRequestHandler):
    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self):
        if self.client_address[0] in ACL:
            return True
        self._reply(403, {"ok": False, "error": "not in the tailnet access list"})
        return False

    def do_GET(self):
        if self._allowed():
            self._reply(200, {"ok": True, "uptime_s": round(time.time() - STARTED, 1), **STATE})

    def do_POST(self):
        if not self._allowed():
            return
        if self.path != "/switch/restart":
            return self._reply(404, {"ok": False})
        req = urllib.request.Request(RELAY_WIRE, data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                result = json.loads(r.read() or b"{}")
        except Exception as e:                          # report, keep the router up
            return self._reply(502, {"ok": False, "error": f"{e.__class__.__name__}: {e}"})
        STATE["switch_restarts"] += 1
        STATE["last_restart"] = round(time.time(), 3)
        self._reply(200, {"ok": True, "switch": result})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    firewall()
    threading.Thread(target=publish_status, daemon=True).start()
    ThreadingHTTPServer((TAILNET_IP, 8022), Control).serve_forever()
