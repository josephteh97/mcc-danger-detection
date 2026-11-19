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
    from catalog import fitted
    eff = {"stepup": 0.94, "cable": 0.97, "splitter": 0.90, "dc12": 0.92,
           **((site.get("power") or {}).get("efficiency") or {})}
    for p in fitted(site, "power_conv"):
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
        from catalog import fitted
        aim = next((c for c in fitted(site, "controller") if c.get("interface") in ("ethernet", "usb")), None)
        if aim is None:
            raise ValueError("port map names laser_controller but no networked controller is fitted")
        return dev, aim
    prod = site["fitted"][dev]
    return prod["id"], prod


def port_table(site, include_legacy=None, extra=None):
    """One row per switch port: device, class, reserved W and draw at the switch (typical and worst).
    `extra` adds devices on spare ports: [{"port": 6, "category": "camera", "product": "<id>"}].
    Legacy products are skipped unless `include_legacy` (default: the site's identify setting)."""
    from catalog import load_product
    eff = efficiencies(site)
    include_legacy = site.get("identify_enabled", False) if include_legacy is None else include_legacy
    ports = {e["port"]: (e, *port_device(site, e)) for e in site["poe_ports"]}
    for x in extra or []:
        prod = load_product(x["category"], x["product"])
        ports[x["port"]] = ({"poe_class": prod.get("poe_class", 4)}, prod["id"], prod)
    rows = []
    for port in sorted(ports):
        e, name, prod = ports[port]
        row = {"port": port, "device": name or "spare", "role": e.get("device"), "class": None, "reserved_w": 0.0, "draw_typ_w": 0.0,
               "draw_max_w": 0.0, "data_only": bool(e.get("data_only"))}
        if prod is None or e.get("data_only") or (prod.get("legacy") and not include_legacy):
            rows.append(row)
            continue
        loss = eff["cable"] * (eff["splitter"] if e.get("via") else 1.0)
        cls = int(e.get("poe_class", prod.get("poe_class", 0)))
        if cls not in CLASS_W:
            raise ValueError(f"port {port} ({name}): PoE class {cls} is not one of 0-8")
        typ = prod.get("watts_typ", prod.get("power_w"))
        if typ is None:
            raise ValueError(f"port {port} ({name}): the product gives no watts_typ or power_w")
        row.update({"class": cls, "reserved_w": CLASS_W[cls],
                    "draw_typ_w": typ / loss, "draw_max_w": prod.get("watts_max", typ) / loss})
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


CELL_NOMINAL_V = 3.2        # LiFePO4 nominal cell voltage


def pack_cells(site):
    """The fitted battery's series cell count, from its nominal voltage."""
    return round(site["fitted"]["battery"]["voltage_v"] / CELL_NOMINAL_V)


def cutoff_voltage(site):
    """The bus cutoff voltage: the fitted power_conv with kind 'cutoff' (its output_v) is the source of
    truth; `power.cutoff_v` is an optional override. None if neither is present."""
    from catalog import fitted
    dev = next((p for p in fitted(site, "power_conv") if p.get("kind") == "cutoff"), None)
    return site.get("power", {}).get("cutoff_v", dev["output_v"] if dev else None)


def port_count(site, extra=None):
    """Fitted PoE devices against the switch's physical port count. -> the spare-port count, and any
    device mapped to a port the switch does not have. Zero spare is a finding; an overflow fails."""
    ports = int(site["fitted"]["switch"]["ports"])
    used = sorted([e["port"] for e in site["poe_ports"] if e.get("device") is not None]
                  + [x["port"] for x in extra or []])
    over = [p for p in used if p > ports]
    spare = ports - len(used)
    findings = (["no spare ports"] if spare == 0 and not over else [])
    if over:
        findings.append(f"{len(over)} device(s) on ports the {ports}-port switch does not have: {over}")
    return {"switch_ports": ports, "devices": len(used), "device_ports": used,
            "spare": spare, "over": over, "ok": not over, "findings": findings}


def input_window(site):
    """The fitted pack's configured operating range (cutoff to absorption) against the input window of
    every bus-powered product that states one. -> the per-cell settings and whether the bus stays
    inside each product's window. The budget pole wants cutoff >= 48 V and absorption <= 3.50 V/cell."""
    from catalog import fitted_products
    cells = pack_cells(site)
    cutoff_v, absorption_v = cutoff_voltage(site), site.get("power", {}).get("absorption_v")
    windows = []
    for p in fitted_products(site):
        lo, hi = p.get("input_v_min"), p.get("input_v_max")
        if lo is None or hi is None:
            continue
        inside = (cutoff_v is None or cutoff_v >= lo) and (absorption_v is None or absorption_v <= hi)
        windows.append({"product": p["id"], "input_v_min": lo, "input_v_max": hi, "inside": inside})
    return {"cells": cells, "cutoff_v": cutoff_v, "absorption_v": absorption_v,
            "cutoff_v_per_cell": None if cutoff_v is None else round(cutoff_v / cells, 3),
            "absorption_v_per_cell": None if absorption_v is None else round(absorption_v / cells, 3),
            "windows": windows, "ok": all(w["inside"] for w in windows)}


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
