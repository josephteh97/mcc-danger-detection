"""The v11 world without Docker: frame size, the lens, postures, the squat key and the squatting
scenario through the app's detector, tracker and alarm logic."""
import math

import numpy as np
import pytest

import catalog
from app.alarm import AlarmFSM, Config, edge_distance, foot_pixel, ground_from_image, undistort_pixel
from app.detect import OracleDetector
from app.track import IoUTracker
from tools.trial import TrialSession
from world.world import World

SITE = catalog.load_site(profile="v11")


@pytest.fixture(scope="module")
def world():
    return World(SITE)


def test_frame_is_1600x1200(world):
    frame, _ = world.render()
    assert frame.shape == (1200, 1600, 3)


@pytest.mark.parametrize("xy", [(0.3, -1.5), (2.7, 2.3), (-4.0, 3.5), (4.2, -3.8), (0.0, 3.8)])
def test_feet_located_through_the_lens(world, xy):
    """The app's foot point (lens undone, then the calibration homography) lands on the worker,
    across the warning ring including its far corners. The box bottom is the near edge of the
    body's footprint, so the estimate sits up to a body radius (0.28 m) toward the camera, as in
    phase 1; the lens adds little to that."""
    w = world.scene.add_controlled(xy)
    try:
        _, info = world.render()
        lens = world.lens.params
        gx, gy = ground_from_image(world.homography(), *undistort_pixel(*foot_pixel(info["boxes"][w.id]), lens))
        assert math.dist((gx, gy), xy) < 0.45, (gx, gy)
    finally:
        world.scene.workers.remove(w)


def test_squat_key():
    """C inside the 3 m ring: the posture becomes squat, the box is about 1.0 m tall, the worker
    does not move while down, and the alarm still fires after the dwell."""
    s = TrialSession(delay_ms=0, profile="v11")
    wid = s.add_worker((0.0, -1.8))                 # 1.0 m from the pit edge, inside the zone
    s.hold(set(), 0.5)
    stand = s.truth["workers"][0]
    s.posture("squat")
    s.hold({"left"}, 1.0)                            # held keys do nothing while squatting
    w = s.worker(wid)
    squat = next(t for t in s.truth["workers"] if t["id"] == wid)
    assert w.posture == "squat" and (w.x, w.y) == (0.0, -1.8)
    ratio = (squat["box"][3] - squat["box"][1]) / (stand["box"][3] - stand["box"][1])
    assert abs(ratio * 1.78 - 1.0) < 0.15, f"squatting box {ratio * 1.78:.2f} m tall"
    s.hold(set(), 5.0)
    kinds = [k for _, k, _ in s.events]
    assert "alarm" in kinds, kinds
    s.posture("squat")                              # C again: stands up and can walk
    s.hold({"left"}, 0.5)
    assert s.worker(wid).posture == "walk" and s.worker(wid).x != 0.0


def test_squat_far_edge_scenario_fires_alarm():
    """The squatting worker at the far side, through the pixel-height miss model, still raises the alarm."""
    world = World(SITE, scenario="squat_far_edge")
    det = OracleDetector(None, delay_ms=120, jitter_ms=20, seed=3, miss_model="pixel_height",
                         native_px=[4000, 3000], tiles=True)
    fsm, tracker, H, lens = AlarmFSM(Config()), IoUTracker(max_age_s=2.0), world.homography(), world.lens.params
    pit, kinds, heights, t = [tuple(p) for p in SITE["site"]["pit"]], [], [], 0.0
    for _ in range(int(30 * 15)):
        world.step(1 / 15)
        t += 1 / 15
        _, info = world.render()
        truth = world.truth(info, t)
        heights += [w["h_native_px"] for w in truth["workers"] if w["posture"] == "squat"]
        det.feed(truth, t)
        boxes = tracker.update(det.run(None, t), t)
        dist = {i: edge_distance(*ground_from_image(H, *undistort_pixel(*foot_pixel(b), lens)), pit) for i, b in boxes.items()}
        kinds += [k for k, _ in fsm.update(t, dist)]
    assert heights and min(heights) >= 100, f"squatting worker only {min(heights):.0f} px in the processed image"
    assert "alarm" in kinds, kinds
