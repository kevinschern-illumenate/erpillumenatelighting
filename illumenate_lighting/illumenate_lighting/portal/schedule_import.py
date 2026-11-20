"""Import schedule lines from a CSV or Excel sheet (plan 3.4).

The dealer uploads a sheet, maps its columns, and sees a dry run. Each row is marked as one of:

- ``ok``: an other-manufacturer or accessory line that is complete as is;
- ``needs_configuration``: an ilLumenate line. It is added as Unconfigured, so the existing
  readiness checks hold the schedule until it is configured. A decodable part number picks
  the fixture template, and the part number, description and length are kept in the notes;
- ``error``: the row cannot be added, with the reason.

The commit re-reads the same sheet and plans it again, because the server decides. It then
adds every line through ``line_add.append_line``, the same builder that "Add line" uses, and
saves the schedule once. If any row fails, nothing is saved.

The sheet round-trips with the CSV export (``api/exports.py``): its "Line ID", "Manufacturer
Type", "Requested Length (in)" and "Part Number" columns map automatically.
"""

import base64
import binascii
import csv
import io
import json
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal import site_flags

MAX_BYTES = 1024 * 1024
MAX_ROWS = 500
MAX_QTY = 1_000_000
MAX_COLUMNS = 60
TEXT_LIMIT = 140
NOTES_LIMIT = 2000
TYPES = ("ILLUMENATE", "OTHER", "ACCESSORY")
LINEAR_FIXTURE = "Linear Fixture"
# The notes label the import writes before a line's part number; ``imported_part_number`` reads it back.
PART_NUMBER_NOTE = "Part number"

# (field, column label, extra header spellings). The labels are the downloadable template's
# header, so the template always maps itself. Spellings are compared after ``_normal``
# (lower case, no dots or trailing colon), so "QTY." and "Qty" are the same header. They cover
# the headers architects' and manufacturers' fixture schedules use.
FIELDS = (
	("line_id", "Type", (
		"line id", "designation", "fixture type", "fixture", "fixture id", "fixture tag", "fixture mark",
		"luminaire type", "mark", "tag", "symbol", "callout", "id",
	)),
	("qty", "Qty", ("quantity", "count", "qnty", "qty ea", "units", "no of fixtures", "fixture count")),
	("location", "Location", ("room", "area", "space", "zone", "room/area", "mounting location", "installed location")),
	("description", "Description", ("desc", "fixture description", "luminaire description", "product description")),
	("part_number", "Part Number", (
		"part no", "part #", "part number", "catalog number", "catalog #", "catalog no", "catalog",
		"cat #", "cat no", "catalog / part number", "ordering code", "order code", "sku", "pn",
	)),
	("notes", "Notes", ("comments", "remarks", "note", "comment")),
	("length_in", "Length (in)", (
		"length", "requested length (in)", "length in", "length (inches)", "length inches", "len",
		"run length", "overall length",
	)),
	("manufacturer_type", "Manufacturer Type", ("mfr type", "mfg type", "manufacturer type")),
	("manufacturer_name", "Manufacturer Name", ("manufacturer", "mfr", "mfg", "mfgr", "make", "brand", "vendor")),
	("fixture_model_number", "Fixture Model", ("fixture model number", "model", "model #", "model no", "model number")),
	("trim_info", "Trim", ("trim type",)),
	("housing_model_number", "Housing Model", ("housing",)),
	("driver_model_number", "Driver Model", ("driver", "ballast", "ballast/driver", "driver/ballast")),
	("lamp_info", "Lamp", ("lamps", "lamping", "lamp type", "source", "light source")),
	("dimming_protocol", "Dimming", ("dimming protocol", "dimming type", "control", "controls")),
	("input_voltage", "Voltage", ("volts", "volt", "input voltage", "v")),
	("other_finish", "Finish", ("color", "colour", "finish color")),
	("accessory_item", "Accessory Item Code", ("item code", "illumenate item code", "accessory item")),
)
FIELD_NAMES = tuple(field for field, _label, _aliases in FIELDS)
TEMPLATE_COLUMNS = [label for _field, label, _aliases in FIELDS]
LABELS = {field: label for field, label, _aliases in FIELDS}
# A row whose first cell is "#", "# ...", "## ..." or "#EX-..." is a comment: the template's
# guidance and examples. "#1" or "#A" is a fixture designation and is imported.
COMMENT = "#"
COMMENT_ROW = re.compile(r"^#(\s|#|$|EX-)", re.IGNORECASE)
# Rows searched for the header: a title block ("Smith Residence - Fixture Schedule") often sits above it.
HEADER_SEARCH = 15
# A full, real ilLumenate part number, as the configurator prints it.
EXAMPLE_PART_NUMBER = "ILL-SH01-SW-67-27K-300-WH-PV-SV-48.0-E2-C"

