## MODIFIED Requirements

### Requirement: Key map
The trial SHALL use this key map:

| Keys | Action |
|---|---|
| Arrows or W A S D | walk; Up walks away from the camera, as on screen; diagonals work |
| Shift | run |
| C | squat or stand up |
| K | kneel or stand up |
| N / Tab | add a worker / switch between workers |
| R | reset the workers and the alarm |
| E | cycle the 16 weather presets without restarting |
| Z / P | show or hide the zone rings / pause |
| Q or Esc | quit and print the scorecard |

The walking speed SHALL be 1.4 m/s and the running speed 3.0 m/s. A squatting or kneeling worker SHALL NOT move until it stands up.

#### Scenario: Trial keys (V29)
- **WHEN** a headless trial session (no window) holds Up, then Right, then Right with Shift
- **THEN** Up moves the worker up the picture, and Right moves it right in the picture
- **AND** the measured speeds are 1.4 m/s walking and 3.0 m/s running, each within 2%

#### Scenario: Squat key
- **WHEN** a headless trial session presses C inside the 3 m ring
- **THEN** the worker's posture becomes squat, its box height drops to 1.0 m, and the alarm still fires after the dwell time
