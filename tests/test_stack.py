"""Full-stack checks against `docker compose up` (V12-V18 and the fault table).

    docker compose up -d --build
    pytest tests/ -v --junitxml=reports/twin-$(date +%F).xml
"""
import ipaddress
import json
import math
import os
import shutil
import subprocess
import time

import pytest

from conftest import DASHBOARD, PROJECT, zone_crossings

FRAME = 1 / 15
DASHBOARD_WS = os.environ.get("TWIN_DASHBOARD", "http://127.0.0.1:8080").replace("http", "ws", 1) + "/live"


def walk_in(stack, scenario="single_walk_in", seconds=16):
    run = stack.scenario(scenario)
    t0 = time.time()
    time.sleep(seconds)
    return run, t0


def test_V12_end_to_end_alarm_latency(stack):
    """Sound starts within 1.5 s of crossing into the zone + dwell, measured at the horn sink."""
    run, t0 = walk_in(stack, seconds=12)
    entries = zone_crossings(stack.run_log(run, "truth"))
    assert entries, "the worker never entered the zone"
    t_enter = entries[0][0]
    sounds = [t for t in stack.horn_sounds(t0) if t >= t_enter + 0.5]   # skip the caution chime
    assert sounds, "no warning sound recorded at the horn sink"
    latency = sounds[0] - (t_enter + 1.0)
    print(f"V12: warning sound {sounds[0] - t_enter:.2f} s after entering; {latency:.2f} s after zone + dwell")
    assert latency <= 1.5


def test_V13_orin_hang_laser_off(stack):
    """Laser off within 2 s of docker pause (2 s after the last heartbeat, which is at most one frame earlier)."""
    stack.scenario("idle")       # the previous walk-in may still hold the laser on; start from off
    stack.wait_for(lambda: not (stack.state().get("arm") or {}).get("laser"), 15, 0.1, "the laser off")
    stack.scenario("single_walk_in")
    stack.wait_for(lambda: (stack.state().get("arm") or {}).get("laser"), 20, 0.05, "the laser on")
    t_pause = time.time()
    stack.c("orin").pause()
    try:
        time.sleep(3.0)
        arm = [a for a in stack.run_log(stack.state()["run"], "arm") if a["t"] >= t_pause]
        off = next((a for a in arm if not a["laser"]), None)
        assert off is not None, "laser still on 3 s after the pause"
        dt = off["t"] - t_pause
        print(f"V13: laser off {dt:.2f} s after docker pause (watchdog={off['watchdog']})")
        assert off["watchdog"] and dt <= 2.0 + FRAME + 0.05
    finally:
        stack.c("orin").unpause()
    status = stack.wait_for(lambda: (s := stack.orin_status()) and time.time() - s["ts"] < 2 and s, 15, 0.5, "the app to resume")
    assert status["state"] in ("monitoring", "warning", "alarm")


def test_V14_camera_cable_cut(stack):
    """'Camera offline' health alert within 10 s, and frames again after the cable is back."""
    stack.scenario("idle")
    t_cut = time.time()
    stack.fault("camera_cable")
    try:
        ev = stack.wait_for(lambda: next((e for e in stack.state()["events"] if e.get("what") == "camera_offline"
                                          and e["ts"] >= t_cut), None), 15, 0.25, "the camera offline alert")
        print(f"V14: camera offline alert {ev['ts'] - t_cut:.1f} s after the cut")
        assert ev["ts"] - t_cut <= 10
    finally:
        stack.fault("camera_cable", restore=True)
    stack.wait_for(lambda: (s := stack.orin_status()) and s["camera_ok"], 60, 1, "frames after reconnecting")


