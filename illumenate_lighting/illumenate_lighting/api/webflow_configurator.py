# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Configurator API (Revised)

Matches the Webflow configurator UI design with horizontal step flow:
Series → Dry/Wet → CCT → Output → Lens → Mounting → Finish → Length → Start Feed → End Feed

Series (including LED Package) is pre-selected based on the fixture product page.
"""

import frappe
import hashlib
import json
from frappe import _
from typing import Optional, List, Dict, Any
from frappe.utils import now_datetime, add_to_date


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

CACHE_TTL_HOURS = 24

# Configurator step order matching Webflow UI design
CONFIGURATOR_STEPS = [
    {"step": 0, "name": "series", "label": "Series", "required": True, "locked": True, "depends_on": []},
    {"step": 1, "name": "environment_rating", "label": "Dry/Wet", "required": True, "locked": False, "depends_on": ["series"]},
    {"step": 2, "name": "cct", "label": "CCT", "required": True, "locked": False, "depends_on": ["series", "environment_rating"]},
    {"step": 3, "name": "output_level", "label": "Output", "required": True, "locked": False, "depends_on": ["series", "environment_rating", "cct"]},
    {"step": 4, "name": "lens_appearance", "label": "Lens", "required": True, "locked": False, "depends_on": ["series"]},
    {"step": 5, "name": "mounting_method", "label": "Mounting", "required": True, "locked": False, "depends_on": []},
    {"step": 6, "name": "finish", "label": "Finish", "required": True, "locked": False, "depends_on": []},
    {"step": 7, "name": "length", "label": "Length", "required": True, "locked": False, "depends_on": []},
    {"step": 8, "name": "start_feed_direction", "label": "Start Feed Direction", "required": True, "locked": False, "depends_on": []},
    {"step": 9, "name": "start_feed_length", "label": "Start Feed Length", "required": True, "locked": False, "depends_on": ["start_feed_direction"]},
    {"step": 10, "name": "end_feed_direction", "label": "End Feed Direction", "required": True, "locked": False, "depends_on": []},
    {"step": 11, "name": "end_feed_length", "label": "End Feed Length", "required": True, "locked": False, "depends_on": ["end_feed_direction"]},
]

# Standard leader cable lengths in feet
STANDARD_LEADER_LENGTHS_FT = [2, 4, 6, 8, 10, 15, 20, 25, 30]


# =============================================================================
# PUBLIC API ENDPOINTS
# =============================================================================

@frappe.whitelist(allow_guest=True)
def get_configurator_init(product_slug: str) -> dict:
    """
    Initialize configurator for a product.
    
    Returns:
    - Product/Series info (locked, pre-selected)
    - All available options for each step
    - Length constraints
    - Feed direction options
    - Part number prefix
    
    Args:
        product_slug: The Webflow product slug
    
    Returns:
        dict: Configurator initialization data
    """
    # Validate product exists and is configurable
    product = _get_configurable_product(product_slug)
    if not product:
        return {
            "success": False,
            "error": "Product not found or not configurable"
        }
    
    template = frappe.get_doc("ilL-Fixture-Template", product.fixture_template)
    
    # Get series info (locked/pre-selected)
    series_info = _get_series_info(template)
    
    # Get initial options for step 1 (Environment) - filtered by series
    environment_options = _get_environment_ratings(template)
    
    # Get independent options (no cascading)
    lens_options = _get_lens_appearances(template)
    mounting_options = _get_mounting_methods(template)
    finish_options = _get_finishes(template)
    
    # Get feed options
    feed_direction_options = _get_feed_directions()
    leader_length_options = _get_leader_length_options()
    
    # Get length constraints
    min_length_mm = getattr(product, 'min_length_mm', None)
    max_length_mm = getattr(product, 'max_length_mm', None)
    
    length_config = {
        "min_inches": min_length_mm / 25.4 if min_length_mm else 12,
        "max_inches": max_length_mm / 25.4 if max_length_mm else 120,
        "default_inches": 50,
        "max_run_note": "Maximum length is 30 ft"
    }
    
    return {
        "success": True,
        "product": {
            "slug": product.product_slug,
            "name": product.product_name,
            "template_code": product.fixture_template,
        },
        "series": series_info,
        "steps": CONFIGURATOR_STEPS,
        "options": {
            "environment_ratings": environment_options,
            "lens_appearances": lens_options,
            "mounting_methods": mounting_options,
            "finishes": finish_options,
            "feed_directions": feed_direction_options,
            "leader_lengths_ft": leader_length_options,
        },
        "length_config": length_config,
        "part_number_prefix": f"ILL-{series_info['series_code']}-{series_info['led_package_code']}",
        "complex_fixture_url": "/portal/projects"
    }


@frappe.whitelist(allow_guest=True)
def get_cascading_options(
    product_slug: str,
    step_name: str,
    selections: str  # JSON string of current selections
) -> dict:
    """
    Get filtered options for a step based on prior selections.
    
    Called when user makes a selection to update dependent steps.
    
    Cascading rules:
    - environment_rating: Filters from series (available tape offerings)
    - cct: Filters from series + environment
    - output_level: Filters from series + environment + cct
    - lens_appearance: Filters from series (profile lens interface)
    - All others: Independent (no filtering)
    
    Args:
        product_slug: The Webflow product slug
        step_name: The step that was just selected
        selections: JSON string of selections made so far
    
    Returns:
        dict: Updated options for dependent steps
    """
    try:
        selections_dict = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid selections JSON"}
    
    product = _get_configurable_product(product_slug)
    if not product:
        return {"success": False, "error": "Product not found or not configurable"}
    
    template = frappe.get_doc("ilL-Fixture-Template", product.fixture_template)
    
    # Check cache
    cache_key = _generate_cache_key(product_slug, step_name, selections_dict)
    cached = _get_cached_options(cache_key)
    if cached:
        return cached
    
    result = {
        "success": True,
        "step_completed": step_name,
        "selections": selections_dict,
        "updated_options": {},
        "part_number_preview": None,
        "clear_selections": []
    }
    
    # Determine which options need updating based on step completed
    env = selections_dict.get("environment_rating")
    cct = selections_dict.get("cct")
    
    if step_name == "environment_rating" and env:
        # Update CCT options (filtered by environment)
        result["updated_options"]["ccts"] = _get_ccts_for_environment(template, env)
        
        # Clear downstream selections that are no longer valid
        result["clear_selections"] = ["cct", "output_level"]
    
    elif step_name == "cct" and env and cct:
        # Update Output options (filtered by environment + CCT)
        result["updated_options"]["output_levels"] = _get_output_levels_for_cct(
            template, env, cct
        )
        result["clear_selections"] = ["output_level"]
    
    # Generate part number preview
    series_info = _get_series_info(template)
    result["part_number_preview"] = _generate_part_number_preview(
        series_info, selections_dict
    )
    
    # Cache result
    _cache_options(cache_key, result)
    
    return result


@frappe.whitelist(allow_guest=True)
def validate_configuration(
    product_slug: str,
    selections: str
) -> dict:
    """
    Validate a complete configuration and generate final part number.
    
    Args:
        product_slug: The Webflow product slug
        selections: JSON string of all selections
    
    Returns:
        dict: Validation result with part number or errors
    """
    try:
        selections_dict = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid selections JSON"}
    
    product = _get_configurable_product(product_slug)
    if not product:
        return {"success": False, "error": "Product not found"}
    
    template = frappe.get_doc("ilL-Fixture-Template", product.fixture_template)
    series_info = _get_series_info(template)
    
    # Validate required fields
    required_fields = [
        "environment_rating", "cct", "output_level", "lens_appearance",
        "mounting_method", "finish", "length_inches",
        "start_feed_direction", "start_feed_length_ft",
        "end_feed_direction", "end_feed_length_ft"
    ]
    
    missing = [f for f in required_fields if not selections_dict.get(f)]
    if missing:
        return {
            "success": False,
            "is_valid": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing
        }
    
    # Validate length
    length_inches = float(selections_dict.get("length_inches", 0))
    min_length_mm = getattr(product, 'min_length_mm', None)
    max_length_mm = getattr(product, 'max_length_mm', None)
    min_len = min_length_mm / 25.4 if min_length_mm else 12
    max_len = max_length_mm / 25.4 if max_length_mm else 120
    
    if length_inches < min_len or length_inches > max_len:
        return {
            "success": False,
            "is_valid": False,
            "error": f"Length must be between {min_len:.0f} and {max_len:.0f} inches",
            "field": "length_inches"
        }
    
    # Validate tape offering exists for combination
    compatibility = _validate_option_compatibility(template, selections_dict)
    if not compatibility["is_valid"]:
        return {
            "success": False,
            "is_valid": False,
            "error": compatibility["message"]
        }
    
    # Generate final part number
    part_number = _generate_full_part_number(series_info, selections_dict)
    
    # Resolve tape offering
    tape_offering_id = _resolve_tape_offering(template, selections_dict)
    
    # Calculate pricing
    pricing = _calculate_pricing_preview(template, selections_dict, tape_offering_id)
    
    return {
        "success": True,
        "is_valid": True,
        "part_number": part_number,
        "tape_offering_id": tape_offering_id,
        "configuration_summary": _build_configuration_summary(selections_dict),
        "pricing": pricing,
        "can_add_to_project": frappe.session.user != "Guest",
        "can_add_to_cart": True,  # For future e-commerce
        "is_complex_fixture": False  # Single segment
    }


@frappe.whitelist(allow_guest=True)
def get_part_number_preview(
    product_slug: str,
    selections: str
) -> dict:
    """
    Get real-time part number preview as user configures.
    
    Returns partial part number with 'xx' for unselected options.
    """
    try:
        selections_dict = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid selections JSON"}
    
    product = _get_configurable_product(product_slug)
    if not product:
        return {"success": False, "error": "Product not found"}
    
    template = frappe.get_doc("ilL-Fixture-Template", product.fixture_template)
    series_info = _get_series_info(template)
    
    preview = _generate_part_number_preview(series_info, selections_dict)
    
    return {
        "success": True,
        "part_number_preview": preview["full"],
        "segments": preview["segments"],
        "complete_percentage": preview["complete_percentage"]
    }


@frappe.whitelist(allow_guest=True)
def create_complex_fixture_session(
    product_slug: str,
    selections: str,
    fixture_type_id: str = None,
    quantity: int = 1
) -> dict:
    """
    Create a session for complex multi-segment fixture configuration.
    
    Called when user clicks "Have a complex jumper fixture? Use our Fixture Coordinator"
    
    Creates a session with prefilled data and returns the portal redirect URL.
    
    Args:
        product_slug: The Webflow product slug
        selections: JSON string of selections made so far (partial config)
        fixture_type_id: Optional fixture type ID to prefill (e.g., "A1")
        quantity: Quantity to prefill
    
    Returns:
        dict: Session info with redirect URL
    """
    try:
        selections_dict = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        selections_dict = {}
    
    # Create session
    session = frappe.new_doc("ilL-Webflow-Session")
    session.session_id = frappe.generate_hash(length=32)
    session.product_slug = product_slug
    session.configuration_json = json.dumps(selections_dict)
    session.is_complex_fixture = 1
    session.prefill_fixture_type_id = fixture_type_id
    session.prefill_quantity = quantity or 1
    session.created_at = now_datetime()
    session.expires_at = add_to_date(now_datetime(), hours=24)
    
    if frappe.session.user != "Guest":
        session.converted_to_user = frappe.session.user
    
    session.insert(ignore_permissions=True)
    frappe.db.commit()
    
    # Build redirect URL
    redirect_url = f"/portal/projects?session_id={session.session_id}"
    
    return {
        "success": True,
        "session_id": session.session_id,
        "redirect_url": redirect_url,
        "expires_at": str(session.expires_at),
        "message": "Session created. Redirecting to Fixture Coordinator..."
    }


@frappe.whitelist(allow_guest=True)
def get_session(session_id: str) -> dict:
    """
    Get session data by session ID.
    
    Used by portal to retrieve prefilled configuration data.
    
    Args:
        session_id: The session identifier
    
    Returns:
        dict: Session data
    """
    if not frappe.db.exists("ilL-Webflow-Session", session_id):
        return {"success": False, "error": "Session not found"}
    
    session = frappe.get_doc("ilL-Webflow-Session", session_id)
    
    if session.is_expired():
        return {
            "success": False,
            "error": "Session has expired",
            "expired": True
        }
    
    return {
        "success": True,
        "session_id": session.session_id,
        "product_slug": session.product_slug,
        "configuration": session.get_configuration(),
        "is_complex_fixture": session.is_complex_fixture,
        "prefill_fixture_type_id": session.prefill_fixture_type_id,
        "prefill_quantity": session.prefill_quantity,
        "status": session.status,
        "expires_at": str(session.expires_at) if session.expires_at else None
    }


# =============================================================================
# SERIES & LED PACKAGE
# =============================================================================

def _get_series_info(template) -> dict:
    """
    Get series information from template.
    
    Series in the UI combines:
    - Profile family (e.g., "RA01") 
    - LED Package (e.g., "FS" for Full Spectrum)
    """
    series_code = getattr(template, 'default_profile_family', None) or template.template_code
    
    # Get LED package from first tape offering (or most common)
    led_packages = set()
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if tape_offering:
            led_pkg = frappe.db.get_value(
                "ilL-Rel-Tape Offering", tape_offering, "led_package"
            )
            if led_pkg:
                led_packages.add(led_pkg)
    
    # Get primary LED package (for display)
    primary_led_pkg = None
    primary_led_pkg_code = "XX"
    spectrum_type = ""
    
    if led_packages:
        # Use first one (or could prioritize by some logic)
        primary_led_pkg = list(led_packages)[0]
        pkg_data = frappe.db.get_value(
            "ilL-Attribute-LED Package",
            primary_led_pkg,
            ["name", "code", "spectrum_type", "description"],
            as_dict=True
        )
        if pkg_data:
            primary_led_pkg_code = pkg_data.get("code") or "XX"
            spectrum_type = pkg_data.get("spectrum_type") or ""
    
    return {
        "series_code": series_code,
        "series_name": template.template_name,
        "led_package": primary_led_pkg,
        "led_package_code": primary_led_pkg_code,
        "spectrum_type": spectrum_type,
        "display_name": f"ilLumenate {template.template_name} [{primary_led_pkg_code}] {spectrum_type}",
        "all_led_packages": list(led_packages)
    }


# =============================================================================
# CASCADING OPTION FUNCTIONS
# =============================================================================

def _get_environment_ratings(template) -> list:
    """Get environment ratings available for this template's tape offerings."""
    environments = set()
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if getattr(tape_row, 'is_active', True) and getattr(tape_row, 'environment_rating', None):
            environments.add(tape_row.environment_rating)
    
    result = []
    for env_name in environments:
        env = frappe.db.get_value(
            "ilL-Attribute-Environment Rating",
            env_name,
            ["name", "code", "notes"],
            as_dict=True
        )
        if env:
            result.append({
                "value": env.name,
                "label": env.name,
                "code": env.get("code"),
                "description": env.get("notes")
            })
    
    return sorted(result, key=lambda x: x["label"])


