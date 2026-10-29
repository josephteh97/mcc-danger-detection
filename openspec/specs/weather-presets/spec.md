# weather-presets Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: Sixteen presets
The world SHALL provide exactly these 16 weather and lighting presets, selected with `--weather <name>` or `WEATHER=<name> docker compose up`:

`clear`, `overcast`, `light_rain`, `tropical_downpour`, `thunderstorm`, `regional_haze`, `dust_or_smoke`, `morning_mist`, `dense_fog`, `humid_lens`, `night_clear`, `night_no_floodlight`, `night_rain`, `low_sun_glare`, `mud_splash`, `strong_wind`.

An unknown name SHALL be rejected with the list of valid names.

#### Scenario: All presets render
- **WHEN** one frame is rendered in each of the 16 presets
- **THEN** each render succeeds at 1280×720, and each preset reports its sun factor, wind speed and storm events

#### Scenario: Unknown preset
- **WHEN** the world is started with `--weather snow`
- **THEN** it exits with an error that lists the 16 valid presets

### Requirement: Image effects
Each preset SHALL change the camera image according to its physics:
- **Scattering by distance (Koschmieder's law):** used for fog, mist, haze, dust, smoke and rain. It is set by visibility in metres and uses the camera geometry, so the far side of the site fades more than the near side.
- **Rain:** falling streaks slanted by the wind, darker wet ground, and drops stuck on the housing window.
- **Humid air:** a fogged window that blurs and whitens the whole image.
- **Night:** low light and sensor noise. The floodlight's pool lights the pit, except in `night_no_floodlight`, which uses camera infrared only.
- **Thunderstorm:** lightning flashes.
- **Sun glare:** flare spots and a darkened scene. The darkening is reduced by the camera's true WDR.
- **Mud:** a splash over the window's lower-left corner.
- **Strong wind:** mast sway.

The visibility, sun-factor and sway values SHALL be kept in one table in `world/weather.py`. They are assumptions, to be calibrated against Meteorological Service Singapore records and site footage.

#### Scenario: Far side fades more in fog
- **WHEN** a frame is rendered in `dense_fog`
- **THEN** the contrast loss for a worker at the far side of the site is greater than for one at the near side

### Requirement: Worker contrast
The twin SHALL measure worker contrast as the brightness difference between the worker and the surrounding ground, and report it as a percentage of the clear-day value.

The guide's measured values are:

| Preset | Contrast vs clear |
|---|---|
| overcast | 60% |
| light_rain | 50% |
| tropical_downpour | 27% |
| thunderstorm | 24% |
| regional_haze | 67% |
| dust_or_smoke | 49% |
| morning_mist | 51% |
| dense_fog | 19% |
| humid_lens | 49% |
| night_clear | 69% |
| night_no_floodlight | 12% |
| night_rain | 56% |
| low_sun_glare | 60% (about 90% with true WDR) |
| mud_splash | 100% (worker outside the splash) |
| strong_wind | 76% |

#### Scenario: Bad weather lowers visibility (V19)
- **WHEN** all 16 presets are rendered with the same worker position
- **THEN** `dense_fog` and `tropical_downpour` each give lower worker contrast than `clear` (about 19% and 27% of clear)

#### Scenario: Haze at site range (V20)
- **WHEN** the worker is rendered at site range in `regional_haze`
- **THEN** the worker keeps more than 60% of clear-day contrast (about 67%)

#### Scenario: Floodlight at night (V22)
- **WHEN** the worker is rendered in `night_clear` and in `night_no_floodlight`
- **THEN** contrast with the floodlight is at least twice the contrast without it (about 69% against 12%)

### Requirement: Weather feeds the rest of the twin
Each preset SHALL also provide:
- a sun factor for the power model
- a wind speed for mast sway and the laser arm
- storm events for the scenario runner

`thunderstorm` SHALL schedule two events: a power surge that reboots the Orin, and a 30 s 4G drop.

The 3-day battery low points SHALL match the guide's weather table within ± 2 points:

| Preset | 3-day low point |
|---|---|
| clear | 70% |
| overcast | 8% |
| regional_haze | 33% |
| dust_or_smoke | 49% |
| morning_mist | 17% |
| humid_lens | 66% |
| low_sun_glare | 70% |
| mud_splash | 70% |
| strong_wind | 49% |
| night presets | same as clear |
| light_rain, tropical_downpour, thunderstorm, dense_fog | runs flat |

#### Scenario: Battery after 3 days of each preset
- **WHEN** the power model runs 3 days under each preset's sun factor
- **THEN** each preset's lowest charge matches the table above

#### Scenario: Thunderstorm events
- **WHEN** a scenario runs in `thunderstorm`
- **THEN** the scenario runner restarts the Orin container once (surge) and cuts the 4G link for 30 s

