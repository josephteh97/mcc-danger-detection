# legacy-identification Specification

## Purpose
Face and tag identification, which version 11 does not use, kept as switched-off legacy code: the identity provider interface, the products and tests that belong to it, and the data-protection gate that must pass before it can be switched back on.
## Requirements
### Requirement: Identification kept as switched-off legacy code
The identification code SHALL be kept, not deleted, and SHALL be switched off by default in the `v11` profile with `identify.enabled: false` in `app/config.v11.yaml`. When it is off, the app SHALL NOT import `app/identify.py` or run any identification step, and alarm events SHALL carry no identity field. The phase-1 profile keeps its current behaviour.

#### Scenario: v11 default (U24)
- **WHEN** the app runs with `app/config.v11.yaml` and an alarm fires
- **THEN** the event has no `identity` field and `app.identify` is not in the loaded modules

#### Scenario: Re-enabled
- **WHEN** `identify.enabled: true` is set
- **THEN** the identify step runs on the person who triggered the alarm and its result is added to the event, as in phase 1

### Requirement: Identity provider interface
Identification SHALL plug in through one interface: `IdentityProvider.identify(frame, box, track_id) -> {"result", "name", "subcon", "confidence", "reason"}`. The phase-1 `identify()` stub SHALL be wrapped as the default provider. A future face-recognition, helmet-tag or PTZ provider SHALL need only a new provider class and configuration, not changes to the alarm state machine or actuation.

#### Scenario: Stub provider
- **WHEN** identification is enabled with the default provider
- **THEN** it returns `result: "unknown"` with the phase-1 reason, and the alarm proceeds unchanged

### Requirement: Legacy products
Catalogue products used only by identification (the PTZ camera `ptz_4mp_25x_hik_ds2de4425iwde` and any kiosk items) SHALL carry `legacy: true`. Legacy products SHALL be excluded from v11 cost totals and PoE budgets unless `identify.enabled: true`, in which case the PoE check SHALL include them.

#### Scenario: PTZ re-added
- **WHEN** identification is enabled and the PTZ is fitted to a spare switch port
- **THEN** the PoE check includes the PTZ's class reservation and still passes on the 240 W switch

### Requirement: Legacy tests
Tests for identification SHALL live in `tests/legacy/`, be skipped by default, and run with `pytest --legacy`.

#### Scenario: Default run
- **WHEN** `pytest tests/` runs without options
- **THEN** legacy tests are reported as skipped

### Requirement: Data-protection gate
The app SHALL refuse to start a face-recognition provider unless the config declares `pdpa.consent_records` and `pdpa.retention_days`, and SHALL store any face templates encrypted.

#### Scenario: Missing consent declaration
- **WHEN** a face-recognition provider is configured without the PDPA fields
- **THEN** the app stops at start-up with an error naming the missing fields

