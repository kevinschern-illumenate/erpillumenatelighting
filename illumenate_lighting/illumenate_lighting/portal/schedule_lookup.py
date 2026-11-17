"""Request-scoped batched reads for the schedule page (plan 2.6).

The schedule page used to issue one ``frappe.db.get_value`` per line per related
record. ``Lookup`` collects the names first, fetches each DocType with one
``frappe.get_all`` and answers later reads from memory. Reads that were not
prefetched fall back to the original single-row query, so callers that pass no
lookup behave exactly as before.
"""

import frappe

CHUNK = 500


class Row(dict):
	"""A result row with attribute access, like ``frappe._dict``."""

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(key) from None


def _columns(fields):
	return [fields] if isinstance(fields, str) else list(fields)


def _shape(row, fields):
	if row is None:
		return None
	if isinstance(fields, str):
		return row.get(fields)
	return Row({column: row.get(column) for column in fields})


class Lookup:
	def __init__(self):
		self._values = {}
		self._where = {}
		self._docs = {}

	# -- by name ---------------------------------------------------------------
	def _bucket(self, doctype, fields):
		key = (doctype, fields if isinstance(fields, str) else tuple(fields))
		return self._values.setdefault(key, {})

	def prefetch(self, doctype, names, fields):
		"""One ``get_all`` per chunk of unknown ``names``; absent names cache as ``None``."""
		known = self._bucket(doctype, fields)
		wanted = sorted({name for name in names if name and isinstance(name, str) and name not in known})
		columns = _columns(fields)
		for start in range(0, len(wanted), CHUNK):
			chunk = wanted[start : start + CHUNK]
			rows = frappe.get_all(
				doctype,
				filters={"name": ["in", chunk]},
				fields=list(dict.fromkeys(["name", *columns])),
				limit_page_length=0,
			)
			for row in rows or []:
				known[row.get("name")] = _shape(row, fields)
			for name in chunk:
				known.setdefault(name, None)

	def value(self, doctype, name, fields):
		"""``frappe.db.get_value(doctype, name, fields)``, answered from the prefetch when possible."""
		known = self._bucket(doctype, fields)
		if name not in known:
			if isinstance(fields, str):
				known[name] = frappe.db.get_value(doctype, name, fields)
			else:
				known[name] = frappe.db.get_value(doctype, name, list(fields), as_dict=True)
		return known[name]

	def exists(self, doctype, name):
		known = self._bucket(doctype, "name")
		if name not in known:
			known[name] = name if frappe.db.exists(doctype, name) else None
		return bool(known[name])

	def doc(self, doctype, name):
		"""``frappe.get_doc`` once per record per request. Callers must not mutate the result."""
		key = (doctype, name)
		if key not in self._docs:
			self._docs[key] = frappe.get_doc(doctype, name)
		return self._docs[key]

	# -- by another field ------------------------------------------------------
	def _where_bucket(self, doctype, field, fields, filters):
		key = (
			doctype,
			field,
			fields if isinstance(fields, str) else tuple(fields),
			tuple(sorted((filters or {}).items())),
		)
		return self._where.setdefault(key, {})

	def prefetch_where(self, doctype, field, values, fields, filters=None):
		"""First row (newest ``modified``) per ``field`` value, matching ``get_value``'s default order."""
		known = self._where_bucket(doctype, field, fields, filters)
		wanted = sorted({value for value in values if value and isinstance(value, str) and value not in known})
		columns = _columns(fields)
		for start in range(0, len(wanted), CHUNK):
			chunk = wanted[start : start + CHUNK]
			rows = frappe.get_all(
				doctype,
				filters={**(filters or {}), field: ["in", chunk]},
				fields=list(dict.fromkeys([field, *columns])),
				order_by="modified desc",
				limit_page_length=0,
			)
			for row in rows or []:
				known.setdefault(row.get(field), _shape(row, fields))
			for value in chunk:
				known.setdefault(value, None)

	def first_where(self, doctype, field, value, fields, filters=None):
		known = self._where_bucket(doctype, field, fields, filters)
		if value not in known:
			conditions = {**(filters or {}), field: value}
			if isinstance(fields, str):
				known[value] = frappe.db.get_value(doctype, conditions, fields)
			else:
				known[value] = frappe.db.get_value(doctype, conditions, list(fields), as_dict=True)
		return known[value]


