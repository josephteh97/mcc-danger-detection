## 1. Catalogue categories

- [x] 1.1 Add `catalog/gimbal/_schema.yaml`: `name`, `source`, `verified`, `price_sgd`, `axes`, `travel_pan_deg`, `travel_tilt_deg`, `hold_torque_kgcm`, `payload_g`, `supply_v`, `watts_idle`, `watts_moving`
- [x] 1.2 Add `catalog/controller/_schema.yaml`: `name`, `source`, `verified`, `price_sgd`, `kind` (`aim` or `interlock`), `interface` (`ethernet`, `usb` or `hardwired`), `breaks_laser_supply` (bool)
- [x] 1.3 Add `catalog/modem/_schema.yaml`: `name`, `source`, `verified`, `price_sgd`, `interface` (`usb` or `ethernet`), `bands`, `carries_vpn_node` (bool)
- [x] 1.4 Add `catalog/enclosure/_schema.yaml`: `name`, `source`, `verified`, `price_sgd`, `kind` (`box`, `pole_kit` or `breather`), `ip_rating`, `volume_l`, `vented` (bool)
- [x] 1.5 Add `catalog/hardware/_schema.yaml` (unmodelled lines): `name`, `source`, `verified`, `price_sgd` only; `watts_typ`/`watts_max`/`bom_item` come from `COMMON_OPTIONAL`
- [x] 1.6 Add `bom_item` (`{type: str, optional}`) to `COMMON_OPTIONAL` in `catalog/__init__.py`; add the five categories to `CATEGORIES` as `BUDGET_CATEGORIES`
- [x] 1.7 Verify: `python3 -c "import catalog; print(catalog.validate_all())"`

## 2. Version 65 products, one file per line item

Every file carries `source` (hardware list version 65, 18 Nov 2026, plus the listing URL where the list has one), `verified: false`, `price_sgd` from the Price-of-my-check column, and `bom_item`.