def _get_ccts_for_environment(template, environment: str) -> list:
    """Get CCTs available for the selected environment."""
    ccts = set()
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if getattr(tape_row, 'environment_rating', None) != environment:
            continue
        
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if tape_offering:
            cct = frappe.db.get_value("ilL-Rel-Tape Offering", tape_offering, "cct")
            if cct:
                ccts.add(cct)
    
    result = []
    for cct_name in ccts:
        cct = frappe.db.get_value(
            "ilL-Attribute-CCT",
            cct_name,
            ["name", "code", "kelvin", "description"],
            as_dict=True
        )
        if cct:
            result.append({
                "value": cct.name,
                "label": cct.name,
                "code": cct.get("code"),
                "kelvin": cct.get("kelvin"),
                "description": cct.get("description")
            })
    
    # Sort by kelvin (handle compound CCTs like "RGB + 1800K + 4000K")
    return sorted(result, key=lambda x: x.get("kelvin") or 0)


def _get_output_levels_for_cct(template, environment: str, cct: str) -> list:
    """Get output levels available for the selected environment + CCT."""
    output_levels = set()
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if getattr(tape_row, 'environment_rating', None) != environment:
            continue
        
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if not tape_offering:
            continue
        
        offering_data = frappe.db.get_value(
            "ilL-Rel-Tape Offering",
            tape_offering,
            ["cct", "output_level"],
            as_dict=True
        )
        
        if offering_data and offering_data.get("cct") == cct and offering_data.get("output_level"):
            output_levels.add(offering_data.get("output_level"))
    
    result = []
    for level_name in output_levels:
        level = frappe.db.get_value(
            "ilL-Attribute-Output Level",
            level_name,
            ["name", "value", "sku_code"],
            as_dict=True
        )
        if level:
            result.append({
                "value": level.name,
                "label": f"{level.get('value')} lm/ft",
                "numeric_value": level.get("value"),
                "sku_code": level.get("sku_code")
            })
    
    return sorted(result, key=lambda x: x.get("numeric_value", 0))


