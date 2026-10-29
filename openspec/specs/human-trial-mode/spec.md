# human-trial-mode Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Trial session
`python3 -m tools.trial` SHALL let a person walk a worker with the keyboard. Each frame runs the tested code path:
1. person boxes from the picture
2. the homography, giving the distance to the pit edge
3. `app/alarm.py`
4. the laser aim from `app/links.py`

Options:
- `--weather <preset>`
- `--camera <product>`
- `--npcs <n>`
- `--miss-rate <0..1>`
- `--delay-ms <ms>`

It SHALL use the products in `site.yaml` unless one is overridden. It SHALL use pygame when installed, and an OpenCV window otherwise.

#### Scenario: Weaker detector
- **WHEN** `python3 -m tools.trial --miss-rate 0.1 --delay-ms 200` runs
- **THEN** detections are dropped in 10% of frames and arrive 200 ms late

### Requirement: Key map
The trial SHALL use this key map:

| Keys | Action |
|---|---|
| Arrows or W A S D | walk; Up walks away from the camera, as on screen; diagonals work |
| Shift | run |
| N / Tab | add a worker / switch between workers |
| R | reset the workers and the alarm |
| E | cycle the 16 weather presets without restarting |
| Z / P | show or hide the zone rings / pause |
| Q or Esc | quit and print the scorecard |

The walking speed SHALL be 1.4 m/s and the running speed 3.0 m/s.

#### Scenario: Trial keys (V29)
- **WHEN** a headless trial session (no window) holds Up, then Right, then Right with Shift
- **THEN** Up moves the worker up the picture, and Right moves it right in the picture
- **AND** the measured speeds are 1.4 m/s walking and 3.0 m/s running, each within 2%

### Requirement: Trial display
The screen SHALL show:
- the pole camera's view, with the fitted products and the chosen weather
- a top bar with the true distance to the edge, the distance the app sees, the time in the zone, and whether the horn, strobe and laser are on
- a plan view in the corner, with the pole, both rings and the laser beam

#### Scenario: Top bar values
- **WHEN** the worker stands 1.0 m from the pit edge with the laser on
- **THEN** the top bar shows a true distance of 1.0 m, the app's distance, the time in the zone, and the laser on

### Requirement: Scorecard
On quit, the trial SHALL save every entry into the 1.5 m zone to `logs/trial-<time>.json`. Each entry SHALL record:
- how long the worker stayed
- the warning and alarm times after entering
- the reset time after leaving
- the laser dot's distance from the feet

#### Scenario: Keyboard walk-in (V30)
- **WHEN** keys steer the worker into the zone on a clear day, with the default 120 ms detector delay
- **THEN** the scorecard shows exactly one caution, warning, alarm and reset
- **AND** the warning comes about 1 s after entering (1.0 s plus up to 0.25 s of detector delay; 1.13 s measured), and the alarm about 3 s after (3.2 s measured)

#### Scenario: Walk out (V32)
- **WHEN** the worker leaves the zone
- **THEN** the reset comes about 2 s after leaving (2.0 s plus up to 0.25 s; 2.2 s measured), and the laser is parked and off

#### Scenario: Laser on the feet (V31)
- **WHEN** the same walk-in is scored
- **THEN** the median distance from the laser dot to the feet is within 0.5 m (0.27 m measured)

### Requirement: Network key sender
`python3 -m tools.trial --send <host>:9200` SHALL open a small keypad window and send the held keys over UDP about 10 times a second to a world started with `--control`.

Because the control port is published only on the twin host's loopback, the sender SHALL be run on the twin host itself. Remote users drive the worker through the dashboard's trial pad.

#### Scenario: Keys over the network (V34)
- **WHEN** `send_keys` sends held Up keys to a world control server
- **THEN** the worker moves up the picture, and stops within 0.5 s (+ one frame) of the last message

