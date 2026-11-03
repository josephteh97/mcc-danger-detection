"""The field-test tool end to end without a phone: a synthetic recording served by the page,
clicked through its API, replayed from the saved session; the sweep, report and layout."""
import json
import os
import time

import cv2
import numpy as np
import pytest
from fakes import fieldtest_synth as syn
from fastapi.testclient import TestClient

import tools.fieldtest.__main__ as cli
from tools import fieldtest as ft
from tools.fieldtest import calib as cb
from tools.fieldtest import lens as ln
from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov
from tools.fieldtest import report as rp
from tools.fieldtest import session as ss
from tools.fieldtest import source as src
from tools.fieldtest import sweep as sw
from tools.fieldtest import web
from tools.fieldtest.__main__ import main

CONES = {"far left": (-2.87, 9.57), "far right": (2.87, 9.57), "near right": (2.87, 3.82), "near left": (-2.87, 3.82)}
POLES = [(2.87, 9.57), (0.0, 6.69), (-2.87, 3.82)]


@pytest.fixture()
def reports(tmp_path, monkeypatch):
    """Reports go to a temporary folder, not reports/fieldtest/."""
    for module in (web, cli):
        monkeypatch.setattr(module, "REPORTS", str(tmp_path))
        monkeypatch.setattr(module, "report_dir", lambda date=None: str(tmp_path))
    return tmp_path


@pytest.fixture()
def recording(tmp_path):
    cam = syn.level_camera(1.5, 0.0)
    return str(syn.write_recording(tmp_path / "rec.mp4", cam, cones=CONES.values(), poles=POLES)), cam


@pytest.fixture()
def open_live(reports, recording):
    """Opens pages on the recording, once a test has saved what they load, and closes them all."""
    opened = []

    def start(*args, **kw):
        opened.append(web.Live(recording[0], *args, loop=True, **kw))
        return opened[-1]
    yield start
    for live in opened:
        live.close()


@pytest.fixture()
def live(open_live):
    return open_live()


def session_cones(cam, points):
    """Cone rows for {name: (x, y)}, clicked exactly where this camera sees them."""
    uv, _ = cam.image_points([[x, y, 0.0] for x, y in points.values()])
    return [{"name": n, "x": float(x), "y": float(y), "u": float(u), "v": float(v)} for (n, (x, y)), (u, v) in zip(points.items(), uv)]


def click_cones(client, cam):
    for cone in session_cones(cam, CONES):
        assert client.post("/api/cone", json=cone).status_code == 200


def lens_of_focal(fx, focal, folder):
    ln.save(ln.FieldLens(syn.STREAM, fx, fx, syn.STREAM[0] / 2, syn.STREAM[1] / 2, rms=0.25, views=20, source="checkerboard"), str(folder), focal)


def test_live_clicks_replay_to_the_same_log(reports, recording, live):
    _, cam = recording
    client = TestClient(web.make_app(live))
    assert client.get("/").status_code == 200
    click_cones(client, cam)
    for i, (x, y) in enumerate(POLES):
        b, t = cam.image_points([[x, y, 0.0], [x, y, 1.0]])[0]
        r = client.post("/api/measure", json={"bottom": list(b), "top": list(t + [0, -1.5]), "length_m": 1, "label": f"pole {i}"})
        assert r.status_code == 200
    state = client.get("/api/state").json()
    assert state["steps"]["pose"] and state["steps"]["overlay"] and state["steps"]["density"]
    assert abs(state["pose"]["height_m"] - 1.5) < 0.01 and state["size"] == [1440, 1080]
    live_log = state["measurements"]
    text = open(client.post("/api/report").json()["report"]).read()
    assert "| density | PASS |" in text and "delete them" in text
    assert os.path.exists(os.path.join(reports, "overlay.png"))
    # replay: the CLI rebuilds the log from the saved session only
    out = str(reports / "replay.csv")
    assert main(["measure", "--session", str(reports / "session.json"), "--out", out]) == 0
    live_csv = str(reports / "live.csv")
    ms.write_csv(live_log, live_csv)
    assert open(out).read() == open(live_csv).read()