def _get_lens_appearances(template) -> list:
    """Get lens appearances with transmission percentages."""
    result = []
    
    for opt in getattr(template, 'allowed_options', []) or []:
        opt_type = getattr(opt, 'option_type', None)
        is_active = getattr(opt, 'is_active', True)
        lens_appearance = getattr(opt, 'lens_appearance', None)
        
        if opt_type == "Lens Appearance" and is_active and lens_appearance:
            lens = frappe.db.get_value(
                "ilL-Attribute-Lens Appearance",
                lens_appearance,
                ["name", "code", "transmission"],
                as_dict=True
            )
            if lens:
                transmission = lens.get("transmission") or 100
                label = f"{lens.name}"
                if transmission < 100:
                    label += f" - {transmission:.0f}% transmission"
                
                result.append({
                    "value": lens.name,
                    "label": label,
                    "short_label": lens.name,
                    "code": lens.get("code"),
                    "transmission_pct": transmission,
                    "is_default": getattr(opt, 'is_default', False)
                })
    
    return sorted(result, key=lambda x: (not x.get("is_default"), x["short_label"]))


def _get_mounting_methods(template) -> list:
    """Get mounting methods for this template."""
    result = []
    
    for opt in getattr(template, 'allowed_options', []) or []:
        opt_type = getattr(opt, 'option_type', None)
        is_active = getattr(opt, 'is_active', True)
        mounting_method = getattr(opt, 'mounting_method', None)
        
        if opt_type == "Mounting Method" and is_active and mounting_method:
            method = frappe.db.get_value(
                "ilL-Attribute-Mounting Method",
                mounting_method,
                ["name", "code", "label"],
                as_dict=True
            )
            if method:
                result.append({
                    "value": method.name,
                    "label": method.get("label") or method.name,
                    "code": method.get("code"),
                    "is_default": getattr(opt, 'is_default', False)
                })
    
    return sorted(result, key=lambda x: (not x.get("is_default"), x["label"]))


