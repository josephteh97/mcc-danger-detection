## ADDED Requirements

### Requirement: Phone camera source
`tools/fieldtest` SHALL read a live picture from the phone over Wi-Fi from a configurable URL in `fieldtest/phone.yaml` (defaults for the IP Webcam app: video `rtsp://<phone>:8080/h264_ulaw.sdp` or MJPEG `http://<phone>:8080/video`, stills `http://<phone>:8080/photo.jpg`, sensors `http://<phone>:8080/sensors.json`). It SHALL take N and the frame height from the frames actually received, and warn when the frame is not 4:3 or its size changes during a session.

#### Scenario: 4:3 stream accepted
- **WHEN** the stream delivers 1440 × 1080 frames
- **THEN** the tool uses N = 1440 for every prediction and shows the frame size on the page

#### Scenario: 16:9 stream flagged (P09)
- **WHEN** the stream delivers 1920 × 1080 frames
- **THEN** the tool warns that the frame is cropped to 16:9, so the 4:3 lens values do not apply, and refuses to run the overlay until the lens is calibrated at that size

### Requirement: Phone profile
`fieldtest/phone.yaml` SHALL ship with the Redmi Note 13 Pro values: main camera Samsung ISOCELL HP3, 200 MP, 1/1.4", 0.56 µm native pixels, sensor about 9.14 × 6.85 mm, 23 mm equivalent, 28 and 35 mm crop modes; ultra-wide 8 MP, 1/4", 1.12 µm, quoted 118°. The tool SHALL compute the effective pixel pitch p of every image it processes as sensor width ÷ N (crop width ÷ N for the 28 and 35 mm modes) and print it with f/p.

#### Scenario: Effective pitch of a 12.5 MP photo
- **WHEN** a 23 mm photo 4,080 px wide is loaded
- **THEN** the tool prints p = 2.24 ± 0.02 µm and nominal f/p = 2,710 ± 20 px

#### Scenario: Effective pitch of the video stream
- **WHEN** the stream is 1440 × 1080 at 23 mm
- **THEN** the tool prints p = 6.35 ± 0.05 µm and nominal f/p = 957 ± 5 px

### Requirement: Lens calibration
The tool SHALL calibrate the lens from at least 12 checkerboard views (default 9 × 6 inner corners, square size in `phone.yaml`) with OpenCV, per stream size, and store f/p (fx, fy), the principal point and distortion coefficients. It SHALL report the reprojection error and compare fx with the nominal f/p from `focal_equiv_mm` (θ = 2·atan(17.31 / f), f/p = (N/2) / tan(θ/2)).

#### Scenario: Good calibration
- **WHEN** 15 sharp views are captured at 1440 × 1080
- **THEN** the reprojection error is at most 0.5 px and the report shows the measured fx against the nominal 957 px for 23 mm, with the difference in percent

#### Scenario: A saved lens belongs to its focal length
- **WHEN** a lens calibrated at 23 mm is saved and the tool runs at the same stream size with 28 mm set
- **THEN** it uses the nominal lens for 28 mm, not the saved one, until the lens is calibrated at 28 mm, and the 23 mm lens, views and clicks are there again on going back

#### Scenario: A bad fit isn't saved
- **WHEN** a fit's reprojection error is over the pass band, or its fx is more than 15% from the nominal at the set focal length
- **THEN** the tool says why and keeps the previous calibration

#### Scenario: Synthetic calibration (P05)
- **WHEN** the calibration runs on 15 synthetic checkerboard views rendered with fx = 957 px
- **THEN** it recovers fx within 0.5%

### Requirement: Pose from ground cones
The tool SHALL find the camera's pose from 4 to 8 cones whose ground positions the user has taped (metres; origin on the ground under the phone, y forward, x right) and whose bases the user clicks on the page. It SHALL solve with `cv2.solvePnP` and the calibrated lens, and report height, pitch, roll, heading and the reprojection error of each cone. When IP Webcam's sensor data is available, it SHALL log the gravity-based pitch and roll beside the solved ones.

#### Scenario: Level phone at 1.5 m
- **WHEN** the phone is level 1.5 m above the ground and four cones are clicked
- **THEN** the solved height is within 5 cm of 1.5 m, pitch within 1° of 0°, and every cone reprojects within 2 px

#### Scenario: Cones with no pose
- **WHEN** four or more cones give no pose (repeated, on one line, or solved below the ground)
- **THEN** the pose step reads FAIL with the reason, the picture keeps running with the assumed camera, and undoing a cone recovers

