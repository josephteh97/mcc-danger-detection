"""Compare products in one catalogue category side by side, everything else as in site.yaml.

    python3 -m tools.compare camera bullet_8mp_4mm_generic my_new_camera \
        --weather clear,tropical_downpour,night_clear,low_sun_glare

Prints the table and saves a picture grid (one row per weather, one column per product).
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import catalog                                         # noqa: E402
from catalog import effects as fx                      # noqa: E402
from devices.power_model import PowerConfig, describe, lowest_charge   # noqa: E402
from world import weather as wx                        # noqa: E402
from world.world import World                          # noqa: E402

GRID_CATEGORIES = {"camera", "floodlight", "laser", "mast"}
THUMB = (480, 270)


def _contrast(site, preset, frames=4):
    w = World(site, weather=preset)
    wk = w.scene.add_controlled(tuple(site["reference_worker"]["xy"]))
    vals = []
    for _ in range(frames):
        w.step(1 / 15)
        f, info = w.render(measure=True)
        vals.append(w.contrast(info, f, wk.id))
    return statistics.median(vals)


def _render(site, preset, laser_on):
    w = World(site, weather=preset)
    ref = site["reference_worker"]["xy"]
    w.scene.add_controlled(tuple(ref))
    if laser_on:
        from app.links import aim_angles
        a = site["arm"]
        w.arm = (*aim_angles(a["xy"], a["heading_deg"], a["pivot_h_m"], ref), True)
    w.step(1 / 15)
    return w.render()[0]


def measures(category, site, weathers):
    """[(label, value)] for one product fitted to the site."""
    f, rows = site["fitted"], []
    energy = PowerConfig.from_site(site).daily_load_wh()
    if category == "camera":
        ppm, d = fx.pixels_per_metre(site)
        rows += [("Pixels per metre on the worker", f"{ppm:.0f} ({fx.dori_level(ppm)})"),
                 ("3 m ring inside the picture", f"{fx.ring_coverage(site):.0%}"),
                 ("Window hidden by drops, downpour", f"{fx.window_drops_pct(f['camera'], wx.get_preset('tropical_downpour')):.1f}%")]
        rows += [(f"Worker contrast, {w}", f"{_contrast(site, w):.0f}") for w in weathers]
    elif category == "floodlight":
        rows += [("Lux on the worker", f"{fx.floodlight_lux(site):.1f}"),
                 ("Worker contrast, night_clear", f"{_contrast(site, 'night_clear'):.0f}"),
                 ("Inverter energy", f"{PowerConfig.from_site(site).inverter_wh_per_day():.0f} Wh/day")]
    elif category == "speaker":
        rows += [("Sound level at 1 m", f"{f['speaker']['spl_1m_db']:.0f} dB")]
        rows += [(f"Margin over noise, {w}", f"{fx.speaker_margin_db(site, f['speaker'], wx.get_preset(w)):+.0f} dB")
                 for w in weathers]
    elif category == "laser":
        s = fx.laser_summary(f["laser"])
        rows += [("Power, wavelength", f"{f['laser']['power_mw']} mW, {f['laser']['wavelength_nm']:.0f} nm"),
                 ("Laser class", s["class"] + ("" if s["class2_ok"] else "  NOT CLASS 2: may not be fitted")),
                 ("Dot brightness vs fitted green", f"{s['brightness']:.2f}x")]
    elif category == "ai_box":
        fps = f["ai_box"]["detector_fps"]
        rows += [("Detector frame rate", f"{fps:.0f} fps"),
                 ("Added alarm latency (one frame)", f"{1000 / fps:.0f} ms")]
    elif category == "mast":
        ppm, d = fx.pixels_per_metre(site)
        sway = f["mast"]["sway_deg_per_ms2"] * 15 ** 2
        rows += [("Camera height", f"{f['mast']['height_m']} m"), ("Distance to the worker", f"{d:.1f} m"),
                 ("Pixels per metre on the worker", f"{ppm:.0f} ({fx.dori_level(ppm)})"),
                 ("3 m ring inside the picture", f"{fx.ring_coverage(site):.0%}"),
                 ("Sway in 15 m/s gusts", f"{sway:.2f} deg")]
    if category in ("battery", "solar", "floodlight", "camera", "ai_box"):
        cfg = PowerConfig.from_site(site)
        for w in weathers if category in ("battery", "solar") else ["clear"]:
            rows.append((f"Battery low point, 3 days {w}", describe(lowest_charge(cfg, wx.get_preset(w).sun_factor, 3))))
    rows += [("Daily energy for the pole", f"{energy:,.0f} Wh"),
             ("Pole hardware cost", f"S${fx.pole_cost_sgd(site):,.0f}"),
             ("Verified against datasheet", "yes" if f[category]["verified"] else "no")]
    return rows


def compare(category, products, weathers, grid=True):
    """Returns {"columns", "rows", "grid"}: the table as lists and the picture grid (BGR) or None."""
    base = catalog.load_site()
    for w in weathers:
        wx.get_preset(w)
    sites = [fx.with_product(base, category, p) for p in products]
    per = [dict(measures(category, s, weathers)) for s in sites]
    labels = list(per[0])
    table = {"columns": ["Measure"] + products, "rows": [[lab] + [p.get(lab, "") for p in per] for lab in labels]}
    image = None
    if grid and category in GRID_CATEGORIES:
        cells = []
        for w in weathers:
            row = []
            for p, s in zip(products, sites):
                thumb = cv2.resize(_render(s, w, category == "laser"), THUMB, interpolation=cv2.INTER_AREA)
                cv2.rectangle(thumb, (0, 0), (THUMB[0], 24), (0, 0, 0), -1)
                cv2.putText(thumb, f"{p} | {w}", (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                row.append(thumb)
            cells.append(np.hstack(row))
        image = np.vstack(cells)
    return {**table, "grid": image}


def format_table(result):
    cols, rows = result["columns"], result["rows"]
    widths = [max(len(str(r[i])) for r in [cols] + rows) for i in range(len(cols))]
    line = lambda r: "  ".join(str(v).ljust(w) for v, w in zip(r, widths))   # noqa: E731
    return "\n".join([line(cols), line(["-" * w for w in widths])] + [line(r) for r in rows])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare catalogue products side by side")
    ap.add_argument("category", choices=catalog.CATEGORIES)
    ap.add_argument("products", nargs="+")
    ap.add_argument("--weather", default="clear", help="comma-separated presets")
    ap.add_argument("--out", help="picture grid path (default logs/compare-<category>-<time>.jpg)")
    a = ap.parse_args(argv)
    weathers = [w.strip() for w in a.weather.split(",") if w.strip()]
    try:
        result = compare(a.category, a.products, weathers)
    except (catalog.CatalogError, ValueError) as e:
        raise SystemExit(f"error: {e}")
    print(format_table(result))
    if result["grid"] is not None:
        out = a.out or os.path.join(ROOT, "logs", time.strftime(f"compare-{a.category}-%Y%m%d-%H%M%S.jpg"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cv2.imwrite(out, result["grid"], [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(f"picture grid saved to {os.path.relpath(out, os.getcwd())}")


if __name__ == "__main__":
    main()
