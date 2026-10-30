"""Runs the app's PoleApp.act() for one alarm, with stand-in devices, in a fresh interpreter, so a
check can see both the event the app emits and which app modules were imported."""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT = r"""
import json, sys
import numpy as np, yaml
sys.path.insert(0, sys.argv[1])
from app.alarm import AlarmFSM, Config
from app.main import PoleApp, identity_provider

class Device:                                  # horn, relays and arm: accept every command
    on = None
    def __getattr__(self, name):
        return lambda *a, **k: None

with open(sys.argv[2]) as f:
    cfg = yaml.safe_load(f)
cfg.setdefault("identify", {}).update(json.loads(sys.argv[3]))
app = PoleApp.__new__(PoleApp)
app.cfg, app.pole = cfg, "07"
app.identity = identity_provider(cfg)
app.fsm = AlarmFSM(Config(**cfg["alarm"]))
app.horn = app.relays = app.arm = Device()
app.dist, app.boxes, events = {1: 0.4}, {1: (700.0, 400.0, 760.0, 560.0)}, []
app.emit = events.append
app.act("alarm", 1, np.zeros((1200, 1600, 3), np.uint8))
print(json.dumps({"event": events[0], "identify_loaded": "app.identify" in sys.modules}))
"""


def alarm_event(config, identify=None):
    """(event, identify_loaded) for one alarm with `config` (a path under app/), with
    `identify` merged into its identify: block. Raises with the app's stderr if it fails."""
    path = config if os.path.isabs(config) else os.path.join(ROOT, config)
    r = subprocess.run([sys.executable, "-c", _SCRIPT, ROOT, path, json.dumps(identify or {})],
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"exit {r.returncode}")
    out = json.loads(r.stdout.strip().splitlines()[-1])
    return out["event"], out["identify_loaded"]