def test_bad_click_is_refused_not_logged(reports, recording, live):
    """With a pose, a base above the horizon is a wrong click: refused, in memory and on disk."""
    client = TestClient(web.make_app(live))
    click_cones(client, recording[1])
    r = client.post("/api/measure", json={"bottom": [700, 10], "top": [700, 0], "length_m": 1})
    assert r.status_code == 400 and "base" in r.json()["detail"] and not live.session["measurements"]
    assert not ss.load(str(reports / "session.json"))["measurements"]


@pytest.mark.parametrize("body", [{"length_m": 0}, {"length_m": -1}, {"length_m": "nan"}, {"length_m": ""}, {"top": ["x", 800]}])
def test_bad_numbers_are_refused_not_logged(live, body):
    client = TestClient(web.make_app(live))
    r = client.post("/api/measure", json={"bottom": [700, 900], "top": [700, 800], "length_m": 1, **body})
    assert r.status_code == 400 and r.json()["detail"] and not live.session["measurements"]
    assert client.get("/api/state").status_code == 200


def test_blank_marker_position_is_refused(live):
    client = TestClient(web.make_app(live))
    r = client.post("/api/cone", json={"u": 1, "v": 1, "x": "", "y": ""})
    assert r.status_code == 400 and "x" in r.json()["detail"] and not live.session["cones"]


@pytest.mark.parametrize("marks", [
    [(1.0, 5.0)] * 4,                                                # x, y not retyped
    [(0.0, 3.0), (0.0, 4.0), (0.0, 5.0), (0.0, 6.0)],                # all on one line
    [(2.87, 9.57), (-2.87, 9.57), (-2.87, 3.82), (2.87, 3.82)],      # x signs swapped
])
def test_bad_markers_read_as_fail_and_the_page_keeps_going(reports, recording, live, marks):
    client = TestClient(web.make_app(live))
    cam = recording[1]
    uv, _ = cam.image_points([[x, y, 0.0] for x, y in CONES.values()])
    for (x, y), (u, v) in zip(marks, uv):
        assert client.post("/api/cone", json={"u": float(u), "v": float(v), "x": x, "y": y}).status_code == 200
    state = client.get("/api/state").json()
    assert not state["pose"]["solved"] and state["pose"]["error"]
    assert state["steps"]["pose"] is False and state["steps"]["overlay"] is None and live.jpeg()
    assert "Not solved" in open(client.post("/api/report").json()["report"]).read()
    assert client.post("/api/undo", json={"what": "cone"}).json()["steps"]["pose"] is None


def test_a_wild_pose_still_draws():
    """Corners projected absurdly far off the picture are left out, not passed to OpenCV."""
    lens = ln.FieldLens(syn.STREAM, 960.0, 960.0, 720, 540, (0.17, -0.79, 0.0, 0.01, 1.28), rms=0.2, views=20, source="checkerboard")
    z = ov.zone(lens.fx, *syn.STREAM, 100)
    cam = ln.FieldCamera.posed(lens, 40.0, 89.0)         # looking straight down from 40 m: corners far out in the polynomial
    assert ov.draw(np.zeros((1080, 1440, 3), np.uint8), cam, z).shape == (1080, 1440, 3)
    assert not ov._drawable(np.array([1e7, 0.0])) and not ov._drawable(np.array([np.nan, 0.0])) and ov._drawable(np.array([-50.0, 2000.0]))


def test_base_above_the_horizon_stays_a_row_and_never_stops_the_page(reports, live):
    """A base the assumed or a later camera can't place: kept, with no numbers, as cone undo can cause."""
    client = TestClient(web.make_app(live))
    r = client.post("/api/measure", json={"bottom": [700, 10], "top": [700, 0], "length_m": 1, "label": "high"})
    assert r.status_code == 200
    row = r.json()["measurements"][0]
    assert row["result"] == "not run" and row["predicted_px"] is None and row["measured_px"] == 10
    assert live.jpeg() and client.post("/api/report").status_code == 200
    assert main(["measure", "--session", str(reports / "session.json"), "--out", str(reports / "m.csv")]) == 0


