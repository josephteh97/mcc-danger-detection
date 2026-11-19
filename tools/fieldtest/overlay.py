"""The largest square zone for the calibrated lens, drawn on the live picture, and the cone layout
sheet to tape out. The zone numbers come from `tools.coverage.largest_zone` (fov method: the phone
removes the main camera's distortion); the px/m at each corner from the full 3D projection."""
from __future__ import annotations

import math

import cv2
import numpy as np

from tools.coverage import largest_zone
from tools.fieldtest import camera_spec
from tools.fieldtest.lens import FieldCamera

CORNERS = ("far left", "far right", "near right", "near left")      # the order `square` returns
SQUARE_NUMBERS = ("w_max", "z_max", "s", "d", "near")
ZONE_NUMBERS = ("rho", "fp", "n", *SQUARE_NUMBERS)                   # a zone's other keys aren't numbers
RHO_RANGE = (10.0, 5000.0)                                           # px/m; the grid grows as 1/rho, and below this it stalls the page
FIT_SCANS = (24, 6, 6, 6, 6, 6, 6)                                   # far edges tried in each narrowing pass
NEAR_SCAN = 12                                                       # near edges tried for each far edge
GREEN, YELLOW, CYAN, WHITE, GRID = (60, 220, 60), (0, 220, 255), (255, 220, 0), (255, 255, 255), (200, 130, 230)


def check_rho(rho):
    """A ρ the page can draw, or a ValueError that says why not."""
    lo, hi = RHO_RANGE
    if not lo <= rho <= hi:
        raise ValueError(f"ρ must be between {lo:g} and {hi:g} px/m")
    return rho


def check_marks(half_m, far_m, centre_m):
    """A square whose near edge is ahead of the phone and short of its far edge, or a ValueError."""
    if not (half_m > 0 and 0 < 2 * centre_m - far_m < far_m):
        raise ValueError(f"taped_square needs half_m > 0 and 0 < near edge < far_m: got half_m {half_m}, far_m {far_m}, centre_m {centre_m}")


def zone(fp, n, h, rho):
    """W_max, z_max, S, d and the near edge for centre ratio fp on an N × h image at rho px/m."""
    s, d = largest_zone(camera_spec(fp, n, h), rho)["fov"]
    z_max = d + s / 2
    return {"rho": rho, "fp": fp, "n": n, "w_max": n / rho, "z_max": z_max, "s": s, "d": d, "near": z_max - s}


def taped_zone(lens, rho, half_m, far_m, centre_m):
    """The square already on the floor: its marks stay put whatever the lens or rho. W_max is the
    frame's width at its far edge (N ÷ rho only when the far edge is z_max = f/p ÷ rho)."""
    plan = zone(lens.fx, *lens.size, rho)
    return {**plan, "w_max": far_m * plan["n"] / plan["fp"], "z_max": far_m, "s": 2 * half_m, "d": centre_m,
            "near": 2 * centre_m - far_m, "taped": True}


_fitted = {}                                     # the page asks for the zone on every frame


def fit_zone(lens, rho, height_m):
    """The largest square a low, tilted phone really covers: in the frame and with its far corners'
    3D px/m at rho or better, for the phone at height_m aimed at the square's centre. `zone` assumes a
    level camera, which leaves room on both counts. Falls back to it if no square reaches rho."""
    key = (str(lens.to_dict()), rho, height_m)
    if key not in _fitted:
        _fitted[key] = _fit_zone(lens, rho, height_m)
    return _fitted[key]


def _bisect(good, bad, ok, steps=24):
    """The last point found where ok holds, between good (it does) and bad (it doesn't)."""
    for _ in range(steps):
        mid = (good + bad) / 2
        good, bad = (mid, bad) if ok(mid) else (good, mid)
    return good


