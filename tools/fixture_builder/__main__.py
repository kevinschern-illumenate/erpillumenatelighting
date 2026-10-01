"""Fixture Builder CLI entry point.

Usage:
    python -m tools.fixture_builder --config path/to/config.yaml --output path/to/output/
    python -m tools.fixture_builder --interactive --output path/to/output/
    python -m tools.fixture_builder --mode new-variant --config variant.yaml --output path/
    python -m tools.fixture_builder --product-type tape --config tape.yaml --output ./output/tape/
    python -m tools.fixture_builder --product-type neon --config neon.yaml --output ./output/neon/
"""

from __future__ import annotations

import argparse
import os
import sys

from .config_schema import FixtureBuilderConfig, load_config
from .erp_reference import REFERENCE, add_catalog, load_reference, unconfirmed_links
from .generators import (
    gen_component_variants,
    gen_fixture_template,
    gen_item_csv,
    gen_led_sheet_submittal_mapping,
    gen_led_sheet_template,
    gen_led_sheet_webflow,
    gen_neon_submittal_mapping,
    gen_rel_driver_eligibility,
    gen_rel_endcap_map,
    gen_rel_mounting_map,
    gen_rel_profile_lens,
    gen_rel_tape_offering,
    gen_spec_accessory,
    gen_spec_led_tape,
    gen_spec_lens,
    gen_spec_profile,
    gen_spec_submittal_mapping,
    gen_tape_item_csv,
    gen_tape_neon_template,
    gen_tape_neon_webflow,
    gen_webflow_product,
)
from .prompts import prompt_all


