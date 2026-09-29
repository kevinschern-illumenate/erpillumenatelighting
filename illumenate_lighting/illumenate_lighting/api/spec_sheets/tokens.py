# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design tokens measured from the InDesign spec sheet exports.

Units are PDF points (1/72 in). Tracking is InDesign tracking in 1/1000 em.
Source: St. Helens [SF] Static White spec sheet (InDesign 20.5 export), measured
with ``tools/spec_sheets/fidelity.py extract``. Colours that a brand may change
are named roles; ``brand_colors`` supplies the ilLumenate values.
"""

from dataclasses import dataclass

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
LOGO = {"x": 463.566, "y": 36.0, "width": 112.289, "height": 72.0}
TITLE = {"x": 198.0, "first_baseline": 57.32, "leading": 24.0, "sublabel_baseline": 109.98}
SPEC_LINE_TOP = {"y": 130.34, "height": 3.6}
SPEC_LINE_BOTTOM = {"y": 704.41, "height": 3.6}
ICON_ROW = {"x": 198.3, "y": 155.1, "gap": 4.9}
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
DRAWINGS = {"caption_below_section": 22.88}

# CCT band sampled from the InDesign "27K-40K Fill Gradient" swatch (Phase 2
# derives stops from ilL-Attribute-CCT.hex_color).
CCT_GRADIENT = (
	("#ffcc68", 0.0),
	("#ffd575", 6.13),
	("#ffe184", 12.39),
	("#feeb92", 18.64),
	("#fdf3a2", 24.90),
	("#fcf7b0", 31.16),
	("#fcf7b8", 37.42),
	("#fcf8c0", 43.68),
	("#fdfaca", 49.93),
	("#fdfad1", 56.19),
	("#fefbd9", 62.45),
	("#fefce1", 68.71),
	("#fdfce6", 74.97),
	("#fcfced", 81.23),
	("#fbfcf3", 87.48),
	("#fafcf8", 93.74),
	("#f9fbfd", 100.0),
)


def brand_colors(brand=None):
	colors = dict(ILLUMENATE_COLORS)
	colors.update((brand or {}).get("colors") or {})
	return colors
