"""Convert Illustrator (.ai, PDF-compatible) or PDF artwork to SVG for spec sheets.

Spec sheet drawings are placed at 1:1, so the SVG keeps the artboard size in
points. Text is converted to outlines: an SVG used as an image cannot load the
sheet's fonts, and outlines keep the dimension labels identical to Illustrator.

Usage:
	python -m tools.spec_sheets.convert_artwork INPUT.ai OUTPUT.svg [--page N]

Requires PyMuPDF (``pip install pymupdf``). This runs on an authoring machine;
the ERPNext server only ever receives SVG, PNG or JPEG files.
"""

import argparse
from pathlib import Path

import pymupdf


def convert(source, target, page_number=1):
	document = pymupdf.open(source)
	if document.page_count < page_number:
		raise ValueError(f"{source} has {document.page_count} artboard(s)")
	page = document[page_number - 1]
	svg = page.get_svg_image(text_as_path=True)
	Path(target).write_text(svg, encoding="utf-8")
	return page.rect.width, page.rect.height


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("source")
	parser.add_argument("target")
	parser.add_argument("--page", type=int, default=1, help="Artboard number (1-based)")
	args = parser.parse_args()
	width, height = convert(args.source, args.target, args.page)
	print(f"Wrote {args.target} ({width:g} x {height:g} pt)")


if __name__ == "__main__":
	main()
