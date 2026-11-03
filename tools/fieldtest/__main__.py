"""Field-test command line: every step on the live phone stream or on a recording.

    python3 -m tools.fieldtest probe [--url URL]
    python3 -m tools.fieldtest serve [--url URL | --file REC] [--bind 127.0.0.1] [--port 8090]
    python3 -m tools.fieldtest record --seconds 60 [--url URL]
    python3 -m tools.fieldtest calibrate (--file REC | --images 'board/*.jpg') [--every 10]
    python3 -m tools.fieldtest layout [--preset office] [--rho 100] [--size 1440x1080]
    python3 -m tools.fieldtest zone [--session S.json | --preset corridor [--height 0.45]]
    python3 -m tools.fieldtest pose --session S.json
    python3 -m tools.fieldtest overlay --session S.json --file REC [--frame 0] [--out overlay.png]
    python3 -m tools.fieldtest measure --session S.json [--out measurements.csv]
    python3 -m tools.fieldtest sweep --file REC --model person.onnx --steps steps.csv --session S.json [--tiles]
    python3 -m tools.fieldtest report --session S.json [--file REC]
    python3 -m tools.fieldtest distortion --images 'ultrawide/*.jpg' [--pole-centre u1,v1,u2,v2 --pole-edge ...]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import sys
import time

import cv2

from tools.fieldtest import REPORTS, describe_pitch, load_phone, report_dir
from tools.fieldtest import calib as cb
from tools.fieldtest import distortion as dz
from tools.fieldtest import lens as ln
from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov
from tools.fieldtest import report as rp
from tools.fieldtest import session as ss
from tools.fieldtest import source as src
from tools.fieldtest import sweep as sw


def _size(text):
    w, h = text.lower().split("x")
    return int(w), int(h)


def _frame_at(path, index=0):
    s = src.Source(path)
    try:
        for i, (_, frame) in enumerate(s):
            if i >= index:
                return frame
    finally:
        s.close()
    raise ValueError(f"{path} has fewer than {index + 1} frames")


def _preset_session(a, phone):
    """A session for `layout` and `zone` before the test: the preset, its overrides and the saved lens."""
    size = a.size or phone["presets"][a.preset]["frame_px"]
    session = ss.new(size, preset=a.preset, phone=phone, rho=a.rho, focal_equiv_mm=a.focal, height_m=getattr(a, "height", None))
    return ss.load_saved_lens(session, REPORTS)


def _which_lens(lens):
    if lens.calibrated:
        return f"calibrated lens: fx {lens.fx:.1f} px ({os.path.basename(ln.calib_path(REPORTS, lens.size))})"
    return "nominal lens (not calibrated at this size and focal length)"


def _images(pattern):
    return (cv2.imread(p) for p in sorted(glob.glob(pattern)))


def build_parser():
    ap = argparse.ArgumentParser(prog="python3 -m tools.fieldtest", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="frame size, fps and shape warnings of the stream")
    p.add_argument("--url")
    p.add_argument("--seconds", type=float, default=3.0)
    p = sub.add_parser("serve", help="the field-test page")
    p.add_argument("--url")
    p.add_argument("--file", help="a recording instead of the live stream (loops)")
    p.add_argument("--bind", default="127.0.0.1", help="address to listen on (default 127.0.0.1: this PC only)")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--preset", default="default")
    p.add_argument("--rho", type=float)
    p = sub.add_parser("record", help="record the stream to reports/fieldtest/<date>/")
    p.add_argument("--url")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--out")
    p = sub.add_parser("calibrate", help="checkerboard calibration at one image size")
    p.add_argument("--file")
    p.add_argument("--images")
    p.add_argument("--every", type=int, default=10, help="use every n-th frame of a recording")
    p.add_argument("--focal", type=float, help="equivalent focal length for the nominal comparison")
    layout = sub.add_parser("layout", help="the cone layout sheet")
    zone = sub.add_parser("zone", help="S, d, z_near, z_far and the square's bounding box in the image")
    for p in (layout, zone):
        p.add_argument("--preset", default="default")
        p.add_argument("--rho", type=float)
        p.add_argument("--size", type=_size)
        p.add_argument("--focal", type=float)
    zone.add_argument("--session", help="use the session's calibrated lens and solved pose")
    zone.add_argument("--height", type=float, help="phone height, m (default: the preset's)")

    pose = sub.add_parser("pose", help="solve the pose from the session's cones")
    overlay = sub.add_parser("overlay", help="draw the overlay on a frame of a recording")
    measure = sub.add_parser("measure", help="the measurement log from the session's clicks")
    sweep = sub.add_parser("sweep", help="detection sweep on a recording")
    report = sub.add_parser("report", help="write the report")
    for p in (pose, overlay, measure, sweep, report):
        p.add_argument("--session", required=True)
    for p in (overlay, measure, sweep, report):
        p.add_argument("--out")
    for p in (overlay, report):
        p.add_argument("--frame", type=int, default=0)
    overlay.add_argument("--file", required=True)
    report.add_argument("--file")
    sweep.add_argument("--file", required=True)
    sweep.add_argument("--model", required=True, help="person-detector ONNX, as the app's yolo mode")
    sweep.add_argument("--steps", required=True, help="CSV: t0,t1,distance_m (when the person was at each mark)")
    sweep.add_argument("--tiles", action="store_true")
    sweep.add_argument("--height", type=float, default=1.0, help="person height for the prediction, m")

    p = sub.add_parser("distortion", help="ultra-wide distortion test from photos")
    p.add_argument("--images", required=True)
    p.add_argument("--pole-centre", help="u1,v1,u2,v2: the 1 m pole at the centre")
    p.add_argument("--pole-edge", help="u1,v1,u2,v2: the same pole near the edge, same depth")
    return ap


def server_config(args, app):
    import uvicorn
    # the page's picture is an endless response: don't let it hold up Ctrl+C
    return uvicorn.Config(app, host=args.bind, port=args.port, log_level="warning", timeout_graceful_shutdown=1)


def main(argv=None):
    a = build_parser().parse_args(argv)
    phone = load_phone()
    url = getattr(a, "url", None) or phone["stream_url"]

    if a.cmd == "probe":
        r = src.probe(url, a.seconds)
        print(f"{r['url']}: {r['size'][0]} × {r['size'][1]} at {r['fps']} fps ({r['frames']} frames)")
        print(describe_pitch(phone, r["size"][0]))
        for w in r["warnings"]:
            print("WARNING:", w)
        return 0

    if a.cmd == "serve":
        import uvicorn

        from tools.fieldtest.web import Live, make_app
        live = Live(a.file or url, a.preset, a.rho, loop=bool(a.file))
        for w in live.src.warnings:
            print("WARNING:", w)
        print(f"{live.src.shown}: {live.src.size[0]} × {live.src.size[1]}; page on http://{a.bind}:{a.port}/")
        if live.session["cones"] or live.session["measurements"]:
            print(f"continuing today's session: {len(live.session['cones'])} markers and "
                  f"{len(live.session['measurements'])} measurements kept; if the phone moved, undo the markers")
        try:
            uvicorn.Server(server_config(a, make_app(live))).run()
        finally:
            live.close()
        return 0

    if a.cmd == "record":
        s = src.Source(url)
        frame, _ = s.read()
        out = a.out or os.path.join(report_dir(), time.strftime(src.REC_NAME))
        w = s.writer(out)
        t0 = time.monotonic()
        while frame is not None and time.monotonic() - t0 < a.seconds:
            w.write(frame)
            frame, _ = s.read()
        w.release()
        s.close()
        print(f"recorded {s.frames} frames of {s.shown} to {out}")
        return 0

    if a.cmd == "calibrate":
        if a.images:
            images = _images(a.images)
        else:
            images = (f for i, (_, f) in enumerate(src.Source(a.file)) if i % a.every == 0)
        focal = a.focal or phone["main"]["focal_equiv_mm"]
        lens = cb.calibrate_images(images, *cb.board_settings(phone))
        path = ln.save(lens, REPORTS, focal)
        n = cb.against_nominal(lens, focal)
        print(f"{lens.views} views at {lens.size[0]} × {lens.size[1]}: reprojection {lens.rms:.3f} px "
              f"({'PASS' if lens.rms <= phone['pass']['lens_rms_px'] else 'FAIL'}, at most {phone['pass']['lens_rms_px']} px)")
        print(f"fx {n['fx']:.1f} px, fy {n['fy']:.1f} px against nominal f/p {n['nominal_fp']:.1f} px ({n['diff_pct']:+.2f}%)")
        print(describe_pitch(phone, lens.size[0], a.focal))
        print(f"saved {path}")
        return 0

    if a.cmd == "distortion":
        lens = cb.calibrate_images(_images(a.images), *cb.board_settings(phone), model="wide")
        c = dz.compare(lens)
        print(f"{lens.views} views, reprojection {lens.rms:.3f} px")
        print(dz.describe(c))
        if a.pole_centre and a.pole_edge:
            pc, pe = ([float(v) for v in s.split(",")] for s in (a.pole_centre, a.pole_edge))
            edge_u = abs(lens.undistort([[pe[0], (pe[1] + pe[3]) / 2]])[0, 0] - lens.cx) / lens.fx
            r = dz.pole_ratio(math.dist(pc[:2], pc[2:]), math.dist(pe[:2], pe[2:]), edge_u, c["D"])
            print(f"pole edge/centre: measured {r['measured']:.3f}, twin model 1 − D·u² {r['model']:.3f} (u = {edge_u:.3f})")
        return 0

    path = getattr(a, "session", None)
    session = ss.load(path) if path else _preset_session(a, phone)
    result, cam, z = ss.evaluate(session)

    if a.cmd == "layout":
        print(describe_pitch(phone, session["size"][0], session["focal_equiv_mm"]))
        print("using the", _which_lens(cam.lens))
        print(ov.describe_layout(result["layout"]))
        out = os.path.join(report_dir(), f"layout_{a.preset}.json")
        with open(out, "w") as f:
            json.dump(result["layout"], f, indent=1)
        print(f"saved {out}")
        return 0

    if a.cmd == "zone":
        if not path:                             # before the test: the phone aimed at the centre
            print("using the", _which_lens(cam.lens))
        print(ov.describe_zone(z, result["box"], cam))
        return 0

    if a.cmd == "pose":
        print(json.dumps(result["pose"], indent=1))
        return 0 if result["steps"]["pose"] is not False else 1

    if a.cmd == "overlay":
        out = a.out or os.path.join(report_dir(), "overlay.png")
        cv2.imwrite(out, rp.annotate(_frame_at(a.file, a.frame), session, cam, z))
        for c in result["corners"]:
            print(f"{c['corner']:10s} ({c['x']:+.2f}, {c['y']:.2f}) m: {ms.num(c['px_per_m_3d'], '.1f')} px/m 3D, {c['px_per_m_plan']:.1f} plan view")
        print(f"saved {out}")
        return 0

    if a.cmd == "measure":
        out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.session)), "measurements.csv")
        ms.write_csv(result["measurements"], out)
        for m in result["measurements"]:
            print(f"{m['label'] or '-':12s} {ms.num(m['distance_m'], '6.2f')} m  predicted {ms.num(m['predicted_px'], '7.1f')} px  "
                  f"measured {m['measured_px']:7.1f} px  {ms.num(m['error_pct'], '+6.1f')}%  {m['result']}")
        print(f"saved {out}")
        return 0 if result["steps"]["density"] is not False else 1

    if a.cmd == "sweep":
        from app.detect import YoloDetector
        with open(a.steps) as f:
            steps = [(float(r["t0"]), float(r["t1"]), float(r["distance_m"])) for r in csv.DictReader(f)]
        r = sw.run(src.Source(a.file), YoloDetector(a.model, conf=0.25, tiles=a.tiles), cam, steps)
        folder = sw.write(r, a.out or os.path.dirname(os.path.abspath(a.session)), cam, a.height)
        session["sweep"] = {"point_90": r["point_90"]}
        ss.save(session, a.session)
        for s in r["steps"]:
            print(f"{s['distance_m']:5.1f} m: {s['detected']}/{s['frames']} frames ({100 * s['rate']:.0f}%), box {s['box_h_px']:.0f} px")
        print("90% point:", r["point_90"], f"- written to {folder}")
        return 0

    if a.cmd == "report":
        frame = _frame_at(a.file, a.frame) if a.file else None
        folder = a.out or os.path.dirname(os.path.abspath(a.session))
        report_path = rp.write(session, result, cam, z, folder, frame)
        print("\n".join(f"{k}: {rp.verdict(v)}" for k, v in result["steps"].items()))
        print(f"saved {report_path}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
