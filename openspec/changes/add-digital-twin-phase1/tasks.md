## 1. Project setup (Step 2 starts here)

- [ ] 1.1 Create the layout from the guide at the repo root: `world/`, `devices/`, `app/`, `orin/`, `dashboard/`, `catalog/`, `tools/`, `tests/`, `cloud/`, `logs/` (git-ignored), `reports/` (git-ignored)
- [ ] 1.2 Add `requirements-dev.txt` (numpy, opencv-python-headless, pyyaml, paho-mqtt, pytest, fastapi, uvicorn, docker, httpx) and `app/requirements.txt` (the Orin app's runtime dependencies only)
- [ ] 1.3 Write `site.yaml`: pit, zone settings, camera pose (6.5 m up, about 8 m from the pit, 90° HFOV), arm pose, site boundary and the fitted `products:`
- [ ] 1.4 Verify: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt` succeeds

## 2. Alarm app core (`alarm-app`)

- [ ] 2.1 `app/alarm.py`: `ground_from_image`, `edge_distance`, `Config`, `AlarmFSM` with the levels, events, timings and 2 s track persistence from design D3
- [ ] 2.2 `app/links.py`: `aim_angles`, `SerialLine`, `RelayAdapter` (line protocol now, hex-frame adapter stub for site), `ArmLink` (AIM, LASER, HB, PARK; parses POS; "arm offline" detection), and `Uplink` (SQLite queue, QoS 1, in order, delete after PUBACK)
- [ ] 2.3 `app/detect.py`: oracle mode (UDP truth, delay, jitter, miss rate, IDs removed) and the YOLO-mode interface (ONNX loader, not part of Phase 1 acceptance)
- [ ] 2.4 `app/track.py`: IoU tracker that keeps tracks through short gaps
- [ ] 2.5 `app/identify.py`: stub returning "unknown"
- [ ] 2.6 `app/health.py`: capture reader thread, 3 s frame-age watchdog, "camera offline" alert queued to the uplink, reopen with backoff
- [ ] 2.7 `app/main.py`: the guide's loop: capture, detect, track, alarm, act (horn tones on `horn`, relays per design D4, floodlight schedule), aim, uplink flush
- [ ] 2.8 `app/config.yaml` with the guide's twin values
- [ ] 2.9 Verify: `python3 tests/smoke.py` shows V01–V04, U01–U03 PASS

## 3. Device emulators (`device-emulators`)

- [ ] 3.1 `devices/arm_emulator.py`: pty via `--link`, AIM, LASER, HB and PARK in, POS out every 50 ms, 180°/s slew, ≥1° tilt interlock on the actual angle, 2 s watchdog with park, JSONL state to `--state`
- [ ] 3.2 `devices/relay_emulator.py`: `R <ch> <0|1>`, replies `OK` or `ERR`, channels 1 to 4, JSONL state to `--state`
- [ ] 3.3 `devices/power_model.py`: hourly model, defaults and start condition from design D13, product overrides, lowest-charge report
- [ ] 3.4 `devices/horn_monitor.py`: the guide's parec peak detector as a module
- [ ] 3.5 Verify: `python3 tests/smoke_links.py` shows V06–V09, U04–U06 PASS; `python3 tests/smoke.py` shows V10 PASS and V11 FAIL (known)

## 4. World simulator and weather (`world-simulator`, `weather-presets`)

- [ ] 4.1 `world/world.py`: site from `site.yaml`, pinhole camera, renderer, workers (scripted, passers-by, scenarios, controlled), site boundary, ground truth to UDP, laser dot from the arm state, frames to stdout, `--fps`, `--truth`, `--weather`, `--npcs`, `--control`
- [ ] 4.2 `image_to_ground_homography()` and a `calibrate` entry point that writes `homography.npy` without overwriting an existing file
- [ ] 4.3 `world/weather.py`: the 16 presets with visibility, sun factor, wind and storm events in one table; Koschmieder fog, rain streaks and drops, fogged window, night with and without floodlight, lightning, glare with WDR, mud and sway
- [ ] 4.4 `world/controls.py`: UDP control server (keys, add and switch worker, reset, weather, scenario), 0.5 s key timeout, `send_keys`
- [ ] 4.5 Contrast metric and foot-error measurement helpers used by the checks
- [ ] 4.6 Verify: `python3 tests/smoke_weather.py` shows V19–V22, U07, U08 PASS; `python3 tests/smoke.py` shows V05, U01 PASS

## 5. Product catalogue (`product-catalogue`)

- [ ] 5.1 `catalog/<category>/_schema.yaml` for all 8 categories, plus the 20 product files named in the guide (source, verified, price, spec fields)
- [ ] 5.2 `catalog/loader.py`: schema validation that names the missing field, `site.yaml` fitting, refusal of non-Class-2 lasers
- [ ] 5.3 Spec effects: pixels per metre and DORI, ring coverage, window drops with and without a hood, WDR darkening, floodlight lux and inverter energy, speaker margin, laser brightness and class, daily energy, cost
- [ ] 5.4 `tools/compare.py`: comparison table and picture grid (rows weather, columns product)
- [ ] 5.5 Verify: `python3 tests/smoke_catalog.py` shows V23–V28, U09 PASS; `python3 -m tools.compare camera bullet_8mp_4mm_generic dome_4mp_2_8mm_generic --weather clear,tropical_downpour` prints the table and writes the grid

## 6. Human trial mode (`human-trial-mode`)

- [ ] 6.1 `tools/trial.py`: key map, 1.4 and 3.0 m/s, multiple workers, weather cycling, rings and pause, top bar, plan view, pygame with OpenCV fallback, headless mode for tests
- [ ] 6.2 Scorecard to `logs/trial-<time>.json` (stay, warning and alarm after entry, reset after leaving, dot-to-feet distance)
- [ ] 6.3 `--send <host>:9200` keypad sender at about 10 Hz
- [ ] 6.4 `tools/evaluate.py`: score a recorded run against ground truth
- [ ] 6.5 Verify: `python3 tests/smoke_trial.py` shows V29–V34, U10 PASS

## 7. Quick-check harness (`validation-suite`)

- [ ] 7.1 `tests/_check.py`: shared reporter (ID, PASS or FAIL, measured value, criterion); expected-outcome table (V11 is a known fail); exit-code rules
- [ ] 7.2 Verify: `python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py` runs to the end with **36 PASS, 1 FAIL (V11, known)**

## 8. Containers and virtual cables (`orin-sandbox`, `virtual-cables`)

- [ ] 8.1 `orin/Dockerfile` with `ARG BASE=ubuntu:22.04`; `orin/entrypoint.sh` with socat retry loops for `/dev/ttyARM` and `/dev/ttyRELAY`, PulseAudio in system mode with the `horn` null sink, then `exec python3 -m app.main`
- [ ] 8.2 `world/Dockerfile` (python, opencv, ffmpeg), `devices/Dockerfile` (python, socat), `dashboard/Dockerfile`
- [ ] 8.3 `cloud/mosquitto.conf` (listener 1883, anonymous allowed on the internal `wan_4g` only)
- [ ] 8.4 `compose.yaml`:
  - the guide's services and networks
  - pinned image tags
  - camera also on `sim_ctrl`
  - one-shot `calib` service
  - `127.0.0.1:8080` and `127.0.0.1:9200/udp` only
  - devices logging to `/logs/arm.jsonl` and `/logs/relay.jsonl`
  - world started with `--control 0.0.0.0:9200`
- [ ] 8.5 Verify: `docker compose up -d --build`; `docker compose ps` shows the services up; `curl -fsS http://localhost:8080/` returns 200

## 9. Dashboard (`dashboard`)

- [ ] 9.1 `dashboard/server.py`: truth reader (UDP 9100), arm and relay log tailers, MQTT event subscriber, `/live` WebSocket at 15 Hz
- [ ] 9.2 `/video/` reverse proxy to MediaMTX HLS on the camera service
- [ ] 9.3 Fault endpoints with an allow-list (camera_cable, 4g_weak, 4g_outage, arm_usb, orin_hang, power_cut, each with a restore); unknown names give 404
- [ ] 9.4 Scenario, weather and trial-key endpoints relayed to `world:9200`
- [ ] 9.5 Products panel backed by the catalogue loader and `tools.compare`
- [ ] 9.6 Run recording to `/logs/run-<time>/` and the replay API
- [ ] 9.7 `dashboard/static/`: three.js scene (pit, rings, pole, camera frustum, workers, arm and beam, strobe and floodlight, level), hls.js player, trial pad with on-screen arrows, vendored libraries at pinned versions
- [ ] 9.8 Verify: open `http://localhost:8080`; the video plays, the 3D view moves, and a trial-pad walk-in shows caution, then warning, then alarm, then reset

## 10. Full-stack tests (`validation-suite`)

- [ ] 10.1 `tests/conftest.py`: docker-SDK fixtures, skip with "stack not running" when the stack is down, helpers to run scenarios and read horn-monitor, MQTT and arm logs
- [ ] 10.2 `tests/test_stack.py`: V12 (horn latency), V13 (pause leads to laser off), V14 (camera cable), V15 (two workers), V16 (power cut), plus the 4G weak and outage behaviours and the arm USB fault
- [ ] 10.3 `tests/test_quick.py`: wraps the 37 quick checks for pytest and JUnit; V17 skipped (needs footage); V18 opt-in with `TWIN_ARM64=1`
- [ ] 10.4 Verify: `docker compose up -d --build && pytest tests/ -v --junitxml=reports/twin-$(date +%F).xml && docker compose down`

## 11. Remote access (`remote-access`, Step 3)

- [ ] 11.1 `share.sh start|status|stop`:
  - checks that `devtunnel` is installed and logged in, and that `127.0.0.1:8080` answers
  - named tunnel with port 8080 only
  - repo access rule, plus optional `--org`, `--tenant` and `--expires`
  - refuses anonymous access
  - background host with its state in `.share/`
  - prints the URL
- [ ] 11.2 `.gitignore` the `.share/` directory
- [ ] 11.3 README "Remote access" section: one-time setup, start, status, stop, who can sign in, the loopback binding and why, and teardown with `devtunnel list` and `devtunnel delete`
- [ ] 11.4 Update the `remote-access` spec with anything learned while implementing
- [ ] 11.5 Verify:
  - `./share.sh start` prints the URL.
  - From another machine, sign-in is required, the video plays and a trial walk-in alarms.
  - `devtunnel show` lists only port 8080.
  - `./share.sh status` shows sharing on.
  - After `./share.sh stop`, the URL is dead and `status` shows sharing off.

## 12. Documentation and close-out

- [ ] 12.1 README: host setup, quick checks, compose up, dashboard, trial mode, fault table, and the deviations from the guide (pointing to `design.md`)
- [ ] 12.2 Verify: `openspec validate add-digital-twin-phase1 --strict` passes; archive the change after Step 3 is accepted (`openspec archive add-digital-twin-phase1`)
