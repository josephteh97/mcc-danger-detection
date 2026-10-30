"""Quick checks: product catalogue and how each spec changes the simulation (V23-V28, U09)."""
import os
import statistics
import tempfile

import yaml
from _check import check, main

import catalog
from catalog import effects as fx
from devices.power_model import PowerConfig
from world import weather as wx
from world.world import World

SITE = catalog.load_site(profile="phase1")
REF = tuple(SITE["reference_worker"]["xy"])


def contrast(site, preset, frames=5):
    w = World(site, weather=preset)
    wk = w.scene.add_controlled(REF)
    vals = []
    for _ in range(frames):
        w.step(1 / 15)
        f, info = w.render(measure=True)
        vals.append(w.contrast(info, f, wk.id))
    return statistics.median(vals)


@check("U09", "Every catalogue file validates")
def u09():
    found = catalog.validate_all()                        # raises on the first bad file
    n = sum(len(v) for v in found.values())
    phase1 = catalog.load_site(profile="phase1")
    v11 = catalog.load_site(profile="v11")
    unpowered = {"laser", "battery", "solar", "mast", "power_conv"}
    no_watts = [p["id"] for c, f in v11["fitted"].items() if c not in unpowered and c != "floodlight"
                for p in (f if isinstance(f, list) else [f]) if "watts_typ" not in p or "watts_max" not in p]
    ok = len(phase1["fitted"]) == 8 and set(v11["fitted"]) == set(catalog.CATEGORIES) and not no_watts
    return ok, (f"{n} product files in {len(found)} categories; phase1 fits {len(phase1['fitted'])} categories, "
                f"v11 fits {len(catalog.fitted_products(v11))} products in {len(v11['fitted'])}"
                + (f"; no watts_typ/watts_max: {', '.join(no_watts)}" if no_watts else "")), \
        "every file passes its schema, phase1 fits one product per base category, v11 fits every category with watts on its powered products"


@check("V23", "Product file checks")
def v23():
    with open(os.path.join(catalog.CATALOG_DIR, "camera", "bullet_8mp_4mm_generic.yaml")) as f:
        data = yaml.safe_load(f)
    del data["hfov_deg"]
    path = os.path.join(tempfile.mkdtemp(), "my_new_camera.yaml")
    with open(path, "w") as f:
        yaml.safe_dump(data, f)
    try:
        catalog.validate("camera", data, path)
        return False, "file without hfov_deg was accepted", "refused, naming the field"
    except catalog.CatalogError as e:
        msg = str(e)
        return "hfov_deg" in msg and "my_new_camera.yaml" in msg, f"refused: {msg}", "a file missing a required field is refused, naming the field"


@check("V24", "Dome vs bullet")
def v24():
    downpour = wx.get_preset("tropical_downpour")
    bullet, dome = (catalog.load_product("camera", n) for n in ("bullet_8mp_4mm_generic", "dome_4mp_2_8mm_generic"))
    drops = {}
    for cam in (bullet, dome):
        w = World(fx.with_product(SITE, "camera", cam["id"]), weather="tropical_downpour")
        mask = w._cached(("drops", downpour.name, cam["id"]), lambda: wx.make_drop_mask(
            w.H, w.W, wx.drop_coverage(downpour, cam), __import__("numpy").random.default_rng(w.seed + 2)))
        drops[cam["id"]] = 100.0 * float((mask > 0.5).mean())
    ppm_b = fx.pixels_per_metre(fx.with_product(SITE, "camera", bullet["id"]))[0]
    ppm_d = fx.pixels_per_metre(fx.with_product(SITE, "camera", dome["id"]))[0]
    db, dd = drops[bullet["id"]], drops[dome["id"]]
    ok = dd > db and ppm_d < ppm_b
    return ok, f"window hidden by drops: dome {dd:.1f}% vs bullet {db:.1f}%; {ppm_d:.0f} vs {ppm_b:.0f} px/m (guide 2.5% vs 1.1%; 93 vs 175)", "dome shows more drops and fewer pixels per metre"


@check("V25", "WDR in low sun")
def v25():
    wdr = contrast(fx.with_product(SITE, "camera", "bullet_8mp_4mm_generic"), "low_sun_glare")
    no_wdr = contrast(fx.with_product(SITE, "camera", "bullet_4mp_hik_ds2cd1043g0i"), "low_sun_glare")
    return no_wdr < wdr, f"worker contrast in low sun: {no_wdr:.0f} without true WDR vs {wdr:.0f} with (guide 30 vs 46)", "camera without true WDR loses contrast"


@check("V26", "Floodlight specs")
def v26():
    narrow = fx.floodlight_lux(fx.with_product(SITE, "floodlight", "led_30w_24v_narrow"))
    wide = fx.floodlight_lux(fx.with_product(SITE, "floodlight", "led_30w_24v_wide"))
    mains = PowerConfig.from_site(fx.with_product(SITE, "floodlight", "vive_50w_230v_sensor")).inverter_wh_per_day()
    ok = narrow > wide and mains > 0
    return ok, f"narrow beam {narrow:.0f} lux vs wide {wide:.0f} lux on the worker; 230 V lamp adds {mains:.0f} Wh/day of inverter energy (guide 19 vs 2 lux; +538 Wh)", "narrow beam gives more lux; mains lamp costs inverter energy"


@check("V27", "Laser class check")
def v27():
    res = {n: fx.laser_summary(catalog.load_product("laser", n)) for n in catalog.list_products("laser")}
    flagged = sorted(n for n, r in res.items() if not r["class2_ok"])
    return flagged == ["green_520nm_4_9mw"], f"not Class 2: {flagged}; " + ", ".join(f"{n} Class {r['class']}" for n, r in res.items()), "the 4.9 mW module is flagged as not Class 2"


@check("V28", "Helmet-tag resolution")
def v28():
    ppm = {n: fx.pixels_per_metre(fx.with_product(SITE, "camera", n))[0] for n in catalog.list_products("camera")}
    best = max(ppm, key=ppm.get)
    return all(v < 250 for v in ppm.values()), f"best {ppm[best]:.0f} px/m ({best}): no catalogue camera reaches 250 px/m from the pole", "records that no camera reaches the 250 px/m identify level"


if __name__ == "__main__":
    main("smoke_catalog.py")
