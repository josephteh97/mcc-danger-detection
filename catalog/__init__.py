"""Product catalogue: one folder per hardware category, one YAML file per product.

Each folder's _schema.yaml lists the fields the simulator reads. A product file missing a
field, or with a field of the wrong type, is refused with the file and field named.
"""
from __future__ import annotations

import functools
import os

import yaml

CATALOG_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CATALOG_DIR)
BASE_CATEGORIES = ["camera", "floodlight", "speaker", "laser", "ai_box", "battery", "solar", "mast"]
V11_CATEGORIES = ["switch", "router", "power_conv", "monitor"]       # version 11 pole network and power
CATEGORIES = BASE_CATEGORIES + V11_CATEGORIES

_TYPES = {"str": str, "bool": bool, "number": (int, float), "list": list}


class CatalogError(ValueError):
    pass


@functools.cache
def load_schema(category):
    path = os.path.join(CATALOG_DIR, category, "_schema.yaml")
    if not os.path.exists(path):
        raise CatalogError(f"unknown catalogue category '{category}' (expected one of {', '.join(CATEGORIES)})")
    with open(path) as f:
        return yaml.safe_load(f)


# Fields any product may carry (version 11): checked for type when present.
COMMON_OPTIONAL = {
    "legacy": {"type": "bool", "doc": "used only by identification; left out of v11 totals and PoE budgets"},
    "watts_typ": {"type": "number", "doc": "typical power drawn"},
    "watts_max": {"type": "number", "doc": "worst-case power drawn"},
    "poe_class": {"type": "number", "doc": "IEEE 802.3 PoE class (0-8) for products powered over PoE"},
}


def validate(category, data, path="<product>"):
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: not a YAML mapping")
    for field, spec in {**COMMON_OPTIONAL, **load_schema(category)["fields"]}.items():
        if field not in data:
            if spec.get("optional") or field in COMMON_OPTIONAL:
                continue
            raise CatalogError(f"{path}: missing required field '{field}' ({spec.get('doc', '')})")
        want = _TYPES[spec["type"]]
        value = data[field]
        if isinstance(value, bool) and spec["type"] == "number" or not isinstance(value, want):
            raise CatalogError(f"{path}: field '{field}' should be {spec['type']}, got {value!r}")
    return data


def list_products(category):
    folder = os.path.join(CATALOG_DIR, category)
    return sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".yaml") and not f.startswith("_"))


def load_product(category, name, changed=None):
    """One product file, validated against its folder's schema. `changed` replaces some of its
    fields for this load only (the dashboard's what-if numbers); the file is untouched."""
    path = os.path.join(CATALOG_DIR, category, f"{name}.yaml")
    if not os.path.exists(path):
        raise CatalogError(f"no product '{name}' in catalog/{category} "
                           f"(available: {', '.join(list_products(category))})")
    with open(path) as f:
        data = yaml.safe_load(f)
    product = dict(validate(category, data, os.path.relpath(path, ROOT_DIR)))
    product["id"] = name
    if changed:
        product.update(validate(category, {**product, **changed}, f"what-if values for {name}"))
        product["id"], product["edited"] = name, sorted(changed)
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

SITES_DIR = os.path.join(ROOT_DIR, "sites")
PROFILES = ("phase1", "v11")


def active_profile(path=None):
    """The site profile in use: $TWIN_PROFILE, else the selector in site.yaml."""
    name = os.environ.get("TWIN_PROFILE")
    if not name:
        with open(path or os.path.join(ROOT_DIR, "site.yaml")) as f:
            name = (yaml.safe_load(f) or {}).get("profile", "phase1")
    if name not in PROFILES:
        raise CatalogError(f"unknown site profile '{name}' (expected one of {', '.join(PROFILES)})")
    return name


def app_config_path(profile=None):
    """The app config the Orin runs for a profile: app/config.yaml (phase 1) or app/config.v11.yaml."""
    profile = profile or active_profile()
    return os.path.join(ROOT_DIR, "app", "config.yaml" if profile == "phase1" else f"config.{profile}.yaml")


def load_site(path=None, overrides=None, profile=None, product_overrides=None):
    """Load a site profile and resolve the fitted products (each power plan's products resolve
    later, in plan_products()). `profile` picks sites/<profile>.yaml; without it, `path` (a site file or
    the site.yaml selector) or the active profile is used. `overrides` swaps products by category,
    e.g. {"camera": "dome_4mp_2_8mm_generic"}; `product_overrides` changes fields of products by id,
    e.g. {"lifepo4_24v_50ah": {"capacity_ah": 100}} (what-if numbers; files untouched)."""
    if profile is None and path:
        with open(path) as f:
            site = yaml.safe_load(f)
        if "site" not in site:                     # a selector file
            return load_site(overrides=overrides, profile=active_profile(path), product_overrides=product_overrides)
        profile = site.get("profile", os.path.splitext(os.path.basename(path))[0])
    else:
        profile = profile or active_profile()
        path = os.path.join(SITES_DIR, f"{profile}.yaml")
        with open(path) as f:
            site = yaml.safe_load(f)
    site["profile"] = profile
    fitted_names = dict(site.get("products", {}))
    fitted_names.update(overrides or {})
    missing = [c for c in BASE_CATEGORIES if c not in fitted_names]
    if missing:
        raise CatalogError(f"{path}: products: has no entry for {', '.join(missing)}")
    unknown = [c for c in fitted_names if c not in CATEGORIES]
    if unknown:
        raise CatalogError(f"{path}: products: unknown category {', '.join(unknown)}")
    edits = site["product_overrides"] = product_overrides or {}
    loaded = {}

    def product(category, name):                  # each product file read once per site
        if (category, name) not in loaded:
            loaded[category, name] = load_product(category, name, edits.get(name))
        return loaded[category, name]
    site["fitted"] = {c: [product(c, n) for n in names] if isinstance(names, list) else product(c, names)
                      for c, names in fitted_names.items()}
    check_laser_fit(site["fitted"]["laser"])
    return site


def plan_products(site, plan=None):
    """Each power plan's products, {plan: {"battery", "solar", "parts"}}, or one plan's. Resolved on
    first use and kept on the site, so a bad name in a plan fails only the power callers."""
    if "_plan_products" not in site:
        edits = site.get("product_overrides") or {}
        loaded = {(c, p["id"]): p for c in site["fitted"] for p in fitted(site, c)}   # reuse the fitted ones

        def product(category, name):
            if name and (category, name) not in loaded:
                loaded[category, name] = load_product(category, name, edits.get(name))
            return loaded.get((category, name)) if name else None
        site["_plan_products"] = {
            name: {"battery": product("battery", p.get("battery")), "solar": product("solar", p.get("solar")),
                   "parts": [product("power_conv", n) for n in p.get("parts", [])]}
            for name, p in (site.get("power_plans") or {}).items()}
    plans = site["_plan_products"]
    return plans if plan is None else plans[plan]


def fitted(site, category):
    """The products fitted in one category, as a list (empty, one, or several like power_conv)."""
    p = site["fitted"].get(category)
    return [] if p is None else p if isinstance(p, list) else [p]


def fitted_products(site):
    """Every fitted product as a flat list (categories that fit several, like power_conv, expanded)."""
    return [p for c in site["fitted"] for p in fitted(site, c)]


def validate_all():
    """Load every product file; returns {category: [names]} or raises on the first bad file."""
    return {c: [load_product(c, n)["id"] for n in list_products(c)] for c in CATEGORIES}
