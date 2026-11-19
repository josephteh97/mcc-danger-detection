## Why

The twin currently models two poles, and both are expensive. Phase 1 is the 14 October guide's pole; version 11 (30 October) is a detection-only pole whose two biggest lines alone — a 12 MP Hikvision camera at S$1,586.18 and a reComputer Super J4012 at S$1,449.00 — cost more than a whole alternative build.

Hardware list version 65 (19 November 2026) is that alternative. It is a complete, priced, link-by-link pole at **S$3,941.94**: a TP-Link VIGI C385 on a VMB-350 pole bracket, a Raspberry Pi 5 doing the detection over PoE, a 2-axis ST3215 gimbal carrying a Class 2 green laser that marks the pit edge on the ground, an IP horn, and a 48 V solar bus with a 2.56 kWh LiFePO4 pack. It is not a cut-down version 11 — it is a different architecture: a Pi instead of a Jetson, an Ethernet ESP32 aim controller plus a hardware interlock instead of a relay board, a 4G USB modem on the Pi instead of an outdoor router, no floodlight, no battery-monitor module, and an existing site tube instead of a bought mast.

Two builds that answer the same brief at a 2× cost difference is a purchasing decision, and the twin exists so that decision is made on simulated numbers rather than on a spreadsheet. Today you cannot put them side by side: `site.yaml` picks one profile, the dashboard's what-if panel is hardcoded to `v11`, and there is no catalogue home for a mount, a gimbal, a junction controller or an enclosure, so most of version 65 cannot be entered at all.

This change adds a **budget/expensive tab pair** to the twin, makes **budget the default**, and models **every one of the 36 version 65 line items one-to-one** as a catalogue entry, so that switching the tab re-runs coverage, PoE, power, 4G and cost against a real, buyable bill of materials.

## What Changes

### Build variants and the tab pair

- Add a `budget` site profile (`sites/budget.yaml`) modelling hardware list version 65. `PROFILES` becomes `("phase1", "v11", "budget")`.
- Add a `tier:` key to site profiles. `sites/budget.yaml` declares `tier: budget`; `sites/v11.yaml` declares `tier: expensive`. `sites/phase1.yaml` declares none and stays out of the pair — it is the profile the guide checks run on and must not move.
- Add a tab bar at the top of the dashboard listing every profile that declares a tier, **budget first and selected on load**. The tab sets the profile used by the what-if panel, the products panel, the coverage heatmap, the HUD figures and the cost totals.
- Change the default in `site.yaml` from `profile: v11` to `profile: budget`, so `docker compose up` brings up the budget pole and `TWIN_PROFILE` still overrides.
- The tab switches the **models**, not the running containers. When the selected tab is not the profile the stack is running, the dashboard says so and keeps the live 3D view, video and events on the running profile. Swapping the running pole stays a `TWIN_PROFILE=... docker compose up -d` operation.

### One-to-one modelling of version 65

- Every version 65 line item maps to exactly one catalogue file, and every budget catalogue file carries `bom_item: "<number>"` (`"1"`, `"1a"`, `"11c"`, …) naming the line it models. A new check asserts the mapping is a bijection: no line unmodelled, no file inventing a line, no line modelled twice.
- Add four modelled categories, each with a `_schema.yaml` whose fields drive a model:
  - `gimbal` — the 2-axis pan/tilt kit (axes, travel, hold torque, payload, supply voltage, idle and moving watts).
  - `controller` — the Ethernet aim controller and the laser interlock (interface, PoE class, watts, whether it breaks the laser supply in hardware).
  - `modem` — the 4G USB modem (bands, interface, watts, whether it carries the Tailscale node).
  - `enclosure` — the pole-top IP66 box, its pole kit and its breather (IP rating, internal volume, vented or sealed).
- Add one unmodelled category, `hardware`, with a minimal schema (`name`, `source`, `verified`, `price_sgd`, optional `watts_typ`/`watts_max`, `bom_item`) for the version 65 lines that carry cost and mass but drive no model: mounts, weatherproofing, cabling, breakers, signage, spares and the calibration board. These are totalled and listed; they are never asked for physics they do not have.
- Allow a base category to be **not fitted**: `products.<category>: null` in a site profile. The budget pole fits no `floodlight`, no `router` and no `monitor`, and the models skip them instead of the loader refusing the profile. The night models report "no floodlight fitted" rather than assuming one.
- Promote the `laser_controller:` block that `sites/v11.yaml` carries inline into the `controller` category, so both profiles get it from the catalogue and the what-if panel edits it the same way.

### Models the budget pole needs

