# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker-based digital twin of a danger-zone pit alarm pole (camera, Orin AI box, horn, strobe, floodlight, laser arm, solar power). The real alarm software in `app/` runs **unchanged** inside an Orin-shaped sandbox container, so passing checks here exercise the code that ships to the pole. Every other container stands in for the site, a device or a cable.

The source of truth is the "Danger-Zone Pole Digital Twin: Linux Implementation Guide". Current specs live in `openspec/specs/`; phase 1's proposal, design and tasks are archived in `openspec/changes/archive/2026-10-29-add-digital-twin-phase1/`. Any deviation from the guide must be recorded in a `design.md` (phase 1's, or the new change's) and the README's "Deviations" list. Validation IDs V01–V34 come from the guide's test matrix; U01–U10 are extra unit checks. OpenSpec workflow skills/commands are in `.claude/` (`/opsx:propose`, `/opsx:apply`, …).

## Commands

Setup: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt` (`pygame` optional, for trial mode).

Quick checks (no Docker), each script is standalone:
```bash
python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py \
  && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py && python3 tests/smoke_v11.py
```
Expected: **53 checks, 52 PASS, 1 known FAIL (V11)**. The first five scripts always load the phase-1 profile (36 PASS + V11); `smoke_v11.py` runs U11–U26 on v11. Legacy identification tests: `pytest --legacy tests/legacy`. `tests/_check.py` holds `KNOWN_FAIL`; a script exits 1 on any regression *or* if V11 starts passing (then update the matrix).

pytest (quick checks via `test_quick.py`, static compose checks via `test_compose.py`, full stack via `test_stack.py`):
```bash
pytest tests/ -v --junitxml=reports/twin-$(date +%F).xml
pytest tests/test_quick.py -k V02            # one quick check (param ids are check IDs)
pytest tests/test_stack.py::test_V12_end_to_end_alarm_latency -s
pytest tests/test_compose.py                 # no Docker needed
```
Full-stack tests auto-skip with "stack not running" unless all six `twin-*-1` containers are up and the dashboard answers `/healthz`. Env overrides: `TWIN_DASHBOARD`, `TWIN_PROJECT`.

Stack:
```bash
docker compose up -d --build                         # v11 pole; dashboard at http://localhost:8080
docker compose -f compose.yaml -f compose.phase1.yaml up -d --build    # phase-1 pole (USB cables)
WEATHER=night_rain SCENARIO=idle docker compose up -d --build
docker compose down
```

Tools: `python3 -m tools.trial [--headless]`, `python3 -m tools.compare <category> <a> <b> --weather ...`, `python3 -m tools.evaluate logs/run-<time>`, `python3 devices/power_model.py --days 3 --weather overcast`. Remote sharing: `./share.sh start|status|stop` (devtunnel; never anonymous — see README).

## Architecture

```
world (renderer | ffmpeg) ─RTSP push─► camera (MediaMTX) ─RTSP on poe_lan─► orin (app) ─wan_4g─► cloud (Mosquitto)
world ─UDP 9100 ground truth─► orin (oracle detector), dashboard
devices (arm + relay emulators, socat TCP 7001/7002) ─usb_bus─► orin /dev/ttyARM, /dev/ttyRELAY
dashboard (FastAPI :8080, Docker socket) ─ HLS from camera, /logs, MQTT, world control :9200
```

- **Networks are the cables.** `poe_lan` (Ethernet), `usb_bus` (USB serial), `wan_4g` (4G) are internal; `sim_ctrl` is the twin's own control/video network. Faults are injected by disconnecting networks, `tc netem` on the Orin's WAN interface, killing socat, or `docker pause/kill` — the dashboard does this through the Docker socket (`dashboard/faults.py`).
- **Fixed IPs sit below each subnet's `ip_range`** (dynamic addresses come from the top half). `test_compose.py` enforces this and other guide-snippet fixes (world pipeline in `world/entrypoint.sh` not a folded `command:`, `-pix_fmt yuv420p`, `pulseaudio` daemon package). Keep those tests passing when editing `compose.yaml` or Dockerfiles.
- **Only loopback ports are published**: 127.0.0.1:8080 (dashboard, holds the Docker socket) and 127.0.0.1:9200/udp (trial keypad).
- **App pipeline** (`app/main.py`, `PoleApp`): capture (`health.FrameSource`) → detect (`detect.py`: `oracle` reads world truth over UDP with delay/miss rate; `yolo` ONNX) → track (`track.IoUTracker`) → `alarm.AlarmFSM` → act (`links.py`: arm aim angles, relays, `horn.py` PulseAudio sink) → upload (`links.Uplink`, SQLite queue at `/data/queue.db` so events survive 4G outages, published to MQTT). Status written to `/data/status.json`; homography from `/data/calib/homography.npy` (written by the one-shot `calib` service via `tools/calibrate.py`).
- **Safety logic is pure functions** in `app/alarm.py` and `app/links.py` (zone geometry, FSM caution→warning→alarm→reset, aim angles, uplink queue), tested without hardware. App code uses `time.monotonic()`.
- **Emulators expose the real device interface.** Swapping in real hardware should change only `app/config.yaml` and `compose.yaml`, never app code; protocol differences go in `links.py` adapters (`LineRelayAdapter`/`HexRelayAdapter`).
- **Profiles**: `site.yaml` is a selector (`profile: v11|phase1`, `$TWIN_PROFILE` overrides) for `sites/<profile>.yaml`; the app runs `app/config.yaml` (phase 1) or `app/config.v11.yaml`. v11 adds the Ethernet laser controller (`app/links.TcpLine`), the coverage maths (`catalog/effects.py`, `tools/coverage.py`), PoE/4G/power models (`devices/poe_model.py`, `tools/network.py`, `devices/power_model.py --profile v11`), the emulated router/Tailscale/cloud relay (`remote/`), and the dashboard what-if panel (`dashboard/v11.py`). Change spec: `openspec/changes/archive/2026-10-30-add-v11-detection-only-pole/`.
- **Site and products**: `sites/<profile>.yaml` (pit, zones, camera/arm pose, fitted products, power loads; metres, origin at pit centre, x east/y north) is read by world, tools and tests via `catalog.load_site()`. `catalog/<category>/` holds `_schema.yaml` plus one YAML per product; files are validated against the schema. `catalog/effects.py` turns specs into simulation numbers for comparisons. `app/config.yaml` duplicates the pit and thresholds for the Orin side.
- **World** (`world/`): `world.py` writes raw BGR frames to stdout piped into ffmpeg, sends per-frame truth over UDP, and takes control messages (keys, weather presets from `weather.py`, scenarios from `scene.py`) on UDP 9200 — weather/scenario switch live, no restart.
- **Orin image** has a fast x86 flavour (default) and a JetPack arm64 flavour (`ORIN_BASE` / `--build-arg BASE=...`).

## Conventions

- Use the guide's numeric thresholds verbatim (1.5 m alarm buffer, 3 m warn ring, 1 s dwell, 3 s escalate, 2 s clear, 2 s watchdog).
- In OpenSpec specs, tag scenarios that implement a guide check with its ID, e.g. "(V02)"; each task group ends with its verify command.
- New quick checks register with `@check("ID", "title")` from `tests/_check.py` and return `(passed, measured, criterion)`.
- Commits carry no AI co-author or "Generated with" attribution lines.
