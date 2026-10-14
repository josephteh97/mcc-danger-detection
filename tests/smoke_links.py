"""Quick checks: laser arm and relay emulators over a pty, aim angles, uplink queue
(V06-V09, U04-U06)."""
import os
import subprocess
import sys
import tempfile
import time

from _check import ROOT, check, main

from app.links import ArmLink, SerialLine, Uplink, aim_angles

PY = sys.executable


class Emulator:
    """Runs a device emulator as its own process on a fresh virtual serial port."""

    def __init__(self, script, seconds=30):
        self.dir = tempfile.mkdtemp(prefix="vdev-")
        self.link = os.path.join(self.dir, "port")
        self.proc = subprocess.Popen([PY, os.path.join(ROOT, "devices", script), "--link", self.link,
                                      "--run-for", str(seconds)], stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + 5
        while not os.path.exists(self.link):
            if time.monotonic() > deadline:
                raise RuntimeError(f"{script} did not create {self.link}")
            time.sleep(0.02)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(5)


def drive(arm, seconds, cmds=("HB",), every=1 / 15):
    """Send `cmds` every frame for `seconds`; returns [(t, pan, tilt, laser)] from POS reports."""
    seen, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        for c in cmds:
            arm.send(c)
        before = arm.last_pos_t
        arm.poll()
        if arm.pos is not None and arm.last_pos_t != before:
            seen.append((time.monotonic(), *arm.pos))
        time.sleep(every)
    return seen


@check("V06", "Laser interlock")
def v06():
    with Emulator("arm_emulator.py") as emu:
        arm = ArmLink(SerialLine(emu.link))
        drive(arm, 1.0, ("AIM 0 -5", "HB"))                 # point 5 deg above horizontal first
        seen = drive(arm, 1.5, ("AIM 0 -5", "LASER 1", "HB"))
        lased = [s for s in seen if s[3]]
        above = [s for s in seen if s[2] < 1.0]
        ok = len(seen) > 10 and len(above) == len(seen) and not lased
        return (ok, f"{len(lased)} of {len(seen)} position reports had the laser on while aimed at tilt {seen[-1][2]:.1f} (above horizontal)",
                "laser stays off when aimed above horizontal, even with LASER 1")


@check("V07", "Laser aims and fires")
def v07():
    with Emulator("arm_emulator.py") as emu:
        arm = ArmLink(SerialLine(emu.link))
        seen = drive(arm, 1.5, ("AIM 20 8", "LASER 1", "HB"))
        pan, tilt, on = seen[-1][1:]
        ok = abs(pan - 20) <= 0.5 and abs(tilt - 8) <= 0.5 and on
        return ok, f"reached pan {pan:.2f}, tilt {tilt:.2f}, laser {'on' if on else 'off'}", "arm reaches pan 20, tilt 8 within 0.5 deg and lases"


@check("V08", "Laser watchdog")
def v08():
    with Emulator("arm_emulator.py") as emu:
        arm = ArmLink(SerialLine(emu.link))
        drive(arm, 1.0, ("AIM 20 8", "LASER 1", "HB"))
        last_hb = time.monotonic()
        seen = drive(arm, 3.0, ())
        off = next((t for t, _, _, on in seen if not on), None)
        if off is None:
            return False, "laser still on 3 s after the last heartbeat", "laser off within 2 s"
        dt = off - last_hb
        parking = [s for s in seen if s[0] >= off]
        tilt_rising = parking[-1][2] > parking[0][2] if len(parking) > 1 else False
        final = seen[-1]
        ok = dt <= 2.0 + 0.05 + 0.02 and tilt_rising and abs(final[2] - 90) < 0.5
        return (ok, f"laser off {dt:.3f} s after the last heartbeat, then parked at pan {final[1]:.1f}, tilt {final[2]:.1f}",
                "laser off and arm parking within 2 s (+ one 50 ms report) of the last heartbeat")


@check("U06", "Servo slew rate")
def u06():
    with Emulator("arm_emulator.py") as emu:
        arm = ArmLink(SerialLine(emu.link))
        drive(arm, 0.8, ("AIM 0 10", "HB"))                 # settle at pan 0
        t0 = time.monotonic()
        seen = drive(arm, 1.0, ("AIM 90 10", "HB"), every=0.01)
        reach = next((t for t, pan, _, _ in seen if abs(pan - 90) <= 0.5), None)
        if reach is None:
            return False, "pan never reached 90 deg", "90 deg in 0.5-0.6 s"
        dt = reach - t0
        return 0.45 <= dt <= 0.62, f"pan 0 -> 90 deg in {dt:.3f} s ({90 / dt:.0f} deg/s)", "180 deg/s: 90 deg in 0.5-0.6 s"


@check("U04", "Aim angles for a known target")
def u04():
    pan, tilt = aim_angles((-6.0, 3.6), -30, 1.1, (0.0, 0.0))
    ok = abs(pan - (-0.96)) < 0.01 and abs(tilt - 8.93) < 0.01
    return ok, f"pan {pan:.3f}, tilt {tilt:.3f}", "pan -0.96, tilt 8.93 (within 0.01 deg)"


@check("U05", "Relay protocol")
def u05():
    with Emulator("relay_emulator.py") as emu:
        line = SerialLine(emu.link)
        replies = []
        for cmd in ("R 1 1", "R 9 1", "R 3 0"):
            line.send(cmd)
            end = time.monotonic() + 1.0
            got = []
            while not got and time.monotonic() < end:
                got = line.readlines()
                time.sleep(0.01)
            replies.append(got[0] if got else "(no reply)")
        ok = replies == ["OK 1 1", "ERR", "OK 3 0"]
        return ok, f"R 1 1 -> {replies[0]}, R 9 1 -> {replies[1]}, R 3 0 -> {replies[2]}", "OK for valid channels, ERR for channel 9"


class FakeLink:
    """A 4G link that can be cut: handles only complete while the link is up."""

    def __init__(self):
        self.up, self.delivered = True, []

    def __call__(self, payload):
        link = self

        class Handle:
            def __init__(self):
                self.done = False

            def is_published(self):
                if link.up and not self.done:
                    self.done = True
                    link.delivered.append(payload)
                return self.done
        if not self.up:
            raise ConnectionError("4G down")
        return Handle()


@check("V09", "Events survive a 4G outage")
def v09():
    import json
    link = FakeLink()
    q = Uplink(os.path.join(tempfile.mkdtemp(), "queue.db"), link, retry_s=5)
    link.up = False
    for i in range(5):
        q.put({"kind": "test", "n": i})
    for k in range(50):
        q.flush(now=k * 0.1)
    sent_while_down = len(link.delivered)
    link.up = True
    for k in range(50, 100):
        q.flush(now=k * 0.1)
    order = [json.loads(p)["n"] for p in link.delivered]
    ok = sent_while_down == 0 and order == [0, 1, 2, 3, 4] and len(q) == 0
    return ok, f"{sent_while_down} sent while down; after restore {order}, {len(q)} left queued", "nothing sent while down, all sent in order after"


if __name__ == "__main__":
    main("smoke_links.py")
