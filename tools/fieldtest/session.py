"""A field-test session: the settings, the lens, the cone clicks and the measurement clicks, saved
as JSON. Every result is worked out from the session alone (`evaluate`), so a recording replayed
with the same clicks gives the same log as the live run."""
from __future__ import annotations

import json
import os
import time

import numpy as np

from tools.fieldtest import lens as ln
from tools.fieldtest import load_phone, nominal_fp
from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov
from tools.fieldtest import pose as ps
from tools.fieldtest import source as src
from tools.fieldtest import sweep as sw
from tools.fieldtest.calib import against_nominal

PER_FOCAL = ("cones", "measurements", "sweep")      # made on the picture of one focal length


def new(size, source="", preset="default", phone=None, **settings):
    phone = phone or load_phone()
    p = dict(phone["presets"][preset])
    p.update({k: v for k, v in settings.items() if v is not None})
    return {"source": source, "size": list(size), "preset": preset, "focal_equiv_mm": p["focal_equiv_mm"],
            "rho": p["rho"], "taped_height_m": p.get("height_m"), "fit_zone": bool(p.get("fit_zone")), "taped_square": p.get("taped_square"), "lens": None, "cones": [],
            "measurements": [], "sensors": None, "pass": phone["pass"]}


def load_saved_lens(session, folder):
    """The session with the lens calibrated at its frame size and focal length, if `folder` has one."""
    lens = ln.load(folder, session["size"], session["focal_equiv_mm"])
    if lens:
        session["lens"] = lens.to_dict()
    return session


def set_focal(session, focal, folder):
    """Change the focal length: its own lens and clicks come in, and this one's are kept for coming
    back. A click locates a point only in the picture it was made on. Returns whether it changed."""
    old, focal = float(session["focal_equiv_mm"]), float(focal)
    if focal == old:
        return False
    parked = session.setdefault("parked", {})
    parked[f"{old:g}"] = {k: session.get(k) for k in PER_FOCAL}
    session.update(parked.pop(f"{focal:g}", {"cones": [], "measurements": [], "sweep": None}), focal_equiv_mm=focal, lens=None)
    load_saved_lens(session, folder)
    return True


def save(session, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(session, f, indent=1)
    return path


def load(path):
    with open(path) as f:
        return json.load(f)


def resume(path, fresh):
    """The session saved at `path` if it is the same setup as `fresh` (frame size and preset), so
    restarting the page keeps the clicks. Any other file is moved aside, never overwritten."""
    if not os.path.exists(path):
        return fresh
    try:
        old = load(path)
        if old["size"] == fresh["size"] and old["preset"] == fresh["preset"]:
            return {**fresh, **old, "source": fresh["source"]}
    except (ValueError, KeyError, TypeError):
        pass
    stem, ext = os.path.splitext(path)
    os.replace(path, f"{stem}_{time.strftime('%H%M%S')}{ext}")
    return fresh


def lens_of(session):
    """The calibrated lens if the session has one, else the nominal pinhole at the received size."""
    if session.get("lens"):
        return ln.FieldLens.from_dict(session["lens"])
    size = session["size"]
    return ln.FieldLens.pinhole(size, nominal_fp(size[0], session["focal_equiv_mm"]))


def height_of(session):
    return session.get("taped_height_m") or 1.5


def zone_of(session, lens):
    """The square: the one already taped if the preset names it, else fitted to a tilted phone, else
    from the level-camera formulas. It stays put once the pose is solved: the markers are its truth."""
    if session.get("taped_square"):
        return ov.taped_zone(lens, session["rho"], **session["taped_square"])
    if session.get("fit_zone"):
        return ov.fit_zone(lens, session["rho"], height_of(session))
    return ov.zone(lens.fx, *lens.size, session["rho"])


def camera_of(session, lens):
    """The solved camera or, until the cones give one, the camera the layout assumes: at the taped
    height over the origin, aimed at the square's centre. Cones with no pose add the reason as
    `error`: a mistyped cone must not stop the page."""
    def assumed():
        return {"camera": ov.aimed(lens, zone_of(session, lens), height_of(session)), "solved": False}
    if len(session["cones"]) < ps.MIN_CONES:
        return assumed()
    try:
        return ps.solve([(c["x"], c["y"]) for c in session["cones"]], [(c["u"], c["v"]) for c in session["cones"]], lens)
    except ValueError as e:
        return {**assumed(), "error": str(e)}


def row_of(session, cam, m, judged=True):
    """The measurement row of one stored click."""
    band = session["pass"]
    return ms.measure(cam, m["bottom"], m["top"], m.get("length_m", 1.0), m.get("label", ""),
                      band["density_pct"], band["density_floor_px"], judged)


def evaluate(session):
    """Every result and its PASS/FAIL, from the session alone."""
    band = session["pass"]
    lens = lens_of(session)
    out = {"lens": lens.to_dict(), "nominal": against_nominal(lens, session["focal_equiv_mm"])}
    out["steps"] = {"lens": None if not lens.calibrated else lens.rms <= band["lens_rms_px"]}
    pose = camera_of(session, lens)
    cam = pose["camera"]
    judged = pose["solved"]                      # an assumed camera is a preview: nothing is judged against it
    out["pose"] = ps.summary(pose)
    if judged:
        ok = pose["max_reproj_px"] <= band["pose_reproj_px"]
        if session.get("taped_height_m") is not None:
            ok = ok and abs(pose["height_m"] - session["taped_height_m"]) <= band["pose_height_m"]
        out["steps"]["pose"] = ok
    else:
        out["steps"]["pose"] = False if "error" in pose else None
    z = zone_of(session, lens)
    out["zone"] = {k: round(float(z[k]), 4) for k in ov.ZONE_NUMBERS}
    out["layout"] = ov.layout(z)
    out["corners"] = ov.corner_table(cam, z)
    out["box"] = ov.zone_box(cam, z)
    out["overlay_allowed"] = src.overlay_allowed(session["size"], lens)
    # on a frame like 16:9 the nominal lens doesn't apply, so neither does its overlay
    overlay = overlay_check(session, cam, z, band["overlay_pct_of_width"], judged and out["overlay_allowed"])
    rows = [row_of(session, cam, m, judged) for m in session["measurements"]]
    out["overlay"], out["measurements"] = overlay, rows
    out["steps"]["overlay"] = overlay["ok"]
    out["steps"]["density"] = all(r["result"] == "PASS" for r in rows) if rows and judged else None
    if session.get("sweep"):
        out["steps"]["detection"] = sw.detection_ok(session["sweep"]) if judged else None
    return out, cam, z


def overlay_check(session, cam, z, pct, judged=True):
    """Each cone named after a square corner, against the drawn corner (within pct of the width).
    Not `judged`, the offsets are still shown, with no verdict."""
    named = dict(zip(ov.CORNERS, ov.camera_square(cam, z)[0]))
    rows = []
    for c in session["cones"]:
        if c.get("name") in named:
            g = named[c["name"]]
            uv, _ = cam.image_points([[g[0], g[1], 0.0]])
            off = float(np.hypot(uv[0, 0] - c["u"], uv[0, 1] - c["v"]))
            rows.append({"corner": c["name"], "off_px": round(off, 2), "off_pct": round(100 * off / cam.width, 2),
                         "ok": 100 * off / cam.width <= pct if judged else None})
    return {"rows": rows, "ok": all(r["ok"] for r in rows) if rows and judged else None}