- [x] 2.1 Detection and aiming — `camera/bullet_8mp_tplink_vigi_c385_4mm` (**1**, 160.00; from the TP-Link datasheet: `resolution_px: [3840, 2160]`, `hfov_deg: 91.5`, vertical 46.1°, diagonal 109.6°, 1/2.7" CMOS, F1.6, `form: bullet`, `sun_hood: true`, IP67, PoE class 0 at 11.5 W max, `dori_fp_px: 2675` from the DORI detect figure of 107 m at 25 px/m — cross-check against observe, 44 m at 62 px/m, which gives 2728), `hardware/pole_bracket_tplink_vmb_350` (**1a**, 25.55), `ai_box/raspberry_pi_5_8gb_poe` (**2**, 396.82; from the Raspberry Pi 5 specification: BCM2712 quad-core Cortex-A76 at 2.4 GHz, VideoCore VII, `ram_gb: 8`, `cpus: 4`, no NPU and no CUDA, `detector_fps: 12` for a YOLO-class person detector with no accelerator fitted), `switch/unmanaged_poe_pp_8p_din_48_56v` (**3**, 113.92; Linovision POE-SW508G2: 8 × gigabit PoE + 2 SFP, ports 1–4 802.3bt 90 W, ports 5–8 802.3at 30 W, `input_v_min: 48`, `input_v_max: 56`, Mode A/B, 6 kV surge, PoE watchdog, IP40, −40 to 75 °C), `modem/usb_4g_modem_lte_sg` (**3b**, 130.55)
- [x] 2.2 Horn — `speaker/horn_30w_ip66_poe_130db` (**4**, 154.00)
- [x] 2.3 Gimbal and laser — `hardware/arm_mount_witi_dual_40cm` (**7**, 151.00), `hardware/base_plate_steel_167x169` (**7a**, 17.41), `hardware/laser_clamp_mto_m_h22a` (**8**, 18.16), `hardware/gimbal_cable_set_glands` (**8a**, 50.00), `gimbal/pan_tilt_st3215_2axis` (**9**, 109.99), `laser/green_520nm_1mw_ytlaser_d12` (**10**, 8.17 × 2)
- [x] 2.4 Weatherproofing — `hardware/gimbal_rain_canopy` (**11**, 55.00), `hardware/sealing_kit_rtv_conformal` (**11a**, 35.00), `hardware/joint_bellows_boots` (**11b**, 30.00), `enclosure/breather_vent_ip66_desiccant` (**11c**, 35.00)
- [x] 2.5 Control — `controller/esp32_poe_iso_ind_olimex` (**12**, 46.50, `kind: aim`, `interface: ethernet`), `power_conv/ddr_15l_5_48_to_5v` (**13**, 42.34), `controller/laser_interlock_mosfet_key_tilt` (**14**, 27.40, `kind: interlock`, `breaks_laser_supply: true`), `hardware/aruco_board_0_6m` (**15**, 0.00)
- [x] 2.6 Power — `solar/panels_4x100w` (**16**, 129.79 × 4), `hardware/solar_tilt_brackets_28in` (**16a**, 49.99), `battery/lifepo4_48v_50ah` (**17**, 579.00), `power_conv/mppt_victron_100_20_48` (**18**, 151.00), `power_conv/ddr_60l_12_48_to_12v` (**19**, 50.57), `power_conv/batteryprotect_48v_100a` (**20**, 170.00, `kind: cutoff`)
- [x] 2.7 Protection, enclosure and site — `hardware/dc_mcb_set_4` (**21**, 72.00), `enclosure/fibox_arca_403015` (**23**, 189.78, `kind: box`), `enclosure/pole_kit_fibox_pmk_arca_30` (**23a**, 131.55, `kind: pole_kit`), `hardware/signage_cctv_laser` (**24**, 0.00), `hardware/spares_kit` (**25**, 120.00), `hardware/site_cabling_set` (**26**, 181.90)
- [x] 2.8 Add `mast/existing_steel_tube_d70_130` (price 0, `source`: version 65 records an existing site tube, not a purchase) so the budget profile fits a mast without inventing a cost
- [x] 2.9 Verify: `python3 -c "import catalog; catalog.validate_all()"` and every file carries a `bom_item` that appears once

## 3. Not-fitted categories and the budget site profile

- [x] 3.1 `load_site()`: accept `products.<category>: null`; drop it from `fitted`; keep the missing-category error only for a base category that is absent from `products:` entirely
- [ ] 3.2 Confirm `fitted()` returns `[]` and every caller of `floodlight`, `router` and `monitor` handles the empty list; make the night and floodlight reports say "no floodlight fitted"
- [ ] 3.3 Add `sites/budget.yaml`: `tier: budget`; camera **12.42 m** from the pit centre, solved from the largest-zone field-of-view method on the C385 (see 6.1); `camera.height_m: 4.0` as an adjustable default inside the 3.31–8.62 m window, marked as a starting value to replace with the measured tube height; `products:` per section 2 with `floodlight: null`, `router: null`, `monitor: null`; `power.bus_v: 48` with the version 65 conversion chain; `poe_ports:` with four ports; `gimbal`/`laser_controller` wiring (IP and ports only)
- [ ] 3.4 Add `app/config.budget.yaml`: guide thresholds verbatim, `identify.enabled: false`, detector settings for the Pi
- [ ] 3.5 Add `tier: expensive` to `sites/v11.yaml`; move its `laser_controller` watts and price into `controller/` and leave only the IP and ports in the profile
- [x] 3.6 Add `budget` to `PROFILES`
- [ ] 3.7 Verify: `TWIN_PROFILE=budget python3 -c "import catalog; s=catalog.load_site(); print(s['profile'], sorted(s['fitted']))"` and the five phase-1 scripts still give 36 PASS + V11 known fail

## 4. One-to-one mapping and cost reconciliation

- [ ] 4.1 Add `catalog.bom_mapping(site)` returning `{bom_item: product}` and raising on a duplicate `bom_item`
- [ ] 4.2 Add the hardware list's item numbers and per-line costs as a data file (`catalog/bom/v65.yaml`) with the document version and date, `total_sgd: 3941.94` (the sum of the item rows), and `totals_table_sgd: 4184.45` marked `stale: true`
- [ ] 4.2a Give `catalog/bom/v65.yaml` a `contingencies:` block separate from `items:`, carrying the appendix E and F entries with their prices and triggers; `total_sgd` SHALL exclude it, mirroring the document's own rule that appendix lines enter no subtotal and no grand total
- [ ] 4.3 Add `catalog.reconcile(site, bom)` returning unmodelled items, unknown products, and the cost difference per group and in total, against `total_sgd`
- [ ] 4.4 Record the stale table in the data file's comments: Laser gimbal +S$24.64, Power +S$217.87, S$242.51 in total; the reconciliation reports it without failing on it
- [ ] 4.5 Verify: U27 (bijection) and U28 (cost) in `tests/smoke_budget.py`

## 5. Power, PoE and network on the budget pole

- [ ] 5.1 `devices/poe_model.py`: fail with a named error when PoE devices outnumber switch ports, listing the devices left without one; report the spare-port count and flag zero spare as a finding
- [ ] 5.1a Check every bus-powered product's `input_v_min`/`input_v_max` against the fitted pack's reachable range (cells × per-cell range) and report the absorption and cutoff settings that keep the bus inside it — for the budget pole, absorption ≤ 3.50 V/cell and cutoff ≥ 48 V
- [ ] 5.2 `devices/power_model.py`: 48 V chain from `sites/budget.yaml`; read a `power_conv` with `kind: cutoff` and use its cutoff voltage instead of the two-stage percentages when one is fitted
- [ ] 5.3 `tools/network.py`: take the uplink from the fitted `modem` when no `router` is fitted
- [ ] 5.4 Laser reach check against the budget gimbal pose; Class 2 fitting rule already refuses anything above 1 mW
- [ ] 5.5 Verify: U29–U36 and U56 pass; `python3 devices/power_model.py --days 3 --weather overcast --profile budget` runs

## 6. Coverage and detection on the budget pole

- [ ] 6.1 Solve the budget standoff with the field-of-view method at ρ = 100 px/m on N = 3840, θ = 91.5°: W_max = 38.40 m, z_max = 18.70 m, S = 12.58 m, **d = 12.42 m**; confirm the method reproduces v11's U14 numbers (S = 11.53 m at d = 10.43 m) before using it
- [ ] 6.2 Confirm the solved zone clears the requirement: the 3 m ring round the 2.4 × 1.6 m pit needs 8.4 m against S = 12.58 m, 4.18 m of margin
- [ ] 6.3 Run the distortion method only once D has been measured for the C385 (P11); until then report that it was not run rather than borrowing another camera's D
- [ ] 6.4 Budget `detector.tiles` / `detector.input_px` set to what a Pi 5 sustains at 12 fps; alarm latency from `ai_box.detector_fps`
- [ ] 6.5 Height window from the existing rule with **ground distances to the warning ring**, not z_max: D_near = 8.62 m, D_far = 16.22 m, θ_min = 11.537°, giving 3.31–8.62 m; confirm it reproduces v11's published 2.7–5.7 m at d = 9.5 m
- [ ] 6.6 Flag a height outside the window with the bound it breaks and by how much; never clamp
- [ ] 6.7 Verify: U37–U41 and U49 pass; `python3 -m tools.coverage --profile budget` reports d = 12.42 ± 0.05 m and the window 3.31–8.62 m

## 6b. Detector rate against the density requirement

- [ ] 6b.1 Record the finding: the far edge of the ring has 115.3 px/m natively, so a downscaled detector input cannot meet 100 px/m — 640 px gives 19.2, 1280 px gives 38.4, and the minimum input that reaches 100 px/m is 3330 px. Full-resolution tiles are therefore mandatory on the budget pole, not optional
- [ ] 6b.2 Compute the tile count over the zone region at the default pose and the sustained rate it implies (≈3 tiles of 640 px, ≈4 fps from the Pi's 12 fps); feed that rate, not 12, into the latency and tracker models
- [ ] 6b.3 Check tracker stability at the sustained rate: a worker at 1.4 m/s moves ≈0.35 m between frames at 4 fps, ≈40 px against a person box ≈58 px wide, so IoU association is marginal and the dwell timer depends on it
- [ ] 6b.4 Verify: U37 and U40 report the sustained rate they used, and the tracker check reports the inter-frame displacement in pixels

## 6c. Candidate accelerator line

- [ ] 6c.1 Add the `ai_accel` category with a minimal schema (`name`, `source`, `verified`, `price_sgd`, `tops`, `interface`, `ambient_max_c`)
- [ ] 6c.2 Add `ai_accel/rpi_ai_hat_plus_26tops` (default pick, Hailo-8, 26 TOPS, US$110) and `ai_accel/rpi_ai_hat_plus_13tops` (Hailo-8L, 13 TOPS, US$70), both `candidate: true` with `trigger: [U37, U40]`, PCIe Gen 3, Raspberry Pi 5 only, ambient 0–50 °C; quote the SGD price from element14 SG (SC1791) before promoting either
- [ ] 6c.3 Exclude candidates from fitted products, from the PoE and power models and from the catalogue total; list them separately with price and trigger
- [ ] 6c.3a Add `hardware/camvate_vesa_plate_75_100` (CAMVATE slotted X-plate, 75/100, S$25.23, Amazon.sg B0FDKRX2Y6) as an appendix F contingency with `trigger: physical` — whether the gimbal chassis lands on the item-7 bracket's top plate at four fixing points — and render its trigger state as "not evaluated here", never as PASS
- [ ] 6c.4 Add `with_candidates=[...]` to `catalog.load_site()` so a candidate fits for one run only, with `replaces:` overriding the AI box's `detector_fps` for that run; label the results a candidate run and leave the profile and the total untouched
- [ ] 6c.5 Mark the 13 TOPS entry untested for YOLOv8-plus-tracker; both entries carry `verified: false` on `detector_fps` until measured, and the rate is never inferred from the TOPS figure
- [ ] 6c.6 Record the thermal caveat: 0–50 °C ambient against a pole-top IP66 box in Singapore sun — fitting one brings an enclosure thermal review that is not in the HAT's price — and that the HAT takes the PCIe lane (free here, the Pi boots from microSD)
- [ ] 6c.7 Verify: U50 and U52 pass — the total is still S$3,941.94, the candidates are listed apart, and switching one in recomputes without changing the total
- [ ] 6c.8 Verify: U57 passes — every appendix entry is outside `items:`, outside the total and outside the PoE and power models, and a `trigger: physical` entry reports not evaluated here

## 6d. Lightning protection

- [ ] 6d.1 Add the `lightning` category (`name`, `source`, `verified`, `price_sgd`, `rod_length_m`, `protection_angle_deg`, `material`) and the `spd` category (`name`, `source`, `verified`, `price_sgd`, `kind` = `ethernet_poe` or `dc`, `lines`, `poe_class_max`, `max_surge_ka`, `din_rail`)
- [ ] 6d.2 Add `lightning/air_terminal_1m_copper` (item 27, S$150 est, 1 m, 45°) and `spd/poe_eth_spd_assmann_dn95421` (item 27b, S$65.53, PoE/PoE+/PoE++, 10 kV, DIN rail); add `hardware/earthing_kit_pole` (item 27a, S$300 est)
- [ ] 6d.3 Add `earthing:` to `sites/budget.yaml` — `target_ohm: 10`, `measured_ohm: null`, `pole_continuity_confirmed: false`, one shared earth reference — plus each pole-mounted item's horizontal offset from the pole axis so the cone check has geometry to work with
- [ ] 6d.4 Protection-zone check in `tools/coverage.py`: `r ≤ (h_tip − h)·tan(angle)` over camera, gimbal, enclosure and array; name any item outside and the extra tip height needed; fail if anything sits above the tip
- [ ] 6d.5 SPD coverage check: enumerate conductors leaving the enclosure from the fitted products, match each to a fitted SPD, and compare the SPD's `poe_class_max` against the line's duty (the 30 W horn needs PoE+; an 802.3af-only device is a mismatch)
- [ ] 6d.6 Flag a profile that fits `lightning` with no `spd` — structure protected, electronics not
- [ ] 6d.7 Verify: U53–U55 pass; `python3 -m tools.coverage --profile budget` reports the cone clearance and the outstanding earth measurement

## 7. Dashboard tab pair

- [ ] 7.1 `GET /api/variants`: every profile that declares a `tier`, its tier, its label, and which profile the stack is running
- [ ] 7.2 Parameterise `dashboard/v11.py` on profile (it already takes `profile="v11"`; remove the hardcoded default from the server routes and pass the tab's profile through `fields()`, `whatif()`, `coverage()` and `hud_static()`)
- [ ] 7.3 Add the tab bar to `dashboard/static/index.html` under the header, budget first; persist the choice in the URL so a reload keeps it
- [ ] 7.4 `app.js`: switching the tab re-requests what-if fields, coverage, HUD figures and cost totals for that profile; the live 3D view, video and events stay on the running profile
- [ ] 7.5 Show a line naming the running profile whenever it differs from the selected tab
- [ ] 7.6 Give `camera_height_m` and `stand_distance_m` in `SITE_FIELDS` their budget defaults (4.00 m, 12.42 m) and show the height and placement windows beside the inputs, so an out-of-window value is visible as it is typed
- [ ] 7.7 List the selected tab's candidate parts at all times with price, trigger and whether that trigger is currently failing; give each a control that switches it into the run and back out
- [ ] 7.8 Verify: U42–U45, U51 and U52 pass; open `http://localhost:8080` and confirm budget is selected on load

## 8. Default profile and docs

- [ ] 8.1 Flip `site.yaml` to `profile: budget` (do this only once section 9 passes)
- [ ] 8.2 README: the new default, the breaking change for `docker compose up`, the tab pair, the version 65 provenance and the totals-table gap
- [ ] 8.3 `CLAUDE.md`: new check counts and the new default profile
- [ ] 8.4 Verify: `python3 -c "import catalog; print(catalog.active_profile())"` prints `budget`

## 9. Validation

- [ ] 9.1 Add `tests/smoke_budget.py` with U27–U57 on the budget profile: bijection (U27), cost reconciliation (U28), PoE port count and budget (U29–U31), 48 V chain and cutoff (U32–U36), coverage and Pi latency (U37–U41), tab defaults and `/api/variants` (U42–U45), unfitted categories reported not assumed (U46–U47), Class 2 laser and reach (U48), appendix contingencies excluded from the total (U57)
- [ ] 9.2 Add the budget profile to `tests/test_compose.py`'s static checks
- [ ] 9.3 Confirm the phase-1 scripts still give 36 PASS + V11 known fail and `tests/smoke_v11.py` still gives U11–U26
- [ ] 9.4 Verify: `python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py && python3 tests/smoke_v11.py && python3 tests/smoke_fieldtest.py && python3 tests/smoke_budget.py`

## 10. Verification pass on the version 65 figures

- [ ] 10.1 The C385 and the Pi 5 are entered from published specifications in 2.1 and may be set `verified: true` with the datasheet URL as `source`
- [ ] 10.2 Replace the remaining typical values — the horn, the switch, the gimbal, the battery, the enclosure — with datasheet figures and set `verified: true` on each
- [ ] 10.3 Optional confirmation: measure the Pi 5's person-detector frame rate on the board with the shipped detector and replace the 12 fps specification figure if it differs
- [ ] 10.3a If an accelerator is ever trialled, measure both variants on the board — 13 TOPS first, since it is US$40 cheaper and the only open question is whether it sustains YOLOv8 plus the tracker
- [ ] 10.4 Confirm the tube's height on site, and whether it stands at the solved 12.42 m; if it does not, record the real distance and let the density report state the cost in px/m
- [ ] 10.5 Verify: `python3 tests/smoke_budget.py` with no `*` unverified markers on the fitted budget products
