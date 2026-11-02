## 1. Settings and source

- [x] 1.1 Add `fieldtest/phone.yaml` with the Redmi Note 13 Pro profile (HP3 main: 200 MP, 1/1.4", 0.56 µm, 9.14 × 6.85 mm, 23/28/35 mm; ultra-wide 8 MP, 1/4", 1.12 µm, 118° quoted), stream, still and sensor URLs, checkerboard size, required ρ
- [x] 1.1a Effective pitch p = sensor (or crop) width ÷ N, printed with f/p for every image
- [x] 1.2 `tools/fieldtest/source.py`: open RTSP or MJPEG with OpenCV, fetch stills and `sensors.json`, read N from frames, warn on non-4:3 or size changes, hide URL passwords
- [x] 1.3 Check with the real phone which IP Webcam endpoints and 4:3 video sizes it offers; update the defaults in `phone.yaml`
  - Found 2026-11-02: the phone streams from an RTSP app on port 1945 (login, read over TCP), not IP Webcam, so no still or sensors endpoints. Sizes: 720p only (1080p and MAX greyed out), all 16:9; probe: 1280 × 720 at 6.5 fps (app set to 15). No 4:3 size, so preset `rtsp720` and a checkerboard calibration at 1280 × 720 replace the 4:3 lens values.
- [x] 1.4 Verify: P09 and P10 pass; `python3 -m tools.fieldtest probe --url <phone>` prints frame size and fps

## 2. Lens calibration

- [x] 2.1 `tools/fieldtest/calib.py`: capture checkerboard views (live or from a recording), `cv2.calibrateCamera`, save per stream size to `reports/fieldtest/calib_<w>x<h>.json`
- [x] 2.2 Report reprojection error and measured fx against nominal f/p
- [x] 2.3 Verify: P05 passes

## 3. Pose from cones

- [x] 3.1 `tools/fieldtest/pose.py`: taped cone positions plus clicked pixels → `cv2.solvePnP` → height, pitch, roll, heading, per-cone reprojection error
- [x] 3.2 Log IP Webcam gravity-based pitch and roll beside the solved values when available
- [x] 3.3 Build a `world.camera.PinholeCamera` from the pose and lens; apply calibrated distortion to image points
- [x] 3.4 Verify: P03 and P04 pass

## 4. Overlay and layout sheet

- [x] 4.1 `tools/fieldtest/overlay.py`: `tools.coverage.largest_zone` with calibrated f/p and received N; footprint, W_max line, square S, centre d, 1 m grid, corner px/m from 3D projection; plan-view values beside 3D when tilted
- [x] 4.2 Layout sheet (corners, centre, W_max points, 1 m marks) printed and saved
- [x] 4.3 Verify: P01, P02 and P07 pass

## 5. Measurement

- [x] 5.1 `tools/fieldtest/measure.py`: two clicks plus true length → ground position, predicted and measured pixel length, error, PASS/FAIL; append to CSV
- [x] 5.2 Verify: P06 and P08 pass

## 6. Detection sweep

- [x] 6.1 `tools/fieldtest/sweep.py`: run `app.detect` YOLO (same model, tiling option) on frames; record box height, confidence, ground distance; detection rate per step and the 90% point; mark 100/80/50 px
- [x] 6.2 Verify: sweep runs on a short recording and writes its table and plot

## 6a. Ultra-wide distortion test

- [x] 6a.1 `tools/fieldtest/distortion.py`: load ultra-wide photos (correction off), calibrate, compute q and D as `catalog.effects.lens` does, compare g = 1 − D·u² with the calibrated lens at u = 0.25, 0.5, 0.75 and the edge; centre and edge pole ratio
- [x] 6a.2 Verify: P11 passes

## 7. Web page, recording and report

- [x] 7.1 `tools/fieldtest/__main__.py`: subcommands `probe`, `serve`, `record`, `calibrate`, `pose`, `overlay`, `measure`, `sweep`, `report`; every step accepts `--file` for a recording
- [x] 7.2 Web page on 127.0.0.1:8090 (FastAPI, MJPEG of the overlaid picture, click capture, step buttons, live readouts)
- [x] 7.3 Report writer: Markdown, CSV, annotated PNGs in `reports/fieldtest/<date>/`, with the privacy reminder
- [x] 7.4 Verify: replaying a recording with saved clicks reproduces the live measurement log

## 8. Quick checks and docs

- [x] 8.1 `tests/smoke_fieldtest.py` with P01–P11 using `tests/_check.py`
- [x] 8.2 README: field-test section (phone setup in IP Webcam, level and tilted runs, cone layout, what PASS means)
- [x] 8.3 Verify: the seven-script chain gives 63 PASS + V11 known fail; `openspec validate add-phone-fieldtest --strict`

## 9. Field run (with the phone)

- [ ] 9.1 Lock focus far; calibrate at the chosen stream size
- [ ] 9.1a Office run: office preset (ρ ≈ 680, phone at 0.9 m), tape the 2.4 m square, check overlay and pole measurements
- [ ] 9.2 Level run (outdoor): phone at 1.5 m, ρ = 100, tape the layout sheet, solve pose, check overlay on cones, measure a 1 m pole at the four corners, the centre and on the forward line every 1 m
- [ ] 9.3 Tilted run: about 10° down; repeat the corner and centre measurements
- [ ] 9.4 Optional: 28 and 35 mm modes, full-resolution stills, detection sweep with a squatting person
- [ ] 9.4a Ultra-wide: switch off ultra-wide distortion correction in the phone's camera settings; take 15 checkerboard photos and two 1 m pole photos (centre and edge, same depth); run the distortion test
- [ ] 9.5 Commit the report summary (not the footage) and delete recordings showing people