def _fit_zone(lens, rho, height_m):
    plan = zone(lens.fx, *lens.size, rho)

    def between(near, far):
        return {**plan, "w_max": far * plan["n"] / plan["fp"], "z_max": far, "s": far - near, "d": (far + near) / 2, "near": near}

    def in_frame(near, far):
        z = between(near, far)
        box = zone_box(aimed(lens, z, height_m), z)
        return box and box["in_frame"]

    def dense(near, far):
        z = between(near, far)
        return min((r["px_per_m_3d"] or 0.0) for r in corner_table(aimed(lens, z, height_m), z)[:2]) >= rho

    def widest(far):
        """The biggest square with this far edge: to the frame's edge if that's dense enough, else
        scan for one that is. A bigger square can pass where a smaller one fails, as it moves the aim."""
        edge = _bisect(far, 0.0, lambda near: in_frame(near, far), steps=14)
        if dense(edge, far):
            return between(edge, far)
        nears = np.linspace(edge, far, NEAR_SCAN + 2)
        for i in range(1, NEAR_SCAN + 1):
            if dense(nears[i], far):
                return between(_bisect(nears[i], nears[i - 1], lambda near: dense(near, far), steps=14), far)
        return between(far, far)

    lo, hi = plan["z_max"] / 2, plan["z_max"] * 2
    for n in FIT_SCANS:                          # the best far edge needn't be where density first falls to rho
        squares = [widest(far) for far in np.linspace(lo, hi, n)]
        best = max(range(n), key=lambda i: squares[i]["s"])
        lo, hi = squares[max(best - 1, 0)]["z_max"], squares[min(best + 1, n - 1)]["z_max"]
    z = squares[best]
    if z["s"] <= 0:
        return plan
    step = plan["z_max"] * 1.5 / (FIT_SCANS[0] - 1)   # the same size further out: as far as the density allows
    return widest(_bisect(z["z_max"], z["z_max"] + step, lambda far: widest(far)["s"] >= z["s"], steps=14))


def square(z, origin=(0.0, 0.0), heading_deg=0.0):
    """The square's corners (in CORNERS order) and centre on the ground, centred on the forward line from `origin` (the point under the phone) along `heading`."""
    h = math.radians(heading_deg)
    fwd, right = np.array([math.sin(h), math.cos(h)]), np.array([math.cos(h), -math.sin(h)])
    o, half = np.asarray(origin, dtype=np.float64), z["s"] / 2
    far, near = o + fwd * z["z_max"], o + fwd * z["near"]
    corners = np.array([far - right * half, far + right * half, near + right * half, near - right * half])
    return corners, o + fwd * z["d"]


def _along(a, b, steps):
    """`steps` ground points along each segment a[i] to b[i], in order: (len(a) · steps, 2)."""
    return (a[:, None] + (b - a)[:, None] * np.linspace(0, 1, steps)[None, :, None]).reshape(-1, 2)


def camera_square(cam, z):
    """The square straight ahead of this camera or, once taped, where it is on the floor."""
    return square(z) if z.get("taped") else square(z, cam.pos[:2], cam.heading_deg)


def layout(z):
    """The layout sheet: (x, y) metres from the point under the phone, ready to tape out."""
    corners, centre = square(z)
    marks = [[0.0, float(m)] for m in range(1, int(math.floor(z["z_max"])) + 1)]
    return {"corners": {name: [round(float(x), 2), round(float(y), 2)] for name, (x, y) in zip(CORNERS, corners)},
            "centre": [0.0, round(float(centre[1]), 2)],
            "w_max_points": [[-round(z["w_max"] / 2, 2), round(z["z_max"], 2)], [round(z["w_max"] / 2, 2), round(z["z_max"], 2)]],
            "forward_marks": marks,
            "numbers": {k: round(float(z[k]), 2) for k in SQUARE_NUMBERS}}


def describe_layout(sheet):
    n = sheet["numbers"]
    lines = [f"square S {n['s']:.2f} m, centre d {n['d']:.2f} m, z_near {n['near']:.2f} m, "
             f"z_far {n['z_max']:.2f} m (= z_max), W_max {n['w_max']:.2f} m",
             "Tape out (x right, y ahead, metres from the point under the phone):"]
    lines += [f"  {name:10s} ({x:+.2f}, {y:.2f})" for name, (x, y) in sheet["corners"].items()]
    lines.append(f"  centre     ({sheet['centre'][0]:+.2f}, {sheet['centre'][1]:.2f})")
    lines += [f"  W_max end  ({x:+.2f}, {y:.2f})" for x, y in sheet["w_max_points"]]
    lines.append("  1 m marks on the forward line at y = " + ", ".join(f"{m[1]:g}" for m in sheet["forward_marks"]))
    return "\n".join(lines)