def _get_finishes(template) -> list:
    """Get finishes for this template."""
    result = []
    
    for opt in getattr(template, 'allowed_options', []) or []:
        opt_type = getattr(opt, 'option_type', None)
        is_active = getattr(opt, 'is_active', True)
        finish = getattr(opt, 'finish', None)
        
        if opt_type == "Finish" and is_active and finish:
            finish_data = frappe.db.get_value(
                "ilL-Attribute-Finish",
                finish,
                ["name", "code", "finish_name"],
                as_dict=True
            )
            if finish_data:
                result.append({
                    "value": finish_data.name,
                    "label": finish_data.get("finish_name") or finish_data.name,
                    "code": finish_data.get("code"),
                    "is_default": getattr(opt, 'is_default', False)
                })
    
    return sorted(result, key=lambda x: (not x.get("is_default"), x["label"]))


def _get_feed_directions() -> list:
    """Get feed direction options (End, Back)."""
    # Check if feed direction attribute exists
    if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
        directions = frappe.get_all(
            "ilL-Attribute-Feed-Direction",
            filters={"is_active": 1},
            fields=["direction_name as name", "code", "description"],
            order_by="direction_name"
        )
        return [
            {"value": d.name, "label": d.name, "code": d.code}
            for d in directions
        ]
    
    # Fallback: use Power Feed Type if it has the right values
    if frappe.db.exists("DocType", "ilL-Attribute-Power Feed Type"):
        feed_types = frappe.get_all(
            "ilL-Attribute-Power Feed Type",
            filters={"is_active": 1},
            fields=["name", "code", "label"],
            order_by="name"
        )
        if feed_types:
            return [
                {"value": f.name, "label": f.get("label") or f.name, "code": f.code}
                for f in feed_types
            ]
    
    # Final fallback: hardcoded based on design
    return [
        {"value": "End", "label": "End", "code": "E"},
        {"value": "Back", "label": "Back", "code": "B"}
    ]