# What to enter in each column: the Excel template's notes and "How to use" sheet, and the
# column guide in the import dialog. (field, what to enter, needed for)
GUIDE = (
	("line_id", "Your fixture type or tag from the drawings, e.g. A1, L2, #3.", "Recommended for every line"),
	("qty", "How many. A whole number; blank means 1. \"12\", \"12 ea\" and \"1,200\" are read.", "Every line"),
	("location", "Room or area.", "Optional"),
	("description", "Plain words: product, colour temperature, output, size. Kept in the line notes.", "Optional"),
	("part_number", "A full ilLumenate part number picks the product for you, e.g. " + EXAMPLE_PART_NUMBER
		+ ". For another manufacturer, their catalog number.", "Optional"),
	("notes", "Anything else to keep with the line.", "Optional"),
	("length_in", "Length of a linear fixture or run. Inches by default; 120, 120\", 10' and 10' 6\" are read.",
		"ilLumenate linear products"),
	("manufacturer_type", "ILLUMENATE, OTHER or ACCESSORY (pick from the list). Blank: worked out from the row.",
		"Optional"),
	("manufacturer_name", "The other manufacturer's name. Writing ilLumenate here makes it an ilLumenate line.",
		"OTHER lines"),
	("fixture_model_number", "The other manufacturer's model or catalog number.", "Optional, OTHER lines"),
	("trim_info", "Trim.", "Optional, OTHER lines"),
	("housing_model_number", "Housing model.", "Optional, OTHER lines"),
	("driver_model_number", "Driver model.", "Optional, OTHER lines"),
	("lamp_info", "Lamp or light source, e.g. LED 12W 3000K.", "Optional, OTHER lines"),
	("dimming_protocol", "Dimming, e.g. 0-10V, ELV, DALI.", "Optional, OTHER lines"),
	("input_voltage", "Input voltage, e.g. 120V or 120-277V.", "Optional, OTHER lines"),
	("other_finish", "Finish or colour.", "Optional, OTHER lines"),
	("accessory_item", "The exact ilLumenate item code of a power supply, profile, lens, end cap or mounting part.",
		"ACCESSORY lines"),
)

def _example(**values):
	return [values.get(field, "") for field in FIELD_NAMES]


# One example of each kind of line; the Excel template's "Examples" sheet, and (marked as
# comments) the CSV template's rows.
EXAMPLES = [
	_example(
		line_id="A1", qty="4", location="Lobby cove", description="ilLumenate linear fixture, part number known",
		part_number=EXAMPLE_PART_NUMBER, notes="The part number picks the product", length_in="48",
		manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="A2", qty="2", location="Conference room", description="Linear pendant, 3000K, black, about 10 ft",
		notes="No part number yet: choose the product when configuring", length_in="10'",
		manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="T1", qty="1", location="Under-cabinet", description="ilLumenate LED tape, 2700K, high output",
		notes="LED tape or neon: the length is the total run", length_in="18' 6\"", manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="S1", qty="1", location="Backlit wall", description="ilLumenate LED sheet, 8 ft x 4 ft coverage",
		notes="LED sheet: give the coverage in the description", manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="B1", qty="12", location="Open office", description="2x4 recessed troffer",
		notes="Another manufacturer's fixture", manufacturer_type="OTHER", manufacturer_name="Acme Lighting",
		fixture_model_number="TRF-24-40K", lamp_info="LED 40W 4000K", dimming_protocol="0-10V",
		input_voltage="120-277V", other_finish="White",
	),
	_example(
		line_id="P1", qty="2", location="Electrical room", description="Power supply for the lobby cove",
		notes="Use a real item code from the catalog", manufacturer_type="ACCESSORY", accessory_item="ITEM-CODE",
	),
]

HOW_TO = (
	"One row per fixture type. Fill in Type, Qty and what you know; leave the rest blank.",
	"ilLumenate lines (linear fixtures, LED tape, neon, LED sheets) are added as Needs configuration. "
	"A full ilLumenate part number picks the product; otherwise you choose it in the configurator. "
	"Description, part number and length are kept in the line notes.",
	"Other manufacturers' fixtures need a Manufacturer Name. They are added as complete lines.",
	"Accessories (power supplies, profiles, lenses, end caps, mounting) need an exact ilLumenate Item Code.",
	"Manufacturer Type can be left blank: a row with an Accessory Item Code is ACCESSORY, a row with another "
	"Manufacturer Name is OTHER, anything else is ILLUMENATE.",
	"Upload the sheet with Import Lines. You see every row's result before anything is added, and nothing is "
	"added until you click Import.",
)

