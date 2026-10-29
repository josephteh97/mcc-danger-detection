# alarm-app Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Zone configuration
The app SHALL read the pit outline, the zone buffers and the timings from `app/config.yaml`. Defaults:
- Pit: polygon `[[-1.2,-0.8],[1.2,-0.8],[1.2,0.8],[-1.2,0.8]]` in metres.
- `alarm_buffer_m: 1.5` (the zone) and `warn_buffer_m: 3.0` (the caution ring).
- `dwell_s: 1.0`, `escalate_s: 3.0` and `clear_s: 2.0`.

On site, only the camera URL, the device paths and the calibration file SHALL change. The app code SHALL NOT change.

#### Scenario: Defaults load
- **WHEN** the app starts with the twin's `app/config.yaml`
- **THEN** the alarm configuration is: alarm buffer 1.5 m, warning ring 3.0 m, dwell 1.0 s, escalation 3.0 s, clear 2.0 s

#### Scenario: Swapping a simulated device for a real one
- **WHEN** `devices.arm` in `app/config.yaml` changes from `/dev/ttyARM` to `/dev/ttyUSB0`
- **THEN** the app drives the device on the new path with no change to any file in `app/` except `config.yaml`

### Requirement: Foot point to ground position
The app SHALL take the bottom-centre of each person's box as the foot pixel. It SHALL map that pixel to ground metres with the image-to-ground homography loaded from `camera.homography`.

`ground_from_image(H, u, v)` SHALL be a pure function.

#### Scenario: Foot position accuracy at 9 m (V05)
- **WHEN** a worker stands about 9 m from the camera in a rendered clear-day frame, and their box's bottom-centre is mapped through the calibrated homography
- **THEN** the mapped position is less than 0.35 m from the worker's true ground position
- **AND** the measured bias, about 0.3 m toward the camera, is reported (first finding)

#### Scenario: Homography round trip
- **WHEN** four ground points with known positions are projected to pixels and the fitted homography maps those pixels back to the ground
- **THEN** every point is recovered within 0.01 m

### Requirement: Distance to the pit edge
The app SHALL compute each person's distance to the nearest edge of the pit polygon in metres. A point inside the pit SHALL have distance 0.

`edge_distance(x, y, pit)` SHALL be a pure function.

#### Scenario: Point inside the pit
- **WHEN** a ground point lies inside the pit polygon
- **THEN** its edge distance is 0

#### Scenario: Point beside the pit
- **WHEN** a ground point lies 1.0 m outside the middle of the pit's long edge
- **THEN** its edge distance is 1.0 m within 1 mm

#### Scenario: Point off a corner
- **WHEN** a ground point lies 1.0 m east and 1.0 m north of the pit's north-east corner
- **THEN** its edge distance is √2 m within 1 mm

### Requirement: Alarm state machine
The app SHALL run an alarm state machine, `AlarmFSM`, that turns per-person edge distances into events.

Levels:
- 0, Monitoring.
- 1, Warning.
- 2, Alarm.

Events:
- **Caution:** emitted once per person when they first come within the 3.0 m ring.
- **Warning:** emitted when a person has been continuously within the 1.5 m zone for `dwell_s` (1.0 s). The level becomes at least 1.
- **Alarm:** emitted when a person has been within the 1.5 m zone for `escalate_s` (3.0 s), counted from when they entered. The level becomes 2.
- **Reset:** emitted when no person has been within the 1.5 m zone for `clear_s` (2.0 s) after the level was 1 or higher. The level returns to 0.

Timings SHALL be measured on a monotonic clock. A level SHALL be reached within one frame (1/15 s at 15 fps) of its set time.

#### Scenario: Alarm sequence on a walk-in (V01)
- **WHEN** a scripted worker walks from outside the 3 m ring into the 1.5 m zone, stays 5 s and walks out, with ground-truth distances at 15 fps
- **THEN** the events are exactly one each of caution, warning, alarm and reset, in that order

#### Scenario: Warning timing (V02)
- **WHEN** a worker enters the 1.5 m zone at time T and stays
- **THEN** the warning event is emitted at T + 1.0 s, within one frame

#### Scenario: Escalation timing (V03)
- **WHEN** a worker enters the 1.5 m zone at time T and stays
- **THEN** the alarm event is emitted at T + 3.0 s, within one frame

#### Scenario: No false alarm at the edge (V04)
- **WHEN** a worker stands 1.6 m from the pit edge for 20 s
- **THEN** exactly one caution is emitted, and no warning, alarm or reset

#### Scenario: Reset after leaving
- **WHEN** the only person in the zone leaves the 1.5 m zone at time T and no one re-enters
- **THEN** the reset event is emitted at T + 2.0 s, within one frame, and the level is 0

### Requirement: Track persistence through missed detections
The state machine SHALL keep a person, with their caution flag and zone entry time, for `clear_s` (2.0 s) after that person was last seen. A person missing from a few frames SHALL NOT be cautioned again and SHALL NOT restart their dwell timer. This is the fifth finding.

#### Scenario: Detector misses 1 frame in 10
- **WHEN** a single walk-in is run with a detector that misses 10% of frames at random
- **THEN** exactly one caution, one warning, one alarm and one reset are emitted

### Requirement: Multiple workers
The state machine SHALL track each person separately.
- The level SHALL be the highest level any person justifies.
- Reset SHALL be emitted only once every person has been clear of the 1.5 m zone for `clear_s`.

#### Scenario: Two workers, one inside (V15)
- **WHEN** worker A stands inside the 1.5 m zone and worker B stands 2.5 m from the edge
- **THEN** the laser is aimed at worker A's feet, not worker B's

