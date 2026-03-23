"""Fixture Builder CLI entry point.

Usage:
    python -m tools.fixture_builder --config path/to/config.yaml --output path/to/output/
    python -m tools.fixture_builder --interactive --output path/to/output/
    python -m tools.fixture_builder --mode new-variant --config variant.yaml --output path/
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
)


def validate_config(config: FixtureBuilderConfig) -> list[str]:
    """Validate config and return list of error messages (empty = valid)."""
    errors = []

    if not config.series_name:
        errors.append("series_name is required")
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

    return errors


def generate_all(config: FixtureBuilderConfig, output_dir: str,
                 source_submittal_csv: str = "") -> dict[str, str]:
    """Generate all CSV files and return {filename: filepath} mapping."""
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
        help="Generation mode: new-family (all 11 CSVs) or new-variant (6 CSVs)",
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
    print(f"\nGenerating CSVs for {config.series_name} series ({config.mode} mode)...")
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
