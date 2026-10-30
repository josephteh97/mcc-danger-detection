"""ESP32 laser arm emulator.

Speaks the serial line protocol the real firmware must implement:
  Orin -> arm:  AIM <pan> <tilt> | LASER <0|1> | HB | PARK
  arm -> Orin:  POS <pan> <tilt> <laser_on>   every 50 ms
and models what the firmware must also do: 180 deg/s servo slew, a tilt interlock (laser only
when the actual tilt is at least 1 deg below horizontal) and a 2 s heartbeat watchdog that
switches the laser off and parks the arm pointing down.

    python3 devices/arm_emulator.py --link /tmp/vdev/arm --state /logs/arm.jsonl
"""
import argparse
import select
import sys
import time

SLEW_DEG_S = 180.0
MIN_TILT_DEG = 1.0
WATCHDOG_S = 2.0
POS_PERIOD_S = 0.05
PARK = (0.0, 90.0)
PAN_LIMIT, TILT_LIMITS = 170.0, (-30.0, 90.0)


class ArmModel:
    def __init__(self, now):
        self.pan, self.tilt = PARK
        self.target = PARK
        self.laser_req = False
        self.laser_on = False
        self.last_cmd = now
        self.watchdog = False
        self._t = now

    def command(self, line, now):
        parts = line.split()
        if not parts:
            return False
        op = parts[0].upper()
        try:
            if op == "AIM" and len(parts) == 3:
                pan = max(-PAN_LIMIT, min(PAN_LIMIT, float(parts[1])))
                tilt = max(TILT_LIMITS[0], min(TILT_LIMITS[1], float(parts[2])))
                self.target = (pan, tilt)
            elif op == "LASER" and len(parts) == 2 and parts[1] in ("0", "1"):
                self.laser_req = parts[1] == "1"
            elif op == "HB" and len(parts) == 1:
                pass
            elif op == "PARK" and len(parts) == 1:
                self.laser_req = False
                self.target = PARK
            else:
                return False
        except ValueError:
            return False
        self.last_cmd = now
        self.watchdog = False
        return True

    def step(self, now):
        dt, self._t = max(0.0, now - self._t), now
        if now - self.last_cmd > WATCHDOG_S and not self.watchdog:
            self.watchdog = True               # Orin silent: laser off, park, wait for a new LASER 1
            self.laser_req = False
            self.target = PARK
        limit = SLEW_DEG_S * dt
        self.pan += max(-limit, min(limit, self.target[0] - self.pan))
        self.tilt += max(-limit, min(limit, self.target[1] - self.tilt))
        self.laser_on = self.laser_req and not self.watchdog and self.tilt >= MIN_TILT_DEG

    def pos_line(self):
        return f"POS {self.pan:.2f} {self.tilt:.2f} {1 if self.laser_on else 0}"

    def state(self):
        return {"t": time.time(), "pan": round(self.pan, 2), "tilt": round(self.tilt, 2),
                "laser": int(self.laser_on), "target": [round(v, 2) for v in self.target],
                "watchdog": self.watchdog}


def serve(link, state_path=None, run_for=None, tcp=None):
    from vserial import JsonlState, open_port
    port, log = open_port(link, tcp), JsonlState(state_path)
    now = time.monotonic()
    arm, next_pos, end = ArmModel(now), now, None if run_for is None else now + run_for
    print(f"arm emulator on {link or port.addr}", flush=True)
    try:
        while end is None or time.monotonic() < end:
            now = time.monotonic()
            select.select([port], [], [], max(0.0, min(0.01, next_pos - now)))
            now = time.monotonic()
            for line in port.readlines():
                arm.command(line, now)
            arm.step(now)
            if now >= next_pos:
                next_pos += POS_PERIOD_S
                if next_pos < now:             # fell behind: don't burst
                    next_pos = now + POS_PERIOD_S
                port.write_line(arm.pos_line())
                s = arm.state()
                log.write(s, (s["pan"], s["tilt"], s["laser"], s["watchdog"]))
    finally:
        port.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--link", help="path where the virtual serial port appears")
    ap.add_argument("--tcp", metavar="HOST:PORT", help="listen on TCP instead (the v11 laser controller on poe_lan)")
    ap.add_argument("--state", help="JSONL file for the arm state (read by the dashboard)")
    ap.add_argument("--run-for", type=float, help="exit after this many seconds (tests)")
    a = ap.parse_args()
    sys.path.insert(0, __import__("os").path.dirname(__file__))
    if not (a.link or a.tcp):
        ap.error("give --link or --tcp")
    serve(a.link, a.state, a.run_for, a.tcp)
