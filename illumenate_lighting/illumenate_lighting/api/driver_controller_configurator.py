# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Driver / Controller Configurator API

Powers the Webflow "configurator settings" experience for power supplies
(ilL-Driver-Template) and controllers (ilL-Controller-Template).

Unlike the fixture and tape/neon configurators, there is no length or
manufacturing math here: a configuration is simply a set of axis selections
that must resolve to exactly one variant row on the template. Every orderable
driver/controller already exists as an ilL-Spec-Driver / ilL-Spec-Controller,
so validation is an exact match against the template's variant table rather
than a nearest/fuzzy lookup.

Endpoints (all guest-accessible, mirroring webflow_configurator.py):
- get_driver_configurator_init / get_controller_configurator_init
- get_driver_cascading_options / get_controller_cascading_options
- validate_driver_configuration / validate_controller_configuration

Each endpoint takes the Webflow ``product_slug`` or, for the portal power
supply configurator that schedules ilL-Driver-Template lines, the template
itself as ``template``.
"""

import json
from typing import Any

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.item_availability import enabled_rows
from illumenate_lighting.illumenate_lighting.doctype.ill_controller_template.ill_controller_template import (
    CONTROLLER_VARIANT_AXES,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_driver_template.ill_driver_template import (
    DRIVER_VARIANT_AXES,
    _normalise_axis_value,
)
from illumenate_lighting.illumenate_lighting.portal.configurator_access import price_scoped
from illumenate_lighting.illumenate_lighting.portal_listing import product_template, template_scoped

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

#: Ordered configurator steps. ``name`` is the key used in the selections
#: payload; ``option_type`` matches the template's allowed_options rows.
DRIVER_STEPS = [
    {"step": 1, "name": "wattage", "option_type": "Wattage", "label": "Wattage", "depends_on": []},
    {"step": 2, "name": "voltage_output", "option_type": "Voltage Output", "label": "Output Voltage", "depends_on": []},
    {"step": 3, "name": "input_protocol", "option_type": "Input Protocol", "label": "Dimming Input", "depends_on": []},
    {"step": 4, "name": "output_protocol", "option_type": "Output Protocol", "label": "Output Protocol", "depends_on": []},
]

CONTROLLER_STEPS = [
    {"step": 1, "name": "controller_type", "option_type": "Controller Type", "label": "Controller Type", "depends_on": []},
    {"step": 2, "name": "channels", "option_type": "Channels", "label": "Channels", "depends_on": ["controller_type"]},
    {"step": 3, "name": "zones", "option_type": "Zones", "label": "Zones", "depends_on": ["controller_type"]},
    {"step": 4, "name": "input_protocol", "option_type": "Input Protocol", "label": "Input Protocol", "depends_on": []},
    {"step": 5, "name": "output_protocol", "option_type": "Output Protocol", "label": "Output Protocol", "depends_on": []},
    {"step": 6, "name": "wireless_protocol", "option_type": "Wireless Protocol", "label": "Wireless Protocol", "depends_on": []},
    {"step": 7, "name": "mounting_type", "option_type": "Mounting Type", "label": "Mounting Type", "depends_on": []},
]

#: product_type -> everything needed to drive the generic implementation.
_KINDS = {
    "Driver": {
        "template_doctype": "ilL-Driver-Template",
        "product_field": "driver_template",
        "spec_field": "driver_spec",
        "spec_doctype": "ilL-Spec-Driver",
        "steps": DRIVER_STEPS,
        "axes": DRIVER_VARIANT_AXES,
    },
    "Controller": {
        "template_doctype": "ilL-Controller-Template",
        "product_field": "controller_template",
        "spec_field": "controller_spec",
        "spec_doctype": "ilL-Spec-Controller",
        "steps": CONTROLLER_STEPS,
        "axes": CONTROLLER_VARIANT_AXES,
    },
}


# =============================================================================
# PUBLIC API ENDPOINTS
# =============================================================================

@frappe.whitelist(allow_guest=True)
@template_scoped("ilL-Driver-Template", resolve=lambda a: a.get("template") or product_template("driver_template")(a))
@price_scoped
def get_driver_configurator_init(product_slug: str | None = None, template: str | None = None) -> dict:
    """Initialise the Driver configurator for a Webflow product slug or an ilL-Driver-Template."""
    return _get_configurator_init("Driver", product_slug, template)


@frappe.whitelist(allow_guest=True)
@template_scoped("ilL-Controller-Template", resolve=product_template("controller_template"))
@price_scoped
def get_controller_configurator_init(product_slug: str) -> dict:
    """Initialise the Controller configurator for a Webflow product slug."""
    return _get_configurator_init("Controller", product_slug)


@frappe.whitelist(allow_guest=True)
@template_scoped("ilL-Driver-Template", resolve=lambda a: a.get("template") or product_template("driver_template")(a))
@price_scoped
def get_driver_cascading_options(
    product_slug: str | None = None,
    step_name: str | None = None,
    selections: str | None = None,
    template: str | None = None,
) -> dict:
    """Narrow the remaining Driver options to those still reachable."""
    return _get_cascading_options("Driver", product_slug, step_name, selections, template)


@frappe.whitelist(allow_guest=True)
@template_scoped("ilL-Controller-Template", resolve=product_template("controller_template"))
@price_scoped
def get_controller_cascading_options(
    product_slug: str,
    step_name: str,
    selections: str,
) -> dict:
    """Narrow the remaining Controller options to those still reachable."""
    return _get_cascading_options("Controller", product_slug, step_name, selections)


@frappe.whitelist(allow_guest=True)
@template_scoped("ilL-Driver-Template", resolve=lambda a: a.get("template") or product_template("driver_template")(a))
@price_scoped
def validate_driver_configuration(
    product_slug: str | None = None, selections: str | None = None, template: str | None = None
) -> dict:
    """Resolve a Driver selection set to exactly one template variant."""
    return _validate_configuration("Driver", product_slug, selections, template)


@frappe.whitelist(allow_guest=True)
@template_scoped("ilL-Controller-Template", resolve=product_template("controller_template"))
@price_scoped
def validate_controller_configuration(product_slug: str, selections: str) -> dict:
    """Resolve a Controller selection set to exactly one template variant."""
    return _validate_configuration("Controller", product_slug, selections)


# =============================================================================
# SHARED IMPLEMENTATION
# =============================================================================

def _get_configurator_init(kind: str, product_slug: str | None, template_name: str | None = None) -> dict:
    cfg = _KINDS[kind]
    template, product = _resolve_template(kind, product_slug, template_name)
    if not template:
        return {"success": False, "error": _("Product not found or not configurable")}

    steps = []
    options = {}
    variants = _matching_variants(template, [], cfg["axes"], {}, partial=True)
    for step in cfg["steps"]:
        values = _allowed_values(template, step["option_type"])
        if template.variants:
            # Only values some enabled, active variant still offers.
            offered = {_normalise_axis_value(v.get(cfg["axes"][step["option_type"]])) for v in variants}
            values = [v for v in values if _normalise_axis_value(v["value"]) in offered]
        if not values:
            continue
        steps.append({
            "step": step["step"],
            "name": step["name"],
            "option_type": step["option_type"],
            "label": step["label"],
            "required": True,
            "depends_on": step["depends_on"],
        })
        options[step["name"]] = values

    return {
        "success": True,
        "product": {
            "slug": product.product_slug if product else "",
            "name": product.product_name if product else template.template_name or template.name,
            "product_type": kind,
            "template_code": template.name,
        },
        "template": {
            "code": template.name,
            "name": template.template_name,
            "series_code": template.sku_series_code or "",
            "base_price_msrp": template.base_price_msrp or 0,
            "image": template_image(template),
            "spec_sheet": template.get("spec_sheet") or "",
            "warranty": template.get("warranty") or (
                _("{0} years").format(template.warranty_years) if template.get("warranty_years") else ""
            ),
        },
        "steps": steps,
        "options": options,
        "variant_count": len(variants),
        "part_number_prefix": _part_number_prefix(template),
    }


def _get_cascading_options(
    kind: str, product_slug: str | None, step_name: str, selections: str, template_name: str | None = None
) -> dict:
    cfg = _KINDS[kind]
    try:
        selections_dict = _coerce_selections(selections)
    except ValueError:
        return {"success": False, "error": _("Invalid selections JSON")}

    template, _product = _resolve_template(kind, product_slug, template_name)
    if not template:
        return {"success": False, "error": _("Product not found or not configurable")}
    active_steps = _active_steps(cfg, template)

    # Variants still reachable given everything selected so far.
    candidates = _matching_variants(template, active_steps, cfg["axes"], selections_dict, partial=True)

    updated_options = {}
    clear_selections = []
    for step in active_steps:
        if step["name"] == step_name:
            continue
        fieldname = cfg["axes"][step["option_type"]]
        reachable = {
            _normalise_axis_value(v.get(fieldname))
            for v in candidates
        }
        values = [
            opt for opt in _allowed_values(template, step["option_type"])
            if _normalise_axis_value(opt["value"]) in reachable
        ]
        updated_options[step["name"]] = values

        # Drop a downstream selection that the new narrowing made impossible.
        current = selections_dict.get(step["name"])
        if current and _normalise_axis_value(current) not in reachable:
            clear_selections.append(step["name"])

    return {
        "success": True,
        "step_completed": step_name,
        "selections": selections_dict,
        "updated_options": updated_options,
        "clear_selections": clear_selections,
        "matching_variant_count": len(candidates),
    }


def _validate_configuration(
    kind: str, product_slug: str | None, selections: str, template_name: str | None = None
) -> dict:
    cfg = _KINDS[kind]
    try:
        selections_dict = _coerce_selections(selections)
    except ValueError:
        return {"success": False, "error": _("Invalid selections JSON")}

    template, product = _resolve_template(kind, product_slug, template_name)
    if not template:
        return {"success": False, "error": _("Product not found or not configurable")}
    active_steps = _active_steps(cfg, template)

    missing = [s["label"] for s in active_steps if not selections_dict.get(s["name"])]
    if missing:
        return {
            "success": False,
            "error": _("Please complete every step before continuing"),
            "missing_steps": missing,
        }

    matches = _matching_variants(template, active_steps, cfg["axes"], selections_dict, partial=False)

    if not matches:
        return {
            "success": False,
            "error": _("No {0} matches that combination of options").format(kind.lower()),
            "selections": selections_dict,
        }
    if len(matches) > 1:
        # Guarded at template save time; surfaced here so bad data is visible.
        return {
            "success": False,
            "error": _("That combination of options matches more than one variant. "
                       "Please contact us so we can correct the product data."),
            "selections": selections_dict,
        }

    variant = matches[0]
    spec_name = variant.get(cfg["spec_field"])
    # The variant's Item is a fetched snapshot that can be blank or stale; the spec is the source.
    item = (spec_name and frappe.db.get_value(cfg["spec_doctype"], spec_name, "item")) or variant.get("item")
    pricing = _calculate_pricing(template, active_steps, selections_dict, variant)
    # Power supplies are ordered by their spec ID, not a template-built part number.
    part_number = (
        spec_name if kind == "Driver" and spec_name
        else _build_part_number(template, active_steps, selections_dict, variant)
    )

    return {
        "success": True,
        "product_slug": product.product_slug if product else "",
        "template_code": template.name,
        "template_name": template.template_name or template.name,
        "selections": selections_dict,
        "part_number": part_number,
        "variant": {
            "spec_doctype": cfg["spec_doctype"],
            "spec_name": spec_name,
            # Child row name — lets the spec-sheet pipeline reload the exact
            # variant even when two variants share the same spec document.
            "variant_name": variant.get("name"),
            "item": item,
            "variant_code": variant.get("variant_code") or "",
            "item_name": frappe.db.get_value("Item", item, "item_name") if item else "",
        },
        "specs": _spec_summary(cfg["spec_doctype"], spec_name, variant),
        "pricing": pricing,
        "stock": _stock(item),
    }


# =============================================================================
# HELPERS
# =============================================================================

def _resolve_template(kind: str, product_slug: str | None = None, template_name: str | None = None):
    """The template a request configures and its Webflow product (None when addressed by template)."""
    cfg = _KINDS[kind]
    if template_name:
        if not frappe.db.get_value(cfg["template_doctype"], template_name, "is_active"):
            return None, None
        return frappe.get_doc(cfg["template_doctype"], template_name), None
    product = _get_configurable_product(kind, product_slug)
    if not product:
        return None, None
    return frappe.get_doc(cfg["template_doctype"], product.get(cfg["product_field"])), product


def template_image(template) -> str | None:
    """A template's picture: its Webflow product's first gallery image."""
    if not template.get("webflow_product"):
        return None
    from illumenate_lighting.templates.pages.configure import _fetch_webflow_gallery

    gallery = _fetch_webflow_gallery([template.webflow_product]).get(template.webflow_product) or []
    return gallery[0]["image"] if gallery else None


#: ilL-Spec-Driver fields shown with a configured power supply, in display order.
DRIVER_SPEC_SUMMARY = (
    ("max_wattage", "Max wattage", " W"),
    ("voltage_output", "Output voltage", ""),
    ("output_type", "Output type", ""),
    ("outputs_count", "Outputs", ""),
    ("input_voltage", "Input voltage", ""),
    ("location_rating", "Location rating", ""),
    ("mounting", "Mounting", ""),
)


def _stock(item_code: str | None) -> dict | None:
    """Portal stock for the resolved Item; signed-in users only, like the other configurators."""
    if not item_code or frappe.session.user == "Guest":
        return None
    from illumenate_lighting.illumenate_lighting.api.pricing_utils import (
        StockScopeUnavailable,
        _bulk_stock_query,
    )

    try:
        available = _bulk_stock_query([item_code]).get(item_code, 0.0)
    except StockScopeUnavailable:
        return {"availability": "unknown"}
    return {"in_stock": available >= 1, "qty_available": int(available) if float(available).is_integer() else available}


def _spec_summary(spec_doctype: str, spec_name: str | None, variant) -> list[dict]:
    """The resolved spec's headline values as [{label, value}] for the summary card."""
    if spec_doctype != "ilL-Spec-Driver" or not spec_name:
        return []
    spec = frappe.db.get_value(
        spec_doctype,
        spec_name,
        [field for field, _label, _unit in DRIVER_SPEC_SUMMARY if field != "input_voltage"]
        + ["input_voltage", "input_voltage_min", "input_voltage_max", "input_voltage_type"],
        as_dict=True,
    )
    if not spec:
        return []
    if not spec.input_voltage and spec.input_voltage_min and spec.input_voltage_max:
        spec.input_voltage = f"{spec.input_voltage_min}-{spec.input_voltage_max} {spec.input_voltage_type or ''}".strip()
    rows = []
    for field, label, unit in DRIVER_SPEC_SUMMARY:
        value = spec.get(field)
        if value in (None, "", 0):
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        rows.append({"label": _(label), "value": f"{value}{unit}"})
    return rows


