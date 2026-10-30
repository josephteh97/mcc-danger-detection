"""Solar and battery model for the pole.

Steps the battery's state of charge hour by hour. A run starts at 19:00 with the battery
full after a clear day; an N-day run covers N daylight periods of the given weather and the
nights around them, through to 07:00 after the last day. The result is the lowest charge,
0 meaning the battery runs flat. The pass floor for the validation checks is 10%.

    python3 devices/power_model.py --days 3 --sun 0.3
    python3 devices/power_model.py --days 3 --weather overcast
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, replace

FLOOR_PCT = 10.0
INVERTER_IDLE_W = 20.0      # a small 24 V -> 230 V inverter left on all day
INVERTER_EFF = 0.91


@dataclass
class PowerConfig:
    base_w: float = 33.0              # AI box, camera, switch, modem, idle devices: all day
    flood_w: float = 30.0             # floodlight, on from 19:00 to 07:00
    flood_hours: tuple = (19, 7)
    inverter: bool = False            # a 230 V floodlight needs an inverter
    battery_wh: float = 2560.0        # 25.6 V x 100 Ah
    panel_w: float = 500.0
    peak_sun_h: float = 4.0           # an average day
    system_eff: float = 0.70
    daylight: tuple = (7, 19)

    def flood_on(self, hour):
        a, b = self.flood_hours
        return (hour >= a or hour < b) if a > b else a <= hour < b

    def load_w(self, hour):
        w = self.base_w
        lamp = self.flood_w if self.flood_on(hour) else 0.0
        if self.inverter:
            w += INVERTER_IDLE_W + lamp / INVERTER_EFF
        else:
            w += lamp
        return w

    def daily_load_wh(self):
        return sum(self.load_w(h) for h in range(24))

    def inverter_wh_per_day(self):
        if not self.inverter:
            return 0.0
        lamp_wh = sum(self.flood_w for h in range(24) if self.flood_on(h))
        return INVERTER_IDLE_W * 24 + lamp_wh * (1 / INVERTER_EFF - 1)

    def solar_w(self, hour, sun_factor):
        a, b = self.daylight
        if not a <= hour < b:
            return 0.0
        weights = [math.sin(math.pi * (h + 0.5 - a) / (b - a)) for h in range(a, b)]
        daily_wh = self.panel_w * self.peak_sun_h * self.system_eff * sun_factor
        return daily_wh * weights[hour - a] / sum(weights)

    @classmethod
    def from_site(cls, site, **overrides):
        """Build from site.yaml's fitted products (catalog.load_site)."""
        f, p = site["fitted"], site.get("power", {})
        flood = f["floodlight"]
        cfg = cls(
            base_w=p.get("other_load_w", 11) + f["camera"]["power_w"] + f["ai_box"]["power_w"],
            flood_w=flood["power_w"],
            flood_hours=tuple(p.get("floodlight_hours", (19, 7))),
            inverter=flood["supply_v"] > 48,
            battery_wh=f["battery"]["voltage_v"] * f["battery"]["capacity_ah"],
            panel_w=f["solar"]["panel_w"],
            daylight=tuple(p.get("daylight_hours", (7, 19))),
        )
        return replace(cfg, **overrides)


def simulate(cfg, sun_factors):
    """Hourly state of charge (Wh) for one weather day per entry of sun_factors."""
    soc, trace = cfg.battery_wh, []
    hours = 24 * len(sun_factors) + 12
    for i in range(hours):
        hour = (19 + i) % 24
        day = (i + 19) // 24 - 1          # 0 for the first daylight period after the start
        sun = sun_factors[day] if 0 <= day < len(sun_factors) else 1.0
        soc = min(cfg.battery_wh, max(0.0, soc + cfg.solar_w(hour, sun) - cfg.load_w(hour)))
        trace.append(soc)
    return trace


def lowest_charge(cfg, sun_factor, days):
    """Lowest state of charge in percent over `days` days at `sun_factor` (0 = runs flat)."""
    return 100.0 * min(simulate(cfg, [sun_factor] * days)) / cfg.battery_wh


def describe(pct):
    return "runs flat" if pct <= 0.0 else f"{pct:.0f}%"


# --------------------------------------------------------------------------- v11 profile
# One 24 V bus. PoE devices are fed through the 24->54 V step-up and the switch (cable loss, and the
# PoE++ splitter for the AI box); the 4G router through its own injector (24->12 V). The battery
# monitor and relays sit on the bus. Stage 1 sheds the floodlight, strobe, servos and laser; Stage 2
# switches off the step-up and with it everything on PoE. The router stays on until the battery's
# own cut-off.

PLANS = ("A", "B", "C")
SOCKET_MODES = ("always", "night_off", "weekend_off")


def bus_watts(device_w, eff, via_splitter=False):
    """Watts the 24 V bus supplies for a PoE device drawing device_w."""
    loss = eff["cable"] * eff["stepup"] * (eff["splitter"] if via_splitter else 1.0)
    return device_w / loss


