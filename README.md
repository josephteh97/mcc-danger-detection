# Danger-Zone Pole Digital Twin

This digital twin of the danger-zone pit alarm pole runs as Docker containers on one Linux PC:
- a simulated site and camera
- a sandbox playing the Orin AI box
- an emulator for every device and cable

The real alarm software in `app/` runs inside the Orin sandbox unchanged, so a check that passes here exercises the code that ships to the pole.

The source of truth is the "Danger-Zone Pole Digital Twin: Linux Implementation Guide". The OpenSpec specs are in `openspec/specs/`; the archived phase-1 proposal, design and tasks are in `openspec/changes/archive/2026-10-29-add-digital-twin-phase1/`. Deviations from the guide are listed at the end of this file and in `design.md`.

**Two site profiles.** `site.yaml` selects one (`$TWIN_PROFILE` overrides it):
- **`phase1`** (`sites/phase1.yaml`, `app/config.yaml`): the guide's pole, with an 8 MP camera on a 6.5 m trailer mast, an Orin Nano, and the arm and relays on USB. The guide checks V01–V34 and U01–U10 always run on this profile.
- **`v11`** (`sites/v11.yaml`, `app/config.v11.yaml`): hardware list version 11, a detection-only pole. It has a 12 MP camera on a 3.8 m wheeled stand 9.5 m south of the pit, a reComputer J4012 on PoE++, the laser controller on Ethernet at 192.168.10.24, a 24 V bus with power Plans A/B/C, and remote management. This is the stack's default. Face/tag identification is kept as switched-off legacy code (`identify.enabled: false`).

```
camera (MediaMTX) ─ RTSP on poe_lan ─► orin (app) ─ 4G (wan_4g) ─► cloud (Mosquitto)
   ▲ HLS ─► dashboard :8080 ◄─ truth, logs, MQTT     ▲ usb_bus (socat)
world (renderer + ffmpeg)                         devices (arm + relay emulators)
```

## Host setup (Ubuntu 22.04 or 24.04, 8+ cores, 16 GB RAM, 50 GB disk)

```bash
sudo apt install -y ca-certificates curl git ffmpeg socat iproute2 pulseaudio-utils python3-venv
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER            # then log out and back in
docker run --privileged --rm tonistiigi/binfmt --install arm64   # only for the JetPack-mode sandbox (V18)

python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pip install pygame                       # optional: trial-mode window and the network keypad
```

## Quick checks (no Docker needed)

```bash
python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py \
  && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py && python3 tests/smoke_v11.py
```

The expected result is **53 checks: 52 PASS and 1 known FAIL**. V11 fails because the phase-1 battery runs flat over three heavily overcast days (the second finding). A script exits 0 when every check matches its expected outcome, so the chain runs to the end. It exits 1 on a regression, or if V11 starts passing. The first five scripts (36 PASS + V11) always load the phase-1 profile.

`smoke_v11.py` runs U11–U26 on the v11 profile:

| Checks | What they cover |
|---|---|
| U11–U16 | Lens distortion q and D, warning-ring density with tiles (and the shrunken-input fail), largest-zone solver, stand pose and height windows, stand too close |
| U17–U23 | PoE budget (and an undersized switch), 4G data a month, PoE++ losses, continuous load, Plan B over three overcast days, Plan A shutdown order |
| U24–U26 | No identity in v11 alarms, PoE watchdog restart (model), laser reach from the stand |

Legacy identification tests are skipped by default; run them with `pytest --legacy tests/legacy`.

## Full stack

```bash
docker compose up --build          # the v11 pole; then open http://localhost:8080
docker compose -f compose.yaml -f compose.phase1.yaml up -d --build    # the phase-1 pole (USB cables)
WEATHER=night_rain SCENARIO=idle docker compose up -d --build
pytest tests/ -v --junitxml=reports/twin-$(date +%F).xml   # quick checks, static checks, full-stack V12-V16 and faults
docker compose down
```