def _get_leader_length_options() -> list:
    """Get standard leader cable length options in feet."""
    return [
        {"value": length, "label": f"{length} ft"}
        for length in STANDARD_LEADER_LENGTHS_FT
    ]


# =============================================================================
# PART NUMBER GENERATION
# =============================================================================

def _generate_part_number_preview(series_info: dict, selections: dict) -> dict:
    """
    Generate part number preview matching the UI format:
    ILL-{Series}{LEDPkg}-{Env}-{CCT}-{Output}-{Lens}-{Mount}-{Finish}
    
    With 'xx' for unselected options.
    """
    segments = []
    
    # Prefix: ILL-{Series}-{LEDPkg}
    prefix = f"ILL-{series_info['series_code']}-{series_info['led_package_code']}"
    segments.append({
        "position": 0,
        "code": prefix,
        "label": "Series",
        "selected": True,
        "locked": True
    })
    
    # Environment
    env_code = "xx"
    if selections.get("environment_rating"):
        env_code = frappe.db.get_value(
            "ilL-Attribute-Environment Rating",
            selections["environment_rating"],
            "code"
        ) or "xx"
    segments.append({
        "position": 1,
        "code": env_code,
        "label": "Dry/Wet",
        "selected": bool(selections.get("environment_rating"))
    })
    
    # CCT
    cct_code = "xx"
    if selections.get("cct"):
        cct_code = frappe.db.get_value(
            "ilL-Attribute-CCT",
            selections["cct"],
            "code"
        ) or "xx"
    segments.append({
        "position": 2,
        "code": cct_code,
        "label": "CCT",
        "selected": bool(selections.get("cct"))
    })
    
    # Output - Calculate fixture-level output (tape output × lens transmission)
    output_code = "xx"
    if selections.get("output_level") and selections.get("lens_appearance"):
        # Get tape output level value
        tape_output_value = frappe.db.get_value(
            "ilL-Attribute-Output Level",
            selections["output_level"],
            "value"
        ) or 0
        
        # Get lens transmission percentage
        lens_transmission = frappe.db.get_value(
            "ilL-Attribute-Lens Appearance",
            selections["lens_appearance"],
            "transmission"
        ) or 100
        
        # Calculate fixture output = tape output × (transmission / 100)
        fixture_output_value = int(round(tape_output_value * (lens_transmission / 100)))
        
        # Find closest fixture-level output level
        fixture_output_levels = frappe.get_all(
            "ilL-Attribute-Output Level",
            filters={"is_fixture_level": 1},
            fields=["name", "value", "sku_code"],
            order_by="value asc"
        )
        
        if fixture_output_levels:
            # Find closest match by value
            closest = min(fixture_output_levels, key=lambda x: abs((x.value or 0) - fixture_output_value))
            output_code = closest.sku_code or "xx"
    elif selections.get("output_level"):
        # Fallback: if no lens selected yet, use tape output level code
        output_code = frappe.db.get_value(
            "ilL-Attribute-Output Level",
            selections["output_level"],
            "sku_code"
        ) or "xx"
    segments.append({
        "position": 3,
        "code": output_code,
        "label": "Output",
        "selected": bool(selections.get("output_level"))
    })
    
    # Lens
    lens_code = "xx"
    if selections.get("lens_appearance"):
        lens_code = frappe.db.get_value(
            "ilL-Attribute-Lens Appearance",
            selections["lens_appearance"],
            "code"
        ) or "xx"
    segments.append({
        "position": 4,
        "code": lens_code,
        "label": "Lens",
        "selected": bool(selections.get("lens_appearance"))
    })
    
    # Mounting
    mount_code = "xx"
    if selections.get("mounting_method"):
        mount_code = frappe.db.get_value(
            "ilL-Attribute-Mounting Method",
            selections["mounting_method"],
            "code"
        ) or "xx"
    segments.append({
        "position": 5,
        "code": mount_code,
        "label": "Mounting",
        "selected": bool(selections.get("mounting_method"))
    })
    
    # Finish
    finish_code = "xx"
    if selections.get("finish"):
        finish_code = frappe.db.get_value(
            "ilL-Attribute-Finish",
            selections["finish"],
            "code"
        ) or "xx"
    segments.append({
        "position": 6,
        "code": finish_code,
        "label": "Finish",
        "selected": bool(selections.get("finish"))
    })
    
    # Build main part number (without length/feed suffix for preview)
    main_codes = [s["code"] for s in segments]
    main_pn = "-".join(main_codes)
    
    # Add length and feed suffix if provided
    suffix_parts = []
    
    if selections.get("length_inches"):
        suffix_parts.append(f"{float(selections['length_inches']):.0f}")
    
    if selections.get("start_feed_direction") and selections.get("start_feed_length_ft"):
        start_dir_code = _get_feed_direction_code(selections["start_feed_direction"])
        suffix_parts.append(f"{start_dir_code}{selections['start_feed_length_ft']}")
    
    if selections.get("end_feed_direction") and selections.get("end_feed_length_ft"):
        end_dir_code = _get_feed_direction_code(selections["end_feed_direction"])
        suffix_parts.append(f"{end_dir_code}{selections['end_feed_length_ft']}")
    
    if suffix_parts:
        main_pn += "-" + "-".join(suffix_parts)
    
    # Calculate completion percentage
    selectable_segments = [s for s in segments if not s.get("locked")]
    feed_selected = all([
        selections.get("start_feed_direction"),
        selections.get("start_feed_length_ft"),
        selections.get("end_feed_direction"),
        selections.get("end_feed_length_ft")
    ])
    length_selected = bool(selections.get("length_inches"))
    
    selected_count = sum(1 for s in selectable_segments if s["selected"])
    total_steps = len(selectable_segments) + 1 + 4  # +1 for length, +4 for feed fields
    selected_count += (1 if length_selected else 0) + (4 if feed_selected else 0)
    
    complete_pct = int((selected_count / total_steps) * 100)
    
    return {
        "full": main_pn,
        "segments": segments,
        "complete_percentage": complete_pct
    }