#### Scenario: Synthetic pose (P04)
- **WHEN** cones are projected through a synthetic camera 1.5 m high and 8° down, with 0.5 px noise added
- **THEN** the solved height is within 2 cm and pitch within 0.3°

### Requirement: Square from the calibrated lens
For a chosen required density ρ (default 100 px/m), the tool SHALL compute W_max, z_max, S and d with `tools.coverage.largest_zone` from the calibrated f/p and the received N (a preset with `taped_square` uses those marks instead, and one with `fit_zone` fits S and z_max to the tilted phone), and place the square on the ground centred on the camera's forward line with its far edge at z_max.

#### Scenario: Default field test numbers (P01)
- **WHEN** the nominal 23 mm lens and a 1440 × 1080 stream are used at ρ = 100 px/m
- **THEN** z_max = 9.57 ± 0.05 m, W_max = 14.4 m, S = 5.75 ± 0.05 m and d = 6.69 ± 0.05 m

#### Scenario: Square fitted to a low, tilted phone
- **WHEN** a preset has `fit_zone` and no `taped_square` (ρ 380, phone at 0.45 m aimed at the square's centre)
- **THEN** the far corners' 3D px/m equals ρ within 0.5 px/m, the near corners reach the frame's edge, and S is larger than the level-camera formula gives

#### Scenario: Square already taped
- **WHEN** a preset has `taped_square`
- **THEN** the layout and the drawn square use those marks whatever the lens or ρ

#### Scenario: Scale invariance (P02)
- **WHEN** the solver runs for N = 1440 at ρ = 100 and for N = 4096 at ρ = 284.4
- **THEN** S, d and z_max agree within 1%

### Requirement: Coverage overlay
The tool SHALL draw on the live picture the camera's ground footprint, the W_max line at z_max, the square S and its centre at d, ground grid lines every 1 m, and the predicted px/m at each corner from the full 3D projection. When the camera is tilted it SHALL print the plan-view values beside the 3D ones.

#### Scenario: Near corners on the image edge (P07)
- **WHEN** a synthetic level camera draws the square
- **THEN** the two near corners fall on the left and right image edges within 1 px, and the far edge lies at z_max

#### Scenario: Corner density beyond the lens fit
- **WHEN** a 1 m pole at a corner has its top outside the calibrated part of the image
- **THEN** the corner's 3D px/m is the density just above the ground, not the pole through the distortion polynomial

#### Scenario: Live overlay on the cones
- **WHEN** cones are taped at the four corners from the layout sheet and the overlay is on
- **THEN** each drawn corner lies within 2% of the image width of its cone's base

### Requirement: Cone layout sheet
The tool SHALL print and save a layout sheet for the current settings: the four corner positions and the centre of the square, the two points where the W_max line meets the footprint, and 1 m marks along the forward line, all as (x, y) metres from the point under the phone, ready to tape out.

#### Scenario: Layout for the default test
- **WHEN** the default field test is set up
- **THEN** the sheet lists the far corners at (±2.88, 9.57) m and the near corners at (±2.88, 3.82) m

#### Scenario: Office preset
- **WHEN** the office preset is chosen (12.5 MP photo, 23 mm, ρ = 680 px/m, phone level at 0.9 m)
- **THEN** the sheet gives z_max 3.99 m, S 2.40 m, d 2.79 m and near edge 1.59 m, so the square fits a 3 × 4 m room

### Requirement: Measurement against prediction
The user SHALL be able to click the two ends of a vertical object (a 1 m pole, or a squatting worker's head and feet) with its true length typed in. The tool SHALL find the object's ground position from the lower click and the pose, predict its pixel length by projecting both ends through the calibrated camera, and log clicked pixels, ground position, predicted and measured length and error. A measurement SHALL pass within ±5% (or ±1 px for objects under 20 px).

#### Scenario: Level pole density (P06)
- **WHEN** a synthetic level camera with fy = 957 px sees a vertical 1 m pole at depth 9.57 m
- **THEN** the projected length is 100.0 ± 0.1 px, equal to fy / z

#### Scenario: Pole at the far corner
- **WHEN** a 1 m pole stands at a far corner of the default square in the level run
- **THEN** it measures about 100 px and the measurement passes within ±5% of the prediction

#### Scenario: No verdict without a pose
- **WHEN** a measurement or a named cone is clicked before the pose is solved (fewer than 4 cones)
- **THEN** the rows are kept, worked out from the camera aimed at the square's centre, and their result and the overlay and density steps read "not run", neither PASS nor FAIL

#### Scenario: Base the camera can't place
- **WHEN** a measurement's base is above the horizon of the current camera
- **THEN** a new click is refused if the pose is solved; a row already saved stays, with no prediction, reading FAIL with a solved pose and "not run" without one, and the page keeps working

#### Scenario: Pass-band logic (P08)
- **WHEN** the measurement log holds a 3% error, a 7% error and a 1 px error on a 15 px object
- **THEN** they are marked PASS, FAIL and PASS

### Requirement: Detection sweep
The tool SHALL optionally run the twin's YOLO person detector (`app.detect`, same model and tiling option) on stream frames while a person walks or squats along the forward line, and record each person box's pixel height, confidence and ground distance. The report SHALL plot detection rate against box height and distance, give the box height where the rate falls below 90%, and mark the 100, 80 and 50 px reference heights.

#### Scenario: Sweep report
- **WHEN** a squatting person is recorded at 1 m steps from 3 m to 20 m
- **THEN** the report gives the detection rate at each step and the box height at the 90% point

#### Scenario: Detection verdict
- **WHEN** the sweep ends
- **THEN** detection passes only if the rate holds 90% down to a 100 px box; a sweep that never reached that box fails, and one with no judged frames or no solved pose reads "not run"

### Requirement: Record and replay
The tool SHALL record the stream to a file in `reports/fieldtest/<date>/` and every step (calibration, pose, overlay, measurement, sweep) SHALL run on a recording as well as live.

#### Scenario: Restarting the page keeps the session
- **WHEN** the page restarts on the same day with the same frame size and preset
- **THEN** it continues the saved `session.json` with its clicks; with another preset, or a file it can't read, it starts anew and moves the old file aside, never overwriting it

#### Scenario: Stopping a recording
- **WHEN** a recording is stopped on the page, or the page exits while recording
- **THEN** the file plays, and on the page another recording can start

#### Scenario: Replay matches live
- **WHEN** a recorded session is replayed with the same clicks
- **THEN** the measurement log is identical to the live one

### Requirement: Field test report
The tool SHALL write a Markdown report, a CSV log and annotated images to `reports/fieldtest/<date>/`, with PASS or FAIL for lens, pose, overlay, density and (if run) detection, and the settings used (focal setting, stream size, ρ, height, pitch).

#### Scenario: Report contents
- **WHEN** a level run with four pole measurements finishes
- **THEN** the report shows each step's result, the measured against nominal f/p, and a table of predicted against measured pixel lengths

### Requirement: Privacy and network limits
The field-test page SHALL bind to 127.0.0.1 unless `--bind` is given. The tool SHALL NOT join the twin's Docker networks or change its published ports. It SHALL never print a password contained in the stream URL. The report SHALL remind the user to delete recordings that show people once the test is done.

#### Scenario: Loopback by default (P10)
- **WHEN** `python3 -m tools.fieldtest serve` starts without `--bind`
- **THEN** it listens only on 127.0.0.1:8090

#### Scenario: Password hidden
- **WHEN** the stream URL is `rtsp://user:secret@192.168.1.20:8080/h264_ulaw.sdp`
- **THEN** logs and the page show `rtsp://user:***@192.168.1.20:8080/h264_ulaw.sdp`

### Requirement: Projection round trip
The overlay and measurement SHALL use one projection: `world.camera.PinholeCamera` built from the solved pose and calibrated lens, with the calibrated distortion applied to image points.

#### Scenario: Ground to image to ground (P03)
- **WHEN** 100 ground points inside the footprint are projected to the image and back to the ground
- **THEN** every point returns within 1 mm

### Requirement: Ultra-wide distortion test
The tool SHALL load ultra-wide photos taken with the phone's distortion correction off, calibrate them from a checkerboard, and compute q and D from the calibrated centre f/p and the measured horizontal field of view with the same formulas as `catalog.effects.lens`. It SHALL compare the model's density factor g = 1 − D·u² with the calibrated lens at u = 0.25, 0.5, 0.75 and the image edge, and report the largest difference in percent.

#### Scenario: Synthetic distorted camera (P11)
- **WHEN** checkerboard views are rendered through a synthetic 102° camera with D = 0.844 and calibrated
- **THEN** the recovered D is within 0.03 of 0.844 and g at the image edge is within 3% of the model

#### Scenario: Real ultra-wide
- **WHEN** 15 ultra-wide checkerboard photos with correction off and two 1 m pole photos (centre and edge, same depth) are loaded
- **THEN** the report gives the ultra-wide's horizontal field of view, q, D, the g comparison table, and the measured edge-to-centre pole ratio against 1 − D·u²
