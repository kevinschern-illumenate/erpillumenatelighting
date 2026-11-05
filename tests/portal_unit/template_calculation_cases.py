"""A small fake Frappe site for the template calculation tests (test_template_calculations.py).

Every template type is described by one or more scenarios over the same records. The expected
results in fixtures/template_calculations_parity.json were captured by running the code that
calculated them before the move (the ilL-Webflow-Product methods on a temporary product,
commit d88125d) over these scenarios, so the parity test checks that the move changed nothing.
"""

import copy
import importlib
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = "illumenate_lighting.illumenate_lighting"
PRODUCT = "ilL-Webflow-Product"
OPTION = "ilL-Child-Webflow-Configurator-Option"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "template_calculations_parity.json"
PRODUCT_JSON = (
	Path(__file__).resolve().parents[2]
	/ "illumenate_lighting/illumenate_lighting/doctype/ill_webflow_product/ill_webflow_product.json"
)


class _dict(dict):
	"""frappe._dict"""

	__getattr__ = dict.get

	def __setattr__(self, key, value):
		self[key] = value


def rows(*values):
	return [_dict(value) for value in values]


TEMPLATE_TABLES = (
	"allowed_options",
	"allowed_tape_offerings",
	"allowed_tape_specs",
	"allowed_specs",
	"certifications",
	"feed_lengths",
	"kit_components",
	"specifications",
	"part_no_configurator",
	"other_documents",
)


class Doc(_dict):
	"""A template (or any record) as get_doc returns it: fields as keys, child rows as _dicts."""

	def __init__(self, doctype, name, **values):
		super().__init__(doctype=doctype, name=name, **values)
		self["flags"] = _dict()
		for table in TEMPLATE_TABLES:
			self.setdefault(table, [])

	def set(self, key, value):
		if isinstance(value, list):
			self[key] = []
			for row in value:
				self.append(key, row)
		else:
			self[key] = value

	def append(self, key, value=None):
		row = value if isinstance(value, _dict) else _dict(value or {})
		table = self.setdefault(key, [])
		if not row.get("idx"):
			row.idx = len(table) + 1
		table.append(row)
		return row


class FakeDocument:
	"""frappe.model.document.Document, enough for ilL-Webflow-Product."""

	def __init__(self, *args, **kwargs):
		self.__dict__["flags"] = _dict()

	def get(self, key, default=None):
		return self.__dict__.get(key, default)

	def set(self, key, value):
		if isinstance(value, list):
			self.__dict__[key] = []
			for row in value:
				self.append(key, row)
		else:
			self.__dict__[key] = value

	def append(self, key, value=None):
		row = value if isinstance(value, _dict) else _dict(value or {})
		table = self.__dict__.get(key)
		if table is None:
			self.__dict__[key] = table = []
		if not row.get("idx"):
			row.idx = len(table) + 1
		table.append(row)
		return row

	def is_new(self):
		return self.__dict__.get("_is_new", True)


def new_product(product_class):
	"""What frappe.new_doc("ilL-Webflow-Product") gives: defaults from the doctype, Int fields
	without a default unset (None), every table empty."""
	product = product_class()
	product.doctype = PRODUCT
	product.name = None
	for field in json.loads(PRODUCT_JSON.read_text())["fields"]:
		kind = field["fieldtype"]
		if kind in ("Section Break", "Column Break", "Tab Break", "HTML"):
			continue
		if kind == "Table":
			value = []
		elif kind == "Check":
			value = int(field.get("default") or 0)
		elif kind == "Select" and not field.get("default"):
			value = (field.get("options") or "").split("\n")[0]
		else:
			value = field.get("default")
		product.__dict__[field["fieldname"]] = value
	return product


# ---------------------------------------------------------------- records


