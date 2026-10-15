## Context

The source of truth is "Danger-Zone Pole Digital Twin: Linux Implementation Guide" (14 Oct 2026). Its "Source files" tab was **not available** for this build, so every module and smoke test is written from the guide's text and tables, not copied from the tested originals. The guide's shell snippets were also never run, so they are treated as sketches.

The repository is empty. The pole hardware arrives around 20 Nov. Phase 1 must run on one Linux PC: Ubuntu 22.04 or 24.04, 8 or more cores, 16 GB or more of RAM, and Docker with Compose.

Architecture: six containers joined by four virtual cables.

```
             sim_ctrl (twin control, not internal)
   ┌──────────────┬───────────────┬─────────────────────────┐
   │              │               │                         │
 world ──RTSP──► camera (MediaMTX) ──HLS /video/──► dashboard :8080 ◄── browser / devtunnel
   │  poe_lan     │ 192.168.10.20                    │   │ docker.sock (faults)
   │  truth UDP   │                                  │   │ /logs (arm, relay, runs)
   └────────► orin 192.168.10.2 ◄── usb_bus ──► devices (arm :7001, relay :7002)
                  │ wan_4g 172.30.4.2                │
                  └─────────► cloud (Mosquitto) 172.30.4.10 ◄── wan_4g
```

The Orin sandbox sees only what the real Orin sees:
- RTSP on the PoE LAN
- two serial ports
- the `horn` audio sink
- a 4G route to the cloud
- the twin-only oracle truth on UDP 9100

## Goals / Non-Goals

**Goals:**
- Run the shipping app (`app/`) unchanged in an Orin-shaped container, against emulated devices and cables.
- Make every safety decision a pure function that can be tested without hardware: zone geometry, the alarm state machine, aim angles and the uplink queue.
- Reproduce the guide's validation results:
  - 36 of the 37 quick checks pass, and V11 fails as known.
  - The full-stack checks V12–V16 run against `docker compose up`.
- Provide a dashboard to watch the twin, run scenarios, inject faults and walk a worker, and share it safely with remote viewers.

**Non-Goals:**
- **GPU or TensorRT performance, and YOLO accuracy (V17).** These need the real Orin and recorded site footage. YOLO mode gets an interface only.
- **Phase 2 (Gazebo and ROS 2) and Phase 3 (hardware in the loop).** The interfaces are kept stable for them, but they are not built.
- **Helmet-tag identification.** `identify.py` is a stub returning "unknown"; V28 already shows no catalogue camera can read tags from the pole.
- **The standalone JavaScript "3D setup page" demo.** The dashboard's trial pad drives the real stack instead.
- **Loudness, optics, thermal, wind and 4G coverage.** These are in the guide's "what the twin cannot prove" list.

## Decisions

### D1. The repo root is the guide's `twin/` folder; the Compose project name stays `twin`
The user asked to build directly in this folder. Keeping `name: twin` means container and network names such as `twin-orin-1` and `twin_poe_lan` match the guide's fault commands word for word.
*Alternative:* a `twin/` subfolder. This adds a level of nesting and gains nothing.

### D2. Safety logic is pure, and I/O sits at the edges
`app/alarm.py` holds:
- `ground_from_image`
- `edge_distance`
- `AlarmFSM` with `Config`

`app/links.py` holds:
- `aim_angles`
- `ArmLink`
- `SerialLine` with a relay adapter
- `Uplink`

`app/main.py` only wires them together. The quick checks drive these functions on a simulated clock, so timing checks (V02, V03, V30, V32) are deterministic and do not depend on host load.

### D3. Alarm state machine semantics
The guide names four events and timings but does not state the rules in full. The rules below are the ones that satisfy V01–V04, V15, V30 and V32 and the fifth finding.

- **Per-person state:** caution flag, zone entry time, last-seen time.
- **Caution:** emitted once per person when they first come within 3.0 m. It is a chime, not a level.
- **Warning:** emitted when a person has been within 1.5 m for `dwell_s` (1.0 s). It sets level 1.
- **Alarm:** emitted when a person has been within 1.5 m for `escalate_s` (3.0 s) since entry. It sets level 2.
- **Reset:** emitted when the level is 1 or higher and no person has been within 1.5 m for `clear_s` (2.0 s). The level returns to 0. A caution-only visit emits no reset.
- **Persistence:** a person is kept for `clear_s` after they were last seen, so a missed frame keeps their caution flag and entry time (fifth finding). A person who steps out and back within `clear_s` keeps their entry time.
- **Level:** the system level is the highest any person justifies. The laser targets the person in the zone nearest the pit edge.

### D4. Actuation mapping
The guide lists horn, strobe, identify and event, but not which output fires on which event.

