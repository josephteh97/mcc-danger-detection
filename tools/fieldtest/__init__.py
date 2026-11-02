"""Field test of the coverage formulas with a phone camera (openspec change add-phone-fieldtest).

The phone streams over Wi-Fi (IP Webcam); this host-side tool runs the twin's own coverage code on
the live picture: `tools.coverage.largest_zone`, `catalog.effects` and `world.camera.PinholeCamera`.
Ground frame: metres from the point on the ground under the phone, x right, y straight ahead, z up.

    python3 -m tools.fieldtest serve --url <stream>          # page on 127.0.0.1:8090
    python3 -m tools.fieldtest --help                        # every step, also on a recording
"""
from __future__ import annotations

import math
import os
import sys
import time

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PHONE_FILE = os.path.join(ROOT, "fieldtest", "phone.yaml")
LOCAL_FILE = os.path.join(ROOT, "fieldtest", "phone.local.yaml")   # git-ignored: the stream URLs with the login
REPORTS = os.path.join(ROOT, "reports", "fieldtest")     # git-ignored with reports/
HALF_WIDTH_35MM = 17.31          # half the width of a 4:3 frame on a 43.27 mm (35 mm film) diagonal


def load_phone(path=None, local=LOCAL_FILE):
    """The phone settings, with the keys of the git-ignored phone.local.yaml (the stream, still and
    sensor URLs with the login) laid over them, so the password never goes into the repo."""
    with open(path or PHONE_FILE) as f:
        phone = yaml.safe_load(f)
    if local and os.path.exists(local):
        with open(local) as f:
            phone.update(yaml.safe_load(f) or {})
    return phone


def report_dir(date=None):
    d = os.path.join(REPORTS, date or time.strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    return d


def nominal_hfov(focal_equiv_mm):
    """Horizontal field of view of a 4:3 frame at an equivalent focal length: 2·atan(17.31 / f)."""
    return math.degrees(2 * math.atan(HALF_WIDTH_35MM / focal_equiv_mm))


def nominal_fp(n, focal_equiv_mm):
    """f/p of an N-pixel-wide 4:3 image at an equivalent focal length: (N/2) / tan(θ/2)."""
    return (n / 2) / math.tan(math.radians(nominal_hfov(focal_equiv_mm)) / 2)


def pitch_um(phone, n, focal_equiv_mm=None):
    """Effective pixel pitch of the processed image: sensor (or crop) width ÷ N. The 28 and 35 mm
    modes crop the middle of the sensor, so their width scales by 23 / f."""
    main = phone["main"]
    crop = main["sensor_mm"][0] * main["focal_equiv_mm"] / (focal_equiv_mm or main["focal_equiv_mm"])
    return 1000.0 * crop / n


def describe_pitch(phone, n, focal_equiv_mm=None):
    f = focal_equiv_mm or phone["main"]["focal_equiv_mm"]
    return (f"{n} px wide at {f:g} mm: p = {pitch_um(phone, n, f):.2f} µm, "
            f"nominal f/p = {nominal_fp(n, f):,.0f} px, HFOV {nominal_hfov(f):.1f}°")


def camera_spec(fp, n, h):
    """The camera keys `largest_zone` and `catalog.effects` read, for a lens of centre ratio f/p
    on an N × h image (a pinhole: the phone removes the main camera's distortion)."""
    return {"resolution_px": [int(n), int(h)], "hfov_deg": math.degrees(2 * math.atan((n / 2) / fp))}
