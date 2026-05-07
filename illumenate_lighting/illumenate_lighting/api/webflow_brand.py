# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Brand API

Single source of truth for resolving per-brand Webflow configuration
(collection IDs, base URLs, n8n credentials, configurator inclusion).

The brand model lets a single ERPNext instance publish to N Webflow sites
(one per brand). Brand records are stored in the ``ilL-Webflow-Brand``
DocType; the brand_code (e.g. ``illumenate``, ``lighting_206``) is the
stable identifier used everywhere (DB, Python, n8n).

Endpoints:
- list_brands: List brands (whitelisted for n8n / UI).
- get_brand_config: Return the full configuration map for one brand.
- get_default_brand: Return the brand_code marked is_default=1.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

import frappe
from frappe import _


# Default base URL when a brand record has no explicit override.
DEFAULT_ERPNEXT_BASE_URL = "https://illumenatelighting.v.frappe.cloud"

# Cache key for the brand map.
_CACHE_KEY = "illumenate_lighting:webflow_brand_cache:v1"


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def clear_brand_cache() -> None:
    """Invalidate the in-process and Redis-backed brand cache."""
    try:
        frappe.cache().delete_value(_CACHE_KEY)
    except Exception:
        pass


def _load_brand_map() -> Dict[str, Dict[str, Any]]:
    """Build the {brand_code: brand_dict} map from the database."""
    cache = frappe.cache()
    cached = cache.get_value(_CACHE_KEY)
    if cached:
        return cached

    rows = frappe.get_all(
        "ilL-Webflow-Brand",
        fields=[
            "name",
            "brand_code",
            "brand_label",
            "is_active",
            "is_default",
            "webflow_site_id",
            "n8n_webhook_url",
            "sync_enabled",
            "n8n_webflow_credential_name",
            "include_configurator_payload",
            "erpnext_base_url",
            "webflow_site_url",
        ],
    )

    brand_map: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        code = row.get("brand_code") or row.get("name")
        if not code:
            continue
        brand_map[code] = {
            "brand_code": code,
            "brand_label": row.get("brand_label") or code,
            "is_active": bool(row.get("is_active")),
            "is_default": bool(row.get("is_default")),
            "webflow_site_id": row.get("webflow_site_id") or "",
            "n8n_webhook_url": row.get("n8n_webhook_url") or "",
            "sync_enabled": bool(row.get("sync_enabled")),
            "n8n_webflow_credential_name": row.get("n8n_webflow_credential_name") or "",
            "include_configurator_payload": bool(row.get("include_configurator_payload")),
            "erpnext_base_url": row.get("erpnext_base_url") or DEFAULT_ERPNEXT_BASE_URL,
            "webflow_site_url": row.get("webflow_site_url") or "",
            "collections": _load_collections_for(row["name"]),
        }

    cache.set_value(_CACHE_KEY, brand_map)
    return brand_map


def _load_collections_for(brand_name: str) -> Dict[str, str]:
    """Load {collection_kind: webflow_collection_id} for one brand."""
    rows = frappe.get_all(
        "ilL-Webflow-Brand-Collection",
        filters={"parent": brand_name, "parenttype": "ilL-Webflow-Brand"},
        fields=["collection_kind", "webflow_collection_id"],
    )
    return {r["collection_kind"]: r["webflow_collection_id"] or "" for r in rows}


# ---------------------------------------------------------------------------
# Public helpers (server-side)
# ---------------------------------------------------------------------------


def resolve_brand(brand_code: Optional[str], *, allow_inactive: bool = False) -> Dict[str, Any]:
    """Return the brand configuration dict.

    If ``brand_code`` is falsy, falls back to the default brand. Raises
    ``frappe.ValidationError`` if the brand is unknown or (unless allowed)
    inactive.
    """
    brand_map = _load_brand_map()

    if not brand_code:
        brand_code = get_default_brand()
        if not brand_code:
            frappe.throw(_("No default Webflow brand is configured."))

    brand = brand_map.get(brand_code)
    if not brand:
        frappe.throw(_("Unknown Webflow brand: {0}").format(brand_code))

    if not brand["is_active"] and not allow_inactive:
        frappe.throw(_("Webflow brand '{0}' is inactive.").format(brand_code))

    return brand


