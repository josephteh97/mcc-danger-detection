"""Quick checks for the phone field-test tool (P01-P11). No phone and no network: a synthetic
camera, synthetic cones and synthetic checkerboards (tests/fakes/fieldtest_synth.py)."""
import math

import numpy as np
from _check import check, main
from fakes import fieldtest_synth as syn

from tools import fieldtest as ft
from tools.fieldtest import distortion as dz
from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov
from tools.fieldtest import pose as ps
from tools.fieldtest import source as src
from tools.fieldtest.calib import calibrate, find_corners
from tools.fieldtest.lens import FieldCamera, FieldLens

PHONE = ft.load_phone()


def near(value, target, tol):
    return abs(value - target) <= tol


def default_zone():
    return ov.zone(ft.nominal_fp(1440, 23), 1440, 1080, 100)


@check("P01", "Phone solver numbers")
def p01():
    z = default_zone()
    p, fp = ft.pitch_um(PHONE, 1440), ft.nominal_fp(1440, 23)
    p_photo, fp_photo = ft.pitch_um(PHONE, 4080), ft.nominal_fp(4080, 23)
    ok = (near(z["z_max"], 9.57, 0.05) and near(z["w_max"], 14.4, 1e-6) and near(z["s"], 5.75, 0.05)
          and near(z["d"], 6.69, 0.05) and near(p, 6.35, 0.05) and near(fp, 957, 5)
          and near(p_photo, 2.24, 0.02) and near(fp_photo, 2710, 20))
    return ok, (f"z_max {z['z_max']:.2f}, W_max {z['w_max']:.1f}, S {z['s']:.2f}, d {z['d']:.2f} m; "
                f"1440 px: p {p:.2f} µm, f/p {fp:.0f}; 4080 px: p {p_photo:.2f} µm, f/p {fp_photo:.0f}"), \
        "9.57 / 14.4 / 5.75 / 6.69 m (±0.05); p 6.35 µm, f/p 957; p 2.24 µm, f/p 2,710"


@check("P02", "Scale invariance")
def p02():
    a = ov.zone(ft.nominal_fp(1440, 23), 1440, 1080, 100.0)
    b = ov.zone(ft.nominal_fp(4096, 23), 4096, 3072, 284.4)
    worst = max(abs(b[k] - a[k]) / a[k] for k in ("s", "d", "z_max"))
    return worst <= 0.01, f"1440 at 100 vs 4096 at 284.4 px/m: S {a['s']:.3f} / {b['s']:.3f} m, worst {100 * worst:.2f}%", \
        "S, d and z_max agree within 1%"


@check("P03", "Projection round trip")
def p03():
    lens = FieldLens((1440, 1080), 957, 955, 722, 538, [-0.05, 0.01, 0, 0, 0], source="synthetic")
    cam = FieldCamera.posed(lens, 1.5, 10.0, heading_deg=3.0, roll_deg=1.0)
    rng = np.random.default_rng(3)
    errs = []
    while len(errs) < 100:
        g = np.array([rng.uniform(-6, 6), rng.uniform(2, 15)])
        uv, z = cam.image_points([[g[0], g[1], 0.0]])
        if z[0] <= 0 or not (0 <= uv[0, 0] < 1440 and 0 <= uv[0, 1] < 1080):
            continue
        back = cam.ground_of_pixel(*uv[0])
        errs.append(math.dist(back, g))
    worst = max(errs)
    return worst <= 0.001, f"100 ground points, worst {1000 * worst:.4f} mm", "every point back within 1 mm"


@check("P04", "Pose from synthetic cones")
def p04():
    cam = syn.level_camera(1.5, 8.0)
    cones = [(-2.5, 4), (2.5, 4), (-3, 8), (3, 8), (0, 5), (-1.5, 10), (1.5, 10), (0, 7)]
    uv, _ = cam.image_points([[x, y, 0.0] for x, y in cones])
    uv += np.random.default_rng(4).normal(0, 0.5, uv.shape)
    p = ps.solve(cones, uv, cam.lens)
    ok = near(p["height_m"], 1.5, 0.02) and near(p["pitch_deg"], 8.0, 0.3)
    return ok, f"height {p['height_m']:.3f} m, pitch {p['pitch_deg']:.2f}°, roll {p['roll_deg']:.2f}°, " \
               f"reprojection up to {p['max_reproj_px']:.2f} px (0.5 px noise)", "height within 2 cm and pitch within 0.3°"


