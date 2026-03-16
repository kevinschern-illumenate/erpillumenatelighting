# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Spec Sheet Generator for Webflow Product Pages

Generates a pre-configured spec sheet (filled PDF submittal) from Webflow
configurator selections, without requiring a project or fixture schedule.

Flow:
1. Webflow user completes configurator selections on product page
2. User clicks "Download Spec Sheet" button
3. This module receives selections, runs them through validate_and_quote
   to create a Configured Fixture, then generates a filled spec submittal PDF
4. Returns a guest-accessible PDF download URL

Reuses existing infrastructure:
- webflow_configurator._resolve_tape_offering() for tape selection
- configurator_engine.validate_and_quote() for fixture creation
- spec_submittal.generate_filled_submittal() for PDF generation
"""

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime


def generate_from_webflow_selections(
    product_slug: str,
    selections: dict,
    project_name: str = "",
    project_location: str = "",
    fixture_type: str = "",
) -> dict:
    """
    Generate a spec sheet PDF from Webflow configurator selections.

    This orchestrates the full pipeline:
    1. Resolve product → fixture template
    2. Map Webflow selections to configurator engine parameters
    3. Run validate_and_quote to create a Configured Fixture
    4. Generate filled spec submittal PDF from that fixture
    5. Make the PDF publicly accessible and return the URL

    Args:
        product_slug: Webflow product slug or fixture template code
        selections: Dict of configurator selections (environment_rating, cct,
                    output_level, lens_appearance, mounting_method, finish,
                    length_inches, start_feed_direction, etc.)
        project_name: Optional project name for the spec sheet header
        project_location: Optional project location for the spec sheet header
        fixture_type: Optional fixture type for the spec sheet header

    Returns:
        dict: {success, file_url, filename, part_number} or {success, error}
    """
    from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
        _get_configurable_product,
        _get_series_info,
        _resolve_tape_offering,
        _generate_full_part_number,
    )

    # ── Step 1: Resolve product and template ──────────────────────────
    product = _get_configurable_product(product_slug)
    if not product:
        return {"success": False, "error": "Product not found or not configurable"}

    template = frappe.get_doc("ilL-Fixture-Template", product.fixture_template)
    series_info = _get_series_info(template)

    # ── Step 2: Resolve tape offering from selections ─────────────────
    tape_offering_id = _resolve_tape_offering(template, selections)
    if not tape_offering_id:
        frappe.log_error(
            title="Spec Sheet - No Tape Offering Found",
            message=(
                f"_resolve_tape_offering returned None for "
                f"template={product.fixture_template}, "
                f"selections={selections!r}"
            ),
        )
        return {
            "success": False,
            "error": (
                "No tape offering matches your configuration. "
                f"Environment={selections.get('environment_rating')!r}, "
                f"Output={selections.get('output_level')!r}. "
                "Please check your selections."
            ),
        }

    # ── Step 3: Map Webflow selections → engine codes ─────────────────
    engine_params = _map_selections_to_engine_codes(
        template, selections, tape_offering_id
    )
    if engine_params.get("error"):
        return {"success": False, "error": engine_params["error"]}

    # ── Step 4: Run validate_and_quote to create Configured Fixture ───
    from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
        validate_and_quote,
    )

    quote_result = validate_and_quote(
        fixture_template_code=product.fixture_template,
        finish_code=engine_params["finish_code"],
        lens_appearance_code=engine_params["lens_appearance_code"],
        mounting_method_code=engine_params["mounting_method_code"],
        endcap_style_start_code=engine_params["endcap_style_start_code"],
        endcap_style_end_code=engine_params["endcap_style_end_code"],
        endcap_color_code=engine_params["endcap_color_code"],
        power_feed_type_code=engine_params["power_feed_type_code"],
        environment_rating_code=engine_params["environment_rating_code"],
        tape_offering_id=tape_offering_id,
        requested_overall_length_mm=engine_params["requested_overall_length_mm"],
        start_feed_direction_code=engine_params.get("start_feed_direction_code"),
        end_feed_direction_code=engine_params.get("end_feed_direction_code", "C"),
        start_leader_len_mm=engine_params.get("start_leader_len_mm", 0),
        end_leader_len_mm=engine_params.get("end_leader_len_mm", 0),
    )

    if not quote_result.get("is_valid"):
        error_msgs = [
            m["text"]
            for m in quote_result.get("messages", [])
            if m.get("severity") == "error"
        ]
        return {
            "success": False,
            "error": "; ".join(error_msgs) if error_msgs else "Configuration is invalid",
        }

    configured_fixture_id = quote_result.get("configured_fixture_id")
    if not configured_fixture_id:
        return {
            "success": False,
            "error": "Could not create configured fixture for this configuration",
        }

    # ── Step 5: Generate the filled spec submittal PDF ────────────────
    from illumenate_lighting.illumenate_lighting.api.spec_submittal import (
        generate_filled_submittal,
    )

    # Check whether a fillable submittal template is configured.
    # Only fall back to the static spec sheet when there is genuinely
    # no submittal template *and* no field mappings — i.e. the series
    # was never set up for filled submittals.
    has_submittal_template = bool(
        getattr(template, "spec_submittal_template", None)
    )
    has_field_mappings = bool(
        frappe.db.count(
            "ilL-Spec-Submittal-Mapping",
            filters={"fixture_template": template.name},
        )
    )

    if not has_submittal_template and not has_field_mappings:
        # No submittal infrastructure configured — return static spec
        # sheet if available.
        spec_sheet_url = (
            template.spec_sheet if hasattr(template, "spec_sheet") else None
        )
        if spec_sheet_url:
            part_number = _generate_full_part_number(series_info, selections)
            return {
                "success": True,
                "file_url": spec_sheet_url,
                "filename": f"Spec_Sheet_{part_number}.pdf",
                "part_number": part_number,
                "note": "Static spec sheet returned (no fillable template configured for this series)",
            }
        return {
            "success": False,
            "error": "No spec submittal template or spec sheet configured for this series",
        }

    # Build webflow overrides dict for fields that have webflow_field mappings
    webflow_overrides = {}
    if project_name:
        webflow_overrides["project_name"] = project_name
    if fixture_type:
        webflow_overrides["fixture_type"] = fixture_type
    if project_location:
        webflow_overrides["project_location"] = project_location

    # Forward feed-length selections so they can be mapped onto the PDF
    # via ilL-Spec-Submittal-Mapping rows whose webflow_field is set to
    # "start_feed_length_ft" or "end_feed_length_ft".
    start_feed_length = selections.get("start_feed_length_ft")
    if start_feed_length is not None and str(start_feed_length) != "":
        webflow_overrides["start_feed_length_ft"] = str(start_feed_length)
    end_feed_length = selections.get("end_feed_length_ft")
    if end_feed_length is not None and str(end_feed_length) != "":
        webflow_overrides["end_feed_length_ft"] = str(end_feed_length)

    # Forward feed direction selections for PDF mapping
    start_feed_dir = selections.get("start_feed_direction")
    if start_feed_dir:
        webflow_overrides["start_feed_direction"] = str(start_feed_dir)
    end_feed_dir = selections.get("end_feed_direction")
    if end_feed_dir:
        webflow_overrides["end_feed_direction"] = str(end_feed_dir)

    submittal_result = generate_filled_submittal(
        configured_fixture_id,
        webflow_overrides=webflow_overrides,
        is_private=0,
    )

    if not submittal_result.get("success") or not submittal_result.get("file_url"):
        # Submittal generation failed even though the template IS
        # configured — surface the real error instead of silently
        # falling back to the static spec sheet.
        error_detail = submittal_result.get("message") or "Unknown error"
        frappe.log_error(
            title="Spec Submittal Generation Failed",
            message=(
                f"generate_filled_submittal returned failure for "
                f"configured_fixture={configured_fixture_id}: {error_detail}"
            ),
        )
        return {
            "success": False,
            "error": f"Could not generate filled spec submittal: {error_detail}",
        }

    # ── Step 6: Make the file publicly accessible ─────────────────────
    file_url = submittal_result["file_url"]
    file_url = _ensure_public_file(file_url)

    part_number = _generate_full_part_number(series_info, selections)

    return {
        "success": True,
        "file_url": file_url,
        "filename": f"Spec_Sheet_{part_number}.pdf",
        "part_number": part_number,
    }


def _map_selections_to_engine_codes(
    template, selections: dict, tape_offering_id: str
) -> dict:
    """
    Map Webflow configurator selections to the parameters expected by
    validate_and_quote().

    The Webflow page sends radio button values which may be:
      - ERPNext document names (e.g. "Dry Rated")
      - Display names (e.g. "100 lm/ft")
      - Short codes (e.g. "WH", "FR")

    This function tries each value as-is first, then falls back to
    looking up by code, then by matching against the template's
    allowed_options child table.

    Returns:
        dict with all engine parameter keys, or {"error": str} on failure
    """
    errors = []

    # ── Resolve each attribute selection ──────────────────────────────
    # For each field, try: raw value → code lookup → allowed_options scan

    finish_code = _resolve_attribute(
        selections, "finish", "finish_code",
        "ilL-Attribute-Finish", "code", template, "Finish", "finish",
    )
    lens_appearance_code = _resolve_attribute(
        selections, "lens_appearance", "lens_appearance_code",
        "ilL-Attribute-Lens Appearance", "code", template, "Lens Appearance", "lens_appearance",
    )
    mounting_method_code = _resolve_attribute(
        selections, "mounting_method", "mounting_method_code",
        "ilL-Attribute-Mounting Method", "code", template, "Mounting Method", "mounting_method",
    )
    environment_rating_code = _resolve_attribute(
        selections, "environment_rating", "environment_rating_code",
        "ilL-Attribute-Environment Rating", "code", template, "Environment Rating", "environment_rating",
    )

    if not finish_code:
        errors.append("Finish is required")
    if not lens_appearance_code:
        errors.append("Lens appearance is required")
    if not mounting_method_code:
        errors.append("Mounting method is required")
    if not environment_rating_code:
        errors.append("Environment rating is required")

    # Length: convert inches → mm
    length_inches = selections.get("length_inches")
    if not length_inches:
        errors.append("Length is required")
        requested_overall_length_mm = 0
    else:
        requested_overall_length_mm = int(round(float(length_inches) * 25.4))

    # ── Endcap & power feed defaults ──────────────────────────────────
    endcap_style_start_code = _get_default_option(template, "Endcap Style", "endcap_style")
    endcap_style_end_code = endcap_style_start_code

    endcap_color_code = _resolve_endcap_color(template, finish_code)

    power_feed_type_code = _resolve_power_feed_type(selections, template)

    # ── Feed direction codes & leader lengths ─────────────────────────
    MM_PER_FOOT = 304.8

    # Start feed direction code — resolve from selection or power_feed_type
    start_feed_direction_code = None
    start_feed_dir_raw = selections.get("start_feed_direction", "")
    if start_feed_dir_raw:
        # Try to get code from Feed Direction attribute
        fd_code = frappe.db.get_value(
            "ilL-Attribute-Feed-Direction", start_feed_dir_raw, "code"
        )
        if fd_code:
            start_feed_direction_code = fd_code
        elif len(start_feed_dir_raw) <= 2:
            # Already a code (e.g. "E", "B")
            start_feed_direction_code = start_feed_dir_raw

    # End feed direction code — "C" for Endcap (default), otherwise resolve
    end_feed_direction_code = "C"
    end_feed_dir_raw = selections.get("end_feed_direction", "")
    if end_feed_dir_raw:
        if end_feed_dir_raw.lower() in ("endcap", "c"):
            end_feed_direction_code = "C"
        else:
            fd_code = frappe.db.get_value(
                "ilL-Attribute-Feed-Direction", end_feed_dir_raw, "code"
            )
            if fd_code:
                end_feed_direction_code = fd_code
            elif len(end_feed_dir_raw) <= 2:
                end_feed_direction_code = end_feed_dir_raw

    # Leader cable lengths — convert feet to mm
    start_leader_len_mm = 0
    start_len_ft = selections.get("start_feed_length_ft")
    if start_len_ft:
        try:
            start_leader_len_mm = int(round(float(start_len_ft) * MM_PER_FOOT))
        except (ValueError, TypeError):
            pass

    end_leader_len_mm = 0
    end_len_ft = selections.get("end_feed_length_ft")
    if end_len_ft and end_feed_direction_code != "C":
        try:
            end_leader_len_mm = int(round(float(end_len_ft) * MM_PER_FOOT))
        except (ValueError, TypeError):
            pass

    if errors:
        return {"error": "; ".join(errors)}

    return {
        "finish_code": finish_code,
        "lens_appearance_code": lens_appearance_code,
        "mounting_method_code": mounting_method_code,
        "endcap_style_start_code": endcap_style_start_code,
        "endcap_style_end_code": endcap_style_end_code,
        "endcap_color_code": endcap_color_code,
        "power_feed_type_code": power_feed_type_code,
        "environment_rating_code": environment_rating_code,
        "requested_overall_length_mm": requested_overall_length_mm,
        "start_feed_direction_code": start_feed_direction_code,
        "end_feed_direction_code": end_feed_direction_code,
        "start_leader_len_mm": start_leader_len_mm,
        "end_leader_len_mm": end_leader_len_mm,
    }


def _resolve_attribute(
    selections: dict,
    value_key: str,
    code_key: str,
    doctype: str,
    code_field: str,
    template,
    option_type: str,
    child_field: str,
) -> str:
    """
    Resolve a Webflow selection to an ERPNext attribute document name.

    Tries in order:
    1. The raw value — if it exists as a document name
    2. The _code value — looked up by the code field
    3. Scan the template's allowed_options for a match by code or name

    Returns the ERPNext document name, or empty string if not resolvable.
    """
    raw_value = selections.get(value_key, "")
    code_value = selections.get(code_key, "")

    if not raw_value and not code_value:
        return ""

    # Try 1: raw value is already a valid document name
    if raw_value and frappe.db.exists(doctype, raw_value):
        return raw_value

    # Try 2: look up by code (the JS sends data-code as {field}_code)
    if code_value:
        match = frappe.db.get_value(doctype, {code_field: code_value}, "name")
        if match:
            return match

    # Try 3: raw value might be a code itself
    if raw_value:
        match = frappe.db.get_value(doctype, {code_field: raw_value}, "name")
        if match:
            return match

    # Try 4: scan allowed_options on the template for a match
    for opt in getattr(template, "allowed_options", []) or []:
        if getattr(opt, "option_type", None) != option_type:
            continue
        if not getattr(opt, "is_active", True):
            continue
        attr_name = getattr(opt, child_field, "") or ""
        if not attr_name:
            continue
        # Check if the code matches
        attr_code = frappe.db.get_value(doctype, attr_name, code_field)
        if attr_code and (attr_code == raw_value or attr_code == code_value):
            return attr_name

    # Last resort: return raw value and let validate_and_quote fail gracefully
    return raw_value


def _get_default_option(template, option_type: str, child_field: str) -> str:
    """
    Get the default (or first active) allowed option of a given type
    from the fixture template's allowed_options child table.
    """
    for opt in getattr(template, "allowed_options", []) or []:
        if (
            getattr(opt, "option_type", None) == option_type
            and getattr(opt, "is_active", True)
        ):
            # Prefer the one marked as default
            if getattr(opt, "is_default", False):
                return getattr(opt, child_field, "") or ""

    # No default found — return the first active one
    for opt in getattr(template, "allowed_options", []) or []:
        if (
            getattr(opt, "option_type", None) == option_type
            and getattr(opt, "is_active", True)
        ):
            return getattr(opt, child_field, "") or ""

    return ""


def _resolve_endcap_color(template, finish_code: str) -> str:
    """
    Resolve a default endcap color for the fixture template.

    Endcap color is resolved from the ilL-Rel-Finish Endcap Color doctype
    which maps finish → endcap_color. Falls back to ilL-Rel-Endcap-Map rows
    keyed by template, or the first active ilL-Attribute-Endcap Color.
    """
    # Primary: resolve from ilL-Rel-Finish Endcap Color mapping
    if finish_code:
        finish_endcap = frappe.db.get_value(
            "ilL-Rel-Finish Endcap Color",
            {"finish": finish_code, "is_active": 1},
            "endcap_color",
            order_by="is_default DESC, modified DESC",
        )
        if finish_endcap:
            return finish_endcap

    template_code = getattr(template, "template_code", None) or template.name

    # Fallback: try the endcap map for this template
    endcap_map_row = frappe.db.get_value(
        "ilL-Rel-Endcap-Map",
        {"fixture_template": template_code, "is_active": 1},
        "endcap_color",
        order_by="is_default DESC, name ASC",
    )
    if endcap_map_row:
        return endcap_map_row

    # Fallback: first active endcap color record
    first_color = frappe.db.get_value(
        "ilL-Attribute-Endcap Color",
        {"is_active": 1},
        "name",
        order_by="sort_order ASC, name ASC",
    )
    return first_color or ""


def _resolve_power_feed_type(selections: dict, template=None) -> str:
    """
    Resolve the power feed type from Webflow feed direction selections.

    The Webflow configurator may send start_feed_direction ("End" / "Back")
    but often omits it entirely.  The engine expects the *name* (primary key)
    of an ilL-Attribute-Power Feed Type document.

    Resolution order:
    1. Exact document-name match on the raw selection value
    2. Lookup by ``code`` field  (e.g. "E" for End)
    3. Lookup by linked Feed Direction (``type`` field → ilL-Attribute-Feed-Direction)
    4. Lookup via the template's allowed_options for Power Feed Type (prefer default)
    5. First Power Feed Type record in the database
    """
    start_dir = selections.get("start_feed_direction", "") or ""

    if not frappe.db.exists("DocType", "ilL-Attribute-Power Feed Type"):
        return start_dir or ""

    # 1. Exact match on document name
    if start_dir and frappe.db.exists("ilL-Attribute-Power Feed Type", start_dir):
        return start_dir

    # 2. Match by code (e.g. "E")
    code_to_try = start_dir[:1].upper() if start_dir else "E"  # default "E" = End feed
    match = frappe.db.get_value(
        "ilL-Attribute-Power Feed Type",
        {"code": code_to_try},
        "name",
    )
    if match:
        return match

    # 3. Match by Feed Direction link  (type → ilL-Attribute-Feed-Direction)
    #    Feed Direction "End" has code "E"
    if start_dir:
        match = frappe.db.get_value(
            "ilL-Attribute-Power Feed Type",
            {"type": start_dir},
            "name",
        )
        if match:
            return match

    # 4. Template's allowed_options for Power Feed Type
    if template:
        pft = _get_default_option(template, "Power Feed Type", "power_feed_type")
        if pft:
            return pft

    # 5. Absolute fallback — first record in the table
    first = frappe.db.get_value(
        "ilL-Attribute-Power Feed Type",
        {},
        "name",
        order_by="name ASC",
    )
    return first or ""


def _ensure_public_file(file_url: str) -> str:
    """
    Ensure the generated file is publicly accessible (not private).

    Spec sheet downloads from Webflow need to be guest-accessible.
    If the file is in /private/files/, move it to /files/ via the File doc.
    """
    import traceback as tb_mod

    if not file_url or not file_url.startswith("/private/files/"):
        return file_url

    try:
        # Use get_all to handle duplicate File records from re-uploads gracefully.
        matches = frappe.get_all(
            "File",
            filters={"file_url": file_url},
            fields=["name"],
            order_by="creation desc",
            limit_page_length=1,
            ignore_permissions=True,
        )
        if not matches:
            frappe.log_error(
                title="Spec Sheet: No File doc found",
                message=f"No File record found for URL: {file_url}",
            )
            return file_url

        file_doc = frappe.get_doc("File", matches[0].name)
        if file_doc.is_private:
            file_doc.is_private = 0
            file_doc.save(ignore_permissions=True)
            frappe.db.commit()
            return file_doc.file_url
    except Exception as e:
        frappe.log_error(
            title="Spec Sheet: Failed to make file public",
            message=(
                f"Could not make file public: {file_url}.\n"
                f"Error type: {type(e).__name__}\n"
                f"Error: {e}\n"
                f"Traceback:\n{tb_mod.format_exc()}"
            ),
        )
        # Fallback: try setting is_private directly via DB and moving the
        # physical file, bypassing the File doc's save hooks that may
        # fail under Guest context.
        try:
            import os
            import shutil
            site_path = frappe.get_site_path()
            private_path = os.path.join(site_path, file_url.lstrip("/"))
            public_filename = file_url.replace("/private/files/", "/files/")
            public_path = os.path.join(site_path, "public", "files", os.path.basename(file_url))
            if os.path.exists(private_path):
                shutil.copy2(private_path, public_path)
                frappe.db.set_value(
                    "File", matches[0].name,
                    {"is_private": 0, "file_url": public_filename},
                    update_modified=False,
                )
                frappe.db.commit()
                return public_filename
        except Exception as e2:
            frappe.log_error(
                title="Spec Sheet: Fallback public file also failed",
                message=f"Fallback failed for {file_url}: {e2}\n{tb_mod.format_exc()}",
            )

    return file_url
