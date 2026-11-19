"""Quick checks for hardware list version 65, the budget pole: the bill-of-materials bijection and
cost, PoE port count and input window, the 4G uplink, the 48 V bus and its hardware cutoff, and the
unfitted categories (U27-U36, U56). They load the budget profile whatever site.yaml selects.
U37-U55 and U57 are added with the coverage, dashboard and contingency work."""
from _check import check, main, near

import catalog
from tools import coverage as cov

SITE = catalog.load_site(profile="budget")
BOM = catalog.load_bom(65)


# --------------------------------------------------------------------------- bill of materials (U27, U28)

@check("U27", "Version 65 maps one-to-one")
def u27():
    r = catalog.reconcile(SITE, BOM)
    n = len(catalog.bom_mapping(SITE))
    ok = not r["unmodelled"] and not r["unknown"] and n == len(BOM["items"])
    return ok, (f"{n} of {len(BOM['items'])} lines claimed once; unmodelled "
                f"{r['unmodelled'] or 'none'}, unknown {r['unknown'] or 'none'}"), \
        "every version 65 line item is claimed exactly once and no fitted product invents a line"


@check("U28", "Cost reconciles to S$3,941.94")
def u28():
    r = catalog.reconcile(SITE, BOM)
    ok = r["ok"] and near(r["fitted_total_sgd"], 3941.94, 0.005) and near(r["table_gap_sgd"], 242.51, 0.005)
    return ok, (f"catalogue S${r['fitted_total_sgd']:.2f} vs item rows S${r['listed_total_sgd']:.2f} "
                f"(diff {r['total_diff_sgd']:.2f}); printed table S${r['table_total_sgd']:.2f} "
                f"stale by S${r['table_gap_sgd']:.2f}"), \
        "reconciles to S$3,941.94 with every per-line difference zero; the stale S$242.51 table gap is reported"


# --------------------------------------------------------------------------- PoE (U29, U30, U56)

@check("U29", "Four devices on eight ports")
def u29():
    from devices.poe_model import port_count, check as poe_check
    pc = port_count(SITE)
    r = poe_check(SITE)
    ok = pc["ok"] and pc["devices"] == 4 and pc["spare"] == 4 and r["ok"]
    return ok, f"{pc['devices']} PoE devices on {pc['switch_ports']} ports, {pc['spare']} spare; power OK={r['ok']}", \
        "four fitted PoE devices on the eight-port switch, four ports spare, within the power budget"


@check("U30", "A ninth PoE device fails as expected")
def u30():
    from devices.poe_model import port_count
    pc = port_count(SITE, extra=[{"port": 9}])
    return not pc["ok"] and pc["over"] == [9], \
        f"a ninth device: over {pc['over']}, {'; '.join(pc['findings'])}", \
        "a device beyond the switch's eight ports is refused and named"


@check("U56", "Switch input window against the pack swing")
def u56():
    from devices.poe_model import input_window
    iw = input_window(SITE)
    ok = iw["ok"] and iw["cutoff_v_per_cell"] >= 3.0 - 1e-9 and iw["absorption_v_per_cell"] <= 3.5 + 1e-9
    return ok, (f"{iw['cells']} cells: cutoff {iw['cutoff_v']} V ({iw['cutoff_v_per_cell']} V/cell), "
                f"absorption {iw['absorption_v']} V ({iw['absorption_v_per_cell']} V/cell)"), \
        "cutoff >= 48 V and absorption <= 3.50 V/cell keep the bus inside the switch's 48-56 V input window"


# --------------------------------------------------------------------------- 4G uplink (U31, U36)

@check("U31", "4G data over the USB modem")
def u31():
    from tools.network import report
    r = report(SITE, events_per_day=50, clip_mb=1.3, view_hours_per_day=1.0, view_mbps=1.0)
    up = r["uplink"]
    ok = up["device"] == "modem" and near(r["data"]["total_gb"], 15.5, 1.0) and r["within_plan"]
    return ok, f"uplink {up['device']} ({up['id']}); {r['data']['total_gb']:.1f} GB of {r['plan_gb']:.0f} GB plan", \
        "the 4G uplink is the USB modem and the monthly data fits the SIM plan"


@check("U36", "VPN node on the AI box is a single point of failure")
def u36():
    from tools.network import uplink
    up = uplink(SITE)
    return up["spof"] and up["carries_vpn_node"], f"uplink {up['device']}: single point of failure ({up['why']})", \
        "the modem carries the VPN node on the AI box, flagged as a single point of failure"


# --------------------------------------------------------------------------- 48 V bus and cutoff (U32-U35)

@check("U32", "48 V bus continuous load")
def u32():
    from devices.power_model import BudgetPowerConfig
    cfg = BudgetPowerConfig.from_site(SITE)
    ok = 25 <= cfg.base_w <= 40 and cfg.battery_wh == 2560 and cfg.panel_w == 400
    return ok, f"continuous load {cfg.base_w:.1f} W on a {cfg.battery_wh:.0f} Wh pack, {cfg.panel_w:.0f} W of panels", \
        "a continuous bus load between 25 and 40 W on the 2.56 kWh pack and the 400 W array"


@check("U33", "Solar-only overcast days")
def u33():
    from devices.power_model import BudgetPowerConfig, simulate_budget, describe
    r = simulate_budget(BudgetPowerConfig.from_site(SITE), [0.3] * 3)
    ok = r["lowest_pct"] > 10 and r["cutoff_events"] == 0
    return ok, f"lowest charge {describe(r['lowest_pct'])}, cutoff {'fired' if r['cutoff_events'] else 'never'}", \
        "three overcast days stay above 10% on solar alone and the hardware cutoff never fires"


@check("U34", "Hardware cutoff is one event")
def u34():
    from devices.power_model import BudgetPowerConfig, simulate_budget
    r = simulate_budget(BudgetPowerConfig.from_site(SITE), [0.05] * 5)
    cutoffs = [e for _, e in r["events"] if "cutoff" in e]
    return len(cutoffs) == 1, f"deep depletion: {len(cutoffs)} cutoff event(s)", \
        "the hardware cutoff opens the bus in a single step, not the two-stage v11 shutdown"


@check("U35", "No battery monitor fitted")
def u35():
    mon = catalog.fitted(SITE, "monitor")
    return mon == [], f"battery monitor fitted: {[p['id'] for p in mon] or 'none'}", \
        "the budget pole fits no battery-monitor module, reported not assumed"


if __name__ == "__main__":
    main("smoke_budget.py")
