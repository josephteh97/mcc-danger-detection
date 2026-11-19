## Context

The twin already separates "which pole" from "how the pole is simulated": `site.yaml` selects a profile, `sites/<profile>.yaml` holds the geometry and the fitted products, and `catalog/<category>/` holds one YAML per product with a `_schema.yaml` saying which fields the simulator reads. Version 11 was added that way and nothing in the app changed.

Hardware list version 56 pushes on three places that profile mechanism does not yet cover:

1. **Shape.** Version 56 fits things the catalogue has no home for — a pole bracket, an arm mount, a 2-axis gimbal, an Ethernet aim controller, a hardware interlock, an IP66 enclosure with a pole kit and a breather, weatherproofing, cabling, breakers, signage. Roughly a third of its lines cannot be entered today.
2. **Absence.** Version 56 fits no floodlight, no router and no monitor. `load_site()` currently refuses a profile missing any of the eight base categories.
3. **Comparison.** The point of having both builds is seeing them against each other. The what-if panel is hardcoded to `v11` and the dashboard has no navigation at all — it is one scrolling column of panels.

The pole itself is also architecturally different, not merely cheaper: detection moves from a Jetson to a Pi 5, the bus moves from 24 V to 48 V, the uplink moves from an outdoor router to a USB modem on the Pi, and the laser gains a hardware interlock in series with its supply.

## Goals / Non-Goals

**Goals**

- Two named build tiers the user can switch between in one click, budget selected by default.
- Every version 56 line item represented exactly once in the catalogue, checkable by machine.
- The existing models — coverage, PoE, power, 4G, laser reach, alarm latency — all run on the budget pole with no new maths invented where the old maths already applies.
- Phase 1 untouched: same profile, same checks, same counts.

**Non-Goals**

- Not a hardware recommendation. The twin reports both tiers; choosing is the purchasing decision.
- Not a live A/B of two running stacks. One pole runs at a time; the tab compares computed models, not live video.
- Not a rewrite of the cost model. Catalogue totals stay a sum of `price_sgd`; freight, GST and labour stay out, as they are today.
- Not a correction of the version 56 document. The twin reconciles against it and reports the gap.

## Decisions

### D1. A tier on the profile, not a third axis

A site profile gains one optional key, `tier: budget | expensive`. The tab bar is built from the profiles that declare one. This keeps a single selector (`profile`) rather than introducing a second dimension that could disagree with it, and it leaves `phase1` — which must never move, because the guide checks pin it — out of the pair by simply not declaring a tier.

Rejected: a `variant:` key inside one site file holding two product sets. That would have made `sites/budget.yaml` a fork of `sites/v11.yaml` and put two poles' geometry in one file, when the two poles differ in pose, bus voltage and fitted categories.

### D2. The tab moves the models, not the containers

Switching the tab re-runs the what-if panel, coverage, PoE, power, 4G and cost totals for that profile. It does not restart the stack: the world, camera, Orin sandbox and emulators keep running the profile they were started with. When the two differ the dashboard shows a line saying which profile is live and which is being computed.

The alternative — making the tab restart six containers — would turn a comparison click into a 30-second rebuild and would lose the running scenario. The models are pure functions over a site profile (that is what made the what-if panel testable without the stack), so computing another profile's numbers is cheap and safe.

### D3. Budget becomes the default

`site.yaml` moves to `profile: budget`. This is what the user asked for and it matches intent: the budget pole is the one being costed for purchase. `TWIN_PROFILE` still overrides, the five phase-1 scripts still load `phase1` explicitly, and `tests/smoke_v11.py` still loads `v11` explicitly, so no existing check changes its answer. The one real consequence is that a bare `docker compose up` starts a different pole than it did before; that is a breaking change and is written in the README.

### D4. Two kinds of catalogue entry

Version 56 lines split cleanly in two:

- **Modelled** — the entry's fields change a simulation result. These get a category with a schema: existing `camera`, `ai_box`, `switch`, `speaker`, `laser`, `battery`, `solar`, `power_conv`, `mast`, plus new `gimbal`, `controller`, `modem`, `enclosure`.
- **Unmodelled** — the entry carries cost and mass and nothing else: mounts, weatherproofing, cabling, breakers, signage, spares, the calibration board. These go in one new `hardware` category with a minimal schema.

