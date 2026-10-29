# virtual-cables Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Compose stack
`compose.yaml` SHALL define the Compose project `twin` with these six services:

| Service | What it is | Networks and address |
|---|---|---|
| `camera` | MediaMTX RTSP and HLS server | `poe_lan` at `192.168.10.20`, and `sim_ctrl` for the dashboard's browser video |
| `world` | renderer piped to ffmpeg; pushes the camera's sensor feed to the camera's `sim_ctrl` address and sends oracle truth to the Orin over `poe_lan` | `poe_lan` and `sim_ctrl` |
| `devices` | arm and relay emulators, with socat TCP bridges on 7001 and 7002 | `usb_bus` |
| `orin` | the sandbox, with `NET_ADMIN` for tc | `poe_lan` at `192.168.10.2`, `usb_bus`, and `wan_4g` at `172.30.4.2` |
| `cloud` | Mosquitto on port 1883 | `wan_4g` at `172.30.4.10` |
| `dashboard` | the FastAPI dashboard | `sim_ctrl` and `wan_4g` |

The image tags for MediaMTX and Mosquitto SHALL be pinned to specific releases. Fixed addresses SHALL sit outside each network's dynamic `ip_range`, so a container without a fixed address can never take one.

`docker compose up --build` SHALL bring the stack up, with the dashboard on `http://localhost:8080`.

#### Scenario: Stack comes up
- **WHEN** `docker compose up -d --build` runs on a host that meets the setup prerequisites
- **THEN** all six services are running, and `http://localhost:8080` returns the dashboard within 60 s

#### Scenario: Fixed addresses never collide
- **WHEN** the stack starts in any container order
- **THEN** the camera gets 192.168.10.20, the Orin gets 192.168.10.2 and 172.30.4.2, and the cloud gets 172.30.4.10

### Requirement: Isolated cable networks
`poe_lan` (`192.168.10.0/24`), `usb_bus` and `wan_4g` (`172.30.4.0/24`) SHALL be internal Docker networks, so nothing on them reaches the real internet. `sim_ctrl` is the twin's own control network.

Only these host ports SHALL be published:
- `127.0.0.1:8080`, the dashboard
- `127.0.0.1:9200/udp`, the world control port for a local `tools.trial --send`

MQTT (1883), RTSP (8554), HLS (8888), the serial bridges (7001 and 7002) and truth (9100) SHALL NOT be published to the host.

#### Scenario: Orin cannot reach the internet
- **WHEN** the orin container tries to connect to a public address
- **THEN** the connection fails

#### Scenario: Only the dashboard and loopback control are published
- **WHEN** `docker compose ps --format json` is inspected
- **THEN** the only published ports are `127.0.0.1:8080->8080/tcp` and `127.0.0.1:9200->9200/udp`

### Requirement: Fault injection commands
Each physical cable SHALL be something that can be cut on command. The commands below, used directly or through the dashboard, SHALL produce the expected behaviour.

| Fault | Command | Expected behaviour |
|---|---|---|
| Camera cable unplugged | `docker network disconnect twin_poe_lan twin-camera-1` | "camera offline" alert within 10 s |
| 4G weak | `tc qdisc add dev $WAN root netem delay 120ms 40ms loss 5%` | events still arrive, a little later |
| 4G outage | netem with `loss 100%`, restored with `tc qdisc del dev $WAN root` | events arrive in order after restore |
| Laser arm USB unplugged | `docker exec twin-devices-1 pkill -f TCP-LISTEN:7001` | "arm offline"; horn and strobe still fire |
| Orin hang | `docker pause twin-orin-1` | arm watchdog |
| Power cut | `docker kill twin-orin-1 && docker start twin-orin-1` | back to Monitoring within 60 s |

`$WAN` is the orin container's interface on `172.30.4.0/24`.

Each command SHALL be run as shown, without wrapping it in `sh -c`. The arm-USB `pkill` pattern also matches the devices container's PID 1, which is harmless because PID 1 ignores signals it has no handler for. Inside `sh -c`, however, the pattern also matches the shell itself, so pkill kills its own shell (exit 143).

#### Scenario: Arm USB unplugged with the guide's command
- **WHEN** `docker exec twin-devices-1 pkill -f TCP-LISTEN:7001` runs
- **THEN** only the arm bridge stops. The devices container keeps running without a restart, the relay bridge and both emulators keep running, and the app reports the arm offline.

#### Scenario: Orin hang (V13)
- **WHEN** `docker pause twin-orin-1` runs while the laser is on
- **THEN** the laser is off and the arm is parking within 2 s of the last heartbeat. The last heartbeat comes at most one frame (67 ms) before the pause.
- **AND** after `docker unpause twin-orin-1`, the app resumes

#### Scenario: Camera cable cut and restored (V14)
- **WHEN** the camera is disconnected from `twin_poe_lan` and reconnected after 20 s
- **THEN** a "camera offline" health alert is queued within 10 s of the disconnect, and the app resumes processing frames after the reconnect

#### Scenario: 4G outage and recovery
- **WHEN** a 100% loss netem is applied to `$WAN`, a walk-in runs, and the netem is removed
- **THEN** the walk-in's events reach the cloud broker in order after the link returns

#### Scenario: Restart after power cut (V16)
- **WHEN** `docker kill twin-orin-1 && docker start twin-orin-1` runs
- **THEN** the app is back in Monitoring within 60 s with the same zone settings

### Requirement: Calibration provisioning
The stack SHALL provision the camera calibration, as an installer does on site. A one-shot step SHALL write `/data/calib/homography.npy` to the orin's persistent volume before the app first starts, and SHALL leave an existing file unchanged.

#### Scenario: First start
- **WHEN** the stack starts with an empty `orin_data` volume
- **THEN** the homography file exists before the app loads it, and the app starts without error