def _get_configurable_product(kind: str, product_slug: str):
    """Return the configurable ilL-Webflow-Product for a slug, or None."""
    cfg = _KINDS[kind]
    if not product_slug:
        return None
    if not frappe.db.exists("ilL-Webflow-Product", {"product_slug": product_slug}):
        return None

    product = frappe.get_doc("ilL-Webflow-Product", {"product_slug": product_slug})
    if product.product_type != kind:
        return None
    if not product.is_configurable:
        return None
    if not product.get(cfg["product_field"]):
        return None
    return product


def _coerce_selections(selections: Any) -> dict:
    """Accept either a JSON string or an already-decoded dict."""
    if selections in (None, ""):
        return {}
    if isinstance(selections, dict):
        return selections
    try:
        decoded = json.loads(selections)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid selections JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Selections must be an object")
    return decoded


def _active_steps(cfg: dict, template) -> list[dict]:
    """Steps the template actually exposes (i.e. that have allowed options)."""
    return [s for s in cfg["steps"] if _allowed_values(template, s["option_type"])]


def _allowed_values(template, option_type: str) -> list[dict]:
    """Active allowed_options rows for one option type, in display order."""
    values = []
    seen = set()
    for opt in template.allowed_options or []:
        if opt.option_type != option_type or not opt.is_active:
            continue
        value = opt.attribute_link or opt.option_value
        if not value or value in seen:
            continue
        seen.add(value)
        values.append({
            "value": value,
            "label": opt.option_label or value,
            "code": opt.option_code or "",
            "is_default": bool(opt.is_default),
            "msrp_adder": opt.msrp_adder or 0,
        })
    return values


