## MODIFIED Requirements

### Requirement: Orin-shaped container
The `orin` container SHALL match the AI box of the active profile as the app sees it.

For phase 1 and version 11, the Orin:
- 6 CPUs and 8 GB of memory
- a persistent `/data` volume (the SSD)
- serial devices at `/dev/ttyARM` and `/dev/ttyRELAY` (phase 1 only; version 11 reaches the laser controller over Ethernet)
- a PulseAudio null sink named `horn`
- one network interface on the PoE LAN (`192.168.10.2`) and one on 4G (`172.30.4.2`)

For the budget profile the box is a Raspberry Pi 5 8 GB and the container SHALL be shaped to it instead:
- 4 CPUs and 8 GB of memory
- the same persistent `/data` volume
- no `/dev/ttyARM` or `/dev/ttyRELAY`: the aim controller is on Ethernet and the interlock is hardwired, outside the app's reach by design
- the same PulseAudio null sink named `horn`
- one interface on the PoE LAN and one standing in for the USB 4G modem, so the app sees an uplink on the box itself rather than through a router

The app SHALL see nothing else of the twin. The app image SHALL stay the shipping image; only its limits, devices and config path change with the profile.

#### Scenario: Device paths and interfaces
- **WHEN** the orin container is running on phase 1
- **THEN** `/dev/ttyARM` and `/dev/ttyRELAY` exist, `pactl list short sinks` shows `horn`, and the container has addresses 192.168.10.2 and 172.30.4.2

#### Scenario: Resource limits
- **WHEN** the orin container is inspected on phase 1 or v11
- **THEN** it is limited to 6 CPUs and 8 GB of memory

#### Scenario: Pi-shaped sandbox
- **WHEN** the orin container is inspected on the budget profile
- **THEN** it is limited to 4 CPUs and 8 GB of memory, has no `/dev/ttyARM` or `/dev/ttyRELAY`, and still exposes the `horn` sink

#### Scenario: The app runs unchanged
- **WHEN** the sandbox starts on the budget profile
- **THEN** it execs `app/config.budget.yaml` and no app source file differs from the one phase 1 runs

## ADDED Requirements

### Requirement: The interlock is outside the app
Where a profile fits a `controller` with `breaks_laser_supply: true`, the twin SHALL model that device as breaking the laser's supply in hardware, reachable by neither the app nor any emulator.

The app SHALL have no command that closes it, and no fault SHALL be able to bypass it. A test that needs the laser dark SHALL open the interlock and assert the app cannot light the laser, rather than asserting the app chose not to.

This is a laser safety rule: on the budget pole the key switch and tilt switch sit in series with the laser's 5 V supply, so software cannot fire the laser when they are open.

#### Scenario: Interlock open
- **WHEN** the budget profile's interlock is open and the app commands the laser on
- **THEN** the laser stays dark and the app's own state records the command as issued but unconfirmed

#### Scenario: No software override exists
- **WHEN** the app's command surface is inspected on the budget profile
- **THEN** it carries no command that closes the interlock
