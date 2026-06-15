#!/usr/bin/env python3
"""
csv_to_seed.py

Converts an ERPNext "Export to CSV" spec-sheet export (the wide format with
Output Options 1-8, per-lens watts/run columns, and CCT lumen columns) into
products.seed.json records and appends them to:

    tools/configurator_ui/src/data/products.seed.json

Usage:
    python tools/csv_to_seed.py path/to/spec-sheet.csv
    python tools/csv_to_seed.py path/to/spec-sheet.csv --overwrite   # replace existing SKU records
    python tools/csv_to_seed.py path/to/spec-sheet.csv --dry-run     # print JSON, don't write

One row -> one product record per Output Option (e.g. 8 output levels in the
CSV -> 8 product entries in the seed, each with its own watts/lm/run fields).
The SKU is derived as "<sanitized-product-name>-<output lm/ft>lmft".
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, quote, urlunparse

SEED_PATH = (
    Path(__file__).parent / "configurator_ui" / "src" / "data" / "products.seed.json"
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _split(value: str) -> list:
    """Split a comma-separated cell into a stripped list, dropping empties."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _float(value: str):
    """Parse a float, stripping common unit suffixes like 'W', 'ft', '"', 'mm'."""
    try:
        cleaned = re.sub(r'[^\d.\-]', '', str(value).strip())
        return float(cleaned) if cleaned else None
    except (ValueError, AttributeError):
        return None


def _int(value: str):
    try:
        return int(float(str(value).strip()))
    except (ValueError, AttributeError):
        return None


def _cri_numeric(cri_str: str) -> int:
    """'95+ / 2 SDCM' -> 95,  '90+' -> 90,  '' -> 90 (default)."""
    m = re.search(r"(\d+)\+", cri_str or "")
    return int(m.group(1)) if m else 90


def _parse_cct_cells(row: dict) -> list:
    """Collect Light Color (CCT) 1-8 columns that have values."""
    result = []
    for i in range(1, 9):
        raw = row.get(f"Light Color (CCT) {i}", "").strip()
        if raw:
            # Strip trailing 'K' and parse integer kelvin value
            k = _int(raw.replace("K", ""))
            if k:
                result.append(k)
    return result


def _infer_light_type(product_name: str) -> str:
    name_lower = product_name.lower()
    if "tunable" in name_lower or " tw " in name_lower:
        return "Tunable white"
    if "dim-to-warm" in name_lower or "dtw" in name_lower:
        return "Dim-to-warm"
    if "rgb" in name_lower or "pixel" in name_lower or "color" in name_lower:
        return "Full-color"
    return "Static white"


def _infer_category(product_name: str) -> str:
    name_lower = product_name.lower()
    if "neon" in name_lower:
        return "LED Neon"
    return "LED Tape"


def _parse_environment(env_str: str) -> str:
    """Return the highest-rated environment from a comma-separated list."""
    ratings = [v.strip() for v in (env_str or "").split(",")]
    for r in ("Wet", "Damp", "Dry"):
        if r in ratings:
            return r
    return "Dry"


def _parse_ip(certifications: str):
    """Extract highest IP rating from certifications cell, or None."""
    matches = re.findall(r"IP\d{2}", certifications or "")
    if not matches:
        return None
    order = {"IP68": 3, "IP67": 2, "IP65": 1}
    return max(matches, key=lambda x: order.get(x, 0))


def _parse_input_voltage(raw: str) -> str:
    """'24VDC (Power Supply: 120V-277VAC)' -> '24VDC'."""
    if not raw:
        return "24VDC"
    return raw.split("(")[0].strip()


def _clean_url(value: str):
    """Return a cleaned, percent-encoded URL string, or None for empty / 'N/A' placeholders.

    Encodes spaces and special characters (brackets, parens, etc.) in the URL
    path so browsers can load them, while preserving slashes and the host.
    """
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.upper() in {"N/A", "NA", "NONE", "-"}:
        return None
    try:
        parsed = urlparse(cleaned)
        # Encode only the path portion; safe chars keep slashes and common
        # URL-path punctuation intact while encoding spaces and brackets.
        encoded_path = quote(parsed.path, safe="/:@!$&'()*+,;=~")
        return urlunparse(parsed._replace(path=encoded_path))
    except Exception:
        return cleaned