| Service | What it is |
|---|---|
| `camera` | MediaMTX. RTSP for the Orin at `rtsp://192.168.10.20:8554/stream1` on `poe_lan`; HLS for the dashboard on `sim_ctrl` |
| `world` | Renders at 15 fps: 1280x720 in phase 1, 1600x1200 through the 12 MP camera's lens in v11. Sends ground truth to UDP 9100. Control port on 9200 |
| `calib` | One-shot: writes `/data/calib/homography.npy` to the Orin's volume, then exits. It keeps a file that still fits the camera and recalibrates when the camera has moved (another profile) |
| `devices` | v11: the laser controller at 192.168.10.24 on `poe_lan` (arm on TCP 7001, relays on 7002). Phase 1: the emulators behind socat bridges on `usb_bus` (the USB cables) |
| `orin` | 6 CPUs and 8 GB. `horn` sink, `/data`, 192.168.10.2 and 172.30.4.2. Phase 1 adds `/dev/ttyARM` and `/dev/ttyRELAY`. v11 runs sshd on 192.168.10.2 only (key login, for engineers) |
| `router`, `engineer`, `superior`, `relay` | v11 only, emulated: the 4G router's Tailscale node (subnet route for the engineer, nothing open on 4G, switch-restart output), an engineer laptop in the tailnet, the superior's client, and the cloud relay the AI box pushes live view to. No real Tailscale; every network is internal |
| `cloud` | Mosquitto on the internal 4G network, at 172.30.4.10:1883 |
| `dashboard` | FastAPI on 127.0.0.1:8080 |

The only ports published on the host are **127.0.0.1:8080**, the dashboard, and **127.0.0.1:9200/udp**, the trial keypad for this host. MQTT, RTSP, HLS and the serial bridges stay inside Docker networks.

### Dashboard (http://localhost:8080)

- **3D view.** A three.js site model driven by live ground truth, arm angles and laser state (`/logs/arm.jsonl`), strobe and floodlight (`/logs/relay.jsonl`), and the app's MQTT events.
- **Camera video.** The browser plays the camera's HLS stream through `/video/`.
- **Scenarios.** Single walk-in, two workers, passer-by on the ring edge, a worker who stops 1.6 m away, a worker hidden behind another, the demo loop, and idle.
- **Weather.** All 16 presets. Thunderstorm also fires a power surge and a 30 s 4G drop.
- **Faults.** One button per row of the fault table, each with a restore button.
- **Human trial pad.** On-screen arrows or the keyboard; Shift runs; C squats and K kneels.
- **3D quality and HUD.** Physically based materials, a sky and sun by Singapore time, soft shadows, rain and haze, the floodlight cone at night, rigged workers in their posture, the wheeled stand (with the solar skid for Plans B and C), the camera's true field of view, and the laser beam with bloom. HUD panels show the alarm and dwell time, power plan, PoE, 4G and active faults. There are low, medium and high quality presets, plus a px/m heatmap.
- **v11 design what-if.** Every catalogue number of the v11 pole (prices, watts, PoE classes, efficiencies, battery and panel sizes) and the site settings (stand distance, camera height and tilt, switch budget, detector input, events and viewing a day) can be keyed in. The PoE budget, power plans, costs, 4G data, coverage and laser reach are then worked out again. Nothing is written to the catalogue files.
- **Products.** Pick products in a category and compare them: table plus picture grid.
- **Runs.** Every scenario starts a recording in `/logs/run-<time>/`, which can be replayed frame by frame in the 3D view.

### Fault injection

