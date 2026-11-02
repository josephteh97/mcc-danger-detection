"""The dashboard's v11 what-if panel and HUD numbers (dashboard/v11.py), without the stack."""
import os

import pytest
import yaml

import catalog
from dashboard import v11
from tools import coverage
from world.world import World

NAMES = {"PoE budget", "Warning ring density", "Stand pose", "Laser reach", "4G data",
         "Plan A battery", "Plan B battery", "Plan C battery"}


def checks(r):
    return {c["name"]: c["ok"] for c in r["checks"]}


def test_fields_cover_products_and_settings():
    f = v11.fields()
    ids = {p["id"] for p in f["products"]}
    assert {"bullet_12mp_hik_ids2cd7ac6g2_izhsy", "lifepo4_24v_200ah", "panels_4x250w", "psu_24v_240w",
            "charger_24v_20a_230v", "managed_poe_8p_240w_48v"} <= ids
    assert {"stand_distance_m", "camera_height_m", "switch_budget_w", "events_per_day"} <= set(f["site"])


def test_catalogue_values_pass_everything():
    r = v11.whatif()
    assert set(checks(r)) == NAMES and all(checks(r).values()), r["checks"]
    assert r["poe"]["reserved_w"] == 135.4 and r["costs_sgd"]["A"] < r["costs_sgd"]["B"] < r["costs_sgd"]["C"]


def test_keyed_in_values_change_the_results():
    r = v11.whatif({"lifepo4_24v_200ah": {"capacity_ah": 100}, "managed_poe_8p_240w_48v": {"poe_budget_w": 90},
                    "bullet_12mp_hik_ids2cd7ac6g2_izhsy": {"price_sgd": 1000}},
                   {"stand_distance_m": 10, "events_per_day": 400})
    c = checks(r)
    assert not c["PoE budget"] and not c["Laser reach"] and not c["Plan B battery"] and c["Plan A battery"]
    assert r["laser"]["shortfall_m"] == 0.02
    base = v11.whatif()
    assert round(base["costs_sgd"]["A"] - r["costs_sgd"]["A"], 2) == 586.18
    assert r["network"]["total_gb"] > base["network"]["total_gb"]


def test_what_if_leaves_the_catalogue_alone():
    v11.whatif({"lifepo4_24v_50ah": {"capacity_ah": 999}})
    assert catalog.load_product("battery", "lifepo4_24v_50ah")["capacity_ah"] == 50


def test_bad_values_are_refused():
    import pytest
    with pytest.raises((catalog.CatalogError, ValueError)):
        v11.whatif({"lifepo4_24v_50ah": {"capacity_ah": "lots"}})


def test_hud_and_heatmap():
    site = catalog.load_site(profile="v11")
    h = v11.hud_static(site)
    assert h["poe"]["reserved_w"] == 135.4 and h["data"]["plan_gb"] == 30
    c = v11.coverage(site, step=1.0)
    assert c["nx"] * c["ny"] == sum(len(row) for row in c["ppm"])
    assert {p["band"] for p in c["corners"]} == {"green"}         # every ring corner >= 100 px/m with tiles


def test_bad_plan_product_fails_only_the_power_callers(tmp_path):
    """A misspelt product in a power plan stops the plan maths, not the world or the coverage."""
    with open(os.path.join(catalog.SITES_DIR, "v11.yaml")) as f:
        site = yaml.safe_load(f)
    site["power_plans"]["B"]["battery"] = "lifepo4_24v_999ah"
    path = tmp_path / "v11.yaml"
    path.write_text(yaml.safe_dump(site))
    loaded = catalog.load_site(path=str(path))
    assert coverage.report(loaded) and World(loaded).render()[0].shape == (1200, 1600, 3)
    with pytest.raises(catalog.CatalogError, match="lifepo4_24v_999ah"):
        catalog.plan_products(loaded)