#### Scenario: Alarm clears only when both are clear (V15)
- **WHEN** two workers are inside the 1.5 m zone and one of them leaves
- **THEN** no reset is emitted until the second worker has also been out of the zone for 2.0 s

### Requirement: Actuation
For each event, the app SHALL drive the outputs as follows:
- **Caution:** a short chime on the `horn` audio sink.
- **Warning:** a warning tone on the horn, laser module power on (relay channel 3), and laser aiming at the feet.
- **Alarm:** the alarm siren on the horn, strobe on (relay channel 1), the identify step run on the person, and the event queued for the cloud.
- **Reset:** horn silent, strobe off, laser off and arm parked, laser module power off, and the event queued for the cloud.

Every event (caution, warning, alarm and reset) SHALL be queued for the cloud with its kind, person ID, level, distance and wall-clock time.

The floodlight (relay channel 2) SHALL be switched on from 19:00 to 07:00 local time.

#### Scenario: Horn and strobe on alarm
- **WHEN** an alarm event is emitted
- **THEN** sound plays on the `horn` sink, and the relay board receives `R 1 1`

#### Scenario: Outputs off on reset
- **WHEN** a reset event is emitted
- **THEN** the horn stops, the relay board receives `R 1 0` and `R 3 0`, and the arm receives `PARK`

### Requirement: Laser aiming
While the level is 1 or higher and at least one person is within the 1.5 m zone, the app SHALL aim the arm at the feet of the person nearest the pit edge and request the laser on.

`aim_angles(arm_xy, heading_deg, pivot_h_m, target_xy)` SHALL be a pure function that returns:
- **Pan:** degrees from the arm's forward direction, counter-clockwise positive, on the same axes as the site's ground coordinates.
- **Tilt:** degrees below horizontal.

At all other times, the app SHALL send `HB` and `PARK` every frame. The laser SHALL NOT be requested while no one is within the 1.5 m zone.

#### Scenario: Aim angles for a known target
- **WHEN** the arm is at (-6.0, 3.6), heading -30°, with its pivot 1.1 m high, and the target is at (0, 0)
- **THEN** pan is -0.96° and tilt is 8.93°, each within 0.01°

#### Scenario: Laser dot on the feet (V31)
- **WHEN** a worker is in the zone at level 1 or higher in a clear-day trial run
- **THEN** the laser dot lands within 0.5 m of the worker's true feet, by median over the run

### Requirement: Offline uplink queue
The app SHALL send cloud events through an on-disk queue (`Uplink`, a SQLite file on `/data`) to the MQTT topic `pole/<id>/event`.
- An event SHALL be removed from the queue only after the broker acknowledges it (QoS 1).
- Events SHALL be sent in the order they were queued.
- Events SHALL survive an app restart.

#### Scenario: Events survive a 4G outage (V09)
- **WHEN** the uplink is cut, five events are queued, and the link is restored
- **THEN** no event is delivered while the link is down
- **AND** all five are delivered after it returns, in their original order, with no duplicates

#### Scenario: Weak 4G
- **WHEN** the 4G link has 120 ms ± 40 ms delay and 5% loss
- **THEN** every event still arrives at the broker

### Requirement: Detector modes
The app SHALL support two detector modes, selected by `detector.mode`:
- **`oracle`** reads ground-truth person boxes from UDP (`detector.oracle_udp`). It applies a configurable delay (default 120 ms), jitter and miss rate (default 0.02), and removes the true IDs so the tracker is exercised.
- **`yolo`** runs an ONNX or TensorRT person detector on the camera frame.

#### Scenario: Oracle delay
- **WHEN** the oracle detector runs with `oracle_delay_ms: 120`
- **THEN** each box is available to the app 120 ms (± jitter) after the frame's ground truth was sent

### Requirement: Person tracker
The app SHALL keep one ID per person across frames, using an IoU tracker, so that each dwell timer belongs to one person.

#### Scenario: Stable IDs on a walk
- **WHEN** one worker walks across the site with no missed detections
- **THEN** the tracker reports one ID for the whole walk

### Requirement: Health alerts
The app SHALL detect when the camera or the arm stops responding, and SHALL keep working with whatever devices are still connected.

- **Camera offline:** when no frame has arrived for 3 s, the app SHALL raise a "camera offline" health alert, queue it for the cloud, and keep trying to reopen the stream.
- **Arm offline:** when the arm's serial port disappears or stops reporting `POS`, the app SHALL log "arm offline". The horn and strobe SHALL keep working.

#### Scenario: Camera cable cut (V14)
- **WHEN** the camera is disconnected from `poe_lan` while the app is running
- **THEN** a "camera offline" health alert is queued within 10 s

#### Scenario: Laser arm USB unplugged
- **WHEN** the arm's serial bridge is killed
- **THEN** the app logs "arm offline"
- **AND** on the next walk-in the horn and strobe still fire

### Requirement: Recovery after power loss
After a restart, the app SHALL return to Monitoring with the same zone settings, read from `config.yaml` and from the calibration file on the persistent `/data` volume.

#### Scenario: Restart after a power cut (V16)
- **WHEN** the Orin container is killed and started again
- **THEN** the app is in Monitoring within 60 s, with the same pit, buffers and homography as before

### Requirement: End-to-end alarm latency
In the full stack, using the oracle detector with 120 ms delay, horn sound for the warning SHALL start within 1.5 s after the person crossed into the 1.5 m zone plus the 1.0 s dwell. Sound start is measured at the `horn` sink monitor.

#### Scenario: Latency at the horn (V12)
- **WHEN** a scripted worker crosses into the 1.5 m zone at time T in the full stack
- **THEN** the horn monitor records the warning sound starting no later than T + 1.0 s + 1.5 s

