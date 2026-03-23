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

# ── Webflow configurator step defaults ─────────────────────────────────
CONFIGURATOR_STEP_TYPES = {
    "Environment Rating": "Dry/Wet",
    "CCT": "CCT",
    "Lens Appearance": "Lens",
    "Output Level": "Output",
    "Mounting Method": "Mounting",
    "Finish": "Finish",
    "Length": "Length",
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