def records():
	"""{doctype: {name: record}}; child records of other doctypes are lists under "_rows"."""
	attribute = lambda **values: values  # noqa: E731
	return {
		"ilL-Rel-Tape Offering": {
			"OFF-30-HO": attribute(
				cri="CRI-90",
				output_level="TAPE-400",
				cct="3000K",
				tape_spec="TAPE-A",
				led_package="LP-2835",
				cut_increment_mm_override=None,
			),
			"OFF-40-HO": attribute(
				cri="CRI-95",
				output_level="TAPE-600",
				cct="4000K",
				tape_spec="TAPE-B",
				led_package="LP-2835",
				cut_increment_mm_override=25,
			),
			"OFF-27-LO": attribute(
				cri="CRI-90",
				output_level="TAPE-200",
				cct="2700K",
				tape_spec="TAPE-A",
				led_package="LP-COB",
				cut_increment_mm_override=None,
			),
		},
		"ilL-Spec-LED Tape": {
			"TAPE-A": attribute(
				input_voltage="24V",
				operating_temp="-20°C to 45°C",
				watts_per_foot=4.4,
				voltage_drop_max_run_length_ft=32,
				cut_increment_mm=50,
				cri_typical=92,
				input_protocol="PWM",
				supported_dimming_protocols=rows({"protocol": "ELV"}, {"protocol": "0-10V"}),
			),
			"TAPE-B": attribute(
				input_voltage="24V",
				operating_temp="-20°C to 45°C ",
				watts_per_foot=2.9,
				voltage_drop_max_run_length_ft=48.5,
				cut_increment_mm=None,
				cri_typical=None,
				input_protocol=None,
				supported_dimming_protocols=rows({"protocol": "DALI"}, {"protocol": ""}),
			),
			"TAPE-C": attribute(
				input_voltage="48V",
				operating_temp=None,
				watts_per_foot=None,
				voltage_drop_max_run_length_ft=None,
				cut_increment_mm=10,
				cri_typical=95,
				input_protocol="DMX",
				supported_dimming_protocols=[],
			),
		},
		"ilL-Attribute-Output Level": {
			"TAPE-200": attribute(
				output_level_name="200 lm/ft", sku_code="02", value=200, is_fixture_level=0
			),
			"TAPE-400": attribute(
				output_level_name="400 lm/ft", sku_code="04", value=400, is_fixture_level=0
			),
			"TAPE-600": attribute(
				output_level_name="600 lm/ft", sku_code="06", value=600, is_fixture_level=0
			),
			"FIX-150": attribute(output_level_name="150", sku_code="F15", value=150, is_fixture_level=1),
			"FIX-300": attribute(output_level_name="300", sku_code="F30", value=300, is_fixture_level=1),
			"FIX-450": attribute(output_level_name="450", sku_code="", value=450, is_fixture_level=1),
			"NOSKU": attribute(output_level_name="nosku", sku_code="", value=99, is_fixture_level=0),
		},
		"ilL-Attribute-CCT": {
			"2700K": attribute(cct_name="2700K Warm", code="27", kelvin=2700, label="2700K"),
			"3000K": attribute(cct_name="3000K", code="30", kelvin=3000, label=None),
			"4000K": attribute(cct_name=None, code="40", kelvin=4000, label="4000K Neutral"),
		},
		"ilL-Attribute-CRI": {
			"CRI-90": attribute(cri_name="90+", minimum_ra=90, code="9"),
			"CRI-95": attribute(cri_name="95+", minimum_ra=95, code="95"),
		},
		"ilL-Attribute-Finish": {
			"Black": attribute(finish_name="Matte Black", code="BK"),
			"White": attribute(finish_name=None, code="WH"),
			"Silver": attribute(finish_name="Anodized Silver", code="SV"),
		},
		"ilL-Attribute-Lens Appearance": {
			"Frosted": attribute(code="FR", transmission=56),
			"Clear": attribute(code="CL", transmission=0.92),
			"Opal": attribute(code="", transmission=40),
		},
		"ilL-Attribute-Mounting Method": {
			"Surface": attribute(code="S"),
			"Recessed": attribute(code="R"),
		},
		"ilL-Attribute-Environment Rating": {
			"Dry": attribute(code="20"),
			"Wet": attribute(code="67"),
			"Damp": attribute(code="54"),
		},
		"ilL-Attribute-IP Rating": {"IP65": attribute(code="65"), "IP68": attribute(code="68")},
		"ilL-Attribute-Power Feed Type": {"Wire": attribute(code="W"), "Plug": attribute(code="P")},
		"ilL-Attribute-Endcap Style": {"Flat": attribute(code="F")},
		"ilL-Attribute-Feed-Direction": {
			"End": attribute(code="E", direction_name="End", description="", is_active=1),
			"Back": attribute(code="B", direction_name="Back", description="", is_active=1),
			"Side": attribute(code="SD", direction_name="Side", description="", is_active=0),
		},
		"ilL-Attribute-Endcap Color": {
			"EC-Black": attribute(code="BK", display_name="Black Cap", is_active=1),
			"EC-White": attribute(code="WH", display_name=None, is_active=1),
		},
		"ilL-Rel-Finish Endcap Color": {
			"REL-1": attribute(
				finish="Black", endcap_color="EC-Black", is_default=1, is_active=1, modified=2
			),
			"REL-2": attribute(
				finish="White", endcap_color="EC-White", is_default=0, is_active=1, modified=3
			),
			"REL-3": attribute(
				finish="Silver", endcap_color="EC-Gone", is_default=0, is_active=1, modified=1
			),
			"REL-4": attribute(
				finish="Black", endcap_color="EC-White", is_default=0, is_active=0, modified=4
			),
		},
		"ilL-Attribute-Dimming Protocol": {
			"ELV": attribute(label="ELV", code="E"),
			"0-10V": attribute(label="0-10V Dimming", code="0"),
			"DALI": attribute(label=None, code="D"),
			"PWM": attribute(label="PWM", code="P"),
		},
		"ilL-Attribute-LED Package": {"LP-2835": attribute(code="28"), "LP-COB": attribute(code="")},
		"ilL-Attribute-Certification": {"UL": attribute(), "ETL": attribute()},
		"ilL-Spec-Profile": {
			"PRF-A": attribute(
				dimensions=None,
				width_mm=17.5,
				height_mm=7,
				stock_length_mm=2000,
				max_assembled_length_mm=6096,
				supported_environment_ratings=rows(
					{"environment_rating": "Wet"}, {"environment_rating": "Dry"}, {"environment_rating": ""}
				),
			),
			"PRF-B": attribute(
				dimensions='1.00" x 0.50"',
				width_mm=25.4,
				height_mm=12.7,
				stock_length_mm=None,
				max_assembled_length_mm=None,
				supported_environment_ratings=[],
			),
		},
		"ilL-Spec-LED-Sheet": {
			"SHEET-A": attribute(
				watts_per_sqft=7.5,
				cri=90,
				input_voltage="24V",
				sheet_width_ft=1,
				sheet_height_ft=2,
				cut_interval_width_in=2,
				cut_interval_height_in=1.5,
				operating_temp_min_c=-20,
				operating_temp_max_c=40,
			),
			"SHEET-B": attribute(
				watts_per_sqft=None,
				cri=95,
				input_voltage=None,
				sheet_width_ft=None,
				sheet_height_ft=None,
				cut_interval_width_in=None,
				cut_interval_height_in=None,
				operating_temp_min_c=0,
				operating_temp_max_c=0,
			),
		},
		"ilL-Spec-Driver": {
			"DRV-60": attribute(
				input_voltage_min=120,
				input_voltage_max=277,
				input_voltage_type="VAC",
				power_factor=0.95,
				efficiency="88%",
				width_mm=30,
				height_mm=40,
				depth_mm=150,
				inrush_aA=None,
				inrush_a=12,
				max_input_a=0.6,
				voltage_output=24,
				input_protocols=rows({"protocol": "0-10V"}, {"protocol": "ELV"}),
			),
			"DRV-96": attribute(
				input_voltage_min=100,
				input_voltage_max=277,
				input_voltage_type="VAC",
				power_factor=None,
				efficiency="90%",
				width_mm=None,
				height_mm=40,
				depth_mm=150,
				inrush_aA=20,
				max_input_aa=1.1,
				voltage_output=24,
				input_protocols=rows({"protocol": "DALI"}),
			),
		},
		"ilL-Attribute-Output Voltage": {"24V": attribute(code="24"), "48V": attribute(code="48")},
		"ilL-Attribute-Wireless": {},
		"Item": {
			"ITM-END": attribute(variant_of="ITM-END-TPL", image=None),
			"ITM-END-TPL": attribute(variant_of=None, image="/files/end.png"),
			"ITM-CLIP": attribute(variant_of=None, image="https://cdn/clip.png"),
		},
		"_rows": {
			"ilL-Child-Driver-Template-Variant": [
				attribute(
					parent="DRV-TPL", parenttype="ilL-Driver-Template", is_active=1, driver_spec="DRV-60"
				),
				attribute(
					parent="DRV-TPL", parenttype="ilL-Driver-Template", is_active=0, driver_spec="DRV-X"
				),
				attribute(
					parent="DRV-TPL", parenttype="ilL-Driver-Template", is_active=1, driver_spec="DRV-96"
				),
				attribute(parent="DRV-TPL", parenttype="ilL-Driver-Template", is_active=1, driver_spec=None),
			],
			OPTION: [
				attribute(parent="fixture-product", parenttype=PRODUCT, option_step=3, is_required=0),
				attribute(parent="tape-product", parenttype=PRODUCT, option_step=2, is_required=0),
			],
		},
	}