def corner_table(cam, z):
    """Per corner: ground position, 3D px/m (`FieldCamera.px_per_m`, None behind the camera) and
    the plan-view px/m f/p ÷ forward distance (None at or behind the camera), which only equals it
    for a level camera."""
    corners, _ = camera_square(cam, z)
    rows = []
    for name, (x, y) in zip(CORNERS, corners):
        fwd = float(np.dot([x - cam.pos[0], y - cam.pos[1]], cam.ground_axes()[0]))
        rows.append({"corner": name, "x": float(x), "y": float(y), "px_per_m_3d": cam.px_per_m((x, y)),
                     "px_per_m_plan": z["fp"] / fwd if fwd > 0 else None})
    return rows


def aimed(lens, z, height_m):
    """The camera the layout assumes before the cones are clicked: at height_m over the origin,
    looking straight ahead and pitched down so the square's centre (0, d) is at the image centre."""
    cam = FieldCamera.posed(lens, height_m, math.degrees(math.atan2(height_m, z["d"])))
    cam.preview = True
    return cam


def zone_box(cam, z, steps=24):
    """The square in the real image: each corner's pixel and the bounding box of its outline (edges
    bent through the lens), or None when part of it is behind the camera."""
    corners, _ = camera_square(cam, z)
    edge = _along(corners, np.roll(corners, -1, axis=0), steps)
    uv, depth = cam.image_points(np.column_stack([edge, np.zeros(len(edge))]))
    if np.any(depth <= 0):
        return None
    cuv, _ = cam.image_points(np.column_stack([corners, np.zeros(4)]))
    (u0, v0), (u1, v1) = uv.min(axis=0), uv.max(axis=0)
    return {"corners_px": {name: [round(float(u), 1), round(float(v), 1)] for name, (u, v) in zip(CORNERS, cuv)},
            "box_px": [round(float(c), 1) for c in (u0, v0, u1, v1)],
            "width_px": round(float(u1 - u0), 1), "height_px": round(float(v1 - v0), 1),
            "in_frame": bool(u0 >= 0 and v0 >= 0 and u1 <= cam.width and v1 <= cam.height)}


def zone_text(z):
    return (f"S {z['s']:.2f} m, d {z['d']:.2f} m, z_near {z['near']:.2f} m, z_far {z['z_max']:.2f} m (= z_max), "
            f"W_max {z['w_max']:.2f} m")


def box_text(box):
    u0, v0, u1, v1 = box["box_px"]
    return (f"u {u0:.0f}–{u1:.0f}, v {v0:.0f}–{v1:.0f} px ({box['width_px']:.0f} × {box['height_px']:.0f} px), "
            f"{'inside' if box['in_frame'] else 'NOT inside'} the frame")


def describe_zone(z, box, cam):
    """S, d, z_near, z_far and the square's bounding box in the image, for the terminal."""
    lines = [f"rho {z['rho']:g} px/m, f/p {z['fp']:.1f} px, frame {cam.width} × {cam.height}", zone_text(z),
             f"phone at {cam.pos[2]:.2f} m, pitch {cam.pitch_deg:.1f}° down"]
    if box is None:
        return "\n".join(lines + ["the square is partly behind the camera: no bounding box"])
    lines.append(f"bounding box {box_text(box)}")
    lines += [f"  {name:10s} ({u:7.1f}, {v:6.1f}) px" for name, (u, v) in box["corners_px"].items()]
    return "\n".join(lines)


def footprint(cam, max_range_m=40.0, n=64):
    """The ground seen by the camera: image-border rays to the ground, capped at max_range_m."""
    w, h = cam.width, cam.height
    border = np.concatenate([np.column_stack([np.linspace(0, w, n), np.zeros(n)]),
                             np.column_stack([np.full(n, w), np.linspace(0, h, n)]),
                             np.column_stack([np.linspace(w, 0, n), np.full(n, h)]),
                             np.column_stack([np.zeros(n), np.linspace(h, 0, n)])])
    d = cam.rays(*cam.lens.undistort(border).T)
    down = d[:, 2] < -1e-9
    s = np.full(len(d), math.inf)
    s[down] = -cam.pos[2] / d[down, 2]
    s = np.minimum(s, max_range_m / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9))
    return cam.pos[:2] + s[:, None] * d[:, :2]


def _drawable(uv):
    """Pixels OpenCV can take: a wild pose projects points absurdly far off the picture."""
    return np.all(np.abs(uv) < 1e6, axis=-1)