| Event | Outputs |
|---|---|
| Caution | chime |
| Warning | warning tone, laser power on (relay 3), aim at the feet |
| Alarm | siren, strobe on (relay 1), identify, event to the cloud |
| Reset | all off, park |

Every event goes to the cloud so the dashboard can show the alarm state. The floodlight (relay 2) follows the 19:00–07:00 schedule assumed by the power model.

Switching relay 3 only while at warning or above means the laser needs three independent conditions to fire:
1. relay 3 has power
2. `LASER 1` arrives with a live heartbeat
3. the firmware's tilt interlock allows it

### D5. Laser safety rules
- **Tilt interlock:** at least 1° below horizontal, on the actual angle and not the commanded one.
- **2 s heartbeat watchdog:** at 2 s the laser goes off immediately and the arm starts slewing to park (pan 0°, tilt 90°).
- **Laser off on PARK.**

"Laser off and arm parked within 2 s" (V08 and V13) is taken to mean that the laser is off and parking has begun by 2 s. Parking then completes at the 180°/s slew rate, in at most about 0.5 s. The arm reports its state every 50 ms, so the measured laser-off time is 2.0 s plus up to one report period.

Class 2 rule: the catalogue flags any laser module over 1 mW CW visible as not Class 2 (V27), and **refuses to fit one** to the pole in `site.yaml`.

### D6. Video to the browser: MediaMTX HLS proxied by the dashboard; the camera also joins `sim_ctrl`
The dashboard is not on `poe_lan`, so in the guide's compose file it cannot reach the camera.

The chosen fix:
- The camera service also joins `sim_ctrl`.
- The dashboard reverse-proxies MediaMTX's HLS output (`:8888`) under `/video/`.
- The browser plays it with hls.js, from the same origin and port 8080. This works through the tunnel.

The world also feeds the camera over `sim_ctrl`, to the camera's fixed `sim_ctrl` address: the renderer is the camera's sensor, not a network cable. So the "camera cable" fault disconnects only `poe_lan`, the Orin loses the camera, and the dashboard keeps showing the scene.

MediaMTX 1.21 answers the first playlist request with a cookie-check redirect. Its `Location` points outside `/video/` and its cookie is `Secure`, which browsers drop on plain-http hosts. The proxy therefore follows the redirect server-side; the per-session `session=` query parameter in the variant playlists passes through unchanged.

*Alternatives:*
- Putting the dashboard on `poe_lan` puts a Docker-socket-holding service on the pole's LAN.
- MJPEG transcoding in the dashboard costs about 10× the bandwidth through the tunnel.
- WebRTC needs UDP media, which does not traverse the tunnel.

### D7. Host exposure: loopback only
The guide publishes `8080:8080`, which is reachable from the LAN with no login. The dashboard holds the Docker socket, which is root-equivalent, so it is published on `127.0.0.1:8080` instead.

The world's control port is published on `127.0.0.1:9200/udp`, so `tools.trial --send localhost:9200` works on the twin host. Remote people drive the worker through the dashboard's trial pad, which relays to `world:9200` inside `sim_ctrl`.

This resolves a conflict between the guide, which says `--send <twin-host>:9200` works from any machine, and the requirement that port 9200 is never exposed.

### D8. Weather and scenario changes go over the control port, not by restarting the world container
The guide says the dashboard restarts the world with the new preset. Changing a container's command or environment means re-creating it through Compose, which the dashboard does not have.

The world already needs live preset cycling for the trial's E key. So the dashboard sends `{"cmd": "weather", "name": ...}` and `{"cmd": "scenario", ...}` to the control port instead. This switches in under a frame, keeps the RTSP stream up, and uses one code path. `WEATHER=` at startup still works.

### D9. Calibration is provisioned by a one-shot `calib` service
On site, an installer writes `/data/calib/homography.npy`. In the twin, a short-lived `calib` service (built from the world image) does the same:
1. computes the homography with `image_to_ground_homography()` for the site in `site.yaml`
2. writes it into the `orin_data` volume
3. exits

`orin` waits for it to complete successfully. An existing file is left unchanged, so a power-cut restart (V16) keeps the same calibration.

*Alternative:* mounting the world's state into the orin. This breaks the rule that the sandbox sees only what the real Orin sees.

### D10. Robust capture and cables
- **Capture:** frames are decoded by an `ffmpeg` subprocess (RTSP over TCP to raw BGR at the configured size) read on a background thread. The main loop treats more than 3 s without a frame as "camera lost". It raises the health alert well inside V14's 10 s. A watchdog kills a stalled ffmpeg and reconnects with backoff. `cv2.VideoCapture` was rejected: its RTSP timeout options mean different things in different bundled FFmpeg versions (in 4.x, `timeout` switches RTSP into listen mode), and a blocked read can outlive the cable fault by minutes. On the real Orin the same reader can sit on a hardware-decoding pipeline.
- **Serial cables:** the orin entrypoint wraps each `socat` in a retry loop, so a re-plugged cable comes back without restarting the app.
- **PulseAudio:** started with the guide's line, as root, which PulseAudio only warns about. The entrypoint first clears the runtime state a previous run left in `/tmp` (D18). The app plays tones on the `horn` sink with `paplay`.

