# validation-suite Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Quick checks
The twin SHALL provide six quick-check scripts that need no Docker stack. They SHALL run in a Python virtual environment with:

`python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py && python3 tests/smoke_v11.py`

The first five scripts SHALL run on the phase-1 profile whatever `site.yaml` selects. Together the six SHALL run exactly these 53 named checks:

| Script | Checks |
|---|---|
| `smoke.py` | V01, V02, V03, V04, V05, U01 (homography round trip), U02 (edge distance), U03 (missed frame does not repeat the caution), V10, V11 |
| `smoke_links.py` | V06, V07, V08, V09, U04 (aim angles), U05 (relay protocol), U06 (servo slew rate) |
| `smoke_weather.py` | V19, V20, V21, V22, U07 (all 16 presets render), U08 (3-day battery per preset) |
| `smoke_catalog.py` | V23, V24, V25, V26, V27, V28, U09 (every catalogue file validates and site.yaml fits) |
| `smoke_trial.py` | V29, V30, V31, V32, V33, V34, U10 (two workers: laser follows the one inside; reset only when both are clear) |
| `smoke_v11.py` | U11 (distortion q and D), U12 (ring density with tiles), U13 (shrunken input fails as expected), U14 (largest-zone solver), U15 (pose inside windows), U16 (stand too close flagged), U17 (PoE budget), U18 (undersized switch fails as expected), U19 (4G data), U20 (PoE++ losses), U21 (continuous load), U22 (Plan B 3 overcast days), U23 (Plan A weekend shutdown order), U24 (no identity in v11), U25 (watchdog restart, model only), U26 (laser reach) |

U13 and U18 SHALL pass when the bad configuration is correctly rejected. Each check SHALL print one line: its ID, PASS or FAIL, the measured value and the pass criterion.

#### Scenario: Expected result
- **WHEN** the quick-check chain runs on a host with the Python dependencies installed
- **THEN** 52 checks print PASS
- **AND** V11 prints FAIL with "runs flat", marked as a known fail (second finding)
- **AND** the whole chain completes

#### Scenario: Laser reach finding
- **WHEN** U26 finds the alarm zone's far corner beyond the 5° stop's reach
- **THEN** it prints FAIL with the shortfall in metres and is reported as a design finding, not hidden

### Requirement: Known-fail handling
Each script SHALL exit with status 0 when every check matches its expected outcome. Every check is expected to pass except V11, which is expected to fail.

A script SHALL exit non-zero, naming the check, when any check deviates:
- a check expected to pass fails
- V11 unexpectedly passes, which means the matrix needs updating

This keeps the `&&` chain running through the known fail.

#### Scenario: Known fail does not stop the chain
- **WHEN** `smoke.py` reports V11 as FAIL (known)
- **THEN** it exits 0 and the next script in the chain runs

#### Scenario: Regression stops the chain
- **WHEN** a change makes V02 fail
- **THEN** `smoke.py` exits non-zero, naming V02

#### Scenario: Known fail fixed
- **WHEN** a change to the power defaults makes V11 pass
- **THEN** `smoke.py` exits non-zero with a message that V11 now passes and the matrix needs updating

### Requirement: Full-stack suite
`pytest tests/ -v --junitxml=reports/twin-<date>.xml` SHALL run the full-stack checks against a stack started with `docker compose up -d --build`. The full-stack checks are V12, V13, V14, V15 and V16, plus the fault-table behaviours.

Checks that cannot run in Phase 1 SHALL be reported as skipped, with the reason:
- **V17:** detector accuracy, which needs recorded site footage.
- **V18:** the arm64 install. It runs only when `TWIN_ARM64=1` is set, because it builds the JetPack image under QEMU.

If the stack is not running, the full-stack tests SHALL be skipped with that reason, and the quick checks SHALL still be collected by pytest.

#### Scenario: Full suite against the live stack
- **WHEN** the stack is up and `pytest tests/ -v --junitxml=reports/twin-$(date +%F).xml` runs
- **THEN** V12–V16 run against the stack, V17 is skipped (needs footage), V18 is skipped unless `TWIN_ARM64=1`, and a JUnit XML report is written to `reports/`

#### Scenario: Stack not running
- **WHEN** pytest runs with no stack up
- **THEN** the full-stack tests are skipped with "stack not running", and the quick checks still run

### Requirement: Regression checks for the fixes to the guide's snippets
The pytest suite SHALL check that each fix to the guide's snippets (design D18) stays in place. `tests/test_compose.py` SHALL need no Docker. The live checks in `tests/test_stack.py` SHALL run with the full-stack suite. None of these SHALL count among the 37 quick checks.

| Fix | Static check (`tests/test_compose.py`) | Live check (`tests/test_stack.py`) |
|---|---|---|
| World pipeline in `world/entrypoint.sh` | the world service has no `command:`; the script parses; its one ffmpeg command holds the encoder and the RTSP output | the browser stream is H.264 |
| Fixed addresses outside `ip_range` | every fixed address is inside its subnet and outside the dynamic range | each service holds its fixed address |
| `-pix_fmt yuv420p` | set on the encoder output | the browser stream is `yuv420p`, 1280×720 |
| PulseAudio daemon and stale state | the daemon package is installed and the `horn` sink is loaded | `docker exec … pactl list short sinks` shows `horn`, also after V16's power cut |
| Arm-USB command run directly | none | the guide's `pkill` stops only the arm bridge |

#### Scenario: Static checks without Docker
- **WHEN** `pytest tests/test_compose.py` runs on a host without Docker
- **THEN** every check runs and passes

#### Scenario: A fix is undone
- **WHEN** the world's pipeline goes back to a folded `command:`, a fixed address moves into the dynamic range, or the encoder loses `-pix_fmt yuv420p`
- **THEN** `pytest tests/test_compose.py` fails and names the problem

### Requirement: Validation matrix traceability
Every check V01–V34 in the guide's validation matrix SHALL map to exactly one test. Its pass criterion SHALL be the one in the matrix:

| ID | Check | Where it is specified |
|---|---|---|
| V01–V04 | alarm sequence and timings | `alarm-app` |
| V05 | foot accuracy under 0.35 m at 9 m | `alarm-app` |
| V06–V08 | laser interlock, aim and fire, watchdog | `device-emulators` |
| V09 | uplink outage | `alarm-app` |
| V10, V11 | power over 2 and 3 overcast days | `device-emulators` |
| V12 | end-to-end latency | `alarm-app` |
| V13, V14, V16 | Orin hang, camera cable cut, power cut | `virtual-cables` |
| V15 | two workers | `alarm-app` |
| V17 | detector accuracy, at least 95% of walk-ins detected and at most 2 false alarms a day | this spec |
| V18 | arm64 install | `orin-sandbox` |
| V19, V20, V22 | weather | `weather-presets` |
| V21 | mast sway | `world-simulator` |
| V23–V28 | products | `product-catalogue` |
| V29–V32 | trial keys and walk-in | `human-trial-mode` |
| V33 | site boundary | `world-simulator` |
| V34 | keys over the network | `world-simulator` and `human-trial-mode` |

#### Scenario: Detector accuracy (V17)
- **WHEN** YOLO mode runs on recorded site footage of staged walk-ins, pushed to the camera URL with `ffmpeg -re -stream_loop -1`
- **THEN** at least 95% of the staged walk-ins are detected and there are at most 2 false alarms per day of footage

#### Scenario: Every ID has a test
- **WHEN** the tests are listed
- **THEN** each of V01–V34 is the ID of exactly one test

