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
        # Update Output options (filtered by environment + CCT + lens)
        lens = selections_dict.get("lens_appearance")
        result["updated_options"]["output_levels"] = _get_output_levels_with_transmission(
            template, env, cct, lens
        )
        result["clear_selections"] = ["output_level"]
    
    elif step_name == "lens_appearance":
        # When lens changes, recalculate output levels with new transmission
        lens = selections_dict.get("lens_appearance")
        if env and cct:
            result["updated_options"]["output_levels"] = _get_output_levels_with_transmission(
                template, env, cct, lens
            )
            # Clear output selection since delivered values changed
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
def download_spec_sheet(
    product_slug: str,
    selections: str,
    project_name: str = "",
    project_location: str = "",
) -> dict:
    """
    Generate and return a spec sheet PDF from configurator selections.

    Called from the Webflow product page when a user clicks "Download Spec Sheet"
    after completing (or partially completing) the part number configurator.

    Uses the existing validate_and_quote → generate_filled_submittal pipeline
    so the output matches the spec submittals used on fixture schedules.

    Args:
        product_slug: The Webflow product slug (or fixture template code)
        selections: JSON string of configurator selections
        project_name: Optional project name to display on the sheet
        project_location: Optional project location to display on the sheet

    Returns:
        dict: {success, file_url, filename, part_number} or {success, error}
    """
    try:
        selections_dict = json.loads(selections) if isinstance(selections, str) else selections
    except (json.JSONDecodeError, TypeError):
        return {"success": False, "error": "Invalid selections JSON"}

    from illumenate_lighting.illumenate_lighting.api.spec_sheet_generator import (
        generate_from_webflow_selections,
    )

    return generate_from_webflow_selections(
        product_slug=product_slug,
        selections=selections_dict,
        project_name=project_name,
        project_location=project_location,
    )


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
            ["name", "code", "spectrum_type"],
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
# MULTI-CCT (TUNABLE WHITE) HELPERS
# =============================================================================

# Spectrum types where the tape offering carries a generic CCT (e.g. "Tunable White")
# but the LED Package's compatible_ccts lists the individual CCTs users can choose.
_MULTI_CCT_SPECTRUM_TYPES = {"Tunable White", "Dim to Warm", "RGB+TW", "RGBTW", "RGB+W", "RGBW"}


