## MODIFIED Requirements

### Requirement: Camera rendering
The world SHALL render the camera's view with plain OpenCV, needing no GPU. The camera pose and lens SHALL come from the active site profile:
- **phase 1:** a pinhole 6.5 m up, about 8 m from the pit, aimed at the pit, 90° horizontal field of view, 1280×720 frames
- **v11:** the 12 MP stand camera 3.8 m up and 9.5 m south of the pit centre, 102° horizontal field of view, 4:3 frames of 1600×1200 with barrel distortion from the catalogue's D; the coverage maths still uses the native 4,000×3,000 resolution

It SHALL write BGR frames of the profile's size to stdout at the `--fps` rate (default 15). The world image's `world/entrypoint.sh` SHALL pipe them into a single `ffmpeg` command that encodes H.264 with `-pix_fmt yuv420p` and publishes `stream1` to the camera over `sim_ctrl`. 4:2:0 is the only H.264 format browsers decode. The Orin reads the stream as `rtsp://192.168.10.20:8554/stream1`.

The pipeline SHALL NOT be written as a folded YAML `command:`. In the guide's version, the line breaks split ffmpeg's encoder and output options into separate shell commands, and no stream was published.

The renderer SHALL draw:
- the ground with texture, the pit, its barriers and site features
- workers as shaded person shapes in their posture (walk, stand, squat, kneel), with hard hat, vest and a ground shadow from the sun
- the laser dot where the arm's beam actually lands
- the effects of the active weather preset
- at night in the `v11` profile, an IR monochrome image with brightness falling off with distance, and sensor noise that grows as light falls

#### Scenario: Frame format
- **WHEN** the world runs with `--fps 15`
- **THEN** it writes frames of the profile's size (1280×720×3 for phase 1, 1600×1200×3 for v11) at 15 frames per second

#### Scenario: Browser-decodable stream
- **WHEN** `ffprobe` reads `http://127.0.0.1:8080/video/stream1/index.m3u8`, the stream a browser gets
- **THEN** the video is H.264, `yuv420p`, at the profile's frame size

#### Scenario: Laser dot drawn where the beam lands
- **WHEN** the arm state shows the laser on at a given pan and tilt
- **THEN** the dot is drawn at the ground point where that beam meets the ground, as seen by the camera

#### Scenario: Barrel distortion in v11
- **WHEN** a straight barrier line crosses the image edge in the v11 profile
- **THEN** it is drawn bowed outward by the amount D predicts, within 2 px

### Requirement: Workers
The world SHALL move workers in ground metres:
- scripted walks: in, stand by the pit, out
- random passers-by (`--npcs <n>`)
- named scenario scripts: single walk-in, two workers at once, a passer-by on the ring edge, a worker who stops 1.6 m away, a worker hidden behind another, and a worker who squats at the far edge of the warning ring
- workers driven by the control port

Each worker SHALL have a posture (walk, stand, squat at 1.0 m, kneel at 1.2 m) that sets its height in the image and in the oracle's boxes.

Workers SHALL NOT pass the site boundary.

#### Scenario: Site boundary (V33)
- **WHEN** a controlled worker holds one direction key for 40 s
- **THEN** the worker stops at the site hoarding and stays inside the site

#### Scenario: Squatting worker size
- **WHEN** a worker squats at the far edge of the 3 m ring in the v11 profile
- **THEN** its box is about 1.0 m × the local px/m tall in the native image, and the processed-image height is what the miss model uses