def get_default_brand() -> Optional[str]:
    """Return the brand_code of the default brand, or None."""
    for code, brand in _load_brand_map().items():
        if brand.get("is_default"):
            return code
    # Fallback: first active brand
    for code, brand in _load_brand_map().items():
        if brand.get("is_active"):
            return code
    return None


def list_active_brands() -> List[str]:
    """Return all brand_codes where is_active=1."""
    return [code for code, brand in _load_brand_map().items() if brand.get("is_active")]


def get_collection_id(brand_code: str, collection_kind: str) -> str:
    """Look up a Webflow collection ID by brand + kind. Returns '' if unset."""
    brand = resolve_brand(brand_code)
    return brand["collections"].get(collection_kind, "")


def get_base_url(brand_code: Optional[str]) -> str:
    """Return the ERPNext base URL to use for absolute file links for a brand."""
    if not brand_code:
        return DEFAULT_ERPNEXT_BASE_URL
    try:
        brand = resolve_brand(brand_code, allow_inactive=True)
    except frappe.ValidationError:
        return DEFAULT_ERPNEXT_BASE_URL
    return brand.get("erpnext_base_url") or DEFAULT_ERPNEXT_BASE_URL


def include_configurator(brand_code: Optional[str]) -> bool:
    """Whether the configurator payload should be emitted for this brand."""
    if not brand_code:
        brand_code = get_default_brand()
    if not brand_code:
        return True
    try:
        brand = resolve_brand(brand_code, allow_inactive=True)
    except frappe.ValidationError:
        return True
    return bool(brand.get("include_configurator_payload"))


def get_or_create_sync_row(parent_doc, child_table_field: str, brand_code: str):
    """Idempotently get or create the per-brand sync child row.

    Args:
        parent_doc: The Frappe document instance owning the child table.
        child_table_field: Name of the child table field (e.g. "sync_targets",
            "webflow_sync_targets").
        brand_code: The brand_code to find/create a row for.

    Returns:
        The child row document.
    """
    rows = parent_doc.get(child_table_field) or []
    for row in rows:
        if row.brand == brand_code:
            return row
    # Append a new row with sane defaults
    return parent_doc.append(child_table_field, {
        "brand": brand_code,
        "sync_status": "Never Synced",
    })


# ---------------------------------------------------------------------------
# Whitelisted endpoints (called by n8n / Desk JS)
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=False)
def list_brands(active_only: bool = True) -> Dict[str, Any]:
    """Return brands as a list (for UI dropdowns / n8n looping).

    Args:
        active_only: If True (default), only is_active=1 brands are returned.

    Returns:
        {"brands": [ {brand_code, brand_label, is_active, is_default}, ... ]}
    """
    out = []
    for code, brand in _load_brand_map().items():
        if active_only and not brand.get("is_active"):
            continue
        out.append({
            "brand_code": code,
            "brand_label": brand["brand_label"],
            "is_active": brand["is_active"],
            "is_default": brand["is_default"],
        })
    return {"brands": out}


@frappe.whitelist(allow_guest=False)
def get_brand_config(brand: str) -> Dict[str, Any]:
    """Return the full per-brand config (used by n8n 'Get Brand Config' nodes).

    Includes products_collection_id and categories_collection_id at the top
    level for convenience, plus the full collections map.
    """
    cfg = resolve_brand(brand, allow_inactive=True)
    collections = cfg.get("collections", {})
    return {
        "brand_code": cfg["brand_code"],
        "brand_label": cfg["brand_label"],
        "is_active": cfg["is_active"],
        "sync_enabled": cfg["sync_enabled"],
        "webflow_site_id": cfg["webflow_site_id"],
        "n8n_webflow_credential_name": cfg["n8n_webflow_credential_name"],
        "include_configurator_payload": cfg["include_configurator_payload"],
        "erpnext_base_url": cfg["erpnext_base_url"],
        "webflow_site_url": cfg["webflow_site_url"],
        "products_collection_id": collections.get("Products", ""),
        "categories_collection_id": collections.get("Categories", ""),
        "collections": collections,
    }
