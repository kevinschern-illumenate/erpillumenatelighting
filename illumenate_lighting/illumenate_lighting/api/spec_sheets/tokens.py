# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design tokens measured from the InDesign spec sheet exports.

Units are PDF points (1/72 in). Tracking is InDesign tracking in 1/1000 em.
Source: St. Helens [SF] Static White spec sheet (InDesign 20.5 export), measured
with ``tools/spec_sheets/fidelity.py extract``. Colours that a brand may change
are named roles; ``brand_colors`` supplies the ilLumenate values.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
MARGIN = 36.0
CONTENT_RIGHT = PAGE_WIDTH - MARGIN

ILLUMENATE_COLORS = {
	"text": "#231f20",
	"muted": "#a2abb6",
	"bullet": "#9fabb7",
	"rule": "#d1d6db",
	"caption": "#7f8081",
	"accent_product": "#fdad0d",
	"accent_length": "#00588c",
	"accent_power": "#ac212a",
}


@dataclass(frozen=True)
class TextStyle:
	font: str
	size: float
	tracking: float = 0
	color: str = "text"

	@property
	def letter_spacing(self):
		return self.tracking * self.size / 1000


STYLES = {
	"title": TextStyle("Manrope-Bold", 20),
	"sublabel": TextStyle("Manrope-Bold", 8.78, 7),
	"section": TextStyle("Manrope-Bold", 8.78, 7),
	"spec_label": TextStyle("Manrope-SemiBold", 7.8, -12),
	"spec_value": TextStyle("Poppins-Light", 7.8, -12),
	"statement": TextStyle("Poppins-Light", 7.8, -12),
	"caption": TextStyle("Poppins-Regular", 7.8, -12),
	"footer_label": TextStyle("Manrope-Regular", 8, 50),
	"footer_text": TextStyle("Poppins-Light", 7, 0, "muted"),
	"page_number": TextStyle("Poppins-Medium", 7),
}

# Page chrome shared by every family.
HERO = {"x": 36.0, "y": 36.0, "size": 144.0, "radius": 14.4}
# The logo artboard (309.26 x 205pt for the line logos) is placed at 40 %.
LOGO = {"x": 457.76, "y": 31.8, "scale": 0.4}
TITLE = {"x": 198.0, "first_baseline": 57.32, "leading": 24.0, "sublabel_baseline": 109.98}
SPEC_LINE_TOP = {"y": 130.34, "height": 3.6}
SPEC_LINE_BOTTOM = {"y": 704.41, "height": 3.6}
# Rating/certification icons are 72-unit artboards that InDesign scales to 24.55pt.
ICON_ROW = {"x": 198.3, "y": 155.1, "size": 24.55, "pitch": 29.45}
LISTING_STATEMENT = {"baseline": 180.0, "icon_size": 10.7, "icon_top": 169.2}

FOOTER = {
	"label_baseline": 731.21,
	"rule_y": 731.0,
	"rule_width": 0.5,
	# (label, label x, rule start, rule end)
	"fields": (
		("project_name", "PROJECT NAME", 36.0, 100.8, 208.8),
		("fixture_type", "FIXTURE TYPE", 233.17, 292.1, 400.1),
		("location", "LOCATION", 424.43, 468.0, 576.0),
	),
	"first_line_baseline": 748.0,
	"second_line_baseline": 756.0,
	"bullet_radius": 1.0,
	"bullet_rise": 2.0,
	"bullet_gap_after": 3.85,
}

# Specifications table.
SPEC_TABLE = {
	"section_to_first_row": 31.42,
	"label_x": 37.44,
	"value_x0": 192.9,
	"value_x1": 576.0,
	"row_pitch": 15.84,
	"value_baseline_shift": -0.07,
	"rule_below_baseline": 3.7,
	"rule_width": 0.25,
	"band_top_above_baseline": 12.14,
	"band_height": 15.8,
	"after_table_to_section": 43.53,
}

# Drawings section (FIXTURE DIMENSIONS).
# Drawings are placed at 1:1 from the artboard, left to right with a fixed gap.
# A captioned drawing ("Side View") sits lower to make room for its caption.
DRAWINGS = {"top_below_section": 22.33, "caption_below_section": 22.88, "caption_offset": 9.0, "gap": 26.1}

# CCT band sampled from the InDesign "27K-40K Fill Gradient" swatch (Phase 2
# derives stops from ilL-Attribute-CCT.hex_color).
CCT_GRADIENT = (
	("#ffcc68", 1.0, 0.0),
	("#ffd575", 1.0, 6.13),
	("#ffe184", 1.0, 12.39),
	("#feeb92", 1.0, 18.64),
	("#fdf3a2", 1.0, 24.90),
	("#fcf7b0", 1.0, 31.16),
	("#fcf7b8", 1.0, 37.42),
	("#fcf8c0", 1.0, 43.68),
	("#fdfaca", 1.0, 49.93),
	("#fdfad1", 1.0, 56.19),
	("#fefbd9", 1.0, 62.45),
	("#fefce1", 1.0, 68.71),
	("#fdfce6", 1.0, 74.97),
	("#fcfced", 1.0, 81.23),
	("#fbfcf3", 1.0, 87.48),
	("#fafcf8", 1.0, 93.74),
	("#f9fbfd", 1.0, 100.0),
)


SPEC_LINES_FILE = Path(__file__).resolve().parent / "spec_lines.json"


@cache
def _spec_lines():
	return json.loads(SPEC_LINES_FILE.read_text(encoding="utf-8"))


def spec_line_stops(code):
	"""Gradient stops for a product line's spec line (SW, DW, TW, FS, CC, PS, OTHER).

	Extracted from the InDesign spec sheets by ``tools/spec_sheets/extract_indesign.py``.
	"""
	lines = _spec_lines()
	if code not in lines:
		raise ValueError(f"Unknown spec line {code!r}; expected one of {', '.join(sorted(lines))}")
	return [tuple(stop) for stop in lines[code]["stops"]]


# Which spec line (gradient bar and logo) a product uses.
SPEC_LINE_BY_SPECTRUM = {
	"Static White": "SW",
	"Dim to Warm": "DW",
	"Tunable White": "TW",
	"Full Spectrum": "FS",
	"RGB": "CC",
	"RGB+W": "CC",
	"RGBW": "CC",
	"RGB+TW": "CC",
	"RGBTW": "CC",
	"Horticulture": "SW",
}
SPEC_LINE_BY_FAMILY = {"Driver": "PS", "Controller": "PS", "Extrusion Kit": "OTHER", "Accessory": "OTHER"}


def spec_line_for(family, spectrum_type=None):
	"""Spec line code for a product: drivers/controllers and kits by family, light sources by spectrum."""
	if family in SPEC_LINE_BY_FAMILY:
		return SPEC_LINE_BY_FAMILY[family]
	if spectrum_type not in SPEC_LINE_BY_SPECTRUM:
		raise ValueError(f"No spec line for LED package spectrum type {spectrum_type!r}")
	return SPEC_LINE_BY_SPECTRUM[spectrum_type]


def brand_colors(brand=None):
	colors = dict(ILLUMENATE_COLORS)
	colors.update((brand or {}).get("colors") or {})
	return colors