# Filters shared by the schedule page's Item Price reads.
STANDARD_SELLING = {"price_list": "Standard Selling", "selling": 1}

FIXTURE = "ilL-Configured-Fixture"
TAPE_NEON = "ilL-Configured-Tape-Neon"
LED_SHEET = "ilL-Configured-LED-Sheet"


def prefetch_schedule(lookup, lines):
	"""Warm ``lookup`` with everything the schedule page reads per line, one query per DocType."""
	illumenate = [line for line in lines if line.manufacturer_type == "ILLUMENATE"]
	accessories = [line for line in lines if line.manufacturer_type == "ACCESSORY"]

	fixture_ids = [line.configured_fixture for line in illumenate if line.configured_fixture]
	lookup.prefetch(FIXTURE, fixture_ids, "name")
	fixtures = [lookup.doc(FIXTURE, name) for name in dict.fromkeys(fixture_ids) if lookup.exists(FIXTURE, name)]
	tape_ids = [line.configured_tape_neon for line in illumenate if line.configured_tape_neon]
	lookup.prefetch(TAPE_NEON, tape_ids, "name")
	sheet_ids = [line.get("configured_led_sheet") for line in illumenate if line.get("configured_led_sheet")]
	lookup.prefetch(LED_SHEET, sheet_ids, "name")

	lookup.prefetch(
		"ilL-Fixture-Template",
		[line.fixture_template for line in illumenate] + [cf.fixture_template for cf in fixtures],
		"template_name",
	)
	lookup.prefetch(
		"ilL-Tape-Neon-Template",
		[line.tape_neon_template for line in illumenate],
		["template_name", "template_code", "description"],
	)
	lookup.prefetch("ilL-LED-Sheet-Template", [line.get("led_sheet_template") for line in illumenate], "template_name")
	lookup.prefetch("Item", [line.accessory_item for line in accessories], ["description", "item_name"])
	lookup.prefetch("ilL-Driver-Template", [line.get("driver_template") for line in accessories], "template_name")
	lookup.prefetch(
		"ilL-Extrusion-Kit-Template",
		[line.get("kit_template") for line in lines if line.get("product_type") == "Extrusion Kit"],
		"template_name",
	)

	lookup.prefetch("ilL-Attribute-Finish", [cf.finish for cf in fixtures], ["code", "finish_name"])
	lookup.prefetch("ilL-Attribute-Lens Appearance", [cf.lens_appearance for cf in fixtures], ["label", "transmission"])
	offering_fields = ["cct", "led_package", "output_level", "tape_spec", "cri"]
	offering_names = [cf.tape_offering for cf in fixtures]
	lookup.prefetch("ilL-Rel-Tape Offering", offering_names, offering_fields)
	offerings = [lookup.value("ilL-Rel-Tape Offering", name, offering_fields) for name in dict.fromkeys(offering_names) if name]
	offerings = [row for row in offerings if row]
	lookup.prefetch("ilL-Attribute-CRI", [row.cri for row in offerings], ["cri_name", "code"])
	lookup.prefetch("ilL-Spec-LED Tape", [row.tape_spec for row in offerings], ["input_voltage"])
	lookup.prefetch("ilL-Attribute-Output Level", [row.output_level for row in offerings], ["output_level_name", "value"])

	driver_items = [alloc.driver_item for cf in fixtures for alloc in (cf.drivers or []) if alloc.driver_item]
	lookup.prefetch_where("ilL-Spec-Driver", "item", driver_items, ["input_voltage", "max_wattage"])
	lookup.prefetch_where(
		"Item Price",
		"item_code",
		driver_items + [line.accessory_item for line in accessories],
		"price_list_rate",
		STANDARD_SELLING,
	)