def v11_loads(site):
    """Typical bus watts per load, grouped by what sheds them. -> {name: (watts, group)}
    group: 'poe' (off at Stage 2), 'router', 'bus' (monitor and relays), 'flood' (night, Stage 1)."""
    from devices.poe_model import efficiencies
    eff, f = efficiencies(site), site["fitted"]
    out = {}
    for e in site["poe_ports"]:
        dev = e.get("device")
        if not dev or e.get("data_only"):
            continue
        prod = site["laser_controller"] if dev == "laser_controller" else f[dev]
        if prod.get("legacy"):
            continue
        out[dev] = (bus_watts(prod["watts_typ"], eff, bool(e.get("via"))), "poe")
    out["switch"] = (f["switch"]["watts_typ"] / eff["stepup"], "poe")
    out["router"] = (f["router"]["watts_typ"] / eff["dc12"], "router")
    for p in f.get("monitor") or []:
        out[p["id"]] = (p["watts_typ"], "bus")
    out["floodlight"] = (f["floodlight"]["power_w"], "flood")
    return out


@dataclass
class V11PowerConfig:
    plan: str = "B"
    loads: dict = None
    flood_hours: tuple = (19, 7)
    daylight: tuple = (7, 19)
    battery_wh: float = 5120.0
    panel_w: float = 0.0
    peak_sun_h: float = 4.0
    system_eff: float = 0.70
    psu_w: float = 0.0                  # Plan A: site socket through the 24 V supply
    charger_w: float = 0.0              # Plan C: 230 V charger
    charge_c: float = 0.2               # DC UPS charge limit (fraction of capacity per hour)
    socket_mode: str = "always"
    night_off: tuple = (22, 6)
    alerts_pct: tuple = (50, 30, 10)
    stage1: tuple = (30, 40)
    stage2: tuple = (10, 20)

    @classmethod
    def from_site(cls, site, plan="B", socket_mode=None, **overrides):
        from catalog import load_product
        p = site["power_plans"][plan]
        pw = site.get("power", {})
        bat = load_product("battery", p["battery"])
        cfg = cls(plan=plan, loads=v11_loads(site),
                  flood_hours=tuple(pw.get("floodlight_hours", (19, 7))),
                  daylight=tuple(pw.get("daylight_hours", (7, 19))),
                  battery_wh=bat["voltage_v"] * bat["capacity_ah"],
                  panel_w=load_product("solar", p["solar"])["panel_w"] if p.get("solar") else 0.0,
                  psu_w=next((load_product("power_conv", n)["rated_w"] for n in p.get("parts", [])
                              if load_product("power_conv", n)["kind"] == "psu"), 0.0),
                  charger_w=sum(load_product("power_conv", n)["rated_w"] * load_product("power_conv", n)["efficiency"]
                                for n in p.get("parts", []) if load_product("power_conv", n)["kind"] == "charger"),
                  socket_mode=socket_mode or ("always" if p.get("socket") else "always"),
                  night_off=tuple((pw.get("socket_schedule") or {}).get("night_off", (22, 6))),
                  alerts_pct=tuple(pw.get("monitor_alerts_pct", (50, 30, 10))),
                  stage1=((pw.get("stage1") or {}).get("off_pct", 30), (pw.get("stage1") or {}).get("on_pct", 40)),
                  stage2=((pw.get("stage2") or {}).get("off_pct", 10), (pw.get("stage2") or {}).get("on_pct", 20)))
        if not p.get("socket"):
            cfg.psu_w = cfg.charger_w = 0.0
        return replace(cfg, **overrides)

    def group_w(self, group):
        return sum(w for w, g in self.loads.values() if g == group)

    def average_load_w(self):
        """Average bus load with no alarms (floodlight on its hours)."""
        flood_h = sum(1 for h in range(24) if PowerConfig.flood_on(self, h))
        return sum(w for w, g in self.loads.values() if g != "flood") + self.group_w("flood") * flood_h / 24

    def solar_w(self, hour, sun_factor):
        return PowerConfig.solar_w(self, int(hour), sun_factor) if self.panel_w else 0.0

    def socket_on(self, t_h, hour, weekday, off_windows):
        if any(a <= t_h < b for a, b in off_windows):
            return False
        if self.socket_mode == "night_off":
            a, b = self.night_off
            return not ((hour >= a or hour < b) if a > b else a <= hour < b)
        if self.socket_mode == "weekend_off":
            return weekday < 5
        return True