def validate_config(config: FixtureBuilderConfig, reference=None) -> list[str]:
    """Validate config and return list of error messages (empty = valid).

    ``reference`` maps DocTypes to record names that already exist in ERPNext.
    """
    if isinstance(config, dict):
        from .catalog import prepare_catalog
        try:
            prepare_catalog(config, reference=reference)
        except ValueError as exc:
            return str(exc).splitlines()
        return []
    errors = []

    if config.product_type not in ("fixture", "tape", "neon", "led-sheet"):
        errors.append("This product type requires a schema_version: 2 catalog configuration")
    if config.mode not in ("new-family", "new-variant"):
        errors.append("mode must be new-family or new-variant")

    if not config.series_name:
        errors.append("series_name is required")

    if config.product_type == "fixture":
        # Fixture-specific validation
        if not config.profiles:
            if config.mode == "new-family":
                errors.append("At least one profile is required for new-family mode")
        if config.mode == "new-family":
            if not config.lenses:
                errors.append("At least one lens definition is required for new-family mode")
            if not config.profile_lens_mappings:
                errors.append("At least one profile-lens mapping is required for new-family mode")

        for p in config.profiles:
            if not p.family:
                errors.append("Profile family code is required")
            if not p.finishes:
                errors.append(f"Profile {p.family}: at least one finish required")

    elif config.product_type in ("tape", "neon"):
        # Tape/Neon-specific validation
        if config.mode == "new-family":
            if not config.tape_specs:
                errors.append("At least one tape_spec is required for new-family mode")

        if not config.tape_neon_templates:
            errors.append("At least one tape_neon_template is required")

        # Validate tape offering references
        valid_spec_codes = {ts.item_code for ts in config.tape_specs}
        for offering in config.tape_offerings:
            if offering.tape_spec and offering.tape_spec not in valid_spec_codes:
                errors.append(
                    f"Tape offering references unknown tape_spec: {offering.tape_spec}"
                )

        # Validate template references
        expected_category = "LED Tape" if config.product_type == "tape" else "LED Neon"
        for tmpl in config.tape_neon_templates:
            if not tmpl.template_code:
                errors.append("Tape/neon template_code is required")
            if tmpl.product_category and tmpl.product_category != expected_category:
                errors.append(
                    f"Template {tmpl.template_code}: product_category should be "
                    f"'{expected_category}' for product_type='{config.product_type}'"
                )
            for spec_ref in tmpl.allowed_tape_specs:
                if spec_ref.tape_spec and spec_ref.tape_spec not in valid_spec_codes:
                    errors.append(
                        f"Template {tmpl.template_code} references unknown "
                        f"tape_spec: {spec_ref.tape_spec}"
                    )

    elif config.product_type == "led-sheet":
        if not config.led_sheet_specs:
            errors.append("At least one led_sheet_spec is required")
        if not config.led_sheet_templates:
            errors.append("At least one led_sheet_template is required")
        if not config.series_code:
            errors.append("series_code is required for led-sheet")
        if not config.led_package:
            errors.append("led_package is required for led-sheet")
        if config.sheet_dimensions.width_ft <= 0 or config.sheet_dimensions.height_ft <= 0:
            errors.append("sheet_dimensions.width_ft and sheet_dimensions.height_ft must be greater than zero")
        if config.watts_per_sqft <= 0:
            errors.append("watts_per_sqft must be greater than zero for led-sheet")
        if config.lumens_per_sqft <= 0:
            errors.append("lumens_per_sqft must be greater than zero for led-sheet")
        for field_name in ("cct_options", "output_options", "environment_options", "mounting_options", "finish_options"):
            if not getattr(config, field_name):
                errors.append(f"{field_name} must include at least one value for led-sheet")
        if not (config.jumper_cable_item or any(t.jumper_cable_item for t in config.led_sheet_templates)):
            errors.append("jumper_cable_item is required for led-sheet")
        if not (config.leader_cable_item or any(t.leader_cable_item for t in config.led_sheet_templates)):
            errors.append("leader_cable_item is required for led-sheet")
        for spec in config.led_sheet_specs:
            from illumenate_lighting.illumenate_lighting.api.authoring_contract import record_issues
            issues = record_issues("ilL-Spec-LED-Sheet", {
                "name": spec.item_code, "item": spec.item_code, "led_package": spec.led_package,
                "sheet_width_ft": spec.sheet_dimensions.width_ft, "sheet_height_ft": spec.sheet_dimensions.height_ft,
                "total_sheet_watts": spec.total_sheet_watts, "watts_per_sqft": spec.watts_per_sqft,
                "input_voltage": spec.input_voltage, "input_protocol": spec.input_protocol,
                "cct": spec.cct, "max_panels_per_feed": spec.max_panels_per_feed,
            })
            errors.extend(f"{row['record']}: {row['field']}: {row['message']}" for row in issues)
            if not spec.led_package:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: led_package is required")
            if spec.sheet_dimensions.width_ft <= 0 or spec.sheet_dimensions.height_ft <= 0:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: sheet_dimensions must be greater than zero")
            if spec.watts_per_sqft <= 0 and spec.total_sheet_watts <= 0:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: full panel watts or watts_per_sqft is required")
            if spec.lumens_per_sqft <= 0:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: lumens_per_sqft must be greater than zero")

    return errors


def generate_all(config: FixtureBuilderConfig, output_dir: str,
                 source_submittal_csv: str = "", reference=None) -> dict[str, str]:
    """Generate all CSV files and return {filename: filepath} mapping."""
    if isinstance(config, dict):
        from .catalog import generate_catalog
        return generate_catalog(config, output_dir, reference)
    if config.product_type not in ("fixture", "tape", "neon", "led-sheet"):
        raise ValueError("Unsupported legacy product_type")
    if config.product_type in ("tape", "neon"):
        return generate_all_tape_neon(config, output_dir, source_submittal_csv)
    if config.product_type == "led-sheet":
        return generate_all_led_sheet(config, output_dir, source_submittal_csv)
    return generate_all_fixture(config, output_dir, source_submittal_csv)


