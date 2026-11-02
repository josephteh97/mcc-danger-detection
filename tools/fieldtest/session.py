"""A field-test session: the settings, the lens, the cone clicks and the measurement clicks, saved
as JSON. Every result is worked out from the session alone (`evaluate`), so a recording replayed
with the same clicks gives the same log as the live run."""
from __future__ import annotations

import json
import math
import os

import numpy as np

from tools.fieldtest import load_phone, nominal_fp
from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov
from tools.fieldtest import pose as ps
from tools.fieldtest.calib import against_nominal
from tools.fieldtest.lens import FieldCamera, FieldLens


def new(size, source="", preset="default", phone=None, **settings):
    phone = phone or load_phone()
    p = dict(phone["presets"][preset])
    p.update({k: v for k, v in settings.items() if v is not None})
    return {"source": source, "size": list(size), "preset": preset, "focal_equiv_mm": p["focal_equiv_mm"],
            "rho": p["rho"], "taped_height_m": p.get("height_m"), "lens": None, "cones": [],
            "measurements": [], "sensors": None, "pass": phone["pass"]}


def save(session, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(session, f, indent=1)
    return path


def load(path):
    with open(path) as f:
        return json.load(f)


def lens_of(session):
    """The calibrated lens if the session has one, else the nominal pinhole at the received size."""
    if session.get("lens"):
        return FieldLens.from_dict(session["lens"])
    size = session["size"]
    return FieldLens.pinhole(size, nominal_fp(size[0], session["focal_equiv_mm"]))


def camera_of(session, lens=None):
    """The solved camera, or a level camera at the taped height until the cones are clicked."""
    lens = lens or lens_of(session)
    if len(session["cones"]) >= 4:
        return ps.solve([(c["x"], c["y"]) for c in session["cones"]], [(c["u"], c["v"]) for c in session["cones"]], lens)
    return {"camera": FieldCamera.posed(lens, session.get("taped_height_m") or 1.5), "solved": False}


def evaluate(session):
    """Every result and its PASS/FAIL, from the session alone."""
    band = session["pass"]
    lens = lens_of(session)
    out = {"lens": lens.to_dict(), "nominal": against_nominal(lens, session["focal_equiv_mm"])}
    out["steps"] = {"lens": None if not lens.calibrated else lens.rms <= band["lens_rms_px"]}
    pose = camera_of(session, lens)
    cam = pose["camera"]
    out["pose"] = ps.summary(pose)
    if pose.get("solved", True):
        ok = pose["max_reproj_px"] <= band["pose_reproj_px"]
        if session.get("taped_height_m") is not None:
            ok = ok and abs(pose["height_m"] - session["taped_height_m"]) <= band["pose_height_m"]
        out["steps"]["pose"] = ok
    else:
        out["steps"]["pose"] = None
    z = ov.zone(lens.fx, lens.size[0], lens.size[1], session["rho"])
    out["zone"] = {k: round(float(v), 4) for k, v in z.items()}
    out["layout"] = ov.layout(z)
    out["corners"] = ov.corner_table(cam, z)
    out["overlay"] = overlay_check(session, cam, z, band["overlay_pct_of_width"])
    out["steps"]["overlay"] = out["overlay"]["ok"]
    out["measurements"] = [ms.measure(cam, m["bottom"], m["top"], m.get("length_m", 1.0), m.get("label", ""),
                                      band["density_pct"], band["density_floor_px"]) for m in session["measurements"]]
    out["steps"]["density"] = all(r["result"] == "PASS" for r in out["measurements"]) if out["measurements"] else None
    if session.get("sensors"):
        out["sensors"] = session["sensors"]
    if session.get("sweep"):                     # reliable down to the twin's 100 px box
        p90 = session["sweep"].get("point_90")
        out["steps"]["detection"] = p90 is None or p90["box_h_px"] <= 100
    return out, cam, z


def overlay_check(session, cam, z, pct):
    """Each cone named after a square corner, against the drawn corner (within pct of the width)."""
    corners, _ = ov.square(z, cam.pos[:2], math.degrees(math.atan2(cam.R[2][0], cam.R[2][1])))
    named = dict(zip(("far left", "far right", "near right", "near left"), corners))
    rows = []
    for c in session["cones"]:
        if c.get("name") in named:
            g = named[c["name"]]
            uv, _ = cam.image_points([[g[0], g[1], 0.0]])
            off = float(np.hypot(uv[0, 0] - c["u"], uv[0, 1] - c["v"]))
            rows.append({"corner": c["name"], "off_px": round(off, 2), "off_pct": round(100 * off / cam.width, 2),
                         "ok": 100 * off / cam.width <= pct})
    return {"rows": rows, "ok": all(r["ok"] for r in rows) if rows else None}
