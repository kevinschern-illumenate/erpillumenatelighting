"""Render a spec sheet model fixture to PDF without Frappe.

Usage:
	ILL_SPEC_SHEET_CHROMIUM=/path/to/headless_shell \\
		python -m tools.spec_sheets.render_fixture MODEL.json OUTPUT.pdf [--html OUTPUT.html]

Assets are resolved from the ``assets`` directory next to the model.
"""

import argparse
import json
from pathlib import Path

from illumenate_lighting.illumenate_lighting.api.spec_sheets.pages import build_html, placeholders
from illumenate_lighting.illumenate_lighting.api.spec_sheets.render import render_pdf
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import DirectoryAssets


def render_fixture(model_path, output_pdf, output_html=None):
	model_path = Path(model_path)
	model = json.loads(model_path.read_text(encoding="utf-8"))
	html = build_html(model, DirectoryAssets(model_path.parent / "assets"))
	if output_html:
		Path(output_html).write_text(html, encoding="utf-8")
	pdf = render_pdf(html)
	Path(output_pdf).write_bytes(pdf)
	return pdf


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("model")
	parser.add_argument("output")
	parser.add_argument("--html")
	args = parser.parse_args()
	pdf = render_fixture(args.model, args.output, args.html)
	print(f"Wrote {args.output} ({len(pdf)} bytes)")
	model = json.loads(Path(args.model).read_text(encoding="utf-8"))
	for item in placeholders(model):
		print(f"PLACEHOLDER {item}")


if __name__ == "__main__":
	main()
