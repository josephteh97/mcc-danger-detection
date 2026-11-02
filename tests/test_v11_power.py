"""Edge cases of the v11 PoE and power models (devices/poe_model.py, devices/power_model.py)."""
import copy

import pytest

import catalog
from devices import poe_model
from devices.power_model import V11PowerConfig, v11_loads

SITE = catalog.load_site(profile="v11")


def test_router_on_a_powered_port_is_counted_once():
    site = copy.deepcopy(SITE)
    site["fitted"]["router"]["poe_class"] = 3
    for e in site["poe_ports"]:
        if e.get("device") == "router":
            e.pop("data_only")
    loads = v11_loads(site)
    assert "router" not in loads and loads[site["fitted"]["router"]["id"]][1] == "poe"
    assert "router" in v11_loads(SITE)                 # on its own injector, as fitted


def test_product_without_worst_case_watts_uses_typical():
    site = copy.deepcopy(SITE)
    del site["fitted"]["speaker"]["watts_max"]
    row = next(r for r in poe_model.port_table(site) if r["role"] == "speaker")
    assert row["draw_max_w"] == row["draw_typ_w"] > 0


def test_unknown_poe_class_is_refused_by_port():
    site = copy.deepcopy(SITE)
    site["poe_ports"][0]["poe_class"] = 9
    with pytest.raises(ValueError, match="port 1 .* PoE class 9"):
        poe_model.port_table(site)


def test_fractional_daylight_hours():
    cfg = V11PowerConfig.from_site(SITE, "B")
    half = V11PowerConfig.from_site(SITE, "B", daylight=(6.5, 18.5))
    assert half.solar_w(6, 1.0) == 0 and half.solar_w(12, 1.0) > 0
    assert sum(half.solar_w(h, 1.0) for h in range(24)) == pytest.approx(sum(cfg.solar_w(h, 1.0) for h in range(24)))
    assert V11PowerConfig.from_site(SITE, "A").solar_w(12, 1.0) == 0          # Plan A has no panels
