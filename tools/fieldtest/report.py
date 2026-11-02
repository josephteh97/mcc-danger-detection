"""The field-test report: Markdown, the measurement CSV and annotated images in
reports/fieldtest/<date>/ (git-ignored)."""
from __future__ import annotations

import os
import time

import cv2

from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov

PRIVACY = ("Recordings and stills that show people are personal data: delete them once the test is "
           "done, and commit only this summary, never the footage.")


def _verdict(v):
    return "not run" if v is None else "PASS" if v else "FAIL"


def annotate(frame, session, cam, z):
    """The overlay plus the cone and measurement clicks."""
    img = ov.draw(frame, cam, z)
    for c in session["cones"]:
        cv2.circle(img, (int(c["u"]), int(c["v"])), 7, (0, 140, 255), 2, cv2.LINE_AA)
        ov._label(img, (c["u"], c["v"] + 18), c.get("name") or f"({c['x']:g}, {c['y']:g})", (0, 140, 255))
    for m in session["measurements"]:
        (bu, bv), (tu, tv) = m["bottom"], m["top"]
        cv2.line(img, (int(bu), int(bv)), (int(tu), int(tv)), (255, 0, 255), 2, cv2.LINE_AA)
    return img


def write(session, result, cam, z, folder, frame=None):
    os.makedirs(folder, exist_ok=True)
    ms.write_csv(result["measurements"], os.path.join(folder, "measurements.csv"))
    if frame is not None:
        cv2.imwrite(os.path.join(folder, "overlay.png"), annotate(frame, session, cam, z))
    with open(os.path.join(folder, "layout.txt"), "w") as f:
        f.write(ov.describe_layout(result["layout"]) + "\n")
    path = os.path.join(folder, "report.md")
    with open(path, "w") as f:
        f.write(markdown(session, result))
    return path


def markdown(session, r):
    s, z, nom, pose = r["steps"], r["zone"], r["nominal"], r["pose"]
    lens = r["lens"]
    lines = [f"# Field test {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"Source {session['source'] or 'n/a'}, frame {session['size'][0]} × {session['size'][1]}, "
             f"{session['focal_equiv_mm']:g} mm, ρ = {session['rho']:g} px/m, preset {session['preset']}.", "",
             "| Step | Result |", "|---|---|"]
    lines += [f"| {k} | {_verdict(v)} |" for k, v in s.items()]
    how = (f"Checkerboard, {lens['views']} views, reprojection {lens['rms']:.3f} px" if lens["source"] != "nominal"
           else "Nominal (not calibrated)")
    lines += ["", "## Lens", "",
              f"{how}: fx {nom['fx']:.1f} px, fy {nom['fy']:.1f} px against the nominal {nom['nominal_fp']:.1f} px "
              f"({nom['diff_pct']:+.2f}%).", "", "## Pose", ""]
    if "height_m" in pose:
        lines.append(f"Height {pose['height_m']:.3f} m (taped {session.get('taped_height_m')}), pitch {pose['pitch_deg']:.2f}°, "
                     f"roll {pose['roll_deg']:.2f}°, heading {pose['heading_deg']:.2f}°; cone reprojection up to "
                     f"{pose['max_reproj_px']:.2f} px.")
        if r.get("sensors"):
            lines.append(f"Phone sensors (cross-check): pitch {r['sensors']['pitch_deg']:.1f}°, roll {r['sensors']['roll_deg']:.1f}°.")
    else:
        lines.append("Not solved (fewer than four cones).")
    lines += ["", "## Square", "",
              f"z_max {z['z_max']:.2f} m, W_max {z['w_max']:.2f} m, S {z['s']:.2f} m, d {z['d']:.2f} m, near edge {z['near']:.2f} m.", "",
              "| Corner | x m | y m | px/m (3D) | px/m (plan) |", "|---|---|---|---|---|"]
    lines += [f"| {c['corner']} | {c['x']:+.2f} | {c['y']:.2f} | {c['px_per_m_3d']:.1f} | {c['px_per_m_plan']:.1f} |" for c in r["corners"]]
    if r["overlay"]["rows"]:
        lines += ["", "| Cone | Off by px | % of width | |", "|---|---|---|---|"]
        lines += [f"| {o['corner']} | {o['off_px']:.1f} | {o['off_pct']:.2f} | {_verdict(o['ok'])} |" for o in r["overlay"]["rows"]]
    lines += ["", "## Measurements", "", "| Label | Length m | Distance m | Predicted px | Measured px | Error | |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {m['label']} | {m['length_m']:g} | {m['distance_m']:.2f} | {m['predicted_px']:.1f} | {m['measured_px']:.1f} | "
              f"{m['error_pct']:+.1f}% | {m['result']} |" for m in r["measurements"]]
    sweep = session.get("sweep")
    if sweep:
        p90 = sweep.get("point_90")
        lines += ["", "## Detection sweep", "",
                  f"90% point: {p90['distance_m']:.1f} m at a {p90['box_h_px']:.0f} px box." if p90 else "Detection rate never fell below 90%.",
                  "See sweep.png and sweep_steps.csv."]
    lines += ["", "## Privacy", "", PRIVACY, ""]
    return "\n".join(lines)