def _placed(cam, ground_xy):
    """Ground points (N, 2) -> real image pixels, and which of them can be drawn: in front of the
    camera and inside the calibrated part of the image. Beyond it the distortion polynomial folds
    points back into the picture, where they would look like real ones."""
    g = np.asarray(ground_xy, dtype=np.float64)
    ideal, z = cam.project(np.column_stack([g, np.zeros(len(g))]))
    uv = cam.lens.distort(ideal)
    return uv, (z > 0.05) & cam.lens.in_fit(ideal.T) & _drawable(uv)


def _poly(img, cam, ground_xy, colour, closed=True, thickness=2, steps=24):
    """Draw a ground polygon, each edge bent through the lens."""
    g = np.asarray(ground_xy, dtype=np.float64)
    a, b = (g, np.roll(g, -1, axis=0)) if closed else (g[:-1], g[1:])
    uv, ok = _placed(cam, _along(a, b, steps))
    edges = zip(uv.reshape(len(a), steps, 2), ok.reshape(len(a), steps))
    lines = [np.round(e[keep] * 4).astype(np.int32) for e, keep in edges if keep.sum() >= 2]
    if lines:
        cv2.polylines(img, lines, False, colour, thickness, cv2.LINE_AA, shift=2)


def _label(img, xy, text, colour=WHITE, scale=0.55):
    """Text on a dark box, up and right of the point or, with no room at the right edge, down and
    left, clear of the point (OpenCV's font is ASCII only: write 'deg', not the degree sign)."""
    x, y = int(xy[0]) + 6, int(xy[1]) - 6
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    if x + w + 4 > img.shape[1]:
        x, y = int(xy[0]) - 12 - w, int(xy[1]) + 12 + h
    x = max(x, 0)
    cv2.rectangle(img, (x - 3, y - h - 4), (x + w + 3, y + base + 2), (20, 20, 20), -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, colour, 1, cv2.LINE_AA)


def draw(frame, cam, z, grid_m=1.0):
    """The overlay: footprint, 1 m grid, W_max line at z_max, square S, its centre at d and the
    3D px/m at each corner (with the plan-view value beside it when the camera is tilted)."""
    img = frame.copy()
    corners, centre = camera_square(cam, z)
    fp_poly = footprint(cam, max_range_m=z["z_max"] * 1.5)
    lo, hi = fp_poly.min(axis=0), fp_poly.max(axis=0)
    for x in np.arange(math.floor(lo[0]), math.ceil(hi[0]) + 1, grid_m):
        _poly(img, cam, [[x, max(lo[1], 0.3)], [x, hi[1]]], GRID, closed=False, thickness=1)
    for y in np.arange(math.ceil(max(lo[1], 0.3)), math.ceil(hi[1]) + 1, grid_m):
        _poly(img, cam, [[lo[0], y], [hi[0], y]], GRID, closed=False, thickness=1)
    _poly(img, cam, fp_poly, CYAN, thickness=1)
    _poly(img, cam, camera_square(cam, {**z, "s": z["w_max"]})[0][:2], YELLOW, closed=False)
    _poly(img, cam, corners, GREEN, thickness=3)
    tilted = abs(cam.pitch_deg) > 1.0
    uv, ok = _placed(cam, corners)
    for row, p, seen in zip(corner_table(cam, z), uv, ok):
        if seen and row["px_per_m_3d"] is not None:
            text = f"{row['px_per_m_3d']:.0f} px/m" + (f" (plan {row['px_per_m_plan']:.0f})" if tilted and row["px_per_m_plan"] else "")
            cv2.circle(img, tuple(int(c) for c in p), 5, GREEN, -1, cv2.LINE_AA)
            _label(img, p, text, GREEN)
    uv, ok = _placed(cam, [centre])
    if ok[0]:
        cv2.drawMarker(img, tuple(int(c) for c in uv[0]), GREEN, cv2.MARKER_CROSS, 18, 2)
        _label(img, uv[0], f"d {z['d']:.2f} m", GREEN)
    _label(img, (2, 30), f"rho {z['rho']:g} px/m  N {z['n']}  f/p {z['fp']:.0f}  S {z['s']:.2f} m  "
                         f"z_max {z['z_max']:.2f} m  pitch {cam.pitch_deg:.1f} deg", WHITE)
    return img
