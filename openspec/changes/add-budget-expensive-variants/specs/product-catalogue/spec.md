## MODIFIED Requirements

### Requirement: Catalogue layout
The catalogue SHALL have one folder per hardware category under `catalog/`: `camera`, `floodlight`, `speaker`, `laser`, `ai_box`, `battery`, `solar`, `mast`, for version 11 also `switch`, `router`, `power_conv` (step-up converter, PoE++ splitter, PoE injector, 24 V supply, charger) and `monitor` (battery monitor and relays), and for version 65 also `gimbal`, `controller`, `modem`, `enclosure`, `lightning`, `spd`, `ai_accel` and `hardware`. Each folder holds a `_schema.yaml` listing the fields the simulator reads, plus one YAML file per product.

Every product file SHALL carry:
- `source`: a link or "typical value"
- `verified: true|false`
- `price_sgd`
- optionally `legacy: true` for products used only by identification
- optionally `bom_item`: the item number of the hardware-list line this file models

Camera files MAY carry `dori_fp_px` (centre pixels per radian from the DORI table). Products that take PoE SHALL carry `poe_class`, and every powered product SHALL carry `watts_typ` and `watts_max`.

Categories SHALL be of two kinds, and the kind SHALL decide where a line goes:
- **Modelled** — the schema's fields change a simulation result. `camera`, `floodlight`, `speaker`, `laser`, `ai_box`, `battery`, `solar`, `mast`, `switch`, `router`, `power_conv`, `monitor`, `gimbal`, `controller`, `modem`, `enclosure`, `lightning`, `spd`.
- **Unmodelled** — `hardware`, whose schema is `name`, `source`, `verified` and `price_sgd` only. It holds lines that carry cost and mass but drive no model: mounts, weatherproofing, cabling, breakers, signage, spares and calibration aids. A `hardware` entry SHALL NOT be given fields no model reads; an entry that later earns a model SHALL be promoted to a category of its own.

The version 11 products SHALL stay as they are. The version 65 products SHALL be added:

| Category | Products (version 65) |
|---|---|
| camera | `bullet_8mp_tplink_vigi_c385_4mm` (item 1, S$160.00) |
| ai_box | `raspberry_pi_5_8gb_poe` (item 2, S$396.82) |
| switch | `unmanaged_poe_pp_8p_din_48_56v` (item 3, S$113.92 — 8 ports, 4 spare) |
| modem | `usb_4g_modem_lte_sg` (item 3b, S$130.55) |
| speaker | `horn_30w_ip66_poe_130db` (item 4, S$154.00) |
| gimbal | `pan_tilt_st3215_2axis` (item 9, S$109.99) |
| laser | `green_520nm_1mw_ytlaser_d12` (item 10, S$8.17 × 2) |
| controller | `esp32_poe_iso_ind_olimex` (item 12, S$46.50), `laser_interlock_mosfet_key_tilt` (item 14, S$27.40) |
| power_conv | `ddr_15l_5_48_to_5v` (item 13), `mppt_victron_100_20_48` (item 18), `ddr_60l_12_48_to_12v` (item 19), `batteryprotect_48v_100a` (item 20) |
| solar | `panels_4x100w` (item 16, S$129.79 × 4) |
| battery | `lifepo4_48v_50ah` (item 17, S$579.00) |
| enclosure | `breather_vent_ip66_desiccant` (item 11c), `fibox_arca_403015` (item 23), `pole_kit_fibox_pmk_arca_30` (item 23a) |
| lightning | `air_terminal_1m_copper` (item 27) |
| spd | `poe_eth_spd_assmann_dn95421` (item 27b) |
| mast | `existing_steel_tube_d70_130` (S$0 — version 65 fits an existing site tube, not a purchase) |
| hardware | items 1a, 7, 7a, 8, 8a, 11, 11a, 11b, 15, 16a, 21, 24, 25, 26, 27a (earthing kit) |

The PTZ camera SHALL be marked `legacy: true`.

#### Scenario: Every catalogue file validates
- **WHEN** the catalogue loader reads every product file
- **THEN** every file passes its folder's schema, and every product named under `products:` in the active site profile exists

#### Scenario: v11 cost totals
- **WHEN** the catalogue totals the v11 profile per power plan, excluding legacy products
- **THEN** each plan's total is reported and matches hardware list version 11 within S$1 for the parts the catalogue holds

#### Scenario: Unmodelled entries stay unmodelled
- **WHEN** a `hardware` file carries a field no model reads
- **THEN** the loader refuses it, naming the file and the field

