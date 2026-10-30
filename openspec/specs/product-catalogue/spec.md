# product-catalogue Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Catalogue layout
The catalogue SHALL have one folder per hardware category under `catalog/`: `camera`, `floodlight`, `speaker`, `laser`, `ai_box`, `battery`, `solar`, `mast`, and for version 11 also `switch`, `router`, `power_conv` (step-up converter, PoE++ splitter, PoE injector, 24 V supply, charger) and `monitor` (battery monitor and relays). Each folder holds a `_schema.yaml` listing the fields the simulator reads, plus one YAML file per product.

Every product file SHALL carry:
- `source`: a link or "typical value"
- `verified: true|false`
- `price_sgd`
- optionally `legacy: true` for products used only by identification

Camera files MAY carry `dori_fp_px` (centre pixels per radian from the DORI table). Products that take PoE SHALL carry `poe_class`, and every powered product SHALL carry `watts_typ` and `watts_max`.

It SHALL start out with the products named in the guide:

| Category | Products |
|---|---|
| camera | `bullet_8mp_4mm_generic`, `dome_4mp_2_8mm_generic`, `bullet_4mp_hik_ds2cd1043g0i`, `ptz_4mp_25x_hik_ds2de4425iwde` |
| floodlight | `led_30w_24v_wide`, `led_30w_24v_narrow`, `vive_50w_230v_sensor` |
| speaker | `horn_30w_analog_generic`, `hik_ds_qaz1307g1t_e_ip_horn` |
| laser | `green_520nm_class2`, `red_650nm_class2`, `green_520nm_4_9mw` |
| ai_box | `jetson_orin_nano_super_8gb`, `jetson_orin_nx_16gb` |
| battery | `lifepo4_24v_100ah`, `lifepo4_24v_200ah` |
| solar | `panels_2x250w`, `panels_4x250w` |
| mast | `trailer_telescopic_6_5m`, `tripod_ballasted_3m` |

and add the version 11 products:

| Category | Products |
|---|---|
| camera | `bullet_12mp_hik_ids2cd7ac6g2_izhsy` (S$1,586.18) |
| ai_box | `seeed_recomputer_super_j4012` (S$1,449.00) |
| mast | `wheeled_cabinet_stand_4m` |
| switch | `managed_poe_8p_240w_48v` |
| router | `outdoor_4g_router_wifi` |
| power_conv | `stepup_24_54v`, `poe_bt_splitter_12v`, `poe_injector_router`, `psu_24v_240w`, `charger_24v_20a_230v` |
| monitor | `battery_monitor_rs485`, `relay_24v_2ch` |
| battery | `lifepo4_24v_50ah` |

The PTZ camera SHALL be marked `legacy: true`.

#### Scenario: Every catalogue file validates
- **WHEN** the catalogue loader reads every product file
- **THEN** every file passes its folder's schema, and every product named under `products:` in the active site profile exists

#### Scenario: v11 cost totals
- **WHEN** the catalogue totals the v11 profile per power plan, excluding legacy products
- **THEN** each plan's total is reported and matches hardware list version 11 within S$1 for the parts the catalogue holds

### Requirement: Schema validation
The loader SHALL refuse a product file that is missing a field required by its folder's `_schema.yaml`. The error SHALL name the file and the missing field.

#### Scenario: Product file checks (V23)
- **WHEN** a camera file without `hfov_deg` is loaded
- **THEN** loading fails with an error naming the file and `hfov_deg`

### Requirement: Fitting products to the pole
The products fitted to the pole SHALL be the file names listed under `products:` in `site.yaml`, one per category. The world, the power model and the comparison tool SHALL read product specs only from the fitted, or explicitly compared, files.

Fitting a laser that is not Class 2 SHALL be refused. This is a laser safety rule.

#### Scenario: Swap the fitted camera
- **WHEN** `products.camera` in `site.yaml` changes to `dome_4mp_2_8mm_generic`
- **THEN** the world renders with that camera's resolution and field of view, and the power model uses its power draw

#### Scenario: Non-Class-2 laser refused
- **WHEN** `products.laser` in `site.yaml` is `green_520nm_4_9mw`
- **THEN** loading the site fails with an error saying that the laser is not Class 2

### Requirement: Spec-driven effects
Each category's spec fields SHALL change the simulation:

- **Camera:** resolution and horizontal field of view give the coverage and the pixels per metre on the worker. These are rated against the IEC 62676-4 DORI levels: 25 detect, 62 observe, 125 recognise, 250 identify. They also give how much of the 3 m ring fits in the picture. A sun hood collects about 40% of the window drops a dome bubble does. True WDR in dB sets how much the scene darkens when the sun is in view. IR range sets the night image without the floodlight.
- **Floodlight:** lumens spread over the beam's footprint give the lux on the worker. A 230 V lamp adds inverter loss to the daily energy.
- **Speaker:** the sound level at 1 m gives the level at the worker against each weather's background noise.
- **Laser:** power and wavelength give the dot's brightness, weighted by the eye's sensitivity, and the laser class.
- **AI box:** measured detector frame rate and power give alarm latency and energy.
- **Battery and solar:** energy and panel watts give the battery low point.
- **Mast:** height and sway give the camera height and the sway in wind.

#### Scenario: Dome vs bullet (V24)
- **WHEN** `bullet_8mp_4mm_generic` and `dome_4mp_2_8mm_generic` are compared in `tropical_downpour`
- **THEN** the dome shows more of the window hidden by drops (about 2.5% against 1.1%) and fewer pixels per metre on the worker (about 93 against 175)

#### Scenario: WDR in low sun (V25)
- **WHEN** a camera without true WDR (`bullet_4mp_hik_ds2cd1043g0i`) and one with it (`bullet_8mp_4mm_generic`) are compared in `low_sun_glare`
- **THEN** the camera without true WDR has lower worker contrast (about 30 against 46)

#### Scenario: Floodlight specs (V26)
- **WHEN** `led_30w_24v_narrow` (60° beam), `led_30w_24v_wide` (120° beam) and `vive_50w_230v_sensor` are compared at night
- **THEN** the narrow beam gives more lux on the worker than the wide one (about 19 against 2 lux)
- **AND** the 230 V lamp adds inverter energy (about 538 Wh a day)

#### Scenario: Laser class check (V27)
- **WHEN** the laser products are compared
- **THEN** `green_520nm_4_9mw` is flagged as not Class 2, and the two Class 2 modules are not

#### Scenario: Helmet-tag resolution (V28)
- **WHEN** pixels per metre on the worker are computed for every catalogue camera at the pole's distance
- **THEN** the result records that no camera reaches 250 px/m, the "identify" level (best about 213 px/m, the PTZ at its widest)

### Requirement: Compare tool
`python3 -m tools.compare <category> <product> <product>... --weather <preset,...>` SHALL compare any number of products in one category, with everything else as fitted in `site.yaml`. It SHALL print a table of the category's measures and save a picture grid, with one row per weather and one column per product.

#### Scenario: Four-camera comparison
- **WHEN** `python3 -m tools.compare camera bullet_8mp_4mm_generic dome_4mp_2_8mm_generic bullet_4mp_hik_ds2cd1043g0i ptz_4mp_25x_hik_ds2de4425iwde --weather clear,tropical_downpour,night_clear,low_sun_glare` runs
- **THEN** it prints, per camera: pixels per metre with DORI level, how much of the 3 m ring is in the picture, how much of the window drops hide in a downpour, worker contrast in low sun and in a downpour, daily pole energy, and pole hardware cost
- **AND** it saves a 4×4 picture grid

