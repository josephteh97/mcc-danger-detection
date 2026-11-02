"""Ultra-wide distortion test (design.md D10): calibrate ultra-wide photos taken with the phone's
distortion correction off, then check the twin's lens model against the real lens.

q and D come from the calibrated centre f/p and the measured horizontal field of view with
`catalog.effects.lens`, exactly as the twin gets them from a datasheet. The twin's density factor
g = 1 − D·u² (u: tangent of the angle off the axis) is compared with the calibrated lens's own
radial magnification at u = 0.25, 0.5, 0.75 and the image edge, and a 1 m pole at the edge and
at the centre (same depth) is compared with the same g.
"""
from __future__ import annotations

import math

import numpy as np

from catalog import effects as fx

POINTS = (0.25, 0.5, 0.75)


def _x_of_u(lens, u):
    """Real image column of the point at tangent u along the horizontal through the centre."""
    return lens.distort([[lens.cx + u * lens.fx, lens.cy]])[0, 0]


def edge_tangent(lens):
    """Tangent of the angle to the image's left and right edges along the centre row (the mean)."""
    ideal = lens.undistort([[0.0, lens.cy], [lens.size[0], lens.cy]])
    return float(np.mean(np.abs(ideal[:, 0] - lens.cx)) / lens.fx)


def measured_hfov(lens):
    return math.degrees(2 * math.atan(edge_tangent(lens)))


def model(lens):
    """(f/p, q, D) for this lens as the twin's datasheet route computes them."""
    return fx.lens({"resolution_px": list(lens.size), "hfov_deg": measured_hfov(lens), "dori_fp_px": lens.fx})


def g_calibrated(lens, u, h=1e-4):
    """The calibrated lens's radial magnification at tangent u, relative to the centre."""
    return (_x_of_u(lens, u + h) - _x_of_u(lens, u - h)) / (2 * h) / lens.fx


def compare(lens):
    """Table of g from the model (1 − D·u²) against the calibrated lens, and the largest difference."""
    _, q, d = model(lens)
    t = edge_tangent(lens)
    rows = []
    for name, u in [*((f"u = {p:g}", p) for p in POINTS if p < t), ("image edge", t)]:
        gm, gc = 1 - d * u * u, g_calibrated(lens, u)
        rows.append({"at": name, "u": u, "g_model": gm, "g_calibrated": gc, "diff_pct": 100.0 * (gm - gc) / gc})
    return {"hfov_deg": measured_hfov(lens), "edge_tangent": t, "fp": lens.fx, "q": q, "D": d, "rows": rows,
            "max_diff_pct": max(abs(r["diff_pct"]) for r in rows)}


def pole_ratio(centre_px, edge_px, edge_u, d):
    """Measured edge-to-centre length of a 1 m pole at the same depth, against the twin's 1 − D·u²."""
    return {"measured": edge_px / centre_px, "model": 1 - d * edge_u ** 2}


def describe(c):
    lines = [f"ultra-wide: HFOV {c['hfov_deg']:.1f}°, centre f/p {c['fp']:.0f} px, q {c['q']:.3f}, D {c['D']:.3f}",
             f"{'where':12s} {'u':>6s} {'1 − D·u²':>9s} {'lens':>7s} {'diff':>7s}"]
    lines += [f"{r['at']:12s} {r['u']:6.3f} {r['g_model']:9.3f} {r['g_calibrated']:7.3f} {r['diff_pct']:6.1f}%" for r in c["rows"]]
    lines.append(f"largest difference {c['max_diff_pct']:.1f}%")
    return "\n".join(lines)