def test_V15_two_workers(stack):
    """Laser follows the worker inside; the alarm clears only when both are clear."""
    run, _ = walk_in(stack, "two_workers", seconds=26)
    truth, arm = stack.run_log(run, "truth"), stack.run_log(run, "arm")
    events = [e for e in stack.run_log(run, "events") if e.get("kind") in ("warning", "alarm", "reset")]
    crossings = zone_crossings(truth)
    last_exit = max(c[1] for c in crossings if c[1] is not None)
    resets = [e["ts"] for e in events if e["kind"] == "reset"]
    assert len(resets) == 1 and resets[0] >= last_exit + 1.9, f"resets {resets}, last exit {last_exit}"
    site = __import__("catalog").load_site(profile=stack.profile)["arm"]
    from app.links import beam_ground_point
    bad = n = 0
    for a in arm:
        if not a["laser"]:
            continue
        frame = min(truth, key=lambda m: abs(m["t"] - a["t"]))
        inside = [w for w in frame["workers"] if w["edge_m"] <= 1.5]
        if len(frame["workers"]) != 2 or len(inside) != 1 or abs(a["pan"] - a["target"][0]) > 1 or abs(a["tilt"] - a["target"][1]) > 1:
            continue                                   # skip transients (arm still slewing)
        dot = beam_ground_point(site["xy"], site["heading_deg"], site["pivot_h_m"], a["pan"], a["tilt"])
        near = min(frame["workers"], key=lambda w: math.dist((w["x"], w["y"]), dot))
        n += 1
        bad += near["edge_m"] > 1.5
    print(f"V15: laser on the worker inside in {n - bad}/{n} settled arm reports; reset {resets[0] - last_exit:.1f} s after the last left")
    assert n > 0 and bad == 0


def test_V16_restart_after_power_cut(stack):
    """Back to Monitoring within 60 s with the same zone settings."""
    before = stack.wait_monitoring()
    t_cut = time.time()
    stack.fault("power_cut")
    after = stack.wait_for(lambda: (s := stack.orin_status()) and s["ts"] > t_cut and s.get("state") == "monitoring" and s,
                           60, 0.5, "Monitoring after the power cut")
    print(f"V16: back in Monitoring {after['ts'] - t_cut:.1f} s after the cut")
    assert after["zones"] == before["zones"] and after["pit"] == before["pit"]
    assert after["homography_sha"] == before["homography_sha"]
    sinks = stack.c("orin").exec_run(["pactl", "list", "short", "sinks"]).output.decode(errors="replace")
    assert "horn" in sinks, f"no horn sink after the restart: {sinks}"


@pytest.mark.skip(reason="V17 needs recorded site footage (YOLO mode, ffmpeg -re -stream_loop -1 -i site_clip.mp4 ...)")
def test_V17_detector_accuracy():
    pass


@pytest.mark.skipif(os.environ.get("TWIN_ARM64") != "1", reason="V18 builds the JetPack image under QEMU; set TWIN_ARM64=1")
def test_V18_arm64_install():
    base = os.environ.get("TWIN_JETPACK_BASE", "nvcr.io/nvidia/l4t-jetpack:r36.4.0")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run(["docker", "build", "--platform", "linux/arm64", "--build-arg", f"BASE={base}", "-f", "orin/Dockerfile",
                    "-t", "pole-orin:arm64", "."], cwd=root, check=True)
    out = subprocess.run(["docker", "run", "--rm", "--platform", "linux/arm64", "--entrypoint", "python3", "pole-orin:arm64",
                          "-c", "import sys; sys.path.insert(0,'/opt/pole'); import app.main, cv2, numpy; "
                                "from app.alarm import AlarmFSM; f=AlarmFSM(); f.update(0,{1:1.0}); print('arm64 ok', f.level)"],
                         capture_output=True, text=True, timeout=900)
    assert "arm64 ok" in out.stdout, out.stderr


# ------------------------------------------------------------------ fault table rows without a V number
def test_fault_4g_weak_events_still_arrive(stack):
    stack.fault("4g_weak")
    try:
        run, t0 = walk_in(stack, seconds=16)
        kinds = [e["kind"] for e in stack.state()["events"] if e.get("ts", 0) >= t0 and e.get("kind") != "health"]
        assert kinds[:4] == ["caution", "warning", "alarm", "reset"], kinds
    finally:
        stack.fault("4g_weak", restore=True)


