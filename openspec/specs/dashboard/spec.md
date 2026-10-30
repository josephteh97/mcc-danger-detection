# dashboard Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Dashboard server
The dashboard SHALL be a FastAPI server on port 8080, published on the host's loopback interface only. It SHALL serve one page with three panels: the 3D view with camera video, Scenarios, and Faults.

#### Scenario: Dashboard loads
- **WHEN** a browser opens `http://localhost:8080` while the stack is running
- **THEN** the page shows the 3D view, the live camera video, the scenario and weather controls, the products panel and the fault buttons

### Requirement: Live state feed
The dashboard SHALL collect and merge live state into one object:
- the world's ground truth, from UDP port 9100
- the arm state, from `/logs/arm.jsonl`
- the relay state, from `/logs/relay.jsonl`
- the app's events, from MQTT topic `pole/+/event` on the cloud broker

It SHALL push that object to every client on the `/live` WebSocket about 15 times a second.

#### Scenario: Live updates
- **WHEN** a client connects to `/live` while a worker walks
- **THEN** it receives about 15 messages a second, carrying the worker's position, the arm angles and laser state, the strobe and floodlight state, and the latest alarm events

### Requirement: 3D view
The page SHALL render a three.js model of the site, driven by the live feed. The model SHALL show:
- the pit, the 1.5 m and 3 m rings and the pole (phase 1) or wheeled stand with its solar skid in Plans B and C (v11)
- the camera's true field of view as a frustum from the fitted lens
- the workers at their true positions, as rigged figures in their posture
- the arm and laser beam at their reported angles, with a glow on the beam and dot
- the strobe and floodlight state, with a visible floodlight cone at night
- the current alarm level

It SHALL also provide:
- physically based materials, tone mapping, a sky and sun that follow the time of day, and soft shadows from the sun
- rain particles, wet ground and haze from the active weather preset
- a switchable px/m heatmap on the ground (green ≥ 100, amber 60–100, red < 60 px/m, in the processed image)
- HUD panels for alarm state and dwell timer, battery charge and plan, PoE used/reserved/budget, 4G uplink and month-to-date data, and active faults
- quality presets (low, medium, high); the medium preset SHALL keep at least 30 frames per second at 1920×1080 on integrated graphics

New three.js add-ons SHALL be vendored and pinned like the existing vendor files.

#### Scenario: Worker moves in 3D
- **WHEN** a worker walks in the world
- **THEN** the worker's marker in the 3D view follows the true position, with at most 0.2 s of lag

#### Scenario: Heatmap matches coverage maths
- **WHEN** the heatmap is on in the v11 profile
- **THEN** the colour at each ring corner matches the band computed by `tools/coverage.py` for that point

#### Scenario: Low preset still usable
- **WHEN** the low preset is chosen
- **THEN** shadows, rain particles and bloom are off and the view still shows every item in the list above

### Requirement: Browser video stream
The page SHALL play the camera's live video in the browser. The dashboard SHALL reverse-proxy MediaMTX's HLS output from the camera service under `/video/` on port 8080, so the video needs no RTSP client and no port other than 8080.

#### Scenario: Video plays from the dashboard origin
- **WHEN** the page loads
- **THEN** the camera stream plays in a standard browser from `/video/stream1/index.m3u8` on the same origin

### Requirement: Scenario runner
The page SHALL provide buttons that start these scripted scenarios in the world:
- single walk-in
- two workers at once
- passer-by on the ring edge
- worker who stops 1.6 m away
- a worker hidden behind another

It SHALL also provide a weather menu with all 16 presets. Choosing a preset SHALL switch the world to it within 5 s.

#### Scenario: Start a scenario
- **WHEN** the user clicks "single walk-in"
- **THEN** the world resets its workers and runs the single walk-in script, and the 3D view and video show it

#### Scenario: Change the weather
- **WHEN** the user picks `night_rain` from the weather menu
- **THEN** the video shows the night rain preset within 5 s, and the live state reports `night_rain`

### Requirement: Products panel
The page SHALL let the user pick any catalogue product for each category, and show the comparison table and picture grid that `tools.compare` produces for the chosen products.

#### Scenario: Compare cameras in the browser
- **WHEN** the user selects two cameras and two weather presets and asks for a comparison
- **THEN** the panel shows the comparison table and the picture grid

### Requirement: Fault buttons
The page SHALL have one button per fault, each with a matching restore button. The faults are:
- camera cable
- 4G weak
- 4G outage
- arm USB
- Orin hang
- power cut

The buttons SHALL call the Docker API through the mounted Docker socket, doing exactly what the fault commands do. A fault request SHALL return a JSON result naming the fault and whether it succeeded. Unknown fault names SHALL be rejected with HTTP 404.

#### Scenario: Orin hang button
- **WHEN** the user clicks "Orin hang"
- **THEN** the orin container is paused, and the response is `{"ok": true, "fault": "orin_hang"}`

#### Scenario: Unknown fault
- **WHEN** a client posts to `/fault/format_disk`
- **THEN** the dashboard responds 404 and runs nothing

### Requirement: Run recording
The dashboard SHALL record every run to `/logs/run-<time>/`: ground truth, app events and device logs. A recorded run SHALL be replayable in the 3D view frame by frame.

#### Scenario: Replay a failed run
- **WHEN** the user opens a recorded run
- **THEN** the 3D view steps through it frame by frame with the recorded truth, arm state and events

### Requirement: Trial pad
The page SHALL offer a Human trial pad: the keyboard arrows, or on-screen arrow buttons on a phone, plus Shift to run. The dashboard SHALL relay the held keys over UDP to the world's control port, inside the twin, about 10 times a second, so the worker in the video walks and the real Orin app raises the alarm.

When the browser stops sending, the worker SHALL stop through the world's 0.5 s rule.

#### Scenario: Remote walk-in through the dashboard
- **WHEN** a viewer holds the Up arrow on the trial pad until the worker is inside the 1.5 m zone, then waits, then walks out
- **THEN** the dashboard shows caution, then warning, then alarm, then reset from the app's events

#### Scenario: Browser tab closed mid-walk
- **WHEN** the viewer closes the tab while holding a key
- **THEN** the worker stops within 0.5 s (+ one frame)