- **48 V bus.** `power.bus_v: 48` with the version 65 conversion chain (MPPT → 51.2 V pack → DDR-60L-12 for the 12 V gimbal rail → DDR-15L-5 for the 5 V laser rail → PoE+ switch for camera, horn, Pi and aim controller). The existing 24 V maths is already parameterised on `bus_v`; this change supplies the budget chain's efficiencies and a cutoff device (`BatteryProtect 48V-100A`) in place of the two-stage shutdown's relay.
- **PoE port count and spares.** The budget pole has exactly four PoE devices (camera, horn, Pi, laser controller), which a 4-port switch would fill with nothing left for a laptop at commissioning — so version 65 fits an 8-port unit with four spare. The port map gains a hard check that device count does not exceed port count, and reports the spare count, flagging zero spare as a finding rather than a pass.
- **DC input windows against the pack's swing.** Every bus-powered product carries its input window, checked against the voltage the 16S pack can actually reach. The budget switch takes 48–56 V and the pack swings wider, so the model reports the two settings that keep the bus inside it — MPPT absorption at or below 3.50 V/cell and cutoff at or above 48 V. Configuration, not hardware, but silent damage if missed.
- **Detection on a Pi, not a Jetson.** `ai_box` gains the Pi 5 with its own `detector_fps`; the existing alarm-latency and pixel-height miss models run unchanged on it. The figures come from the Raspberry Pi 5 specification — Broadcom BCM2712, quad-core Cortex-A76 at 2.4 GHz, VideoCore VII GPU, **no NPU and no CUDA**, so detection runs on the CPU at roughly 12 fps for a YOLO-class person detector with no accelerator fitted. Version 11's Orin NX figure of 60 fps is not carried over; the budget pole's alarm latency follows from the Pi's own rate.
- **Camera placement derived, not inherited.** The budget camera's distance from the pit comes from the largest-zone solver's field-of-view method rather than from version 11's pose (see below).
- **Laser reach from a 48 V gimbal.** The existing laser-reach check runs against the budget geometry (gimbal pivot and stops from `sites/budget.yaml`), and the Class 2 fitting rule already refuses anything above 1 mW — the version 65 laser is 1 mW at 520 nm and passes.
- **4G without a router.** `tools/network.py` takes its uplink from the fitted `modem` when no `router` is fitted.

### Lightning protection

Singapore has one of the highest lightning-strike densities in the world and this pole is an isolated metal structure in open ground. Version 65 adds three lines — an air terminal (item 27), the earthing that gives it somewhere to discharge (27a) and PoE/Ethernet surge arrestors (27b) — and the twin models the first and third:

- A new `lightning` category carrying the air terminal's rod length and protective angle, and a new `spd` category carrying each arrestor's kind, line count, maximum PoE class and surge rating. The earthing kit is a `hardware` line, because its one meaningful number is a field measurement.
- A **protection-zone check**: every pole-mounted item must satisfy `r ≤ (h_tip − h)·tan(angle)` against the terminal's tip, over the camera, the gimbal head, the enclosure and the array. This ties straight into the adjustable pole height — raising the camera raises the tip height the rod needs, and the check says by how much. An array on its own frame is reported as a separate structure rather than silently included.
- An **SPD coverage check**: every conductor leaving the enclosure is enumerated from the fitted products and matched to a fitted arrestor, with the arrestor's PoE class compared against the line's duty. A profile that fits an air terminal and no arrestor is flagged — the structure would be protected and the electronics would not, since the damaging event is the induced surge from a nearby strike and needs no direct hit.
- **Earthing is measured, not catalogued**: `earthing.measured_ohm` against a 10 Ω target, plus whether the steel pole's continuity as a natural down conductor has been confirmed. Both report as outstanding until entered.

### Cost reconciliation

- Add a cost reconciliation check: the budget profile's catalogue total SHALL equal the version 65 total for the lines the catalogue holds.
- The authoritative figure is **S$3,941.94**, the sum of the version 65 item rows' Price-of-my-check column. The document's printed grand total of S$4,184.45 comes from a hand-maintained totals table that has drifted: three of its five group subtotals reconcile exactly (Detection and aiming S$826.84, Horn S$154.00, Protection/enclosure/site S$1,321.29) and two do not — Laser gimbal is S$24.64 above its items and Power is S$217.87 above, S$242.51 in total.
- The twin reconciles against the **item rows**, because they are what the catalogue models one-to-one. The totals table is recorded as stale in `catalog/bom/v65.yaml` so the discrepancy is on the record, and correcting the document is a task on the hardware list, not on the twin.

### Contingency items live in the appendix

