"""USB relay board emulator: channel 1 strobe, 2 floodlight, 3 laser power, 4 spare.

Protocol (one line each way): 'R <channel> <0|1>' -> 'OK <channel> <0|1>', or 'ERR'.
Real boards often use 4-byte hex frames instead; the app's relay adapter handles that.

    python3 devices/relay_emulator.py --link /tmp/vdev/relay --state /logs/relay.jsonl
"""
import argparse
import os
import select
import sys
import time

NAMES = {1: "strobe", 2: "floodlight", 3: "laser_power", 4: "spare"}


class RelayBoard:
    def __init__(self):
        self.on = {ch: False for ch in NAMES}

    def command(self, line):
        parts = line.split()
        if len(parts) != 3 or parts[0].upper() != "R" or parts[2] not in ("0", "1"):
            return "ERR"
        try:
            ch = int(parts[1])
        except ValueError:
            return "ERR"
        if ch not in self.on:
            return "ERR"
        self.on[ch] = parts[2] == "1"
        return f"OK {ch} {parts[2]}"

    def state(self):
        return {"t": time.time(), **{NAMES[ch]: int(v) for ch, v in self.on.items()}}


def serve(link, state_path=None, run_for=None):
    from vserial import JsonlState, VirtualSerial
    port, log, board = VirtualSerial(link), JsonlState(state_path, every_s=5.0), RelayBoard()
    end = None if run_for is None else time.monotonic() + run_for
    print(f"relay emulator on {link}", flush=True)
    log.write(board.state(), tuple(board.on.values()))
    try:
        while end is None or time.monotonic() < end:
            select.select([port], [], [], 0.1)
            for line in port.readlines():
                port.write_line(board.command(line))
            s = board.state()
            log.write(s, tuple(board.on.values()))
    finally:
        port.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--link", required=True)
    ap.add_argument("--state", help="JSONL file for the relay state (read by the dashboard)")
    ap.add_argument("--run-for", type=float)
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(__file__))
    serve(a.link, a.state, a.run_for)