def test_restarting_the_page_keeps_the_clicks(reports, recording, open_live):
    """Same setup: clicks and settings kept. Another preset: a new session, the old file moved aside."""
    live = open_live(rho=90)
    click_cones(TestClient(web.make_app(live)), recording[1])
    live.close()
    live = open_live()
    assert len(live.session["cones"]) == 4 and live.session["rho"] == 90
    assert TestClient(web.make_app(live)).get("/api/state").json()["pose"]["solved"]
    live.close()
    live = open_live(rho=95)
    assert len(live.session["cones"]) == 4 and live.session["rho"] == 95
    live.save()
    live.close()
    live = open_live("office")
    assert not live.session["cones"] and live.session["preset"] == "office"
    live.save()
    kept = [f for f in os.listdir(reports) if f.startswith("session_")]
    assert len(kept) == 1 and len(ss.load(str(reports / kept[0]))["cones"]) == 4


def test_a_damaged_session_file_is_moved_aside(reports, open_live):
    (reports / "session.json").write_text("{not json")
    live = open_live()
    assert not live.session["cones"] and any(f.startswith("session_") for f in os.listdir(reports))


def test_recording_stops_and_starts_again_and_closes_on_exit(reports, live):
    client = TestClient(web.make_app(live))
    first = client.post("/api/record", json={"on": True}).json()["recording"]
    assert first and client.post("/api/record", json={"on": False}).json()["recording"] is None
    second = client.post("/api/record", json={"on": True}).json()["recording"]
    assert second
    time.sleep(0.5)                                      # some frames
    live.close()                                         # as Ctrl+C does, still recording
    cap = cv2.VideoCapture(second)
    assert cap.isOpened() and cap.read()[0]
    cap.release()


def test_corner_density_ignores_the_polynomial_beyond_the_frame():
    """The corridor's near corners: a 1 m pole's top is far outside the frame, where this real
    k1/k2/k3 fit explodes. The density comes from the part of the pole the lens fit covers."""
    lens = ln.FieldLens((1280, 720), 901.3, 900.7, 664.2, 358.8, (0.1728, -0.7876, 0.0014, 0.01, 1.2798),
                        rms=0.25, views=33, source="checkerboard")
    z = ov.zone(lens.fx, 1280, 720, 380)
    cam = ov.aimed(lens, z, 0.45)
    rows = {r["corner"]: r["px_per_m_3d"] for r in ov.corner_table(cam, z)}
    x, y = z["s"] / 2, z["near"]
    local = np.linalg.norm(np.subtract(*cam.image_points([[x, y, 0.0], [x, y, 0.02]])[0])) / 0.02
    assert cam.pole_px((x, y)) > 3000                    # the raw 1 m pole, through the polynomial
    assert abs(rows["near right"] - local) / local < 0.02
    plain = ov.aimed(ln.FieldLens.pinhole((1280, 720), lens.fx), z, 0.45)
    assert all(r["px_per_m_3d"] == plain.pole_px((r["x"], r["y"])) for r in ov.corner_table(plain, z))   # still the 1 m pole


def test_sixteen_nine_recording_warned(tmp_path):
    cam = syn.level_camera()
    path = syn.write_recording(tmp_path / "wide.mp4", cam, seconds=0.5, size=(1920, 1080))
    s = src.Source(str(path))
    s.read()
    assert s.size == (1920, 1080) and "16:9" in s.warnings[0]
    while s.read()[0] is not None:
        pass
    s.reopen()                                     # as the page does after a dropped stream
    assert s.read()[0] is not None
    assert s.size == (1920, 1080) and len(s.warnings) == 1 and "16:9" in s.warnings[0]
    s.close()