COLUMNS = {
	"ilL-Attribute-Endcap Color": ("code", "display_name", "is_active"),
	"ilL-Attribute-Feed-Direction": ("code", "is_active"),
	"ilL-Attribute-Mounting Method": ("code",),
	"ilL-Attribute-Lens Appearance": ("code",),
	"ilL-Attribute-Finish": ("code",),
	"ilL-Attribute-Environment Rating": ("code",),
	"ilL-Attribute-IP Rating": ("code",),
	"ilL-Attribute-Power Feed Type": ("code",),
	"ilL-Attribute-Endcap Style": ("code",),
	"ilL-Attribute-CCT": ("code",),
	"ilL-Attribute-PCB Mounting": ("code",),
}

# webflow_attributes.ATTRIBUTE_DOCTYPES, the entries the calculations look up.
ATTRIBUTE_DOCTYPES = {
	"output_level": {"doctype": "ilL-Attribute-Output Level", "code_field": "sku_code"},
	"cct": {"doctype": "ilL-Attribute-CCT", "code_field": "code"},
	"finish": {"doctype": "ilL-Attribute-Finish", "code_field": "code"},
	"lens": {"doctype": "ilL-Attribute-Lens Appearance", "code_field": "code"},
	"output_voltage": {"doctype": "ilL-Attribute-Output Voltage", "code_field": None},
}


