"""Generator for ilL-Webflow-Product.csv — Webflow product skeleton entries.

Multi-line for configurator_options, specifications, and attribute_links child tables.
Leaves marketing fields blank for manual fill-in later.
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, LED_PACKAGE_NAMES, CONFIGURATOR_STEP_TYPES

HEADERS = [
    "Product Name",
    "Product Slug",
    "Product Type",
    "Product Category",
    "Series",
    "Is Active",
    "Fixture Template",
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

# Column index for the start of each child table section
COL_CONFIG_OPTIONS = HEADERS.index("Allowed Values (JSON) (Configurator Options)")
COL_KIT_COMPONENTS = HEADERS.index("Component Item (Kit Components)")
COL_GALLERY = HEADERS.index("Alt Text (Gallery Images)")
COL_DOCUMENTS = HEADERS.index("Display Order (Documents)")
COL_SPECIFICATIONS = HEADERS.index("Attribute DocType (Specifications)")
COL_ATTRIBUTE_LINKS = HEADERS.index("Attribute DocType (Attribute Links)")
COL_CERTIFICATIONS = HEADERS.index("Certification (Certifications)")
COL_COMPATIBLE = HEADERS.index("Notes (Compatible Products)")


def _build_configurator_step(step_order, option_type, label="", description="",
                             is_required=1, depends_on=0, allowed_values_json=""):
    """Build configurator_options child columns."""
    cols = [""] * 7
    cols[0] = allowed_values_json  # Allowed Values (JSON)
    cols[1] = depends_on           # Depends on Step
    cols[2] = is_required          # Is Required
    cols[3] = description          # Option Description
    cols[4] = label or CONFIGURATOR_STEP_TYPES.get(option_type, option_type)  # Option Label
    cols[5] = option_type          # Option Type
    cols[6] = step_order           # Step Order
    return cols


def _build_attribute_link(attr_doctype, attr_name, attr_type, display_label, display_order):
    """Build attribute_links child columns."""
    return [attr_doctype, attr_name, attr_type, display_label, display_order]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Webflow-Product.csv and return the filepath."""
    rows = []
    wf = config.webflow
    ft = config.fixture_templates

    for profile in config.profiles:
        for led_pkg in ft.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"
            pkg_name = LED_PACKAGE_NAMES.get(led_pkg, led_pkg)
            label = profile.variant_label
            product_name = f"{config.series_name} {label} {pkg_name}" if label else f"{config.series_name} [{profile.family}] {pkg_name}"
            product_slug = f"ill-{profile.family.lower()}-{led_pkg.lower()}"

            # Resolve per-template allowed options
            opts = config.get_options_for_template(profile.family, led_pkg)

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

            # Attribute links — add from allowed options
            attr_order = 0
            for finish in (opts.allowed_finishes or profile.finishes):
                attr_order += 1
                child_rows.append(("attr", _build_attribute_link(
                    "ilL-Attribute-Finish", finish, "Finish", finish, attr_order
                )))
            for lens in opts.allowed_lenses:
                attr_order += 1
                child_rows.append(("attr", _build_attribute_link(
                    "ilL-Attribute-Lens Appearance", lens, "Lens Appearance", lens, attr_order
                )))
            for mount in opts.allowed_mountings:
                attr_order += 1
                child_rows.append(("attr", _build_attribute_link(
                    "ilL-Attribute-Mounting Method", mount, "Mounting Method", mount, attr_order
                )))
            for es in opts.allowed_endcap_styles:
                attr_order += 1
                child_rows.append(("attr", _build_attribute_link(
                    "ilL-Attribute-Endcap Style", es, "Endcap Style", es, attr_order
                )))

            # Primary row
            primary = [""] * NUM_COLS
            primary[0] = product_name
            primary[1] = product_slug
            primary[2] = "Fixture Template"
            primary[3] = wf.product_category
            primary[4] = config.series_name
            primary[5] = 1  # Is Active
            primary[6] = template_code
            primary[13] = 1  # Is Configurable
            primary[19] = wf.sublabel
            primary[22] = 1  # Auto Calculate Specs
            primary[23] = 1  # Auto Populate Attributes
            primary[24] = wf.beam_angle
            primary[25] = wf.operating_temp_min_c
            primary[26] = wf.operating_temp_max_c
            primary[27] = wf.l70_life_hours
            primary[28] = wf.warranty_years
            primary[53] = "products"  # Webflow Collection Slug

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
    elif child_type == "spec":
        for i, val in enumerate(child_data):
            row[COL_SPECIFICATIONS + i] = val
