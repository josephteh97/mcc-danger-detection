## MODIFIED Requirements

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
