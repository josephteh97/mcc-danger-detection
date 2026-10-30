"""PoE port map and budget for the v11 managed switch.

The switch reserves power per port by the device's PoE class and refuses a port whose
reservation no longer fits its budget (ports are powered in port order). Actual draw is the
device's worst-case watts plus cable loss, and the PoE++ splitter's loss for the AI box.

    python3 devices/poe_model.py                   # v11 site
    python3 devices/poe_model.py --budget 90
"""
from __future__ import annotations

import argparse
import os
import sys

CLASS_W = {0: 15.4, 1: 4.0, 2: 7.0, 3: 15.4, 4: 30.0, 5: 45.0, 6: 60.0, 7: 75.0, 8: 90.0}   # PSE allocation


def efficiencies(site):
    """Conversion efficiencies: the site's defaults, replaced by the fitted converters' own figures."""
    eff = dict((site.get("power") or {}).get("efficiency") or {})
    eff.setdefault("stepup", 0.94)
    eff.setdefault("cable", 0.97)
    eff.setdefault("splitter", 0.90)
    eff.setdefault("dc12", 0.92)
    convs = site["fitted"].get("power_conv") or []
    for p in convs if isinstance(convs, list) else [convs]:
        key = {"stepup": "stepup", "splitter": "splitter", "injector": "dc12"}.get(p.get("kind"))
        if key:
            eff[key] = p["efficiency"]
    return eff


def port_device(site, entry):
    """(name, product-like dict with watts) for a port map entry, or (None, None) for a spare."""
    dev = entry.get("device")
    if dev is None:
        return None, None
    if dev == "laser_controller":
        return dev, site["laser_controller"]
    prod = site["fitted"][dev]
    return prod["id"], prod


def port_table(site, include_legacy=None, extra=None):
    """One row per switch port: device, class, reserved W and draw at the switch (typical and worst).
    `extra` adds devices on spare ports: [{"port": 6, "category": "camera", "product": "<id>"}].
    Legacy products are skipped unless `include_legacy` (default: the site's identify setting)."""
    from catalog import load_product
    eff = efficiencies(site)
    include_legacy = site.get("identify_enabled", False) if include_legacy is None else include_legacy
    entries = {e["port"]: dict(e) for e in site["poe_ports"]}
    for x in extra or []:
        prod = load_product(x["category"], x["product"])
        entries[x["port"]] = {"port": x["port"], "device": x["category"], "_product": prod,
                              "poe_class": prod.get("poe_class", 4)}
    rows = []
    for port in sorted(entries):
        e = entries[port]
        name, prod = (e["_product"]["id"], e["_product"]) if "_product" in e else port_device(site, e)
        row = {"port": port, "device": name or "spare", "class": None, "reserved_w": 0.0, "draw_typ_w": 0.0,
               "draw_max_w": 0.0, "data_only": bool(e.get("data_only"))}
        if prod is None or e.get("data_only") or (prod.get("legacy") and not include_legacy):
            rows.append(row)
            continue
        loss = eff["cable"] * (eff["splitter"] if e.get("via") else 1.0)
        cls = int(e.get("poe_class", prod.get("poe_class", 0)))
        row.update({"class": cls, "reserved_w": CLASS_W[cls],
                    "draw_typ_w": prod["watts_typ"] / loss, "draw_max_w": prod["watts_max"] / loss})
        rows.append(row)
    return rows


def check(site, budget_w=None, include_legacy=None, extra=None):
    """Power ports in order against the budget. -> dict with reserved, draw, refused ports, ok."""
    budget = budget_w if budget_w is not None else site["fitted"]["switch"]["poe_budget_w"]
    rows = port_table(site, include_legacy, extra)
    left, refused = budget, []
    for r in rows:
        if r["reserved_w"] > left + 1e-9:
            refused.append(r)
        else:
            left -= r["reserved_w"]
    reserved = sum(r["reserved_w"] for r in rows)
    draw = sum(r["draw_max_w"] for r in rows)
    return {"ok": not refused and draw <= budget, "budget_w": budget, "reserved_w": reserved,
            "draw_w": draw, "draw_typ_w": sum(r["draw_typ_w"] for r in rows), "rows": rows,
            "refused": [f"port {r['port']} ({r['device']}, class {r['class']}, {r['reserved_w']:g} W)" for r in refused]}


def describe(result):
    lines = [f"port {r['port']}: {r['device']:38s} "
             + ("data only" if r["data_only"] else "spare" if r["class"] is None else
                f"class {r['class']}, reserves {r['reserved_w']:5.1f} W, draws {r['draw_typ_w']:5.1f}-{r['draw_max_w']:5.1f} W")
             for r in result["rows"]]
    lines.append(f"reserved {result['reserved_w']:.1f} W, draw up to {result['draw_w']:.1f} W, budget "
                 f"{result['budget_w']:.0f} W: " + ("OK" if result["ok"] else "REFUSED " + "; ".join(result["refused"])))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import catalog
    ap = argparse.ArgumentParser(description="PoE port map and budget for the v11 switch")
    ap.add_argument("--budget", type=float, help="switch PoE budget in W (default: the fitted switch's)")
    a = ap.parse_args()
    print(describe(check(catalog.load_site(profile="v11"), a.budget)))
