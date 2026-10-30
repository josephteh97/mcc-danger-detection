## MODIFIED Requirements

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
