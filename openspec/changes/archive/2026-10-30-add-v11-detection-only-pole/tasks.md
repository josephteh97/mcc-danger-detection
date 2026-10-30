## 1. Profiles

- [x] 1.1 Move `site.yaml` to `sites/phase1.yaml` unchanged; make `site.yaml` a selector (`profile: phase1`); update the site loader
- [x] 1.2 Make the five existing quick-check scripts load `phase1` explicitly
- [x] 1.3 Add `sites/v11.yaml` (stand 9.5 m south, camera 3.8 m, pivot 1.1 m, v11 products) and `app/config.v11.yaml` (guide thresholds verbatim, `identify.enabled: false`, `detector.miss_model: pixel_height`, `detector.tiles: true`)
- [x] 1.4 Verify: `python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py` still gives 36 PASS + V11 known fail

## 2. Legacy identification

- [x] 2.1 Add `IdentityProvider` and wrap the `identify()` stub as the default provider; keep `app/identify.py`
- [x] 2.2 Import and call the provider in `app/main.py` only when `identify.enabled` is true
- [x] 2.3 Add the PDPA gate for face-recognition providers
- [x] 2.4 Add `tests/legacy/` with a `--legacy` option in `tests/conftest.py`; move identification tests there
- [x] 2.5 Mark `ptz_4mp_25x_hik_ds2de4425iwde` `legacy: true`
- [x] 2.6 Verify: `pytest tests/` reports legacy tests as skipped; `pytest --legacy tests/legacy` passes

## 3. Catalogue

- [x] 3.1 Add the `switch`, `router`, `power_conv` and `monitor` folders with `_schema.yaml`
- [x] 3.2 Add the v11 products with `source`, `verified`, `price_sgd`, `watts_typ`, `watts_max`, `poe_class` and camera `dori_fp_px`
- [x] 3.3 Add plan totals excluding legacy products
- [x] 3.4 Verify: `python3 tests/smoke_catalog.py` (U09 covers both profiles)

## 4. Detection coverage

- [x] 4.1 Distortion q, D and density in `catalog/effects.py` with exact optical-axis depth
- [x] 4.2 Processed-image density from `detector.input_px` or tiles
- [x] 4.3 `tools/coverage.py`: largest-zone solver (both methods), placement and height windows, ring grid check, `/api/coverage` data for the heatmap
- [x] 4.4 Pixel-height miss model and tiling flag in `app/detect.py`
- [x] 4.5 Verify: U11–U16 pass

## 5. Ethernet laser controller

- [x] 5.1 `TcpLine` adapter in `app/links.py` with reconnect every second
- [x] 5.2 Arm and relay emulators listen on TCP at `192.168.10.24` in the v11 profile; compose service joins `poe_lan`
- [x] 5.3 Orin entrypoint skips `socat` in v11 and execs the v11 config
- [x] 5.4 Laser geometry: pivot below camera, 5°–45° stops, reach check
- [x] 5.5 Verify: U26 passes; `python3 tests/smoke_links.py` unchanged

## 6. Pole network and power

- [x] 6.1 `devices/poe_model.py` port map, draw and class reservation
- [x] 6.2 `tools/network.py` per-link load and monthly 4G data
- [x] 6.3 `devices/power_model.py --profile v11 --plan A|B|C` with conversion losses, socket schedule, monitor alerts and two-stage shutdown with hysteresis
- [x] 6.4 Verify: U17–U23 pass; V10 and V11 unchanged

## 7. Faults

- [x] 7.1 Switch hang, router-driven restart, AI box hang with PoE watchdog, site power cut in the dashboard fault table
- [x] 7.2 Verify: U24 and U25 pass; live recovery scenarios added to `tests/test_stack.py` pass

## 8. Remote access

- [x] 8.1 Check `share.sh` already matches the updated spec (options refused while sharing, lock, failed-start clean-up); add tests for the three new scenarios
- [x] 8.2 Add a Tailscale-node emulator on the router (`wan_4g` + `poe_lan`, subnet route `192.168.10.0/24`) and engineer and superior client containers
- [x] 8.3 Add the cloud relay emulator that the AI box connects out to; no inbound port on the router's 4G side
- [x] 8.4 Verify: engineer SSH to the AI box succeeds, superior cannot reach `poe_lan`, the 4G scan finds no open port, and remote switch restart works during a switch hang

## 9. Rendering

- [x] 9.1 World: 1600×1200 v11 frames, distortion remap, ground texture, postured shaded workers with shadows, IR night and noise; keep 15 fps on one core
- [x] 9.2 Postures in the world and oracle boxes; squatting scenario script
- [x] 9.3 Dashboard: vendor and pin new three.js add-ons
- [x] 9.4 Dashboard: PBR, tone mapping, sky and sun, soft shadows, rain and haze, floodlight cone
- [x] 9.5 Dashboard: rigged workers, wheeled stand and solar skid, true frustum, laser glow
- [x] 9.6 Dashboard: px/m heatmap, HUD panels, quality presets
- [x] 9.7 Verify: ffprobe shows 1600×1200 H.264 yuv420p in v11; medium preset ≥ 30 fps at 1080p on integrated graphics

## 10. Trial mode

- [x] 10.1 C squat and K kneel keys; no movement while down
- [x] 10.2 Verify: `python3 tests/smoke_trial.py` (V29–V34, U10) still passes and the squat scenario fires the alarm

## 11. Validation

- [x] 11.1 `tests/smoke_v11.py` with U11–U26 using `tests/_check.py`
- [x] 11.2 Update README check counts (53 checks, 52 PASS + V11 known fail)
- [x] 11.3 Verify: full six-script chain; `openspec validate add-v11-detection-only-pole --strict`