# Maps raw CSV "Available Mountings" hardware accessory names to the seed
# installation-method vocabulary used by the recommendation engine
# (questions.json options: Surface / Recessed / Angled / Drywall-plaster-in / Suspended).
# Add entries here as new accessory names appear in future CSV exports.
_MOUNTING_ACCESSORY_MAP = {
    # Surface-mount hardware
    "mounting clip":          "Surface",
    "mounting clips":         "Surface",
    "surface clip":           "Surface",
    "surface mount clip":     "Surface",
    "direct surface mount":   "Surface",
    "magnet mount":           "Surface",
    "3m adhesive backing":    "Surface",
    "aluminum channel":       "Surface",
    # Angled / corner hardware
    "pivot clip":             "Angled",
    "corner clip":            "Angled",
    "angled clip":            "Angled",
    # Recessed hardware
    "recessed clip":          "Recessed",
    "recessed bracket":       "Recessed",
    "spring clip":            "Recessed",
    # Suspended hardware
    "suspension kit":         "Suspended",
    "suspension cable":       "Suspended",
    "pendant kit":            "Suspended",
    # Drywall / plaster-in hardware
    "drywall clip":           "Drywall-plaster-in",
    "plaster clip":           "Drywall-plaster-in",
    "drywall":                "Drywall-plaster-in",
    # Pass-through: if the CSV already uses the seed vocabulary, keep it as-is.
    "surface":                "Surface",
    "recessed":               "Recessed",
    "angled":                 "Angled",
    "drywall-plaster-in":     "Drywall-plaster-in",
    "suspended":              "Suspended",
}


def _map_mounting_methods(raw_list: list) -> list:
    """Translate raw CSV accessory names to seed vocabulary.

    Values that don't match the map are kept as-is (with a warning printed)
    so no data is silently dropped — they can be fixed in the seed manually.
    """
    result = []
    seen = set()
    for item in raw_list:
        mapped = _MOUNTING_ACCESSORY_MAP.get(item.lower())
        if mapped:
            if mapped not in seen:
                result.append(mapped)
                seen.add(mapped)
        else:
            print(
                f"  WARNING: unknown mounting accessory '{item}' — kept as-is. "
                "Add it to _MOUNTING_ACCESSORY_MAP in csv_to_seed.py if needed."
            )
            if item not in seen:
                result.append(item)
                seen.add(item)
    return result


def _max_run(*values) -> float | None:
    """Return the maximum non-None run length across the given values."""
    nums = [_float(v) for v in values if _float(v) is not None]
    return max(nums) if nums else None


def _sanitize_sku(text: str) -> str:
    """Convert arbitrary text to a URL/SKU-safe string."""
    slug = re.sub(r"[^\w\-]", "-", text)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Per-output record builder
# ---------------------------------------------------------------------------

def _build_output_record(row: dict, n: int, base: dict):
    """Build one seed product record for output slot n (1-indexed).
    Returns None if the slot is empty."""
    output_label = row.get(f"Output Options {n}", "").strip()
    if not output_label:
        return None

    # Parse lm/ft from label like "250 lm/ft"
    lm_match = re.search(r"(\d+)\s*lm", output_label, re.IGNORECASE)
    lumens_per_foot = int(lm_match.group(1)) if lm_match else None

    watts_white = _float(row.get(f"Watts per Foot (White Lens) {n}", ""))
    watts_black = _float(row.get(f"Watts per Foot (Black Lens) {n}", ""))
    watts_other = _float(row.get(f"Watts per Foot (Other Lenses) {n}", ""))

    run_white = _float(row.get(f"Max Run Length (White Lens) {n}", ""))
    run_black = _float(row.get(f"Max Run Length (Black Lens) {n}", ""))
    run_other = _float(row.get(f"Max Run Length (Other Lenses) {n}", ""))

    # Build a human-readable watts range string, e.g. "0.8-2.5W"
    all_watts = [w for w in [watts_white, watts_black, watts_other] if w is not None]
    if all_watts:
        mn, mx = min(all_watts), max(all_watts)
        watts_range = f"{mn}-{mx}W" if mn != mx else f"{mn}W"
    else:
        watts_range = None

    # Primary watts_per_foot: Other Lenses (lowest draw, most common install)
    watts_primary = watts_other if watts_other is not None else watts_white

    sku_suffix = f"{lumens_per_foot}lmft" if lumens_per_foot else f"output{n}"
    sku = f"{base['sku_base']}-{sku_suffix}"

    record = {
        "sku": sku,
        "brand": base["brand"],
        "series": base["series"],
        "product_category": base["product_category"],
        "light_type": base["light_type"],
        "input_voltage": base["input_voltage"],
        # Watts range across all lens types
        "watts_per_foot": watts_primary,
        "watts_per_foot_white_lens": watts_white,
        "watts_per_foot_black_lens": watts_black,
        "watts_per_foot_other_lenses": watts_other,
        "watts_range_display": watts_range,
        # Lumens
        "lumens_per_foot": lumens_per_foot,
        "output_label": output_label,
        # Electrical
        "cri_typical": base["cri_typical"],
        # Max run length (most permissive / best case)
        "voltage_drop_max_run_length_ft": _max_run(
            row.get(f"Max Run Length (White Lens) {n}", ""),
            row.get(f"Max Run Length (Black Lens) {n}", ""),
            row.get(f"Max Run Length (Other Lenses) {n}", ""),
        ),
        "max_run_white_lens_ft": run_white,
        "max_run_black_lens_ft": run_black,
        "max_run_other_lenses_ft": run_other,
        # Control
        "supported_dimming_protocols": base["dimming_protocols"],
        # Color
        "cct_available": base["cct_available"],
        # Environment
        "environment_rating": base["environment_rating"],
        "ip_rating": base["ip_rating"],
        # Options
        "lens_appearance": base["lens_appearance"],
        "finish": base["finish"],
        # Mounting methods have been translated from CSV hardware accessory
        # names to seed vocabulary by _map_mounting_methods().
        "mounting_methods": base["mounting_methods"],
        # Media / links (shown on recommendation cards)
        "image_hero_url": base["image_hero_url"],
        "spec_sheet_url": base["spec_sheet_url"],
    }

    # Remove keys whose value is None to keep the JSON lean — except the media
    # link fields, which are always kept (as null when absent) so the frontend
    # and data owners can see they exist and are ready to populate.
    _ALWAYS_KEEP = {"image_hero_url", "spec_sheet_url"}
    return {k: v for k, v in record.items() if v is not None or k in _ALWAYS_KEEP}