def generate_all_fixture(config: FixtureBuilderConfig, output_dir: str,
                         source_submittal_csv: str = "") -> dict[str, str]:
    """Generate all fixture CSV files and return {filename: filepath} mapping."""
    os.makedirs(output_dir, exist_ok=True)
    results = {}

    is_new_family = config.mode == "new-family"

    if is_new_family:
        # Phase 1: New family CSVs
        component_files = gen_component_variants.generate(config, output_dir)
        results["Item Attribute.csv"] = component_files["Item Attribute.csv"]
        results["Item CSV.csv"] = gen_item_csv.generate(config, output_dir)
        results["Item Variants.csv"] = component_files["Item Variants.csv"]
        results["ilL-Spec-Profile.csv"] = gen_spec_profile.generate(config, output_dir)
        results["ilL-Spec-Lens.csv"] = gen_spec_lens.generate(config, output_dir)
        results["ilL-Spec-Accessory.csv"] = gen_spec_accessory.generate(config, output_dir)
        results["ilL-Rel-Profile Lens.csv"] = gen_rel_profile_lens.generate(config, output_dir)

    # Phase 2: Both modes
    results["ilL-Fixture-Template.csv"] = gen_fixture_template.generate(config, output_dir)
    results["ilL-Rel-Mounting-Accessory-Map.csv"] = gen_rel_mounting_map.generate(config, output_dir)
    results["ilL-Rel-Endcap-Map.csv"] = gen_rel_endcap_map.generate(config, output_dir)
    results["ilL-Rel-Driver-Eligibility.csv"] = gen_rel_driver_eligibility.generate(config, output_dir)
    results["ilL-Spec-Submittal-Mapping.csv"] = gen_spec_submittal_mapping.generate(
        config, output_dir, source_csv_path=source_submittal_csv
    )
    results["ilL-Webflow-Product.csv"] = gen_webflow_product.generate(config, output_dir)

    return results


def generate_all_tape_neon(config: FixtureBuilderConfig, output_dir: str,
                           source_submittal_csv: str = "") -> dict[str, str]:
    """Generate all tape/neon CSV files and return {filename: filepath} mapping."""
    os.makedirs(output_dir, exist_ok=True)
    results = {}

    is_new_family = config.mode == "new-family"

    if is_new_family:
        # Phase 1: New family CSVs (specs & offerings)
        results["Item CSV.csv"] = gen_tape_item_csv.generate(config, output_dir)
        results["ilL-Spec-LED Tape.csv"] = gen_spec_led_tape.generate(config, output_dir)
        results["ilL-Rel-Tape Offering.csv"] = gen_rel_tape_offering.generate(config, output_dir)

    # Phase 2: Both modes (templates, submittal, webflow)
    results["ilL-Tape-Neon-Template.csv"] = gen_tape_neon_template.generate(config, output_dir)
    if config.mounting_accessories:
        results["ilL-Rel-Mounting-Accessory-Map.csv"] = gen_rel_mounting_map.generate(config, output_dir)
    results["ilL-Rel-Driver-Eligibility.csv"] = gen_rel_driver_eligibility.generate(config, output_dir)
    results["ilL-Neon-Submittal-Mapping.csv"] = gen_neon_submittal_mapping.generate(
        config, output_dir, source_csv_path=source_submittal_csv
    )
    results["ilL-Webflow-Product.csv"] = gen_tape_neon_webflow.generate(config, output_dir)

    return results


def generate_all_led_sheet(config: FixtureBuilderConfig, output_dir: str,
                           source_submittal_csv: str = "") -> dict[str, str]:
    """Generate all LED Sheet CSV files and return {filename: filepath}."""
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    results.update(gen_led_sheet_template.generate(config, output_dir))
    results["ilL-Rel-Driver-Eligibility.csv"] = gen_rel_driver_eligibility.generate(config, output_dir)
    results["ilL-LED-Sheet-Submittal-Mapping.csv"] = gen_led_sheet_submittal_mapping.generate(
        config, output_dir, source_csv_path=source_submittal_csv
    )
    # LED Sheet Webflow uses the same wide import columns with LED Sheet product type.
    results["ilL-Webflow-Product.csv"] = gen_led_sheet_webflow.generate(config, output_dir)
    return results


