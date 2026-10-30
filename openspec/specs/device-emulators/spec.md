# device-emulators Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Laser arm serial protocol
The arm emulator (`devices/arm_emulator.py`) SHALL speak a newline-terminated ASCII line protocol on a pseudo-serial port, given by `--link`. It defines the protocol the real ESP32 firmware must implement.

Orin to arm:
- `AIM <pan> <tilt>`: pan in degrees from the arm's forward direction; tilt in degrees below horizontal.
- `LASER <0|1>`: request the laser off or on.
- `HB`: heartbeat, sent at least every 2 s.
- `PARK`: point down with the laser off.

Arm to Orin:
- `POS <pan> <tilt> <laser_on>`: the actual servo angles and laser state, every 50 ms.

The emulator SHALL ignore unknown or malformed lines without crashing. It SHALL append its state to the JSONL file given by `--state` (for example `/logs/arm.jsonl`).

#### Scenario: Position reports
- **WHEN** the arm emulator is running and connected
- **THEN** it emits a `POS` line every 50 ms (± 10 ms) with its current pan, tilt and laser state

#### Scenario: Malformed input
- **WHEN** the Orin sends `AIM banana`
- **THEN** the emulator ignores the line and keeps reporting `POS`

### Requirement: Servo slew
The emulator SHALL move each servo toward its commanded angle at no more than 180°/s.

#### Scenario: Slew rate
- **WHEN** the arm at pan 0° is commanded to `AIM 90 10`
- **THEN** the reported pan reaches 90° no sooner than 0.5 s and no later than 0.6 s after the command

### Requirement: Laser aims and fires
The emulator SHALL turn the laser on when all three hold:
- `LASER 1` was the most recent laser request.
- The heartbeat has not lapsed.
- The tilt interlock allows it.

#### Scenario: Laser aims and fires (V07)
- **WHEN** the arm link sends `AIM 20 8`, `LASER 1` and regular `HB`
- **THEN** the reported angles converge to pan 20° and tilt 8° within 0.5° and the reported laser state is 1

### Requirement: Tilt interlock
The laser SHALL be on only while the arm's actual tilt is at least 1° below horizontal, whatever the software requests. This is a laser safety rule.

#### Scenario: Laser interlock (V06)
- **WHEN** the arm is commanded to `AIM 0 -5` (above horizontal) with `LASER 1` and regular heartbeats
- **THEN** the reported laser state stays 0

#### Scenario: Interlock while slewing up
- **WHEN** the laser is on at tilt 8° and the arm is commanded to tilt 0.5°
- **THEN** the laser turns off as the actual tilt passes 1° below horizontal

### Requirement: Heartbeat watchdog
If no `HB` (or other valid command) arrives for 2 s, the emulator SHALL turn the laser off immediately and park the arm: pan 0° and tilt 90° below horizontal, reached at the slew rate. The laser SHALL stay off until a new `LASER 1` arrives after heartbeats resume. This is a laser safety rule.

#### Scenario: Laser watchdog (V08)
- **WHEN** the laser is on and heartbeats stop at time T
- **THEN** the reported laser state is 0 no later than T + 2.0 s (+ one 50 ms report period)
- **AND** the arm is moving to the park pose at that point, and reaches it within the slew time

#### Scenario: Recovery after watchdog
- **WHEN** heartbeats resume after a watchdog park
- **THEN** the laser stays off until a new `LASER 1` is received

### Requirement: Park command
On `PARK`, the emulator SHALL turn the laser off and slew to the park pose (pan 0°, tilt 90°).

#### Scenario: Park
- **WHEN** the arm receives `PARK` while lasing
- **THEN** the laser state is 0 in the next `POS` report and the angles converge to pan 0° and tilt 90°

### Requirement: Relay board emulator
The relay emulator (`devices/relay_emulator.py`) SHALL accept `R <channel> <0|1>` lines on its pseudo-serial port (phase 1) or on TCP port 7002 at the laser controller's address `192.168.10.24` (v11), and acknowledge each with `OK <channel> <0|1>`.

