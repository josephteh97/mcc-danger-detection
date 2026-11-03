"""Detection sweep (design.md D7): the twin's YOLO person detector (`app.detect`, same model and
tiling option) on frames of a person standing or squatting at marked distances along the
forward line. Steps are (t0, t1, distance_m): when the person was at each mark."""
from __future__ import annotations

import csv
import math
import os

import cv2
import numpy as np

from app.alarm import foot_pixel

REFERENCE_PX = (100, 80, 50)
RATE_OK = 0.9
REQUIRED_PX = 100                   # the twin's box for a 1 m squatting worker at the required density


def run(frames, det, cam, steps, window_m=0.75):
    """frames: iterable of (t, frame). -> {"detections": rows, "steps": rows, "point_90": ...}.
    A step's frame counts as detected when a box's foot lands within window_m of the mark."""
    dets, seen, hits = [], [0] * len(steps), [[] for _ in steps]     # per step: frames, (box height, confidence)
    for t, frame in frames:
        step = next((i for i, (t0, t1, _) in enumerate(steps) if t0 <= t <= t1), None)
        found = False
        for box, conf in det.scored(frame):
            g = cam.ground_of_pixel(*foot_pixel(box))
            dist = cam.ground_distance(g) if g else float("nan")
            h = box[3] - box[1]
            dets.append({"t": round(t, 3), "step": step, "box_h_px": round(h, 1), "confidence": round(conf, 3),
                         "distance_m": round(dist, 2)})
            if step is not None and abs(dist - steps[step][2]) <= window_m and not found:
                found = True
                hits[step].append((h, conf))
        if step is not None:
            seen[step] += 1
    rows = []
    for (_, _, d), n, hit in zip(steps, seen, hits):
        rows.append({"distance_m": d, "frames": n, "detected": len(hit), "rate": len(hit) / n if n else float("nan"),
                     "box_h_px": float(np.median([h for h, _ in hit])) if hit else float("nan"),
                     "confidence": float(np.mean([c for _, c in hit])) if hit else float("nan"),
                     "predicted_h_px": None})
    return {"detections": dets, "steps": rows, **summary(rows)}


def point_90(rows):
    """Where the detection rate first falls below 90% going out: the distance (interpolated) and the
    box height there, or None if it never does."""
    ok = [r for r in sorted(rows, key=lambda r: r["distance_m"]) if r["frames"]]
    for a, b in zip(ok, ok[1:]):
        if a["rate"] >= RATE_OK > b["rate"]:
            f = (a["rate"] - RATE_OK) / (a["rate"] - b["rate"])
            h = a["box_h_px"] + f * (b["box_h_px"] - a["box_h_px"]) if not math.isnan(b["box_h_px"]) else a["box_h_px"]
            return {"distance_m": a["distance_m"] + f * (b["distance_m"] - a["distance_m"]), "box_h_px": h}
    if ok and ok[0]["rate"] < RATE_OK:
        h = ok[0]["box_h_px"]
        return {"distance_m": ok[0]["distance_m"], "box_h_px": None if math.isnan(h) else h}
    return None


def summary(rows):
    """What a session keeps of a sweep: the 90% point, the frames judged and the smallest box height
    the rate holds 90% down to (None if it never does or no frame was judged)."""
    p90 = point_90(rows)
    boxes = [r["box_h_px"] for r in rows if r["frames"] and not math.isnan(r["box_h_px"])]
    return {"point_90": p90, "frames": sum(r["frames"] for r in rows),
            "reliable_to_px": p90["box_h_px"] if p90 else min(boxes, default=None)}


def detection_ok(sweep):
    """The sweep's result: reliable down to the twin's 100 px box. None if no frame fell inside a step."""
    if not sweep.get("frames"):
        return None
    px = sweep.get("reliable_to_px")
    return px is not None and px <= REQUIRED_PX


def write(result, folder, cam, person_h_m=1.0):
    """steps.csv, detections.csv and sweep.png (rate against distance, box height on the second
    axis, the 100/80/50 px reference heights marked)."""
    os.makedirs(folder, exist_ok=True)
    for r in result["steps"]:
        xy = cam.pos[:2] + cam.ground_axes()[0] * r["distance_m"]
        r["predicted_h_px"] = round(cam.pole_px(xy, person_h_m), 1)
    for name, rows in (("steps", result["steps"]), ("detections", result["detections"])):
        with open(os.path.join(folder, f"sweep_{name}.csv"), "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    cv2.imwrite(os.path.join(folder, "sweep.png"), plot(result))
    return folder


def plot(result, w=900, h=480, m=60):
    """Detection rate (green) and median box height (orange) against distance."""
    img = np.full((h, w, 3), 255, np.uint8)
    rows = [r for r in result["steps"] if r["frames"]]
    if not rows:
        return img
    dmax = max(r["distance_m"] for r in rows) * 1.05
    hmax = max([r["box_h_px"] for r in rows if not math.isnan(r["box_h_px"])] + [max(REFERENCE_PX)]) * 1.1
    X = lambda d: int(m + (w - 2 * m) * d / dmax)                       # noqa: E731
    Yr = lambda r: int(h - m - (h - 2 * m) * r)                         # noqa: E731
    Yh = lambda px: int(h - m - (h - 2 * m) * px / hmax)                # noqa: E731
    cv2.rectangle(img, (m, m), (w - m, h - m), (0, 0, 0), 1)
    for px in REFERENCE_PX:
        cv2.line(img, (m, Yh(px)), (w - m, Yh(px)), (200, 200, 200), 1)
        cv2.putText(img, f"{px} px", (w - m + 4, Yh(px) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 90, 90), 1)
    cv2.line(img, (m, Yr(RATE_OK)), (w - m, Yr(RATE_OK)), (180, 230, 180), 1)
    pr = [(X(r["distance_m"]), Yr(r["rate"])) for r in rows]
    ph = [(X(r["distance_m"]), Yh(r["box_h_px"])) for r in rows if not math.isnan(r["box_h_px"])]
    for pts, col in ((pr, (40, 160, 40)), (ph, (0, 140, 255))):
        if len(pts) > 1:
            cv2.polylines(img, [np.array(pts, np.int32)], False, col, 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(img, p, 4, col, -1, cv2.LINE_AA)
    p90 = result.get("point_90")
    if p90:
        cv2.line(img, (X(p90["distance_m"]), m), (X(p90["distance_m"]), h - m), (60, 60, 220), 1)
    cv2.putText(img, "detection rate (green), box height px (orange) against distance m", (m, m - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    for d in range(0, int(dmax) + 1, max(1, int(dmax) // 10)):
        cv2.putText(img, str(d), (X(d) - 4, h - m + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    return img