def _is_multi_cct_template(template) -> bool:
    """Check if any LED package on this template's tapes is a multi-CCT type."""
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if tape_offering:
            led_pkg = frappe.db.get_value("ilL-Rel-Tape Offering", tape_offering, "led_package")
            if led_pkg:
                spectrum_type = frappe.db.get_value("ilL-Attribute-LED Package", led_pkg, "spectrum_type") or ""
                if spectrum_type in _MULTI_CCT_SPECTRUM_TYPES:
                    return True
    return False


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
    """Get CCTs available for the selected environment.
    
    For multi-CCT LED packages (Tunable White, Dim to Warm, etc.), returns the
    individual CCTs from the LED Package's compatible_ccts table rather than the
    tape offering's generic CCT (e.g. "Tunable White").
    """
    MULTI_CCT_SPECTRUM_TYPES = {"Tunable White", "Dim to Warm", "RGB+TW", "RGBTW", "RGB+W", "RGBW"}
    
    # ── Determine LED packages and check for multi-CCT spectrum types ──
    led_packages_on_env = set()
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if not _env_matches(tape_row, environment):
            continue
        tape_offering = getattr(tape_row, 'tape_offering', None)
        if tape_offering:
            pkg = frappe.db.get_value("ilL-Rel-Tape Offering", tape_offering, "led_package")
            if pkg:
                led_packages_on_env.add(pkg)
    
    # Check if any LED package is multi-CCT
    multi_cct_ccts = []
    for pkg_name in led_packages_on_env:
        pkg_data = frappe.db.get_value(
            "ilL-Attribute-LED Package", pkg_name,
            ["name", "spectrum_type"], as_dict=True
        )
        if pkg_data and (pkg_data.get("spectrum_type") or "") in MULTI_CCT_SPECTRUM_TYPES:
            # Get individual CCTs from LED Package's compatible_ccts table
            pkg_doc = frappe.get_doc("ilL-Attribute-LED Package", pkg_name)
            for row in pkg_doc.get("compatible_ccts", []):
                if row.cct:
                    cct_data = frappe.db.get_value(
                        "ilL-Attribute-CCT", row.cct,
                        ["name", "code", "kelvin", "description"], as_dict=True
                    )
                    if cct_data:
                        multi_cct_ccts.append({
                            "value": cct_data.name,
                            "label": cct_data.name,
                            "code": cct_data.get("code"),
                            "kelvin": cct_data.get("kelvin"),
                            "description": cct_data.get("description")
                        })
    
    if multi_cct_ccts:
        # Deduplicate by value
        seen = set()
        unique = []
        for c in multi_cct_ccts:
            if c["value"] not in seen:
                seen.add(c["value"])
                unique.append(c)
        return sorted(unique, key=lambda x: x.get("kelvin") or 0)
    
    # ── Standard flow: get CCTs directly from tape offerings ──
    ccts = set()
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if not _env_matches(tape_row, environment):
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
    """Get output levels available for the selected environment + CCT.
    
    For multi-CCT packages (Tunable White, etc.), the tape's CCT won't match
    the user-selected individual CCT, so we skip the CCT filter.
    """
    is_multi_cct = _is_multi_cct_template(template)
    output_levels = set()
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if not _env_matches(tape_row, environment):
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
        
        # For multi-CCT packages, skip the exact CCT check on tape offerings
        cct_matches = is_multi_cct or (offering_data and offering_data.get("cct") == cct)
        if offering_data and cct_matches and offering_data.get("output_level"):
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


