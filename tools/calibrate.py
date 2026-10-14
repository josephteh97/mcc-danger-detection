"""Calibration step, as an installer does on site: four ground markers with known positions,
their pixels in the camera image, and the image-to-ground homography the app loads.

    python3 -m tools.calibrate --out /data/calib/homography.npy

An existing file is left unchanged (so a restart keeps the same calibration); use --force
to recalibrate.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog                                                        # noqa: E402
from world.camera import PinholeCamera, image_to_ground_homography    # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the image-to-ground homography")
    ap.add_argument("--out", default="/data/calib/homography.npy")
    ap.add_argument("--site")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if os.path.exists(a.out) and not a.force:
        print(f"calibration: {a.out} already exists; keeping it")
        return
    site = catalog.load_site(a.site)
    H, pix = image_to_ground_homography(PinholeCamera.from_site(site), site["calibration"]["points"])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.save(a.out, H)
    print(f"calibration: wrote {a.out} from markers at pixels {np.round(pix, 1).tolist()}")


if __name__ == "__main__":
    main()
