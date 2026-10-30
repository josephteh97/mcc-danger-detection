"""The v11 laser controller's Ethernet links: the relay and arm emulators on TCP, the app's
TcpLine, and reconnection after the controller restarts (no Docker needed)."""
import os
import socket
import subprocess
import sys
import time

from app.links import ArmLink, Relays, TcpLine, make_line

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(script, port):
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "devices", script), "--tcp", f"127.0.0.1:{port}",
                          "--run-for", "30"], stdout=subprocess.DEVNULL)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    p.kill()
    raise RuntimeError(f"{script} did not listen on {port}")


def wait_lines(line, want, timeout=3.0):
    got, end = [], time.monotonic() + timeout
    while time.monotonic() < end:
        got += line.readlines()
        if want in got:
            return got
        time.sleep(0.02)
    return got


def test_make_line_picks_transport():
    assert isinstance(make_line("127.0.0.1:1"), TcpLine)


def test_relay_over_ethernet_and_reconnect():
    port = free_port()
    emu = start("relay_emulator.py", port)
    line = TcpLine(f"127.0.0.1:{port}")
    try:
        relays = Relays(line)
        relays.set(1, True)
        assert "OK 1 1" in wait_lines(line, "OK 1 1")
        assert line.send("R 9 1") and "ERR" in wait_lines(line, "ERR")
        gen = line.generation
        emu.kill()
        emu.wait()
        line.readlines()                               # notices the far end has gone
        emu = start("relay_emulator.py", port)
        t0, acks = time.monotonic(), []
        while time.monotonic() - t0 < 2.0 and "OK 1 1" not in acks:
            acks += relays.poll()                      # resends channel state after reconnecting
            time.sleep(0.02)
        assert line.generation > gen and "OK 1 1" in acks, f"no reconnect within 2 s ({acks})"
    finally:
        line.close()
        emu.kill()


def test_arm_over_ethernet():
    port = free_port()
    emu = start("arm_emulator.py", port)
    arm = ArmLink(f"127.0.0.1:{port}")
    try:
        end = time.monotonic() + 3
        while time.monotonic() < end and arm.pos is None:
            arm.point_at(10.0, 20.0)
            arm.poll()
            time.sleep(0.05)
        assert arm.pos is not None
    finally:
        arm.line.close()
        emu.kill()
