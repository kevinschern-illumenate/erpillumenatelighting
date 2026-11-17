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

# (field, column label, extra header spellings). The labels are the downloadable template's
# header, so the template always maps itself.
FIELDS = (
	("line_id", "Type", ("line id", "designation", "fixture type", "mark", "tag")),
	("qty", "Qty", ("quantity", "count")),
	("location", "Location", ("room", "area")),
	("description", "Description", ()),
	("part_number", "Part Number", ("part no", "part #", "catalog number", "catalog #", "catalog no", "pn")),
	("notes", "Notes", ("comments", "remarks")),
	("length_in", "Length (in)", ("length", "requested length (in)", "length in")),
	("manufacturer_type", "Manufacturer Type", ()),
	("manufacturer_name", "Manufacturer Name", ("manufacturer",)),
	("fixture_model_number", "Fixture Model", ("fixture model number",)),
	("trim_info", "Trim", ()),
	("housing_model_number", "Housing Model", ()),
	("driver_model_number", "Driver Model", ()),
	("lamp_info", "Lamp", ()),
	("dimming_protocol", "Dimming", ()),
	("input_voltage", "Voltage", ()),
	("other_finish", "Finish", ()),
	("accessory_item", "Accessory Item Code", ("item code",)),
)
FIELD_NAMES = tuple(field for field, _label, _aliases in FIELDS)
TEMPLATE_COLUMNS = [label for _field, label, _aliases in FIELDS]
# A row whose first cell starts with this is a comment: the template's guidance and examples.
COMMENT = "#"


def _example(**values):
	return [values.get(field, "") for field in FIELD_NAMES]


