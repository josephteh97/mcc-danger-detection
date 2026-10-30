# detection-coverage Specification

## Purpose
How the v11 stand camera's coverage is worked out before purchase: lens distortion from the datasheet, pixel density at a ground point and in the image the detector processes, the largest zone one camera covers, the stand placement and height windows, and the pixel-height miss model that ties detection to how tall a worker appears.
## Requirements
### Requirement: Distortion strength from the datasheet
`catalog/effects.py` SHALL derive the lens distortion from the camera's native width N, horizontal field of view θ and centre lens ratio `dori_fp_px` (f/p, from the DORI table as px/m × distance): q = (N/2) / (f/p · tan(θ/2)) and D = 3(1 − q) / tan²(θ/2). Without `dori_fp_px`, D SHALL be 0 (field-of-view method).

#### Scenario: 12 MP Hikvision at 2.8 mm (U11)
- **WHEN** the camera is `bullet_12mp_hik_ids2cd7ac6g2_izhsy` (4,000 px, 102°, `dori_fp_px` 2,840)
- **THEN** q = 0.571 ± 0.005 and D = 0.844 ± 0.01

#### Scenario: No DORI figure
- **WHEN** a camera file has no `dori_fp_px`
- **THEN** D is 0 and f/p comes from N and θ alone

### Requirement: Density at a ground point
The native density at a ground point SHALL be (f/p) · g / z, where g = 1 − D·u², u is the tangent of the point's angle from the optical axis, and z is the exact depth along the optical axis, not the slant range.

#### Scenario: Centre of the image
- **WHEN** a point lies on the optical axis at depth 10 m with the 12 MP Hikvision
- **THEN** its native density is 284 ± 1 px/m

### Requirement: Density in the processed image
The coverage maths SHALL report density in the image the detector actually processes: native density divided by the detector's downsampling factor (`detector.input_px` against the native width; 1 when the detector runs on full-resolution tiles). The v11 requirement SHALL be 100 px/m everywhere inside the 3 m warning ring (100 px for a 1.0 m squatting worker).

#### Scenario: Full-resolution tiles pass (U12)
- **WHEN** the v11 site runs with `detector.tiles: true`
- **THEN** every point of the 3 m warning ring has at least 100 px/m in the processed image

#### Scenario: Shrunken detector input fails (U13)
- **WHEN** the same site runs with `detector.input_px: 1280` and no tiles
- **THEN** the check reports the ring points below 100 px/m and fails, as expected

### Requirement: Largest-zone solver
`tools/coverage.py` SHALL compute, for a camera at the required density, the largest square zone and the camera's distance from its centre, by both methods:
- field of view: W_max = N/ρ, z_max = N / (2ρ·tan(θ/2)), S = W_max·z_max / (z_max + W_max), d = z_max − S/2
- distortion: u_opt solves 1 − 3D·u² − 4D·u³ = 0, g_opt = 1 − D·u_opt², c = (f/p)/ρ, S_max = c·2·g_opt·u_opt / (1 + 2·u_opt), d_S = g_opt·c − S_max/2

#### Scenario: Reference numbers (U14)
- **WHEN** the solver runs for the 12 MP Hikvision at ρ = 100 px/m
- **THEN** the field-of-view method gives S = 11.5 ± 0.1 m at d = 10.4 ± 0.1 m
- **AND** the distortion method gives S_max = 11.2 ± 0.1 m at d_S = 17.1 ± 0.2 m

### Requirement: Stand placement and camera height windows
The coverage tool SHALL report the allowed distance from the zone centre and the allowed camera height for the fitted camera and site, and flag a pose outside them:
- distance: the near corners fit the field of view, and the far edge keeps the required density
- height: h ≥ D_far · tan θ_min, with sin θ_min = 2 px / (ρ · 0.1 m), so feet are located to ±10 cm; and h ≤ D_near · tan 45°

#### Scenario: v11 site pose passes (U15)
- **WHEN** the v11 site has the stand 9.5 m south of the pit centre with the camera 3.8 m up
- **THEN** the pose is inside both windows: the far edge of the warning ring has 122 ± 3 px/m (field-of-view method) and the camera height is between 2.7 m and 5.7 m

#### Scenario: Stand too close (U16)
- **WHEN** the stand is moved to 5 m from the pit centre
- **THEN** the near corners of the warning ring fall outside the image and the pose is flagged

