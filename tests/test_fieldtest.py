"""The field-test tool end to end without a phone: a synthetic recording served by the page,
clicked through its API, replayed from the saved session; the sweep, report and layout."""
import json
import os

import pytest
from fakes import fieldtest_synth as syn
from fastapi.testclient import TestClient

from tools import fieldtest as ft
from tools.fieldtest import measure as ms
from tools.fieldtest import overlay as ov
from tools.fieldtest import session as ss
from tools.fieldtest import source as src
from tools.fieldtest import sweep as sw
from tools.fieldtest.__main__ import main

CONES = {"far left": (-2.87, 9.57), "far right": (2.87, 9.57), "near right": (2.87, 3.82), "near left": (-2.87, 3.82)}
POLES = [(2.87, 9.57), (0.0, 6.69), (-2.87, 3.82)]


@pytest.fixture()
def reports(tmp_path, monkeypatch):
    """Reports go to a temporary folder, not reports/fieldtest/."""
    import tools.fieldtest.web as web
    monkeypatch.setattr(ft, "REPORTS", str(tmp_path))
    monkeypatch.setattr(web, "REPORTS", str(tmp_path))
    monkeypatch.setattr(ft, "report_dir", lambda date=None: str(tmp_path))
    monkeypatch.setattr(web, "report_dir", lambda date=None: str(tmp_path))
    import tools.fieldtest.__main__ as cli
    monkeypatch.setattr(cli, "report_dir", lambda date=None: str(tmp_path))
    return tmp_path


@pytest.fixture()
def recording(tmp_path):
    cam = syn.level_camera(1.5, 0.0)
    return str(syn.write_recording(tmp_path / "rec.mp4", cam, cones=CONES.values(), poles=POLES)), cam


def test_live_clicks_replay_to_the_same_log(reports, recording, capsys):
    path, cam = recording
    from tools.fieldtest.web import Live, make_app
    live = Live(path, loop=True)
    try:
        client = TestClient(make_app(live))
        assert client.get("/").status_code == 200
        for name, (x, y) in CONES.items():
            (u, v), = cam.image_points([[x, y, 0.0]])[0]
            assert client.post("/api/cone", json={"u": u, "v": v, "x": x, "y": y, "name": name}).status_code == 200
        for i, (x, y) in enumerate(POLES):
            b, t = cam.image_points([[x, y, 0.0], [x, y, 1.0]])[0]
            r = client.post("/api/measure", json={"bottom": list(b), "top": list(t + [0, -1.5]), "length_m": 1, "label": f"pole {i}"})
            assert r.status_code == 200
        state = client.get("/api/state").json()
        assert state["steps"]["pose"] and state["steps"]["overlay"] and state["steps"]["density"]
        assert abs(state["pose"]["height_m"] - 1.5) < 0.01 and state["size"] == [1440, 1080]
        live_log = state["measurements"]
        report = client.post("/api/report").json()["report"]
    finally:
        live.stop = True
    text = open(report).read()
    assert "| density | PASS |" in text and "delete them" in text
    assert os.path.exists(os.path.join(reports, "overlay.png"))
    # replay: the CLI rebuilds the log from the saved session only
    out = str(reports / "replay.csv")
    assert main(["measure", "--session", str(reports / "session.json"), "--out", out]) == 0
    live_csv = str(reports / "live.csv")
    ms.write_csv(live_log, live_csv)
    assert open(out).read() == open(live_csv).read()


def test_bad_click_is_refused_not_logged(reports, recording):
    path, _ = recording
    from tools.fieldtest.web import Live, make_app
    live = Live(path, loop=True)
    try:
        client = TestClient(make_app(live))
        r = client.post("/api/measure", json={"bottom": [700, 10], "top": [700, 0], "length_m": 1})
        assert r.status_code == 400 and not live.session["measurements"]
    finally:
        live.stop = True


def test_sixteen_nine_recording_warned(tmp_path):
    cam = syn.level_camera()
    path = syn.write_recording(tmp_path / "wide.mp4", cam, seconds=0.5, size=(1920, 1080))
    s = src.Source(str(path))
    s.read()
    assert s.size == (1920, 1080) and "16:9" in s.warnings[0]
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
    session = ss.new((1440, 1080))
    result, _, _ = ss.evaluate(session)
    assert result["steps"]["pose"] is None and result["steps"]["lens"] is None


def test_zone_box_corridor(capsys):
    """The corridor preset fits 1.8 × 2.5 m; the aimed phone puts the centre mid-frame and the far
    corners S/2 · f/p / z_far either side of it; `zone` prints S, d, z_near, z_far and the box."""
    assert main(["zone", "--preset", "corridor"]) == 0
    out = capsys.readouterr().out
    assert "S 1.42 m, d 1.65 m, z_near 0.94 m, z_far 2.36 m" in out and "inside the frame" in out
    lens = ss.lens_of(ss.new((1280, 720), preset="corridor"))
    z = ov.zone(lens.fx, 1280, 720, 360)
    assert z["s"] <= 1.8 and z["z_max"] <= 2.5
    cam = ov.aimed(lens, z, 0.45)
    u, v = cam.image_points([[0.0, z["d"], 0.0]])[0][0]
    assert abs(u - 640) < 0.01 and abs(v - 360) < 0.01
    box = ov.zone_box(cam, z)
    far_l, far_r = box["corners_px"]["far left"], box["corners_px"]["far right"]
    half = z["s"] / 2 * lens.fx / float(cam.R[2] @ ([0.0, z["z_max"], 0.0] - cam.pos))
    assert abs((far_r[0] - far_l[0]) / 2 - half) < 0.2
    assert box["in_frame"] and box["box_px"][0] == min(c[0] for c in box["corners_px"].values())


def test_session_reports_the_box():
    result, _, _ = ss.evaluate(ss.new((1440, 1080)))
    assert result["box"]["in_frame"]
    from tools.fieldtest import report as rp
    assert "Bounding box in the image" in rp.markdown(ss.new((1440, 1080)), result)


def test_local_file_keeps_the_login_out_of_the_repo(tmp_path):
    local = tmp_path / "phone.local.yaml"
    local.write_text("stream_url: rtsp://me:secret@10.0.0.2:1945/\n")
    phone = ft.load_phone(local=str(local))
    assert phone["stream_url"] == "rtsp://me:secret@10.0.0.2:1945/" and phone["presets"]["corridor"]["rho"] == 360
    assert "secret" not in open(ft.PHONE_FILE).read()