class FakeDB:
	def __init__(self, data, calls):
		self.data = data
		self.calls = calls

	def record(self, doctype, name):
		return self.data.get(doctype, {}).get(name) if isinstance(name, str) else None

	def get_value(self, doctype, name, fields="name", as_dict=False, **kwargs):
		self.calls.append(("db.get_value", doctype, name))
		found = self.record(doctype, name)
		if found is None:
			return None
		found = {"name": name, **found}
		if isinstance(fields, (list, tuple)):
			values = {field: found.get(field) for field in fields}
			return _dict(values) if as_dict else tuple(values.values())
		return _dict({fields: found.get(fields)}) if as_dict else found.get(fields)

	def has_column(self, doctype, column):
		return column in COLUMNS.get(doctype, ())

	def exists(self, doctype, name=None):
		self.calls.append(("db.exists", doctype, name))
		if doctype == "DocType":
			return name in self.data or name in self.data["_rows"]
		return bool(self.record(doctype, name))


def _matches(row, filters):
	for key, wanted in (filters or {}).items():
		value = row.get(key)
		if isinstance(wanted, (list, tuple)) and wanted and wanted[0] == "in":
			if value not in wanted[1]:
				return False
		elif value != wanted:
			return False
	return True


def make_frappe(data, product_class=None):
	"""A fake frappe module over ``data``; ``frappe.calls`` lists every lookup."""
	frappe = types.ModuleType("frappe")
	calls = []
	frappe.calls = calls
	frappe._dict = _dict
	frappe._ = lambda text: text
	frappe.db = FakeDB(data, calls)
	frappe.conf = _dict()
	frappe.flags = _dict()
	frappe.local = types.SimpleNamespace()
	frappe.errors = []

	class DoesNotExistError(Exception):
		pass

	class ValidationError(Exception):
		pass

	frappe.DoesNotExistError = DoesNotExistError
	frappe.ValidationError = ValidationError

	def throw(message, *args, **kwargs):
		raise ValidationError(message)

	frappe.throw = throw
	frappe.log_error = lambda *args, **kwargs: frappe.errors.append((args, kwargs))
	frappe.msgprint = lambda *args, **kwargs: frappe.errors.append(("msgprint", args, kwargs))
	frappe.as_json = lambda value, indent=1: json.dumps(
		value, indent=indent, sort_keys=True, default=str, separators=(",", ": ")
	)
	frappe.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
	frappe.only_for = lambda *args, **kwargs: None

	def whitelist(**kwargs):
		return lambda function: function

	frappe.whitelist = whitelist

	def get_doc(doctype, name=None):
		calls.append(("get_doc", doctype, name))
		found = data.get(doctype, {}).get(name)
		if found is None:
			raise DoesNotExistError(f"{doctype} {name} not found")
		return Doc(doctype, name, **copy.deepcopy(found))

	frappe.get_doc = get_doc

	def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
		calls.append(("get_all", doctype, copy.deepcopy(filters)))
		if doctype in data["_rows"]:
			source = [dict(row) for row in data["_rows"][doctype]]
		else:
			source = [{"name": name, **row} for name, row in data.get(doctype, {}).items()]
		found = [row for row in source if _matches(row, filters)]
		for part in reversed([p.strip() for p in (order_by or "").split(",") if p.strip()]):
			key, _, direction = part.partition(" ")
			found.sort(
				key=lambda row, key=key: (
					row.get(key) is None,
					row.get(key) or 0 if not isinstance(row.get(key), str) else row.get(key),
				),
				reverse=direction.strip().lower() == "desc",
			)
		result = []
		for row in found:
			out = _dict()
			for field in fields or ["name"]:
				source_field, _, alias = field.partition(" as ")
				out[(alias or source_field).strip()] = row.get(source_field.strip())
			result.append(out)
		return result

	frappe.get_all = get_all

	def new_doc(doctype):
		calls.append(("new_doc", doctype))
		assert doctype == PRODUCT and product_class is not None, doctype
		return new_product(product_class)

	frappe.new_doc = new_doc
	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda value: int(value or 0)
	utils.flt = lambda value: float(value or 0)
	frappe.utils = utils
	return frappe