def _generate_full_part_number(series_info: dict, selections: dict) -> str:
    """Generate the complete validated part number."""
    preview = _generate_part_number_preview(series_info, selections)
    return preview["full"]


def _get_feed_direction_code(direction: str) -> str:
    """Get the code for a feed direction."""
    if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
        code = frappe.db.get_value(
            "ilL-Attribute-Feed-Direction",
            direction,
            "code"
        )
        if code:
            return code
    
    # Fallback
    direction_codes = {"End": "E", "Back": "B"}
    return direction_codes.get(direction, "X")


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _validate_option_compatibility(template, selections: dict) -> dict:
    """Validate that a tape offering exists for the selected combination."""
    environment = selections.get("environment_rating")
    cct = selections.get("cct")
    output_level = selections.get("output_level")
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if getattr(tape_row, 'environment_rating', None) != environment:
            continue
        
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if not tape_offering:
            continue
        
        offering_data = frappe.db.get_value(
            "ilL-Rel-Tape Offering",
            tape_offering,
            ["cct", "output_level"],
            as_dict=True
        )
        
        if (offering_data and 
            offering_data.get("cct") == cct and 
            offering_data.get("output_level") == output_level):
            return {"is_valid": True}
    
    return {
        "is_valid": False,
        "message": "No tape offering available for this combination. Please adjust your selections."
    }


