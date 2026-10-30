"""Quick checks: weather presets, contrast, mast sway, battery per preset (V19-V22, U07, U08)."""
import math
import statistics

from _check import check, main

import catalog
from app.alarm import foot_pixel, ground_from_image
from devices.power_model import PowerConfig, lowest_charge
from world import weather as wx
from world.world import World

SITE = catalog.load_site(profile="phase1")
REF = tuple(SITE["reference_worker"]["xy"])
_contrast = {}

# The guide's 3-day battery table (percent; 0 = runs flat)
BATTERY_3D = {"clear": 70, "overcast": 8, "light_rain": 0, "tropical_downpour": 0, "thunderstorm": 0,
              "regional_haze": 33, "dust_or_smoke": 49, "morning_mist": 17, "dense_fog": 0, "humid_lens": 66,
              "night_clear": 70, "night_no_floodlight": 70, "night_rain": 70, "low_sun_glare": 70,
              "mud_splash": 70, "strong_wind": 49}


def contrast(preset, frames=6):
    """Median worker contrast at the reference position (grey levels)."""
    if preset not in _contrast:
        w = World(SITE, weather=preset)
        wk = w.scene.add_controlled(REF)
        vals = []
        for _ in range(frames):
            w.step(1 / 15)
            f, info = w.render(measure=True)
            vals.append(w.contrast(info, f, wk.id))
        _contrast[preset] = statistics.median(vals)
    return _contrast[preset]


def pct(preset):
    return 100.0 * contrast(preset) / contrast("clear")


@check("U07", "All 16 presets render")
def u07():
    problems = []
    for name in wx.NAMES:
        w = World(SITE, weather=name)
        w.step(1 / 15)
        f, _ = w.render()
        p = w.preset
        if f.shape != (720, 1280, 3) or not (0 <= p.sun_factor <= 1) or p.wind_ms < 0:
            problems.append(name)
    try:
        wx.get_preset("snow")
        rejected = False
    except ValueError as e:
        rejected = all(n in str(e) for n in wx.NAMES)
    ok = len(wx.NAMES) == 16 and not problems and rejected
    return ok, f"{len(wx.NAMES)} presets rendered at 1280x720 with sun, wind and events; 'snow' rejected with the valid list: {rejected}", "16 presets render; unknown names are rejected"


@check("V19", "Bad weather lowers visibility")
def v19():
    fog, rain = pct("dense_fog"), pct("tropical_downpour")
    return fog < 100 and rain < 100, f"dense fog {fog:.0f}%, downpour {rain:.0f}% of clear-day contrast (guide 19%, 27%)", "fog and downpour lower than clear"


@check("V20", "Haze at site range")
def v20():
    haze = pct("regional_haze")
    return haze > 60, f"regional haze keeps {haze:.0f}% of clear contrast (guide 67%)", "more than 60% of clear contrast"


@check("V21", "Mast sway")
def v21():
    def foot_estimates(preset):
        w = World(SITE, weather=preset)
        wk = w.scene.add_controlled((0.6, -1.6))
        H, est = w.homography(), []
        for _ in range(60):                       # 4 s covers the sway and gust cycles
            w.step(1 / 15)
            _, info = w.render()
            est.append(ground_from_image(H, *foot_pixel(info["boxes"][wk.id])))
        return est
    calm, windy = foot_estimates("clear"), foot_estimates("strong_wind")
    moves = [math.dist(a, b) for a, b in zip(calm, windy)]
    worst = max(moves)
    return (worst < 0.15, f"15 m/s gusts move the foot estimate by up to {worst:.2f} m (mean {statistics.mean(moves):.2f} m; guide about 0.08 m)",
            "under 0.15 m added to the foot error")


@check("V22", "Floodlight at night")
def v22():
    on, off = pct("night_clear"), pct("night_no_floodlight")
    return on >= 2 * off, f"{on:.0f}% with the floodlight vs {off:.0f}% without (guide 69% vs 12%)", "with at least twice without"


@check("U08", "Battery after 3 days of each preset")
def u08():
    cfg, bad, parts = PowerConfig.from_site(SITE), [], []
    for name in wx.NAMES:
        got = lowest_charge(cfg, wx.get_preset(name).sun_factor, 3)
        want = BATTERY_3D[name]
        ok = got <= 0 if want == 0 else abs(got - want) <= 2
        parts.append(f"{name} {'flat' if got <= 0 else f'{got:.0f}%'}")
        if not ok:
            bad.append(name)
    return not bad, ("all 16 match the guide's table" if not bad else f"mismatch: {', '.join(bad)}") + f" ({'; '.join(parts[:6])}; ...)", "each within 2 points of the guide (or runs flat)"


if __name__ == "__main__":
    main("smoke_weather.py")