# The CSV template: guidance and examples as comment rows ("#"), so a dealer can type their
# lines under them and import the file as is; they are never added.
TEMPLATE_ROWS = [
	_example(line_id="# HOW TO USE: one schedule line per row. Rows starting with # (like this one) are "
		"ignored on import. The Excel template has the same columns with drop-downs and a column guide."),
	*(_example(line_id="# " + text) for text in HOW_TO[1:5]),
	*([("#EX-" + row[0]), *row[1:]] for row in EXAMPLES),
]


OTHER_FIELDS = (
	"manufacturer_name",
	"fixture_model_number",
	"trim_info",
	"housing_model_number",
	"driver_model_number",
	"lamp_info",
	"dimming_protocol",
	"input_voltage",
	"other_finish",
)


def _normal(header):
	"""Lower case, single spaces, no dots, no trailing colon: "QTY." and "Cat. No.:" read as "qty", "cat no"."""
	text = re.sub(r"\s+", " ", str(header or "").replace(".", " ")).strip().rstrip(":").strip().lower()
	return re.sub(r"\s+", " ", text)


LABEL_FIELDS = {_normal(label): field for field, label, _aliases in FIELDS}
ALIASES = {}
for _field, _label, _aliases in FIELDS:
	for _name in (_label, *_aliases):
		ALIASES.setdefault(_normal(_name), _field)


def _cell(value):
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value).strip()


def _csv_rows(data):
	try:
		text = data.decode("utf-8-sig")
	except UnicodeDecodeError:
		text = data.decode("cp1252", errors="replace")
	try:
		dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
	except csv.Error:
		dialect = csv.excel
	try:
		reader = csv.reader(io.StringIO(text, newline=""), dialect)
		return _limited(reader)
	except csv.Error:
		frappe.throw(_("The CSV file could not be read"))


def _xlsx_rows(data):
	from openpyxl import load_workbook

	try:
		book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
	except Exception:
		frappe.throw(_("The Excel file could not be read"))
	try:
		if not book.worksheets:
			frappe.throw(_("The Excel file has no sheets"))
		# The template's "Lines" sheet wherever it sits; otherwise the first sheet.
		sheet = next((ws for ws in book.worksheets if str(ws.title).strip().lower() == "lines"), book.worksheets[0])
		return _limited(sheet.iter_rows(values_only=True))
	finally:
		book.close()


class SheetRow(list):
	"""A row's trimmed cells, with ``number``: its row number in the sheet (1-based, blanks counted)."""

	number = 0
	titled = False


def _limited(rows):
	"""Rows as lists of trimmed strings, blank rows dropped; refuses sheets over the row cap.

	Each row keeps its sheet row number, so the preview names the row the dealer sees.
	"""
	result = []
	for number, row in enumerate(rows, start=1):
		cells = SheetRow(_cell(value) for value in list(row or ())[:MAX_COLUMNS])
		if not any(cells):
			continue
		if len(result) > MAX_ROWS + HEADER_SEARCH:
			frappe.throw(_("Import at most {0} lines at a time").format(MAX_ROWS))
		cells.number = number
		result.append(cells)
	return result


def is_comment(cells):
	first = next((cell for cell in cells if cell), "")
	return bool(COMMENT_ROW.match(first))


def find_header(rows):
	"""Index of the header row: the first of the top rows naming two or more known columns.

	A title block above the header (project name, date, "Lighting Fixture Schedule") is common;
	without a recognisable header the first row is the header, as before.
	"""
	for index, cells in enumerate(rows[:HEADER_SEARCH]):
		if len(suggest_mapping(cells)) >= 2:
			return index
	return 0


NUMBER = r"(\d+(?:\.\d+)?|\.\d+)"
# Straight, typographic (\u2019 \u201d) and prime (\u2032 \u2033) marks: Excel and Word autocorrect them.
FEET = "(?:'|\u2019|\u2032|ft\\.?|feet|foot)"
INCHES = '(?:"|\u201d|\u2033|\'\'|in\\.?|inch|inches)'
LENGTHS = (
	# 10' 6"  10'-6"  10 ft 6 in  10ft6in
	(re.compile(rf"^{NUMBER}\s*{FEET}\s*-?\s*{NUMBER}\s*(?:{INCHES})?$", re.IGNORECASE), lambda f, i: float(f) * 12 + float(i)),
	(re.compile(rf"^{NUMBER}\s*{FEET}$", re.IGNORECASE), lambda f: float(f) * 12),
	(re.compile(rf"^{NUMBER}\s*(?:{INCHES})?$", re.IGNORECASE), float),
	(re.compile(rf"^{NUMBER}\s*mm$", re.IGNORECASE), lambda mm: float(mm) / 25.4),
)