def enrich(record, doc):
	"""Stand-in for webflow_export_v2._enrich_specifications_from_linked_doctypes: echoes what
	it is given, so the parity test sees exactly what reaches it."""
	existing = sorted({row["spec_label"] for row in record["specifications"]})
	inputs = {key: record.get(key) for key in sorted(record) if key != "specifications"}
	from_doc = {
		field: getattr(doc, field, None)
		for field in ("operating_temp_min_c", "operating_temp_max_c", "l70_life_hours", "warranty_years")
	}
	certifications = [
		(row.certification, getattr(row, "webflow_badge_images", None))
		for row in getattr(doc, "certifications", None) or []
	]
	record["specifications"] += [
		{"spec_label": "Record", "spec_value": json.dumps(inputs, sort_keys=True), "display_order": 85},
		{"spec_label": "Doc", "spec_value": json.dumps(from_doc, sort_keys=True), "spec_unit": "doc"},
		{"spec_label": "Existing", "spec_value": ", ".join(existing), "attribute_doctype": "X"},
		{"spec_label": "Empty", "spec_value": ""},
		{
			"spec_label": "Certifications & Ratings",
			"spec_value": json.dumps(certifications),
			"display_order": 120,
			"attribute_options_json": "[]",
		},
	]


@contextmanager
def site(data=None, product_class=None, modules=None):
	"""Patch sys.modules with the fake frappe and the stand-ins the calculations import."""
	frappe = make_frappe(records() if data is None else data, product_class)
	document = types.ModuleType("frappe.model.document")
	document.Document = FakeDocument
	model = types.ModuleType("frappe.model")
	model.document = document
	export = types.ModuleType(ROOT + ".api.webflow_export_v2")
	export._enrich_specifications_from_linked_doctypes = enrich
	attributes = types.ModuleType(ROOT + ".api.webflow_attributes")
	attributes.ATTRIBUTE_DOCTYPES = ATTRIBUTE_DOCTYPES
	profile = types.ModuleType(ROOT + ".doctype.ill_spec_profile.ill_spec_profile")
	profile.compute_profile_dimensions = lambda width, height: f"{width} x {height}"
	stubs = {
		"frappe": frappe,
		"frappe.utils": frappe.utils,
		"frappe.model": model,
		"frappe.model.document": document,
		export.__name__: export,
		attributes.__name__: attributes,
		profile.__name__: profile,
	}
	with patch.dict(sys.modules, {**stubs, **(modules or {})}):
		yield frappe


def load(name):
	"""Import a module of the app afresh, bound to the fake frappe of the current ``site``."""
	sys.modules.pop(name, None)
	return importlib.import_module(name)


# ---------------------------------------------------------------- scenarios


def option(option_type, **values):
	return {"option_type": option_type, "is_active": 1, "is_default": 0, **values}


