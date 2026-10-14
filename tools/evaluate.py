"""Score a recorded run (dashboard /logs/run-<time>/) against ground truth.

    python3 -m tools.evaluate logs/run-20261014-101500

For every true entry into the 1.5 m zone: was it warned and alarmed, how long after
entering, and how long after leaving was the reset. Warnings outside any entry are false alarms.
"""
from __future__ import annotations

import argparse
import json
import os


def load_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def evaluate(run_dir, alarm_buffer_m=1.5, dwell_s=1.0, slack_s=2.5):
    truth = load_jsonl(os.path.join(run_dir, "truth.jsonl"))
    events = [e for e in load_jsonl(os.path.join(run_dir, "events.jsonl")) if "kind" in e]
    entries, open_ = [], {}
    for msg in truth:
        t, seen = msg["t"], set()
        for w in msg.get("workers", []):
            seen.add(w["id"])
            inside = w["edge_m"] <= alarm_buffer_m
            if inside and w["id"] not in open_:
                open_[w["id"]] = {"worker": w["id"], "entered": t, "left": None}
                entries.append(open_[w["id"]])
            elif not inside and w["id"] in open_:
                open_.pop(w["id"])["left"] = t
        for wid in [i for i in open_ if i not in seen]:
            open_.pop(wid)["left"] = t
    used, report = set(), []
    for e in entries:
        end = (e["left"] or float("inf")) + slack_s

        def first(kind, after):
            for i, ev in enumerate(events):
                if i not in used and ev["kind"] == kind and after <= ev["ts"] <= end:
                    used.add(i)
                    return ev["ts"]
            return None
        warn, alarm = first("warning", e["entered"]), first("alarm", e["entered"])
        reset = first("reset", e["left"]) if e["left"] else None
        stay = (e["left"] - e["entered"]) if e["left"] else None
        report.append({"worker": e["worker"], "stay_s": stay,
                       "warning_after_s": None if warn is None else round(warn - e["entered"], 3),
                       "alarm_after_s": None if alarm is None else round(alarm - e["entered"], 3),
                       "reset_after_leaving_s": None if reset is None else round(reset - e["left"], 3),
                       "detected": warn is not None or (stay is not None and stay < dwell_s)})
    false_alarms = [ev for i, ev in enumerate(events) if ev["kind"] == "warning" and i not in used]
    n = len(report)
    return {"entries": report, "detected": sum(r["detected"] for r in report), "entries_total": n,
            "detection_rate": None if n == 0 else round(sum(r["detected"] for r in report) / n, 3),
            "false_alarms": len(false_alarms)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    a = ap.parse_args(argv)
    print(json.dumps(evaluate(a.run_dir), indent=2))


if __name__ == "__main__":
    main()