Version 65 changed where contingencies sit. The hardware list now holds them in appendices — outside the bill-of-materials table, excluded from every subtotal and from the grand total — and states that rule in its header. The twin mirrors it: `catalog/bom/v65.yaml` carries a `contingencies:` block alongside `items:`, and the bijection check neither demands a fitted product for an appendix entry nor counts it as a line left unmodelled.

This splits contingencies into two kinds, and the difference matters. Appendix E's accelerator boards have **simulated** triggers — U37 and U40 — so the panel can say whether the trigger is currently failing. Appendix F's VESA adapter plate has a **physical** trigger: whether the gimbal chassis lands on the mount's top plate at four fixing points, which no model here can answer. Those entries carry `trigger: physical` and report as *not evaluated here* rather than as passing, because a physical trigger rendered as a pass reads as a cleared check and is worse than showing no state at all.

### Camera placement from the solver

Version 65 fixes the camera to an existing hollow steel tube of Ø100 mm — confirmed on site, not a catalogue range — but records neither the tube's height nor its distance from the pit. Rather than inherit version 11's pose, the budget profile's standoff is **derived from the largest-zone solver already in the spec**, using the field-of-view method on the C385's own figures (3840 px wide, 91.5° horizontal field of view at the 4 mm setting) at the 100 px/m requirement:

| | |
|---|---|
| W_max = N/ρ | 38.40 m |
| z_max = N / (2ρ·tan(θ/2)) | 18.70 m |
| S = W_max·z_max / (z_max + W_max) | **12.58 m** |
| d = z_max − S/2 | **12.42 m** |

The 3 m warning ring around the 2.4 × 1.6 m pit needs an 8.4 m square, so the 12.58 m largest zone clears it with 4.18 m to spare. `sites/budget.yaml` SHALL therefore place the camera **12.42 m from the pit centre**.

The same formula reproduces version 11's published reference numbers (S = 11.53 m at d = 10.43 m against the spec's 11.5 ± 0.1 m at 10.4 ± 0.1 m), so the method is applied identically across both tiers.

### Pole height as an adjustable input

Height follows the same shape — distance × tan(angle) — using the window rule the repo already implements, with **the ground distances to the warning ring**, not the optical-axis depth z_max:

| Quantity | Value |
|---|---|
| D_near = d − 3.8 | 8.62 m |
| D_far = d + 3.8 | 16.22 m |
| θ_min, from sin θ_min = 2 px/(ρ · 0.1 m) | 11.537° |
| h_min = D_far · tan θ_min | 3.31 m |
| h_max = D_near · tan 45° | 8.62 m |
| **default** | **4.00 m** |

z_max is a slant limit along the optical axis and runs 6.28 m past D_far; substituting it would raise the minimum height to 3.82 m, overstating it by 0.51 m. The rule as written reproduces version 11's published 2.7–5.7 m window at d = 9.5 m exactly.

Height and distance SHALL be editable inputs in the what-if panel — `SITE_FIELDS` already carries `camera_height_m` and `stand_distance_m` — starting at the profile's defaults, with the window shown beside the input so an out-of-range value is visible as it is typed. Editing them changes no file. The 4.00 m default is a starting value to sweep, not a measurement; the measured tube height replaces it.

### What the Pi can actually process, and a candidate accelerator

At d = 12.42 m the far edge of the warning ring has **115.3 px/m natively**, above the 100 px/m requirement. But the requirement applies to the image the detector *processes*, and a downscaled input cannot reach it: 640 px gives 19.2 px/m, 1280 px gives 38.4, and the minimum input that reaches 100 px/m is **3330 px** — effectively full resolution. Full-resolution tiles are therefore mandatory on the budget pole, not an option.

Tiling the zone region at the default pose takes roughly 3 tiles of 640 px, which turns the Pi's 12 fps into about **4 fps** of complete zone coverage. That still fits the V12 latency budget — about 620 ms of the 1.5 s allowance — but it puts the tracker under strain: at 4 fps a worker walking at 1.4 m/s moves 0.35 m between frames, about 40 px against a person box roughly 58 px wide, so IoU association is marginal, and the 1 s dwell timer depends on stable IDs.

A **PCIe neural accelerator is therefore added as a candidate line**, not a fitted one: `ai_accel/rpi_ai_hat_plus_26tops` (Raspberry Pi AI HAT+, Hailo-8, 26 TOPS, US$110 list) as the default pick, with `ai_accel/rpi_ai_hat_plus_13tops` (Hailo-8L, 13 TOPS, US$70) beside it. Both carry `candidate: true` and `trigger: [U37, U40]`, and both are excluded from the fitted products, from the PoE and power models and from the S$3,941.94 total.