def test_fault_4g_outage_events_queue_in_order(stack):
    stack.fault("4g_outage")
    try:
        run, t0 = walk_in(stack, seconds=16)
        during = [e for e in stack.state()["events"] if e.get("ts", 0) >= t0]
        assert not during, f"events arrived during the outage: {during}"
        assert stack.orin_status()["queue"] >= 4
    finally:
        stack.fault("4g_outage", restore=True)
    got = stack.wait_for(lambda: (ev := [e for e in stack.state()["events"] if e.get("ts", 0) >= t0
                                         and e.get("kind") != "health"]) and len(ev) >= 4 and ev, 60, 1, "queued events")
    assert [e["kind"] for e in got[:4]] == ["caution", "warning", "alarm", "reset"]
    seqs = [e["seq"] for e in got]
    assert seqs == sorted(seqs)


def test_fault_arm_usb_unplugged(stack):
    stack.fault("arm_usb")
    try:
        stack.wait_for(lambda: (s := stack.orin_status()) and not s["arm_online"], 15, 0.5, "arm offline")
        run, t0 = walk_in(stack, seconds=12)
        kinds = [e["kind"] for e in stack.state()["events"] if e.get("ts", 0) >= t0]
        assert "alarm" in kinds
        sounds = stack.horn_sounds(t0)
        relay = [r for r in stack.run_log(run, "relay") if r["strobe"]]
        assert sounds and relay, "horn and strobe must still fire with the arm unplugged"
    finally:
        stack.fault("arm_usb", restore=True)
    stack.wait_for(lambda: (s := stack.orin_status()) and s["arm_online"], 20, 0.5, "arm back online")


# ---------------------------------------------------------------- regressions from the Step 2 findings
def test_guide_arm_usb_command_unplugs_only_the_arm(phase1):
    stack = phase1
    """The guide's command, verbatim: `docker exec twin-devices-1 pkill -f TCP-LISTEN:7001`.
    Only the arm bridge stops; the devices container (same PID 1, no restart), both emulators
    and the relay bridge keep running."""
    devices = stack.c("devices")
    started, restarts = devices.attrs["State"]["StartedAt"], devices.attrs["RestartCount"]

    def running(pattern):
        return devices.exec_run(["pgrep", "-f", pattern]).exit_code == 0

    res = devices.exec_run(["pkill", "-f", "TCP-LISTEN:7001"])
    try:
        assert res.exit_code == 0, "no arm bridge was running"
        time.sleep(2.0)
        devices.reload()
        assert devices.status == "running"
        assert (devices.attrs["State"]["StartedAt"], devices.attrs["RestartCount"]) == (started, restarts), \
            "the devices container restarted: pkill matched its PID 1"
        assert not running("^socat TCP-LISTEN:7001"), "the arm bridge is still listening"
        assert running("^socat TCP-LISTEN:7002") and running("arm_emulator.py") and running("relay_emulator.py")
        stack.wait_for(lambda: (s := stack.orin_status()) and not s["arm_online"], 15, 0.5, "arm offline")
    finally:
        stack.fault("arm_usb", restore=True)
    stack.wait_for(lambda: (s := stack.orin_status()) and s["arm_online"], 20, 0.5, "arm back online")


def test_fixed_addresses_held(stack):
    """Fixed addresses never collide: each service holds its own, dynamic ones sit above them."""
    def ips(service):
        nets = stack.c(service).attrs["NetworkSettings"]["Networks"]
        return {n.removeprefix(f"{PROJECT}_"): v["IPAddress"] for n, v in nets.items()}
    orin = ips("orin")
    assert ips("camera")["poe_lan"] == "192.168.10.20"
    if stack.profile == "v11":
        assert ips("devices") == {"poe_lan": "192.168.10.24"}
        assert ips("router")["poe_lan"] == "192.168.10.1"
    assert (orin["poe_lan"], orin["wan_4g"]) == ("192.168.10.2", "172.30.4.2")
    assert ips("cloud")["wan_4g"] == "172.30.4.10"
    assert ipaddress.ip_address(ips("world")["poe_lan"]) in ipaddress.ip_network("192.168.10.128/25")


