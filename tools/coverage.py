"""Detection coverage for the v11 stand camera: largest zone, placement and height windows,
the warning-ring density check, the px/m heatmap and the laser's reach.

    python3 -m tools.coverage                     # report for the active profile
    python3 -m tools.coverage --profile v11 --distance 5
"""
from __future__ import annotations

import argparse
import copy
import functools
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import catalog                                   # noqa: E402
from catalog import effects as fx                # noqa: E402

FOOT_PX = 2.0           # feet located to 2 px ...
FOOT_M = 0.1            # ... which must be within 10 cm on the ground
MAX_TILT_DEG = 45.0     # the near edge is seen at most 45 degrees down
BANDS = ((100, "green"), (60, "amber"), (0, "red"))


def band(ppm):
    return next(name for limit, name in BANDS if ppm >= limit)


# --------------------------------------------------------------------------- largest zone

def largest_zone(camera, rho):
    """Largest square zone a camera covers at `rho` px/m, and the camera's distance from its
    centre, by both methods. -> {"fov": (S, d), "distortion": (S, d)}"""
    n = fx.native_size(camera)[0]
    t = math.tan(math.radians(camera["hfov_deg"]) / 2)
    w_max, z_max = n / rho, n / (2 * rho * t)
    s = w_max * z_max / (z_max + w_max)
    out = {"fov": (s, z_max - s / 2)}
    fp, _, d = fx.lens(camera)
    if d:
        lo, hi = 0.0, 2.0                     # 1 − 3D·u² − 4D·u³ falls from 1: bisect for its root
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if 1 - 3 * d * mid ** 2 - 4 * d * mid ** 3 > 0 else (lo, mid)
        u = (lo + hi) / 2
        g, c = 1 - d * u ** 2, fp / rho
        s_max = c * 2 * g * u / (1 + 2 * u)
        out["distortion"] = (s_max, g * c - s_max / 2)
    return out


# --------------------------------------------------------------------------- site pose

def _bearing(site):
    xy = np.asarray(site["camera"]["xy"], float)
    look = np.asarray(site["camera"].get("look_at", [0.0, 0.0]), float)
    return look, (look - xy) / np.linalg.norm(look - xy)


def moved(site, distance=None, height=None):
    """A copy of the site with the stand `distance` m from the zone centre (along the same
    bearing, camera, arm and floodlight together) and/or the camera at `height` m."""
    s = copy.deepcopy(site)
    look, fwd = _bearing(site)
    if distance is not None:
        xy = (look - fwd * distance).round(6).tolist()
        for key in ("camera", "arm", "floodlight"):
            if key in s and "xy" in s[key] and np.allclose(s[key]["xy"], site["camera"]["xy"]):
                s[key]["xy"] = xy
    if height is not None:
        s["camera"]["height_m"] = height
    return s


@functools.lru_cache(maxsize=16)
def _ring(pit, buffer_m, n):
    return fx.ring_points({"site": {"pit": [list(p) for p in pit]}}, buffer_m, n)


def warn_ring(site, n=360):
    """The warning ring (depends only on the pit and the buffer, so it is computed once)."""
    return _ring(tuple(map(tuple, site["site"]["pit"])), site["zones"]["warn_buffer_m"], n).copy()


def ring_check(site, detector=None, rho=None, method="worst"):
    """Processed-image density at every point of the warning ring. -> dict"""
    detector = site.get("detector") if detector is None else detector
    rho = rho or (detector or {}).get("density_px_per_m", 100)
    ring = warn_ring(site)
    dens, inside = fx.processed_density(site, ring, detector, method)
    low = [(round(float(x), 2), round(float(y), 2), round(float(v), 1))
           for (x, y), v, i in zip(ring, dens, inside) if v < rho or not i]
    return {"ok": not low, "min_ppm": float(dens.min()), "rho": rho, "below": low,
            "outside": int((~inside).sum()), "points": len(ring)}


def height_window(site, rho=None):
    """Allowed camera heights: h ≥ D_far·tan θ_min (sin θ_min = 2 px / (ρ·0.1 m)) and
    h ≤ D_near·tan 45°, with D_far and D_near the ground distances to the warning ring."""
    rho = rho or (site.get("detector") or {}).get("density_px_per_m", 100)
    along = (warn_ring(site) - np.asarray(site["camera"]["xy"])) @ _bearing(site)[1]
    d_far, d_near = float(along.max()), float(along.min())
    theta_min = math.asin(FOOT_PX / (rho * FOOT_M))
    return d_far * math.tan(theta_min), d_near * math.tan(math.radians(MAX_TILT_DEG)), d_far, d_near


