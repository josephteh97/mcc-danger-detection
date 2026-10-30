"""Calibration step, as an installer does on site: four ground markers with known positions,
their pixels in the camera image, and the image-to-ground homography the app loads.

    python3 -m tools.calibrate --out /data/calib/homography.npy

An existing file is left unchanged while it still fits the camera (it maps the markers' pixels
onto the markers within 2 cm), so a restart keeps the same calibration. If the camera has moved,
for example to the stand of another site profile, it is calibrated again, as an installer would;
--force always recalibrates.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog                                                        # noqa: E402
from world.camera import PinholeCamera, image_to_ground_homography    # noqa: E402


def fits(H, pix, ground, tol_m=0.02):
    """Does homography H map these marker pixels onto their ground positions?"""
    from app.alarm import ground_from_image
    return all(np.hypot(*(np.array(ground_from_image(H, u, v)) - g)) <= tol_m for (u, v), g in zip(pix, ground))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the image-to-ground homography")
    ap.add_argument("--out", default="/data/calib/homography.npy")
    ap.add_argument("--site")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    site = catalog.load_site(a.site)
    markers = site["calibration"]["points"]
    H, pix = image_to_ground_homography(PinholeCamera.from_site(site), markers)
    if os.path.exists(a.out) and not a.force:
        try:
            if fits(np.load(a.out), pix, np.asarray(markers, float)):
                print(f"calibration: {a.out} still fits the {site['profile']} camera; keeping it")
                return
        except (OSError, ValueError):
            pass
        print(f"calibration: {a.out} does not fit the {site['profile']} camera (it has moved); calibrating again")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.save(a.out, H)
    print(f"calibration: wrote {a.out} for the {site['profile']} camera from markers at pixels {np.round(pix, 1).tolist()}")


if __name__ == "__main__":
    main()