### Requirement: Fitting products to the pole
The products fitted to the pole SHALL be the file names listed under `products:` in the active site profile, one per category or a list where several are fitted. A category MAY be set to `null`, meaning the pole does not carry it. The world, the power model and the comparison tool SHALL read product specs only from the fitted, or explicitly compared, files.

Fitting a laser that is not Class 2 SHALL be refused. This is a laser safety rule.

Where a product fact lives in the catalogue, a site profile SHALL NOT also carry it. The laser controller's watts and price SHALL move from `sites/v11.yaml`'s inline `laser_controller:` block into the `controller` category; only its IP address and ports, which are site wiring, SHALL stay in the profile.

#### Scenario: Swap the fitted camera
- **WHEN** `products.camera` in the active profile changes to `dome_4mp_2_8mm_generic`
- **THEN** the world renders with that camera's resolution and field of view, and the power model uses its power draw

#### Scenario: Non-Class-2 laser refused
- **WHEN** `products.laser` in the active profile is `green_520nm_4_9mw`
- **THEN** loading the site fails with an error saying that the laser is not Class 2

#### Scenario: Version 65 laser passes (U48)
- **WHEN** the budget profile fits `green_520nm_1mw_ytlaser_d12` at 1 mW and 520 nm
- **THEN** it is Class 2 and is fitted

## ADDED Requirements

### Requirement: Bill-of-materials mapping
A site profile modelling a published hardware list SHALL map to it one-to-one. Every product fitted by that profile SHALL carry `bom_item` naming the line it models, including letter suffixes (`"1a"`, `"11c"`), and the hardware list SHALL be held as data (`catalog/bom/<list>.yaml`) carrying the document's version, its date, and each line's number, quantity and unit price.

`catalog.bom_mapping(site)` SHALL return `{bom_item: product}` and SHALL raise naming both files when two products claim the same line.

The mapping SHALL be a bijection: no line of the hardware list left unmodelled, no fitted product claiming a line the list does not contain, and no line claimed twice.

#### Scenario: Budget profile maps one-to-one (U27)
- **WHEN** the budget profile's fitted products are mapped against `catalog/bom/v65.yaml`
- **THEN** all 36 line items are claimed exactly once, and no fitted product claims a line the list does not contain

#### Scenario: A duplicated line is refused
- **WHEN** two budget product files both carry `bom_item: "9"`
- **THEN** the mapping fails naming both files and the line

### Requirement: Cost reconciliation against a hardware list
`catalog.reconcile(site, bom)` SHALL report, per group and in total: items the catalogue does not model, products claiming unknown lines, and the difference between the catalogue's `price_sgd × quantity` and the hardware list's line costs.

The reconciliation SHALL be made against the hardware list's **item rows**, not against its printed totals table, because the item rows are what the catalogue models one-to-one. The data file SHALL carry both figures: `total_sgd`, the sum of the item rows, which the check reconciles against; and `totals_table_sgd`, the document's printed total, marked `stale: true` where the two differ.

For version 65 the authoritative total is **S$3,941.94**. Its printed totals table reads S$4,184.45 because two of its five group subtotals have drifted from the items beneath them — Laser gimbal by S$24.64 and Power by S$217.87, S$242.51 in all — while Detection and aiming (S$826.84), Horn (S$154.00) and Protection/enclosure/site (S$1,321.29) reconcile exactly. The data file SHALL record that drift so it stays visible.

#### Scenario: Budget costs reconcile against the item rows (U28)
- **WHEN** the budget profile's catalogue total is reconciled against `catalog/bom/v65.yaml`
- **THEN** the total is S$3,941.94 and the per-line difference is zero for every line the catalogue holds

#### Scenario: A stale table is recorded, not adopted
- **WHEN** the hardware list's printed grand total differs from the sum of its item rows
- **THEN** the data file carries both figures with the printed one marked stale, and the reconciliation reports the difference while passing against the item rows

### Requirement: Candidate and contingency line items
A hardware list MAY carry **candidate** lines: parts that are specified and priced but not fitted, to be added only if a named check fails. A candidate SHALL carry `candidate: true` and `trigger:` naming the check or checks that would bring it in.

A candidate SHALL be excluded from the fitted products, from the power and PoE models and from the profile's catalogue total, and SHALL be listed separately with its price and its trigger so the cost of the contingency is visible before it is incurred.

