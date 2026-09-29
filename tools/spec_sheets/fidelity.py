"""Compare a generated spec sheet PDF with its InDesign golden.

Checks, per page:
  * words: same text, font, size (±size_pt), colour, baseline and x (±position_pt), width (±width_pt)
  * images: every golden raster image has a generated image in the same box (±position_pt)
  * rules: horizontal/vertical strokes cover the same extents with the same colour and width
  * raster: share of visibly different pixels at 150 dpi, plus a diff image

Text inside ``asset_boxes`` (drawings and icons, whose labels are artwork) is
compared by the raster check only, as are golden images listed in ``vector_images``
(drawn as vectors on purpose, e.g. spec line gradients). ``approved_differences`` lists deliberate
content changes; with ``line_shifts`` the rest of that line may move sideways.

Usage:
	python -m tools.spec_sheets.fidelity compare CONFIG.json GENERATED.pdf [--report DIR]
	python -m tools.spec_sheets.fidelity extract FILE.pdf [--page N]

Requires PyMuPDF (``pip install pymupdf``).
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SUBSET = re.compile(r"^[A-Z]{6}\+")


@dataclass
class Word:
	text: str
	font: str
	size: float
	color: str
	x0: float
	x1: float
	baseline: float

	@property
	def center(self):
		return ((self.x0 + self.x1) / 2, self.baseline)


def _font_name(name):
	return SUBSET.sub("", name)


def extract_words(page):
	"""Split spans into words, keeping each word's own font, size, colour and extent."""
	words = []
	for block in page.get_text("rawdict")["blocks"]:
		for line in block.get("lines", []):
			for span in line["spans"]:
				font, size, color = _font_name(span["font"]), span["size"], f"#{span['color']:06x}"
				current = []
				for char in [*span["chars"], None]:
					if char is None or not char["c"].strip():
						if current:
							words.append(
								Word(
									"".join(c["c"] for c in current),
									font,
									round(size, 3),
									color,
									current[0]["origin"][0],
									current[-1]["bbox"][2],
									current[0]["origin"][1],
								)
							)
						current = []
					else:
						current.append(char)
	return words


def extract_images(page):
	boxes = []
	for info in page.get_image_info():
		x0, y0, x1, y1 = info["bbox"]
		if x1 - x0 > 1 and y1 - y0 > 1:
			boxes.append((round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)))
	return sorted(set(boxes))


def extract_rules(page, max_thickness=0.1):
	"""Axis-aligned stroked lines, merged per (orientation, position, colour, width)."""
	segments = {}
	for drawing in page.get_drawings():
		if drawing.get("type") != "s" or not drawing.get("color"):
			continue
		color = "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in drawing["color"][:3]))
		width = round(drawing.get("width") or 0, 2)
		for item in drawing["items"]:
			if item[0] != "l":
				continue
			a, b = item[1], item[2]
			if abs(a.y - b.y) <= max_thickness:
				key = ("h", round(a.y, 1), color, width)
				segments.setdefault(key, []).append((min(a.x, b.x), max(a.x, b.x)))
			elif abs(a.x - b.x) <= max_thickness:
				key = ("v", round(a.x, 1), color, width)
				segments.setdefault(key, []).append((min(a.y, b.y), max(a.y, b.y)))
	merged = []
	for key, spans in segments.items():
		spans.sort()
		start, end = spans[0]
		for s, e in spans[1:]:
			if s <= end + 0.2:
				end = max(end, e)
			else:
				merged.append((*key, round(start, 1), round(end, 1)))
				start, end = s, e
		merged.append((*key, round(start, 1), round(end, 1)))
	return sorted(merged)


def _inside(word, boxes):
	cx, cy = (word.x0 + word.x1) / 2, word.baseline - word.size * 0.3
	return any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in boxes)