def test_browser_stream_is_h264_420(stack):
    """The stream a browser gets (HLS through the dashboard's /video/ proxy) is H.264 4:2:0 at the
    profile's frame size (1280x720 phase 1, 1600x1200 v11)."""
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed on this host")
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,pix_fmt,width,height", "-of", "json",
                          f"{DASHBOARD}/video/stream1/index.m3u8"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    s = json.loads(out.stdout)["streams"][0]
    size = (stack.site["render"].get("width", 1280), stack.site["render"].get("height", 720))
    assert (s["codec_name"], s["pix_fmt"], s["width"], s["height"]) == ("h264", "yuv420p", *size)


def test_horn_sink_visible_to_docker_exec(stack):
    """`docker exec twin-orin-1 pactl list short sinks` shows `horn` (the orin-sandbox scenario)."""
    res = stack.c("orin").exec_run(["pactl", "list", "short", "sinks"])
    out = res.output.decode(errors="replace")
    assert res.exit_code == 0 and "horn" in out, out


def _hold_keys(ws, keys, seconds, run=False):
    import json as _json
    end = time.time() + seconds
    while time.time() < end:
        ws.send(_json.dumps({"type": "keys", "keys": keys, "run": run}))
        time.sleep(0.1)
    ws.send(_json.dumps({"type": "keys", "keys": []}))


def test_trial_walk_in_via_dashboard(stack):
    """A human trial walk-in, driven through the dashboard's trial pad (the WebSocket a browser
    uses), gives caution, then warning, then alarm, then reset from the real Orin app."""
    from websockets.sync.client import connect
    stack.scenario("idle")
    stack.wait_monitoring()
    t0 = time.time()
    with connect(DASHBOARD_WS) as ws:
        _hold_keys(ws, ["down"], 4.5)          # from (6, -6) toward the camera, south of the pit
        _hold_keys(ws, ["left"], 1.2)          # step into the 1.5 m zone
        time.sleep(5.0)                        # stand by the pit
        _hold_keys(ws, ["up"], 4.0)            # walk away from the camera, out of the zone
    time.sleep(3.0)
    kinds = [e["kind"] for e in stack.state()["events"] if e.get("ts", 0) >= t0 and e.get("kind") != "health"]
    print(f"trial walk-in via the dashboard: {kinds}")
    assert kinds == ["caution", "warning", "alarm", "reset"]


# ---------------------------------------------------------------- v11: Ethernet laser controller, remote management
def _exec(stack, service, cmd, timeout=None):
    code, out = stack.sh(service, cmd if timeout is None else f"timeout {timeout} {cmd}")
    return code, out


def test_v11_laser_controller_on_poe_lan(v11):
    """The orin reaches the laser controller at 192.168.10.24:7001 and :7002; no container is on usb_bus."""
    stack = v11
    code, out = _exec(stack, "orin", "python3 -c \"import socket;[socket.create_connection(('192.168.10.24',p),2).close() for p in (7001,7002)]\"")
    assert code == 0, out
    on_usb = [c.name for c in stack.dk.containers.list() if f"{PROJECT}_usb_bus" in c.attrs["NetworkSettings"]["Networks"]]
    assert not on_usb, on_usb
    assert stack.wait_for(lambda: (s := stack.orin_status()) and s["arm_online"], 20, 0.5, "the arm online over TCP")


def test_v11_laser_controller_restart_reconnects(v11):
    """Ethernet link re-connected: the app's TCP arm link comes back within 2 s of the controller restarting."""
    stack = v11
    stack.fault("arm_usb")
    stack.wait_for(lambda: (s := stack.orin_status()) and not s["arm_online"], 15, 0.5, "arm offline")
    t0 = time.time()
    stack.fault("arm_usb", restore=True)
    stack.wait_for(lambda: (s := stack.orin_status()) and s["arm_online"] and s["ts"] > t0, 10, 0.2, "arm back online")
    print(f"arm link back {time.time() - t0:.1f} s after the controller restarted")
    assert time.time() - t0 <= 2.0 + 1.5        # 2 s reconnect + the 1 s status period and polling


