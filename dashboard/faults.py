"""Fault injection through the Docker API: one entry per row of the guide's fault table, plus
the v11 remote-management faults (switch hang, router-driven switch restart, site power cut).

Only the faults named here can run; anything else is rejected, so the dashboard never
exposes a general container API.
"""
from __future__ import annotations

import os
import time

PROJECT = os.environ.get("TWIN_PROJECT", "twin")
WAN = "$(ip -o -4 addr | awk '/172\\.30\\.4\\./{print $2}')"
ARM_BRIDGE = "socat TCP-LISTEN:7001,reuseaddr,fork FILE:/tmp/vdev/arm,raw,echo=0"
ARM_TCP = "python3 devices/arm_emulator.py --tcp 0.0.0.0:7001 --state /logs/arm.jsonl"
POE_LAN = {"camera": "192.168.10.20", "orin": "192.168.10.2", "devices": "192.168.10.24"}   # on the switch
SWITCH_BOOT_S = float(os.environ.get("TWIN_SWITCH_BOOT_S", "15"))

FAULTS = {                     # the guide's fault table (phase 1)
    "camera_cable": "Camera cable unplugged",
    "4g_weak": "4G weak (120 ms +-40 ms, 5% loss)",
    "4g_outage": "4G outage (100% loss)",
    "arm_usb": "Laser arm USB unplugged",
    "orin_hang": "Orin software hangs",
    "power_cut": "Power cut and restore",
}
V11_FAULTS = {                 # the v11 pole: Ethernet laser controller, PoE switch, site power
    "arm_usb": "Laser controller arm link down",
    "orin_hang": "AI box hangs (PoE watchdog power-cycles port 4)",
    "switch_hang": "PoE switch hangs (router stays up)",
    "switch_restart": "Router-driven switch restart",
    "site_power_cut": "Site power cut (battery and shutdown stages)",
}
# How the arm link is cut and restored: (pkill pattern, pgrep pattern of the running link, its command).
# Phase 1 uses the guide's command; the pgrep pattern is anchored so it cannot match our own shell.
ARM_LINK = {
    "phase1": ("TCP-LISTEN:7001", "^socat TCP-LISTEN:7001", ARM_BRIDGE),
    "v11": ("arm_emulator.py --tcp", "^python3 devices/arm_emulator.py --tcp", ARM_TCP),
}


class FaultError(RuntimeError):
    pass


class Faults:
    def __init__(self, profile="phase1", client=None):
        self._client = client
        self.profile = profile
        self.table = {**FAULTS, **(V11_FAULTS if profile == "v11" else {})}
        self.arm_kill, self.arm_alive, self.arm_cmd = ARM_LINK[profile]
        self.active = {}
        self.power_cut_plan = None

    @property
    def dk(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    def container(self, service):
        return self.dk.containers.get(f"{PROJECT}-{service}-1")

    def _exec(self, service, cmd, detach=False):
        res = self.container(service).exec_run(["sh", "-c", cmd], detach=detach)
        if not detach and res.exit_code not in (0, None):
            raise FaultError(f"{service}: '{cmd}' exited {res.exit_code}: {res.output.decode(errors='replace')[-200:]}")
        return res

    def _poe_lan(self):
        """The poe_lan network (fresh) and the names of the containers on it."""
        net = self.dk.networks.get(f"{PROJECT}_poe_lan")
        net.reload()
        return net, {c.name for c in net.containers}

    def inject(self, name):
        if name not in self.table:
            raise KeyError(name)
        if name == "camera_cable":
            self.dk.networks.get(f"{PROJECT}_poe_lan").disconnect(f"{PROJECT}-camera-1")
        elif name == "4g_weak":
            self._exec("orin", f"tc qdisc replace dev {WAN} root netem delay 120ms 40ms loss 5%")
        elif name == "4g_outage":
            self._exec("orin", f"tc qdisc replace dev {WAN} root netem loss 100%")
        elif name == "switch_hang":
            net, on = self._poe_lan()
            for svc in POE_LAN:
                if f"{PROJECT}-{svc}-1" in on:
                    net.disconnect(f"{PROJECT}-{svc}-1")
        elif name == "switch_restart":
            return self.switch_restart()
        elif name == "site_power_cut":
            self.power_cut_plan = site_power_cut()
        elif name == "arm_usb":            # run directly, not in a shell, so pkill cannot match our own shell
            res = self.container("devices").exec_run(["pkill", "-f", self.arm_kill])
            if res.exit_code not in (0, 1):
                raise FaultError(f"devices: pkill exited {res.exit_code}")
        elif name == "orin_hang":
            self.container("orin").pause()
        elif name == "power_cut":
            c = self.container("orin")
            if c.status == "paused":
                c.unpause()
            c.kill()
            time.sleep(1.0)
            c.start()
            return {"ok": True, "fault": name, "note": "killed and started again"}
        self.active[name] = time.time()
        return {"ok": True, "fault": name}

    def restore(self, name):
        if name not in self.table:
            raise KeyError(name)
        if name == "camera_cable":
            net, on = self._poe_lan()
            if f"{PROJECT}-camera-1" not in on:
                net.connect(f"{PROJECT}-camera-1", ipv4_address="192.168.10.20")
        elif name in ("4g_weak", "4g_outage"):
            self._exec("orin", f"tc qdisc del dev {WAN} root 2>/dev/null || true")
        elif name == "switch_hang":
            self._reconnect_switch()
        elif name == "switch_restart":
            pass
        elif name == "site_power_cut":
            self.power_cut_plan = None
        elif name == "arm_usb":
            self._exec("devices", f"pgrep -f '{self.arm_alive}' >/dev/null || exec {self.arm_cmd}", detach=True)
        elif name == "orin_hang":
            c = self.container("orin")
            if c.status == "paused":
                c.unpause()
        elif name == "power_cut":
            c = self.container("orin")
            if c.status != "running":
                c.start()
        self.active.pop(name, None)
        return {"ok": True, "fault": name, "restored": True}

    def _reconnect_switch(self):
        net, on = self._poe_lan()
        for svc, ip in POE_LAN.items():
            if f"{PROJECT}-{svc}-1" not in on:
                net.connect(f"{PROJECT}-{svc}-1", ipv4_address=ip)

    def switch_restart(self):
        """The router's digital output power-cycles the switch: it boots, then every poe_lan link is back."""
        t0 = time.time()
        time.sleep(SWITCH_BOOT_S)
        self._reconnect_switch()
        self.active.pop("switch_hang", None)
        return {"ok": True, "fault": "switch_restart", "links_back_s": round(time.time() - t0, 1)}

    def status(self):
        out = {}
        try:
            orin = self.container("orin")
            out["orin"] = orin.status
        except Exception as e:      # stack not running
            out["orin"] = f"unavailable: {e.__class__.__name__}"
        out["active"] = sorted(self.active)
        return out


def site_power_cut(plan=None):
    """What a site power cut does to the v11 pole from now: the socket goes off, the battery takes
    over and the shutdown stages follow (from the power profile, for the HUD)."""
    import catalog
    from devices.power_model import V11PowerConfig, simulate_v11
    site = catalog.load_site()
    plan = plan or os.environ.get("TWIN_POWER_PLAN", "A")
    r = simulate_v11(V11PowerConfig.from_site(site, plan), [1.0] * 4, socket_off=[(0, 96)])
    return {"plan": plan, "started": time.time(), "events": r["events"],
            "hours_without_alarm": round(r["hours_without_alarm"], 1)}
