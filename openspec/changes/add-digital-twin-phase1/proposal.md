## Why

The danger-zone pole hardware arrives around 20 Nov. Until then, nothing exercises the alarm software, the device protocols, the wiring plan or the failure handling. A Phase 1 digital twin lets us test all of these repeatably on one Linux PC, at any hour, without a site. The Orin app runs inside the twin unchanged, so a test that passes here exercises the same code that will ship to the pole.

## What Changes

- Add a Docker Compose stack, project name `twin`, with six containers and four virtual cables:
  - Containers: `camera` (MediaMTX), `world`, `devices`, `orin`, `cloud` (Mosquitto) and `dashboard`.
  - Cables: `poe_lan`, `usb_bus`, `wan_4g` and `sim_ctrl`. Each one can be cut on command for fault injection.
- Add the world simulator and camera renderer (`world/`): pinhole camera, calibration homography, scripted and keyboard-driven workers, UDP ground truth, and 16 weather and lighting presets.
- Add device emulators (`devices/`):
  - Laser arm: the AIM, LASER, HB, PARK and POS protocol, servo slew, tilt interlock and a 2 s watchdog.
  - Relay board: strobe, floodlight, laser power and a spare channel.
  - Horn: null sink and sound-start monitor.
  - Power: solar and battery model.
- Add the Orin application that ships to the pole (`app/`): zone geometry, alarm state machine, serial links, aim angles, offline uplink queue, oracle detector, tracker, and the capture, detect, track, alarm, act and upload loop.
- Add the Orin sandbox image (`orin/`), built in two flavours from one Dockerfile: x86 fast mode and arm64 JetPack mode.
- Add a product catalogue (`catalog/`): schemas, product files, a comparison tool and fitting products through `site.yaml`.
- Add human trial mode (`tools/trial.py`), driven by keyboard locally and over UDP in the full stack.
- Add a FastAPI dashboard on port 8080: 3D view, browser video, scenarios, weather, products, fault injection, run recording and a trial pad.
- Add the validation suite: 37 quick checks (36 pass, plus known fail V11) and a full-stack pytest suite covering V12–V18 with a JUnit report.
- Add `share.sh` (start, stop, status) to share the dashboard remotely over a sign-in-protected Microsoft Dev Tunnel. Only port 8080 is exposed.

## Capabilities

### New Capabilities
- `world-simulator`: Site model, pinhole camera renderer, calibration homography, scripted and controlled workers, ground truth over UDP, laser dot rendering, control port.
- `weather-presets`: The 16 weather and lighting presets. Their effect on the image, and the sun, wind and storm events they feed to the rest of the twin.
- `product-catalogue`: Per-category product files with schemas, validation, fitting through `site.yaml`, and side-by-side comparison under any weather.
- `device-emulators`: Laser arm, relay board, horn sink and monitor, and power model, each behind the same interface as the real device.
- `orin-sandbox`: A container shaped like the Orin AI box: CPUs, RAM, device paths, audio sink, two network interfaces, and fast and JetPack flavours.
- `virtual-cables`: The Compose stack, its networks and addresses, and the fault-injection commands that cut each cable.
- `alarm-app`: The Orin application: zone geometry, caution, warning, alarm and reset logic and timings, actuation, laser aiming, uplink queue and health alerts.
- `dashboard`: The web control room on port 8080: live 3D view, browser video, scenario runner, weather and product panels, fault buttons, run recording and trial pad.
- `human-trial-mode`: The arrow-key worker for supervisors: key map, speeds, scorecard, and network key sender.
- `validation-suite`: The quick checks and full-stack checks V01–V34, their pass criteria and reports.
- `remote-access`: `share.sh` to share only the dashboard with signed-in remote viewers, and close access again.

### Modified Capabilities
<!-- None: this is the first change in the repository. -->

## Impact

- **New code:** `world/`, `devices/`, `app/`, `orin/`, `dashboard/`, `catalog/`, `tools/`, `tests/`, `cloud/`, `compose.yaml`, `site.yaml` and `share.sh`. There is no existing code.
- **New host dependencies:** Docker Engine and the Compose plugin, ffmpeg, socat, PulseAudio utilities, and Python 3 with numpy, opencv-python-headless, pyyaml, paho-mqtt, pytest, fastapi, uvicorn and docker. Optional: pygame for trial mode, `devtunnel` for remote access, and QEMU binfmt for the arm64 sandbox.
- **Container images:** `bluenviron/mediamtx`, `eclipse-mosquitto:2` and `ubuntu:22.04`. Optional: NVIDIA `l4t-jetpack` for the arm64 flavour.
- **Security:**
  - The dashboard mounts the Docker socket for fault injection, so anyone who can reach it has root-level control of the host.
  - The dashboard is therefore bound to localhost, and is only shared through a sign-in-protected tunnel.
- **Interfaces fixed by this change, which the firmware and the site installation must follow:**
  - The arm serial protocol (AIM, LASER, HB, PARK, POS).
  - The relay line protocol (`R <ch> <0|1>`).
  - The camera RTSP URL.
  - The MQTT topic `pole/<id>/event`.
  - The `app/config.yaml` layout.