def fixture_template(**overrides):
	values = dict(
		template_name="Linear 100",
		display_name="  ",
		webflow_product="",
		product_category=None,
		series="SER-1",
		product_status="Active",
		default_profile_spec="PRF-A",
		assembled_max_len_mm=3048,
		default_profile_stock_len_mm=2000,
		allowed_tape_offerings=rows(
			{"tape_offering": "OFF-30-HO"},
			{"tape_offering": "OFF-40-HO"},
			{"tape_offering": ""},
			{"tape_offering": "OFF-27-LO"},
		),
		allowed_options=rows(
			option("Environment Rating", environment_rating="Wet"),
			option("Environment Rating", environment_rating="Dry", is_default=1),
			option("Lens Appearance", lens_appearance="Frosted", is_default=1),
			option("Lens Appearance", lens_appearance="Clear"),
			option("Lens Appearance", lens_appearance="Opal"),
			option("Lens Appearance", lens_appearance="Old", is_active=0),
			option("Mounting Method", mounting_method="Surface"),
			option("Mounting Method", mounting_method="Recessed", is_active=0),
			option("Finish", finish="Black"),
			option("Finish", finish="White"),
			option("Endcap Style", endcap_style="Flat"),
		),
		certifications=rows({"certification": "UL"}, {"certification": ""}, {"certification": "ETL"}),
		specifications=rows(
			{"spec_label": "Lens Options", "spec_value": "stale", "display_order": 60, "is_calculated": 1},
			{"spec_label": "Hand Note", "spec_value": "typed", "display_order": 55, "is_calculated": 0},
			{"spec_label": "Finish Options", "spec_value": "typed managed", "display_order": 5},
			{"spec_label": "No Order", "spec_value": "x", "display_order": None, "is_calculated": 0},
		),
		part_no_configurator=rows({"option_step": 3, "is_required": 0}, {"option_step": 1, "is_required": 1}),
	)
	values.update(overrides)
	return Doc("ilL-Fixture-Template", "FIX-TPL", **values)


def tape_template(name="TAPE-TPL", **overrides):
	values = dict(
		template_name="Tape HD",
		display_name="Tape HD Display",
		webflow_product="tape-product",
		product_category="LED Tape",
		webflow_category=None,
		beam_angle="120.0",
		spec_sheet_dimensions="10mm x 2mm",
		minimum_side_bend_diameter_mm=20,
		minimum_top_bend_diameter_mm=None,
		is_free_cutting=0,
		production_interval_mm=None,
		warranty_years=5,
		min_length_mm=305,
		max_length_mm=None,
		default_length_mm=1219,
		cut_increment_mm=None,
		allowed_tape_specs=rows({"tape_spec": "TAPE-A"}, {"tape_spec": "TAPE-B"}, {"tape_spec": None}),
		allowed_options=rows(
			option("Environment Rating", environment_rating="Dry", is_default=1),
			option("Environment Rating", environment_rating="Wet"),
			option("CCT", cct="3000K"),
			option("CCT", cct="2700K", is_default=1),
			option("CCT", cct="3000K"),
			option("Output Level", output_level="TAPE-400"),
			option("Output Level", output_level="NOSKU"),
			option("Output Level", output_level="TAPE-200", is_active=0),
			option("Power Feed Type", power_feed_type="Wire"),
			option("Mounting Method", mounting_method="Surface"),
			option("Finish", finish="Silver", custom_value_label="Silver (custom)"),
			option("Feed Direction", feed_direction="End", feed_position="Start"),
			option("Feed Direction", feed_direction="Back"),
			option("Feed Direction", feed_direction="Side", feed_position="End", is_default=1),
			option("IP Rating", ip_rating="IP65"),
		),
		feed_lengths=rows(
			{"step": 6, "code": "06", "label": "6 in", "display_order": 2, "idx": 1},
			{"step": 6, "code": "12", "label": "12 in", "display_order": 1, "idx": 2},
			{"step": 8, "code": "24", "label": "24 in", "display_order": 0, "idx": 3},
		),
		certifications=rows({"certification": "UL"}),
		specifications=rows({"spec_label": "Watts per Foot", "spec_value": "typed", "is_calculated": 0}),
		part_no_configurator=rows(
			{"option_step": 2, "is_required": 0, "option_type": "CCT"},
			{"option_step": 4, "is_required": "0"},
			{"option_step": None, "is_required": 0},
		),
	)
	values.update(overrides)
	return Doc("ilL-Tape-Neon-Template", name, **values)


