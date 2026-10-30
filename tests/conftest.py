"""Fixtures for the full-stack checks (V12-V18 and the fault table), and the --legacy option.

The stack must be up (docker compose up -d --build); otherwise these tests are skipped with
"stack not running" and only the quick checks run.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (HERE, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

LEGACY_DIR = os.path.join(HERE, "legacy")


def pytest_addoption(parser):
    parser.addoption("--legacy", action="store_true",
                     help="run the legacy identification tests in tests/legacy/ (skipped by default)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--legacy"):
        return
    skip = pytest.mark.skip(reason="legacy identification test: run with --legacy")
    for item in items:
        if str(item.fspath).startswith(LEGACY_DIR + os.sep):
            item.add_marker(skip)


DASHBOARD = os.environ.get("TWIN_DASHBOARD", "http://127.0.0.1:8080")
PROJECT = os.environ.get("TWIN_PROJECT", "twin")


class Stack:
    def __init__(self, dk, http):
        self.dk, self.http = dk, http

    def c(self, service):
        return self.dk.containers.get(f"{PROJECT}-{service}-1")

    def sh(self, service, cmd):
        res = self.c(service).exec_run(["sh", "-c", cmd])
        return res.exit_code, res.output.decode(errors="replace")

    def state(self):
        return self.http.get(f"{DASHBOARD}/api/state").json()

    def scenario(self, name):
        r = self.http.post(f"{DASHBOARD}/api/scenario/{name}")
        r.raise_for_status()
        return r.json()["run"]

    def weather(self, name):
        self.http.post(f"{DASHBOARD}/api/weather/{name}").raise_for_status()

    def fault(self, name, restore=False):
        r = self.http.post(f"{DASHBOARD}/fault/{name}{'/restore' if restore else ''}", timeout=60)
        assert r.status_code == 200 and r.json().get("ok"), r.text
        return r.json()

    def run_log(self, run, kind):
        code, out = self.sh("dashboard", f"cat /logs/{run}/{kind}.jsonl 2>/dev/null")
        return [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]

    def orin_status(self):
        code, out = self.sh("orin", "cat /data/status.json 2>/dev/null")
        try:
            return json.loads(out)
        except ValueError:
            return None

    def horn_sounds(self, since):
        code, out = self.sh("orin", "cat /data/horn.log 2>/dev/null")
        times = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == "SOUND" and float(parts[0]) >= since:
                times.append(float(parts[0]))
        return times

    def wait_for(self, pred, timeout, every=0.2, what="condition"):
        end = time.time() + timeout
        while time.time() < end:
            v = pred()
            if v:
                return v
            time.sleep(every)
        raise AssertionError(f"timed out after {timeout} s waiting for {what}")

    def wait_monitoring(self, timeout=60):
        return self.wait_for(lambda: (s := self.orin_status()) and s.get("state") == "monitoring"
                             and time.time() - s["ts"] < 3 and s, timeout, 0.5, "the app in Monitoring")

    def quiet(self):
        """Empty site, clear weather, no faults, app back in Monitoring."""
        for f in ("4g_weak", "4g_outage", "arm_usb", "orin_hang", "camera_cable"):
            try:
                self.fault(f, restore=True)
            except AssertionError:
                pass
        self.weather("clear")
        self.scenario("idle")
        self.wait_monitoring()


@pytest.fixture(scope="session")
def stack():
    try:
        import docker
        import httpx
        dk = docker.from_env()
        names = {c.name for c in dk.containers.list()}
        need = {f"{PROJECT}-{s}-1" for s in ("camera", "world", "devices", "orin", "cloud", "dashboard")}
        if not need <= names:
            pytest.skip(f"stack not running (missing {', '.join(sorted(need - names))})")
        http = httpx.Client(timeout=10)
        http.get(f"{DASHBOARD}/healthz").raise_for_status()
    except pytest.skip.Exception:
        raise
    except Exception as e:
        pytest.skip(f"stack not running ({e.__class__.__name__}: {e})")
    s = Stack(dk, http)
    s.quiet()
    yield s
    s.quiet()


def zone_crossings(truth, buffer_m=1.5):
    """[(t_enter, t_leave, worker)] from a recorded truth log."""
    open_, out = {}, []
    for msg in truth:
        seen = set()
        for w in msg["workers"]:
            seen.add(w["id"])
            inside = w["edge_m"] <= buffer_m
            if inside and w["id"] not in open_:
                open_[w["id"]] = msg["t"]
            elif not inside and w["id"] in open_:
                out.append((open_.pop(w["id"]), msg["t"], w["id"]))
        for wid in [i for i in open_ if i not in seen]:
            out.append((open_.pop(wid), msg["t"], wid))
    out += [(t, None, wid) for wid, t in open_.items()]
    return sorted(out)


def dist(a, b):
    return math.dist(a, b)