class FakeDetector:
    """A person seen at each step's distance until 9 m, then less often (box height from the camera)."""

    def __init__(self, cam, steps):
        self.cam, self.steps, self.n = cam, steps, 0

    def scored(self, frame):
        self.n += 1
        t = (self.n - 1) / 10
        step = next((d for t0, t1, d in self.steps if t0 <= t <= t1), None)
        if step is None or (step > 9 and self.n % 3):
            return []
        b, top = self.cam.image_points([[0.0, step, 0.0], [0.0, step, 1.0]])[0]
        return [((b[0] - 15, top[1], b[0] + 15, b[1]), 0.8)]


def test_sweep_writes_table_and_plot(tmp_path):
    cam = syn.level_camera()
    path = syn.write_recording(tmp_path / "walk.mp4", cam, seconds=6.0)
    steps = [(i * 0.5, i * 0.5 + 0.4, 3.0 + 2 * i) for i in range(12)]       # 3 m to 25 m
    r = sw.run(src.Source(str(path)), FakeDetector(cam, steps), cam, steps)
    sw.write(r, str(tmp_path), cam)
    near = [s for s in r["steps"] if s["distance_m"] <= 9]
    assert all(s["rate"] == 1.0 for s in near) and 9 < r["point_90"]["distance_m"] < 11
    assert all(os.path.exists(tmp_path / f) for f in ("sweep.png", "sweep_steps.csv", "sweep_detections.csv"))


def test_layout_presets(reports, capsys):
    assert main(["layout"]) == 0
    assert "(+2.87, 9.57)" in capsys.readouterr().out
    assert main(["layout", "--preset", "office"]) == 0
    sheet = json.load(open(reports / "layout_office.json"))["numbers"]
    assert sheet == {"z_max": 3.99, "w_max": 6.0, "s": 2.4, "d": 2.79, "near": 1.59}


def test_tilted_overlay_drifts_from_plan_view():
    cam = syn.level_camera(1.5, 10.0)
    rows = ov.corner_table(cam, ov.zone(syn.FP, 1440, 1080, 100))
    drift = {r["corner"]: r["px_per_m_plan"] - r["px_per_m_3d"] for r in rows}  # plan view drifts when tilted
    assert 0.1 < drift["far left"] < 1 and drift["near left"] > 5
    result, _, _ = ss.evaluate(ss.new(syn.STREAM))
    assert result["steps"]["pose"] is None and result["steps"]["lens"] is None


def test_zone_box_corridor(reports, capsys):
    """The corridor preset fits 1.8 × 2.5 m; the aimed phone puts the centre mid-frame and the far
    corners S/2 · f/p / z_far either side of it; `zone` prints S, d, z_near, z_far and the box."""
    assert main(["zone", "--preset", "corridor"]) == 0
    out = capsys.readouterr().out
    assert "S 1.34 m, d 1.57 m, z_near 0.89 m, z_far 2.24 m" in out and "nominal lens" in out and "inside the frame" in out
    lens = ss.lens_of(ss.new((1280, 720), preset="corridor"))
    z = ov.zone(lens.fx, 1280, 720, 380)
    assert z["s"] <= 1.8 and z["z_max"] <= 2.5
    assert ov.zone(901.3, 1280, 720, 380)["z_max"] <= 2.4      # still fits with the phone's calibrated fx
    cam = ov.aimed(lens, z, 0.45)
    u, v = cam.image_points([[0.0, z["d"], 0.0]])[0][0]
    assert abs(u - 640) < 0.01 and abs(v - 360) < 0.01
    box = ov.zone_box(cam, z)
    far_l, far_r = box["corners_px"]["far left"], box["corners_px"]["far right"]
    half = z["s"] / 2 * lens.fx / float(cam.R[2] @ ([0.0, z["z_max"], 0.0] - cam.pos))
    assert abs((far_r[0] - far_l[0]) / 2 - half) < 0.2
    assert box["in_frame"] and box["box_px"][0] == min(c[0] for c in box["corners_px"].values())


def test_session_reports_the_box():
    result, _, _ = ss.evaluate(ss.new(syn.STREAM))
    assert result["box"]["in_frame"]
    assert "Bounding box in the image" in rp.markdown(ss.new(syn.STREAM), result)


