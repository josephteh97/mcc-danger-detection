## MODIFIED Requirements

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
