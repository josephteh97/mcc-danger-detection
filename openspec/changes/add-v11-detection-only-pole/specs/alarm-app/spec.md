## MODIFIED Requirements

### Requirement: Actuation
For each event, the app SHALL drive the outputs as follows:
- **Caution:** a short chime on the `horn` audio sink.
- **Warning:** a warning tone on the horn, laser module power on (relay channel 3), and laser aiming at the feet.
- **Alarm:** the alarm siren on the horn, strobe on (relay channel 1), the identify step run on the person when `identify.enabled` is true (always in the phase-1 profile, off by default in the `v11` profile), and the event queued for the cloud.
- **Reset:** horn silent, strobe off, laser off and arm parked, laser module power off, and the event queued for the cloud.

Every event (caution, warning, alarm and reset) SHALL be queued for the cloud with its kind, person ID, level, distance and wall-clock time.

The floodlight (relay channel 2) SHALL be switched on from 19:00 to 07:00 local time.

In the `v11` profile the relay and arm lines SHALL travel over TCP to the laser controller (see `orin-sandbox`); the commands and replies are unchanged.

#### Scenario: Horn and strobe on alarm
- **WHEN** an alarm event is emitted
- **THEN** sound plays on the `horn` sink, and the relay board receives `R 1 1`

#### Scenario: Outputs off on reset
- **WHEN** a reset event is emitted
- **THEN** the horn stops, the relay board receives `R 1 0` and `R 3 0`, and the arm receives `PARK`

#### Scenario: No identify step in v11
- **WHEN** an alarm event is emitted with `app/config.v11.yaml`
- **THEN** the horn, strobe and cloud event behave as above and no identify step runs

### Requirement: Detector modes
The app SHALL support two detector modes, selected by `detector.mode`:
- **`oracle`** reads ground-truth person boxes from UDP (`detector.oracle_udp`). It applies a configurable delay (default 120 ms), jitter and miss rate (default 0.02), and removes the true IDs so the tracker is exercised. With `detector.miss_model: pixel_height` (the `v11` default) the miss rate SHALL instead depend on the person's height in the processed image: 0.02 at 100 px or more, rising linearly to 0.5 at 50 px, and 1.0 below 30 px, then multiplied by the weather preset's contrast factor.
- **`yolo`** runs an ONNX or TensorRT person detector on the camera frame. With `detector.tiles: true` it SHALL run on full-resolution tiles covering the zone region instead of one downscaled frame.

#### Scenario: Oracle delay
- **WHEN** the oracle detector runs with `oracle_delay_ms: 120`
- **THEN** each box is available to the app 120 ms (± jitter) after the frame's ground truth was sent

#### Scenario: Small person missed more often
- **WHEN** the pixel-height miss model sees a squatting worker 60 px tall in the processed image
- **THEN** about 40% of that worker's frames are dropped, and a worker 120 px tall is dropped in about 2%