A candidate SHALL nevertheless be **loadable into a simulation run** without being promoted. `catalog.load_site(..., with_candidates=[<id>, ...])` SHALL fit the named candidates for that run only: the models then compute as if the part were fitted, the results are labelled as a candidate run, and neither the site profile nor the catalogue total changes. This is what makes a candidate a usable backup rather than a note — when a check fails, the replacement can be switched in and the same checks re-run in the same session.

A candidate's catalogue entry MAY carry `replaces:` naming fields it overrides on another fitted product when loaded, so that fitting the accelerator raises the AI box's `detector_fps` for that run instead of requiring a second `ai_box` file.

Promoting a candidate SHALL be an edit to the hardware list — adding the line and its item number — and then to `catalog/bom/<list>.yaml`, never a silent change in the twin.

From version 65 the hardware list holds its contingency lines in **appendices**, outside the bill-of-materials table and excluded by the document from every subtotal and from the grand total. `catalog/bom/v65.yaml` SHALL mirror that split: appendix entries go in a `contingencies:` block and never in `items:`, so the bijection check of U27 neither demands a fitted product for them nor counts them as lines left unmodelled.

A contingency's trigger MAY be a check the twin cannot run. Where it is, the entry SHALL carry `trigger: physical` with the condition stated in prose instead of a check ID, and the panel SHALL show its trigger state as **not evaluated here** — never as passing. A physical trigger that renders as a pass is worse than no trigger at all, because it reads as a cleared check.

Version 65 SHALL carry its contingencies across two appendices. Appendix E holds a PCIe neural accelerator for the Raspberry Pi 5, `ai_accel/rpi_ai_hat_plus_26tops` (Raspberry Pi AI HAT+, Hailo-8, 26 TOPS, US$110 list; the 13 TOPS Hailo-8L at US$70 is the cheaper variant), triggered by **U37 and U40 together** — the density requirement and the latency requirement — because the two interact: meeting 100 px/m forces full-resolution tiles, and tiles cut the sustained rate.

The 13 TOPS Hailo-8L variant SHALL be carried as a second candidate, `ai_accel/rpi_ai_hat_plus_13tops` (US$70). The 26 TOPS entry SHALL be the default pick. Whether 13 TOPS sustains YOLOv8 plus the tracker is unresolved and SHALL be settled by running it, not by scaling TOPS: until a measurement exists, both entries SHALL carry `verified: false` on `detector_fps` and the 13 TOPS entry SHALL be marked as untested for this workload.

Both entries SHALL record that the HAT is Raspberry Pi 5 only, that it occupies the PCIe lane, and that its rated ambient range is 0–50 °C, which a pole-top IP66 box in Singapore sun may exceed — so fitting one brings an enclosure thermal review that is not in the HAT's price.

Appendix F holds the gimbal mount's VESA adapter plate, `hardware/camvate_vesa_plate_75_100` (CAMVATE slotted X-plate, 75/100, S$25.23). Its trigger is physical: whether the Waveshare chassis base lands on the item-7 bracket's top plate at four fixing points. Four points are required because two bolts in a line are held against the tilt axis's ±3 N·m servo reaction by bolt preload alone, and on a 290 mm arm that joint works loose and the aim walks off the zone. The twin models neither bolt patterns nor preload, so this entry SHALL carry `trigger: physical` and SHALL report as not evaluated here.

#### Scenario: Appendix contingencies stay out of the total (U57)
- **WHEN** the budget profile's catalogue total is reconciled against `catalog/bom/v65.yaml`
- **THEN** every appendix E and F entry is absent from `items:`, absent from the total of S$3,941.94 and absent from the PoE and power models, and each is listed separately with its price and its trigger
- **AND** a contingency carrying `trigger: physical` reports "not evaluated here" rather than PASS

#### Scenario: A candidate is costed but not fitted (U50)
- **WHEN** the budget profile's catalogue total is computed
- **THEN** the accelerator is excluded from the total of S$3,941.94, and is listed separately with its price and its trigger

#### Scenario: A candidate is not modelled as present
- **WHEN** the PoE budget and the power model run for the budget profile
- **THEN** neither includes the accelerator's draw

#### Scenario: A candidate is switched in for a run (U52)
- **WHEN** the budget profile is loaded with the 26 TOPS accelerator as a candidate
- **THEN** the detector rate, density, latency and tracker checks recompute with it fitted, the results are labelled a candidate run, and the catalogue total is still S$3,941.94

#### Scenario: Both accelerator variants are available to try
- **WHEN** the 13 TOPS candidate is loaded in place of the 26 TOPS one
- **THEN** the run reports that its detector rate for this workload is untested, and does not infer it from the TOPS figure
