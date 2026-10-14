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


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap = argparse.ArgumentParser(description="Lowest battery charge over a run of days")
    ap.add_argument("--days", type=int, default=3)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sun", type=float, help="sun factor (1.0 = average day)")
    g.add_argument("--weather", help="weather preset name")
    ap.add_argument("--site", help="site.yaml path")
    a = ap.parse_args()
    import catalog
    cfg = PowerConfig.from_site(catalog.load_site(a.site))
    sun = a.sun
    if a.weather:
        from world.weather import get_preset
        sun = get_preset(a.weather).sun_factor
    sun = 1.0 if sun is None else sun
    pct = lowest_charge(cfg, sun, a.days)
    print(f"load {cfg.daily_load_wh():.0f} Wh/day, battery {cfg.battery_wh:.0f} Wh, "
          f"panels {cfg.panel_w:.0f} W, sun factor {sun:.2f}, {a.days} days: lowest charge "
          f"{describe(pct)} ({'above' if pct > FLOOR_PCT else 'below'} the {FLOOR_PCT:.0f}% floor)")