def test_local_file_keeps_the_login_out_of_the_repo(tmp_path):
    local = tmp_path / "phone.local.yaml"
    local.write_text("stream_url: rtsp://me:secret@10.0.0.2:1945/\n")
    phone = ft.load_phone(local=str(local))
    assert phone["stream_url"] == "rtsp://me:secret@10.0.0.2:1945/" and phone["presets"]["corridor"]["rho"] == 380
    assert "secret" not in open(ft.PHONE_FILE).read()


def test_saved_calibration_drives_layout_and_views_survive(reports, capsys):
    """layout/zone use the lens calibrated at that size; captured views are kept on disk."""
    ln.save(ln.FieldLens((1280, 720), 901.3, 900.7, 640, 360, rms=0.25, views=20, source="checkerboard"), str(reports), 23)
    assert main(["zone", "--preset", "corridor"]) == 0
    out = capsys.readouterr().out
    assert "calibrated lens: fx 901.3" in out and "z_far 2.37 m" in out
    views = [np.full((54, 1, 2), i, np.float32) for i in range(3)]
    cb.save_views(views, str(reports), (1280, 720), 23)
    assert len(cb.load_views(str(reports), (1280, 720), 23)) == 3


def test_main_camera_fit_keeps_k3_and_tangential_at_zero():
    corners = syn.board_views(ln.FieldLens.pinhole(syn.STREAM, syn.FP))
    lens = cb.calibrate(corners, (9, 6), 0.025, syn.STREAM)
    assert lens.dist[2] == lens.dist[3] == lens.dist[4] == 0.0 and abs(lens.fx - syn.FP) / syn.FP < 0.005


def test_distortion_runs_from_the_command_line(tmp_path, capsys):
    """The full fit from board photos, through main(): it needs no session."""
    lens = ln.FieldLens.pinhole(syn.STREAM, syn.FP)
    for i, (r, t) in enumerate(syn.board_poses(15, np.random.default_rng(5))):
        cv2.imwrite(str(tmp_path / f"{i:02d}.png"), syn.render_board(lens, r, t))
    assert main(["distortion", "--images", str(tmp_path / "*.png")]) == 0
    out = capsys.readouterr().out
    assert "ultra-wide: HFOV" in out and "image edge" in out


def test_nothing_is_judged_without_a_pose():
    """Rows and clicks stay visible, but no PASS or FAIL until the pose is solved."""
    cam = syn.level_camera(1.5, 10.0)
    session = ss.new(syn.STREAM)
    b, t = cam.image_points([[0.0, 6.0, 0.0], [0.0, 6.0, 1.0]])[0]
    session["measurements"] = [{"label": "pole", "length_m": 1, "bottom": list(map(float, b)), "top": list(map(float, t))}]
    session["cones"] = session_cones(cam, {"far left": CONES["far left"], "far right": CONES["far right"]})
    result, _, _ = ss.evaluate(session)
    assert result["steps"]["pose"] is None and result["steps"]["overlay"] is None and result["steps"]["density"] is None
    assert result["measurements"][0]["result"] == "not run" and result["measurements"][0]["predicted_px"] > 0
    assert len(result["overlay"]["rows"]) == 2 and all(r["ok"] is None for r in result["overlay"]["rows"])
    text = rp.markdown(session, result)
    assert "| density | not run |" in text and "| overlay | not run |" in text and "PASS" not in text and "FAIL" not in text


def test_saved_lens_and_views_belong_to_their_focal_length(reports, capsys):
    lens = ln.FieldLens((1280, 720), 901.3, 900.7, 640, 360, rms=0.25, views=20, source="checkerboard")
    ln.save(lens, str(reports), 23)
    assert ln.load(str(reports), (1280, 720), 23).fx == 901.3 and ln.load(str(reports), (1280, 720), 28) is None
    assert main(["layout", "--preset", "corridor", "--focal", "28"]) == 0
    assert "nominal lens" in capsys.readouterr().out
    assert main(["zone", "--preset", "corridor"]) == 0
    assert "calibrated lens: fx 901.3" in capsys.readouterr().out
    views = [np.full((54, 1, 2), 1, np.float32)]
    cb.save_views(views, str(reports), (1280, 720), 23)
    assert len(cb.load_views(str(reports), (1280, 720), 23)) == 1 and cb.load_views(str(reports), (1280, 720), 28) == []