def _matching_variants(
    template,
    active_steps: list[dict],
    axes: dict[str, str],
    selections: dict,
    partial: bool,
) -> list:
    """Active variants consistent with *selections*.

    With ``partial=True`` unselected steps are ignored, which is what the
    cascading endpoint needs. With ``partial=False`` every active step must
    match exactly, giving the single variant a configuration resolves to.
    """
    matches = []
    # A variant whose Item is disabled cannot be configured.
    for variant in enabled_rows(template.variants or [], "item"):
        if not variant.is_active:
            continue
        for step in active_steps:
            selected = selections.get(step["name"])
            if selected in (None, "") and partial:
                continue
            fieldname = axes[step["option_type"]]
            if _normalise_axis_value(variant.get(fieldname)) != _normalise_axis_value(selected):
                break
        else:
            matches.append(variant)
    return matches


def _part_number_prefix(template) -> str:
    series_code = template.sku_series_code or template.name
    return f"ILL-{series_code}"


def _build_part_number(template, active_steps: list[dict], selections: dict, variant) -> str:
    """Build the configured part number.

    A variant_code, when present, is authoritative: it is the manufacturer's
    own SKU suffix. Otherwise the part number is assembled from the option
    codes of the selected allowed_options rows.
    """
    prefix = _part_number_prefix(template)
    if variant.get("variant_code"):
        return f"{prefix}-{variant.get('variant_code')}"

    segments = []
    for step in active_steps:
        selected = selections.get(step["name"])
        code = ""
        for opt in _allowed_values(template, step["option_type"]):
            if opt["value"] == selected:
                code = opt["code"]
                break
        segments.append(code or "xx")
    return "-".join([prefix, *segments])


def _calculate_pricing(template, active_steps: list[dict], selections: dict, variant) -> dict:
    """Variant MSRP (or template base) plus the adders of the selected options."""
    base_price = variant.get("msrp") or template.base_price_msrp or 0

    option_adders = 0.0
    for step in active_steps:
        selected = selections.get(step["name"])
        for opt in _allowed_values(template, step["option_type"]):
            if opt["value"] == selected:
                option_adders += float(opt["msrp_adder"] or 0)
                break

    return {
        "base_price": float(base_price),
        "option_adders": option_adders,
        "total_msrp": float(base_price) + option_adders,
        "currency": frappe.defaults.get_global_default("currency") or "USD",
    }