def compare_words(golden, generated, tolerances, asset_boxes=(), approved=()):
	approved = list(approved)
	replacement = {item["golden"]: item["generated"] for item in approved}
	shifted_lines = set()
	for item in approved:
		if item.get("line_shifts"):
			shifted_lines |= {round(w.baseline, 1) for w in golden if w.text == item["golden"]}
	golden = [w for w in golden if not _inside(w, asset_boxes)]
	generated = [w for w in generated if not _inside(w, asset_boxes)]
	unused = list(generated)
	failures, matched, deltas = [], 0, []
	for word in golden:
		expected_text = replacement.get(word.text, word.text)
		candidates = [w for w in unused if w.text == expected_text]
		if not candidates:
			failures.append({"kind": "missing", "golden": asdict(word)})
			continue
		best = min(candidates, key=lambda w: abs(w.x0 - word.x0) + abs(w.baseline - word.baseline))
		unused.remove(best)
		problems = []
		if best.font != word.font:
			problems.append(f"font {best.font} != {word.font}")
		if abs(best.size - word.size) > tolerances["size_pt"]:
			problems.append(f"size {best.size} != {word.size}")
		if best.color != word.color:
			problems.append(f"color {best.color} != {word.color}")
		dy = best.baseline - word.baseline
		if abs(dy) > tolerances["position_pt"]:
			problems.append(f"baseline {dy:+.2f}pt")
		line_may_shift = round(word.baseline, 1) in shifted_lines
		dx = best.x0 - word.x0
		dw = (best.x1 - best.x0) - (word.x1 - word.x0)
		if not line_may_shift and abs(dx) > tolerances["position_pt"]:
			problems.append(f"x {dx:+.2f}pt")
		if expected_text == word.text and abs(dw) > tolerances["width_pt"]:
			problems.append(f"width {dw:+.2f}pt")
		if not line_may_shift:
			deltas.append((abs(dx), abs(dy), abs(dw)))
		if problems:
			failures.append({"kind": "mismatch", "text": word.text, "problems": problems})
		else:
			matched += 1
	for word in unused:
		failures.append({"kind": "unexpected", "generated": asdict(word)})
	worst = [max((d[i] for d in deltas), default=0) for i in range(3)]
	return {
		"golden_words": len(golden),
		"matched": matched,
		"max_dx": round(worst[0], 3),
		"max_dy": round(worst[1], 3),
		"max_dwidth": round(worst[2], 3),
		"failures": failures,
	}


def _listed(box, boxes, tolerance=0.5):
	return any(all(abs(a - b) <= tolerance for a, b in zip(box, other, strict=True)) for other in boxes)


def compare_boxes(golden, generated, tolerance):
	missing = [
		box
		for box in golden
		if not any(
			all(abs(a - b) <= tolerance for a, b in zip(box, other, strict=True)) for other in generated
		)
	]
	return {"golden": len(golden), "generated": len(generated), "missing": missing}


def compare_rules(golden, generated, tolerance):
	def found(rule, pool):
		return any(
			rule[0] == other[0]
			and abs(rule[1] - other[1]) <= tolerance
			and rule[2] == other[2]
			and abs(rule[3] - other[3]) <= 0.05
			and abs(rule[4] - other[4]) <= tolerance
			and abs(rule[5] - other[5]) <= tolerance
			for other in pool
		)

	return {
		"golden": len(golden),
		"missing": [rule for rule in golden if not found(rule, generated)],
		"unexpected": [rule for rule in generated if not found(rule, golden)],
	}


def raster_diff(golden_page, generated_page, output=None, dpi=150, threshold=48):
	from PIL import Image, ImageChops

	def pixels(page):
		pix = page.get_pixmap(dpi=dpi, alpha=False)
		return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

	a, b = pixels(golden_page), pixels(generated_page)
	if a.size != b.size:
		return {"error": f"page size differs: {a.size} vs {b.size}"}
	difference = ImageChops.difference(a, b).convert("L")
	mask = difference.point(lambda value: 255 if value > threshold else 0)
	changed = sum(1 for value in mask.getdata() if value)
	if output:
		overlay = Image.blend(a.convert("L").convert("RGB"), b.convert("L").convert("RGB"), 0.5)
		overlay.paste((230, 0, 60), mask=mask)
		overlay.save(output)
	return {
		"changed_ratio": round(changed / (a.size[0] * a.size[1]), 5),
		"diff_image": str(output) if output else None,
	}