| Fault | Command | Expected behaviour |
|---|---|---|
| Camera cable unplugged | `docker network disconnect twin_poe_lan twin-camera-1` | "Camera offline" alert within 10 s, queued for the cloud |
| 4G weak | `docker exec twin-orin-1 sh -c 'tc qdisc add dev $WAN root netem delay 120ms 40ms loss 5%'` | Events still arrive, a little later |
| 4G outage | same with `loss 100%`; restore with `tc qdisc del dev $WAN root` | Events queue on disk and arrive in order |
| Laser arm USB unplugged | `docker exec twin-devices-1 pkill -f TCP-LISTEN:7001` | App logs "arm offline"; horn and strobe still fire |
| Orin software hangs | `docker pause twin-orin-1` | Laser off and arm parked within 2 s (watchdog) |
| Power cut and restore | `docker kill twin-orin-1 && docker start twin-orin-1` | Back to Monitoring within 60 s with the same zones |
| v11: laser controller arm link down | `docker exec twin-devices-1 pkill -f 'arm_emulator.py --tcp'` | "arm offline"; the TCP link reconnects within 2 s of the controller coming back |
| v11: AI box hangs | `docker pause twin-orin-1` | The PoE watchdog (in the dashboard) power-cycles it within 40 s; Monitoring within 60 s after that |
| v11: PoE switch hangs | dashboard button (disconnects every `poe_lan` device except the router) | The router keeps reporting to the cloud; the engineer's restart brings back the camera and arm within 60 s |
| v11: router-driven switch restart | `docker exec twin-engineer-1 curl -X POST http://100.64.0.1:8022/switch/restart` | All `poe_lan` links back |
| v11: site power cut | dashboard button | The HUD shows the battery taking over and the shutdown stages |

`$WAN` is the Orin's 4G interface:

```bash
WAN=$(docker exec twin-orin-1 sh -c "ip -o -4 addr | awk '/172\.30\.4\./{print \$2}'")
```

Run the commands as shown, not inside `sh -c`: there the `pkill` pattern also matches the shell, and pkill kills its own shell.

## Remote access (`share.sh`)

`share.sh` shares the dashboard with people on other machines through a Microsoft Dev Tunnel.
- **One port.** Only port 8080 goes on the tunnel. MQTT, RTSP, HLS, the serial bridges, truth (9100) and the trial control port 9200 never do.
- **Through the dashboard.** Remote viewers drive the worker and inject faults with the dashboard's controls.
- **Browser video.** Viewers watch the camera through the dashboard's own browser stream (`/video/`, HLS), not raw RTSP.

**Every viewer must sign in.** The dashboard can inject faults, move workers and, through the Docker socket, control this host, so the tunnel is never anonymous:
- `share.sh` refuses `--allow-anonymous`.
- `start` checks that an anonymous request is turned away, and takes the tunnel down again if one gets through.
- No extra password is added, because the tunnel service itself enforces sign-in.

### One-time setup

```bash
curl -sL https://aka.ms/DevTunnelCliInstall | bash      # installs devtunnel (or put the binary on PATH)
devtunnel user login -g                                  # GitHub; add -d to get a device code instead
```

A GitHub login does not last long: the one on this host expired overnight. When the login has expired, `share.sh` says so and prints the login command.

### Share, check, stop

```bash
docker compose up -d --build     # the dashboard must answer on 127.0.0.1:8080
./share.sh start                 # prints the https://…devtunnels.ms URL to open on the other machine
./share.sh status                # URL, ports (8080 only), access rules, sign-in and video checks
./share.sh stop                  # stops hosting and deletes the tunnel; the URL stops working
```

| `start` option | Who can sign in |
|---|---|
| (none) | only you (sign in with the GitHub account `devtunnel` is logged in as) |
| `--repo owner/repo` | GitHub accounts with access to that repository. Not usable yet: `devtunnel` 1.0.2115 and earlier reject every repository rule with "Specify access control parameters", and `start` then deletes the tunnel. |
| `--org <github-org>` | members of that GitHub organization (repeatable) |
| `--tenant` | accounts in your Microsoft Entra tenant (needs an Entra login) |
| `--owner-only` | only you |
| `--expires 8h` | the access rules and the tunnel expire after that time (1h to 30d); without it they last until `stop` |