def _resolve_tape_offering(template, selections: dict) -> Optional[str]:
    """Find the tape offering ID for the selected combination."""
    environment = selections.get("environment_rating")
    cct = selections.get("cct")
    output_level = selections.get("output_level")
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if getattr(tape_row, 'environment_rating', None) != environment:
            continue
        
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if not tape_offering:
            continue
        
        offering_data = frappe.db.get_value(
            "ilL-Rel-Tape Offering",
            tape_offering,
            ["cct", "output_level"],
            as_dict=True
        )
        
        if (offering_data and 
            offering_data.get("cct") == cct and 
            offering_data.get("output_level") == output_level):
            return tape_offering
    
    return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_configurable_product(product_slug: str):
    """Get a configurable Webflow product by slug."""
    if not frappe.db.exists("ilL-Webflow-Product", {"product_slug": product_slug}):
        return None
    
    product = frappe.get_doc("ilL-Webflow-Product", {"product_slug": product_slug})
    
    is_configurable = getattr(product, 'is_configurable', False)
    fixture_template = getattr(product, 'fixture_template', None)
    
    if not is_configurable or not fixture_template:
        return None
    
    return product


def _calculate_pricing_preview(template, selections: dict, tape_offering_id: str) -> dict:
    """Calculate pricing preview."""
    base_price = getattr(template, 'base_price_msrp', None) or 0
    price_per_ft = getattr(template, 'price_per_ft_msrp', None) or 0
    
    length_inches = float(selections.get("length_inches", 0))
    length_ft = length_inches / 12
    
    length_price = price_per_ft * length_ft
    total_msrp = base_price + length_price
    
    return {
        "base_price": float(base_price),
        "length_price": round(float(length_price), 2),
        "total_msrp": round(float(total_msrp), 2),
        "currency": "USD",
        "note": "Final quote provided upon order."
    }