def test_v11_engineer_ssh_to_ai_box(v11):
    """An engineer in the tailnet opens SSH to the AI box at its poe_lan address through the router."""
    code, out = _exec(v11, "engineer", "ssh -i /keys/engineer -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                                       "-o BatchMode=yes -o ConnectTimeout=5 root@192.168.10.2 'cat /data/status.json'")
    assert code == 0 and '"state"' in out, out


def test_v11_superior_cannot_reach_lan_but_sees_relay(v11):
    stack = v11
    code, _ = _exec(stack, "superior", "nc -z -w 2 192.168.10.2 22")
    assert code != 0, "the superior reached the pole's LAN"
    stack.wait_for(lambda: '"live_ts": null' not in _exec(stack, "superior", "curl -s http://172.30.4.11:8090/status")[1]
                   and _exec(stack, "superior", "curl -s http://172.30.4.11:8090/status")[0] == 0, 60, 2, "live view on the relay")
    code, out = _exec(stack, "superior", "curl -s -o /dev/null -w '%{http_code} %{content_type}' http://172.30.4.11:8090/live.jpg")
    assert out.startswith("200 image/jpeg"), out
    code, out = _exec(stack, "superior", "curl -s http://172.30.4.11:8090/events")
    assert code == 0 and out.startswith("["), out


def test_v11_no_inbound_port_on_4g(v11):
    """A client on wan_4g outside the tailnet scans the router's 4G address: no port answers."""
    code, out = _exec(v11, "superior", "sh -c 'for p in 22 80 443 1883 7001 7002 8022 8080 8554 41641; do "
                                       "nc -z -w 1 172.30.4.3 $p && echo open $p; done; true'")
    assert "open" not in out, out


def test_v11_watchdog_recovers_ai_box_hang(v11):
    """AI box hang: the PoE watchdog power-cycles it within 40 s, Monitoring within 60 s after that."""
    stack = v11
    stack.wait_monitoring()
    t0 = time.time()
    stack.fault("orin_hang")
    try:
        ev = stack.wait_for(lambda: next((e for e in stack.state()["events"] if e.get("what") == "watchdog_power_cycle"
                                          and e["ts"] >= t0), None), 50, 1, "the watchdog power cycle")
    finally:
        c = stack.c("orin")
        c.reload()
        if c.status == "paused":
            c.unpause()
    t_cycle = ev["ts"] - t0
    after = stack.wait_for(lambda: (s := stack.orin_status()) and s["ts"] > ev["ts"] and s.get("state") == "monitoring" and s,
                           60, 0.5, "Monitoring after the watchdog")
    print(f"watchdog: power cycle {t_cycle:.0f} s after the hang, Monitoring {after['ts'] - ev['ts']:.0f} s after that")
    assert t_cycle <= 40 and after["ts"] - ev["ts"] <= 60


def test_v11_switch_hang_and_remote_restart(v11):
    """Switch hang: the router keeps reporting to the cloud; an engineer restarts the switch through
    the tailnet and the camera stream and arm link come back within 60 s."""
    stack = v11
    stack.wait_monitoring()
    stack.fault("switch_hang")
    try:
        stack.wait_for(lambda: (s := stack.orin_status()) and not s["camera_ok"] and not s["arm_online"], 30, 1,
                       "camera and arm lost")
        t_hang = time.time()
        stack.wait_for(lambda: '"uptime_s"' in _exec(stack, "superior", "curl -s http://172.30.4.11:8090/events")[1]
                       and any(e.get("ts", 0) > t_hang for e in json.loads(_exec(stack, "superior",
                               "curl -s http://172.30.4.11:8090/events")[1]) if "uptime_s" in e), 15, 1,
                       "router status reaching the cloud during the hang")
        t0 = time.time()
        code, out = _exec(stack, "engineer", "curl -s -m 90 -X POST http://100.64.0.1:8022/switch/restart")
        assert code == 0 and '"ok": true' in out, out
    finally:
        stack.fault("switch_hang", restore=True)
    stack.wait_for(lambda: (s := stack.orin_status()) and s["camera_ok"] and s["arm_online"] and s["ts"] > t0, 60, 1,
                   "camera stream and arm link back")
    print(f"switch restart: links back {time.time() - t0:.0f} s after the engineer's request")
    assert time.time() - t0 <= 60
