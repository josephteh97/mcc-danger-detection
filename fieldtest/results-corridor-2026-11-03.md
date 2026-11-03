# Corridor field test: results, 3 November 2026

**Result: the density formula ρ = (f/p)/z and the largest-square formula held to about 1% across the
floor, on one setup. The solved pose failed its pass band, and the vertical stick check wasn't run.**
The experiment is closed on this result.

## Setup

- Redmi Note 13 Pro main camera, RTSP stream 1280 × 720, 23 mm equivalent, on a stand on a chair that
  isn't level, about 0.5 m above the floor.
- Office corridor, 1.8 × 2.5 m, carpet.
- Taped marks (metres from the point under the phone): corners (±0.71, 0.99) and (±0.71, 2.37), centre
  (0, 1.68). This is 1.42 m wide by 1.38 m deep, so 4 cm short of a square. They were taped from an
  earlier layout and not re-taped after the final calibration.

## Lens

| | Value |
|---|---|
| Reprojection error | 0.18 px (band 0.5 px), 28 views, **PASS** |
| fx measured | 877.2 px |
| fx nominal | 850.4 px (3.15% lower) |
| Distortion | k1 +0.067, k2 −0.099 |

## The formula against the clicks

The most direct check. It uses the taped width, the clicked pixels and the calibrated fx, and doesn't
use the solved pose.

| Edge | Tape distance z | Formula (f/p)/z | Measured (px between corners ÷ 1.42 m) | Difference |
|---|---|---|---|---|
| Far | 2.37 m | 370.1 px/m | 373.2 px/m | +0.8% |
| Near | 0.99 m | 886.0 px/m | 881.3 px/m | −0.5% |

The 1–2 cm uncertainty in the hand-placed tape moves these differences by up to about 2%.

For ρ = 370 px/m, the largest-square formula gives W_max 3.46 m, z_max 2.37 m, S 1.41 m, d 1.67 m and a
near edge of 0.96 m. The tape is S 1.42 m, d 1.68 m and near edge 0.99 m, and its near corners span
1252 of the 1280 px across the frame (13 px and 16 px from the sides). So the formula's square does
fill the frame as predicted.

**Limit on this agreement:** z is the taped floor distance, not depth along the lens axis. The solved
pose has the phone about 10 cm ahead of the origin and tilted 17° down, and those two effects roughly
cancel here. With the solved pose, the depth-based prediction is 378 and 875 px/m, also within about
1.5%, but that uses the same clicks. A different tilt or height would need the 3D projection.

## The tool's pass bands

| Step | Result | Detail |
|---|---|---|
| Lens | **PASS** | above |
| Pose | **FAIL** | worst marker 7.83 px (band 2 px), height 0.507 m against 0.45 m taped (band 5 cm) |
| Overlay | PASS | corners 1.3–5.7 px off (band about 26 px) |
| Density | **not run** | no stick was measured |

Solved pose: pitch 17.0° down, roll −2.0°, heading 2.0°, phone at (−0.04, 0.10) m.

- **Pose:** the likely causes are a lens height that was never re-measured and tape 1–2 cm off, but
  neither was confirmed with a tape measure. At the far edge, 2 px is only about 5 mm sideways, so
  the band is hard to meet with hand-placed tape from this low.
- **Overlay:** this PASS is weak evidence. A taped square is drawn at its floor coordinates using the
  pose solved from the same clicks, so it mostly repeats the pose's fit.

## What the corner labels mean

The picture's labels are the pixels of a 1 m vertical pole: 434 and 424 px/m at the far corners. They
are higher than the across-floor 373 px/m because the pole's top is above the phone and nearer to it.
The label doesn't test (f/p)/z on a low, tilted phone, and no real pole or stick was measured against it.

## Not tested

- The vertical density check with a real stick.
- Level and tilted outdoor runs at ρ 100 (tasks 9.2, 9.3), the office preset (9.1a), and 28 and 35 mm.
- The detection sweep, and the ultra-wide distortion test.
- Any height or distance other than this one setup.

Output is in `reports/fieldtest/2026-11-03/` (git-ignored). No recording was kept.
