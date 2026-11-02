"""Field-test command line: every step on the live phone stream or on a recording.

    python3 -m tools.fieldtest probe [--url URL]
    python3 -m tools.fieldtest serve [--url URL | --file REC] [--bind 127.0.0.1] [--port 8090]
    python3 -m tools.fieldtest record --seconds 60 [--url URL]
    python3 -m tools.fieldtest calibrate (--file REC | --images 'board/*.jpg') [--every 10]
    python3 -m tools.fieldtest layout [--preset office] [--rho 100] [--size 1440x1080]
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

from tools.fieldtest import REPORTS, describe_pitch, load_phone, nominal_fp, report_dir

DEFAULT_BIND, DEFAULT_PORT = "127.0.0.1", 8090


def _size(text):
    w, h = text.lower().split("x")
    return int(w), int(h)


def _frame_at(path, index=0):
    from tools.fieldtest.source import Source
    s = Source(path)
    try:
        for i, (_, frame) in enumerate(s):
            if i >= index:
                return frame
    finally:
        s.close()
    raise ValueError(f"{path} has fewer than {index + 1} frames")


def build_parser():
    ap = argparse.ArgumentParser(prog="python3 -m tools.fieldtest", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, help_):
        p = sub.add_parser(name, help=help_)
        return p

    p = cmd("probe", "frame size, fps and shape warnings of the stream")
    p.add_argument("--url")
    p.add_argument("--seconds", type=float, default=3.0)
    p = cmd("serve", "the field-test page")
    p.add_argument("--url")
    p.add_argument("--file", help="a recording instead of the live stream (loops)")
    p.add_argument("--bind", default=DEFAULT_BIND, help="address to listen on (default 127.0.0.1: this PC only)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--preset", default="default")
    p.add_argument("--rho", type=float)
    p = cmd("record", "record the stream to reports/fieldtest/<date>/")
    p.add_argument("--url")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--out")
    p = cmd("calibrate", "checkerboard calibration at one image size")
    p.add_argument("--file")
    p.add_argument("--images")
    p.add_argument("--every", type=int, default=10, help="use every n-th frame of a recording")
    p.add_argument("--focal", type=float, help="equivalent focal length for the nominal comparison")
    p = cmd("layout", "the cone layout sheet")
    p.add_argument("--preset", default="default")
    p.add_argument("--rho", type=float)
    p.add_argument("--size", type=_size)
    p.add_argument("--focal", type=float)
    for name, help_ in (("pose", "solve the pose from the session's cones"),
                        ("overlay", "draw the overlay on a frame of a recording"),
                        ("measure", "the measurement log from the session's clicks"),
                        ("sweep", "detection sweep on a recording"),
                        ("report", "write the report")):
        p = cmd(name, help_)
        p.add_argument("--session", required=True)
        if name in ("overlay", "sweep", "report"):
            p.add_argument("--file", required=name != "report")
            p.add_argument("--frame", type=int, default=0)
        p.add_argument("--out")
        if name == "sweep":
            p.add_argument("--model", required=True, help="person-detector ONNX, as the app's yolo mode")
            p.add_argument("--steps", required=True, help="CSV: t0,t1,distance_m (when the person was at each mark)")
            p.add_argument("--tiles", action="store_true")
            p.add_argument("--height", type=float, default=1.0, help="person height for the prediction, m")
    p = cmd("distortion", "ultra-wide distortion test from photos")
    p.add_argument("--images", required=True)
    p.add_argument("--pole-centre", help="u1,v1,u2,v2: the 1 m pole at the centre")
    p.add_argument("--pole-edge", help="u1,v1,u2,v2: the same pole near the edge, same depth")
    return ap


def server_config(args, app):
    import uvicorn
    return uvicorn.Config(app, host=args.bind, port=args.port, log_level="warning")


def main(argv=None):
    a = build_parser().parse_args(argv)
    phone = load_phone()
    from tools.fieldtest import source as src
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
        uvicorn.Server(server_config(a, make_app(live))).run()
        return 0

    if a.cmd == "record":
        s = src.Source(url)
        frame, _ = s.read()
        out = a.out or os.path.join(report_dir(), time.strftime("rec_%H%M%S.mp4"))
        w = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), s.file_fps if 0 < s.file_fps < 61 else 15.0, s.size)
        t0 = time.monotonic()
        while frame is not None and time.monotonic() - t0 < a.seconds:
            w.write(frame)
            frame, _ = s.read()
        w.release()
        s.close()
        print(f"recorded {s.frames} frames of {s.shown} to {out}")
        return 0

    if a.cmd == "calibrate":
        from tools.fieldtest import calib as cb
        from tools.fieldtest import lens as ln
        b = phone["checkerboard"]
        if a.images:
            images = [cv2.imread(p) for p in sorted(glob.glob(a.images))]
        else:
            images = [f for i, (_, f) in enumerate(src.Source(a.file)) if i % a.every == 0]
        lens = cb.calibrate_images(images, b["inner_corners"], b["square_mm"] / 1000, b["min_views"])
        path = ln.save(lens, REPORTS)
        n = cb.against_nominal(lens, a.focal or phone["main"]["focal_equiv_mm"])
        print(f"{lens.views} views at {lens.size[0]} × {lens.size[1]}: reprojection {lens.rms:.3f} px "
              f"({'PASS' if lens.rms <= phone['pass']['lens_rms_px'] else 'FAIL'}, at most {phone['pass']['lens_rms_px']} px)")
        print(f"fx {n['fx']:.1f} px, fy {n['fy']:.1f} px against nominal f/p {n['nominal_fp']:.1f} px ({n['diff_pct']:+.2f}%)")
        print(describe_pitch(phone, lens.size[0], a.focal))
        print(f"saved {path}")
        return 0

    if a.cmd == "layout":
        from tools.fieldtest import overlay as ov
        p = dict(phone["presets"][a.preset])
        size = a.size or tuple(p["frame_px"])
        fp = nominal_fp(size[0], a.focal or p["focal_equiv_mm"])
        print(describe_pitch(phone, size[0], a.focal or p["focal_equiv_mm"]))
        sheet = ov.layout(ov.zone(fp, size[0], size[1], a.rho or p["rho"]))
        print(ov.describe_layout(sheet))
        out = os.path.join(report_dir(), f"layout_{a.preset}.json")
        with open(out, "w") as f:
            json.dump(sheet, f, indent=1)
        print(f"saved {out}")
        return 0

    from tools.fieldtest import session as ss
    session = ss.load(a.session)
    result, cam, z = ss.evaluate(session)

    if a.cmd == "pose":
        print(json.dumps(result["pose"], indent=1))
        return 0 if result["steps"]["pose"] is not False else 1

    if a.cmd == "overlay":
        from tools.fieldtest import report as rp
        out = a.out or os.path.join(report_dir(), "overlay.png")
        cv2.imwrite(out, rp.annotate(_frame_at(a.file, a.frame), session, cam, z))
        for c in result["corners"]:
            print(f"{c['corner']:10s} ({c['x']:+.2f}, {c['y']:.2f}) m: {c['px_per_m_3d']:.1f} px/m 3D, {c['px_per_m_plan']:.1f} plan view")
        print(f"saved {out}")
        return 0

    if a.cmd == "measure":
        from tools.fieldtest import measure as ms
        out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.session)), "measurements.csv")
        ms.write_csv(result["measurements"], out)
        for m in result["measurements"]:
            print(f"{m['label'] or '-':12s} {m['distance_m']:6.2f} m  predicted {m['predicted_px']:7.1f} px  "
                  f"measured {m['measured_px']:7.1f} px  {m['error_pct']:+6.1f}%  {m['result']}")
        print(f"saved {out}")
        return 0 if result["steps"]["density"] is not False else 1

    if a.cmd == "sweep":
        from tools.fieldtest import sweep as sw
        with open(a.steps) as f:
            steps = [(float(r["t0"]), float(r["t1"]), float(r["distance_m"])) for r in csv.DictReader(f)]
        r = sw.run(src.Source(a.file), sw.detector(a.model, a.tiles), cam, steps)
        folder = sw.write(r, a.out or os.path.dirname(os.path.abspath(a.session)), cam, a.height)
        session["sweep"] = {"point_90": r["point_90"]}
        ss.save(session, a.session)
        for s in r["steps"]:
            print(f"{s['distance_m']:5.1f} m: {s['detected']}/{s['frames']} frames ({100 * s['rate']:.0f}%), box {s['box_h_px']:.0f} px")
        print("90% point:", r["point_90"], f"- written to {folder}")
        return 0

    if a.cmd == "report":
        from tools.fieldtest import report as rp
        frame = _frame_at(a.file, a.frame) if a.file else None
        folder = a.out or os.path.dirname(os.path.abspath(a.session))
        path = rp.write(session, result, cam, z, folder, frame)
        print("\n".join(f"{k}: {'not run' if v is None else 'PASS' if v else 'FAIL'}" for k, v in result["steps"].items()))
        print(f"saved {path}")
        return 0

    if a.cmd == "distortion":
        from tools.fieldtest import calib as cb
        from tools.fieldtest import distortion as dz
        b = phone["checkerboard"]
        lens = cb.calibrate_images([cv2.imread(p) for p in sorted(glob.glob(a.images))], b["inner_corners"],
                                   b["square_mm"] / 1000, b["min_views"])
        c = dz.compare(lens)
        print(f"{lens.views} views, reprojection {lens.rms:.3f} px")
        print(dz.describe(c))
        if a.pole_centre and a.pole_edge:
            pc, pe = ([float(v) for v in s.split(",")] for s in (a.pole_centre, a.pole_edge))
            edge_u = abs(lens.undistort([[pe[0], (pe[1] + pe[3]) / 2]])[0, 0] - lens.cx) / lens.fx
            r = dz.pole_ratio(math.dist(pc[:2], pc[2:]), math.dist(pe[:2], pe[2:]), edge_u, c["D"])
            print(f"pole edge/centre: measured {r['measured']:.3f}, twin model 1 − D·u² {r['model']:.3f} (u = {edge_u:.3f})")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
