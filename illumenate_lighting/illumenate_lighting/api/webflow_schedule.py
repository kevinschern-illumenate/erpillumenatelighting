# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Schedule Integration API

Provides endpoints for adding configured fixtures from the Webflow configurator
to project fixture schedules. Bridges the Webflow configurator selections to
the existing validate_and_quote API format.
"""

import frappe
import json
from frappe import _
from typing import Optional, Dict, Any
from frappe.utils import now_datetime


# =============================================================================
# PUBLIC API ENDPOINTS
# =============================================================================

@frappe.whitelist(allow_guest=False)
def add_to_schedule(
    schedule_id: str,
    configuration: str,
    quantity: int = 1,
    fixture_type_id: str = None,
    notes: str = None
) -> dict:
    """
    Add a configured fixture to a project schedule.
    
    Maps Webflow configurator selections to the existing
    validate_and_quote API format.
    
    Args:
        schedule_id: The fixture schedule ID
        configuration: JSON string of configurator selections
        quantity: Number of fixtures to add
        fixture_type_id: Optional fixture type ID (e.g., "A1")
        notes: Optional notes for the line item
    
    Returns:
        dict: Result with line_id or error
    """
    try:
        config = json.loads(configuration) if isinstance(configuration, str) else configuration
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid configuration JSON"}
    
    # Validate schedule access
    if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_id):
        return {"success": False, "error": "Schedule not found"}
    
    schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_id)
    if not schedule.has_permission("write"):
        return {"success": False, "error": "Permission denied"}
    
    # Get product and template
    product_slug = config.get("product_slug")
    if not product_slug:
        return {"success": False, "error": "Missing product_slug in configuration"}
    
    # First try to find a Webflow product
    template = None
    product = None
    if frappe.db.exists("ilL-Webflow-Product", {"product_slug": product_slug}):
        product = frappe.get_doc("ilL-Webflow-Product", {"product_slug": product_slug})
        if product.fixture_template:
            template = frappe.get_doc("ilL-Fixture-Template", product.fixture_template)
    
    # Fallback: treat product_slug as a fixture template code
    if not template and frappe.db.exists("ilL-Fixture-Template", product_slug):
        template = frappe.get_doc("ilL-Fixture-Template", product_slug)
    
    if not template:
        return {"success": False, "error": f"Product or template not found: {product_slug}"}
    
    # Resolve tape offering from selections
    from illumenate_lighting.illumenate_lighting.api.webflow_configurator import _resolve_tape_offering
    tape_offering_id = _resolve_tape_offering(template, config)
    
    if not tape_offering_id:
        return {"success": False, "error": "Could not resolve tape offering for this configuration"}
    
    # Convert length to mm
    length_inches = float(config.get("length_inches", 0))
    if length_inches <= 0:
        return {"success": False, "error": "Invalid length specified"}
    
    length_mm = int(length_inches * 25.4)
    
    # Map feed directions to power feed type
    start_feed_dir = config.get("start_feed_direction", "End")
    power_feed_type = _map_feed_direction_to_power_feed(start_feed_dir)
    
    # Get default endcap style and color
    default_endcap_style = _get_default_endcap_style(template)
    default_endcap_color = _get_default_endcap_color(template, finish_code=config.get("finish"))
    
    # Try to call existing configurator engine
    try:
        from illumenate_lighting.illumenate_lighting.api.configurator_engine import validate_and_quote
        
        engine_result = validate_and_quote(
            fixture_template_code=template.name,
            finish_code=config.get("finish"),
            lens_appearance_code=config.get("lens_appearance"),
            mounting_method_code=config.get("mounting_method"),
            endcap_style_start_code=default_endcap_style,
            endcap_style_end_code=default_endcap_style,
            endcap_color_code=default_endcap_color,
            power_feed_type_code=power_feed_type,
            environment_rating_code=config.get("environment_rating"),
            tape_offering_id=tape_offering_id,
            requested_overall_length_mm=length_mm,
            qty=quantity
        )
        
        if not engine_result.get("is_valid"):
            return {
                "success": False,
                "error": engine_result.get("message", "Configuration validation failed")
            }
        
        configured_fixture_id = engine_result.get("configured_fixture_id")
        
        if not configured_fixture_id:
            return {
                "success": False,
                "error": "Configuration engine did not create a fixture"
            }
        
    except ImportError:
        # Configurator engine not available - create fixture directly
        configured_fixture_id = _create_configured_fixture_directly(
            template, config, tape_offering_id, length_mm, quantity
        )
    except Exception as e:
        frappe.log_error(f"Error calling configurator engine: {str(e)}")
        return {"success": False, "error": f"Configuration error: {str(e)}"}
    
    # Generate part number
    from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
        _get_series_info, _generate_full_part_number
    )
    series_info = _get_series_info(template)
    part_number = _generate_full_part_number(series_info, config)
    
    # Get next fixture type ID if not provided
    if not fixture_type_id:
        fixture_type_id = _get_next_fixture_type_id(schedule)
    
    # Add line to schedule
    line = schedule.append("lines", {
        "line_id": fixture_type_id,
        "configured_fixture": configured_fixture_id,
        "qty": quantity,
        "manufacturer_type": "ILLUMENATE",
        "notes": notes or "",
        "ill_item_code": part_number,
    })
    
    schedule.save()
    frappe.db.commit()
    
    return {
        "success": True,
        "line_id": line.name,
        "fixture_type_id": fixture_type_id,
        "configured_fixture_id": configured_fixture_id,
        "part_number": part_number,
        "quantity": quantity,
        "schedule_id": schedule_id,
        "message": f"Added {quantity}x {part_number} to schedule"
    }


@frappe.whitelist(allow_guest=False)
def add_from_session(
    session_id: str,
    schedule_id: str,
    quantity: int = None
) -> dict:
    """
    Add a configured fixture from a Webflow session to a schedule.
    
    Used when user arrives at portal from Webflow configurator.
    
    Args:
        session_id: The Webflow session ID
        schedule_id: The fixture schedule ID
        quantity: Override quantity (defaults to session prefill)
    
    Returns:
        dict: Result with line_id or error
    """
    # Get session
    if not frappe.db.exists("ilL-Webflow-Session", session_id):
        return {"success": False, "error": "Session not found"}
    
    session = frappe.get_doc("ilL-Webflow-Session", session_id)
    
    if session.is_expired():
        return {"success": False, "error": "Session has expired"}
    
    # Get configuration from session
    config = session.get_configuration()
    config["product_slug"] = session.product_slug
    
    # Use session quantity if not overridden
    qty = quantity or session.prefill_quantity or 1
    fixture_type_id = session.prefill_fixture_type_id
    
    # Add to schedule
    result = add_to_schedule(
        schedule_id=schedule_id,
        configuration=json.dumps(config),
        quantity=qty,
        fixture_type_id=fixture_type_id,
        notes=f"Added from Webflow session {session_id}"
    )
    
    if result.get("success"):
        # Mark session as converted
        session.mark_converted(frappe.session.user)
        session.redirect_to_schedule = schedule_id
        session.save()
    
    return result


@frappe.whitelist(allow_guest=False)
def get_user_schedules() -> dict:
    """
    Get list of fixture schedules the current user can add fixtures to.
    
    Returns:
        dict: List of schedules with project info
    """
    user = frappe.session.user
    
    # Get schedules where user is owner or collaborator
    schedules = frappe.db.sql("""
        SELECT 
            s.name,
            s.schedule_name,
            s.project,
            p.project_name,
            s.status,
            s.creation
        FROM `tabilL-Project-Fixture-Schedule` s
        LEFT JOIN `tabilL-Project` p ON p.name = s.project
        WHERE (
            s.owner = %(user)s
            OR EXISTS (
                SELECT 1 FROM `tabilL-Child-Schedule-Collaborator` c
                WHERE c.parent = s.name AND c.user = %(user)s
            )
            OR EXISTS (
                SELECT 1 FROM `tabilL-Child-Project-Collaborator` pc
                WHERE pc.parent = s.project AND pc.user = %(user)s
            )
        )
        AND s.status IN ('Draft', 'In Progress')
        ORDER BY s.creation DESC
        LIMIT 50
    """, {"user": user}, as_dict=True)
    
    return {
        "success": True,
        "schedules": schedules,
        "count": len(schedules)
    }


@frappe.whitelist(allow_guest=False)
def create_quick_project_and_schedule(
    project_name: str,
    schedule_name: str = None
) -> dict:
    """
    Create a new project and schedule for quick add from Webflow.
    
    Args:
        project_name: Name for the new project
        schedule_name: Optional name for the schedule (defaults to "Main Schedule")
    
    Returns:
        dict: Created project and schedule IDs
    """
    try:
        # Create project
        project = frappe.new_doc("ilL-Project")
        project.project_name = project_name
        project.owner = frappe.session.user
        project.status = "Draft"
        project.insert()
        
        # Create schedule
        schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
        schedule.project = project.name
        schedule.schedule_name = schedule_name or "Main Schedule"
        schedule.status = "Draft"
        schedule.insert()
        
        frappe.db.commit()
        
        return {
            "success": True,
            "project_id": project.name,
            "project_name": project.project_name,
            "schedule_id": schedule.name,
            "schedule_name": schedule.schedule_name,
            "message": f"Created project '{project_name}' with schedule"
        }
    
    except Exception as e:
        frappe.db.rollback()
        return {"success": False, "error": str(e)}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _map_feed_direction_to_power_feed(direction: str) -> str:
    """
    Map feed direction from configurator to power feed type code.
    
    Args:
        direction: Feed direction ("End", "Back", "Left", or "Right")
    
    Returns:
        str: Power feed type code
    """
    # Try to find matching power feed type
    if frappe.db.exists("DocType", "ilL-Attribute-Power Feed Type"):
        # Map based on direction
        mapping = {
            "End": ["End Feed", "End", "E"],
            "Back": ["Back Feed", "Back", "B", "Center"],
            "Left": ["Left Feed", "Left", "L"],
            "Right": ["Right Feed", "Right", "R"]
        }
        
        for code in mapping.get(direction, [direction]):
            if frappe.db.exists("ilL-Attribute-Power Feed Type", code):
                return code
    
    # Fallback - return the direction as-is
    return direction


def _get_default_endcap_style(template) -> Optional[str]:
    """Get default endcap style from template options."""
    for opt in getattr(template, 'allowed_options', []) or []:
        if (getattr(opt, 'option_type', None) == "Endcap Style" and 
            getattr(opt, 'is_default', False) and 
            getattr(opt, 'is_active', True)):
            return getattr(opt, 'endcap_style', None)
    
    # Return first active endcap style
    for opt in getattr(template, 'allowed_options', []) or []:
        if (getattr(opt, 'option_type', None) == "Endcap Style" and 
            getattr(opt, 'is_active', True)):
            return getattr(opt, 'endcap_style', None)
    
    return None


def _get_default_endcap_color(template, finish_code: str = None) -> Optional[str]:
    """Get default endcap color, resolved from finish via ilL-Rel-Finish Endcap Color."""
    # Primary: resolve from finish via ilL-Rel-Finish Endcap Color
    if finish_code:
        finish_endcap = frappe.db.get_value(
            "ilL-Rel-Finish Endcap Color",
            {"finish": finish_code, "is_active": 1},
            "endcap_color",
            order_by="is_default DESC, modified DESC",
        )
        if finish_endcap:
            return finish_endcap

    # Fallback: try template allowed options
    for opt in getattr(template, 'allowed_options', []) or []:
        if (getattr(opt, 'option_type', None) == "Endcap Color" and 
            getattr(opt, 'is_default', False) and 
            getattr(opt, 'is_active', True)):
            return getattr(opt, 'endcap_color', None)
    
    # Return first active endcap color
    for opt in getattr(template, 'allowed_options', []) or []:
        if (getattr(opt, 'option_type', None) == "Endcap Color" and 
            getattr(opt, 'is_active', True)):
            return getattr(opt, 'endcap_color', None)
    
    return None


def _get_next_fixture_type_id(schedule) -> str:
    """
    Get the next fixture type ID for a schedule.
    
    Follows pattern: A1, A2, A3... B1, B2, B3...
    """
    existing_ids = set()
    
    for line in getattr(schedule, 'lines', []) or []:
        if getattr(line, 'line_id', None):
            existing_ids.add(line.line_id)
    
    # Generate next ID
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for num in range(1, 100):
            type_id = f"{letter}{num}"
            if type_id not in existing_ids:
                return type_id
    
    # Fallback
    return f"X{len(existing_ids) + 1}"


def _create_configured_fixture_directly(
    template,
    config: dict,
    tape_offering_id: str,
    length_mm: int,
    quantity: int
) -> str:
    """
    Create a configured fixture document directly.
    
    Used when the configurator engine is not available.
    
    Args:
        template: The fixture template document
        config: The configuration selections
        tape_offering_id: The resolved tape offering ID
        length_mm: Length in millimeters
        quantity: Quantity
    
    Returns:
        str: The configured fixture ID
    """
    fixture = frappe.new_doc("ilL-Configured-Fixture")
    
    fixture.fixture_template = template.name
    fixture.tape_offering = tape_offering_id
    fixture.overall_length_mm = length_mm
    fixture.quantity = quantity
    
    # Set options from config
    fixture.finish = config.get("finish")
    fixture.lens_appearance = config.get("lens_appearance")
    fixture.mounting_method = config.get("mounting_method")
    fixture.environment_rating = config.get("environment_rating")
    
    # Store raw configuration
    fixture.configuration_json = json.dumps(config)
    fixture.source = "Webflow Configurator"
    
    fixture.insert()
    
    return fixture.name


@frappe.whitelist(allow_guest=False)
def update_line_quantity(
    line_name: str,
    new_quantity: int
) -> dict:
    """
    Update the quantity for a fixture schedule line.
    
    Args:
        line_name: The line item name
        new_quantity: The new quantity
    
    Returns:
        dict: Update result
    """
    if new_quantity < 1:
        return {"success": False, "error": "Quantity must be at least 1"}
    
    # Find the line and its parent schedule
    line = frappe.db.get_value(
        "ilL-Child-Fixture-Schedule-Line",
        line_name,
        ["parent", "quantity"],
        as_dict=True
    )
    
    if not line:
        return {"success": False, "error": "Line not found"}
    
    schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", line.parent)
    
    if not schedule.has_permission("write"):
        return {"success": False, "error": "Permission denied"}
    
    # Update quantity
    frappe.db.set_value(
        "ilL-Child-Fixture-Schedule-Line",
        line_name,
        "quantity",
        new_quantity
    )
    
    frappe.db.commit()
    
    return {
        "success": True,
        "line_name": line_name,
        "old_quantity": line.quantity,
        "new_quantity": new_quantity
    }


@frappe.whitelist(allow_guest=False)
def remove_line(line_name: str) -> dict:
    """
    Remove a fixture schedule line.
    
    Args:
        line_name: The line item name
    
    Returns:
        dict: Removal result
    """
    # Find the line and its parent schedule
    line = frappe.db.get_value(
        "ilL-Child-Fixture-Schedule-Line",
        line_name,
        ["parent"],
        as_dict=True
    )
    
    if not line:
        return {"success": False, "error": "Line not found"}
    
    schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", line.parent)
    
    if not schedule.has_permission("write"):
        return {"success": False, "error": "Permission denied"}
    
    # Remove line
    schedule.lines = [
        l for l in schedule.lines if l.name != line_name
    ]
    schedule.save()
    frappe.db.commit()
    
    return {
        "success": True,
        "line_name": line_name,
        "message": "Line removed successfully"
    }