def compare(config_path, generated_pdf, report_dir=None):
	config_path = Path(config_path)
	config = json.loads(config_path.read_text(encoding="utf-8"))
	tolerances = config["tolerances"]
	golden_doc = pymupdf.open(config_path.parent / config["golden"])
	generated_doc = pymupdf.open(generated_pdf)
	golden_page = golden_doc[config.get("golden_page", 1) - 1]
	generated_page = generated_doc[config.get("generated_page", 1) - 1]
	report_path = Path(report_dir) if report_dir else None
	if report_path:
		report_path.mkdir(parents=True, exist_ok=True)
	result = {
		"page_size": {
			"golden": list(golden_page.rect),
			"generated": list(generated_page.rect),
			"ok": golden_page.rect == generated_page.rect,
		},
		"words": compare_words(
			extract_words(golden_page),
			extract_words(generated_page),
			tolerances,
			config.get("asset_boxes", ()),
			config.get("approved_differences", ()),
		),
		"images": compare_boxes(
			[box for box in extract_images(golden_page) if not _listed(box, config.get("vector_images", ()))],
			extract_images(generated_page),
			tolerances["position_pt"],
		),
		"rules": compare_rules(
			extract_rules(golden_page), extract_rules(generated_page), tolerances["position_pt"]
		),
		"raster": raster_diff(golden_page, generated_page, report_path / "diff.png" if report_path else None),
		"approved_differences": config.get("approved_differences", []),
	}
	result["passed"] = (
		result["page_size"]["ok"]
		and not result["words"]["failures"]
		and not result["images"]["missing"]
		and not result["rules"]["missing"]
		and "error" not in result["raster"]
		and result["raster"]["changed_ratio"] <= tolerances["raster_changed_ratio"]
	)
	if report_path:
		(report_path / "report.json").write_text(
			json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
		)
	return result


def _summary(result):
	words, raster = result["words"], result["raster"]
	lines = [
		f"page size ok: {result['page_size']['ok']}",
		f"words: {words['matched']}/{words['golden_words']} matched, max dx {words['max_dx']}pt, "
		f"max baseline {words['max_dy']}pt, max width {words['max_dwidth']}pt",
		f"images: {result['images']['golden'] - len(result['images']['missing'])}/{result['images']['golden']} boxes matched",
		f"rules: {result['rules']['golden'] - len(result['rules']['missing'])}/{result['rules']['golden']} matched, "
		f"{len(result['rules']['unexpected'])} unexpected",
		f"raster: {raster.get('changed_ratio', raster.get('error'))} of pixels differ",
	]
	for failure in words["failures"][:40]:
		lines.append(
			f"  word {failure['kind']}: {failure.get('text') or failure.get('golden') or failure.get('generated')} "
			f"{failure.get('problems', '')}"
		)
	for rule in result["rules"]["missing"][:20]:
		lines.append(f"  rule missing: {rule}")
	for rule in result["rules"]["unexpected"][:20]:
		lines.append(f"  rule unexpected: {rule}")
	for box in result["images"]["missing"]:
		lines.append(f"  image missing: {box}")
	lines.append("PASSED" if result["passed"] else "FAILED")
	return "\n".join(lines)


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	commands = parser.add_subparsers(dest="command", required=True)
	compare_cmd = commands.add_parser("compare")
	compare_cmd.add_argument("config")
	compare_cmd.add_argument("generated")
	compare_cmd.add_argument("--report")
	extract_cmd = commands.add_parser("extract")
	extract_cmd.add_argument("pdf")
	extract_cmd.add_argument("--page", type=int, default=1)
	args = parser.parse_args()
	if args.command == "extract":
		page = pymupdf.open(args.pdf)[args.page - 1]
		print(
			json.dumps(
				{
					"page": list(page.rect),
					"words": [asdict(w) for w in extract_words(page)],
					"images": extract_images(page),
					"rules": extract_rules(page),
				},
				indent=1,
				ensure_ascii=False,
			)
		)
		return
	result = compare(args.config, args.generated, args.report)
	print(_summary(result))
	sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
	main()
