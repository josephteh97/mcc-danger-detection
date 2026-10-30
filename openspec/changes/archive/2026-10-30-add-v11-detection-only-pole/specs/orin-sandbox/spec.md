## MODIFIED Requirements

### Requirement: Virtual USB cables
In the phase-1 profile, the entrypoint SHALL plug in the virtual USB cables with `socat`:
- `PTY,link=/dev/ttyARM` to `devices:7001`
- `PTY,link=/dev/ttyRELAY` to `devices:7002`

It SHALL re-plug each cable automatically, retrying every second, after the far end goes away.

In the `v11` profile the entrypoint SHALL NOT start the `socat` cables. The app SHALL instead open TCP line links to the laser controller at `192.168.10.24` on `poe_lan` (port 7001 for the arm, 7002 for the relays) through a `TcpLine` adapter in `app/links.py` with the same read and write methods as the serial link. It SHALL reconnect every second after the far end goes away.

The entrypoint SHALL then start PulseAudio with the `horn` sink, and finally `exec` the app with the profile's config (`/opt/pole/app/config.yaml` or `/opt/pole/app/config.v11.yaml`).

PulseAudio SHALL start with the guide's line, `pulseaudio --start --exit-idle-time=-1 && pactl load-module module-null-sink sink_name=horn`, with two additions:
- **The daemon package.** The image SHALL install `pulseaudio` as well as `pulseaudio-utils`, which has only the clients.
- **Stale state cleared.** Before starting, the entrypoint SHALL remove the PulseAudio runtime state a previous run left in `/tmp`. A real boot clears it, but `docker kill` followed by `docker start` does not, and with the old pid file in place `pulseaudio --start` exits 0 without starting a daemon.

#### Scenario: Cable re-plugged
- **WHEN** the arm bridge in the devices container is killed and then restarted
- **THEN** `/dev/ttyARM` is re-created and the app reconnects to the arm without restarting

#### Scenario: Ethernet link re-connected in v11
- **WHEN** the laser controller emulator is restarted in the v11 profile
- **THEN** the app's TCP arm and relay links reconnect within 2 s without restarting the app

#### Scenario: Horn sink after a power cut
- **WHEN** `docker kill twin-orin-1 && docker start twin-orin-1` runs, once or several times in a row
- **THEN** `docker exec twin-orin-1 pactl list short sinks` shows `horn` each time