def neon_template(**overrides):
	values = dict(
		webflow_category="neon",
		product_category="LED Tape",
		webflow_product="",
		is_free_cutting=1,
		production_interval_mm=None,
		minimum_side_bend_diameter_mm=None,
		minimum_top_bend_diameter_mm=50.8,
		beam_angle="wide",
		max_length_mm=15240,
		cut_increment_mm=25.4,
		allowed_tape_specs=rows({"tape_spec": "TAPE-C"}, {"tape_spec": "TAPE-A"}),
		part_no_configurator=rows({"option_step": 5, "is_required": 0}),
	)
	values.update(overrides)
	return tape_template("NEON-TPL", **values)


def led_sheet_template(**overrides):
	values = dict(
		template_name="Sheet",
		webflow_product="sheet-product",
		product_category="led-sheets",
		beam_angle=120,
		warranty_years=3,
		allowed_specs=rows({"spec": "SHEET-A"}, {"spec": "SHEET-B"}, {"spec": ""}),
		allowed_options=rows(
			option("CCT", attribute_link="3000K", option_code="30", is_default=1),
			option("CCT", attribute_link="4000K"),
			option("CCT", attribute_link="3000K"),
			option("Output Level", attribute_link="TAPE-600"),
			option("Output Level", output_level="TAPE-200"),
			option("Environment Rating", attribute_link="Dry"),
			option("Mounting", attribute_link="Adhesive"),
			option("Mounting Method", attribute_link="Surface"),
			option("Finish", attribute_link="Black", is_active=0),
			option("Finish", finish="White"),
		),
		part_no_configurator=rows({"option_step": 4, "is_required": 0}),
	)
	values.update(overrides)
	return Doc("ilL-LED-Sheet-Template", "SHEET-TPL", **values)


def driver_template(**overrides):
	values = dict(
		template_name="Driver 60-96W",
		webflow_product="driver-product",
		warranty_years=None,
		warranty=7,
		allowed_options=rows(
			option("Wattage", option_value="60", option_label="60W", option_code="060", is_default=1),
			option("Wattage", option_value="96"),
			option("Voltage Output", attribute_link="24V", attribute_doctype="ilL-Attribute-Output Voltage"),
			option("Voltage Output", attribute_link="48V", attribute_doctype="ilL-Attribute-Output Voltage"),
			option(
				"Input Protocol", attribute_link="0-10V", attribute_doctype="ilL-Attribute-Dimming Protocol"
			),
			option("Input Protocol", attribute_link="ELV", option_code="ELV", is_active=0),
			option("Output Protocol", attribute_link="DALI", attribute_doctype="ilL-Attribute-Missing"),
		),
		part_no_configurator=rows({"option_step": 2, "is_required": 0}),
	)
	values.update(overrides)
	return Doc("ilL-Driver-Template", "DRV-TPL", **values)


def controller_template(**overrides):
	values = dict(
		template_name="Controller",
		webflow_product="",
		product_category="controls",
		allowed_options=rows(
			option("Controller Type", option_value="Wall", option_code="W"),
			option("Channels", option_value="4"),
			option("Zones", option_value="1", is_default=1),
			option("Wireless Protocol", option_value="Zigbee", option_label="Zigbee 3.0"),
			option("Mounting Type", option_value="Surface", is_active=0),
		),
		part_no_configurator=[],
	)
	values.update(overrides)
	return Doc("ilL-Controller-Template", "CTL-TPL", **values)


def kit_template(**overrides):
	values = dict(
		template_name="Kit RA01",
		display_name="Rainier Kit",
		webflow_product="kit-product",
		product_category="extrusions",
		default_profile_spec="PRF-A",
		profile_stock_length_mm=None,
		default_profile_stock_len_mm=None,
		operating_temp_min_c=-20,
		operating_temp_max_c=45,
		allowed_options=rows(
			option("Lens Appearance", lens_appearance="Frosted", is_default=1),
			option("Lens Appearance", lens_appearance="Clear"),
			option("Mounting Method", mounting_method="Surface"),
			option("Finish", finish="Black"),
			option("Finish", finish="Silver", is_active=0),
		),
		kit_components=rows(
			{"component_type": "Endcap", "component_item": "ITM-END", "component_description": "End cap"},
			{"component_type": "Clip", "component_item": "ITM-CLIP", "component_description": None},
			{"component_type": "", "component_item": "ITM-X"},
			{"component_type": "Endcap", "component_item": None, "component_description": "Spare"},
		),
		certifications=rows({"certification": "UL"}),
		part_no_configurator=rows({"option_step": 4, "is_required": 0}),
	)
	values.update(overrides)
	return Doc("ilL-Extrusion-Kit-Template", "KIT-TPL", **values)


