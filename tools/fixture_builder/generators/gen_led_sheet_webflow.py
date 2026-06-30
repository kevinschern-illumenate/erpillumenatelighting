"""Generator for ilL-Webflow-Product.csv — Webflow product entries for LED Sheet.

Multi-line for configurator_options and attribute_links child tables.
Reuses the same CSV filename but with LED Sheet-specific content and
product type set to "LED Sheet".
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, CONFIGURATOR_STEP_TYPES

# Use the same headers as the fixture webflow generator for compatibility
HEADERS = [
    "Product Name",
    "Product Slug",
    "Product Type",
    "Product Category",
    "Series",
    "Is Active",
    "Fixture Template",
    "LED Sheet Template",
    "Driver Spec",
    "Controller Spec",
    "Profile Spec",
    "Lens Spec",
    "LED Tape Spec",
    "Accessory Spec",
    "Is Configurable",
    "Configurator Intro Text",
    "Min Length (mm)",
    "Max Length (mm)",
    "Length Increment (mm)",
    "Short Description",
    "Sublabel",
    "Long Description",
    "Featured Image",
    "Auto Calculate Specs",
    "Auto Populate Attributes",
    "Beam Angle (°)",
    "Min Operating Temp (°C)",
    "Max Operating Temp (°C)",
    "L70 Life (hours)",
    "Warranty (years)",
    "Fixture Weight per Foot (g)",
    # Image fields (30-52)
    "Image_ilLumenate Logo",
    "Image_Spec Line",
    "Image_Hero",
    "Image_Channel Component Image",
    "Image_Channel URL",
    "Image_Tape Component Image",
    "Image_Tape URL",
    "Image_ETL Rated Icon",
    "Image_UL Rated Icon",
    "Image_5V DC Icon",
    "Image_12V DC Icon",
    "Image_24V DC Icon",
    "Image_120V DC Icon",
    "Image_Dry Rated Icon",
    "Image_Damp Rated Icon",
    "Image_Wet Rated Icon",
    "Image_Dimensions 1",
    "Image_Dimensions 2",
    "Image_Dimensions 3",
    "Image_Dimensions 4",
    "Image_Acc Dims 1",
    "Image_Acc Dims 2",
    "Image_Acc Dims 3",
    # Sync fields
    "Webflow Collection Slug",
    "Last Synced At",
    "Sync Status",
    "Sync Error Message",
    # Configurator Options child table
    "Allowed Values (JSON) (Configurator Options)",
    "Depends on Step (Configurator Options)",
    "Is Required (Configurator Options)",
    "Option Description (Configurator Options)",
    "Option Label (Configurator Options)",
    "Option Type (Configurator Options)",
    "Step Order (Configurator Options)",
    # Kit Components child table
    "Component Item (Kit Components)",
    "Component Type (Kit Components)",
    "Notes (Kit Components)",
    "Quantity (Kit Components)",
    "Spec DocType (Kit Components)",
    "Spec Reference (Kit Components)",
    # Gallery Images child table
    "Alt Text (Gallery Images)",
    "Caption (Gallery Images)",
    "Display Order (Gallery Images)",
    "Image (Gallery Images)",
    # Documents child table
    "Display Order (Documents)",
    "Document File (Documents)",
    "Document Title (Documents)",
    "Document Type (Documents)",
    # Specifications child table
    "Attribute DocType (Specifications)",
    "Attribute Options (JSON) (Specifications)",
    "Display Order (Specifications)",
    "Is Calculated (Specifications)",
    "Show on Card (Specifications)",
    "Specification Group (Specifications)",
    "Specification Label (Specifications)",
    "Specification Value (Specifications)",
    "Unit (Specifications)",
    # Attribute Links child table
    "Attribute DocType (Attribute Links)",
    "Attribute Name (Attribute Links)",
    "Attribute Type (Attribute Links)",
    "Display Label (Attribute Links)",
    "Display Order (Attribute Links)",
    # Certifications child table
    "Certification (Certifications)",
    "Display Order (Certifications)",
    # Compatible Products child table
    "Notes (Compatible Products)",
    "Related Product (Compatible Products)",
    "Relationship Type (Compatible Products)",
]

NUM_COLS = len(HEADERS)

# Column index for child table sections
COL_CONFIG_OPTIONS = HEADERS.index("Allowed Values (JSON) (Configurator Options)")
COL_ATTRIBUTE_LINKS = HEADERS.index("Attribute DocType (Attribute Links)")


def _build_configurator_step(step_order, option_type, label="",
                             is_required=1, depends_on=0):
    """Build configurator_options child columns."""
    cols = [""] * 7
    cols[0] = ""                         # Allowed Values (JSON)
    cols[1] = depends_on                 # Depends on Step
    cols[2] = is_required                # Is Required
    cols[3] = ""                         # Option Description
    cols[4] = label or CONFIGURATOR_STEP_TYPES.get(option_type, option_type)
    cols[5] = option_type                # Option Type
    cols[6] = step_order                 # Step Order
    return cols


def _build_attribute_link(attr_doctype, attr_name, attr_type, display_label, display_order):
    """Build attribute_links child columns."""
    return [attr_doctype, attr_name, attr_type, display_label, display_order]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Webflow-Product.csv for LED Sheet and return the filepath."""
    rows = []
    wf = config.led_sheet_webflow

    for tmpl in config.led_sheet_templates:
        product_name = tmpl.template_name or f"{config.series_name} LED Sheet"
        product_slug = tmpl.template_code.lower().replace(" ", "-")

        # Build child table rows
        child_rows = []

        # Configurator steps
        for i, step_type in enumerate(wf.configurator_steps, 1):
            step_label = CONFIGURATOR_STEP_TYPES.get(step_type, step_type)
            child_rows.append(("config", _build_configurator_step(
                step_order=i,
                option_type=step_type,
                label=step_label,
                is_required=1,
            )))

        # Attribute links from template allowed_options
        attr_order = 0
        seen_types = set()
        for opt in tmpl.allowed_options:
            attr_key = (opt.option_type, opt.value)
            if attr_key in seen_types:
                continue
            seen_types.add(attr_key)

            attr_order += 1
            attr_doctype = f"ilL-Attribute-{opt.option_type}"
            child_rows.append(("attr", _build_attribute_link(
                attr_doctype, opt.value, opt.option_type,
                opt.value, attr_order
            )))

        # Primary row
        primary = [""] * NUM_COLS
        primary[0] = product_name
        primary[1] = product_slug
        primary[2] = "LED Sheet"
        primary[3] = wf.product_category
        primary[4] = tmpl.series or config.series_name
        primary[5] = 1   # Is Active
        primary[7] = tmpl.template_code
        primary[12] = ""
        primary[14] = 1  # Is Configurable
        primary[20] = wf.sublabel
        primary[23] = 1  # Auto Calculate Specs
        primary[24] = 1  # Auto Populate Attributes
        primary[25] = wf.beam_angle
        primary[26] = wf.operating_temp_min_c
        primary[27] = wf.operating_temp_max_c
        primary[28] = wf.l70_life_hours
        primary[29] = wf.warranty_years
        primary[54] = "products"  # Webflow Collection Slug

        if child_rows:
            first_type, first_data = child_rows[0]
            _place_child(primary, first_type, first_data)
            rows.append(primary)

            for child_type, child_data in child_rows[1:]:
                cont_row = [""] * NUM_COLS
                _place_child(cont_row, child_type, child_data)
                rows.append(cont_row)
        else:
            rows.append(primary)

    filepath = f"{output_dir}/ilL-Webflow-Product.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath


def _place_child(row, child_type, child_data):
    """Place child table data into the correct columns of a row."""
    if child_type == "config":
        for i, val in enumerate(child_data):
            row[COL_CONFIG_OPTIONS + i] = val
    elif child_type == "attr":
        for i, val in enumerate(child_data):
            row[COL_ATTRIBUTE_LINKS + i] = val
