## MODIFIED Requirements

### Requirement: PoE port map and budget
`devices/poe_model.py` SHALL model the fitted PoE switch from the fitted products and the active profile's `poe_ports:` map, reporting actual draw and power reserved by class and checking both against the switch's PoE budget.

For version 11 the map SHALL be: port 1 camera (PoE+ class 4), port 2 IP horn (class 4, worst case), port 3 4G router data only (the router has its own injector), port 4 AI box over PoE++ (802.3bt class 6) through a splitter, port 5 laser controller (class 0), ports 6–8 spare.

For version 65 the map SHALL be an 8-port switch with four PoE devices fitted: port 1 camera, port 2 IP horn, port 3 AI box (the Pi's PoE HAT), port 4 laser aim controller, ports 5–8 spare. The 4G modem is on the Pi's USB and takes no port.

The model SHALL check **port count**, not only wattage: when the PoE devices outnumber the switch's ports it SHALL fail with an error naming the devices left without a port. It SHALL also report the **spare port count**, and SHALL flag a build with zero spare ports as a finding — a pole with no free port cannot take a laptop at commissioning or during fault-finding. This is why version 65 moved from a 4-port to an 8-port switch.

#### Scenario: v11 budget (U17)
- **WHEN** the v11 products are fitted to a 240 W switch
- **THEN** reserved power is 135.4 W, actual draw is 88 ± 5 W, and the check passes

#### Scenario: Undersized switch (U18)
- **WHEN** the switch budget is set to 90 W
- **THEN** the check fails on reserved power and names the ports that would be refused

#### Scenario: Budget pole has spare ports (U29)
- **WHEN** the budget pole's four PoE devices are fitted to the 8-port switch
- **THEN** the check passes on wattage and reports four spare ports

#### Scenario: Zero spare ports is a finding
- **WHEN** a profile fits exactly as many PoE devices as the switch has ports
- **THEN** the check reports zero spare and flags it, even though every device has a port

#### Scenario: One device too many (U30)
- **WHEN** nine PoE devices are fitted to the budget pole
- **THEN** the check fails naming the device left without a port, before any wattage check runs

### Requirement: 24 V bus and conversion losses
The power profile SHALL compute bus load from the fitted products' typical and worst watts and the active profile's `power.efficiency` map.

Every fitted product that is powered from the bus SHALL carry its DC input window (`input_v_min`, `input_v_max`), and the model SHALL check that window against the voltage range the fitted battery can actually reach — cell count times the per-cell range, from float and absorption down to the cutoff. A product whose window is narrower than the pack's swing SHALL be reported with the charge and cutoff settings that would keep the bus inside it, because those are configuration, not extra hardware.

For version 11 the bus is 24 V and the efficiencies are: 24→54 V step-up 94%, PoE cable 97%, PoE++ splitter 90%, 24→12 V 92%.

For version 65 the bus is 48 V (a 51.2 V LiFePO4 pack) and the chain is: MPPT charge controller to the pack, the pack direct to the PoE+ switch, 48→12 V for the gimbal servos and 48→5 V for the laser module, with the PoE cable loss as before. Each stage's efficiency SHALL come from `sites/budget.yaml`, not be hardcoded.

#### Scenario: AI box over PoE++ (U20)
- **WHEN** the AI box draws 25 W
- **THEN** the bus supplies 30.5 ± 0.5 W for it

#### Scenario: Continuous load (U21)
- **WHEN** the v11 pole runs with no alarms
- **THEN** the average bus load is between 65 and 75 W

#### Scenario: Switch input window against the pack's swing (U56)
- **WHEN** the fitted switch's DC input window is checked against the fitted battery's cell count and per-cell voltage range
- **THEN** any bus voltage the pack can reach outside that window is reported, naming the MPPT absorption setting and the cutoff setting that keep it inside
- **AND** for the budget pole the 48–56 V window requires absorption at or below 3.50 V/cell and a cutoff at or above 48 V

#### Scenario: Budget pole continuous load (U32)
- **WHEN** the budget pole runs with no alarms on the 48 V bus
- **THEN** the average bus load is reported with each conversion stage's loss itemised, and the 2.56 kWh pack's runtime without sun follows from it

### Requirement: Power plans
`devices/power_model.py --profile <profile>` SHALL support each profile's plans.

Version 11 SHALL keep:
- Plan A (primary): shared site socket, 24 V 240 W supply, 50 Ah LiFePO4 backup with DC UPS, and a socket schedule (on, off at night, off at weekends)
- Plan B (backup): 4 × 250 W panels, MPPT controller, 200 Ah LiFePO4
- Plan C (backup): Plan B plus a 20 A charger fed by the socket schedule

Version 65 SHALL have one plan: 4 × 100 W panels in series through a Victron SmartSolar MPPT 100/20-48 into a 51.2 V 50 Ah (2.56 kWh) pack, with no site socket. A solar-only pole has no fallback, so the run SHALL report the consecutive overcast days it survives rather than only a pass or fail.

#### Scenario: Plan B, three heavily overcast days (U22)
- **WHEN** Plan B runs 3 days at 30% of normal sun
- **THEN** the lowest charge stays above 10% and Stage 2 never triggers

#### Scenario: Budget pole on solar only (U33)
- **WHEN** the budget plan runs at 30% of normal sun
- **THEN** the run reports the number of consecutive days before the cutoff opens, and the lowest state of charge reached

### Requirement: Battery monitor and two-stage shutdown
Where a profile fits a battery monitor, the power profile SHALL raise alerts at the profile's `monitor_alerts_pct` and follow its staged shutdown. For version 11 that is: alerts at 50%, 30% and 10%; floodlight, strobe, servos and laser off at 30% (back on at 40%); the step-up converter, and with it the switch, AI box, camera, horn and laser controller, off at 10% (back on at 20%); and the 4G router on until the battery's own cut-off.

Where a profile instead fits a `power_conv` with `kind: cutoff`, the model SHALL use that device's cutoff and reconnect voltages in place of the staged percentages, and SHALL report that load shedding is a single hardware event rather than a software sequence. Version 65 fits a Victron BatteryProtect 48V-100A and no battery monitor module; its pack's own BMS and RS485 port provide the state of charge.

#### Scenario: Plan A weekend switch-off (U23)
- **WHEN** Plan A's socket is off for 60 hours
- **THEN** Stage 1 and then Stage 2 trigger in order, the router stays on for at least 10 hours after Stage 2, and the run reports the hours without an alarm

#### Scenario: Hardware cutoff instead of staged shedding (U34)
- **WHEN** the budget pole's pack falls to the BatteryProtect's cutoff voltage
- **THEN** the whole bus opens in one event, the run reports the time to that event, and no partial shedding is modelled

#### Scenario: No monitor fitted is reported (U35)
- **WHEN** the budget profile's power run starts
- **THEN** it records that no battery-monitor product is fitted and that state of charge comes from the pack's own BMS

### Requirement: Laser reach on the stand
The laser geometry SHALL come from the active profile: the pivot height and position, the hardware stops, and a check SHALL confirm the beam can reach every point of the 1.5 m alarm zone.

Version 11 SHALL keep its pivot 1.1 m up directly below the camera with stops 5°–45° below horizontal. Version 65 SHALL take the gimbal pivot and the stops from `sites/budget.yaml`, where the gimbal is carried on the WiTi arm on the same tube as the camera.

#### Scenario: Reach covers the alarm zone (U26)
- **WHEN** the stand is 9.5 m south of the pit centre
- **THEN** the far corner of the 1.5 m alarm zone, 12.1 m from the pivot, is within the 5° stop's reach of 1.1 / tan 5° = 12.57 m

#### Scenario: Budget gimbal reach (U48)
- **WHEN** the budget pole's gimbal pose is checked against the 1.5 m alarm zone
- **THEN** the reach is reported with its shortfall in metres if any, and the fitted laser is confirmed Class 2 at 1 mW

## ADDED Requirements

### Requirement: Uplink without a router
`tools/network.py` SHALL take the pole's uplink from the fitted `router` where one is fitted, and from the fitted `modem` where none is. A pole with neither SHALL be reported as having no uplink rather than assumed to have one.

Where the modem carries the VPN node (`carries_vpn_node: true`), the remote-access paths SHALL be modelled as terminating on the AI box rather than on a separate router, and the model SHALL note that a hung AI box takes the remote path down with it — there is no independent route back in.

#### Scenario: Budget pole 4G data (U31)
- **WHEN** the budget pole's monthly data is estimated with the version 65 event rate and clip size
- **THEN** the estimate is reported against the SIM plan and the uplink is attributed to the USB modem, not a router

#### Scenario: Single point of remote failure (U36)
- **WHEN** the budget pole's remote paths are modelled
- **THEN** the report states that the VPN node runs on the AI box and that an AI box hang removes remote access, unlike version 11 where the router keeps its own path

### Requirement: Lightning protection zone
A pole profile MAY fit a `lightning` air terminal. Where one is fitted, the coverage tool SHALL check that every pole-mounted item lies inside its protected volume, using the protective-angle method of SS 555 / IEC 62305 at the terminal's `protection_angle_deg` (45° unless the product says otherwise).

An item at height `h` and horizontal offset `r` from the pole axis is protected when `r ≤ (h_tip − h) · tan(angle)`, where `h_tip` is the terminal's tip height — the pole height plus the rod's own length. The check SHALL run over the camera, the gimbal head, the enclosure and the solar array, taking each one's height and offset from the site profile, and SHALL name any item that falls outside the cone together with the extra tip height that would bring it in.

The air terminal SHALL be the highest point on the structure. A profile where any fitted item sits above the tip SHALL fail the check rather than report a partial cone.

A solar array on its own frame away from the pole is a separate structure. Where its offset puts it outside the cone, the check SHALL say so and SHALL NOT assume a second terminal that is not in the bill of materials.

#### Scenario: Budget pole inside the cone (U53)
- **WHEN** the budget pole fits a 1 m air terminal above a camera at 4.00 m with the gimbal on its 40 cm arm
- **THEN** every pole-mounted item is inside the 45° cone and the clearance of the tightest one is reported

#### Scenario: Rod too short
- **WHEN** the terminal's tip is below the camera's height plus its bracket offset
- **THEN** the check fails naming the camera and the extra tip height needed

#### Scenario: Array outside the cone
- **WHEN** the solar array stands clear of the pole on its own frame
- **THEN** the check reports it as outside the pole's protected volume rather than silently including it

### Requirement: Surge protection coverage
Every conductor that leaves the enclosure SHALL have a fitted `spd` on it, and the check SHALL enumerate those conductors from the fitted products rather than from a count typed into the profile: each PoE device's Ethernet run, the PV string, and any DC run to a pole-top load.

For each line the check SHALL confirm the fitted device's rating covers that line's duty — in particular that an Ethernet SPD on a PoE+ or PoE++ line is rated for that class, since a device rated only to 802.3af on a 30 W line is a silent mismatch. A line without an SPD, or with one of insufficient class, SHALL be named.

The model SHALL record that an air terminal without surge protection protects the structure and not the electronics: the damaging event is the induced surge from a nearby strike on the Ethernet and DC runs, which needs no direct hit. A profile fitting `lightning` but no `spd` SHALL be flagged.

Every SPD's earth SHALL reference the same earthing point as the air terminal; the profile SHALL carry one earth reference, not one per device.

#### Scenario: Every exit line protected (U54)
- **WHEN** the budget pole's conductors leaving the enclosure are enumerated
- **THEN** the camera line, the horn line and the PV string are listed, each with its fitted SPD, and any unprotected line is named

#### Scenario: Class mismatch on a PoE+ line
- **WHEN** an SPD rated to 802.3af is fitted on the 30 W horn line
- **THEN** the check names the line, the fitted device's class and the class the line needs

#### Scenario: A rod without arrestors is flagged
- **WHEN** a profile fits an air terminal and no SPD
- **THEN** the check reports that the structure is protected and the electronics are not

### Requirement: Earthing is measured, not assumed
The earth electrode's resistance SHALL be a recorded field measurement, not a catalogue figure. The profile SHALL carry `earthing.target_ohm` (10 Ω unless the site says otherwise) and `earthing.measured_ohm`, and the check SHALL report the measurement as outstanding until one is entered.

Where a steel pole is relied on as a natural down conductor, the profile SHALL record that its electrical continuity has been confirmed; an unconfirmed pole SHALL be reported as an open item.

#### Scenario: Earth resistance outstanding (U55)
- **WHEN** the budget profile is checked before installation
- **THEN** the earth resistance is reported as not yet measured, against a 10 Ω target, and the pole's continuity as not yet confirmed

