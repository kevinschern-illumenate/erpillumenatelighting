"""Extract Phase 0 stand-in assets from an InDesign-exported spec sheet PDF.

The designer's own exports (SVG drawings with outlined text, PNG photos,
icons, logo and spec lines) replace these files once they are uploaded to
ERPNext. Until then, cutting them out of the published PDF lets the generated
page be compared with the golden without any asset differences.

Usage:
	python -m tools.spec_sheets.extract_standins GOLDEN.pdf OUTPUT_DIR

Requires PyMuPDF (``pip install pymupdf``).
"""

import argparse
import json
from pathlib import Path

import pymupdf

# St. Helens [SF] Static White page 1, measured in PDF points (x0, y0, x1, y1).
VECTOR_CLIPS = {
	"icon_24vdc.svg": (198.3, 155.1, 222.9, 179.7),
	"icon_dry.svg": (227.8, 155.1, 252.3, 179.7),
	"icon_damp.svg": (257.3, 155.1, 281.8, 179.7),
	"icon_wet.svg": (286.6, 155.1, 311.1, 179.7),
	"icon_ul.svg": (515.9, 169.2, 526.6, 179.9),
	"drawing_cross_section.svg": (35.5, 559.2, 144.5, 618.0),
	"drawing_side_view.svg": (169.6, 566.5, 577.6, 613.5),
}
# Raster images keyed by the box they occupy on page 1.
RASTER_BOXES = {
	"hero.jpg": (36.0, 36.0),
	"logo.png": (463.6, 36.0),
	"spec_line.png": (0.0, 130.3),
}


def _isolated_copy(source, page_number, rect):
	"""Copy one page with everything outside ``rect`` removed, so the SVG stays small."""
	copy = pymupdf.open()
	copy.insert_pdf(source, from_page=page_number, to_page=page_number)
	page = copy[0]
	width, height = page.rect.width, page.rect.height
	for band in (
		(0, 0, width, rect.y0),
		(0, rect.y1, width, height),
		(0, rect.y0, rect.x0, rect.y1),
		(rect.x1, rect.y0, width, rect.y1),
	):
		if band[2] > band[0] and band[3] > band[1]:
			page.add_redact_annot(pymupdf.Rect(band))
	page.apply_redactions(
		images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
		graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
		text=pymupdf.PDF_REDACT_TEXT_REMOVE,
	)
	return copy


def _clip_to_svg(source, page_number, clip):
	rect = pymupdf.Rect(clip)
	isolated = _isolated_copy(source, page_number, rect)
	scratch = pymupdf.open()
	page = scratch.new_page(width=rect.width, height=rect.height)
	page.show_pdf_page(page.rect, isolated, 0, clip=rect)
	# Outlined text matches the recommended designer export.
	return page.get_svg_image(text_as_path=True)


def _image_bytes(document, xref, smask):
	if not smask:
		info = document.extract_image(xref)
		return info["image"], info["ext"]
	pixmap = pymupdf.Pixmap(document, xref)
	if pixmap.colorspace and pixmap.colorspace.n != 3:
		pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
	with_alpha = pymupdf.Pixmap(pixmap, pymupdf.Pixmap(document, smask))
	return with_alpha.tobytes("png"), "png"


def extract(golden, output_dir, page_number=0):
	output = Path(output_dir)
	output.mkdir(parents=True, exist_ok=True)
	document = pymupdf.open(golden)
	page = document[page_number]
	written = {}
	for name, clip in VECTOR_CLIPS.items():
		(output / name).write_text(_clip_to_svg(document, page_number, clip), encoding="utf-8")
		written[name] = {"box": clip}
	for xref, smask, *_ in page.get_images(full=True):
		for rect in page.get_image_rects(xref):
			for name, origin in RASTER_BOXES.items():
				if abs(rect.x0 - origin[0]) < 1 and abs(rect.y0 - origin[1]) < 1 and name not in written:
					content, ext = _image_bytes(document, xref, smask)
					if not name.endswith(ext) and not (ext == "jpeg" and name.endswith(".jpg")):
						name = f"{Path(name).stem}.{ext}"
					(output / name).write_bytes(content)
					written[name] = {"box": tuple(round(v, 2) for v in rect)}
	(output / "standins.json").write_text(
		json.dumps({"source": Path(golden).name, "page": page_number + 1, "assets": written}, indent=1),
		encoding="utf-8",
	)
	return written


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("golden")
	parser.add_argument("output_dir")
	args = parser.parse_args()
	for name, info in extract(args.golden, args.output_dir).items():
		print(f"{name}: {info['box']}")


if __name__ == "__main__":
	main()
