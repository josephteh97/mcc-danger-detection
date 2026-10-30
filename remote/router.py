"""The v11 4G router with its Tailscale node, emulated.

- Subnet route: engineers in the tailnet's access list reach poe_lan (192.168.10.0/24) through
  this node. As in Tailscale's userspace-networking mode, the route is served as a SOCKS5 proxy
  on the node's tailnet address (port 1055): packets never cross from one Docker network to
  another, which Docker's internal networks would drop. Nobody outside the list is let through,
  and only LAN addresses can be reached. (The kernel route with SNAT is set up too, for a host
  that allows it.)
- Carrier-grade NAT: nothing answers on the 4G side; both remote paths are outbound.
- Its own PoE injector, so it stays up when the switch or the AI box hangs. It publishes its
  status to the cloud every few seconds, and its digital output drives the switch-restart relay
  (in the twin: a call to the dashboard, which plays the switch).
- Control endpoint on the tailnet only: POST /switch/restart, GET /status.
"""
import ipaddress
import json
import os
import select
import socket
import socketserver
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


class Socks(socketserver.BaseRequestHandler):
    """SOCKS5 CONNECT for the subnet route (no other commands, no auth: the ACL is the tailnet's)."""
    lan = ipaddress.ip_network(LAN)

    def handle(self):
        c = self.request
        if self.client_address[0] not in ACL:
            return
        try:
            head = c.recv(2)
            c.recv(head[1])                                   # offered auth methods
            c.sendall(b"\x05\x00")
            ver, cmd, _, atyp = c.recv(4)
            if atyp == 1:
                host = socket.inet_ntoa(c.recv(4))
            elif atyp == 3:
                host = c.recv(c.recv(1)[0]).decode()
            else:
                raise ValueError("address type")
            port = int.from_bytes(c.recv(2), "big")
            if cmd != 1 or ipaddress.ip_address(socket.gethostbyname(host)) not in self.lan:
                c.sendall(b"\x05\x02\x00\x01" + bytes(6))     # not allowed by the route
                return
            far = socket.create_connection((host, port), timeout=5)
        except (OSError, ValueError, IndexError):
            try:
                c.sendall(b"\x05\x04\x00\x01" + bytes(6))
            except OSError:
                pass
            return
        c.sendall(b"\x05\x00\x00\x01" + socket.inet_aton(far.getsockname()[0]) + far.getsockname()[1].to_bytes(2, "big"))
        far.settimeout(None)
        try:
            while True:
                r, _, _ = select.select([c, far], [], [], 600)
                if not r:
                    return
                for a in r:
                    data = a.recv(65536)
                    if not data:
                        return
                    (far if a is c else c).sendall(data)
        finally:
            far.close()


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
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socks = socketserver.ThreadingTCPServer((TAILNET_IP, 1055), Socks)
    socks.daemon_threads = True
    threading.Thread(target=socks.serve_forever, daemon=True).start()
    ThreadingHTTPServer((TAILNET_IP, 8022), Control).serve_forever()
