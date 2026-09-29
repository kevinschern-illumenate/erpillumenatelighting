"""Extract spec line gradients and colour swatches from InDesign spec sheet files.

Each product line's spec sheet (.indd) places a "Spec Line_<LINE>.png" gradient bar
and keeps a full-resolution copy of it inside the document. This tool pulls that
image out, checks it is a purely horizontal gradient, and fits the fewest linear
colour stops that reproduce every pixel within ``--tolerance`` levels (0-255). It
also reads the document's solid colour swatches from its XMP metadata.

The result, ``api/spec_sheets/spec_lines.json``, is what the renderer draws, so
spec lines are vector gradients rather than placed images.

Usage:
	python -m tools.spec_sheets.extract_indesign INDD [INDD ...] [--tolerance 1.0]

Requires Pillow.
"""

import argparse
import io
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "illumenate_lighting/illumenate_lighting/api/spec_sheets/spec_lines.json"
LINES = {
	"Static White": "SW",
	"Dim to Warm": "DW",
	"Tunable White": "TW",
	"Full Spectrum": "FS",
	"Color Changing": "CC",
	"Power Supply": "PS",
	"Extrusion Kit": "OTHER",
}
PNG = b"\x89PNG\r\n\x1a\n"


def line_code(path):
	for name, code in LINES.items():
		if name in Path(path).name:
			return code, name
	raise ValueError(f"Cannot tell the product line of {path}")


def swatches(content):
	"""Solid RGB swatches from the document XMP (name -> hex)."""
	found = {}
	for packet in re.findall(rb"<\?xpacket begin.*?<\?xpacket end[^>]*>", content, re.S):
		for name, body in re.findall(
			rb"<xmpG:swatchName>([^<]+)</xmpG:swatchName>(.*?)</rdf:li>", packet, re.S
		):
			values = dict(re.findall(rb"<xmpG:(mode|red|green|blue)>([^<]+)", body))
			if values.get(b"mode") == b"RGB":
				rgb = (round(float(values[key])) for key in (b"red", b"green", b"blue"))
				found[name.decode("utf-8", "replace")] = "#{:02x}{:02x}{:02x}".format(*rgb)
	return dict(sorted(found.items()))


def embedded_spec_line(content):
	"""The widest embedded PNG with a spec-line aspect ratio (> 100:1)."""
	best = None
	for match in re.finditer(re.escape(PNG), content):
		end = content.find(b"IEND", match.start())
		if end == -1:
			continue
		data = content[match.start() : end + 8]
		try:
			image = Image.open(io.BytesIO(data))
			image.load()
		except Exception:
			continue
		width, height = image.size
		if width / max(height, 1) > 100 and (best is None or width > best.size[0]):
			best = image.convert("RGBA")
	if best is None:
		raise ValueError("No embedded spec line image found")
	return best


def fit_stops(row, tolerance):
	"""Greedy piecewise-linear fit over RGBA; returns breakpoint indexes."""

	def fits(start, end):
		span = end - start
		for k in range(start + 1, end):
			t = (k - start) / span
			for channel in range(4):
				expected = row[start][channel] + (row[end][channel] - row[start][channel]) * t
				if abs(expected - row[k][channel]) > tolerance:
					return False
		return True

	stops, start, last = [0], 0, len(row) - 1
	while start < last:
		low, high, best = start + 1, last, start + 1
		while low <= high:
			middle = (low + high) // 2
			if fits(start, middle):
				best, low = middle, middle + 1
			else:
				high = middle - 1
		stops.append(best)
		start = best
	return stops


def extract(path, tolerance):
	content = Path(path).read_bytes()
	code, name = line_code(path)
	image = embedded_spec_line(content)
	width, height = image.size
	pixels = image.load()
	middle = height // 2
	# Edge rows and the first/last column are anti-aliased coverage, not colour.
	row = [pixels[x, middle] for x in range(width)]
	row[0], row[-1] = row[1], row[-2]
	for y in range(1, height - 1):
		if any(pixels[x, y][:3] != row[x][:3] for x in range(1, width - 1)):
			raise ValueError(f"{name} spec line is not a horizontal gradient (row {y})")
	stops = [
		[
			"#{:02x}{:02x}{:02x}".format(*row[index][:3]),
			round(row[index][3] / 255, 3),
			round(100 * index / (width - 1), 2),
		]
		for index in fit_stops(row, tolerance)
	]
	return code, {
		"name": name,
		"source": Path(path).name,
		"source_pixels": [width, height],
		"tolerance": tolerance,
		"stops": stops,
		"swatches": swatches(content),
	}


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("indd", nargs="+")
	parser.add_argument("--tolerance", type=float, default=1.0)
	args = parser.parse_args()
	lines = json.loads(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else {}
	for path in args.indd:
		code, data = extract(path, args.tolerance)
		lines[code] = data
		print(f"{code}: {data['name']}, {len(data['stops'])} stops from {data['source_pixels']} px")
	TARGET.write_text(
		json.dumps(dict(sorted(lines.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
	)
	print(f"Wrote {TARGET}")


if __name__ == "__main__":
	main()
