## MODIFIED Requirements

### Requirement: Camera rendering
The world SHALL render the camera's view with plain OpenCV, needing no GPU. The camera pose and lens SHALL come from the active site profile:
- **phase 1:** a pinhole 6.5 m up, about 8 m from the pit, aimed at the pit, 90° horizontal field of view, 1280×720 frames
- **v11:** the 12 MP stand camera 3.8 m up and 9.5 m south of the pit centre, 102° horizontal field of view, 4:3 frames of 1600×1200 with barrel distortion from the catalogue's D; the coverage maths still uses the native 4,000×3,000 resolution
- **budget:** the 8 MP TP-Link VIGI C385 on the existing steel tube, 12.42 m from the pit centre (the solved standoff), 3840×2160 native at 91.5° horizontal field of view, render size from `sites/budget.yaml`; the undistorted pinhole until D has been measured for this camera, stated in the render's metadata

It SHALL write BGR frames of the profile's size to stdout at the `--fps` rate (default 15). The world image's `world/entrypoint.sh` SHALL pipe them into a single `ffmpeg` command that encodes H.264 with `-pix_fmt yuv420p` and publishes `stream1` to the camera over `sim_ctrl`. 4:2:0 is the only H.264 format browsers decode. The Orin reads the stream as `rtsp://192.168.10.20:8554/stream1`.

The pipeline SHALL NOT be written as a folded YAML `command:`. In the guide's version, the line breaks split ffmpeg's encoder and output options into separate shell commands, and no stream was published.

#### Scenario: Budget camera pose comes from the profile
- **WHEN** the world renders the budget profile
- **THEN** the standoff is the solved 12.42 m, the field of view and frame size come from the fitted camera and `sites/budget.yaml`, and the frame carries the camera height as the one unconfirmed site input

## ADDED Requirements

### Requirement: Rendering a pole with no floodlight
Where a profile fits no `floodlight`, the world SHALL render night scenes lit only by what is fitted — the camera's own IR illuminator on the budget pole — and SHALL NOT fall back to a default lamp.

The night render's metadata SHALL record that no floodlight is fitted, so a night image from the budget pole is not mistaken for one from a lit pole.

#### Scenario: Budget pole at night
- **WHEN** a night preset renders on the budget profile
- **THEN** the scene is lit by the camera's IR range alone, and the metadata says no floodlight is fitted

#### Scenario: Floodlight presets on an unlit pole
- **WHEN** a weather preset that switches the floodlight on runs on the budget profile
- **THEN** the render completes with no floodlight contribution and the preset's report says the pole carries none