def _build_configuration_summary(selections: dict) -> list:
    """Build human-readable configuration summary."""
    summary = []
    
    field_labels = {
        "environment_rating": "Environment",
        "cct": "Color Temperature",
        "output_level": "Output Level",
        "lens_appearance": "Lens",
        "mounting_method": "Mounting",
        "finish": "Finish",
        "length_inches": "Length",
        "start_feed_direction": "Start Feed Direction",
        "start_feed_length_ft": "Start Feed Length",
        "end_feed_direction": "End Feed Direction",
        "end_feed_length_ft": "End Feed Length"
    }
    
    for field, label in field_labels.items():
        value = selections.get(field)
        if value:
            display_value = value
            if field == "length_inches":
                display_value = f"{value} inches"
            elif field.endswith("_length_ft"):
                display_value = f"{value} ft"
            
            summary.append({"field": field, "label": label, "value": display_value})
    
    return summary


# =============================================================================
# CACHING FUNCTIONS
# =============================================================================

def _generate_cache_key(product_slug: str, step: str, selections: dict) -> str:
    """Generate cache key from product, step, and selections."""
    sorted_selections = json.dumps(selections, sort_keys=True)
    key_string = f"{product_slug}|{step}|{sorted_selections}"
    return hashlib.md5(key_string.encode()).hexdigest()


def _get_cached_options(cache_key: str) -> Optional[dict]:
    """Get cached options if valid."""
    cache_name = f"webflow-cfg-{cache_key}"
    if frappe.db.exists("ilL-Webflow-Configurator-Cache", cache_name):
        try:
            cache_doc = frappe.get_doc("ilL-Webflow-Configurator-Cache", cache_name)
            if cache_doc.is_valid and cache_doc.expires_at and cache_doc.expires_at > now_datetime():
                cache_doc.hit_count = (cache_doc.hit_count or 0) + 1
                cache_doc.last_accessed = now_datetime()
                cache_doc.save(ignore_permissions=True)
                frappe.db.commit()
                return json.loads(cache_doc.options_json)
        except Exception:
            pass
    return None


def _cache_options(cache_key: str, result: dict) -> None:
    """Cache options for future requests."""
    cache_name = f"webflow-cfg-{cache_key}"
    try:
        if frappe.db.exists("ilL-Webflow-Configurator-Cache", cache_name):
            cache_doc = frappe.get_doc("ilL-Webflow-Configurator-Cache", cache_name)
        else:
            cache_doc = frappe.new_doc("ilL-Webflow-Configurator-Cache")
            cache_doc.cache_key = cache_name
        
        cache_doc.product_slug = result.get("selections", {}).get("product_slug", "")
        cache_doc.step_name = result.get("step_completed", "")
        cache_doc.selections_json = json.dumps(result.get("selections", {}))
        cache_doc.options_json = json.dumps(result)
        cache_doc.is_valid = 1
        cache_doc.created_at = now_datetime()
        cache_doc.expires_at = add_to_date(now_datetime(), hours=CACHE_TTL_HOURS)
        cache_doc.last_accessed = now_datetime()
        cache_doc.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass  # Cache failures should not break API


def invalidate_cache_for_product(product_slug: str) -> int:
    """Invalidate all cache entries for a product."""
    count = frappe.db.sql("""
        UPDATE `tabilL-Webflow-Configurator-Cache`
        SET is_valid = 0
        WHERE product_slug = %s
    """, (product_slug,))
    frappe.db.commit()
    return count


def cleanup_expired_cache() -> int:
    """Clean up expired cache entries."""
    result = frappe.db.delete(
        "ilL-Webflow-Configurator-Cache",
        {"expires_at": ["<", now_datetime()]}
    )
    frappe.db.commit()
    return result