Channels:
- 1: strobe.
- 2: floodlight.
- 3: laser power.
- 4: spare.

An invalid channel or value SHALL be answered with `ERR`. The emulator SHALL append each state change to a JSONL log given by `--state` (for example `/logs/relay.jsonl`).

The app's relay driver SHALL keep the line protocol behind a small adapter, so that on site only the adapter changes to the real board's 4-byte hex frames or the ESP32 laser controller's network protocol.

#### Scenario: Relay protocol
- **WHEN** the app sends `R 1 1`
- **THEN** the emulator replies `OK 1 1` and logs the strobe as on

#### Scenario: Bad channel
- **WHEN** the app sends `R 9 1`
- **THEN** the emulator replies `ERR` and no channel changes

#### Scenario: Relay over Ethernet
- **WHEN** the v11 app sends `R 1 1` over TCP to `192.168.10.24:7002`
- **THEN** the emulator replies `OK 1 1` exactly as over the serial port

### Requirement: Horn sink and sound monitor
The Orin sandbox SHALL provide a PulseAudio null sink named `horn`. A horn monitor SHALL read `horn.monitor` and, each time sound starts, print the wall-clock time and `SOUND`. Sound starts when a 4410-byte block's peak sample exceeds 500, with 0.5 s of hold-off between reports.

#### Scenario: Sound start logged
- **WHEN** the app plays the warning tone on the `horn` sink
- **THEN** the monitor prints a timestamped `SOUND` line within 0.1 s of the start of playback

### Requirement: Power model
The power model (`devices/power_model.py`) SHALL step the battery's state of charge hourly, with a `--profile` option (`phase1`, the default, or `v11`). The phase-1 defaults SHALL stay as follows:
- **Load:** 33 W around the clock (AI box, camera, switch, modem and idle devices), plus 30 W of floodlight from 19:00 to 07:00. That is 1,152 Wh a day.
- **Solar:** 500 W of panels, 4 peak sun hours on an average day, 70% system efficiency (1,400 Wh a day at sun factor 1.0), spread over daylight 07:00–19:00, multiplied by the weather's sun factor.
- **Battery:** 25.6 V × 100 Ah, so 2.56 kWh.
- **Product overrides:** battery, panels, floodlight and AI box, from the fitted catalogue products.

The `v11` profile SHALL take its loads, conversion losses, power plans, battery monitor alerts and shutdown stages from the `pole-network-power` capability, using the same solar model.

A run SHALL start at 19:00 with the battery full, after a clear day. An N-day run SHALL cover N daylight periods of the given weather and the nights around them. The run SHALL report the lowest state of charge, clipped at 0%, which is reported as "runs flat". The 10% floor SHALL be the pass threshold.

#### Scenario: Two heavily overcast days (V10)
- **WHEN** the model runs 2 days at 30% of normal sun with the planned battery and panels
- **THEN** the lowest charge stays above 10%: 12% ± 2 points

#### Scenario: Three heavily overcast days (V11, known fail)
- **WHEN** the model runs 3 days at 30% of normal sun with the planned battery and panels
- **THEN** the battery runs flat, so V11's "stays above 10%" check fails, which is the second finding

#### Scenario: Mitigation options
- **WHEN** the model runs 3 days at 30% sun for each option
- **THEN** the lowest charge is within ± 2 points of the guide:
  - floodlight off: 40%
  - 1,000 W of panels: 33%
  - a second battery (5.1 kWh): 42%

#### Scenario: Clear days
- **WHEN** the model runs 3 clear days
- **THEN** the lowest charge is 70% ± 2 points

#### Scenario: v11 profile selected
- **WHEN** the model runs with `--profile v11 --plan B`
- **THEN** it uses the v11 loads with 1,000 W of panels and a 200 Ah battery, and the phase-1 results above are unchanged when run without `--profile`