def test_files_from_before_focal_was_recorded_are_the_main_cameras(reports):
    """Calibration and views files saved earlier (no focal length) were made at 23 mm, and only match that."""
    (reports / "calib_1280x720.json").write_text(json.dumps(
        {"size": [1280, 720], "fx": 901.3, "fy": 900.7, "cx": 664.2, "cy": 358.8, "dist": [0.1, 0, 0, 0, 0],
         "rms": 0.25, "views": 33, "source": "checkerboard"}))
    (reports / "views_1280x720.json").write_text(json.dumps([[[1.0, 2.0]] * 54]))
    assert ln.load(str(reports), (1280, 720), 23).views == 33
    assert len(cb.load_views(str(reports), (1280, 720), 23)) == 1
    assert ln.load(str(reports), (1280, 720), 28) is None and cb.load_views(str(reports), (1280, 720), 28) == []
    assert ln.saved_focals(str(reports), (1280, 720)) == [23.0]
    cb.save_views([], str(reports), (1280, 720), 23)        # cleared: the old file no longer counts
    assert cb.load_views(str(reports), (1280, 720), 23) == []


def test_each_focal_length_keeps_its_lens_views_and_clicks(reports, open_live):
    """Going to 28 mm and back loses nothing, and old clicks are never judged by another lens."""
    lens_of_focal(960.0, 23, reports)
    lens_of_focal(1170.0, 28, reports)
    views = [np.full((54, 1, 2), float(i), np.float32) for i in range(3)]
    cb.save_views(views, str(reports), syn.STREAM, 23)
    live = open_live()
    client = TestClient(web.make_app(live))
    click_cones(client, ln.FieldCamera.posed(ss.lens_of(live.session), 1.5))
    before = client.get("/api/state").json()
    assert before["pose"]["solved"] and before["views"] == 3
    state = client.post("/api/settings", json={"focal_equiv_mm": 28}).json()
    assert state["nominal"]["fx"] == 1170.0 and state["views"] == 0 and not state["session"]["cones"]
    assert state["steps"]["pose"] is None and state["steps"]["overlay"] is None
    client.post("/api/calib/clear")                     # at 28 mm: the 23 mm views stay
    state = client.post("/api/settings", json={"focal_equiv_mm": 23}).json()
    assert state["nominal"]["fx"] == 960.0 and state["views"] == 3 and len(state["session"]["cones"]) == 4
    assert state["pose"]["height_m"] == before["pose"]["height_m"] and not state["session"]["parked"].get("23")


def test_a_failed_settings_post_changes_nothing(reports, open_live):
    lens_of_focal(960.0, 23, reports)
    live = open_live()
    client = TestClient(web.make_app(live))
    for body in ({"focal_equiv_mm": "28", "taped_height_m": "1,5"}, {"focal_equiv_mm": 0}, {"rho": -1}, {"rho": "nan"}):
        r = client.post("/api/settings", json=body)
        assert r.status_code == 400 and r.json()["detail"]
        assert live.session["focal_equiv_mm"] == 23 and live.session["rho"] == 100
    state = client.post("/api/settings", json={"focal_equiv_mm": "28", "taped_height_m": "1.5"}).json()
    assert state["steps"]["lens"] is None and state["session"]["taped_height_m"] == 1.5


def test_serve_can_start_at_another_focal(reports, open_live):
    lens_of_focal(1170.0, 28, reports)
    live = open_live(focal=28)
    assert live.session["lens"]["fx"] == 1170.0 and ss.lens_of(live.session).focal_equiv_mm == 28
    assert ln.saved_focals(str(reports), syn.STREAM) == [28.0]


