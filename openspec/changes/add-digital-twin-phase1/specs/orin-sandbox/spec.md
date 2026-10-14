## ADDED Requirements

### Requirement: Orin-shaped container
The `orin` container SHALL match the Orin AI box as the app sees it:
- 6 CPUs and 8 GB of memory
- a persistent `/data` volume (the SSD)
- serial devices at `/dev/ttyARM` and `/dev/ttyRELAY`
- a PulseAudio null sink named `horn`
- one network interface on the PoE LAN (`192.168.10.2`) and one on 4G (`172.30.4.2`)

The app SHALL see nothing else of the twin.

#### Scenario: Device paths and interfaces
- **WHEN** the orin container is running
- **THEN** `/dev/ttyARM` and `/dev/ttyRELAY` exist, `pactl list short sinks` shows `horn`, and the container has addresses 192.168.10.2 and 172.30.4.2

#### Scenario: Resource limits
- **WHEN** the orin container is inspected
- **THEN** it is limited to 6 CPUs and 8 GB of memory

### Requirement: Virtual USB cables
The entrypoint SHALL plug in the virtual USB cables with `socat`:
- `PTY,link=/dev/ttyARM` to `devices:7001`
- `PTY,link=/dev/ttyRELAY` to `devices:7002`

It SHALL re-plug each cable automatically, retrying every second, after the far end goes away. It SHALL then start PulseAudio with the `horn` sink, and finally `exec` the app with `/opt/pole/app/config.yaml`.

#### Scenario: Cable re-plugged
- **WHEN** the arm bridge in the devices container is killed and then restarted
- **THEN** `/dev/ttyARM` is re-created and the app reconnects to the arm without restarting

### Requirement: Two build flavours from one Dockerfile
`orin/Dockerfile` SHALL take a `BASE` build argument:
- **Fast mode (default):** `ubuntu:22.04` on x86, for day-to-day logic, timing, protocol and fault tests in real time.
- **JetPack mode:** NVIDIA `l4t-jetpack` for the JetPack 6 release, built with `--platform linux/arm64` and run under QEMU. It proves the app installs and starts on the Orin's OS and CPU architecture, using the oracle detector.

#### Scenario: arm64 install (V18)
- **WHEN** the image is built with `docker build --platform linux/arm64 --build-arg BASE=nvcr.io/nvidia/l4t-jetpack:<tag> -f orin/Dockerfile -t pole-orin:arm64 .` and started
- **THEN** the app installs without missing arm64 wheels and reaches Monitoring with the oracle detector

### Requirement: App image is the shipping image
The sandbox SHALL install the app from `app/` and `app/requirements.txt` exactly as on the real Orin. Twin-only behaviour SHALL be selected by `config.yaml` values, never by code that checks whether it is inside the twin.

#### Scenario: No twin-only code paths
- **WHEN** `app/` is searched for checks that detect the twin
- **THEN** none are found; detector mode, device paths and URLs come only from `config.yaml`