### D11. Uplink: SQLite queue with MQTT QoS 1, strictly in order
- `Uplink.put()` appends an event with an increasing sequence number.
- `flush()` publishes the queue head with QoS 1. It deletes the row only after PUBACK, and stops at the first failure, so order is preserved and nothing is lost across outages or restarts.
- A duplicate after a crash between PUBACK and delete is possible (at-least-once). Events carry `seq` so the cloud can drop duplicates.

### D12. Oracle detector removes IDs, and an IoU tracker assigns them
The oracle receives the world's ground truth. It applies delay (120 ms), jitter and miss rate, then drops the true IDs. This means `track.py`, a simple IoU tracker that keeps tracks through gaps, is exercised exactly as it will be with YOLO.

### D13. Power model initial condition
The guide's battery figures are reproduced by an hourly model with these settings:
- Load: 396 Wh by day, 756 Wh by night.
- Generation: 1,400 Wh per average day, multiplied by the sun factor.
- Start: battery full at 19:00 after a clear day.
- An N-day run: N weather daylight periods and the N + 1 nights around them.
- Result: the lowest charge.

| Case | Model | Guide |
|---|---|---|
| Clear | 70.5% | 70% |
| 2 days at 30% sun | 13.3% | 12% |
| 3 days at 30% sun | flat | flat |
| Floodlight off | 40.9% | 40% |
| 1,000 W of panels | 33.9% | 33% |
| Second battery | 42.3% | 42% |

The sun factors for the presets are solved from the guide's weather table:

| Preset | Sun factor |
|---|---|
| overcast | 0.44 |
| regional_haze | 0.59 |
| dust_or_smoke | 0.69 |
| morning_mist | 0.50 |
| humid_lens | 0.80 |
| strong_wind | 0.69 |
| light_rain | at most 0.35 |
| tropical_downpour | at most 0.35 |
| thunderstorm | at most 0.35 |
| dense_fog | at most 0.35 |
| clear, night presets, low_sun_glare, mud_splash | 1.0 |

### D14. Quick checks: 37 named checks with known-fail exit semantics
The guide says 37 checks ran and 36 passed, but its matrix marks only 27 rows Pass or Fail before the full stack. The 37 are therefore defined as those 27 V-rows plus 10 named unit checks, U01–U10, listed in the `validation-suite` spec.

The guide chains the scripts with `&&`. So a script exits 0 when every check matches its expected outcome, V11 included, and non-zero on any regression, or if V11 starts passing.

### D15. Rendering resolution
The world always renders 1280×720, a scaled-down 8 MP stream. A catalogue camera's field of view changes the projection. Pixels per metre and the DORI level are computed analytically at the product's native resolution, matching the guide's 175, 93, 130 and 213 px/m figures to within ±5%.

### D16. Remote access with Microsoft Dev Tunnels, sign-in enforced by the tunnel service
This was the user's choice. `share.sh` uses `devtunnel` and does the following:
1. Creates a named tunnel with port 8080 only.
2. Adds an access rule for the GitHub repository, so collaborators of the private repo can sign in.
3. Optionally adds org or tenant rules, with an expiry.
4. Hosts the tunnel in the background, logging to `.share/`.

The tunnel is never anonymous. Basic auth is not added, because the requirement asks for basic auth only on a *public* tunnel, and a tunnel that requires sign-in is not public.

Devtunnel rewrites Host and Origin to localhost by default, so FastAPI's WebSocket and the HLS proxy work unchanged.

### D17. Pinned images and vendored front-end libraries
- MediaMTX and Mosquitto are pinned to release tags. The guide's `mediamtx:latest` is pinned once it works.
- three.js and hls.js are vendored into `dashboard/static/` at pinned versions, so the dashboard works with no internet access.

