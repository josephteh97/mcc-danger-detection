# pole-network-power Specification

## Purpose
The v11 pole's network and power, modelled so the design numbers can be checked before purchase: the PoE port map and budget, stream bitrates and monthly 4G data, the 24 V bus with its conversion losses, power Plans A, B and C, the battery monitor and two-stage shutdown, the remote-management faults, and the laser's reach from the stand.
## Requirements
### Requirement: PoE port map and budget
`devices/poe_model.py` SHALL model the managed PoE switch from the fitted products: port 1 camera (PoE+ class 4), port 2 IP horn (class 4, worst case), port 3 4G router data only (the router has its own injector), port 4 AI box over PoE++ (802.3bt class 6) through a splitter, port 5 laser controller (class 0), ports 6–8 spare. It SHALL report actual draw and power reserved by class, and check both against the switch's PoE budget.

#### Scenario: v11 budget (U17)
- **WHEN** the v11 products are fitted to a 240 W switch
- **THEN** reserved power is 135.4 W, actual draw is 88 ± 5 W, and the check passes

#### Scenario: Undersized switch (U18)
- **WHEN** the switch budget is set to 90 W
- **THEN** the check fails on reserved power and names the ports that would be refused

### Requirement: Stream bitrates and 4G data
`tools/network.py` SHALL compute per-link load from these streams (typical/cap Mbit/s): camera main 8/16; camera sub 1/2 while watched; horn 0.1; laser and relay lines 0.05; events 0.03 average; live view to the cloud relay 1/2 per watched stream; maintenance over the VPN 1–4/8. It SHALL estimate monthly 4G data from events a day, clip size and viewing hours, and flag use above the SIM plan (default 30 GB).

#### Scenario: Baseline data (U19)
- **WHEN** there are 50 events a day with 1.3 MB clips and 1 hour of live viewing a day at 1 Mbit/s
- **THEN** the estimate is 15 ± 1 GB a month, within the plan, and every wired link is below 5% load

### Requirement: 24 V bus and conversion losses
The v11 power profile SHALL compute bus load from the fitted products' typical and worst watts and these efficiencies: 24→54 V step-up 94%, PoE cable 97%, PoE++ splitter 90%, 24→12 V 92%.

#### Scenario: AI box over PoE++ (U20)
- **WHEN** the AI box draws 25 W
- **THEN** the bus supplies 30.5 ± 0.5 W for it

#### Scenario: Continuous load (U21)
- **WHEN** the v11 pole runs with no alarms
- **THEN** the average bus load is between 65 and 75 W

### Requirement: Power plans
`devices/power_model.py --profile v11` SHALL support:
- Plan A (primary): shared site socket, 24 V 240 W supply, 50 Ah LiFePO4 backup with DC UPS, and a socket schedule (on, off at night, off at weekends)
- Plan B (backup): 4 × 250 W panels, MPPT controller, 200 Ah LiFePO4
- Plan C (backup): Plan B plus a 20 A charger fed by the socket schedule

#### Scenario: Plan B, three heavily overcast days (U22)
- **WHEN** Plan B runs 3 days at 30% of normal sun
- **THEN** the lowest charge stays above 10% and Stage 2 never triggers

### Requirement: Battery monitor and two-stage shutdown
The v11 power profile SHALL raise alerts at 50%, 30% and 10% state of charge; switch off the floodlight, strobe, servos and laser at 30% (back on at 40%); switch off the step-up converter, and with it the switch, AI box, camera, horn and laser controller, at 10% (back on at 20%); and keep the 4G router on until the battery's own cut-off.

#### Scenario: Plan A weekend switch-off (U23)
- **WHEN** Plan A's socket is off for 60 hours
- **THEN** Stage 1 and then Stage 2 trigger in order, the router stays on for at least 10 hours after Stage 2, and the run reports the hours without an alarm

### Requirement: Remote-management faults
The dashboard's fault table SHALL add, for the v11 profile:
- **Switch hang:** every `poe_lan` device loses its link; the 4G router stays up because it has its own injector.
- **Router-driven switch restart:** restores all `poe_lan` links within 60 s.
- **AI box hang:** the PoE watchdog power-cycles port 4 after 3 missed pings 10 s apart.
- **Site power cut:** the power profile switches to battery and follows the shutdown stages.

#### Scenario: AI box hang recovered by the watchdog (U25)
- **WHEN** `twin-orin-1` is paused in the v11 profile
- **THEN** the PoE watchdog restarts it within 40 s and the app returns to Monitoring within 60 s after that

#### Scenario: Switch hang and remote restart
- **WHEN** the switch-hang fault is injected and then the router-driven restart is pressed
- **THEN** the cloud keeps receiving router status during the hang, and the camera stream and arm link return after the restart

### Requirement: Laser reach on the stand
The v11 laser geometry SHALL put the pivot 1.1 m up directly below the camera, with hardware stops 5°–45° below horizontal, and a check SHALL confirm the beam can reach every point of the 1.5 m alarm zone.

#### Scenario: Reach covers the alarm zone (U26)
- **WHEN** the stand is 9.5 m south of the pit centre
- **THEN** the far corner of the 1.5 m alarm zone, 12.1 m from the pivot, is within the 5° stop's reach of 1.1 / tan 5° = 12.57 m

#### Scenario: Reach shortfall reported
- **WHEN** the stand is moved to 10 m from the pit centre
- **THEN** the far corner is 12.59 m away and the check fails, reporting a 0.02 m shortfall