# ---------------------------------------------------------------------------
# Row -> list of records
# ---------------------------------------------------------------------------

def row_to_records(row: dict) -> list:
    product_name = row.get("Product Name", "").strip()
    if not product_name:
        return []

    base = {
        "sku_base": _sanitize_sku(product_name),
        "brand": "ilLumenate Lighting",
        "series": product_name,
        "product_category": _infer_category(product_name),
        "light_type": _infer_light_type(product_name),
        "input_voltage": _parse_input_voltage(row.get("Input Voltage", "")),
        "cri_typical": _cri_numeric(row.get("CRI Quality", "")),
        "dimming_protocols": _split(row.get("Dimming Protocols", "")),
        "cct_available": _parse_cct_cells(row),
        "environment_rating": _parse_environment(row.get("Environment Ratings", "")),
        "ip_rating": _parse_ip(row.get("Certifications", "")),
        "lens_appearance": _split(row.get("Lenses", "")),
        "finish": _split(row.get("Finish", "")),
        "mounting_methods": _map_mounting_methods(_split(row.get("Available Mountings", ""))),
        # Hero image URL for recommendation cards (CSV column custom_image_hero).
        "image_hero_url": _clean_url(row.get("custom_image_hero", "")),
        # Spec sheet link — not yet present in the CSV export. Falls back to a
        # dedicated column if/when one is added; otherwise stays null.
        "spec_sheet_url": _clean_url(
            row.get("Spec Sheet URL", "") or row.get("custom_spec_sheet_url", "")
        ),
    }

    records = []
    for n in range(1, 9):
        rec = _build_output_record(row, n, base)
        if rec:
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Append ERP spec-sheet CSV rows to products.seed.json"
    )
    parser.add_argument("csv_file", help="Path to the exported CSV file")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing records whose SKU already exists in the seed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated records as JSON without writing to disk",
    )
    parser.add_argument(
        "--seed",
        default=str(SEED_PATH),
        metavar="PATH",
        help=f"Path to products.seed.json (default: {SEED_PATH})",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    seed_path = Path(args.seed)
    if not seed_path.exists():
        print(f"ERROR: seed file not found: {seed_path}", file=sys.stderr)
        sys.exit(1)

    with open(seed_path, encoding="utf-8") as f:
        seed = json.load(f)

    existing_skus = {p["sku"] for p in seed["products"]}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        new_records = []
        for row in reader:
            new_records.extend(row_to_records(row))

    if not new_records:
        print("No records generated — check that the CSV has Product Name and Output Options columns.")
        sys.exit(0)

    added = skipped = overwritten = 0
    for rec in new_records:
        sku = rec["sku"]
        if sku in existing_skus:
            if args.overwrite:
                seed["products"] = [p for p in seed["products"] if p["sku"] != sku]
                seed["products"].append(rec)
                overwritten += 1
                print(f"  OVERWRITE: {sku}")
            else:
                print(f"  SKIP (already exists, use --overwrite to replace): {sku}")
                skipped += 1
        else:
            seed["products"].append(rec)
            existing_skus.add(sku)
            added += 1
            print(f"  ADD: {sku}")

    print(f"\nResults: {added} added, {overwritten} overwritten, {skipped} skipped")
    print(f"Total records in seed after import: {len(seed['products'])}")

    if args.dry_run:
        print("\n--- DRY RUN: generated records (not written) ---")
        print(json.dumps(new_records, indent=2, ensure_ascii=False))
        return

    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nWritten: {seed_path}")


if __name__ == "__main__":
    main()