@check("P05", "Synthetic checkerboard calibration")
def p05():
    lens = FieldLens.pinhole((1440, 1080), syn.FP)
    rng = np.random.default_rng(5)
    corners = [find_corners(syn.render_board(lens, r, t), (9, 6)) for r, t in syn.board_poses(15, rng)]
    found = sum(c is not None for c in corners)
    cal = calibrate(corners, (9, 6), 0.025, (1440, 1080), min_views=12)
    err = 100 * abs(cal.fx - syn.FP) / syn.FP
    return err <= 0.5, f"{found}/15 views found, fx {cal.fx:.1f} px ({err:.2f}% off 957), reprojection {cal.rms:.3f} px", \
        "fx within 0.5% of 957 px"


@check("P06", "Level pole density")
def p06():
    px = syn.level_camera().pole_px((0.0, 9.57))
    return near(px, 100.0, 0.1), f"1 m pole at 9.57 m: {px:.3f} px", "100.0 ± 0.1 px (fy / z)"


@check("P07", "Near corners on the image edge")
def p07():
    cam, z = syn.level_camera(), ov.zone(syn.FP, 1440, 1080, 100)
    corners, _ = ov.square(z)
    uv, depth = cam.image_points(np.column_stack([corners, np.zeros(4)]))
    near_u = (uv[3, 0], uv[2, 0])                         # near left, near right
    ok = near(near_u[0], 0, 1) and near(near_u[1], 1440, 1) and np.allclose(depth[:2], z["z_max"], atol=1e-6)
    return ok, f"near corners at u = {near_u[0]:.2f} and {near_u[1]:.2f} px, far edge depth {depth[0]:.3f} m " \
               f"(z_max {z['z_max']:.3f})", "near corners on u = 0 and 1440 within 1 px, far edge at z_max"


@check("P08", "Measurement pass bands")
def p08():
    got = [ms.passes(100.0, 103.0), ms.passes(100.0, 107.0), ms.passes(15.0, 16.0)]
    return got == [True, False, True], "3%, 7%, 1 px on 15 px: " + ", ".join("PASS" if g else "FAIL" for g in got), \
        "PASS, FAIL, PASS"


@check("P09", "16:9 stream flagged")
def p09():
    warn = src.shape_warning(1920, 1080)
    cal = FieldLens((1920, 1080), 1300, 1300, 960, 540, source="checkerboard")
    ok = (warn is not None and "16:9" in warn and src.shape_warning(1440, 1080) is None
          and not src.overlay_allowed((1920, 1080), None) and src.overlay_allowed((1920, 1080), cal))
    return ok, f"1920 × 1080: '{warn[:48]}…'; overlay refused until calibrated at that size", \
        "16:9 warned, 4:3 accepted, overlay waits for a calibration at 1920 × 1080"


@check("P10", "Page binds to loopback")
def p10():
    from tools.fieldtest.__main__ import build_parser, server_config
    cfg = server_config(build_parser().parse_args(["serve"]), app=None)
    shown = src.hide_password("rtsp://user:secret@192.168.1.20:8080/h264_ulaw.sdp")
    ok = cfg.host == "127.0.0.1" and cfg.port == 8090 and shown == "rtsp://user:***@192.168.1.20:8080/h264_ulaw.sdp"
    return ok, f"serve listens on {cfg.host}:{cfg.port}; URL shown as {shown}", \
        "127.0.0.1:8090 without --bind, password hidden"


@check("P11", "D recovered from a synthetic distorted camera")
def p11():
    true = syn.wide_lens()
    views = syn.wide_board_views(true, np.random.default_rng(11))
    cal = calibrate(views, (9, 6), 0.1, true.size, min_views=12)
    _, _, d_true = dz.model(true)
    c = dz.compare(cal)
    g_true = dz.g_calibrated(true, dz.edge_tangent(true))
    g_cal = c["rows"][-1]["g_calibrated"]
    ok = near(c["D"], 0.844, 0.03) and abs(g_cal - g_true) / g_true <= 0.03
    return ok, (f"{len(views)} views of a {c['hfov_deg']:.1f}° lens: D {c['D']:.3f} (lens {d_true:.3f}), "
                f"edge g {g_cal:.3f} vs {g_true:.3f}; twin's 1 − D·u² at the edge {c['rows'][-1]['g_model']:.3f}"), \
        "D within 0.03 of 0.844, calibrated edge g within 3% of the lens"


if __name__ == "__main__":
    main("smoke_fieldtest.py")
