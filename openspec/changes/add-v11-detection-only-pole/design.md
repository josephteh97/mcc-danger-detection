## Context

The twin (`josephteh97/mcc-danger-detection`) is a Docker Compose stack that models the phase-1 pole from the 14 October guide: a world renderer publishing RTSP through MediaMTX, an Orin sandbox running `app/`, device emulators behind `socat` serial cables, Mosquitto, a FastAPI dashboard with a three.js view, and quick checks pinned to the guide (V01–V34, U01–U10). Hardware list version 11 (30 October 2026) replaces most of the pole: a 12 MP camera on a 3.5–4 m wheeled stand doing detection only, a reComputer Super J4012 on PoE++, the laser controller on Ethernet, a 24 V bus with three power plans and a staged shutdown, and remote management through a 4G router.

## Goals / Non-Goals

**Goals:**
- Check every version 11 design number (coverage, PoE, data, power, laser reach) with a quick check before purchase.
- Run the stack in a `v11` profile without breaking any phase-1 check.
- Keep identification as switched-off legacy code that can be turned back on.
- Make the camera image and the 3D view good enough to judge coverage, night, weather and the laser dot.

**Non-Goals:**
- Changing the alarm state machine or the guide's thresholds.
- Electrical simulation below watts, volts and state of charge.
- Training a detector; the `yolo` mode stays as it is apart from tiling.

## Decisions

### D1. Profiles, not a fork
`site.yaml` becomes a one-line selector (`profile: v11`) with `sites/phase1.yaml` (today's file, moved unchanged) and `sites/v11.yaml`. The app reads `app/config.yaml` (phase 1) or `app/config.v11.yaml`. The five existing quick-check scripts load the phase-1 profile explicitly, so their results cannot change. *Alternative:* edit `site.yaml` in place; rejected because V-checks would drift from the guide.

### D2. Guide thresholds stay
The 1.5 m and 3 m buffers, the dwell and reset times and the 2 s watchdog are copied verbatim into `config.v11.yaml`. Version 11 changes how people are seen, not when the alarm fires.

### D3. Identification as a provider behind a flag
`app/identify.py` is kept. A small `IdentityProvider` interface wraps today's stub as the default provider; `app/main.py` imports it only when `identify.enabled` is true. The PTZ product gets `legacy: true`. Tests go to `tests/legacy/`, run with `pytest --legacy`. A face-recognition provider must pass a PDPA gate (consent records and retention days declared) before start-up. *Alternative:* delete the stub; rejected because the user may need identification again.

### D4. Camera and density
New catalogue fields `dori_fp_px`, `native_w_px`, `native_h_px`, `hfov_deg`. `catalog/effects.py` computes q, D and density g·(f/p)/z with exact optical-axis depth. The world renders 1600×1200 (4:3) so the stream stays light, but density and the oracle's box heights use the native 4,000×3,000 maths. The oracle's miss model reads the box's height in the processed image (`detector.input_px` or tiles). Reference: 12 MP Hikvision, q = 0.571, D = 0.844; field-of-view method 11.5 m @ 10.4 m, distortion method 11.2 m @ 17.1 m.

### D5. Ethernet laser controller
`app/links.py` gains a `TcpLine` adapter with the serial link's methods. In `v11` the arm (7001) and relay (7002) emulators listen on `192.168.10.24` on `poe_lan`; the line protocols do not change. Phase 1 keeps `socat` and `usb_bus`.

### D6. Laser geometry on the stand
Pivot 1.1 m up directly below the camera, stops 5°–45° below horizontal. Reach at the 5° stop is 1.1/tan 5° = 12.57 m. The v11 stand sits 9.5 m south of the pit centre so the alarm zone's far corner (12.1 m) is in reach; at 10 m it would miss by 2 cm. U26 checks this.

### D7. Power profile v11
`devices/power_model.py --profile v11 --plan A|B|C`. Loads come from catalogue watts; efficiencies step-up 94%, cable 97%, splitter 90%, 24→12 V 92%; solar keeps the repo's 70% system efficiency and weather sun factors. Battery monitor alerts at 50/30/10%; Stage 1 at 30% (back at 40%), Stage 2 at 10% (back at 20%); router last. The phase-1 model and V10/V11 are untouched.

### D8. Network model
`devices/poe_model.py` holds the port map and checks actual draw and class reservation (135.4 W) against the switch budget (240 W). `tools/network.py` sums stream bitrates per link and estimates 4G data a month (baseline about 15 GB against a 30 GB plan).

### D9. v11 faults
The dashboard fault table adds switch hang, router-driven switch restart, AI box hang with a PoE watchdog (ping every 10 s, power-cycle after 3 misses, implemented in the devices container through the existing fault API's pause/unpause), and a site power cut that hands over to the power profile.

### D10. Rendering
- **World (OpenCV, CPU):** ground texture, shaded postured workers with shadows, barrier lines, distortion remap from D (precomputed map), IR monochrome at night with fall-off, light-dependent noise. Must keep 15 fps at 1600×1200 on one CPU core; the remap map is computed once.
- **Dashboard (three.js):** PBR materials, ACES tone mapping, sky and sun by time of day, soft shadows limited to stand and workers, rain and haze, floodlight cone, rigged workers, true frustum, laser glow (bloom), px/m heatmap from `/api/coverage`, HUD panels, quality presets. New add-ons vendored and pinned.

### D11. New quick checks
`tests/smoke_v11.py` runs U11–U26 with the existing `@check` helper in `tests/_check.py`. U13 and U18 assert that bad configurations are rejected. U25 tests the watchdog logic as a model; the live recovery scenario runs in `tests/test_stack.py`.

### D12. Remote access
`share.sh` already behaves as the updated spec says; the delta only records it. The v11 pole's own remote paths are emulated: a Tailscale-node container stands for the router (subnet route to `poe_lan`), plus an engineer client, a superior client and a cloud relay. The real Tailscale service is not used, so nothing leaves the internal networks. *Alternative:* run real Tailscale in the containers; rejected because the twin's networks must stay offline.

## Risks / Trade-offs

- **Hikvision publishes no pixel size or DORI basis** → both coverage methods are reported; the report flags the range.
- **Oracle miss model may be optimistic** → conservative curve; compare with `yolo` mode on rendered frames when a model is available.
- **Laser reach is marginal** (2 cm short at 10 m) → stand fixed at 9.5 m in the v11 profile; U26 fails loudly if the pose changes.
- **Rendering cost** → low preset; world image stays CPU-only.
- **Profile split adds config files** → one selector line and a loader test (U09 still covers the active profile).

## Migration Plan

1. Move `site.yaml` to `sites/phase1.yaml`; make `site.yaml` select `phase1`; run the five existing scripts (still 36 PASS + V11 known fail).
2. Add the v11 profile, catalogue and models; run `smoke_v11.py`.
3. Switch the selector to `v11`; bring the stack up; run `tests/test_stack.py`.
Rollback: set `profile: phase1`.

## Open Questions

- Exact 4G router model (RS485 port and digital output for the switch relay).
- PoE class of the chosen IP horn (class 4 assumed).
- Whether the ESP32 laser controller will speak the line protocol over TCP or a binary UDP frame on site (the adapter hides either).
