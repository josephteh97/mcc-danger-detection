## MODIFIED Requirements

### Requirement: Isolated cable networks
`poe_lan` (`192.168.10.0/24`), `usb_bus` and `wan_4g` (`172.30.4.0/24`) SHALL be internal Docker networks, so nothing on them reaches the real internet. `sim_ctrl` is the twin's own control network.

In the `v11` profile the laser controller emulator SHALL join `poe_lan` at `192.168.10.24`, and `usb_bus` SHALL be used only by the phase-1 profile.

Only these host ports SHALL be published:
- `127.0.0.1:8080`, the dashboard
- `127.0.0.1:9200/udp`, the world control port for a local `tools.trial --send`

MQTT (1883), RTSP (8554), HLS (8888), the serial bridges (7001 and 7002), the laser controller's TCP ports and truth (9100) SHALL NOT be published to the host.

#### Scenario: Orin cannot reach the internet
- **WHEN** the orin container tries to connect to a public address
- **THEN** the connection fails

#### Scenario: Only the dashboard and loopback control are published
- **WHEN** `docker compose ps --format json` is inspected
- **THEN** the only published ports are `127.0.0.1:8080->8080/tcp` and `127.0.0.1:9200->9200/udp`

#### Scenario: Laser controller on the PoE LAN
- **WHEN** the stack runs in the v11 profile
- **THEN** the orin container reaches `192.168.10.24:7001` and `:7002`, and no container is attached to `usb_bus`