The split keeps the repo's rule that "each category's spec fields change the simulation" honest. The alternative — inventing a `mount` category with `sway_deg_per_ms2`-style fields nobody computes — would put fabricated physics in the catalogue to satisfy a shape.

A mount that later earns a model (say the VMB-350's clamp range against the tube diameter) can be promoted out of `hardware` into its own category without touching the site profile, because the profile names files, not schemas.

### D5. `bom_item` makes the mapping checkable

Every budget product file carries `bom_item: "<number>"` matching the hardware list's item column, including letter suffixes (`"1a"`, `"11c"`). The reconciliation check then has something to verify rather than something to assume:

- every item number in the hardware list appears on exactly one fitted budget product;
- every fitted budget product carries a `bom_item` that the hardware list contains;
- the sum of `price_sgd × qty` over them equals the hardware list's total for those lines.

`bom_item` is optional on products generally, so phase 1 and v11 files are unaffected.

### D6. Not-fitted categories

`products.<category>: null` means the pole does not carry that category. `load_site()` accepts it for base categories, `fitted(site, category)` returns `[]` (it already returns `[]` for a missing entry), and every model that reads a category must already handle the empty list because `power_conv` and `monitor` are list-valued. The night and floodlight models report "no floodlight fitted" instead of substituting a default.

Rejected: a zero-watt, zero-price `none_floodlight` placeholder product. It would have kept the loader simple at the cost of making every report claim a floodlight exists, and it would have polluted the comparison tool's product list.

### D7. The laser controller moves into the catalogue

`sites/v11.yaml` carries a `laser_controller:` block with `watts_typ`, `watts_max`, `price_sgd` and the IP and ports. The watts and price are product facts that belong in a catalogue file; the IP and ports are site wiring and stay in the profile. Version 56 fits a different controller (Olimex ESP32-POE-ISO-IND) plus a separate hardware interlock, so both profiles end up fitting from the same `controller` category and the what-if panel edits them through the ordinary product path rather than through the three bespoke `SITE_FIELDS` entries it has today.

### D8. 48 V bus reuses the 24 V maths

`devices/power_model.py` already takes `bus_v` and an `efficiency` map from the profile. The budget chain is a different set of stages (MPPT, 48→12 V, 48→5 V, PoE+ switch) with the same structure, so this is configuration, not new code. The one genuinely new piece is the cutoff: version 11 drops load in two stages under software control, version 56 fits a Victron BatteryProtect that opens the whole bus at a voltage threshold. Modelled as a `power_conv` entry with `kind: cutoff` and a cutoff voltage, which the battery run reads instead of the two-stage percentages when it is fitted.

### D9. Four PoE ports and exactly four devices

The budget switch has four ports and the budget pole has four PoE devices: camera, horn, Pi and aim controller. That is a zero-margin design and the port map should say so loudly rather than silently overflowing. `devices/poe_model.py` gains a port-count check that fails with a named error listing the devices that did not get a port, alongside the existing wattage-budget check.

### D10. Coverage on the C385 and the Pi

Nothing in the coverage maths is camera-specific — it reads resolution, field of view and optionally `dori_fp_px`, and it already supports both the tiled and the fixed-input detector paths. The budget profile sets `detector.tiles` and `detector.input_px` to what a Pi 5 can actually sustain, which is the honest difference from a Jetson: the same picture, fewer pixels processed per second. Alarm latency follows from `ai_box.detector_fps` through the existing model.

The Pi 5's figures come from its own specification, not from scaling the Jetson's: Broadcom BCM2712, quad-core Cortex-A76 at 2.4 GHz, VideoCore VII GPU, and critically **no NPU and no CUDA**, so there is no TensorRT path and detection runs on the CPU. A YOLO-class person detector with no accelerator fitted runs at roughly 12 fps on a Pi 5, against the Orin NX's 60. That single number is the architectural difference between the two tiers, and it propagates straight into alarm latency and into how much of the warning ring can be processed per frame.

Version 56 fits no AI accelerator. If the budget pole later cannot meet the guide's 1 s dwell at 12 fps, the fix is a PCIe accelerator HAT as a new line on the hardware list, not a change to the thresholds — the thresholds are the guide's and stay verbatim.

### D19. The camera's distance is solved, not inherited

Version 56 does not say where the tube stands. Carrying version 11's 9.5 m standoff across would mean quoting coverage figures for a pose nobody chose.

Instead the standoff comes from the largest-zone solver that `openspec/specs/detection-coverage/spec.md` already defines, field-of-view method, on the C385's own figures (N = 3840 px, θ = 91.5° at the 4 mm setting) at the 100 px/m requirement:

```
W_max = N/ρ                        = 38.40 m
z_max = N / (2ρ·tan(θ/2))          = 18.70 m
S     = W_max·z_max/(z_max+W_max)  = 12.58 m
d     = z_max − S/2                = 12.42 m
```

So `sites/budget.yaml` places the camera 12.42 m from the pit centre. The 3 m warning ring around the 2.4 × 1.6 m pit needs an 8.4 m square and the solved zone is 12.58 m, so there is 4.18 m of margin — the budget camera is not short of pixels at this distance, which is the result worth having before anything is bought.

The same four lines reproduce version 11's published reference numbers (S = 11.53 m at d = 10.43 m, against U14's 11.5 ± 0.1 m at 10.4 ± 0.1 m), so both tiers are placed by the same method and the comparison between them is like for like.

