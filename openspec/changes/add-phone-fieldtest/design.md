## Context

The twin's coverage maths (`tools/coverage.py`, `catalog/effects.py`, `world/camera.py`) is tested only against the twin's own renderer. The user has a 12 MP phone (main camera 4096 × 3072, 23 mm equivalent, with 28 and 35 mm crop modes in the phone's own camera app) and the IP Webcam app, and wants to check the formulas in a car park before the Hikvision is bought.

## Goals / Non-Goals

**Goals:**
- Check, with a real lens and a real scene, that density, the largest-zone square, its placement and the height window come out as the formulas predict.
- Reuse the twin's code, not a second copy of the maths.
- Make the same tool work later with the Hikvision's RTSP stream.

**Non-Goals:**
- A phone app. The phone only streams.
- Testing reaction time or the alarm chain (Wi-Fi latency is irrelevant to geometry).
- Testing the barrel-distortion model with the main camera: the phone removes its distortion in software, so main-camera frames test the field-of-view method (D ≈ 0). The distortion model is tested with the ultra-wide camera instead (D10).

## Decisions

### D1. Host tool with a local web page
`python3 -m tools.fieldtest serve --url <stream>` serves `127.0.0.1:8090`: the live picture with the overlay, and buttons for each step. Clicking happens in the browser, so OpenCV stays headless (no GUI package, no conflict with `opencv-python-headless`). Every step is also a CLI subcommand that works on a recording. *Alternative:* OpenCV windows; rejected because the repo uses the headless build.

### D2. Phone settings in `fieldtest/phone.yaml`, not the catalogue
The file has the same camera keys `largest_zone()` reads (`resolution_px`, `hfov_deg`), plus `stream_url`, `still_url`, `sensors_url` and `focal_equiv_mm`. Nominal HFOV comes from the equivalent focal length on a 4:3 frame: θ = 2·atan(17.31 mm / f), so 73.9° at 23 mm, 63.4° at 28 mm, 52.6° at 35 mm. After calibration the measured f/p replaces the nominal one. The phone is a test instrument, so it stays out of `catalog/` and its cost totals.

### D2a. Phone: Redmi Note 13 Pro, Samsung ISOCELL HP3
Main camera: ISOCELL HP3, 200 MP, 1/1.4", 0.56 µm native pixels, about 16,320 × 12,240, so the sensor is about 9.14 × 6.85 mm. Lens 23 mm equivalent, f/1.7, so the physical focal length is about 6.07 mm (crop factor 43.27 / 11.42 = 3.79). The pixel pitch p in ρ = f/(p·z) is the pitch of the image the tool actually processes: sensor width ÷ N.

| Mode | Image width N | Effective p | f/p | HFOV |
|---|---|---|---|---|
| 200 MP full | 16,320 | 0.56 µm | about 10,840 | 73.9° |
| 50 MP (4-in-1) | 8,160 | 1.12 µm | about 5,420 | 73.9° |
| 12.5 MP (16-in-1), 23 mm | about 4,080 | 2.24 µm | about 2,710 | 73.9° |
| 28 mm crop, 12.5 MP | about 4,080 | about 1.84 µm | about 3,300 | 63.4° |
| 35 mm crop, 12.5 MP | about 4,080 | about 1.47 µm | about 4,130 | 52.6° |
| Video 1920 × 1440 | 1,920 | about 4.76 µm | about 1,276 | 73.9° |
| Video 1440 × 1080 | 1,440 | about 6.35 µm | about 957 | 73.9° |

The 28 and 35 mm modes crop the middle of the 200 MP sensor (7.5 and 6.0 mm wide, still more than 4,080 binned pixels), so they carry real detail, not upscaling. These are nominal values from the published specs. The checkerboard calibration replaces them, and the photo's EXIF gives the exact width (about 4,080 or 4,096).

Ultra-wide camera: 8 MP, 1/4", 1.12 µm, f/2.2, about 3,264 × 2,448, quoted at 118° (probably diagonal, so roughly 100–108° horizontal; calibration decides). With the phone's ultra-wide distortion correction switched off, it shows real barrel distortion over a field of view like the Hikvision's (102°), so it can test the distortion model.

### D3. N is what arrives
The tool reads the frame size from the stream. All predictions use that N and the f/p calibrated at that size. The formulas scale as N/ρ, so a 1440 × 1080 stream at ρ = 100 tests the same equations as 4096 × 3072 at ρ = 284 — and fits a car park:

| Setting | Stream | f/p | z_max | W_max | S | d | Near edge |
|---|---|---|---|---|---|---|---|
| 23 mm | 1440 × 1080 | 957 | 9.57 m | 14.4 m | 5.75 m | 6.69 m | 3.82 m |
| 23 mm | 1920 × 1440 | 1276 | 12.76 m | 19.2 m | 7.67 m | 8.93 m | 5.09 m |
| 23 mm | 4096 × 3072 | 2722 | 27.22 m | 40.96 m | 16.35 m | 19.04 m | 10.87 m |
| 28 mm | 1440 × 1080 | 1165 | 11.65 m | 14.4 m | 6.44 m | 8.43 m | 5.21 m |
| 35 mm | 1440 × 1080 | 1456 | 14.56 m | 14.4 m | 7.24 m | 10.94 m | 7.32 m |

(ρ = 100 px/m, nominal lens, field-of-view method.) The first row is the default field test. A full-resolution check uses stills from IP Webcam's photo endpoint, calibrated separately if their field of view differs from the video's.

### D4. Pose from cones, sensors as cross-check
The user tapes 4–8 cone positions on the ground (metres, origin at the point under the phone, y forward). Clicking each cone's base gives pixel–ground pairs; `cv2.solvePnP` with the calibrated intrinsics gives height, pitch, roll and heading. This is the same idea as `tools/calibrate.py`'s four markers, and more accurate than phone sensors. IP Webcam's `sensors.json` gravity vector, if available, is logged as a cross-check on pitch and roll.

### D5. Two runs: level and tilted
- **Level run:** phone level at 1.5 m. Depth along the optical axis equals the forward ground distance, so the plan-view formulas apply exactly, and a vertical 1 m pole at depth z is exactly f/p ÷ z pixels tall. The near edge (3.82 m) is above the ground cut-off (1.5 m / tan 29.4° = 2.66 m), so the whole square is visible.
- **Office run:** for a 3 × 4 m room, ρ is raised until the far edge is 4 m away: about 680 px/m with 12.5 MP photos (f/p ≈ 2,710) or 240 px/m with the 1440 stream. S = 2.40 m, d = 2.79 m, near edge 1.59 m, phone level at 0.9 m or lower. It tests the same geometry at a smaller scale; detection at 100 px is mimicked by shrinking the picture.
- **Tilted run:** phone tilted about 10° down. The tool predicts with full 3D projection (`PinholeCamera`) and also prints the plan-view numbers, showing how far they drift.

### D6. Measurement and pass bands
Each measurement stores: clicked pixels, ground position (from the pose), predicted pixel length, measured length, error. Pass bands:
- lens: reprojection error ≤ 0.5 px
- pose: height within 5 cm of the tape, cone reprojection ≤ 2 px
- overlay: each taped corner cone within 2 % of the image width of its drawn corner
- density: measured within ±5 % of predicted (±1 px floor for short objects)

### D7. Detection sweep reuses `app.detect`
The sweep calls the twin's YOLO detector (same ONNX model, same tiling option) on stream frames and records person box height and confidence against the person's ground distance, then fits the distance where the detection rate falls below 90 % and reports the box height there.

### D8. Privacy and network
The page binds to 127.0.0.1 unless `--bind` is given. Recordings and reports stay in `reports/fieldtest/` (git-ignored) and the report reminds the user to delete footage of people after the test. IP Webcam should be set with a login; the URL may carry it, and the tool never prints it.

### D10. Ultra-wide distortion test
The phone's own camera app takes ultra-wide photos with distortion correction off (IP Webcam may not open the ultra-wide). The tool loads them as files:
1. Checkerboard calibration with OpenCV's standard model gives the real distortion.
2. From the calibrated centre f/p and the measured horizontal field of view, the tool computes q and D exactly as `catalog.effects.lens` does from a datasheet (q = (N/2) / (f/p · tan(θ/2)), D = 3(1 − q) / tan²(θ/2)).
3. It compares the model's density factor g = 1 − D·u² with the density the calibration gives across the image (at u = 0.25, 0.5, 0.75 and the edge), and measures a 1 m pole at the centre and near the edge at the same depth.
This shows whether the simple D model the twin uses for the Hikvision is close enough, or whether a calibrated distortion profile should replace it.

### D9. Quick checks without a phone
P01–P11 run on a synthetic pinhole camera: solver numbers, scale invariance, projection round trip, pose recovery, checkerboard calibration, level-pole density, overlay geometry, pass-band logic, stream-shape guard, loopback binding, and recovery of D from a synthetic distorted camera (P11).

### D11. Implementation notes (deviations found while building)
- **The corridor's square is fitted to the tilted phone.** `largest_zone` assumes a level camera. At 0.45 m and tilted down that left the far corners reading 421 px/m at ρ 380 and the near corners about 60 px inside the frame. With `fit_zone`, `overlay.fit_zone` searches for the far edge where the corner's 3D px/m (a 1 m pole's pixels, the number on the picture) equals ρ and the near corners reach the frame's edge, for the phone aimed at the square's centre: S 1.53 m against 1.37 m with fx 877. Across the floor, and for a short stick at the far corner, that edge has about 343 px/m: the pole reads higher because its top is above the phone and nearer to it. The other presets keep the level-camera numbers, and `tools.coverage` and the v11 pole's figures don't change. The square doesn't change when the pose is solved, because the markers were taped from it. The corridor preset also has `taped_square`, the marks already on the floor (±0.71 m, z_far 2.37 m, d 1.68 m), which takes priority: at ρ 380 its far corners read about 408 px/m and its near corners sit about 65 px inside the frame, and it is 1.42 m wide by 1.38 m deep. A taped square is drawn at its floor coordinates, not ahead of the solved phone, so its overlay check measures the marks against the pose; the phone's offset is read from the pose line. Removing `taped_square` brings the fit back.
- **P11 checks calibration, not 1 − D·u² at the edge.** A 102° lens with q = 0.571 gives D = 0.844, but the twin's g = 1 − D·u² turns negative past u = 1.09, while the frame edge is at u = tan 51° = 1.23 (the same fold as v11's D14). No lens can match the cubic at the edge. So P11 renders checkerboard corners through an OpenCV-model lens with the same field of view and q (monotone to the corners). It checks that the recovered D is within 0.03 of 0.844 and that the calibrated g at the edge is within 3% of that lens's true g. The report still prints 1 − D·u² beside the calibrated lens at u = 0.25, 0.5, 0.75 and the edge, as the spec asks. For the synthetic lens that is 3.7%, 19%, 33% and a sign change at the edge, which is the finding this test is meant to make on the real ultra-wide.
- **`app.detect.YoloDetector.scored()`.** The sweep needs each box's confidence, which `run()` drops. `scored()` returns (box, confidence) pairs with the same tiling and NMS; `run()` returns the same boxes as before.
- **Corner coordinates.** The layout sheet prints ±2.87 m: S/2 = 2.8746 m. The ±2.88 in the tables above is the rounded S (5.75 m) halved.
- **One camera model.** `FieldCamera` is a `world.camera.PinholeCamera` in the calibrated lens's ideal image (one focal length fx, the calibrated principal point), with any pose including roll; `FieldLens` moves clicks and drawings between that image and the real, distorted one. fy is applied when distorting, so vertical lengths use the calibrated fy.
- **The page survives bad input.** Cones with no pose read pose FAIL with the reason and the picture falls back to the assumed camera; a saved row whose base can't be placed stays with no numbers. New clicks that are not numbers, and a base above a solved camera's horizon, get a 400 and are not saved.
- **A restart continues the day's session** when frame size and preset match; otherwise the old `session.json` is moved aside. A session's clicks are worth more than a clean start, and undoing them is one button.
- **Corner px/m stays inside the lens fit.** A low phone's 1 m pole at a near corner runs far outside the frame, where the distortion polynomial means nothing (6000 px/m against about 840). There the corner shows the density just above the ground instead; poles inside the frame, and undistorted lenses, keep the 1 m pole.
- **No verdict without a pose.** Before four cones are clicked the camera is an assumption (at the taped height, aimed at the square's centre). It draws the preview and fills the rows, but overlay and density read "not run": a PASS against an assumed pose would prove nothing.
- **Everything belongs to its focal length.** The 23, 28 and 35 mm settings share stream sizes, so each has its own `calib_WxH_<f>mm.json` and `views_WxH_<f>mm.json`, and the tool falls back to the nominal lens (and no views) until calibrated there. An older `calib_WxH.json` or `views_WxH.json` counts as the focal it records, or 23 mm (the only one used then). Clicks and the sweep are parked in the session when the focal length changes and come back with it: a click locates a point only in the picture it was made on. `serve --focal` picks the focal at the start.
- **A bad fit doesn't replace a lens.** A reprojection over the band, or fx more than 15% from nominal (23 to 28 mm is 22%, the phone's real lens 6%), isn't saved; `calibrate --force` overrides on the command line. A view whose corners match an earlier one within 0.5 px isn't counted (a frozen stream, a board not moved), and a stream that changes size stops capture and calibration.
- **The overlay gate covers verdicts too.** On a non-4:3 frame without a lens calibrated at that size, the overlay step reads "not run", `overlay.png` is the plain frame and the `overlay` command refuses.
- **Detection PASS.** The sweep step passes when the detection rate stays at 90% or more down to a 100 px box (the twin's required density for a 1 m squatting worker), so the sweep must actually reach that box: a perfect run stopping at 225 px fails. It reads "not run" with no frame inside a step, or without a solved pose (the feet are placed with the camera). The detector runs as the app's yolo mode does (`make_detector`, confidence 0.4), not at a lower threshold that would flatter it.

## Risks / Trade-offs

- **IP Webcam may not offer 4:3 video, or may stream from a crop** → the source check flags it; use stills for the 4:3 checks.
- **Autofocus changes f/p slightly** → lock focus far (or set continuous video focus) before calibrating and keep it.
- **28/35 mm crops may not be available to IP Webcam** → use IP Webcam's zoom (1.22×, 1.52×) and check that detail is real, not upscaled (calibrated f/p must scale with the zoom and the checkerboard must stay sharp).
- **Clicking error** → about ±1 px; long objects (1 m pole at ≤ 10 m is ≥ 95 px at 1440) keep it under 1–2 %.
- **Sun and shadows on cones** → click the cone base centre; use contrasting cones.

## Migration Plan

New tool only; nothing to migrate. Remove by deleting `tools/fieldtest/`, `fieldtest/` and `tests/smoke_fieldtest.py` and the seventh script in the chain.

## Open Questions

- Exact model (Note 13 Pro 5G or Pro+); both use the same 200 MP HP3 main camera, so the main-camera values do not change.
- Which IP Webcam video sizes the phone offers in 4:3.