def simulate_v11(cfg, sun_factors, socket_off=(), step_h=0.1, start_weekday=4, extra_h=12):
    """Step the v11 battery from 19:00 (full) through the daylight periods in sun_factors.
    socket_off: [(start_h, end_h)] windows (hours from the start) with the site socket off.
    -> dict: lowest charge %, trace, events [(hour, text)], hours without an alarm (Stage 2 or flat),
    router hours after Stage 2."""
    has_socket = cfg.psu_w > 0 or cfg.charger_w > 0
    soc, cap = cfg.battery_wh, cfg.battery_wh
    stage1 = stage2 = flat = False
    armed = {a: True for a in cfg.alerts_pct}
    events, trace, lowest = [], [], 100.0
    dark_h, router_after_s2, s2_since = 0.0, 0.0, None
    n = int(round((24 * len(sun_factors) + extra_h) / step_h))
    for i in range(n):
        t = i * step_h
        clock = 19 + t
        hour, day = int(clock) % 24, int((clock - 7) // 24)          # day 0 = first daylight period
        weekday = (start_weekday + int(clock // 24)) % 7
        sun = sun_factors[day] if 0 <= day < len(sun_factors) else 1.0
        socket = has_socket and cfg.socket_on(t, hour, weekday, socket_off)
        load = 0.0
        if not flat:
            load += cfg.group_w("bus") + cfg.group_w("router")
            if not stage2:
                load += cfg.group_w("poe")
                if not stage1 and PowerConfig.flood_on(cfg, hour):
                    load += cfg.group_w("flood")
        if socket and cfg.psu_w:                        # Plan A: the supply carries the load and charges
            net = min(cfg.psu_w - load, cfg.charge_c * cap)
        else:
            net = cfg.solar_w(hour, sun) + (cfg.charger_w if socket else 0.0) - load
        soc = min(cap, max(0.0, soc + net * step_h))
        pct = 100.0 * soc / cap
        lowest = min(lowest, pct)
        trace.append(pct)
        for a in cfg.alerts_pct:
            if armed[a] and pct < a:
                armed[a] = False
                events.append((round(t, 1), f"battery monitor alert: below {a}%"))
            elif not armed[a] and pct >= a + 5:
                armed[a] = True
        if not stage1 and pct < cfg.stage1[0]:
            stage1 = True
            events.append((round(t, 1), "Stage 1: floodlight, strobe, servos and laser off"))
        elif stage1 and pct >= cfg.stage1[1]:
            stage1 = False
            events.append((round(t, 1), "Stage 1 cleared"))
        if not stage2 and pct < cfg.stage2[0]:
            stage2, s2_since = True, t
            events.append((round(t, 1), "Stage 2: step-up off (switch, AI box, camera, horn, laser controller)"))
        elif stage2 and pct >= cfg.stage2[1]:
            stage2, s2_since = False, None
            events.append((round(t, 1), "Stage 2 cleared: pole back on"))
        if not flat and soc <= 0.0:
            flat = True
            events.append((round(t, 1), "battery cut-off: router off"))
        elif flat and soc > 0.0 and net > 0:
            flat = False
        if stage2 or flat:
            dark_h += step_h
        if stage2 and not flat:
            router_after_s2 += step_h
    return {"lowest_pct": lowest, "trace": trace, "events": events, "hours_without_alarm": dark_h,
            "router_hours_after_stage2": router_after_s2, "stage2": any("Stage 2:" in e for _, e in events)}


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap = argparse.ArgumentParser(description="Lowest battery charge over a run of days")
    ap.add_argument("--days", type=int, default=3)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sun", type=float, help="sun factor (1.0 = average day)")
    g.add_argument("--weather", help="weather preset name")
    ap.add_argument("--site", help="site file path")
    ap.add_argument("--profile", choices=("phase1", "v11"), default="phase1",
                    help="phase1 (the guide's pole, default) or v11 (hardware list version 11)")
    ap.add_argument("--plan", choices=PLANS, default="B", help="v11 power plan")
    ap.add_argument("--socket", choices=SOCKET_MODES, help="v11 site socket schedule (Plans A and C)")
    ap.add_argument("--socket-off", type=float, nargs=2, metavar=("FROM_H", "TO_H"), action="append",
                    default=[], help="v11: socket off between these hours from the start (repeatable)")
    a = ap.parse_args()
    import catalog
    sun = a.sun
    if a.weather:
        from world.weather import get_preset
        sun = get_preset(a.weather).sun_factor
    sun = 1.0 if sun is None else sun
    if a.profile == "v11":
        site = catalog.load_site(a.site, profile=None if a.site else "v11")
        cfg = V11PowerConfig.from_site(site, a.plan, a.socket)
        r = simulate_v11(cfg, [sun] * a.days, [tuple(w) for w in a.socket_off])
        print(f"v11 Plan {a.plan}: average load {cfg.average_load_w():.1f} W, battery {cfg.battery_wh:.0f} Wh, "
              f"panels {cfg.panel_w:.0f} W, sun factor {sun:.2f}, {a.days} days: lowest charge "
              f"{describe(r['lowest_pct'])}, {r['hours_without_alarm']:.1f} h without an alarm")
        for t, text in r["events"]:
            print(f"  +{t:5.1f} h  {text}")
        sys.exit(0)
    cfg = PowerConfig.from_site(catalog.load_site(a.site, profile=None if a.site else "phase1"))
    pct = lowest_charge(cfg, sun, a.days)
    print(f"load {cfg.daily_load_wh():.0f} Wh/day, battery {cfg.battery_wh:.0f} Wh, "
          f"panels {cfg.panel_w:.0f} W, sun factor {sun:.2f}, {a.days} days: lowest charge "
          f"{describe(pct)} ({'above' if pct > FLOOR_PCT else 'below'} the {FLOOR_PCT:.0f}% floor)")
