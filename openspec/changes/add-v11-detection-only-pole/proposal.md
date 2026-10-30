## Why

Phase 1 models the pole from the 14 October guide: an 8 MP camera on a 6.5 m trailer mast, an Orin Nano Super, a laser arm and relay board on USB, 100 Ah and 500 W of solar. Hardware list version 11 (30 October 2026) changes most of that:
- One 12 MP camera on a 3.5–4 m wheeled cabinet stand does human detection only, sized at 100 px/m in the image the detector processes (100 px for a 1.0 m squatting worker).
- The AI box is a Jetson Orin NX 16 GB (reComputer Super J4012) powered over PoE++.
- The laser controller and its relays sit on Ethernet.
- Power is one 24 V bus with a primary plan (shared site power) and two backups (solar; solar + charger), with a battery monitor and a two-stage low-battery shutdown.
- Remote management is part of the design: Tailscale VPN, cloud relay, PoE watchdog and a router-driven switch restart.

The twin must model version 11 so its numbers can be checked before purchase, without breaking the phase-1 guide checks (V01–V34, U01–U10) that pin the original design. Face recognition is not used in version 11 but may come back, so the identification hook stays as switched-off legacy code. The dashboard's 3D view and the world's camera image also need better rendering to judge coverage, night, weather and the laser dot.

## What Changes

- Add a `v11` site and app profile next to the phase-1 one. The guide checks keep running on the phase-1 profile, unchanged; the stack and the new checks default to `v11`.
- Add the version 11 products to the catalogue (12 MP Hikvision camera, wheeled stand, managed PoE switch, step-up converter, PoE++ splitter, 4G router with Wi-Fi, PoE injector, battery monitor and relays, 50 Ah battery, 240 W supply, 230 V charger), with new categories and a `legacy: true` flag.
- Add detection coverage: camera density with barrel distortion (D from the datasheet), processed-image density for the detector's input size, the largest-zone solver (B1–B8, F1–F12), stand placement and height windows, and a pixel-height-based miss model for the oracle detector.
- Keep the alarm state machine and the guide's thresholds unchanged (1.5 m, 3 m, 1 s, 3 s, 2 s, 2 s watchdog). In `v11`, the identify step only runs when `identify.enabled: true` (default false).
- Move the arm and relay links from virtual USB to Ethernet in `v11`: the same line protocols over TCP to the laser controller at `192.168.10.24` on `poe_lan`; phase 1 keeps the USB cables.
- Laser geometry for the stand: pivot 1.1 m directly below the camera, hardware stops 5°–45° below horizontal, and a reach check against the 1.5 m alarm zone.
- Add pole network and power models: PoE port map with class reservation against a 240 W budget, stream bitrates and monthly 4G data, the 24 V bus with conversion losses, Plans A/B/C, battery state of charge, battery-monitor alerts and the two-stage shutdown. The phase-1 power model and V10/V11 stay as they are.
- Add v11 faults: switch hang, PoE watchdog restart, router-driven switch restart, site power cut, and low battery stages.
- Keep face recognition as legacy: the `identify` hook becomes an optional `IdentityProvider` behind a flag; PTZ and identification products stay in the catalogue marked `legacy: true`; legacy tests run with `--legacy`.
- Improve rendering:
  - **World camera image (OpenCV):** 4:3 stream at 1600×1200, barrel distortion, worker postures (walk, stand, squat, kneel) with shading and shadows, ground texture, IR monochrome at night with IR fall-off, sensor noise.
  - **Dashboard 3D view (three.js):** physically based materials, sky and sun by time of day, soft shadows, rain and haze, floodlight cone at night, rigged workers with postures, the wheeled stand and solar skid, a px/m ground heatmap, the camera's true frustum, a laser beam with glow, and HUD panels for alarm, power, PoE and 4G, with quality presets.
- Remote access: bring the `share.sh` spec up to date (options refused while sharing, one start or stop at a time, clean-up after a failed start) and model the v11 pole's own remote paths (Tailscale for engineers, cloud relay for the superior, no inbound 4G port).
- Add trial-mode posture keys (C squat, K kneel).
- Add quick checks U11–U26 in a new `tests/smoke_v11.py`.

## Capabilities

### New Capabilities
- `detection-coverage`: Camera density with distortion, processed-image density, largest-zone solver, placement and height windows, and the pixel-height miss model.
- `legacy-identification`: The identification hook kept as switched-off legacy code, its interface, legacy products and legacy tests, and the data-protection gate.
- `pole-network-power`: PoE port map and budget, stream bitrates and 4G data, the 24 V bus and conversion losses, Plans A/B/C, battery monitor and two-stage shutdown, and the v11 remote-management faults.

### Modified Capabilities
- `alarm-app`: Identify step behind a flag; detector modes gain the processed-density miss model.
- `world-simulator`: Camera rendering for the 12 MP stand camera and better image rendering; worker postures.
- `product-catalogue`: New categories and products for version 11; `legacy` flag.
- `dashboard`: Improved 3D view and HUD panels.
- `human-trial-mode`: Posture keys.
- `orin-sandbox`: Arm and relay links over Ethernet in the `v11` profile.
- `device-emulators`: Relay emulator reachable over Ethernet; power model profiles.
- `virtual-cables`: Laser controller on `poe_lan`; `usb_bus` used only by the phase-1 profile.
- `remote-access`: `share.sh` behaviour added since phase 1; v11 pole remote paths (Tailscale, cloud relay) and remote restart during faults.
- `validation-suite`: New quick-check script and counts.

## Impact

- **Changed code:** `site.yaml` (becomes the profile selector), new `sites/phase1.yaml` and `sites/v11.yaml`, `app/config.v11.yaml`, `catalog/` (new categories and products), `catalog/effects.py` (coverage maths), `app/detect.py` (miss model), `app/links.py` (TCP line transport), `app/identify.py` and `app/main.py` (provider interface and flag), `world/` (renderer), `devices/` (power and PoE models, relay over TCP), `dashboard/static/` (3D view), `tools/trial.py` (posture keys), `tests/smoke_v11.py`, `tests/legacy/`, `compose.yaml` (Tailscale-node, engineer and superior client emulators), `share.sh` (no behaviour change; spec catches up).
- **Unchanged:** the alarm state machine, its thresholds, the uplink queue, the MQTT topics and the phase-1 checks (still 36 PASS + known-fail V11 on the phase-1 profile).
- **Interfaces:** the arm and relay line protocols are unchanged; only the transport moves to TCP. The camera URL keeps the same path.
- **New vendored front-end files:** three.js add-ons for post-processing (bloom), environment lighting and model loading, pinned like the existing vendor files.
