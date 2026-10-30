"""Stream bitrates per link and the 4G data a month for the v11 pole.

    python3 -m tools.network
    python3 -m tools.network --events 120 --view-hours 3
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Streams in Mbit/s: (typical, cap)
STREAMS = {
    "camera_main": (8.0, 16.0),
    "camera_sub": (1.0, 2.0),          # only while someone watches
    "horn": (0.1, 0.1),
    "laser_lines": (0.05, 0.05),       # arm and relay lines to the laser controller
    "events": (0.03, 0.03),            # average
    "live_view": (1.0, 2.0),           # per watched stream, to the cloud relay
    "maintenance": (4.0, 8.0),         # engineer over the VPN (1-4 typical)
}

# Which streams cross each wired link (switch port -> device)
LINKS = {
    "port 1 camera": ["camera_main", "camera_sub"],
    "port 2 horn": ["horn"],
    "port 3 router": ["events", "live_view", "maintenance"],
    "port 4 AI box": ["camera_main", "camera_sub", "horn", "laser_lines", "events", "live_view", "maintenance"],
    "port 5 laser controller": ["laser_lines"],
}
CLIP_EVENT_KB = 1.0                     # one MQTT event message


def link_loads(port_mbps=1000.0, watched=True):
    """{link: (typical %, cap %)} of the port speed."""
    out = {}
    for link, streams in LINKS.items():
        streams = [s for s in streams if watched or s not in ("camera_sub", "live_view")]
        typ = sum(STREAMS[s][0] for s in streams)
        cap = sum(STREAMS[s][1] for s in streams)
        out[link] = (100 * typ / port_mbps, 100 * cap / port_mbps)
    return out


def monthly_4g_gb(events_per_day=50, clip_mb=1.3, view_hours_per_day=1.0, view_mbps=1.0, days=30):
    """4G data a month (GB): event clips, event messages and live viewing through the cloud relay.
    The twin's 1 s status topic is a twin convenience and not counted (design.md D15)."""
    clips_mb = events_per_day * clip_mb
    messages_mb = events_per_day * CLIP_EVENT_KB / 1000
    view_mb = view_hours_per_day * 3600 * view_mbps / 8
    per_day = clips_mb + messages_mb + view_mb
    return {"total_gb": per_day * days / 1000, "clips_gb": clips_mb * days / 1000,
            "view_gb": view_mb * days / 1000, "messages_gb": messages_mb * days / 1000}


def report(site, **kw):
    net = dict(site.get("network") or {})
    net.update({k: v for k, v in kw.items() if v is not None})
    data = monthly_4g_gb(net.get("events_per_day", 50), net.get("clip_mb", 1.3),
                         net.get("view_hours_per_day", 1.0), net.get("view_mbps", 1.0))
    plan = net.get("sim_plan_gb", 30)
    loads = link_loads(net.get("port_mbps", 1000))
    return {"data": data, "plan_gb": plan, "within_plan": data["total_gb"] <= plan, "links": loads,
            "max_link_pct": max(cap for _, cap in loads.values())}


def main(argv=None):
    import catalog
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--events", type=float, dest="events_per_day")
    ap.add_argument("--clip-mb", type=float)
    ap.add_argument("--view-hours", type=float, dest="view_hours_per_day")
    ap.add_argument("--view-mbps", type=float)
    a = ap.parse_args(argv)
    r = report(catalog.load_site(profile="v11"), **vars(a))
    d = r["data"]
    print(f"4G a month: {d['total_gb']:.1f} GB (clips {d['clips_gb']:.1f}, live view {d['view_gb']:.1f}, "
          f"messages {d['messages_gb']:.2f}) against a {r['plan_gb']:.0f} GB plan: "
          + ("within plan" if r["within_plan"] else "OVER PLAN"))
    for link, (typ, cap) in r["links"].items():
        print(f"  {link:24s} {typ:5.2f}% typical, {cap:5.2f}% at cap")


if __name__ == "__main__":
    main()
