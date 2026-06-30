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
from .prompts import prompt_all
from .generators import (
    gen_item_csv,
    gen_spec_profile,
    gen_spec_lens,
    gen_spec_accessory,
    gen_rel_profile_lens,
    gen_fixture_template,
    gen_rel_mounting_map,
    gen_rel_endcap_map,
    gen_rel_driver_eligibility,
    gen_spec_submittal_mapping,
    gen_webflow_product,
    gen_tape_item_csv,
    gen_spec_led_tape,
    gen_rel_tape_offering,
    gen_tape_neon_template,
    gen_neon_submittal_mapping,
    gen_tape_neon_webflow,
    gen_led_sheet_template,
    gen_led_sheet_submittal_mapping,
    gen_led_sheet_webflow,
)


def validate_config(config: FixtureBuilderConfig) -> list[str]:
    """Validate config and return list of error messages (empty = valid)."""
    errors = []

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
            if not spec.led_package:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: led_package is required")
            if spec.sheet_dimensions.width_ft <= 0 or spec.sheet_dimensions.height_ft <= 0:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: sheet_dimensions must be greater than zero")
            if spec.watts_per_sqft <= 0:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: watts_per_sqft must be greater than zero")
            if spec.lumens_per_sqft <= 0:
                errors.append(f"LED Sheet spec {spec.item_code or '(unnamed)'}: lumens_per_sqft must be greater than zero")

    return errors


def generate_all(config: FixtureBuilderConfig, output_dir: str,
                 source_submittal_csv: str = "") -> dict[str, str]:
    """Generate all CSV files and return {filename: filepath} mapping."""
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
        results["Item CSV.csv"] = gen_item_csv.generate(config, output_dir)
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
    results["ilL-LED-Sheet-Submittal-Mapping.csv"] = gen_led_sheet_submittal_mapping.generate(
        config, output_dir, source_csv_path=source_submittal_csv
    )
    # LED Sheet Webflow uses the same wide import columns with LED Sheet product type.
    results["ilL-Webflow-Product.csv"] = gen_led_sheet_webflow.generate(config, output_dir)
    return results


def _count_data_rows(filepath: str) -> int:
    """Count non-header rows in a CSV file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1


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
        choices=["fixture", "tape", "neon", "led-sheet"],
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

    args = parser.parse_args()

    # Load or create config
    if args.config:
        if not os.path.exists(args.config):
            print(f"Error: config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        config = load_config(args.config)
    else:
        config = FixtureBuilderConfig()

    # Override mode if specified
    if args.mode:
        config.mode = args.mode

    # Override product type if specified
    if args.product_type:
        config.product_type = args.product_type

    # Interactive prompts for missing data
    if args.interactive or not args.config:
        prompt_all(config)

    # Validate
    errors = validate_config(config)
    if errors:
        print("Configuration errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Generate
    ptype = config.product_type
    print(f"\nGenerating CSVs for {config.series_name} series ({config.mode} mode, {ptype})...")
    print(f"Output directory: {os.path.abspath(args.output)}\n")

    results = generate_all(config, args.output, source_submittal_csv=args.source_submittal_csv)

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


if __name__ == "__main__":
    main()
