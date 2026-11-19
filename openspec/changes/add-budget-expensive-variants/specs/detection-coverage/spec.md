## MODIFIED Requirements

### Requirement: Density in the processed image
The coverage maths SHALL report density in the image the detector actually processes: native density divided by the detector's downsampling factor (`detector.input_px` against the native width; 1 when the detector runs on full-resolution tiles). The requirement SHALL be 100 px/m everywhere inside the 3 m warning ring (100 px for a 1.0 m squatting worker), for every profile.

The requirement does not change with the AI box. What changes is what the box can sustain: version 11 processes full-resolution tiles on a Jetson Orin NX, version 56 processes what a Raspberry Pi 5 sustains, taken from `detector.tiles` and `detector.input_px` in `sites/budget.yaml`. Where the budget pole cannot reach 100 px/m across the ring, the check SHALL report the shortfall and the points at which it occurs rather than lower the requirement.

#### Scenario: Full-resolution tiles pass (U12)
- **WHEN** the v11 site runs with `detector.tiles: true`
- **THEN** every point of the 3 m warning ring has at least 100 px/m in the processed image

#### Scenario: Shrunken detector input fails (U13)
- **WHEN** the same site runs with `detector.input_px: 1280` and no tiles
- **THEN** the check reports the ring points below 100 px/m and fails, as expected

#### Scenario: Budget pole density across the ring (U37)
- **WHEN** the budget site runs with the C385's native resolution and its detector settings
- **THEN** the processed density is reported at every point of the 3 m warning ring against the same 100 px/m requirement, with any shortfall named

## ADDED Requirements

### Requirement: Camera standoff is solved, not inherited
A site profile's camera distance from the pit centre SHALL be derived from the largest-zone solver for the fitted camera at the required density, not carried over from another profile. Where a profile's distance differs from the solved one — because the mounting point is fixed on site — the reports SHALL state both and what the difference costs in px/m.

For the budget profile the field-of-view method SHALL be used, on the C385's datasheet figures (N = 3840 px, θ = 91.5° at the 4 mm setting) at ρ = 100 px/m:

| Quantity | Value |
|---|---|
| W_max = N/ρ | 38.40 m |
| z_max = N / (2ρ·tan(θ/2)) | 18.70 m |
| S = W_max·z_max / (z_max + W_max) | 12.58 m |
| d = z_max − S/2 | **12.42 m** |

`sites/budget.yaml` SHALL place the camera at d = 12.42 m from the pit centre.

The distortion method SHALL NOT be used for the budget camera until D has been measured for it (P11); until then the report SHALL say the method was not run rather than substitute another camera's D.

#### Scenario: Budget standoff is solved (U38)
- **WHEN** the largest-zone solver runs for the C385 at ρ = 100 px/m
- **THEN** it gives S = 12.58 ± 0.05 m at d = 12.42 ± 0.05 m, and `sites/budget.yaml` places the camera at that distance

#### Scenario: The solved zone clears the requirement
- **WHEN** the solved zone is checked against the 3 m warning ring round the 2.4 × 1.6 m pit
- **THEN** the required 8.4 m square fits inside the 12.58 m zone with 4.18 m of margin

#### Scenario: The method is the same for both tiers (U14)
- **WHEN** the same field-of-view method runs for the 12 MP Hikvision at ρ = 100 px/m
- **THEN** it reproduces S = 11.5 ± 0.1 m at d = 10.4 ± 0.1 m, so the two tiers are placed alike and may be compared

### Requirement: Pole height is an adjustable input, defaulted from the window
Camera height SHALL be an input the user can change, not a constant. `sites/budget.yaml` SHALL carry a default and the dashboard SHALL expose it, so a height can be tried before it is measured and the measured height can be entered when it is known.

The height window SHALL be computed by the existing rule — h ≥ D_far · tan θ_min with sin θ_min = 2 px / (ρ · 0.1 m), and h ≤ D_near · tan 45° — where **D_far and D_near are the ground distances from the camera to the far and near edges of the 3 m warning ring**, not the optical-axis depth z_max. z_max is a slant limit along the optical axis and is 6.28 m longer than D_far here; using it in place of D_far would raise the minimum height from 3.31 m to 3.82 m, a 0.51 m overstatement.

For the budget pole at d = 12.42 m, with the ring reaching 3.8 m either side of the pit centre:

| Quantity | Value |
|---|---|
| D_near = d − 3.8 | 8.62 m |
| D_far = d + 3.8 | 16.22 m |
| θ_min, from sin θ_min = 2/(100 × 0.1) | 11.537° |
| h_min = D_far · tan θ_min | **3.31 m** |
| h_max = D_near · tan 45° | **8.62 m** |
| default | **4.00 m** |

The default of 4.00 m sits 0.69 m above the minimum, giving a depression angle of 13.9° at the far edge of the ring and 24.9° at the near edge. It is a starting value, not a measurement.

The same rule reproduces version 11's published window of 2.7–5.7 m at d = 9.5 m, so the two tiers' heights are derived alike.

A height outside the window SHALL be flagged with which bound it breaks and by how much, and SHALL NOT be silently clamped.

#### Scenario: Budget height window and default (U49)
- **WHEN** the height window is computed for the budget profile at d = 12.42 m
- **THEN** it is 3.31–8.62 m, and the profile's default height of 4.00 m is inside it

#### Scenario: Measured height outside the window
- **WHEN** a measured tube height of 3.0 m is entered
- **THEN** the pose is flagged as 0.31 m below the minimum, with the far edge's foot-location error stated, and the height is not clamped

#### Scenario: The slant limit is not used as a ground distance
- **WHEN** the height window is computed
- **THEN** it uses D_far = 16.22 m and not z_max = 18.70 m



### Requirement: Alarm latency from the fitted AI box
The alarm-latency estimate SHALL come from the fitted `ai_box`'s `detector_fps` and the profile's detector settings, so that comparing two builds compares their detection rates and not two hardcoded numbers.

`detector_fps` SHALL be traceable to the board's own specification or to a measurement on that board, named in `source`. It SHALL NOT be scaled or inferred from another board's figure.

The budget profile's AI box is a Raspberry Pi 5 8 GB: Broadcom BCM2712, quad-core Cortex-A76 at 2.4 GHz, VideoCore VII GPU, **no NPU and no CUDA**, so there is no TensorRT path and detection runs on the CPU. Its `detector_fps` SHALL be 12 for a YOLO-class person detector with no accelerator fitted, against the Orin NX's 60.

Where the fitted board's rate cannot meet the guide's dwell and escalate thresholds, that SHALL be reported as a finding about the build. The thresholds are the guide's and SHALL NOT be relaxed to accommodate a board.

#### Scenario: Pi against Jetson (U39)
- **WHEN** alarm latency is computed for the budget and expensive profiles
- **THEN** each is reported with its fitted AI box, its detector frame rate and the source of that rate

#### Scenario: Latency against the guide's thresholds (U40)
- **WHEN** the budget pole's latency is checked at 12 fps
- **THEN** it is compared against the guide's 1 s dwell and 3 s escalate unchanged, and a rate too low to meet them is reported as a design finding, not accommodated

#### Scenario: Rate is traceable (U41)
- **WHEN** the budget AI box's `detector_fps` is read
- **THEN** its `source` names the Raspberry Pi 5 specification and records that no accelerator is fitted