def parse_inches(text):
	"""A length as entered (``120``, ``120"``, ``120 in``, ``10'``, ``10' 6"``, ``3048 mm``) in inches, or None."""
	text = re.sub(r"\s+", " ", str(text or "").strip().replace(",", ""))
	for pattern, convert in LENGTHS:
		match = pattern.match(text)
		if match:
			return round(convert(*match.groups()), 3)
	return None


def parse_qty(text):
	"""A quantity as entered (``12``, ``12.0``, ``1,200``, ``12 ea``, ``12 pcs``, ``x12``) as a number, or None."""
	text = str(text or "").strip().lower()
	text = re.sub(r"^(?:x|qty)\s*", "", text)
	text = re.sub(r"\s*(?:ea|each|pcs?|pieces?|units?|x)\.?$", "", text)
	if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
		text = text.replace(",", "")
	try:
		return float(text)
	except ValueError:
		return None


def manufacturer_kind(text):
	"""ILLUMENATE, OTHER or ACCESSORY for the spellings dealers use ("ilLumenate", "Other mfr", "Acc"); "" if blank; None if unknown."""
	letters = re.sub(r"[^a-z0-9]", "", str(text or "").lower())
	if not letters:
		return ""
	if letters.startswith("ill"):
		return "ILLUMENATE"
	if letters.startswith(("oth", "thirdparty", "3rdparty", "external", "nonillumenate")):
		return "OTHER"
	if letters.startswith("acc"):
		return "ACCESSORY"
	return None


def is_illumenate_name(text):
	return re.sub(r"[^a-z]", "", str(text or "").lower()).startswith("illumenate")