def test_a_bad_fit_does_not_replace_the_saved_lens(reports, recording):
    """Too rough, or fx of another focal length: refused on the page and the command line."""
    lens_of_focal(960.0, 23, reports)
    fit = ln.FieldLens(syn.STREAM, syn.FP, syn.FP, 720, 540, rms=0.2, views=15, source="checkerboard")
    cb.check_fit(fit, 23, 0.5)
    fit.rms = 0.9
    with pytest.raises(ValueError, match="not saved"):
        cb.check_fit(fit, 23, 0.5)
    fit.rms = 0.2
    with pytest.raises(ValueError, match="from the nominal"):
        cb.check_fit(fit, 35, 0.5)
    lens = ln.FieldLens.pinhole(syn.STREAM, ft.nominal_fp(syn.STREAM[0], 28))         # filmed at 28 mm
    folder = reports / "board"
    folder.mkdir()
    for i, (r, t) in enumerate(syn.board_poses(14, np.random.default_rng(3))):
        cv2.imwrite(str(folder / f"{i:02d}.png"), syn.render_board(lens, r, t))
    pattern = str(folder / "*.png")
    assert main(["calibrate", "--images", pattern]) == 1                               # taken for 23 mm: refused
    assert ln.load(str(reports), syn.STREAM, 23).fx == 960.0
    assert main(["calibrate", "--images", pattern, "--focal", "28"]) == 0
    assert ln.load(str(reports), syn.STREAM, 23).fx == 960.0
    assert abs(ln.load(str(reports), syn.STREAM, 28).fx - lens.fx) / lens.fx < 0.01


def test_repeated_pictures_are_not_new_views(live, monkeypatch):
    """A frozen stream, or the board not moved between captures."""
    view = np.full((54, 1, 2), 100.0, np.float32) + np.arange(54, dtype=np.float32).reshape(-1, 1, 1)
    assert cb.is_repeat(view + 0.2, [view]) and not cb.is_repeat(view + 5, [view]) and not cb.is_repeat(view, [])
    client = TestClient(web.make_app(live))
    monkeypatch.setattr(cb, "find_corners", lambda *a: view)
    assert client.post("/api/calib/capture").json()["views"] == 1
    r = client.post("/api/calib/capture")
    assert r.status_code == 400 and "earlier view" in r.json()["detail"] and len(live.views) == 1


def test_stream_size_change_stops_calibration(live):
    client = TestClient(web.make_app(live))
    live.session["size"] = [640, 480]                   # the session's size; the stream has moved on
    for url in ("/api/calib/capture", "/api/calib/solve"):
        r = client.post(url)
        assert r.status_code == 400 and "restart" in r.json()["detail"]


def test_no_overlay_verdict_on_an_uncalibrated_cropped_frame(reports):
    """16:9 with the nominal lens: no overlay PASS or FAIL, no drawing in the picture or by command."""
    session = ss.new((1280, 720), preset="corridor")
    cam = ov.aimed(ss.lens_of(session), ss.zone_of(session, ss.lens_of(session)), 0.45)
    z = ss.zone_of(session, cam.lens)
    corners, _ = ov.camera_square(cam, z)
    session["cones"] = session_cones(cam, dict(zip(ov.CORNERS, corners)))
    result, solved, _ = ss.evaluate(session)
    assert result["pose"]["solved"] and not result["overlay_allowed"] and result["steps"]["overlay"] is None
    frame = np.zeros((720, 1280, 3), np.uint8)
    rp.write(session, result, solved, z, str(reports), frame)
    assert not cv2.imread(str(reports / "overlay.png")).any()
    path = ss.save(session, str(reports / "s.json"))
    video = syn.write_recording(reports / "wide.mp4", syn.level_camera(), seconds=0.2, size=(1280, 720))
    assert main(["overlay", "--session", path, "--file", str(video)]) == 1


