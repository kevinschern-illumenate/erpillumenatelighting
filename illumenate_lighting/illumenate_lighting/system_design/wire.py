# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Field wire rules shared by the ``ilL-Spec-Wire`` controller and the CSV import (WP-1.4, D7).

Everything here is pure: callers pass plain values and the Item's facts, and get back normalized
values or a list of problems. The engine reads the stored values through A.6 (``wire_type``).
"""

import re

RUN_TYPES = (
	"lv-branch",
	"lv-fixture-whip",
	"class2-dc",
	"class2-dc-multichannel",
	"landscape-ac",
	"dmx",
	"ethernet",
	"spi-data",
	"0-10v",
	"dali",
	"lutron-qs",
	"lutron-ecosystem",
	"wireless",
)
CATEGORIES = {
	"class2-power": "Class 2 Power",
	"building-wire": "Building Wire",
	"cable-assembly": "Cable Assembly",
	"data": "Data",
	"control": "Control",
	"landscape": "Landscape",
	"flex-cord": "Flex Cord",
}
AWG = (
	"24",
	"22",
	"20",
	"18",
	"16",
	"14",
	"12",
	"10",
	"8",
	"6",
	"4",
	"3",
	"2",
	"1",
	"1/0",
	"2/0",
	"3/0",
	"4/0",
)
ROLES = {
	"power": "Power",
	"ground": "Ground",
	"signal": "Signal",
	"data-pair": "Data Pair",
	"channel": "Channel",
}
TEMP_RATINGS = ("60", "75", "90", "105")
AMPACITY_BASES = ("310.16", "402.5 fallback", "Manufacturer")
SALES_MODES = ("Per Foot", "Per Spool")
FOOT_UOMS = ("Foot", "Feet")
SPOOL_UOM = "Spool"

_CONDUCTOR = re.compile(
	r"^(?P<count>\d+)\s*[x\u00d7]\s*#?(?P<awg>\d/0|\d+)\s+(?P<material>cu|al)\s+(?P<stranding>solid|stranded)\s+"
	r"(?P<role>power|ground|signal|data[- ]pair|channel)\s*(?:\((?P<colors>[^)]*)\))?$",
	re.IGNORECASE,
)


def key(text):
	return re.sub(r"[\s_]+", "-", str(text or "").strip().lower())


def category_label(value):
	"""Accept the Desk label or the engine's kebab id; return the Desk label or ``None``."""
	text = str(value or "").strip()
	if text in CATEGORIES.values():
		return text
	return CATEGORIES.get(key(text))


def split_applications(value):
	"""Return ``(run_types, unknown)``; order kept, duplicates dropped."""
	seen, unknown = [], []
	for part in re.split(r"[,;\s]+", str(value or "").strip()):
		name = part.strip().lower()
		if not name:
			continue
		if name not in RUN_TYPES:
			unknown.append(part.strip())
		elif name not in seen:
			seen.append(name)
	return seen, unknown


def colors_list(value):
	return [c.strip() for c in re.split(r"[,/]", str(value or "")) if c.strip()]


def parse_conductors(text):
	"""Parse ``"2x18 Cu stranded power; 1x18 Cu stranded ground (green)"`` into child rows.

	Returns ``(rows, problems)``. Colors in parentheses are separated by ``/`` or ``,``.
	"""
	rows, problems = [], []
	for index, part in enumerate(p.strip() for p in str(text or "").split(";")):
		if not part:
			continue
		match = _CONDUCTOR.match(part)
		if not match:
			problems.append(
				f"Conductor group {index + 1} '{part}' should look like '2x18 Cu stranded power' "
				"(count x AWG, Cu/Al, solid/stranded, power/ground/signal/data pair/channel)"
			)
			continue
		awg = match["awg"]
		if awg not in AWG:
			problems.append(f"Conductor group {index + 1}: AWG {awg} is not supported")
			continue
		row = {
			"count": int(match["count"]),
			"awg": awg,
			"material": "Cu" if match["material"].lower() == "cu" else "Al",
			"stranding": match["stranding"].capitalize(),
			"role": ROLES[key(match["role"])],
		}
		if match["colors"]:
			row["colors"] = ", ".join(colors_list(match["colors"]))
		rows.append(row)
	return rows, problems


def conductor_problems(rows):
	problems = []
	if not rows:
		return ["Add at least one conductor group"]
	for index, row in enumerate(rows, 1):
		count = int(row.get("count") or 0)
		if count < 1:
			problems.append(f"Conductor row {index}: count must be at least 1")
		if row.get("role") == "Data Pair" and count % 2:
			problems.append(f"Conductor row {index}: data pairs need an even conductor count")
		colors = colors_list(row.get("colors"))
		if colors and len(colors) != count:
			problems.append(f"Conductor row {index}: list one color per conductor ({count})")
		for field in ("resistance_ohm_per_kft", "ampacity_a"):
			if row.get(field) not in (None, "") and float(row[field]) <= 0:
				problems.append(f"Conductor row {index}: {field} must be positive when set")
	return problems


def item_problems(item, sales_uom_mode):
	"""``item`` is the Item's facts (``None`` when it does not exist)."""
	if not item:
		return ["Item does not exist"]
	problems = []
	if not item.get("is_sales_item"):
		problems.append(f"Item {item.get('name')} must be a sales item")
	if item.get("disabled"):
		problems.append(f"Item {item.get('name')} is disabled")
	if item.get("has_variants"):
		problems.append(f"Item {item.get('name')} is a template; link a sellable variant")
	uom = item.get("stock_uom")
	if sales_uom_mode == "Per Foot" and uom not in FOOT_UOMS:
		problems.append(
			f"Item {item.get('name')} is sold per foot, so its stock UOM must be Foot (not {uom})"
		)
	if sales_uom_mode == "Per Spool" and uom in FOOT_UOMS:
		problems.append(f"Item {item.get('name')} is sold per spool, so its stock UOM cannot be {uom}")
	return problems


def spec_problems(values):
	"""Field-level rules for one wire spec; ``values`` is a dict of ``ilL-Spec-Wire`` fields."""
	problems = []
	if not category_label(values.get("category")):
		problems.append(f"Unknown category '{values.get('category')}'")
	applications, unknown = split_applications(values.get("applications"))
	if unknown:
		problems.append("Unknown run types: " + ", ".join(unknown))
	elif not applications:
		problems.append("List at least one run type in Applications")
	if str(values.get("temp_rating_c") or "") not in TEMP_RATINGS:
		problems.append("Temperature rating must be 60, 75, 90 or 105")
	if values.get("ampacity_basis") and values["ampacity_basis"] not in AMPACITY_BASES:
		problems.append(f"Unknown ampacity basis '{values['ampacity_basis']}'")
	mode = values.get("sales_uom_mode") or "Per Foot"
	if mode not in SALES_MODES:
		problems.append("Sold must be Per Foot or Per Spool")
	if mode == "Per Spool" and not float(values.get("spool_length_ft") or 0) > 0:
		problems.append("Spool length (ft) is required when the wire is sold per spool")
	if float(values.get("rated_v") or 0) < 0:
		problems.append("Rated voltage cannot be negative")
	for field in ("impedance_ohm", "resistance_ohm_per_kft", "ampacity_a", "od_in"):
		if values.get(field) not in (None, "") and float(values[field]) <= 0:
			problems.append(f"{field} must be positive when set")
	if re.search(r"\bexample\b", str(values.get("source_reference") or ""), re.IGNORECASE):
		problems.append("Source reference names EXAMPLE data; import only reviewed manufacturer data")
	return problems
