## MODIFIED Requirements

### Requirement: Products panel
The page SHALL let the user pick any catalogue product for each category, and show the comparison table and picture grid that `tools.compare` produces for the chosen products.

The category list SHALL include the version 65 categories (`gimbal`, `controller`, `modem`, `enclosure`, `hardware`). A category the selected tab's profile does not fit SHALL be shown as not fitted rather than hidden, so the difference between the two builds is visible. Products in the unmodelled `hardware` category SHALL be listed with their cost and SHALL NOT offer a picture grid, because nothing renders them.

#### Scenario: Compare cameras in the browser
- **WHEN** the user selects two cameras and two weather presets and asks for a comparison
- **THEN** the panel shows the comparison table and the picture grid

#### Scenario: A category the build does not fit
- **WHEN** the budget tab is selected and the floodlight category is shown
- **THEN** it is marked not fitted on this build, and the expensive tab shows the floodlight it fits

#### Scenario: Unmodelled products compare on cost only
- **WHEN** two `hardware` products are compared
- **THEN** the table shows name, source, verified and price, and no picture grid is produced

## ADDED Requirements

### Requirement: Camera height and distance are adjustable inputs
The what-if panel SHALL expose the camera height and the camera's distance from the pit centre as editable inputs for the selected tab's profile, each starting from that profile's value, and SHALL recompute the height window, the placement window, the far-edge density and the ring coverage on every change.

The panel SHALL show the window beside the input, so a value outside it is visible as it is typed rather than only in the results. Editing these inputs SHALL NOT write to the site profile.

For the budget profile the height SHALL start at 4.00 m within a window of 3.31–8.62 m, and the distance at the solved 12.42 m.

#### Scenario: Sweeping the pole height (U51)
- **WHEN** the camera height is changed from 4.00 m to 6.00 m on the budget tab
- **THEN** the height window, far-edge density, placement window and laser reach are recomputed, and `sites/budget.yaml` is unchanged

#### Scenario: A height outside the window is visible immediately
- **WHEN** 3.00 m is entered on the budget tab
- **THEN** the input is marked against the 3.31 m minimum before the results are read

### Requirement: Candidate parts are always shown and can be switched in
The panel SHALL list the selected tab's candidate parts at all times, whether or not their trigger has fired, each with its price, its trigger and whether that trigger is currently failing. A candidate is a backup held ready; hiding it until it is needed defeats the purpose.

Each candidate SHALL have a control that loads it into the run. Switching one in SHALL recompute every model panel with the part fitted, label the results as a candidate run, and leave the catalogue total and the site profile unchanged. Switching it out SHALL return to the fitted build.

Where a candidate's trigger is failing, the panel SHALL say so next to it, so the part to try is obvious without reading the check output.

#### Scenario: Candidates are visible before they are needed
- **WHEN** the budget tab is open and every check passes
- **THEN** both accelerator candidates are listed with price and trigger, marked not currently triggered

#### Scenario: Switching a candidate in (U52)
- **WHEN** the 26 TOPS accelerator is switched in on the budget tab
- **THEN** density, latency and tracker results recompute with it fitted and are labelled a candidate run
- **AND** the catalogue total stays S$3,941.94 and `sites/budget.yaml` is unchanged

#### Scenario: A failing trigger points at its candidate
- **WHEN** U37 and U40 both fail on the budget tab
- **THEN** the accelerator candidates are marked as triggered, with the failing checks named

### Requirement: Build-tier tabs
The page SHALL carry a tab bar under the header, one tab per site profile that declares a `tier`, ordered budget first. The budget tab SHALL be selected when the page loads.

The selection SHALL be kept in the URL so a reload returns to the same tab.

`GET /api/variants` SHALL return, for each profile that declares a tier: its name, its tier, a label, its hardware-list reference, and its catalogue total; and separately the profile the stack is running.

#### Scenario: Budget is selected on load (U42)
- **WHEN** the dashboard is opened with no tab in the URL
- **THEN** the budget tab is selected and the model panels show budget figures

#### Scenario: Tabs come from the profiles
- **WHEN** `/api/variants` is requested
- **THEN** it lists `budget` (tier budget, hardware list version 65) and `v11` (tier expensive, hardware list version 11), and names the running profile
- **AND** it does not list `phase1`, which declares no tier

### Requirement: Model panels follow the selected tab
The what-if panel, the coverage heatmap, the PoE budget, the power plans and battery runs, the 4G estimate, the laser reach and every cost total SHALL be computed for the selected tab's profile.

The 3D view, the browser video stream, the app events, the fault buttons and the trial pad SHALL stay on the profile the stack is running. Switching tabs SHALL NOT restart, rebuild or reconfigure a container.

When the selected tab is not the running profile, the page SHALL say which profile is live and which is being computed.

#### Scenario: Switching tabs recomputes the models (U44)
- **WHEN** the user switches from the budget tab to the expensive tab
- **THEN** the what-if fields, coverage, PoE, power and cost panels show `v11` figures
- **AND** no container is restarted and the video keeps playing

#### Scenario: Live and computed differ (U45)
- **WHEN** the budget tab is selected and the stack is running `v11`
- **THEN** the page shows a line naming `v11` as live and `budget` as computed