def pose_check(site, rho=None):
    """Is the stand's pose inside both windows? Near corners must be in the image, the far edge
    must keep the density (field-of-view method, as the conservative sizing), and the camera
    height must be inside the height window."""
    rho = rho or (site.get("detector") or {}).get("density_px_per_m", 100)
    ring = warn_ring(site)
    _, inside = fx.native_density(site, ring, "fov")
    _, inside_d = fx.native_density(site, ring, "distortion")
    look, fwd = _bearing(site)
    far = look + fwd * (float(((ring - look) @ fwd).max()))
    far_ppm = float(fx.processed_density(site, [far], method="fov")[0][0])
    h_min, h_max, d_far, d_near = height_window(site, rho)
    h = site["camera"].get("height_m", site["fitted"]["mast"]["height_m"])
    problems = []
    if not (inside.all() and inside_d.all()):
        problems.append(f"{int((~(inside & inside_d)).sum())} warning-ring points outside the image")
    if far_ppm < rho:
        problems.append(f"far edge {far_ppm:.0f} px/m < {rho}")
    if not h_min <= h <= h_max:
        problems.append(f"camera height {h:.2f} m outside {h_min:.2f}-{h_max:.2f} m")
    return {"ok": not problems, "problems": problems, "far_edge_ppm": far_ppm, "height_m": h,
            "height_window": (h_min, h_max), "d_far": d_far, "d_near": d_near,
            "distance": float(np.linalg.norm(np.asarray(site["camera"]["xy"]) - look))}


def placement_window(site, rho=None, lo=2.0, hi=30.0, step=0.1):
    """Stand distances from the zone centre (same bearing, height and tilt) whose pose passes."""
    ok = [d for d in np.arange(lo, hi + 1e-9, step) if pose_check(moved(site, float(d)), rho)["ok"]]
    return (round(min(ok), 2), round(max(ok), 2)) if ok else None


# --------------------------------------------------------------------------- heatmap

def heatmap(site, step=0.5, margin=1.0, detector=None):
    """Processed px/m on a ground grid around the warning ring, for the dashboard's heatmap."""
    ring = warn_ring(site)
    (x0, y0), (x1, y1) = ring.min(0) - margin, ring.max(0) + margin
    xs, ys = np.arange(x0, x1 + 1e-9, step), np.arange(y0, y1 + 1e-9, step)
    gx, gy = np.meshgrid(xs, ys)
    dens, inside = fx.processed_density(site, np.stack([gx.ravel(), gy.ravel()], 1), detector)
    dens = np.where(inside, dens, 0.0).reshape(gx.shape)
    return {"x0": float(xs[0]), "y0": float(ys[0]), "step": step, "nx": len(xs), "ny": len(ys),
            "ppm": dens.round(1).tolist(), "bands": [[limit, name] for limit, name in BANDS]}


# --------------------------------------------------------------------------- laser reach

def alarm_zone_corners(site):
    """Corners of the 1.5 m alarm zone as a rectangle around the pit (the conservative outline)."""
    pit = np.asarray(site["site"]["pit"], float)
    b = site["zones"]["alarm_buffer_m"]
    (x0, y0), (x1, y1) = pit.min(0) - b, pit.max(0) + b
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def laser_reach(site):
    """Can the beam reach every point of the alarm zone between the arm's tilt stops?"""
    arm = site["arm"]
    lo, hi = arm.get("tilt_stops_deg", [0.5, 89.5])
    h = arm["pivot_h_m"]
    reach_max, reach_min = h / math.tan(math.radians(lo)), h / math.tan(math.radians(hi))
    dists = np.linalg.norm(alarm_zone_corners(site) - np.asarray(arm["xy"], float), axis=1)
    far = float(dists.max())
    near = float(np.linalg.norm(np.clip(np.asarray(arm["xy"]), *alarm_zone_corners(site)[[0, 2]]) - arm["xy"]))
    ok = far <= reach_max and near >= reach_min
    return {"ok": ok, "far_m": far, "reach_m": reach_max, "near_m": near, "min_reach_m": reach_min,
            "shortfall_m": max(0.0, far - reach_max)}


# --------------------------------------------------------------------------- report

def report(site):
    cam = site["fitted"]["camera"]
    rho = (site.get("detector") or {}).get("density_px_per_m", 100)
    fp, q, d = fx.lens(cam)
    lines = [f"camera {cam['id']}: f/p {fp:.0f} px, q {q:.3f}, D {d:.3f}"]
    for m, (s, dist) in largest_zone(cam, rho).items():
        lines.append(f"largest zone at {rho} px/m ({m}): {s:.1f} m square, camera {dist:.1f} m from its centre")
    p = pose_check(site, rho)
    lines.append(f"pose: {p['distance']:.1f} m from the pit centre, camera {p['height_m']:.2f} m up "
                 f"(window {p['height_window'][0]:.2f}-{p['height_window'][1]:.2f} m), far edge "
                 f"{p['far_edge_ppm']:.0f} px/m: {'OK' if p['ok'] else '; '.join(p['problems'])}")
    w = placement_window(site, rho)
    lines.append(f"placement window: {w[0]:.1f}-{w[1]:.1f} m" if w else "placement window: none")
    r = ring_check(site)
    lines.append(f"warning ring: lowest {r['min_ppm']:.0f} px/m in the processed image "
                 f"({'OK' if r['ok'] else str(len(r['below'])) + ' points below ' + str(rho)})")
    lr = laser_reach(site)
    lines.append(f"laser: far corner {lr['far_m']:.2f} m, reach {lr['reach_m']:.2f} m: "
                 + ("OK" if lr["ok"] else f"short by {lr['shortfall_m']:.2f} m"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", choices=catalog.PROFILES)
    ap.add_argument("--distance", type=float, help="move the stand to this distance from the pit centre")
    ap.add_argument("--height", type=float, help="set the camera height")
    a = ap.parse_args(argv)
    site = moved(catalog.load_site(profile=a.profile), a.distance, a.height)
    print(report(site))


if __name__ == "__main__":
    main()