def _count_data_rows(filepath: str) -> int:
    """Count non-header rows in a CSV file."""
    import csv
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def main():
    parser = argparse.ArgumentParser(
        prog="fixture_builder",
        description="Generate ERPNext CSV import files for new fixture families or LED package variants.",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output directory for generated CSV files",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["new-family", "new-variant"],
        default=None,
        help="Generation mode: new-family (all CSVs) or new-variant (subset)",
    )
    parser.add_argument(
        "--product-type", "-t",
        choices=["fixture", "tape", "neon", "led-sheet", "extrusion-kit", "driver", "controller"],
        default=None,
        help="Product type: fixture (default), tape, neon, or led-sheet",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode, prompting for missing values",
    )
    parser.add_argument(
        "--source-submittal-csv",
        default="",
        help="Path to existing ilL-Spec-Submittal-Mapping.csv to clone from",
    )
    parser.add_argument(
        "--reference",
        default=str(REFERENCE),
        help="ERPNext records snapshot from tools.fixture_builder.erp_reference; "
        "version 2 links to these records resolve as existing",
    )
    parser.add_argument(
        "--no-reference",
        action="store_true",
        help="Ignore the ERPNext records snapshot; only declared external_links resolve",
    )

    args = parser.parse_args()

    # Load or create config
    if args.config:
        if not os.path.exists(args.config):
            print(f"Error: config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        try:
            config = load_config(args.config)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
    else:
        config = FixtureBuilderConfig()

    # Override mode if specified
    if args.mode:
        if isinstance(config, dict):
            parser.error("--mode applies only to legacy family configs")
        config.mode = args.mode

    # Override product type if specified
    if args.product_type:
        if isinstance(config, dict):
            config["product_type"] = args.product_type
        else:
            config.product_type = args.product_type

    # Interactive prompts for missing data
    if args.interactive or not args.config:
        if isinstance(config, dict) or config.product_type in ("extrusion-kit", "driver", "controller"):
            parser.error("Use the YAML Builder product catalog editor to author version 2 configurations")
        prompt_all(config)

    reference = None
    if args.reference != str(REFERENCE) and not os.path.exists(args.reference):
        parser.error(f"reference file not found: {args.reference}")
    if isinstance(config, dict) and not args.no_reference and os.path.exists(args.reference):
        reference = load_reference(args.reference, config)
        for doctype, name in unconfirmed_links(config, args.reference):
            print(f"Warning: {doctype} / {name} is declared existing but is not in the ERPNext export",
                  file=sys.stderr)

    # Validate
    errors = validate_config(config, reference)
    if errors:
        print("Configuration errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Generate
    ptype = config["product_type"] if isinstance(config, dict) else config.product_type
    series = config.get("series_name", "Product catalog") if isinstance(config, dict) else config.series_name
    print(f"\nGenerating CSVs for {series} ({ptype})...")
    print(f"Output directory: {os.path.abspath(args.output)}\n")

    results = generate_all(config, args.output, source_submittal_csv=args.source_submittal_csv,
                           reference=reference)

    # Summary
    print("=" * 60)
    print(f"{'File':<45} {'Rows':>6}")
    print("-" * 60)
    total_rows = 0
    for filename, filepath in results.items():
        count = _count_data_rows(filepath)
        total_rows += count
        print(f"  {filename:<43} {count:>6}")
    print("-" * 60)
    print(f"  {'TOTAL':<43} {total_rows:>6}")
    print(f"\n{len(results)} CSV files generated successfully.")

    if isinstance(config, dict) and config.get("add_to_reference"):
        if reference is None:
            print("\nNot added to the ERPNext reference: no reference file is in use.")
        else:
            add_to_reference(config, args.reference, reference)


def add_to_reference(config, path, reference):
    """Record a generated catalog as existing ERPNext records for later catalogs."""
    import json

    from .catalog import prepare_catalog
    from .catalog_schema import build_schema

    schema = build_schema()
    records, _, _ = prepare_catalog(config, schema, reference)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    count = add_catalog(data, config, records, schema)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"\nAdded {count} records to the ERPNext reference ({path}).")
    print("Import the package into ERPNext, then commit that file so the hosted YAML Builder can link to them.")


if __name__ == "__main__":
    main()
