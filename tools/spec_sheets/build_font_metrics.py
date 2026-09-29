"""Build ``fonts/metrics.json`` for spec sheet text measurement.

Layout needs text widths (right-aligned composites, bullets, wrapping and
overflow checks). The server does not ship a shaper, so this tool shapes every
glyph and kerning pair of the supported character set with HarfBuzz (the shaper
Chromium uses) and stores advances in font units.

Usage:
	python -m tools.spec_sheets.build_font_metrics

Requires ``pip install uharfbuzz fonttools``.
"""

import json
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont

FONTS_DIR = (
	Path(__file__).resolve().parents[2] / "illumenate_lighting/illumenate_lighting/api/spec_sheets/fonts"
)
# Printable ASCII, Latin-1 and the typographic marks used on spec sheets. Pair
# deltas include kerning and two-character standard ligatures (Manrope "tt"),
# matching InDesign and Chromium defaults.
CHARSET = (
	[chr(c) for c in range(0x20, 0x7F)]
	+ [chr(c) for c in range(0xA0, 0x100)]
	+ list(
		"\u2013\u2014\u2018\u2019\u201c\u201d\u2022\u2026\u00d7\u2212\u2264\u2265\u00b1\u00b0\u2122\u20ac"
	)  # dashes, quotes, bullet, ellipsis, times, minus, comparison, plus-minus, degree, TM, euro
)


def _shape(font, text):
	buffer = hb.Buffer()
	buffer.add_str(text)
	buffer.guess_segment_properties()
	hb.shape(font, buffer, {"kern": True, "liga": True})
	return buffer


def build_font(path):
	blob = hb.Blob.from_file_path(str(path))
	face = hb.Face(blob)
	font = hb.Font(face)
	cmap = TTFont(path).getBestCmap()
	chars = [c for c in CHARSET if ord(c) in cmap]
	advances = {c: sum(p.x_advance for p in _shape(font, c).glyph_positions) for c in chars}
	kerning = {}
	for left in chars:
		for right in chars:
			pair = sum(p.x_advance for p in _shape(font, left + right).glyph_positions)
			delta = pair - advances[left] - advances[right]
			if delta:
				kerning[left + right] = delta
	return {"units_per_em": face.upem, "advances": advances, "kerning": kerning}


def main():
	metrics = {path.stem: build_font(path) for path in sorted(FONTS_DIR.glob("*.ttf"))}
	target = FONTS_DIR / "metrics.json"
	target.write_text(json.dumps(metrics, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
	for name, data in metrics.items():
		print(f"{name}: {len(data['advances'])} glyphs, {len(data['kerning'])} kerning pairs")
	print(f"Wrote {target} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
	main()