The distortion method is not used for the budget camera: it needs D, which comes from a field measurement (P11), and the C385's has not been taken. The report says so rather than borrowing another camera's D.

### D20. Height is an input, and the distance in the height rule is a ground distance

Height is derived the same way as the standoff — a distance times the tangent of an angle — but the distance is **the ground distance to the warning ring**, not z_max. z_max is a slant limit along the optical axis; D_far is the ground distance to the thing the camera has to resolve. They differ by 6.28 m here, and substituting z_max would put h_min at 3.82 m instead of 3.31 m.

The repo already has this rule and it reproduces version 11's published 2.7–5.7 m window exactly, so it is kept as written:

```
D_near = d − 3.8 = 8.62 m        D_far = d + 3.8 = 16.22 m
sin θ_min = 2 px / (ρ · 0.1 m)   → θ_min = 11.537°   (feet located to ±10 cm)
h_min = D_far · tan θ_min = 3.31 m
h_max = D_near · tan 45°  = 8.62 m
```

Height is then a **default inside that window, not a constant**: `sites/budget.yaml` carries 4.00 m and the what-if panel exposes it, because the tube's real height is a field measurement that has not been taken and the point of the panel is to try values before committing. `SITE_FIELDS` already carries `camera_height_m` and `stand_distance_m`, so this is defaults and a window readout, not new machinery. A value outside the window is flagged with the bound it breaks, never clamped — clamping would hide exactly the finding the check exists to surface.

### D21. The accelerator is a candidate line, triggered by density and latency together

The budget pole's binding constraint is not frame rate on its own. At d = 12.42 m the far edge of the ring has 115.3 px/m natively, which clears the 100 px/m requirement — but only at full resolution. A 640 px detector input gives 19.2 px/m and 1280 px gives 38.4; the minimum input that reaches 100 px/m is 3330 px. So tiles are mandatory, and tiling the zone at the default pose takes about 3 tiles, turning the Pi's 12 fps into about 4 fps of complete coverage.

At 4 fps the V12 latency budget still holds with room (≈620 ms of 1.5 s), so a trigger on latency alone would miss the problem. What 4 fps actually threatens is tracking: a worker at 1.4 m/s moves 0.35 m between frames, about 40 px against a person box roughly 58 px wide, and the dwell timer depends on the tracker holding one ID.

Hence `trigger: [U37, U40]` rather than U40 alone, and the tracker displacement reported alongside. The accelerator stays a candidate — specified, priced, excluded from the total and from every model — until a check actually fails. Promoting it is an edit to the hardware list first, then to the BOM data file; the twin never adds a line to the build on its own.