### D18. Fixes to the guide's snippets
Each fix was reproduced against the guide's own text. Each has a regression check in `tests/test_compose.py` (no Docker needed) or `tests/test_stack.py`.
- **The world command splits ffmpeg's options.** In a folded (`>`) block, more-indented lines keep their line breaks. In the guide's world command, sh therefore runs `ffmpeg … -i -` with no encoder or output, then fails on `-c:v …` and `-f rtsp …` as separate commands ("not found"). No stream is ever published. The pipeline now lives in `world/entrypoint.sh`, which the world image runs, so neither YAML folding nor Compose's own word-splitting touches it. The devices command uses the same folded form but works, because each of its lines ends in `&` or `;`. It is kept as the guide has it.
- **Dynamic addresses can steal fixed ones.** A container without a fixed address on `poe_lan` (the world) took 192.168.10.2, the Orin's address. Each network now limits dynamic addresses to the top half of its subnet (`ip_range`).
- **Browsers need `-pix_fmt yuv420p`.** Without it, libx264 encodes BGR input as 4:4:4, which browsers cannot decode.
- **The PulseAudio daemon is missing, and its stale state blocks a restart.**
  - The guide's apt list has only `pulseaudio-utils`, so `pulseaudio` is not found and the horn sink never exists. The `pulseaudio` package is added.
  - The guide's start line then works as root; it only warns.
  - After a power cut (`docker kill`, then `docker start`), the previous daemon's pid file and socket are still in `/tmp`. `pulseaudio --start` then exits 0 without starting a daemon, so the horn stays silent. The entrypoint clears that runtime state first, as a real boot would.
- **The arm-USB command must not run inside a shell.**
  - Run as the guide writes it, `docker exec twin-devices-1 pkill -f TCP-LISTEN:7001` works. It also matches the devices container's PID 1, but PID 1 ignores signals it has no handler for, so only the socat bridge stops.
  - Wrapped in `sh -c`, the pattern also matches the shell, so pkill kills its own shell (exit 143). That is how the dashboard first ran it.
  - The dashboard now runs the guide's command directly. Its restore runs inside `sh -c`, so it checks for the bridge with an anchored `pgrep -f '^socat TCP-LISTEN:7001'`.
- **Contrast tuning.** The renderer's light, visibility and window-fog values were tuned so that every preset's worker contrast lands within a few points of the guide's table: fog 19%, downpour 26%, haze 66%, night 69% with the floodlight and 12% without, low sun 60% without true WDR and 90% with it. The numbers are recorded in `world/weather.py`.

## Risks / Trade-offs

- **The code is not the guide's tested source.** The guide's measured figures (contrast percentages, foot error 0.29 m, 1.13 s and 3.2 s) may differ from the rewritten modules.
  → Pass criteria are the matrix thresholds. Measured values are printed next to them and reported honestly, never tuned to match.
- **Docker socket in the dashboard.** Anyone who reaches the dashboard controls the host.
  → Loopback binding, sign-in-only tunnel, an allow-list of fault names (unknown names give 404) and no general container API.
- **Real-time checks under host load.** V12–V16 use wall-clock time in containers.
  → Each check measures from the event timestamps logged in the container, and the stack runs with the guide's CPU and memory limits. The timing-critical checks also have deterministic quick-check versions.
- **HLS adds 1–3 s of latency to the dashboard video.** This is for viewing only; the app reads RTSP directly. The dashboard shows alarm state from events, not from the video.
- **Internal networks and footage injection.** The host may not be able to push to `192.168.10.20` on an internal network.
  → Document pushing footage through `docker compose exec world ffmpeg …`, or a helper container on `poe_lan`.
- **Expired devtunnel login, or Docker group membership not active.**
  → Both are checked up front, with the exact fix printed.
- **The arm64 JetPack image is large and slow under QEMU.**
  → V18 is opt-in (`TWIN_ARM64=1`) and is not part of the Step 2 done criteria.

## Migration Plan

This is a new project, so there is nothing to migrate.

- **Rollback:** `docker compose down -v` and `./share.sh stop`.
- **Phase 2:** replaces only the `world` service with Gazebo and bridge nodes on the same RTSP URL and serial protocol.
- **Phase 3:** changes only `app/config.yaml` and `compose.yaml` per device.

## Open Questions

These need the reviewer's confirmation before Step 2.

1. **Alarm semantics (D3).** Is caution a once-per-person chime at the 3 m ring, with no reset after a caution-only visit? Does the laser start at warning, not at caution?
2. **Laser power relay (D4).** Is relay 3 on only from warning to reset? The guide names the channel but not when it switches.
3. **Watchdog reading (D5).** Does "laser off and parked within 2 s" mean the laser is off and parking has started by 2 s, with the park completing after slew? With one 50 ms report period of tolerance?
4. **Class 2 (D5).** Should fitting a non-Class-2 laser be refused, rather than only flagged?
5. **Weather switching (D8).** Is a live switch over the control port acceptable instead of restarting the world container?
6. **Exposure (D6, D7).** Is it acceptable to put the dashboard on `127.0.0.1:8080` instead of `8080:8080`, to publish 9200 on loopback only, and to add the camera to `sim_ctrl` for the browser video?
7. **The 37 checks (D14).** Are the 27 V-rows plus U01–U10 an acceptable definition, given that the original smoke tests are unavailable?
8. **Power model start condition (D13).** Is a full battery at sunset after a clear day the right start? It reproduces every guide figure to within 1.3 points.
