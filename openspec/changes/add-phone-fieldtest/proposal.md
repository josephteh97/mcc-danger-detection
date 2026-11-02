## Why

The v11 design rests on the coverage formulas in `tools/coverage.py` and `catalog/effects.py`: density ρ = (f/p)/z, the largest square zone (W_max = N/ρ, z_max = N/(2ρ·tan(θ/2)), S = W_max·z_max/(z_max + W_max), d = z_max − S/2), and the placement and height windows. So far they have only been checked against the twin's own renderer. Before buying the 12 MP camera we want a real-world check with a real lens, real perspective and a real detector.

A phone's 12 MP main camera (4096 × 3072, 23 mm equivalent, about 74° horizontal) is a good stand-in. The phone streams over Wi-Fi with the free IP Webcam app, and a tool on the Linux PC runs the same coverage code as the twin on the live picture. This mirrors the real chain (camera → RTSP → AI box), and when the Hikvision arrives only the stream address and the camera settings change.

## What Changes

- Add a host-side field-test tool, `tools/fieldtest/`, with a local web page on `127.0.0.1:8090` and command-line subcommands. It is not part of the Docker stack and does not join the twin's networks.
- **Phone source:** read IP Webcam's video stream (RTSP or MJPEG) and full-resolution stills; take N from the frames actually received, not from settings; flag a stream that isn't 4:3 or isn't the main camera at 1×.
- **Lens calibration:** a checkerboard calibration (OpenCV) gives the real f/p and distortion per stream size; the report compares them with the 23 mm prediction.
- **Pose from cones:** 4–8 cones at taped ground positions are clicked in the image; `solvePnP` gives the camera height, tilt, roll and heading. The phone's sensors (IP Webcam `sensors.json`) are a cross-check only.
- **Coverage overlay:** for a chosen ρ, draw on the live picture the camera's ground footprint, the W_max line at z_max, the square S and its centre d, 1 m grid lines, and the predicted px/m at the corners. A cone layout sheet gives the four corner positions to tape out.
- **Measurement:** click the two ends of a 1 m pole or a squatting worker; compare measured pixel height with the prediction from the calibrated camera; log every measurement.
- **Detection sweep (optional):** run the twin's YOLO detector on the stream and record box height and confidence against distance, to find where detection stops being reliable and compare with the 100, 80 and 50 px figures.
- **Record and replay:** record the stream to a file; every step also runs on a recording, so a site visit can be analysed again later.
- **Report:** Markdown, CSV and annotated images under `reports/fieldtest/<date>/` (already git-ignored), with PASS or FAIL per step.
- **Ultra-wide distortion test:** ultra-wide photos taken with the phone's distortion correction off are loaded as files; the tool calibrates them and checks the twin's q, D and g = 1 − D·u² model against the real lens, at a field of view (about 100–118°) like the Hikvision's.
- `fieldtest/phone.yaml` ships with the Redmi Note 13 Pro values (Samsung ISOCELL HP3 main camera; 8 MP ultra-wide).
- Add quick checks P01–P11 in a new `tests/smoke_fieldtest.py` that need no phone (synthetic camera, cones and checkerboard).

## Capabilities

### New Capabilities
- `phone-fieldtest`: Phone camera source and profile, lens calibration, pose from cones, coverage overlay and layout sheet, measurement, ultra-wide distortion test, optional detection sweep, record and replay, report, and privacy and network limits.

### Modified Capabilities
- `validation-suite`: A seventh quick-check script, `tests/smoke_fieldtest.py`, with P01–P11; counts become 64 checks, 63 PASS plus the V11 known fail.

## Impact

- **New code:** `tools/fieldtest/` (source, calib, pose, overlay, measure, sweep, report, web page), `fieldtest/phone.yaml` (phone settings, kept out of `catalog/` because the phone is a test instrument, not a product), `tests/smoke_fieldtest.py`, a small synthetic fixture under `tests/fakes/`.
- **Reused unchanged:** `tools.coverage.largest_zone`, `catalog.effects` density maths, `world.camera.PinholeCamera` projection, `app.detect` YOLO detector.
- **Dependencies:** none new for the required parts (OpenCV headless, numpy, FastAPI and uvicorn are already in `requirements.txt`). The detection sweep needs a person-detector ONNX file, as the `yolo` mode already does.
- **Unchanged:** the Docker stack, its networks and published ports, the alarm app, and all existing checks.
