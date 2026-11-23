"""Read the ilLumenate price list workbook (``ilLumenate_Price_List_<date>.xlsx``).

The workbook's Price List sheet has section header rows (text in the Part Number column
only) followed by product rows: Part Number, Description, Unit, MSRP, four tier prices and
Options / Notes. Bracketed part-number segments (``[27K/30K]``) list the options a row covers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Row:
	row: int
	section: str
	part: str
	description: str
	unit: str
	msrp: float
	notes: str = ""


@dataclass
class FixtureLine:
	"""One linear-fixture price row: a kit line x a tape type x an environment rating."""

	family: str
	package: str  # SW, DW, TW, FS
	environment: str  # 20 (Dry), 54 (Damp), 67 (Wet)
	high_output: bool
	lenses: list[str]
	mounts: list[str]
	msrp: float
	name: str  # e.g. "Castle [SF]"


@dataclass
class PriceList:
	rows: list[Row] = field(default_factory=list)

	def section(self, prefix):
		return [row for row in self.rows if row.section.startswith(prefix)]

	def find(self, part):
		return next((row for row in self.rows if row.part == part), None)


def read(path):
	import openpyxl

	sheet = openpyxl.load_workbook(path, data_only=True, read_only=True)["Price List"]
	rows, section = [], ""
	for number, values in enumerate(sheet.iter_rows(min_row=5, values_only=True), start=5):
		values = list(values) + [None] * 9
		part, description, unit, msrp = values[:4]
		if not part:
			continue
		if not any((description, unit, msrp)):
			section = str(part).strip()
			continue
		if not isinstance(msrp, (int, float)):
			continue
		rows.append(
			Row(
				number,
				section,
				str(part).strip(),
				str(description or "").strip(),
				str(unit or ""),
				float(msrp),
				str(values[8] or ""),
			)
		)
	return PriceList(rows)


def segments(part):
	"""Split a part number on hyphens outside brackets: KIT-RA01-[WL/WX]-SP -> [KIT, RA01, [WL/WX], SP]."""
	out, depth, current = [], 0, ""
	for char in part:
		if char == "[":
			depth += 1
		elif char == "]":
			depth -= 1
		if char == "-" and depth == 0:
			out.append(current)
			current = ""
		else:
			current += char
	out.append(current)
	return out


def options(segment):
	return segment.strip("[]").split("/") if segment else []


FIXTURE = re.compile(r"^ILL-(?P<family>[A-Z]+\d+)-(?P<package>SW|DW|TW|FS)-(?P<env>20|54|67)-")
KIT = re.compile(r"Kit:\s*(?P<kit>\S+)")


def fixture_lines(price_list):
	lines = []
	for row in price_list.section("LINEAR FIXTURES"):
		match = FIXTURE.match(row.part)
		kit = KIT.search(row.notes)
		if not match or not kit:
			continue
		parts = segments(kit.group("kit"))
		# KIT-<family>-<lens>-<mount>-<finish>
		lenses, mounts = (options(parts[2]), options(parts[3])) if len(parts) >= 5 else ([], [])
		lines.append(
			FixtureLine(
				family=match.group("family"),
				package=match.group("package"),
				environment=match.group("env"),
				high_output=any(level in row.part for level in ("750", "1000", "1250", "1500"))
				and match.group("package") == "SW",
				lenses=lenses,
				mounts=mounts,
				msrp=row.msrp,
				name=row.description.split(" — ")[0].strip(),
			)
		)
	return lines