Options apply only when a new tunnel is created: while sharing is on, `start` with options is refused, so run `stop` first to change access or expiry.

The dashboard stays published on `127.0.0.1:8080` only. The tunnel connects to it locally, and nobody on your network can reach it without signing in. If `DASHBOARD_BIND` also puts the dashboard on another address, `share.sh` warns about it.

`.share/` (git-ignored) holds the tunnel ID, the URL, the host's process ID and `host.log`.

### Teardown

```bash
./share.sh stop                          # also lists twin tunnels left over from earlier runs
devtunnel list --labels twin-dashboard   # should list nothing
devtunnel delete <tunnel-id> -f          # for any leftover
docker compose down                      # stop the twin
devtunnel user logout                    # optional
```

## Tools

```bash
python3 -m tools.trial                                     # human trial mode (pygame or OpenCV window)
python3 -m tools.trial --weather night_rain --camera dome_4mp_2_8mm_generic --npcs 1
python3 -m tools.trial --miss-rate 0.1 --delay-ms 200      # a weaker detector
python3 -m tools.trial --headless                          # scripted walk-in, prints the scorecard
python3 -m tools.trial --send 127.0.0.1:9200               # keypad for the full-stack worker (this host)
python3 -m tools.compare camera bullet_8mp_4mm_generic dome_4mp_2_8mm_generic --weather clear,tropical_downpour
python3 -m tools.evaluate logs/run-<time>                  # score a recorded run
python3 devices/power_model.py --days 3 --weather overcast
python3 devices/power_model.py --profile v11 --plan B --days 3 --sun 0.3      # v11 power plans A, B, C
python3 devices/power_model.py --profile v11 --plan A --socket-off 0 60       # weekend without the site socket
python3 -m tools.coverage [--distance 10] [--height 4.5]   # v11 coverage, placement windows, laser reach
python3 -m tools.network [--events 120]                    # v11 link loads and 4G data a month
python3 devices/poe_model.py [--budget 90]                 # v11 PoE port map and budget
docker exec twin-engineer-1 ssh 192.168.10.2               # v11: an engineer on the AI box through the tailnet
```

Trial keys:

| Key | Action |
|---|---|
| arrows or WASD | walk (Up walks away from the camera) |
| Shift | run |
| C / K | squat / kneel, or stand up again (no walking while down) |
| N / Tab | add a worker / switch between workers |
| R | reset |
| E | next weather |
| Z | zone rings |
| P | pause |
| Q or Esc | quit and save `logs/trial-<time>.json` |

## Layout

```
compose.yaml   compose.phase1.yaml  # stack (v11 default) and the phase-1 override
site.yaml      sites/               # profile selector; phase1.yaml and v11.yaml (pit, camera pose, arm, products, PoE, plans)
share.sh                            # remote access to the dashboard (devtunnel)
app/           the Orin app: alarm.py, links.py, detect.py, track.py, health.py, horn.py, identify.py (legacy), main.py, config.yaml, config.v11.yaml
world/         entrypoint.sh (renderer | ffmpeg), world.py (renderer), camera.py, scene.py (workers), weather.py (16 presets), controls.py, stream.py
devices/       arm_emulator.py, relay_emulator.py, power_model.py, poe_model.py, poe_watchdog.py, vserial.py
remote/        v11 router (Tailscale node), cloud relay, engineer client (emulated)
orin/          Dockerfile (fast and JetPack flavours), entrypoint.sh, horn_monitor.py
dashboard/     server.py, live.py, faults.py, v11.py (what-if, HUD, heatmap), static/ (three.js, add-ons and hls.js vendored)
catalog/       one folder per category, _schema.yaml plus product files; effects.py
tools/         trial.py, compare.py, evaluate.py, calibrate.py, coverage.py, network.py
tests/         smoke*.py (quick checks), test_compose.py (static), test_stack.py (full stack), test_quick.py (pytest wrapper),
               test_v11_world.py, test_links_tcp.py, test_share.py, test_whatif.py, legacy/ (pytest --legacy)
```

