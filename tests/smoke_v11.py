"""Quick checks for hardware list version 11: coverage, PoE, 4G data, power plans, identification
off, watchdog and laser reach (U11-U26). They load the v11 profile whatever site.yaml selects."""
import math

from _check import check, main

import catalog
from catalog import effects as fx
from tools import coverage as cov

SITE = catalog.load_site(profile="v11")
CAMERA = SITE["fitted"]["camera"]
RHO = SITE["detector"]["density_px_per_m"]


def near(value, target, tol):
    return abs(value - target) <= tol


# --------------------------------------------------------------------------- coverage (U11-U16)

@check("U11", "Distortion q and D")
def u11():
    fp, q, d = fx.lens(CAMERA)
    # a point on the optical axis at depth 10 m: 284 px/m at the image centre
    from world.camera import PinholeCamera
    cam = PinholeCamera.from_site(SITE)
    centre = cam.pos + 10.0 * cam.R[2]
    dens = float(fx.native_density(SITE, [centre])[0][0])
    ok = near(q, 0.571, 0.005) and near(d, 0.844, 0.01) and near(dens, 284, 1)
    return ok, f"q {q:.3f}, D {d:.3f}, centre density at 10 m {dens:.1f} px/m", \
        "q = 0.571 ± 0.005, D = 0.844 ± 0.01, centre 284 ± 1 px/m"


@check("U12", "Ring density with tiles")
def u12():
    r = cov.ring_check(SITE, {**SITE["detector"], "tiles": True})
    return r["ok"], f"lowest {r['min_ppm']:.0f} px/m over {r['points']} ring points (full-resolution tiles)", \
        f"every warning-ring point ≥ {RHO} px/m in the processed image"


@check("U13", "Shrunken detector input fails as expected")
def u13():
    r = cov.ring_check(SITE, {**SITE["detector"], "tiles": False, "input_px": 1280})
    return not r["ok"] and r["below"], \
        f"input 1280 px, no tiles: lowest {r['min_ppm']:.0f} px/m, {len(r['below'])} of {r['points']} points below {RHO}", \
        "the check reports ring points below 100 px/m and fails"


@check("U14", "Largest-zone solver")
def u14():
    z = cov.largest_zone(CAMERA, RHO)
    (s, d), (s2, d2) = z["fov"], z["distortion"]
    ok = near(s, 11.5, 0.1) and near(d, 10.4, 0.1) and near(s2, 11.2, 0.1) and near(d2, 17.1, 0.2)
    return ok, f"field of view {s:.2f} m at {d:.2f} m; distortion {s2:.2f} m at {d2:.2f} m", \
        "11.5 ± 0.1 m at 10.4 ± 0.1 m, and 11.2 ± 0.1 m at 17.1 ± 0.2 m"


@check("U15", "Pose inside windows")
def u15():
    p = cov.pose_check(SITE, RHO)
    lo, hi = p["height_window"]
    ok = p["ok"] and near(p["far_edge_ppm"], 122, 3) and near(lo, 2.7, 0.05) and near(hi, 5.7, 0.05)
    return ok, (f"stand {p['distance']:.1f} m, camera {p['height_m']:.2f} m (window {lo:.2f}-{hi:.2f} m), "
                f"far edge {p['far_edge_ppm']:.0f} px/m"), \
        "inside both windows, far edge 122 ± 3 px/m, height window 2.7-5.7 m"


@check("U16", "Stand too close is flagged")
def u16():
    p = cov.pose_check(cov.moved(SITE, 5.0), RHO)
    flagged = not p["ok"] and any("outside the image" in m for m in p["problems"])
    return flagged, "; ".join(p["problems"]) or "no problem found", \
        "at 5 m the warning ring's near corners fall outside the image and the pose is flagged"


if __name__ == "__main__":
    main("smoke_v11.py")
