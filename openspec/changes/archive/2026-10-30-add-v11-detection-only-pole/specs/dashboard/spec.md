## MODIFIED Requirements

### Requirement: 3D view
The page SHALL render a three.js model of the site, driven by the live feed. The model SHALL show:
- the pit, the 1.5 m and 3 m rings and the pole (phase 1) or wheeled stand with its solar skid in Plans B and C (v11)
- the camera's true field of view as a frustum from the fitted lens
- the workers at their true positions, as rigged figures in their posture
- the arm and laser beam at their reported angles, with a glow on the beam and dot
- the strobe and floodlight state, with a visible floodlight cone at night
- the current alarm level

It SHALL also provide:
- physically based materials, tone mapping, a sky and sun that follow the time of day, and soft shadows from the sun
- rain particles, wet ground and haze from the active weather preset
- a switchable px/m heatmap on the ground (green ≥ 100, amber 60–100, red < 60 px/m, in the processed image)
- HUD panels for alarm state and dwell timer, battery charge and plan, PoE used/reserved/budget, 4G uplink and month-to-date data, and active faults
- quality presets (low, medium, high); the medium preset SHALL keep at least 30 frames per second at 1920×1080 on integrated graphics

New three.js add-ons SHALL be vendored and pinned like the existing vendor files.

#### Scenario: Worker moves in 3D
- **WHEN** a worker walks in the world
- **THEN** the worker's marker in the 3D view follows the true position, with at most 0.2 s of lag

#### Scenario: Heatmap matches coverage maths
- **WHEN** the heatmap is on in the v11 profile
- **THEN** the colour at each ring corner matches the band computed by `tools/coverage.py` for that point

#### Scenario: Low preset still usable
- **WHEN** the low preset is chosen
- **THEN** shadows, rain particles and bloom are off and the view still shows every item in the list above