# Guidance and one example per kind of line. Every row starts with "#", so a dealer can type
# their lines under them and import the file as is; the examples are never added.
TEMPLATE_ROWS = [
	_example(line_id="# HOW TO USE: one schedule line per row. Rows whose first cell starts with # (like this one and the examples below) are ignored on import; delete them or leave them."),
	_example(line_id="# Manufacturer Type: ILLUMENATE, OTHER or ACCESSORY. If blank, a row with an Accessory Item Code is ACCESSORY, a row with a Manufacturer Name is OTHER, and anything else is ILLUMENATE."),
	_example(line_id="# ILLUMENATE lines (linear fixtures, LED tape, LED neon, LED sheets) are added as Needs configuration. A full ilLumenate part number picks the product; Description, Part Number and Length (in) are kept in the line notes so you can finish it in the configurator."),
	_example(line_id="# OTHER lines are another manufacturer's product: Manufacturer Name is required; Fixture Model through Finish are optional. ACCESSORY lines need an exact ilLumenate Item Code (power supplies, profiles, lenses, end caps, mounting)."),
	_example(line_id="# Qty is a whole number (blank means 1). Length (in) is the requested length in inches for linear products and runs."),
	_example(
		line_id="#EX-A1", qty="4", location="Lobby cove", description="ilLumenate linear fixture, part number known",
		part_number="ILL-SH01-S-D-30-O3-FR-CL-SV-48-L10-C", notes="Example: decoded part number", length_in="48",
		manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="#EX-A2", qty="2", location="Conference room", description="ilLumenate linear pendant, 3000K, black, about 10 ft",
		notes="Example: no part number yet; choose the product when configuring", length_in="120", manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="#EX-T1", qty="1", location="Under-cabinet", description="ilLumenate LED tape, 2700K, high output",
		notes="Example: LED tape or neon; length is the total run", length_in="216", manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="#EX-S1", qty="1", location="Backlit wall", description="ilLumenate LED sheet, 8 ft x 4 ft coverage",
		notes="Example: LED sheet; give the coverage in the description", manufacturer_type="ILLUMENATE",
	),
	_example(
		line_id="#EX-B1", qty="12", location="Open office", description="2x4 recessed troffer",
		notes="Example: another manufacturer's fixture", manufacturer_type="OTHER", manufacturer_name="Acme Lighting",
		fixture_model_number="TRF-24-40K", lamp_info="LED 40W 4000K", dimming_protocol="0-10V",
		input_voltage="120-277V", other_finish="White",
	),
	_example(
		line_id="#EX-P1", qty="2", location="Electrical room", description="Power supply for the lobby cove",
		notes="Example: replace with a real Item Code from the catalog", manufacturer_type="ACCESSORY",
		accessory_item="ITEM-CODE",
	),
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
	return re.sub(r"\s+", " ", str(header or "")).strip().rstrip(":").strip().lower()


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
		return _limited(book.worksheets[0].iter_rows(values_only=True))
	finally:
		book.close()


def _limited(rows):
	"""Rows as lists of trimmed strings, blank rows dropped; refuses sheets over the row cap."""
	result = []
	for row in rows:
		cells = [_cell(value) for value in list(row or ())[:MAX_COLUMNS]]
		if not any(cells):
			continue
		if len(result) > MAX_ROWS:
			frappe.throw(_("Import at most {0} lines at a time").format(MAX_ROWS))
		result.append(cells)
	return result


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
	"""``{field: column index}`` for every header that names a known field (first match wins)."""
	mapping = {}
	for index, header in enumerate(columns):
		field = ALIASES.get(_normal(header))
		if field and field not in mapping:
			mapping[field] = index
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
		first = next((cell for cell in cells if cell), "")
		if first.startswith(COMMENT):
			return None
		values = {field: (cells[index] if index < len(cells) else "") for field, index in mapping.items()}
		if not any(values.values()) or any(cell.upper() == "SCHEDULE TOTAL" for cell in cells):
			return None
		row = {"row": number, "status": "error", "messages": [], "line_id": values.get("line_id", "")}
		errors = []

		qty = values.get("qty") or "1"
		try:
			number_qty = float(qty)
		except ValueError:
			number_qty = 0.0
		if not number_qty.is_integer() or not 1 <= number_qty <= MAX_QTY:
			errors.append(_("Quantity must be a whole number of at least 1"))
		row["qty"] = int(number_qty) if number_qty.is_integer() and number_qty >= 1 else qty
		row["location"] = values.get("location", "")
		for field in ("line_id", "location", "part_number", "description", *OTHER_FIELDS, "accessory_item"):
			if len(values.get(field, "")) > TEXT_LIMIT:
				label = next(label for name, label, _aliases in FIELDS if name == field)
				errors.append(_("{0} is limited to {1} characters").format(label, TEXT_LIMIT))

		kind = values.get("manufacturer_type", "").upper()
		if kind and kind not in TYPES:
			errors.append(_("Manufacturer Type must be ILLUMENATE, OTHER or ACCESSORY"))
		elif not kind:
			kind = "ACCESSORY" if values.get("accessory_item") else "OTHER" if values.get("manufacturer_name") else "ILLUMENATE"
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
		elif kind == "OTHER":
			if not values.get("manufacturer_name"):
				errors.append(_("Enter the manufacturer name"))
			for field in OTHER_FIELDS:
				line_data[field] = values.get(field) or None
			row["summary"] = " ".join(filter(None, (values.get("manufacturer_name"), values.get("fixture_model_number"))))
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

	def _illumenate(self, values, line_data, notes, row, errors):
		part_number = values.get("part_number", "")
		length = values.get("length_in", "")
		if length:
			try:
				inches = float(length)
			except ValueError:
				inches = 0.0
			if not inches > 0:
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
			notes.append(_("Length: {0} in").format(length))


def _plan_sheet(filename, content, mapping, is_sales_staff):
	rows = read_sheet(filename, content)
	columns = rows[0]
	chosen = _mapping(mapping, columns)
	if not chosen:
		frappe.throw(_("Map at least one column"))
	planner = _Planner(is_sales_staff)
	planned = []
	for number, cells in enumerate(rows[1:], start=2):
		result = planner.plan(number, cells, chosen)
		if result:
			planned.append(result)
	if not planned:
		frappe.throw(_("The file has no lines to import"))
	return columns, chosen, planned


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


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def preview_schedule_import(schedule, filename, content, mapping=None):
	"""Dry run: the sheet's columns, the mapping used and every row's planned status. Saves nothing."""
	doc = _schedule(schedule)
	columns, chosen, planned = _plan_sheet(filename, content, mapping, _sales_staff())
	return {
		"success": True,
		"schedule": doc.name,
		"columns": columns,
		"mapping": chosen,
		"fields": [{"field": field, "label": label} for field, label, _aliases in FIELDS],
		"rows": [row for row, _line in planned],
		"counts": _counts(planned),
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
	_columns, _chosen, planned = _plan_sheet(filename, content, mapping, is_sales_staff)
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