def test_record_makes_its_folder_and_reports_failure(reports, recording, tmp_path, capsys):
    out = tmp_path / "new" / "folder" / "r.mp4"
    assert main(["record", "--url", recording[0], "--seconds", "0.2", "--out", str(out)]) == 0
    assert out.stat().st_size > 100
    assert main(["record", "--url", recording[0], "--seconds", "0.2", "--out", str(tmp_path / "bad.nope")]) == 1
    assert "cannot record" in capsys.readouterr().err


def test_bad_command_line_numbers_are_refused(capsys):
    for args in (["layout", "--rho", "0"], ["zone", "--focal", "-1"], ["serve", "--rho", "nan"]):
        with pytest.raises(SystemExit):
            main(args)
    assert "above 0" in capsys.readouterr().err


def test_calibrating_from_no_images_says_so(tmp_path, capsys):
    assert main(["calibrate", "--images", str(tmp_path / "none*.png")]) == 1
    assert "no images" in capsys.readouterr().err


STEP = {"distance_m": 5.0, "frames": 10, "detected": 10, "rate": 1.0, "box_h_px": 300.0, "confidence": 0.8, "predicted_h_px": None}


@pytest.mark.parametrize("rows, expected", [
    ([], None),                                                          # no step at all
    ([{**STEP, "frames": 0, "detected": 0, "rate": float("nan"), "box_h_px": float("nan")}], None),   # steps outside the recording
    ([STEP, {**STEP, "distance_m": 10.0, "box_h_px": 95.0}], True),      # holds down to 95 px
    ([STEP, {**STEP, "distance_m": 10.0, "box_h_px": 225.0}], False),    # perfect, but stopped at 225 px
    ([STEP, {**STEP, "distance_m": 10.0, "detected": 0, "rate": 0.0, "box_h_px": float("nan")}], False),   # lost at 300 px
    ([{**STEP, "detected": 0, "rate": 0.0, "box_h_px": float("nan")}], False),                             # never seen
])
def test_detection_needs_90_percent_down_to_100_px(rows, expected):
    sweep = sw.summary(rows)
    json.dumps(sweep, allow_nan=False)                                   # goes to session.json and the page
    assert sw.detection_ok(sweep) is expected


def test_sweep_uses_the_apps_detector_settings_and_needs_a_pose(reports, tmp_path, capsys, monkeypatch):
    """Same confidence as the app's yolo mode. Without a pose the sweep runs but isn't judged."""
    import app.detect
    made = {}

    class Yolo:
        def __init__(self, model, conf, tiles=False):
            made.update(model=model, conf=conf, tiles=tiles)

        def scored(self, frame):
            return []

    monkeypatch.setattr(app.detect, "YoloDetector", Yolo)
    cam = syn.level_camera()
    video = syn.write_recording(tmp_path / "walk.mp4", cam, seconds=0.5)
    (tmp_path / "steps.csv").write_text("t0,t1,distance_m\n0,0.4,5\n")
    path = ss.save(ss.new(syn.STREAM), str(tmp_path / "s.json"))
    assert main(["sweep", "--file", str(video), "--model", "m.onnx", "--steps", str(tmp_path / "steps.csv"), "--session", path]) == 0
    assert made["conf"] == 0.4
    assert "won't be judged" in capsys.readouterr().out
    session = ss.load(path)
    assert session["sweep"]["frames"] > 0 and ss.evaluate(session)[0]["steps"]["detection"] is None
    text = rp.markdown(session, ss.evaluate(session)[0])
    assert "Not judged" in text and "| detection | not run |" in text
    session["cones"] = session_cones(cam, CONES)
    assert ss.evaluate(session)[0]["steps"]["detection"] is False        # with a pose: never seen, so it fails


def test_changing_focal_on_the_page_changes_the_lens(reports, open_live):
    lens_of_focal(960.0, 23, reports)
    live = open_live()
    client = TestClient(web.make_app(live))
    assert client.get("/api/state").json()["steps"]["lens"] is True
    state = client.post("/api/settings", json={"focal_equiv_mm": 28}).json()
    assert state["steps"]["lens"] is None and live.session["lens"] is None
    state = client.post("/api/settings", json={"focal_equiv_mm": 23}).json()
    assert state["steps"]["lens"] is True
