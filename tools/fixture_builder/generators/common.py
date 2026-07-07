"""Shared constants and helper utilities for CSV generators."""

from __future__ import annotations

import csv
import io
import os
from typing import Any

# ── Finish → Endcap Color mapping (global convention) ──────────────────
FINISH_TO_ENDCAP_COLOR = {
    "WH": "WH",
    "BK": "BK",
    "SV": "GR",
}

FINISH_NAMES = {
    "WH": "White",
    "BK": "Black",
    "SV": "Anodized Silver",
}

ENDCAP_COLOR_NAMES = {
    "WH": "White",
    "BK": "Black",
    "GR": "Grey",
}

LENS_APPEARANCE_CODES = {
    "White": "WH",
    "Black": "BK",
    "Clear": "CL",
    "Frosted": "FR",
}

# ── Item group mappings ────────────────────────────────────────────────
ITEM_GROUPS = {
    "profile": "Profiles",
    "lens": "Lenses",
    "accessory_joiner": "Profile Accessories",
    "accessory_mounting": "Mounting",
    "endcap": "Endcaps",
}

# ── LED package display names ──────────────────────────────────────────
LED_PACKAGE_NAMES = {
    "FS": "Full Spectrum",
    "SW": "Static White",
    "TW": "Tunable White",
}

# ── LED Sheet option type → attribute DocType ──────────────────────────
# The LED Sheet allowed-option child stores a Dynamic Link keyed on
# ``attribute_doctype``. The option_type label does NOT always match the
# DocType suffix (e.g. "Mounting" → "ilL-Attribute-Mounting Method"), so a
# naive ``ilL-Attribute-{option_type}`` derivation is wrong.
LED_SHEET_OPTION_TYPE_TO_ATTRIBUTE_DOCTYPE = {
    "CCT": "ilL-Attribute-CCT",
    "Output Level": "ilL-Attribute-Output Level",
    "Environment Rating": "ilL-Attribute-Environment Rating",
    "Mounting": "ilL-Attribute-Mounting Method",
    "Finish": "ilL-Attribute-Finish",
}


def led_sheet_attribute_doctype(option_type: str) -> str:
    """Return the attribute DocType for an LED Sheet option type."""
    return LED_SHEET_OPTION_TYPE_TO_ATTRIBUTE_DOCTYPE.get(
        option_type, f"ilL-Attribute-{option_type}"
    )


# ── Webflow configurator step defaults ─────────────────────────────────
CONFIGURATOR_STEP_TYPES = {
    "Environment Rating": "Dry/Wet",
    "CCT": "CCT",
    "Lens Appearance": "Lens",
    "Output Level": "Output",
    "Mounting Method": "Mounting",
    "Finish": "Finish",
    "Length": "Length",
    "Feed Direction": "Feed Direction",
    "Power Feed Type": "Power Feed",
    "IP Rating": "IP Rating",
    "PCB Mounting": "PCB Mounting",
    "PCB Finish": "PCB Finish",
    "Endcap Style": "Endcap Style",
}

# ── Tape / Neon constants ──────────────────────────────────────────────
TAPE_NEON_OPTION_TYPES = {
    "CCT": "cct",
    "Output Level": "output_level",
    "Environment Rating": "environment_rating",
    "IP Rating": "ip_rating",
    "Feed Direction": "feed_direction",
    "Power Feed Type": "power_feed_type",
    "PCB Mounting": "pcb_mounting",
    "PCB Finish": "pcb_finish",
    "Mounting Method": "mounting_method",
    "Finish": "finish",
    "Endcap Style": "endcap_style",
}

TAPE_NEON_CONFIGURATOR_STEPS = [
    "Environment Rating",
    "CCT",
    "Output Level",
    "Length",
    "Feed Direction",
]

TAPE_ITEM_GROUPS = {
    "LED Tape": "LED Tape",
    "LED Neon": "LED Neon",
}


def write_csv(filepath: str, headers: list[str], rows: list[list[Any]]) -> int:
    """Write a CSV file with the given headers and rows. Returns row count."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
    return len(rows)


def blank_row(ncols: int) -> list[str]:
    """Return a list of ncols empty strings (for continuation rows)."""
    return [""] * ncols
