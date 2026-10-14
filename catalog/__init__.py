"""Product catalogue: one folder per hardware category, one YAML file per product.

Each folder's _schema.yaml lists the fields the simulator reads. A product file missing a
field, or with a field of the wrong type, is refused with the file and field named.
"""
from __future__ import annotations

import os

import yaml

CATALOG_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CATALOG_DIR)
CATEGORIES = ["camera", "floodlight", "speaker", "laser", "ai_box", "battery", "solar", "mast"]

_TYPES = {"str": str, "bool": bool, "number": (int, float), "list": list}


class CatalogError(ValueError):
    pass


def load_schema(category):
    path = os.path.join(CATALOG_DIR, category, "_schema.yaml")
    if not os.path.exists(path):
        raise CatalogError(f"unknown catalogue category '{category}' (expected one of {', '.join(CATEGORIES)})")
    with open(path) as f:
        return yaml.safe_load(f)


def validate(category, data, path="<product>"):
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: not a YAML mapping")
    for field, spec in load_schema(category)["fields"].items():
        if field not in data:
            raise CatalogError(f"{path}: missing required field '{field}' ({spec.get('doc', '')})")
        want = _TYPES[spec["type"]]
        value = data[field]
        if isinstance(value, bool) and spec["type"] == "number" or not isinstance(value, want):
            raise CatalogError(f"{path}: field '{field}' should be {spec['type']}, got {value!r}")
    return data


def list_products(category):
    folder = os.path.join(CATALOG_DIR, category)
    return sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".yaml") and not f.startswith("_"))


def load_product(category, name):
    path = os.path.join(CATALOG_DIR, category, f"{name}.yaml")
    if not os.path.exists(path):
        raise CatalogError(f"no product '{name}' in catalog/{category} "
                           f"(available: {', '.join(list_products(category))})")
    with open(path) as f:
        data = yaml.safe_load(f)
    product = dict(validate(category, data, os.path.relpath(path, ROOT_DIR)))
    product["id"] = name
    return product


# --------------------------------------------------------------------------- laser class

def laser_class(power_mw, wavelength_nm):
    """Simplified IEC 60825-1 class for a visible continuous-wave dot laser."""
    if not 400 <= wavelength_nm <= 700:
        return "not visible: check the standard"
    if power_mw <= 0.39:
        return "1"
    if power_mw <= 1.0:
        return "2"
    if power_mw <= 5.0:
        return "3R"
    return "3B"


def check_laser_fit(product):
    cls = laser_class(product["power_mw"], product["wavelength_nm"])
    if cls not in ("1", "2"):
        raise CatalogError(f"laser '{product['id']}' is Class {cls}, not Class 2: "
                           f"it may not be fitted to the pole (laser safety rule)")


# --------------------------------------------------------------------------- site

def load_site(path=None, overrides=None):
    """Load site.yaml and resolve the fitted products. `overrides` swaps products by
    category, e.g. {"camera": "dome_4mp_2_8mm_generic"}."""
    path = path or os.path.join(ROOT_DIR, "site.yaml")
    with open(path) as f:
        site = yaml.safe_load(f)
    fitted_names = dict(site.get("products", {}))
    fitted_names.update(overrides or {})
    missing = [c for c in CATEGORIES if c not in fitted_names]
    if missing:
        raise CatalogError(f"{path}: products: has no entry for {', '.join(missing)}")
    site["fitted"] = {c: load_product(c, fitted_names[c]) for c in CATEGORIES}
    check_laser_fit(site["fitted"]["laser"])
    return site


def validate_all():
    """Load every product file; returns {category: [names]} or raises on the first bad file."""
    return {c: [load_product(c, n)["id"] for n in list_products(c)] for c in CATEGORIES}
