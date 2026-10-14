## ADDED Requirements

### Requirement: Site model
The world simulator (`world/world.py`) SHALL load the site from `site.yaml`:
- the pit outline in metres (default 2.4 m by 1.6 m, centred at the origin)
- the 1.5 m alarm zone and the 3 m warning ring
- the site boundary (the hoarding)
- the camera pose
- the laser arm position and heading
- the products fitted to the pole

#### Scenario: Default site
- **WHEN** the world starts with the default `site.yaml`
- **THEN** the pit is 2.4 m by 1.6 m, the alarm zone is 1.5 m and the warning ring is 3.0 m from the pit edge

### Requirement: Camera rendering
The world SHALL render the camera's view with plain OpenCV, needing no GPU. The default camera is a pinhole at the real pose: 6.5 m up, about 8 m from the pit, aimed at the pit, 90° horizontal field of view.

It SHALL write 1280×720 BGR frames to stdout at the `--fps` rate (default 15). `ffmpeg` encodes them as H.264 and pushes them to `rtsp://192.168.10.20:8554/stream1`.

The renderer SHALL draw:
- the ground, the pit and site features
- workers as simple person shapes
- the laser dot where the arm's beam actually lands
- the effects of the active weather preset

#### Scenario: Frame format
- **WHEN** the world runs with `--fps 15`
- **THEN** it writes 1280×720×3 byte frames at 15 frames per second

#### Scenario: Laser dot drawn where the beam lands
- **WHEN** the arm state shows the laser on at a given pan and tilt
- **THEN** the dot is drawn at the ground point where that beam meets the ground, as seen by the camera

### Requirement: Calibration homography
The world SHALL provide `image_to_ground_homography()`, which works as calibration does on site:
1. Take four ground points with known positions.
2. Find their pixels in the camera image.
3. Fit the image-to-ground homography that the app loads.

#### Scenario: Calibration file
- **WHEN** the calibration step runs for the default site
- **THEN** it writes a 3×3 homography to `/data/calib/homography.npy`, which maps the four calibration pixels to their ground points within 0.01 m

### Requirement: Workers
The world SHALL move workers in ground metres:
- scripted walks: in, stand by the pit, out
- random passers-by (`--npcs <n>`)
- named scenario scripts: single walk-in, two workers at once, a passer-by on the ring edge, a worker who stops 1.6 m away, and a worker hidden behind another
- workers driven by the control port

Workers SHALL NOT pass the site boundary.

#### Scenario: Site boundary (V33)
- **WHEN** a controlled worker holds one direction key for 40 s
- **THEN** the worker stops at the site hoarding and stays inside the site

### Requirement: Ground truth over UDP
For every frame, the world SHALL send ground truth as JSON over UDP to each `--truth host:port` target. The truth SHALL include:
- the frame time
- each worker's ID, true ground position and image box
- the arm and laser state it rendered
- the active weather preset

#### Scenario: Truth fan-out
- **WHEN** the world runs with `--truth dashboard:9100,192.168.10.2:9100`
- **THEN** both targets receive one truth message per frame, with matching frame times

### Requirement: Control port
When started with `--control <addr:port>` (for example `0.0.0.0:9200`), the world SHALL accept UDP control messages:
- held keys for a controlled worker
- add, switch and reset workers
- weather changes
- scenario starts

A controlled worker SHALL stop if no key message has arrived for 0.5 s, so a dropped link cannot leave them walking.

#### Scenario: Keys over the network (V34)
- **WHEN** a sender sends held-key messages about 10 times a second over UDP to the control port
- **THEN** the controlled worker moves in the held direction
- **AND** when the messages stop, the worker stops within 0.5 s (+ one frame)

### Requirement: Mast sway
The world SHALL move the whole image to model mast sway in wind, scaled by the weather preset's wind speed.

#### Scenario: Mast sway effect on foot error (V21)
- **WHEN** foot positions are measured in the `strong_wind` preset (15 m/s gusts) and compared with `clear`
- **THEN** the extra foot error is under 0.15 m (about 0.08 m expected)
