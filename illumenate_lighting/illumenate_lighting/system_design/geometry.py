# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Profile and accessory cross-sections (plan H8.8).

``cross_section_json`` holds closed outlines in 1/1000 inch with the origin at the channel bottom
centre: ``{"body": [x, y, ...], "lens": [...], "clip": [...]}``, the visualizer's ``CAD_SH01`` format.
Extra views (``swivelFront``, ``swivelPlan``) are kept as given. SH01 is seeded from
``seed/sh01_cross_section.json`` (WP-1.5); DXF extraction from ``cross_section_file`` comes later.
"""

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent / "seed"
SH01_SEED = SEED_DIR / "sh01_cross_section.json"
OUTLINES = ("body", "lens", "clip")


def load_sh01_seed():
	return json.loads(SH01_SEED.read_text(encoding="utf-8"))


def cross_section_problems(value):
	"""Return a list of problems with a ``cross_section_json`` value (empty is fine)."""
	if value in (None, ""):
		return []
	try:
		data = json.loads(value) if isinstance(value, str) else value
	except ValueError:
		return ["Cross-section outlines must be valid JSON"]
	if not isinstance(data, dict):
		return ["Cross-section outlines must be a JSON object"]
	if "body" not in data:
		return ["Cross-section outlines need a body outline"]
	problems = []
	for name in OUTLINES:
		if name not in data:
			continue
		points = data[name]
		if (
			not isinstance(points, list)
			or len(points) < 6
			or len(points) % 2
			or not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in points)
		):
			problems.append(f"The {name} outline must be a flat list of at least three x, y points")
	return problems