def _get_output_levels_with_transmission(template, environment: str, cct: str, lens_appearance: Optional[str] = None) -> list:
    """
    Get output levels as delivered lumens (tape output × lens transmission).
    
    This calculates the actual fixture output (delivered lumens) by:
    1. Finding compatible tapes for environment + CCT
    2. Getting lens transmission (decimal, e.g., 0.56 = 56%)
    3. Calculating delivered output = tape output × transmission
    4. Matching to fixture-level output levels
    
    For multi-CCT packages (Tunable White, etc.), the tape's CCT won't match
    the user-selected individual CCT, so we skip the CCT filter.
    
    Args:
        template: The fixture template document
        environment: Selected environment rating name
        cct: Selected CCT name
        lens_appearance: Selected lens appearance name (optional)
    
    Returns:
        list: Output options with delivered lumen values
    """
    # Get lens transmission as decimal (stored as 0.56 = 56%)
    lens_transmission = 1.0  # Default to 100% if no lens selected
    if lens_appearance:
        transmission = frappe.db.get_value(
            "ilL-Attribute-Lens Appearance", lens_appearance, "transmission"
        )
        if transmission:
            lens_transmission = float(transmission)
    
    # Get fixture-level output levels for matching
    fixture_output_levels = frappe.get_all(
        "ilL-Attribute-Output Level",
        filters={"is_fixture_level": 1},
        fields=["name", "value", "sku_code"],
        order_by="value asc"
    )
    
    # Get compatible tape offerings and their output levels
    is_multi_cct = _is_multi_cct_template(template)
    tape_output_data = {}  # output_level_name -> tape_output_value
    
    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if not _env_matches(tape_row, environment):
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
        
        # For multi-CCT packages, skip the exact CCT check on tape offerings
        cct_matches = is_multi_cct or (offering_data and offering_data.get("cct") == cct)
        if offering_data and cct_matches and offering_data.get("output_level"):
            output_level_name = offering_data.get("output_level")
            if output_level_name not in tape_output_data:
                # Get the tape's output level value
                level_data = frappe.db.get_value(
                    "ilL-Attribute-Output Level",
                    output_level_name,
                    ["name", "value", "sku_code"],
                    as_dict=True
                )
                if level_data:
                    tape_output_data[output_level_name] = level_data
    
    if not tape_output_data:
        return []
    
    # Calculate delivered outputs and match to fixture-level output levels
    result = []
    seen_fixture_levels = set()  # Avoid duplicates if multiple tapes map to same fixture level
    
    for output_level_name, level_data in tape_output_data.items():
        tape_output_value = level_data.get("value") or 0
        # Calculate delivered lumens: tape output × transmission (decimal)
        delivered_lm_ft = tape_output_value * lens_transmission
        
        # If fixture-level output levels exist, find closest match
        if fixture_output_levels:
            closest = min(fixture_output_levels, key=lambda x: abs((x.value or 0) - delivered_lm_ft))
            if closest.name not in seen_fixture_levels:
                seen_fixture_levels.add(closest.name)
                result.append({
                    "value": output_level_name,  # Original tape output level for tape selection
                    "label": f"{closest.value} lm/ft",  # Displayed as delivered (fixture) output
                    "numeric_value": closest.value,
                    "sku_code": closest.sku_code or level_data.get("sku_code"),
                    "tape_output_lm_ft": tape_output_value,
                    "delivered_lm_ft": closest.value,
                    "transmission_pct": round(lens_transmission * 100, 1)
                })
        else:
            # No fixture levels defined, use raw delivered output
            delivered_rounded = int(round(delivered_lm_ft))
            result.append({
                "value": output_level_name,
                "label": f"{delivered_rounded} lm/ft",
                "numeric_value": delivered_rounded,
                "sku_code": level_data.get("sku_code"),
                "tape_output_lm_ft": tape_output_value,
                "delivered_lm_ft": delivered_rounded,
                "transmission_pct": round(lens_transmission * 100, 1)
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
                # Transmission is stored as decimal (0.56 = 56%), convert to percentage for display
                transmission_decimal = lens.get("transmission")
                if transmission_decimal:
                    transmission_pct = transmission_decimal * 100
                else:
                    transmission_pct = 100  # Default to 100% if not set
                
                label = f"{lens.name}"
                if transmission_pct < 100:
                    label += f" - {transmission_pct:.0f}% transmission"
                
                result.append({
                    "value": lens.name,
                    "label": label,
                    "short_label": lens.name,
                    "code": lens.get("code"),
                    "transmission_pct": transmission_pct,
                    "transmission_decimal": transmission_decimal or 1.0,
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
        {"value": "Back", "label": "Back", "code": "B"},
        {"value": "Left", "label": "Left", "code": "L"},
        {"value": "Right", "label": "Right", "code": "R"},
        {"value": "Endcap", "label": "Endcap", "code": "CAP"}
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
        # Get tape output level data
        tape_output_data = frappe.db.get_value(
            "ilL-Attribute-Output Level",
            selections["output_level"],
            ["value", "sku_code"],
            as_dict=True
        )
        tape_output_value = (tape_output_data.get("value") if tape_output_data else 0) or 0
        tape_output_sku = (tape_output_data.get("sku_code") if tape_output_data else None)
        
        # Get lens transmission as decimal (0.56 = 56%)
        lens_transmission = frappe.db.get_value(
            "ilL-Attribute-Lens Appearance",
            selections["lens_appearance"],
            "transmission"
        ) or 1.0
        
        # Calculate fixture output = tape output × transmission (decimal)
        fixture_output_value = int(round(tape_output_value * lens_transmission))
        
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
        elif tape_output_sku:
            # Fallback: no fixture-level outputs defined, use tape output sku_code
            output_code = tape_output_sku
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
    
    if selections.get("end_feed_direction"):
        if selections["end_feed_direction"] == "Endcap":
            suffix_parts.append("CAP")
        elif selections.get("end_feed_length_ft"):
            end_dir_code = _get_feed_direction_code(selections["end_feed_direction"])
            suffix_parts.append(f"{end_dir_code}{selections['end_feed_length_ft']}")
    
    if suffix_parts:
        main_pn += "-" + "-".join(suffix_parts)
    
    # Calculate completion percentage
    selectable_segments = [s for s in segments if not s.get("locked")]
    end_feed_complete = (
        selections.get("end_feed_direction") == "Endcap"
        or (selections.get("end_feed_direction") and selections.get("end_feed_length_ft"))
    )
    feed_selected = all([
        selections.get("start_feed_direction"),
        selections.get("start_feed_length_ft"),
        end_feed_complete
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
    direction_codes = {"End": "E", "Back": "B", "Left": "L", "Right": "R", "Endcap": "CAP"}
    return direction_codes.get(direction, "X")


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _validate_option_compatibility(template, selections: dict) -> dict:
    """Validate that a tape offering exists for the selected combination.

    Uses the same lens-transmission-aware logic as ``_resolve_tape_offering``
    so that the user's selected output (delivered fixture output) is compared
    against tape_output × lens_transmission rather than the raw tape output.
    """
    # If _resolve_tape_offering can find a tape, the combination is valid.
    tape = _resolve_tape_offering(template, selections)
    if tape:
        return {"is_valid": True}

    return {
        "is_valid": False,
        "message": "No tape offering available for this combination. Please adjust your selections."
    }


def _resolve_tape_offering(template, selections: dict) -> Optional[str]:
    """Find the tape offering ID that delivers the user's selected output level.

    The user's selected output (e.g. "100 lm/ft") represents the **delivered
    fixture output**, not the raw tape output.  The delivered output is::

        delivered_lm_ft = tape_output_lm_ft × lens_transmission

    This function therefore:
    1. Gets the lens transmission factor from the selected lens appearance.
    2. Iterates through allowed tape offerings, filtering by environment and CCT.
    3. For each tape, calculates the delivered output with the lens applied.
    4. Finds the closest fixture-level output level.
    5. Checks whether that fixture-level output matches the user's selection.

    For multi-CCT packages (Tunable White, etc.), skips the exact CCT match
    since the tape carries a generic CCT while the user selects individual CCTs.

    Uses flexible matching for environment rating to handle Webflow page radio
    values that may be display labels/codes rather than exact ERPNext names.
    """
    environment = selections.get("environment_rating")
    env_code = selections.get("environment_rating_code")
    cct = selections.get("cct")
    output_level = selections.get("output_level")
    output_level_code = selections.get("output_level_code")
    lens_appearance = selections.get("lens_appearance")
    lens_appearance_code = selections.get("lens_appearance_code")
    is_multi_cct = _is_multi_cct_template(template)

    # ── Resolve lens transmission ─────────────────────────────────────
    lens_transmission = 1.0  # Default to 100% (clear lens / no lens)
    lens_name = lens_appearance or lens_appearance_code
    if lens_name:
        # Try the raw value first (could be a document name)
        transmission = frappe.db.get_value(
            "ilL-Attribute-Lens Appearance", lens_name, "transmission"
        )
        if transmission is None and lens_appearance_code:
            # Fallback: look up by code field
            lens_doc_name = frappe.db.get_value(
                "ilL-Attribute-Lens Appearance", {"code": lens_appearance_code}, "name"
            )
            if lens_doc_name:
                transmission = frappe.db.get_value(
                    "ilL-Attribute-Lens Appearance", lens_doc_name, "transmission"
                )
        if transmission is not None:
            lens_transmission = float(transmission)

    # ── Parse the user's desired delivered output value ────────────────
    desired_output_value = _parse_output_value(output_level, output_level_code)

    # ── Fetch fixture-level output levels for closest-match logic ─────
    fixture_output_levels = frappe.get_all(
        "ilL-Attribute-Output Level",
        filters={"is_fixture_level": 1},
        fields=["name", "value", "sku_code", "output_level_name"],
        order_by="value asc",
    )

    frappe.logger().info(
        f"_resolve_tape_offering: env={environment!r}, env_code={env_code!r}, "
        f"cct={cct!r}, output={output_level!r}, output_code={output_level_code!r}, "
        f"desired_value={desired_output_value}, lens_transmission={lens_transmission}, "
        f"is_multi_cct={is_multi_cct}"
    )

    best_match = None
    best_diff = float("inf")

    for tape_row in getattr(template, 'allowed_tape_offerings', []) or []:
        if not getattr(tape_row, 'is_active', True):
            continue
        if not _env_matches(tape_row, environment, env_code):
            continue

        tape_offering = getattr(tape_row, 'tape_offering', None)
        if not tape_offering:
            continue

        offering_data = frappe.db.get_value(
            "ilL-Rel-Tape Offering",
            tape_offering,
            ["cct", "output_level"],
            as_dict=True,
        )
        if not offering_data:
            continue

        cct_matches = is_multi_cct or (offering_data.get("cct") == cct)
        if not cct_matches:
            frappe.logger().debug(
                f"_resolve_tape_offering: skipped {tape_offering} (cct mismatch)"
            )
            continue

        tape_output_level = offering_data.get("output_level")
        if not tape_output_level:
            continue

        # Get the tape's raw output value (lm/ft)
        tape_ol_data = frappe.db.get_value(
            "ilL-Attribute-Output Level",
            tape_output_level,
            ["value", "sku_code"],
            as_dict=True,
        )
        if not tape_ol_data or not tape_ol_data.value:
            continue

        tape_output_lm_ft = float(tape_ol_data.value)
        # Calculate delivered lumens: tape output × lens transmission
        delivered_lm_ft = tape_output_lm_ft * lens_transmission

        # Find closest fixture-level output level
        if fixture_output_levels:
            closest = min(
                fixture_output_levels,
                key=lambda x: abs((x.value or 0) - delivered_lm_ft),
            )
            delivered_fixture_value = closest.value
        else:
            delivered_fixture_value = int(round(delivered_lm_ft))

        frappe.logger().debug(
            f"_resolve_tape_offering: tape={tape_offering}, "
            f"tape_output={tape_output_lm_ft}, delivered={delivered_lm_ft:.1f}, "
            f"closest_fixture={delivered_fixture_value}"
        )

        # Check if this tape's delivered output matches the user's selection
        matches = False
        if desired_output_value is not None:
            # Numeric comparison against the fixture output level value
            if delivered_fixture_value == desired_output_value:
                matches = True
        else:
            # Fallback: try direct name/label matching against the fixture
            # output level (for cases where we couldn't parse a number)
            if fixture_output_levels:
                if _output_level_matches(closest.name, output_level, output_level_code):
                    matches = True
            else:
                if _output_level_matches(tape_output_level, output_level, output_level_code):
                    matches = True

        if matches:
            diff = abs(delivered_lm_ft - delivered_fixture_value)
            if diff < best_diff:
                best_diff = diff
                best_match = tape_offering

    if best_match:
        frappe.logger().info(
            f"_resolve_tape_offering: matched tape_offering={best_match}"
        )
        return best_match

    frappe.logger().warning(
        f"_resolve_tape_offering: no tape found for template={template.name}, "
        f"env={environment!r}, output={output_level!r}, "
        f"lens_transmission={lens_transmission}"
    )
    return None


def _parse_output_value(output_level: str | None, output_level_code: str | None) -> int | None:
    """Extract the numeric output value (lm/ft) from user selections.

    Tries (in order):
    1. Parse number from the output_level string (e.g. "100 lm/ft" → 100)
    2. Parse output_level_code as int (e.g. "100" → 100)
    3. Look up the fixture-level output level by name or code
    Returns None if nothing works.
    """
    # Try parsing from the label string
    if output_level:
        import re
        m = re.search(r"(\d+(?:\.\d+)?)", output_level.replace(",", ""))
        if m:
            return int(float(m.group(1)))
        # Maybe it's a document name
        val = frappe.db.get_value("ilL-Attribute-Output Level", output_level, "value")
        if val is not None:
            return int(float(val))

    if output_level_code:
        try:
            return int(float(output_level_code))
        except (ValueError, TypeError):
            pass
        # Try looking up by sku_code
        val = frappe.db.get_value(
            "ilL-Attribute-Output Level",
            {"sku_code": output_level_code, "is_fixture_level": 1},
            "value",
        )
        if val is not None:
            return int(float(val))

    return None


def _env_matches(tape_row, environment: str, env_code: str = None) -> bool:
    """Check if a template's allowed tape offering row matches the environment selection.
    
    Matching rules:
    1. If the child row has no environment_rating set → matches any (wildcard)
    2. Exact name match
    3. Match by environment rating code
    """
    row_env = getattr(tape_row, 'environment_rating', None)
    
    # If the child row has no env set, treat as wildcard (matches any)
    if not row_env:
        return True
    
    # No selection → only match if row also has no env (handled above)
    if not environment:
        return False
    
    # Direct name match
    if row_env == environment:
        return True
    
    # Match by code: compare the row's env rating code with the selection code
    if env_code:
        row_env_code = frappe.db.get_value(
            "ilL-Attribute-Environment Rating", row_env, "code"
        )
        if row_env_code and row_env_code == env_code:
            return True
    
    return False


def _output_level_matches(tape_output_level: str, selected_output: str, selected_code: str = None) -> bool:
    """Check if a tape offering's output level matches the user selection.
    
    Matching rules:
    1. Exact document name match
    2. Match by sku_code (e.g., "100" matches Output Level with sku_code "100")
    3. Match by label format: tape's "{value} lm/ft" vs selected_output
    
    This handles Webflow pages that may send display labels or codes
    instead of exact ERPNext document names.
    """
    if not tape_output_level:
        return False
    
    if not selected_output and not selected_code:
        return False
    
    # 1. Direct name match
    if selected_output and tape_output_level == selected_output:
        return True
    
    # Fetch the output level details for further matching
    ol_data = frappe.db.get_value(
        "ilL-Attribute-Output Level",
        tape_output_level,
        ["value", "sku_code", "output_level_name"],
        as_dict=True
    )
    if not ol_data:
        return False
    
    # 2. Match by sku_code (e.g., selection sends code "100")
    if selected_code and ol_data.sku_code:
        if ol_data.sku_code == selected_code:
            return True
    
    # 3. Match by label format: "{value} lm/ft"
    if selected_output and ol_data.value is not None:
        label = f"{ol_data.value} lm/ft"
        if label == selected_output:
            return True
        # Also try just the numeric part: "100" vs "100"
        try:
            selected_numeric = selected_output.replace(" lm/ft", "").strip()
            if selected_numeric == str(ol_data.value):
                return True
        except (ValueError, AttributeError):
            pass
    
    # 4. Match raw value against output_level_name
    if selected_output and ol_data.output_level_name:
        if ol_data.output_level_name == selected_output:
            return True
    
    return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_configurable_product(product_slug: str):
    """
    Get a configurable Webflow product by slug, or create a virtual product
    from a fixture template code if no product exists.
    
    This allows the configurator to work with:
    1. Webflow products (product_slug matches ilL-Webflow-Product.product_slug)
    2. Direct template codes (product_slug matches ilL-Fixture-Template.name)
    """
    # First, try to find a Webflow product
    if frappe.db.exists("ilL-Webflow-Product", {"product_slug": product_slug}):
        product = frappe.get_doc("ilL-Webflow-Product", {"product_slug": product_slug})
        
        is_configurable = getattr(product, 'is_configurable', False)
        fixture_template = getattr(product, 'fixture_template', None)
        
        if is_configurable and fixture_template:
            return product
    
    # Fallback: treat product_slug as a fixture template code
    if frappe.db.exists("ilL-Fixture-Template", product_slug):
        template = frappe.get_doc("ilL-Fixture-Template", product_slug)
        
        # Create a virtual product-like object for compatibility
        class VirtualProduct:
            pass
        
        virtual = VirtualProduct()
        virtual.product_slug = product_slug
        virtual.product_name = template.template_name
        virtual.fixture_template = template.name
        virtual.is_configurable = True
        virtual.min_length_mm = getattr(template, 'min_length_mm', None)
        virtual.max_length_mm = getattr(template, 'max_length_mm', None)
        
        return virtual
    
    return None


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