def read_sheet(filename, content):
	"""The non-blank rows of an uploaded ``.csv``/``.xlsx`` (base64 ``content``), header first."""
	name = str(filename or "").strip().lower()
	extension = name.rsplit(".", 1)[-1] if "." in name else ""
	if extension not in ("csv", "xlsx"):
		frappe.throw(_("Upload a .csv or .xlsx file"))
	if not isinstance(content, str) or not content:
		frappe.throw(_("The file is empty"))
	if len(content) > (MAX_BYTES * 4) // 3 + 4:
		frappe.throw(_("The file is larger than 1 MB"))
	try:
		data = base64.b64decode(content, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The file could not be read"))
	if not data:
		frappe.throw(_("The file is empty"))
	if len(data) > MAX_BYTES:
		frappe.throw(_("The file is larger than 1 MB"))
	if extension == "xlsx":
		if not data.startswith(b"PK\x03\x04"):
			frappe.throw(_("This is not an Excel .xlsx file"))
		rows = _xlsx_rows(data)
	else:
		rows = _csv_rows(data)
	if len(rows) < 2:
		frappe.throw(_("The file has no lines under its header row"))
	return rows


def suggest_mapping(columns):
	"""``{field: column index}`` for every header that names a known field.

	A column named exactly by a field's label wins over one matching an alias (an export has
	both "Driver" and "Driver Model"); otherwise the first match wins.
	"""
	mapping = {}
	normal = [_normal(header) for header in columns]
	for index, header in enumerate(normal):
		field = LABEL_FIELDS.get(header)
		if field and field not in mapping:
			mapping[field] = index
	taken = set(mapping.values())
	for index, header in enumerate(normal):
		field = ALIASES.get(header)
		if field and field not in mapping and index not in taken:
			mapping[field] = index
			taken.add(index)
	return mapping


def _mapping(mapping, columns):
	if mapping in (None, ""):
		return suggest_mapping(columns)
	if isinstance(mapping, str):
		try:
			mapping = json.loads(mapping)
		except ValueError:
			frappe.throw(_("Invalid column mapping"))
	if not isinstance(mapping, dict):
		frappe.throw(_("Invalid column mapping"))
	result = {}
	for field, index in mapping.items():
		if field not in FIELD_NAMES:
			frappe.throw(_("Unknown import field {0}").format(field))
		if index in (None, "", -1, "-1"):
			continue
		try:
			index = int(index)
		except (TypeError, ValueError):
			frappe.throw(_("Invalid column mapping"))
		if not 0 <= index < len(columns):
			frappe.throw(_("Invalid column mapping"))
		result[field] = index
	return result


class _Planner:
	"""Turns sheet rows into ``append_line`` payloads, sharing lookups across rows."""

	def __init__(self, is_sales_staff):
		self.is_sales_staff = is_sales_staff
		self.decode_enabled = site_flags.part_number_decode_enabled()
		self.decoded = {}
		self.items = {}

	def decode(self, part_number):
		key = part_number.upper()
		if key not in self.decoded:
			from illumenate_lighting.illumenate_lighting.portal.part_number import NotAPartNumber, decode

			try:
				self.decoded[key] = decode(part_number)
			except NotAPartNumber:
				self.decoded[key] = None
		return self.decoded[key]

	def item(self, code):
		if code not in self.items:
			from illumenate_lighting.illumenate_lighting.api.portal import orderable_item_problem

			problem = orderable_item_problem(code, self.is_sales_staff)
			details = None if problem else frappe.db.get_value("Item", code, ["item_name", "item_group"], as_dict=True)
			self.items[code] = (problem, details)
		return self.items[code]

	def plan(self, number, cells, mapping):
		if is_comment(cells):
			return None
		values = {field: (cells[index] if index < len(cells) else "") for field, index in mapping.items()}
		if not any(values.values()) or any(cell.upper() == "SCHEDULE TOTAL" for cell in cells):
			return None
		row = {"row": number, "status": "error", "messages": [], "line_id": values.get("line_id", "")}
		errors = []

		qty = values.get("qty") or "1"
		number_qty = parse_qty(qty)
		valid_qty = number_qty is not None and number_qty.is_integer() and 1 <= number_qty <= MAX_QTY
		if not valid_qty:
			errors.append(_("Quantity must be a whole number of at least 1"))
		row["qty"] = int(number_qty) if valid_qty else qty
		row["location"] = values.get("location", "")
		for field in ("line_id", "location", "part_number", "description", *OTHER_FIELDS, "accessory_item"):
			if len(values.get(field, "")) > TEXT_LIMIT:
				errors.append(_("{0} is limited to {1} characters").format(LABELS[field], TEXT_LIMIT))

		kind = manufacturer_kind(values.get("manufacturer_type"))
		if kind is None:
			errors.append(_("Manufacturer Type must be ILLUMENATE, OTHER or ACCESSORY"))
			kind = values.get("manufacturer_type", "").upper()
		elif not kind:
			name = values.get("manufacturer_name")
			kind = (
				"ACCESSORY"
				if values.get("accessory_item")
				else "OTHER"
				if name and not is_illumenate_name(name)
				else "ILLUMENATE"
			)
		row["manufacturer_type"] = kind

		line_data = {
			"line_id": values.get("line_id") or None,
			"qty": row["qty"],
			"location": values.get("location") or None,
			"manufacturer_type": kind,
		}
		notes = [values.get("notes", "")]
		if kind == "ACCESSORY":
			code = values.get("accessory_item", "")
			if not code:
				errors.append(_("Enter the accessory Item code"))
			else:
				problem, details = self.item(code)
				if problem:
					errors.append(problem)
				else:
					from illumenate_lighting.illumenate_lighting.api.portal import is_power_supply_group

					line_data["accessory_item"] = code
					line_data["accessory_item_name"] = details.get("item_name") or code
					if not is_power_supply_group(details.get("item_group")):
						line_data["accessory_product_type"] = details.get("item_group")
					row["summary"] = line_data["accessory_item_name"]
					self._describe(values, notes, line_data["accessory_item_name"], code)
		elif kind == "OTHER":
			if not values.get("manufacturer_name"):
				errors.append(_("Enter the manufacturer name"))
			for field in OTHER_FIELDS:
				line_data[field] = values.get(field) or None
			# An architect's schedule has one catalog number column: for another maker it is the model.
			if not line_data.get("fixture_model_number") and values.get("part_number"):
				line_data["fixture_model_number"] = values["part_number"]
			row["summary"] = " ".join(filter(None, (values.get("manufacturer_name"), line_data.get("fixture_model_number"))))
			self._describe(values, notes, row["summary"], values.get("manufacturer_name"), line_data.get("fixture_model_number"))
		elif kind == "ILLUMENATE":
			self._illumenate(values, line_data, notes, row, errors)

		note = "\n".join(filter(None, notes))
		if len(note) > NOTES_LIMIT:
			errors.append(_("Notes are limited to {0} characters").format(NOTES_LIMIT))
		line_data["notes"] = note or None
		if errors:
			row["messages"] = errors
			return row, None
		row["status"] = "needs_configuration" if kind == "ILLUMENATE" else "ok"
		return row, line_data

	@staticmethod
	def _describe(values, notes, *already_shown):
		"""Keep the sheet's description in the notes unless it only repeats the name or model."""
		description = values.get("description")
		shown = {str(text).strip().lower() for text in already_shown if text}
		if description and description.strip().lower() not in shown:
			notes.append(_("Description: {0}").format(description))

	def _illumenate(self, values, line_data, notes, row, errors):
		part_number = values.get("part_number", "")
		if not part_number and values.get("fixture_model_number", "").upper().startswith("ILL-"):
			part_number = values["fixture_model_number"]
		length = values.get("length_in", "")
		inches = None
		if length:
			inches = parse_inches(length)
			if not inches or inches <= 0:
				errors.append(_("Length (in) must be a number of inches"))
		decoded = self.decode(part_number) if part_number and self.decode_enabled else None
		if decoded and decoded.get("template"):
			line_data["product_type"] = LINEAR_FIXTURE
			line_data["fixture_template"] = decoded["template"]
			row["summary"] = decoded.get("template_name") or decoded["template"]
			row["messages"].append(_("Matched {0}. Configure this line to finish it.").format(row["summary"]))
			unmatched = ", ".join(entry.get("answer", "") for entry in decoded.get("unmatched") or [])
			if unmatched:
				row["messages"].append(_("Not recognised: {0}").format(unmatched))
		else:
			if values.get("description"):
				notes.append(_("Description: {0}").format(values["description"]))
			if part_number and decoded and decoded.get("status") == "ambiguous":
				row["messages"].append(_("This part number fits several products. Choose one when configuring."))
			elif part_number:
				row["messages"].append(_("Part number not recognised. Choose the product when configuring."))
			else:
				row["messages"].append(_("Choose the product when configuring."))
		if part_number:
			notes.append(_("Part number: {0}").format(part_number))
		if length:
			shown = f"{inches:g}" if inches else length
			if inches and shown != length.strip():
				notes.append(_("Length: {0} in (entered as {1})").format(shown, length))
			else:
				notes.append(_("Length: {0} in").format(shown))
			if inches:
				row["length_in"] = float(shown)


def imported_part_number(notes):
	"""The part number an import kept in a line's notes ("Part number: ILL-..."), or None."""
	match = re.search(rf"^{PART_NUMBER_NOTE}: *(\S+) *$", str(notes or ""), re.MULTILINE)
	return match.group(1) if match else None


def _read(filename, content, mapping):
	"""``(header row, columns, mapping, data rows)``; the header is found under any title rows."""
	rows = read_sheet(filename, content)
	# Found the same way on every call, so a mapping chosen against the preview's columns still fits.
	header = find_header(rows)
	columns = list(rows[header])
	if header + 1 >= len(rows):
		frappe.throw(_("The file has no lines under its header row"))
	header_row = rows[header]
	# The Excel template's "#" tip above its header is expected; only a real title block is reported.
	header_row.titled = any(not is_comment(cells) for cells in rows[:header])
	return header_row, columns, _mapping(mapping, columns), rows[header + 1 :]


def _warnings(chosen, header_row, comments):
	warnings = []
	if getattr(header_row, "titled", False):
		warnings.append(
			_("Row {0} is used as the header row; the rows above it were skipped.").format(header_row.number)
		)
	if comments:
		warnings.append(_("{0} row(s) starting with # were skipped as notes.").format(comments))
	if "qty" not in chosen:
		warnings.append(
			_("No quantity column was found, so every line gets Qty 1. If your sheet has one, choose it under Qty.")
		)
	if not {"manufacturer_type", "manufacturer_name", "accessory_item"} & set(chosen):
		warnings.append(
			_(
				"No manufacturer column was found, so every line is treated as an ilLumenate line. If the sheet "
				"lists other manufacturers' fixtures, choose that column under Manufacturer Name."
			)
		)
	if "line_id" not in chosen:
		warnings.append(_("No Type column was found, so lines are added without a fixture type."))
	return warnings


def _plan_sheet(filename, content, mapping, is_sales_staff, read=None):
	header_row, columns, chosen, rows = read or _read(filename, content, mapping)
	if not chosen:
		frappe.throw(_("Map at least one column"))
	planner = _Planner(is_sales_staff)
	planned = []
	comments = 0
	for cells in rows:
		if is_comment(cells):
			comments += 1
			continue
		result = planner.plan(cells.number, cells, chosen)
		if result:
			planned.append(result)
			if len(planned) > MAX_ROWS:
				frappe.throw(_("Import at most {0} lines at a time").format(MAX_ROWS))
	if not planned:
		frappe.throw(_("The file has no lines to import"))
	return columns, chosen, planned, _warnings(chosen, header_row, comments)


def _counts(planned):
	counts = {"ok": 0, "needs_configuration": 0, "error": 0}
	for row, _line in planned:
		counts[row["status"]] += 1
	return counts


def _schedule(schedule, lock=False):
	from illumenate_lighting.illumenate_lighting.portal.bulk_lines import _editable
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to import schedule lines"), frappe.PermissionError)
	if not site_flags.schedule_import_enabled():
		frappe.throw(_("Schedule import is turned off"))
	doc = schedule_context(schedule, write=True, lock=lock)
	_editable(doc)
	return doc


def _sales_staff():
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return allowed("sales")


STATUSES = (
	("Ready", "Another manufacturer's fixture or an accessory, complete as entered."),
	("Needs configuration", "An ilLumenate line. It is added as Unconfigured; click Configure on the line to "
		"choose its options before you submit the schedule."),
	("Error", "The row can't be added; the reason is shown. Fix the sheet and upload it again, or tick "
		"\"Skip the rows with errors\"."),
)
TEMPLATE_TIP = (
	"# Fill in one line per fixture type, starting in row 3. Point at a column name for a tip; the "
	"\"How to use\" tab explains every column and the \"Examples\" tab shows each kind of line. "
	"Rows starting with # are ignored."
)
TEMPLATE_FILENAME = "ilLumenate-schedule-import-template.xlsx"


def guide():
	"""The column guide, for the import dialog and the Excel template: label, what to enter, needed for."""
	return [
		{"field": field, "label": LABELS[field], "help": _(help_text), "needed": _(needed)}
		for field, help_text, needed in GUIDE
	]


def template_workbook():
	"""The Excel import template: "Lines" to fill in, "How to use" and "Examples". Returns the .xlsx bytes."""
	from openpyxl import Workbook
	from openpyxl.comments import Comment
	from openpyxl.styles import Alignment, Font, PatternFill
	from openpyxl.utils import get_column_letter
	from openpyxl.worksheet.datavalidation import DataValidation

	navy, light = "1F3A5F", "E8EEF5"
	bold_white = Font(bold=True, color="FFFFFF")
	header_fill = PatternFill("solid", fgColor=navy)
	wrap = Alignment(wrap_text=True, vertical="top")
	widths = {"line_id": 10, "qty": 8, "description": 40, "part_number": 44, "notes": 34, "length_in": 13}
	columns = guide()

	book = Workbook()
	lines = book.active
	lines.title = "Lines"
	lines.append([_(TEMPLATE_TIP)])
	lines.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(FIELDS))
	lines["A1"].font = Font(italic=True, color="555555")
	lines["A1"].alignment = Alignment(wrap_text=True, vertical="center")
	lines.row_dimensions[1].height = 32
	lines.append(TEMPLATE_COLUMNS)
	for index, column in enumerate(columns, start=1):
		cell = lines.cell(row=2, column=index)
		cell.font, cell.fill = bold_white, header_fill
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cell.comment = Comment(f"{column['help']}\n\n{_('Needed for')}: {column['needed']}", "ilLumenate", width=320, height=140)
		lines.column_dimensions[get_column_letter(index)].width = widths.get(column["field"], 18)
	lines.freeze_panes = "B3"
	last = MAX_ROWS + 2
	kinds = DataValidation(type="list", formula1='"ILLUMENATE,OTHER,ACCESSORY"', allow_blank=True)
	kinds.error = _("Choose ILLUMENATE, OTHER or ACCESSORY, or leave it blank.")
	kinds.prompt = _("ILLUMENATE, OTHER or ACCESSORY. Blank: worked out from the row.")
	kinds.showErrorMessage = kinds.showInputMessage = True
	qty = DataValidation(type="whole", operator="between", formula1="1", formula2=str(MAX_QTY), allow_blank=True)
	qty.error = _("Qty is a whole number of at least 1.")
	qty.showErrorMessage = True
	for validation, field in ((kinds, "manufacturer_type"), (qty, "qty")):
		letter = get_column_letter(FIELD_NAMES.index(field) + 1)
		validation.add(f"{letter}3:{letter}{last}")
		lines.add_data_validation(validation)

	how = book.create_sheet("How to use")
	how.column_dimensions["A"].width = 24
	how.column_dimensions["B"].width = 90
	how.column_dimensions["C"].width = 28
	how.append([_("Importing a fixture schedule")])
	how["A1"].font = Font(bold=True, size=14, color=navy)
	how.append([])
	for number, text in enumerate(HOW_TO, start=1):
		how.append([_("Step {0}").format(number), _(text)])
		how.cell(row=how.max_row, column=1).font = Font(bold=True)
		how.cell(row=how.max_row, column=2).alignment = wrap
	how.append([])
	how.append([_("Column"), _("What to enter"), _("Needed for")])
	for cell in how[how.max_row]:
		cell.font, cell.fill = bold_white, header_fill
	for column in columns:
		how.append([column["label"], column["help"], column["needed"]])
		how.cell(row=how.max_row, column=1).font = Font(bold=True)
		for cell in how[how.max_row]:
			cell.alignment = wrap
	how.append([])
	how.append([_("After you upload"), _("Every row is checked first and shown with one of these results:")])
	how.cell(row=how.max_row, column=1).font = Font(bold=True)
	for label, text in STATUSES:
		how.append([_(label), _(text)])
		how.cell(row=how.max_row, column=2).alignment = wrap

	examples = book.create_sheet("Examples")
	examples.append([_("# Examples of each kind of line. Copy rows into the Lines tab and change them; this tab is not imported.")])
	examples["A1"].font = Font(italic=True, color="555555")
	examples.append(TEMPLATE_COLUMNS)
	for index, column in enumerate(columns, start=1):
		cell = examples.cell(row=2, column=index)
		cell.font, cell.fill = Font(bold=True), PatternFill("solid", fgColor=light)
		examples.column_dimensions[get_column_letter(index)].width = widths.get(column["field"], 18)
	for row in EXAMPLES:
		examples.append(row)
	examples.freeze_panes = "B3"

	book.active = 0
	output = io.BytesIO()
	book.save(output)
	return output.getvalue()


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=30, seconds=60)
def download_import_template():
	"""The Excel import template as a download, for signed-in users."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to download the import template"), frappe.PermissionError)
	frappe.local.response.filename = TEMPLATE_FILENAME
	frappe.local.response.filecontent = template_workbook()
	frappe.local.response.type = "download"


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def preview_schedule_import(schedule, filename, content, mapping=None):
	"""Dry run: the sheet's columns, the mapping used and every row's planned status. Saves nothing."""
	doc = _schedule(schedule)
	fields = [{"field": field, "label": label} for field, label, _aliases in FIELDS]
	read = _read(filename, content, mapping)
	header_row, columns, chosen, _rows = read
	if mapping in (None, ""):
		if not chosen:
			# No header matched: show the columns so the dealer can say which is which.
			return {
				"success": True,
				"schedule": doc.name,
				"columns": columns,
				"header_row": header_row.number,
				"mapping": {},
				"fields": fields,
				"rows": [],
				"counts": {"ok": 0, "needs_configuration": 0, "error": 0},
				"warnings": [
					_(
						"None of the column names were recognised. Choose which column holds each field below, "
						"then click Update preview."
					)
				],
			}
	columns, chosen, planned, warnings = _plan_sheet(filename, content, mapping, _sales_staff(), read)
	return {
		"success": True,
		"schedule": doc.name,
		"columns": columns,
		"mapping": chosen,
		"fields": fields,
		"rows": [row for row, _line in planned],
		"counts": _counts(planned),
		"warnings": warnings,
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
@atomic_build
def commit_schedule_import(schedule, filename, content, mapping=None, expected_modified=None, skip_errors=None):
	"""Add the sheet's lines to ``schedule`` in one save, all or nothing.

	Rows with errors refuse the import unless ``skip_errors`` is set; then only the other rows
	are added. Returns ``{"success", "count", "skipped", "modified"}``.
	"""
	from illumenate_lighting.illumenate_lighting.portal.line_add import append_line
	from illumenate_lighting.illumenate_lighting.portal.schedule_lines import require_fresh

	doc = _schedule(schedule, lock=True)
	require_fresh(doc, expected_modified)
	is_sales_staff = _sales_staff()
	_columns, _chosen, planned, _notes = _plan_sheet(filename, content, mapping, is_sales_staff)
	counts = _counts(planned)
	skip = str(skip_errors or "").strip().lower() in ("1", "true", "yes", "on")
	if counts["error"] and not skip:
		return {
			"success": False,
			"error": _("Fix or skip the rows with errors"),
			"rows": [row for row, _line in planned],
			"counts": counts,
		}
	added = 0
	for row, line_data in planned:
		if line_data is None:
			continue
		error = append_line(doc, line_data, is_sales_staff)
		if error:
			row.update(status="error", messages=[error])
			return {"success": False, "error": _("Row {0}: {1}").format(row["row"], error), "rows": [row]}
		added += 1
	doc.save(ignore_permissions=True)
	return {"success": True, "schedule": doc.name, "count": added, "skipped": counts["error"], "modified": str(doc.modified)}