def scenarios():
	"""{name: template}, covering every template type."""
	return {
		"fixture": fixture_template(),
		"fixture_listed_as_a_controller": fixture_template(product_category="controls"),
		"fixture_without_options": fixture_template(
			allowed_options=[], allowed_tape_offerings=[], default_profile_spec="PRF-B", certifications=[]
		),
		"tape": tape_template(),
		"cob_tape": tape_template(product_category="cob-tape-unknown", webflow_category="cob-tape"),
		"tape_free_cutting_with_interval": tape_template(is_free_cutting=1, production_interval_mm=62.5),
		"neon": neon_template(),
		"tape_hand_set": tape_template(auto_populate_configurator=0),
		"led_sheet": led_sheet_template(),
		"driver": driver_template(),
		"controller": controller_template(),
		"kit": kit_template(),
		"kit_with_stock_length": kit_template(
			profile_stock_length_mm=None, default_profile_stock_len_mm=2438.4, default_profile_spec="PRF-B"
		),
		"kit_without_profile_stock": kit_template(
			default_profile_spec="PRF-B", operating_temp_min_c=0, operating_temp_max_c=0
		),
		"kit_without_profile": kit_template(default_profile_spec=None),
	}


# Products saved on their own (not through a template), for the product wrappers.
PRODUCT_CASES = {
	"fixture": ("fixture-product", "Fixture Template", "fixture_template", "FIX-TPL"),
	"tape": ("tape-product", "LED Tape", "tape_neon_template", "TAPE-TPL"),
	"neon": ("neon-product", "LED Neon", "tape_neon_template", "NEON-TPL"),
	"led_sheet": ("sheet-product", "LED Sheet", "led_sheet_template", "SHEET-TPL"),
	"driver": ("driver-product", "Driver", "driver_template", "DRV-TPL"),
	"controller": ("controller-product", "Controller", "controller_template", "CTL-TPL"),
	"kit": ("kit-product", "Extrusion Kit", "kit_template", "KIT-TPL"),
	"kit_missing_template": ("kit-product", "Extrusion Kit", "kit_template", "KIT-GONE"),
}

POPULATE = {
	"fixture_template": "populate_configurator_options",
	"tape_neon_template": "populate_tape_neon_configurator_options",
	"led_sheet_template": "populate_led_sheet_configurator_options",
	"driver_template": "populate_driver_configurator_options",
	"controller_template": "populate_controller_configurator_options",
	"kit_template": "populate_extrusion_kit_configurator_options",
}


def product_site_data():
	"""The records plus the saved templates the product cases read with get_doc."""
	data = records()
	for template in (
		fixture_template(),
		tape_template(),
		neon_template(),
		led_sheet_template(),
		driver_template(),
		controller_template(),
		kit_template(),
	):
		data.setdefault(template.doctype, {})[template.name] = {
			key: value for key, value in template.items() if key not in ("doctype", "name", "flags")
		}
	return data


# Steps a product (or a hand-set template) holds before the Tape/Neon refresh runs.
HAND_SET_TAPE_STEPS = (
	{"option_step": 1, "option_type": "Environment Rating", "option_label": "Environment"},
	{"option_step": 2, "option_type": "CCT", "option_label": "CCT", "is_required": 0},
	{"option_step": 4, "option_type": "Feed Direction", "option_label": "Start Feed Direction"},
	{"option_step": 5, "option_type": "Feed Direction", "option_label": "End Feed Direction"},
	{"option_step": 6, "option_type": "Feed Length", "option_label": "Start Feed Length"},
	{"option_step": 7, "option_type": "Finish", "option_label": "Finish"},
	{"option_step": 8, "option_type": "Unknown", "option_label": "Keep", "allowed_values_json": "[1]"},
)


def product_rows(product):
	"""What the product holds after its calculations, for comparison."""

	def plain(table):
		return [dict(row) for row in product.get(table) or []]

	return {
		"product_type": product.get("product_type"),
		"product_category": product.get("product_category"),
		"series": product.get("series"),
		"webflow_template_status": product.get("webflow_template_status"),
		"webflow_specifications": plain("webflow_specifications"),
		"configurator_options": plain("configurator_options"),
		"documents": plain("documents"),
		"certifications": plain("certifications"),
		"kit_components": plain("kit_components"),
	}
