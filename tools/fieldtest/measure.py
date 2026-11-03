"""Measured against predicted: two clicks on a vertical object of known length (a 1 m pole, or a
squatting worker's head and feet). The lower click and the pose give its ground position; both
ends projected through the calibrated camera give the predicted pixel length."""
from __future__ import annotations

import csv
import math
import os

PASS_PCT, FLOOR_PX, SHORT_PX = 5.0, 1.0, 20.0
NOT_RUN = "not run"                 # a row's result until the pose is solved
NO_GROUND = "the lower click has no ground position under this camera: click the object's base"
FIELDS = ("label", "length_m", "bottom_u", "bottom_v", "top_u", "top_v", "ground_x", "ground_y",
          "distance_m", "predicted_px", "measured_px", "error_px", "error_pct", "result")


def passes(predicted_px, measured_px, pct=PASS_PCT, floor_px=FLOOR_PX):
    """Within ±pct of the prediction, or ±floor_px for objects under 20 px."""
    err = abs(measured_px - predicted_px)
    if predicted_px < SHORT_PX:
        return err <= floor_px + 1e-9
    return 100.0 * err / predicted_px <= pct + 1e-9


def num(value, spec):
    """A row's number for printing; a row with no prediction has None."""
    return "-" if value is None else format(value, spec)


def measure(cam, bottom, top, length_m, label, pct, floor_px):
    """One measurement row (see FIELDS). bottom and top are real image pixels. A base this camera
    can't place on the ground (above its horizon) stays a row, with no prediction, and fails: the
    click may be right and the camera wrong, as when a cone is undone."""
    g = cam.ground_of_pixel(*bottom)
    pred = float("nan") if g is None else cam.pole_px(g, length_m)
    meas = float(math.dist(bottom, top))
    clicks = {"label": label, "length_m": float(length_m),
              "bottom_u": float(bottom[0]), "bottom_v": float(bottom[1]), "top_u": float(top[0]), "top_v": float(top[1])}
    if not pred > 0:                    # above the horizon, behind the camera or no length
        return {**clicks, "ground_x": None, "ground_y": None, "distance_m": None, "predicted_px": None,
                "measured_px": round(meas, 3), "error_px": None, "error_pct": None, "result": "FAIL"}
    return {**clicks,
            "ground_x": round(g[0], 4), "ground_y": round(g[1], 4),
            "distance_m": round(cam.ground_distance(g), 4),
            "predicted_px": round(pred, 3), "measured_px": round(meas, 3), "error_px": round(meas - pred, 3),
            "error_pct": round(100.0 * (meas - pred) / pred, 3),
            "result": "PASS" if passes(pred, meas, pct, floor_px) else "FAIL"}


def write_csv(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path