## Deviations from the guide

The guide's "Source files" tab was not available, so every module was written from the guide's text and tables. All of these deviations are recorded in `openspec/changes/archive/2026-10-29-add-digital-twin-phase1/design.md`.

- **37 phase-1 quick checks.** These are the 27 V-rows the guide marks Pass or Fail before the full stack, plus 10 named unit checks (U01-U10). Version 11 adds U11-U26 (53 in all).
- **Loopback-only ports.** The dashboard is published on 127.0.0.1 because it holds the Docker socket. The control port 9200 is also loopback only; remote people drive the worker through the dashboard.
- **Camera on two networks.** The camera also joins `sim_ctrl`, so the dashboard can serve its HLS stream. The world feeds the camera over `sim_ctrl` too, so the "camera cable" fault cuts only the Orin's view.
- **Live weather and scenario switching.** These go over the world's control port instead of restarting the world container.
- **Calibration service.** A one-shot `calib` service writes the homography to the Orin's volume.
- **World pipeline in a script.** The guide's folded `command:` keeps its line breaks, so ffmpeg runs without its encoder and output options and no stream is published. The renderer-to-ffmpeg pipeline is in `world/entrypoint.sh` instead.
- **Fixed addresses outside the dynamic range.** Without an `ip_range`, the world took 192.168.10.2, the Orin's address. Dynamic addresses now come from the top half of each subnet.
- **Video encoding.** The world's ffmpeg adds `-pix_fmt yuv420p`, which browsers need to decode H.264.
- **PulseAudio.** The `pulseaudio` daemon package is added (the guide installs only `pulseaudio-utils`). The entrypoint also clears PulseAudio's state left in `/tmp` before the guide's start line. Without that, `pulseaudio --start` starts nothing after a power cut and the horn stays silent.
- **Socat retry loops.** The sandbox wraps `socat` in retry loops so a re-plugged cable comes back.
- **Power-model start.** The model starts with a full battery at sunset after a clear day. This reproduces the guide's battery figures to within about 1 point.

### Version 11 notes (recorded in `openspec/changes/add-v11-detection-only-pole/design.md`)

- **Typical values.** Only the 12 MP camera (S$1,586.18) and the J4012 (S$1,449.00) carry prices from hardware list version 11. Every other v11 figure is a typical value marked `verified: false`. It was chosen so the change's reference numbers hold (135.4 W PoE reserved, about 88 W drawn, 65–75 W bus load). Correct the values in the what-if panel, then in the catalogue files.
- **What-if panel** (D13). The dashboard lets you key in product values and site settings and recalculates every v11 model. This was asked for during implementation; it is not in the guide.
- **Rendering lens** (D14). The datasheet's distortion D = 0.845 folds over before the edge of a 102° lens: g = 1 − D·u² turns negative past u = 1.09, but the frame edge is at u = 1.23. The coverage maths keeps D, which is valid over the zone (u ≤ 0.6). The world renders through a monotone arctan lens with the same centre f/p and field of view, and the app undoes it per foot point before the homography.
- **4G estimate** (D15). Monthly data counts event clips, event messages and live viewing. The twin's 1 s status topic is a twin convenience and is not counted.
- **PoE watchdog location** (D16). It runs in the dashboard, which holds the Docker socket, rather than in the devices container.
- **Subnet route as a SOCKS5 proxy** (D17). Docker drops packets routed between two internal networks. So the router node serves the engineer's subnet route the way Tailscale's userspace-networking mode does: as a SOCKS5 proxy on its tailnet address. The engineer's SSH goes through it.
- **Workers are articulated, not loaded models.** The 3D view builds jointed figures from primitives (no GLTF), so nothing new is downloaded.