Two caveats sit on the entry. The HAT is Raspberry Pi 5 only and occupies the PCIe lane, which is free here because the Pi boots from the microSD card in item 2. And its rated ambient range is 0–50 °C: a pole-top IP66 box in Singapore sun can exceed that, so if the accelerator is ever fitted, the enclosure's thermal design becomes a line of its own.

### D11. Check numbering

`tests/smoke_budget.py` uses **U27–U48**, after v11's U11–U26. The phone field test's P01–P11 is a separate series and does not collide. Each check registers with `@check("ID", "title")` and returns `(passed, measured, criterion)` like every other quick check.

### D12. The item rows are the authority, and the gap is on the record

The reconciliation check compares the catalogue total against the hardware list's **item rows**, which sum to **S$3,419.59**. That is the figure the twin uses.

The document's printed grand total of S$3,659.10 comes from a hand-maintained totals table whose Laser gimbal (+S$21.64) and Power (+S$217.87) subtotals have drifted from the items beneath them. `catalog/bom/v56.yaml` records both numbers and marks the table's as stale, so the check passes against a figure that is defensible line by line while the discrepancy stays visible rather than being quietly resolved in either direction.

If the hardware list is later corrected, the data file's `totals_table_sgd` is updated and the stale marker removed; the item rows and therefore the catalogue total do not move.

## Risks / Trade-offs

- **The default moves.** Anyone with muscle memory for `docker compose up` gets a different pole. Mitigated by the README, the dashboard tab showing which profile is live, and `TWIN_PROFILE` still working.
- **Unverified product figures.** Every version 56 price is real and sourced, but most of the optical, thermal and power figures are not yet checked against datasheets. All budget files start `verified: false`, and the proposal's task list includes the verification pass. The what-if panel already marks unverified figures with `*`.
- **Category sprawl.** Five new categories is a lot at once. The `hardware` catch-all is what stops it being nine; the trade is that a `hardware` entry gets no physics until someone promotes it.
- **Pi 5 detector figures.** `detector_fps` for a Pi 5 running the person detector is the number the whole alarm-latency result rests on, and it is the one most likely to be optimistic until measured on the actual board. Flagged in the open questions.
- **Two poles, one stack.** The tab compares models, not behaviour. Comparing alarm behaviour still means starting each profile in turn.

## Migration Plan

1. Add the categories, schemas and the 32 budget product files; the catalogue validates with nothing else changed.
2. Add `sites/budget.yaml` and `app/config.budget.yaml`; add `tier:` to `sites/v11.yaml`; the loader accepts null-fitted categories.
3. Teach the models the budget pole: 48 V chain, cutoff device, port count, modem uplink, Pi detector.
4. Parameterise `dashboard/v11.py` on profile and add `/api/variants`; add the tab bar.
5. Flip `site.yaml` to `profile: budget` **last**, after `tests/smoke_budget.py` passes, so the default never points at a profile that does not yet compute.
6. Update the README and `CLAUDE.md` check counts and the new default.

Rollback is one line: `site.yaml` back to `profile: v11`. The budget profile and its catalogue entries are additive and harm nothing if unused.

## Open Questions

- **How tall is the tube, and does it stand 12.42 m from the pit?** The standoff is solved (D19) and the height defaults to 4.00 m inside a 3.31–8.62 m window (D20), both adjustable in the panel. The field measurement replaces the default; if the tube is outside the window or at a different distance, the windows and the density report say what that costs in px/m.
- **Does the tracker hold at ~4 fps?** This is the live question, not latency. Tiles are mandatory to meet the density requirement and they cut the Pi's 12 fps to roughly 4 (D21), at which a walking worker moves ~40 px between frames against a ~58 px box. If IoU association breaks, the dwell timer breaks with it, and the accelerator's trigger fires.
- **Does the horn's PoE class fit the 120 W budget alongside the Pi's PoE HAT?** Four devices on a 120 W switch should be comfortable, but the horn's draw under full alarm is the worst case and is currently a typical value.
- **Should `phase1` get a tier?** Left out deliberately for now. If someone wants three tabs, the mechanism already allows it — it is one key in one file.
- **Who corrects the hardware list's totals table?** Not blocking: the twin reconciles to the item rows at S$3,419.59 and records the table's S$3,659.10 as stale. Worth fixing in the document before purchase so the two agree.
