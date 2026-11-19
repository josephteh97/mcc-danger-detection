## MODIFIED Requirements

### Requirement: Quick checks
The twin SHALL provide eight quick-check scripts that need no Docker stack. They SHALL run in a Python virtual environment with:

`python3 tests/smoke.py && python3 tests/smoke_links.py && python3 tests/smoke_weather.py && python3 tests/smoke_catalog.py && python3 tests/smoke_trial.py && python3 tests/smoke_v11.py && python3 tests/smoke_fieldtest.py && python3 tests/smoke_budget.py`

The first five scripts SHALL run on the phase-1 profile whatever `site.yaml` selects. `smoke_v11.py` SHALL run on `v11` and `smoke_budget.py` on `budget`, each naming its profile explicitly, so that changing the default profile changes no check's answer. `smoke_fieldtest.py` needs no phone or network; it uses a synthetic camera. Together the eight SHALL run exactly these 95 named checks:

| Script | Checks |
|---|---|
| `smoke.py` | V01, V02, V03, V04, V05, U01 (homography round trip), U02 (edge distance), U03 (missed frame does not repeat the caution), V10, V11 |
| `smoke_links.py` | V06, V07, V08, V09, U04 (aim angles), U05 (relay protocol), U06 (servo slew rate) |
| `smoke_weather.py` | V19, V20, V21, V22, U07 (all 16 presets render), U08 (3-day battery per preset) |
| `smoke_catalog.py` | V23, V24, V25, V26, V27, V28, U09 (every catalogue file validates and site.yaml fits) |
| `smoke_trial.py` | V29, V30, V31, V32, V33, V34, U10 (two workers: laser follows the one inside; reset only when both are clear) |
| `smoke_v11.py` | U11 (distortion q and D), U12 (ring density with tiles), U13 (shrunken input fails as expected), U14 (largest-zone solver), U15 (pose inside windows), U16 (stand too close flagged), U17 (PoE budget), U18 (undersized switch fails as expected), U19 (4G data), U20 (PoE++ losses), U21 (continuous load), U22 (Plan B 3 overcast days), U23 (Plan A weekend shutdown order), U24 (no identity in v11), U25 (watchdog restart, model only), U26 (laser reach) |
| `smoke_fieldtest.py` | P01 (phone solver numbers), P02 (scale invariance), P03 (projection round trip), P04 (pose from synthetic cones), P05 (synthetic checkerboard calibration), P06 (level pole density), P07 (near corners on the image edge), P08 (measurement pass bands), P09 (16:9 stream flagged), P10 (page binds to loopback), P11 (D recovered from a synthetic distorted camera) |
| `smoke_budget.py` | U27 (version 65 maps one-to-one), U28 (cost reconciles to S$3,941.94 against the item rows), U29 (four devices on eight ports, four spare), U30 (a ninth PoE device fails as expected), U31 (4G data over the USB modem), U32 (48 V bus continuous load), U33 (solar-only overcast days), U34 (hardware cutoff is one event), U35 (no battery monitor fitted is reported), U36 (VPN node on the AI box is a single point of failure), U37 (ring density on the C385), U38 (standoff solved at d = 12.42 m), U39 (latency from the fitted AI box), U40 (latency against the guide's thresholds), U41 (detector rate traced to the Pi 5 specification), U42 (budget tab selected on load), U43 (default profile is budget), U44 (switching the tab recomputes without restarting), U45 (live and computed profiles named when they differ), U46 (no floodlight fitted is reported, not assumed), U47 (a forgotten category is still an error), U48 (budget gimbal reach and Class 2 laser), U49 (height window and default), U50 (candidate line costed but not fitted), U51 (sweeping height recomputes without writing the profile), U52 (a candidate switches into a run without entering the total), U53 (every pole-mounted item inside the air terminal's cone), U54 (every conductor leaving the enclosure has a rated SPD), U55 (earth resistance and pole continuity reported outstanding), U56 (switch input window against the pack's swing), U57 (appendix contingency items are excluded from every subtotal and from the total) |

U13, U18, U30 and U47 SHALL pass when the bad configuration is correctly rejected. U28 SHALL reconcile against the hardware list's item rows (S$3,941.94) and SHALL report, without failing on, the S$242.51 by which the document's printed totals table exceeds them. The item rows are the BOM table only: from version 65 the hardware list holds its contingency lines in appendices E and F, excluded by the document from every subtotal and from the grand total, and U57 SHALL assert the catalogue excludes them on the same rule. Each check SHALL print one line: its ID, PASS or FAIL, the measured value and the pass criterion.

#### Scenario: Expected result
- **WHEN** the quick-check chain runs on a host with the Python dependencies installed
- **THEN** 94 checks print PASS
- **AND** V11 prints FAIL with "runs flat", marked as a known fail (second finding)
- **AND** the whole chain completes

#### Scenario: Laser reach finding
- **WHEN** U26 finds the alarm zone's far corner beyond the 5° stop's reach
- **THEN** it prints FAIL with the shortfall in metres and is reported as a design finding, not hidden

#### Scenario: Default profile does not change a check
- **WHEN** `site.yaml` is switched between `budget` and `v11`
- **THEN** every quick check reports the same result, because each script names its own profile