Candidates are **shown in the panel at all times**, not revealed only once something fails, each with its price, its trigger and whether that trigger is currently failing — a backup is only useful if you can see it before you need it. Each can be **switched into a run** (`load_site(..., with_candidates=[...])`, with `replaces:` overriding the AI box's `detector_fps` for that run): the models recompute as if the part were fitted, the results are labelled a candidate run, and neither the profile nor the total moves. So when a check fails, the replacement is tried in the same session rather than researched from scratch.

Whether 13 TOPS sustains YOLOv8 plus the tracker is an open question that will be settled by running it, not by scaling the TOPS figure. Both entries keep `verified: false` on `detector_fps` and the 13 TOPS one is marked untested for this workload; 26 TOPS stays the default until a measurement says otherwise.

The trigger is both checks, not latency alone: it is the density requirement that forces tiles, and tiles that cut the rate. Two caveats are recorded on the entry — the HAT is Raspberry Pi 5 only and takes the PCIe lane, and its rated ambient range is 0–50 °C, which a pole-top IP66 box in Singapore sun may exceed.

### Checks

- Add `tests/smoke_budget.py` with checks **U27–U57** on the budget profile: the bijection, the cost reconciliation, eight-port PoE, the 48 V chain, Pi detector latency, C385 coverage, the height window and default, the candidate line, laser reach and Class 2, unfitted categories, and the tab default.
- The phase-1 guide checks (V01–V34, U01–U10) keep running on `phase1` and keep their counts. `tests/smoke_v11.py` (U11–U26) keeps running on `v11`. Only the default profile moves.

## Capabilities

### New Capabilities
- `build-variants`: Site profiles declare a cost tier; the tab pair and its default; which models follow the tab and which follow the running stack; the not-fitted category rule; the one-to-one `bom_item` mapping and its bijection check.

### Modified Capabilities
- `product-catalogue`: Four modelled categories (`gimbal`, `controller`, `modem`, `enclosure`) and the unmodelled `hardware` category; the version 65 products; `bom_item`; `products.<category>: null`; the laser controller moved out of the site file; cost reconciliation against a hardware list.
- `dashboard`: The tab bar, its default, what the tab re-runs, and the warning when the tab and the running stack differ; the what-if panel taking a profile instead of hardcoding `v11`.
- `pole-network-power`: Port-count check; the 48 V budget chain and its cutoff device; 4G from a modem when no router is fitted; laser reach on the budget gimbal.
- `detection-coverage`: Coverage on the C385 and the Pi detector.
- `validation-suite`: `tests/smoke_budget.py`, checks U27–U57 and the new counts.
- `world-simulator`: Rendering a site with no floodlight fitted.
- `orin-sandbox`: The sandbox runs `app/config.budget.yaml` on the budget profile; the Pi flavour of the app image.

## Impact

- **Changed code:** `site.yaml` (default becomes `budget`), new `sites/budget.yaml` and `app/config.budget.yaml`, `sites/v11.yaml` (gains `tier`, loses the inline `laser_controller:`), `catalog/__init__.py` (profiles, new categories, `bom_item`, null-fitted categories, reconciliation), new `catalog/{gimbal,controller,modem,enclosure,hardware,ai_accel,lightning,spd}/`, 36 new budget product files, `catalog/effects.py`, `devices/poe_model.py` (port-count check), `devices/power_model.py` (48 V chain, cutoff device), `tools/network.py` (modem uplink), `tools/coverage.py`, `dashboard/v11.py` (becomes profile-parameterised), `dashboard/server.py` (`/api/variants`, profile query on the v11 endpoints), `dashboard/static/index.html` and `app.js` (tab bar), `tests/smoke_budget.py`, `README.md` and `CLAUDE.md` (check counts and the new default).
- **Unchanged:** the alarm state machine and the guide's thresholds (1.5 m, 3 m, 1 s, 3 s, 2 s, 2 s watchdog); the uplink queue; the MQTT topics; the arm and relay line protocols; every phase-1 check and its counts.
- **Breaking:** `docker compose up` with no `TWIN_PROFILE` now starts the budget pole, not the v11 pole. Anyone relying on the old default must set `TWIN_PROFILE=v11`. Called out in the README.
- **Outside the repo:** the version 65 hardware list's totals table is stale by S$242.51 against its own item rows (Laser gimbal +S$24.64, Power +S$217.87). The twin reconciles to the item rows at S$3,941.94 and records the table's figure as stale; correcting the document is a job on the hardware list.
- **Open site input:** the camera's distance from the pit is now derived (12.42 m) and the height defaults to 4.00 m inside a 3.31–8.62 m window, both adjustable in the panel. The remaining site facts are the tube's measured height and whether it stands at 12.42 m; if not, the windows and the density report say what the real pose costs in px/m.
