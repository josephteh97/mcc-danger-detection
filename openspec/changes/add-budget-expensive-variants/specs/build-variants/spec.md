## ADDED Requirements

### Requirement: Cost tier on a site profile
A site profile MAY declare `tier: budget | expensive`, and `PROFILES` SHALL be `("phase1", "v11", "budget")`. The tier names what the build costs, not what it does; two profiles with different tiers answer the same brief with different hardware.

`sites/budget.yaml` SHALL declare `tier: budget` and model hardware list version 65 (19 November 2026), whose item rows total S$3,941.94. `sites/v11.yaml` SHALL declare `tier: expensive` and keep modelling hardware list version 11 unchanged. `sites/phase1.yaml` SHALL declare no tier: it is the profile the guide checks V01–V34 run on and it MUST NOT move.

#### Scenario: Tiers are discoverable (U42)
- **WHEN** the site profiles are listed
- **THEN** `budget` reports tier `budget`, `v11` reports tier `expensive`, and `phase1` reports no tier

#### Scenario: Phase 1 is unaffected
- **WHEN** the five phase-1 quick-check scripts run
- **THEN** they load `phase1` and still report 36 PASS with V11 the known fail

### Requirement: Budget is the default profile
`site.yaml` SHALL select `profile: budget`. `$TWIN_PROFILE` SHALL still override it, and a script that names its profile explicitly SHALL be unaffected.

This is a breaking change to `docker compose up` with no `TWIN_PROFILE`: it brings up the budget pole where it previously brought up the v11 pole. The README SHALL say so.

#### Scenario: Default with no override (U43)
- **WHEN** `TWIN_PROFILE` is unset and the active profile is read
- **THEN** it is `budget`

#### Scenario: Override still wins
- **WHEN** `TWIN_PROFILE=v11` is set
- **THEN** the active profile is `v11` whatever `site.yaml` says

### Requirement: The tab moves the models, not the stack
The dashboard SHALL compute its model-driven panels for the **selected tab's** profile and SHALL leave the live panels on the profile the stack is running.

Following the tab: the what-if panel, the coverage heatmap, the PoE budget, the power plans and battery runs, the 4G estimate, the laser reach and every cost total.

Following the running stack: the 3D view, the browser video stream, the app events, the fault buttons and the trial pad.

Switching the tab SHALL NOT restart, rebuild or reconfigure any container.

#### Scenario: Switching the tab recomputes (U44)
- **WHEN** the tab changes from budget to expensive
- **THEN** the what-if fields, coverage, PoE, power and cost results are those of `v11`, and no container is restarted

#### Scenario: Tab and stack disagree (U45)
- **WHEN** the selected tab is `budget` and the stack is running `v11`
- **THEN** the page states which profile is live and which is being computed

### Requirement: A category may be not fitted
A site profile MAY set `products.<category>: null` to say the pole does not carry that category. The loader SHALL accept it for a base category, SHALL leave that category out of `fitted`, and `fitted(site, category)` SHALL return an empty list.

A base category absent from `products:` entirely SHALL still be an error, so a forgotten line is not silently read as "not fitted".

Every model that reads a category SHALL report its absence rather than substitute a default. The budget pole fits no `floodlight`, no `router` and no `monitor`.

#### Scenario: Budget pole has no floodlight (U46)
- **WHEN** the budget profile is loaded and the night models run
- **THEN** `fitted(site, "floodlight")` is empty and the night report says no floodlight is fitted, with no lux figure invented

#### Scenario: Forgetting a category is still an error (U47)
- **WHEN** a profile's `products:` has no `camera` entry at all
- **THEN** loading fails naming the file and `camera`
