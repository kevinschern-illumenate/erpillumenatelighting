"""Template calculations: a template's Specifications and Part No. Configurator (plan 4.17, 4.18).

Owner rule (2026-11-05): calculations on the template live solely in the template; they do not
rely on ilL-Webflow-Product. Everything here reads the template document (and the attribute and
spec records it links to), never a Webflow Product record.

The calculations were methods of ilL-Webflow-Product that a template ran on a temporary, unsaved
product. They moved here unchanged (``TemplateCalculator``), and build plain in-memory rows
(``frappe._dict``), so a template's rows are exactly what they were:

- ``calculate(template)``: the template's ``specifications`` and ``part_no_configurator`` rows
  (``template_listing.compute``);
- ``refresh_hand_set_tape_neon(template)``: a Tape/Neon template whose steps are set up by hand
  takes its current allowed options (moved from the product's save, owner 2026-11-05).

A Webflow Product saved on its own still runs the same calculations through thin wrappers
(``TemplateCalculator.for_product``) that write the rows into its own tables, as before, until
those tables are removed (plan 4.18).
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import is_tape_category
from illumenate_lighting.illumenate_lighting.api.tape_selection import closest_tape, transmission_fraction
from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	CONFIGURATOR_FIELD,
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)

TAPE = "ilL-Tape-Neon-Template"
TAPE_NEON_TYPES = ("LED Tape", "COB Tape", "LED Neon")
SPEC_FIELDS = (
	"spec_label",
	"spec_value",
	"display_order",
	"attribute_doctype",
	"attribute_options_json",
	"is_calculated",
)
CONFIGURATOR_FIELDS = (
	"option_step",
	"option_type",
	"option_label",
	"option_description",
	"is_required",
	"depends_on_step",
	"allowed_values_json",
)
# The calculation that builds each template type's configurator steps.
CONFIGURATOR_METHODS = {
	"fixture_template": "populate_configurator_options",
	"tape_neon_template": "populate_tape_neon_configurator_options",
	"led_sheet_template": "populate_led_sheet_configurator_options",
	"driver_template": "populate_driver_configurator_options",
	"controller_template": "populate_controller_configurator_options",
	"kit_template": "populate_extrusion_kit_configurator_options",
}
LINK_FIELDS = tuple(WEBFLOW_PRODUCT_LINKS.values())

# The template a Webflow Product type reads its specifications from.
PRODUCT_TYPE_TEMPLATE_MAP = {
	"LED Tape": {"link_field": "tape_neon_template", "doctype": "ilL-Tape-Neon-Template"},
	"COB Tape": {"link_field": "tape_neon_template", "doctype": "ilL-Tape-Neon-Template"},
	"LED Neon": {"link_field": "tape_neon_template", "doctype": "ilL-Tape-Neon-Template"},
	"Fixture Template": {"link_field": "fixture_template", "doctype": "ilL-Fixture-Template"},
	"Driver": {"link_field": "driver_template", "doctype": "ilL-Driver-Template"},
	"Controller": {"link_field": "controller_template", "doctype": "ilL-Controller-Template"},
	"LED Sheet": {"link_field": "led_sheet_template", "doctype": "ilL-LED-Sheet-Template"},
	"Extrusion Kit": {"link_field": "kit_template", "doctype": "ilL-Extrusion-Kit-Template"},
}

# Specification labels the calculation rebuilds on every run. Rows with any other label were
# typed by hand and are kept (template_listing and the Webflow Product use the same list).
MANAGED_LABELS = (
	"Color Rendering (CRI)",
	"Output Options",
	"Light Color (CCT)",
	"Lens Options",
	"Mounting Options",
	"Mounting",
	"Finish Options",
	"Finish",
	"Lenses",
	"Environment Ratings",
	"Environment Rating(s)",
	"Operating Temperature",
	"Production Interval",
	"Dimensions",
	"Dimensions (ft)",
	"Cut Interval",
	"Watts per Foot",
	"Watts per Square Foot",
	"Max Run Length",
	"Input Voltage",
	"Dimming",
	"Max Footage per 100W Supply",
	"Beam Spread",
	"Minimum Bending Diameter",
	"Warranty",
	"Power Factor",
	"Total Harmonic Distortion",
	"Efficiency",
	"Start Up Time",
	"Minimum Load",
	"Inrush Current",
	"Max Input Current",
	"Output Voltage",
	"Max Output Current",
	"Certifications",
	"Stock Length",
	"Max Assembled Length",
	"Cuttable",
	"Lens Interface",
)

# Environment Ratings are always listed Dry, Damp, Wet (owner, 2026-11-03); others follow A-Z.
ENVIRONMENT_ORDER = ("Dry", "Damp", "Wet")

# Linked-record rows a template type does not store (owner, 2026-11-03: kits leave out
# Certifications & Ratings; the Webflow export still adds it for kit products).
SKIPPED_LINKED_ROWS = {
	"Extrusion Kit": ("Certifications & Ratings",),
	# The calculation has "Color Rendering (CRI)" already (owner, 2026-11-13).
	"Fixture Template": ("Color Rendering",),
}

# What the export's spec enrichment reads from a product record.
LINKED_SPEC_KEYS = (
	"name",
	"product_type",
	"product_name",
	"fixture_template",
	"tape_neon_template",
	"led_sheet_template",
	"driver_template",
	"controller_template",
	"kit_template",
	"driver_spec",
	"controller_spec",
	"profile_spec",
	"lens_spec",
	"tape_spec",
	"accessory_spec",
)


def order_environment_ratings(ratings):
	unique = list(dict.fromkeys(r for r in ratings if r))
	return sorted(
		unique,
		key=lambda r: (ENVIRONMENT_ORDER.index(r) if r in ENVIRONMENT_ORDER else len(ENVIRONMENT_ORDER), r),
	)


def plain_rows(rows, fields):
	"""Pure: ``rows`` as plain dicts holding ``fields`` only."""
	return [{field: row.get(field) for field in fields} for row in rows or []]


def display_name(template):
	"""The name the product shows: Display Name, else Template Name (owner, 2026-11-02)."""
	return (template.get("display_name") or "").strip() or (template.get("template_name") or "").strip()


def product_type_for(template):
	"""The Webflow Product type a template is listed as: from its Webflow Category
	(``CATEGORY_PRODUCT_TYPES``), else from its doctype (Tape/Neon: its tape family)."""
	from illumenate_lighting.illumenate_lighting.web_listing_schema import (
		CATEGORY_PRODUCT_TYPES,
		template_category,
	)

	mapped = CATEGORY_PRODUCT_TYPES.get(template_category(template) or "")
	if mapped:
		return mapped
	field = WEBFLOW_PRODUCT_LINKS[template.doctype]
	if template.doctype == TAPE:
		return template.get("product_category") or WEBFLOW_PRODUCT_LINK_TYPES[field][0]
	return WEBFLOW_PRODUCT_LINK_TYPES[field][0]


def _resolve_attribute_code_field(doctype: str) -> str | None:
	"""Look up the column on an attribute doctype that stores its short code.

	Falls back to "code" for legacy/uncatalogued attribute doctypes; returns
	None if no plausible code column exists on the doctype.

	Most attribute doctypes use ``code``, but a few diverge
	(e.g. ``ilL-Attribute-Output Level`` -> ``sku_code``,
	``ilL-Attribute-Output Voltage`` -> ``voltage_code``).
	"""
	try:
		from illumenate_lighting.illumenate_lighting.api.webflow_attributes import (
			ATTRIBUTE_DOCTYPES,
		)
	except Exception:
		ATTRIBUTE_DOCTYPES = {}

	for cfg in ATTRIBUTE_DOCTYPES.values():
		if cfg.get("doctype") == doctype:
			return cfg.get("code_field") or None

	# Fallback: legacy default
	if frappe.db.has_column(doctype, "code"):
		return "code"
	return None


def format_inches(mm):
	if not mm:
		return None
	inches = float(mm) / 25.4
	return f'{inches:.2f}"'


def dimension_part(mm):
	"""Pure: 304.8 -> '12.00" (304.8mm)' (owner, 2026-11-12: curly inch mark, mm without
	trailing zeros)."""
	return f"{float(mm) / 25.4:.2f}\u201d ({float(mm):g}mm)"


def dimensions_text(width_mm, height_mm, length_mm=None, fallback=None):
	"""Pure: the Dimensions specification. Length (fixtures: the template's Min Length) first,
	then the profile's width and height, joined by ' \u00d7 '. When the profile has no width or
	height, its free-text Dimensions (``fallback``) is used, after the length if there is one.
	None when there is nothing to show."""
	parts = [dimension_part(length_mm)] if length_mm else []
	if width_mm and height_mm:
		parts += [dimension_part(width_mm), dimension_part(height_mm)]
	elif fallback:
		parts.append(fallback)
	elif not parts:
		return None
	return " \u00d7 ".join(parts)


def ceil_val(num):
	i = int(num)
	if num > i:
		return i + 1
	return i


def append_spec(current_doc, group, label, value, unit="", order=50, attr_doctype="", options=None):
	# D43: a placeholder is not a specification.
	if str(value or "").strip().upper() == "TBD":
		return
	current_doc.append(
		"webflow_specifications",
		{
			"spec_group": group,
			"spec_label": label,
			"spec_value": value,
			"spec_unit": unit,
			"is_calculated": 1,
			"display_order": order,
			"attribute_doctype": attr_doctype,
			"attribute_options_json": json.dumps(options, default=str, indent=1) if options else None,
		},
	)


def record(debug_dict, label, found_count=None, values=None, appended=False, skip_reason=None):
	debug_dict["results"][label] = {
		"found_count": found_count,
		"values": values or [],
		"appended": appended,
		"skip_reason": skip_reason,
	}


def sort_specifications(rows):
	"""Sort the rows by display_order (no order last) and renumber idx, in place."""
	if rows:
		# 1. Sort the list
		rows.sort(
			key=lambda row: (
				int(row.get("display_order")) if row.get("display_order") not in (None, "") else 999
			)
		)

		# 2. Re-assign idx so ERPNext saves and renders them in the new sorted order
		row_idx = 1
		for row in rows:
			row.idx = row_idx
			row_idx += 1


def calculate(template):
	"""The template's rows, from the template alone: (specifications, configurator steps).

	``specifications`` are the calculated rows, the rows typed on the template by hand (labels
	that are not calculated) and the rows from the linked spec records (``linked_spec_rows``).
	The configurator steps keep the template's own "Is Required" choices.
	"""
	calculator = TemplateCalculator.for_template(template)
	specifications = plain_rows(calculator.specification_rows(), SPEC_FIELDS)
	configurator = calculator.configurator_rows()
	return (
		specifications + linked_spec_rows(calculator, specifications),
		plain_rows(configurator, CONFIGURATOR_FIELDS),
	)


def linked_spec_rows(product, specifications):
	"""Rows the export adds from the linked spec records (CRI, input voltage, dimensions,
	dimming and the like): the same code (``_enrich_specifications_from_linked_doctypes``), so
	the template's Specifications are complete (owner, 2026-11-02). Marked ``is_calculated``.

	``product`` is a ``TemplateCalculator`` (or anything with ``get`` and the attributes the
	enrichment reads). A failure here leaves these rows out and is logged; it never blocks the
	template save.
	"""
	from illumenate_lighting.illumenate_lighting.api.webflow_export_v2 import (
		_enrich_specifications_from_linked_doctypes,
	)

	record = {field: product.get(field) for field in LINKED_SPEC_KEYS}
	record["specifications"] = [dict(row) for row in specifications]
	before = len(record["specifications"])
	try:
		_enrich_specifications_from_linked_doctypes(record, product)
	except Exception:
		frappe.log_error(title=f"Linked spec rows failed: {product.get('product_name')}")
		return []
	rows = []
	for row in record["specifications"][before:]:
		if row.get("spec_label") in SKIPPED_LINKED_ROWS.get(product.get("product_type"), ()):
			continue
		value = row.get("spec_value")
		if value in (None, ""):
			continue
		unit = row.get("spec_unit")
		rows.append(
			{
				"spec_label": row.get("spec_label"),
				"spec_value": f"{value} {unit}" if unit else value,
				"display_order": row.get("display_order") or 0,
				"attribute_doctype": row.get("attribute_doctype"),
				"attribute_options_json": row.get("attribute_options_json"),
				"is_calculated": 1,
			}
		)
	return rows


class TemplateCalculator:
	"""The specification and configurator calculations for one template, on in-memory rows.

	It holds what the calculations used to read from a Webflow Product: the product type, the
	link to the template, the template itself (``flags.template_doc``, so unsaved values are
	seen) and the "Is Required" choices to keep. ``webflow_specifications`` and
	``configurator_options`` are plain lists of ``frappe._dict`` rows; ``configurator_options``
	stays None until a configurator calculation runs (a product keeps its table then).
	"""

	def __init__(
		self,
		name=None,
		product_type=None,
		product_name=None,
		links=None,
		template_doc=None,
		existing_is_required=None,
		specifications=None,
	):
		self.name = name
		self.product_name = product_name
		self.product_type = product_type
		for field in LINK_FIELDS:
			setattr(self, field, (links or {}).get(field))
		self.flags = frappe._dict(template_doc=template_doc)
		# A dict, or a function returning one (read when a calculation needs it).
		self._existing_is_required = existing_is_required
		self.webflow_specifications = list(specifications or [])
		self.configurator_options = None
		# What the linked spec enrichment reads besides the record (``linked_spec_rows``).
		self.certifications = []
		self.operating_temp_min_c = None
		self.operating_temp_max_c = None
		self.l70_life_hours = None
		self.warranty_years = None

	@classmethod
	def for_template(cls, template):
		"""The calculations for ``template``, from the template alone.

		The values are the ones the temporary product had (``template_listing.shadow_product``
		until 2026-11-05): the Webflow Product name (or ``template:<name>``), the display name,
		the product type from the Webflow Category, only this template's link, the rows typed
		on the template by hand, and the template's own "Is Required" choices.
		"""
		field = WEBFLOW_PRODUCT_LINKS[template.doctype]
		return cls(
			name=template.get("webflow_product") or f"template:{template.name}",
			product_name=display_name(template) or template.name,
			product_type=product_type_for(template),
			links={field: template.name},
			template_doc=template,
			existing_is_required={
				int(row["option_step"]): int(row["is_required"] or 0)
				for row in plain_rows(template.get(CONFIGURATOR_FIELD), CONFIGURATOR_FIELDS)
				if row.get("option_step") is not None
			},
			# Hand-typed template rows go in first so the calculation keeps them (it only
			# replaces rows with calculated labels).
			specifications=[
				frappe._dict(row)
				for row in plain_rows(template.get("specifications"), SPEC_FIELDS)
				if not row.get("is_calculated")
			],
		)

	@classmethod
	def for_product(cls, product):
		"""The calculations a Webflow Product runs on its own save: its type and links, the
		template it was handed (``flags.template_doc``), its stored "Is Required" choices and
		its specification rows."""
		return cls(
			name=product.name,
			product_name=product.get("product_name"),
			product_type=product.get("product_type"),
			links={field: product.get(field) for field in LINK_FIELDS},
			template_doc=product.flags.template_doc,
			existing_is_required=product._get_existing_is_required,
			specifications=product.get("webflow_specifications"),
		)

	def get(self, key, default=None):
		return self.__dict__.get(key, default)

	def append(self, table, row):
		rows = getattr(self, table)
		if rows is None:
			rows = []
			setattr(self, table, rows)
		row = frappe._dict(row)
		rows.append(row)
		return row

	def _template_doc(self, doctype, name):
		"""The linked template: the one handed in when it matches (so the calculations see its
		unsaved values), else the saved one."""
		override = self.flags.template_doc
		if override is not None and override.doctype == doctype and override.name == name:
			return override
		return frappe.get_doc(doctype, name)

	def _get_existing_is_required(self) -> dict:
		"""{option_step: is_required} to keep, so an unchecked "Is Required" is not clobbered
		the next time the steps are calculated."""
		existing = self._existing_is_required
		if callable(existing):
			existing = existing()
		return existing or {}

	# ------------------------------------------------------------ specifications

	def specification_rows(self):
		"""The template's specification rows: what ``sync_custom_template_data`` did on the
		temporary product, without the parts only a product keeps (documents, kit components).
		The certifications and product type are set as that did, for ``linked_spec_rows``."""
		debug = {
			"product": self.name,
			"product_type": self.product_type,
			"existing_labels_before": [row.spec_label for row in (self.webflow_specifications or [])],
			"results": {},
		}
		if self.product_type not in PRODUCT_TYPE_TEMPLATE_MAP:
			for label in MANAGED_LABELS:
				record(debug, label, skip_reason=f"No mapping defined for product_type '{self.product_type}'")
		else:
			mapping = PRODUCT_TYPE_TEMPLATE_MAP[self.product_type]
			linked_doc_name = self.get(mapping["link_field"])
			debug["template_link_field"] = mapping["link_field"]
			debug["template_doctype"] = mapping["doctype"]
			debug["template_name"] = linked_doc_name

			if not linked_doc_name:
				reason = f"Field '{mapping['link_field']}' is empty on this product"
				for label in MANAGED_LABELS:
					record(debug, label, skip_reason=reason)
			else:
				template_doc = self._template_doc(mapping["doctype"], linked_doc_name)
				# The Webflow Category decides the product type (owner, 2026-11-03).
				from illumenate_lighting.illumenate_lighting.web_listing_schema import (
					CATEGORY_PRODUCT_TYPES,
					template_category,
				)

				category = template_category(template_doc)
				if category and CATEGORY_PRODUCT_TYPES.get(category):
					self.product_type = CATEGORY_PRODUCT_TYPES[category]
				self.certifications = [
					frappe._dict(certification=c_row.certification, display_order=0)
					for c_row in getattr(template_doc, "certifications", [])
					if c_row.certification
				]
				self.calculate_specifications(template_doc, debug)

		sort_specifications(self.webflow_specifications)
		debug["existing_labels_after"] = [row.spec_label for row in (self.webflow_specifications or [])]

		# Only when asked for in site config.
		if frappe.conf.get("webflow_enrichment_debug"):
			frappe.log_error(
				title=f"Combined Full Enrichment Debug: {self.name}",
				message=json.dumps(debug, indent=2, default=str),
			)
		return self.webflow_specifications

	def calculate_specifications(self, template_doc, debug):
		"""The calculated specification rows for ``template_doc`` (rows with a managed label
		are rebuilt, the rest are kept), by product type."""
		self.webflow_specifications = [
			row for row in (self.webflow_specifications or []) if row.spec_label not in MANAGED_LABELS
		]

		if self.product_type == "Fixture Template":
			offering_rows = template_doc.get("allowed_tape_offerings") or []
			debug["offering_rows_checked"] = len(offering_rows)

			offerings = []
			for t_row in offering_rows:
				offering_name = t_row.get("tape_offering")
				if not offering_name:
					continue
				data = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					offering_name,
					["cri", "output_level", "cct", "tape_spec"],
					as_dict=True,
				)
				if data:
					offerings.append(data)

			voltage_values = set()
			for o in offerings:
				tape_spec_name = o.get("tape_spec")
				if not tape_spec_name:
					continue
				input_voltage = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec_name, "input_voltage")
				if input_voltage:
					voltage_values.add(str(input_voltage))
			if voltage_values:
				append_spec(
					self,
					"Electrical",
					"Input Voltage",
					", ".join(sorted(voltage_values)),
					"",
					90,
					"ilL-Attribute-Output Voltage",
				)
				record(debug, "Input Voltage", len(voltage_values), sorted(voltage_values), appended=True)
			else:
				record(
					debug,
					"Input Voltage",
					0,
					skip_reason="No input_voltage values resolved from allowed_tape_offerings",
				)

			temp_values = set()
			for o in offerings:
				tape_spec_name = o.get("tape_spec")
				if not tape_spec_name:
					continue
				op_temp = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec_name, "operating_temp")
				if op_temp:
					temp_values.add(str(op_temp).strip())
			if temp_values:
				append_spec(
					self, "Environmental", "Operating Temperature", ", ".join(sorted(temp_values)), "", 120
				)
				record(debug, "Operating Temperature", len(temp_values), sorted(temp_values), appended=True)
			else:
				record(
					debug,
					"Operating Temperature",
					0,
					skip_reason="No operating_temp values resolved from allowed_tape_offerings",
				)

			cri_values = set()
			for o in offerings:
				if o.get("cri"):
					cri_values.add(str(o["cri"]))
			if cri_values:
				append_spec(
					self, "Optical", "Color Rendering (CRI)", ", ".join(sorted(cri_values)), "CRI", 50
				)
				record(debug, "Color Rendering (CRI)", len(cri_values), sorted(cri_values), appended=True)
			else:
				record(debug, "Color Rendering (CRI)", 0, skip_reason="No CRI values resolved")

			seen_output = set()
			output_pairs = []
			for o in offerings:
				ol_name = o.get("output_level")
				if ol_name and ol_name not in seen_output:
					seen_output.add(ol_name)
					ol_data = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						ol_name,
						["output_level_name", "sku_code"],
						as_dict=True,
					)
					if ol_data and ol_data.get("sku_code"):
						output_pairs.append(
							(ol_data["sku_code"], ol_data.get("output_level_name") or ol_name)
						)
			if output_pairs:
				options = [
					{
						"attribute_type": "Output Level",
						"attribute_doctype": "ilL-Attribute-Output Level",
						"code": pair[0],
						"display_label": pair[1],
					}
					for pair in output_pairs
				]
				append_spec(
					self,
					"Performance",
					"Output Options",
					", ".join(pair[1] for pair in output_pairs),
					"lm/ft",
					10,
					"ilL-Attribute-Output Level",
					options,
				)
				record(
					debug,
					"Output Options",
					len(output_pairs),
					[pair[1] for pair in output_pairs],
					appended=True,
				)
			else:
				record(debug, "Output Options", 0, skip_reason="No output_level values resolved")

			cct_pairs = []
			seen_cct = set()
			for o in offerings:
				if o.get("cct") and o["cct"] not in seen_cct:
					seen_cct.add(o["cct"])
					cct_data = frappe.db.get_value(
						"ilL-Attribute-CCT", o["cct"], ["cct_name", "code"], as_dict=True
					)
					if cct_data:
						cct_pairs.append((cct_data.get("code") or "", cct_data.get("cct_name") or o["cct"]))
			if cct_pairs:
				options = [
					{
						"attribute_type": "CCT",
						"attribute_doctype": "ilL-Attribute-CCT",
						"code": pair[0],
						"display_label": pair[1],
					}
					for pair in cct_pairs
				]
				append_spec(
					self,
					"Optical",
					"Light Color (CCT)",
					", ".join(pair[1] for pair in cct_pairs),
					"",
					40,
					"ilL-Attribute-CCT",
					options,
				)
				record(
					debug, "Light Color (CCT)", len(cct_pairs), [pair[1] for pair in cct_pairs], appended=True
				)
			else:
				record(debug, "Light Color (CCT)", 0, skip_reason="No CCT values resolved")

			wpf_values = set()
			run_values = set()
			for o in offerings:
				tape_spec_name = o.get("tape_spec")
				if not tape_spec_name:
					continue
				spec_data = frappe.db.get_value(
					"ilL-Spec-LED Tape",
					tape_spec_name,
					["watts_per_foot", "voltage_drop_max_run_length_ft"],
					as_dict=True,
				)
				if not spec_data:
					continue
				if spec_data.get("watts_per_foot"):
					wpf_values.add(float(spec_data["watts_per_foot"]))
				if spec_data.get("voltage_drop_max_run_length_ft"):
					run_values.add(float(spec_data["voltage_drop_max_run_length_ft"]))

			if wpf_values:
				sorted_wpf = sorted(wpf_values)
				append_spec(
					self, "Electrical", "Watts per Foot", ", ".join(f"{v:g}" for v in sorted_wpf), "W/ft", 20
				)
				record(
					debug, "Watts per Foot", len(sorted_wpf), [f"{v:g}" for v in sorted_wpf], appended=True
				)

				calc_footage = sorted([ceil_val(80.0 / v) for v in wpf_values if v > 0], reverse=True)
				if calc_footage:
					append_spec(
						self,
						"Electrical",
						"Max Footage per 100W Supply",
						", ".join(f"{v} ft" for v in calc_footage),
						"",
						35,
					)
					record(
						debug,
						"Max Footage per 100W Supply",
						len(calc_footage),
						[f"{v} ft" for v in calc_footage],
						appended=True,
					)
			else:
				record(debug, "Watts per Foot", 0, skip_reason="No watts_per_foot values resolved")
				record(
					debug,
					"Max Footage per 100W Supply",
					0,
					skip_reason="No watts_per_foot values resolved for footage calculation",
				)

			if run_values:
				sorted_run = sorted(run_values, reverse=True)
				append_spec(
					self, "Electrical", "Max Run Length", ", ".join(f"{v:g} ft" for v in sorted_run), "", 30
				)
				record(
					debug, "Max Run Length", len(sorted_run), [f"{v:g} ft" for v in sorted_run], appended=True
				)
			else:
				record(debug, "Max Run Length", 0, skip_reason="No max_run_length values resolved")

			cut_increments = set()
			for o in offerings:
				tape_spec_name = o.get("tape_spec")
				if not tape_spec_name:
					continue
				cut_mm = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec_name, "cut_increment_mm")
				if cut_mm:
					formatted = format_inches(cut_mm)
					if formatted:
						cut_increments.add(formatted)
			if cut_increments:
				append_spec(
					self, "Physical", "Production Interval", ", ".join(sorted(cut_increments)), "", 110
				)
				record(
					debug, "Production Interval", len(cut_increments), sorted(cut_increments), appended=True
				)
			else:
				record(debug, "Production Interval", 0, skip_reason="No cut_increment_mm values resolved")

			lens_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Lens Appearance" and o_row.get("lens_appearance"):
					lens_values.add(o_row.get("lens_appearance"))
			if lens_values:
				append_spec(
					self,
					"Optical",
					"Lens Options",
					", ".join(sorted(lens_values)),
					"",
					60,
					"ilL-Attribute-Lens Appearance",
				)
				record(debug, "Lens Options", len(lens_values), sorted(lens_values), appended=True)
			else:
				record(
					debug,
					"Lens Options",
					0,
					skip_reason="No active 'Lens Appearance' rows in allowed_options",
				)

			mount_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Mounting Method" and o_row.get("mounting_method"):
					mount_values.add(o_row.get("mounting_method"))
			if mount_values:
				append_spec(
					self,
					"Physical",
					"Mounting Options",
					", ".join(sorted(mount_values)),
					"",
					70,
					"ilL-Attribute-Mounting Method",
				)
				record(debug, "Mounting Options", len(mount_values), sorted(mount_values), appended=True)
			else:
				record(
					debug,
					"Mounting Options",
					0,
					skip_reason="No active 'Mounting Method' rows in allowed_options",
				)

			finish_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Finish" and o_row.get("finish"):
					disp = frappe.db.get_value(
						"ilL-Attribute-Finish", o_row.get("finish"), "finish_name"
					) or o_row.get("finish")
					finish_values.add(disp)
			if finish_values:
				append_spec(
					self,
					"Physical",
					"Finish Options",
					", ".join(sorted(finish_values)),
					"",
					80,
					"ilL-Attribute-Finish",
				)
				record(debug, "Finish Options", len(finish_values), sorted(finish_values), appended=True)
			else:
				record(debug, "Finish Options", 0, skip_reason="No active 'Finish' rows in allowed_options")

			profile_spec_name = template_doc.get("default_profile_spec")
			if profile_spec_name:
				profile = frappe.db.get_value(
					"ilL-Spec-Profile",
					profile_spec_name,
					["dimensions", "width_mm", "height_mm"],
					as_dict=True,
				)
				# Owner, 2026-11-12: Min Length x width x height, e.g.
				# 12.00" (304.8mm) x 0.59" (15mm) x 0.59" (15mm).
				dims = (
					dimensions_text(
						profile.get("width_mm"),
						profile.get("height_mm"),
						template_doc.get("min_length_mm"),
						profile.get("dimensions"),
					)
					if profile
					else None
				)
				if dims:
					append_spec(self, "Physical", "Dimensions", dims, "", 95)
					record(debug, "Dimensions", 1, [dims], appended=True)
				else:
					record(debug, "Dimensions", 0, skip_reason="Profile has no dimensions/width_mm/height_mm")
			else:
				record(debug, "Dimensions", 0, skip_reason="Template has no default_profile_spec")

			dimming_values = set()
			for o in offerings:
				tape_spec_name = o.get("tape_spec")
				if not tape_spec_name:
					continue
				tape_doc = frappe.get_doc("ilL-Spec-LED Tape", tape_spec_name)
				for row in tape_doc.get("supported_dimming_protocols") or []:
					protocol_name = row.get("protocol")
					if not protocol_name:
						continue
					label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", protocol_name, "label")
					dimming_values.add(label or protocol_name)
			if dimming_values:
				append_spec(
					self,
					"Control",
					"Dimming",
					", ".join(sorted(dimming_values)),
					"",
					100,
					"ilL-Attribute-Dimming Protocol",
				)
				record(debug, "Dimming", len(dimming_values), sorted(dimming_values), appended=True)
			else:
				record(debug, "Dimming", 0, skip_reason="No dimming protocols resolved")

			# Owner, 2026-11-13: "<warranty_years> year(s)".
			warranty = template_doc.get("warranty_years")
			if warranty:
				append_spec(self, "Performance", "Warranty", f"{warranty} year(s)", "", 150)
				record(debug, "Warranty", 1, [f"{warranty} year(s)"], appended=True)
			else:
				record(debug, "Warranty", 0, skip_reason="Template has no warranty_years")

		elif self.product_type in ("LED Tape", "COB Tape", "LED Neon"):
			tape_rows = template_doc.get("allowed_tape_specs") or []
			debug["tape_rows_checked"] = len(tape_rows)

			tape_specs = []
			for r in tape_rows:
				ts = r.get("tape_spec")
				if ts:
					tape_specs.append(ts)

			seen_output = set()
			output_pairs = []
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Output Level" and o_row.get("output_level"):
					ol_name = o_row.get("output_level")
					if ol_name not in seen_output:
						seen_output.add(ol_name)
						ol_data = frappe.db.get_value(
							"ilL-Attribute-Output Level",
							ol_name,
							["output_level_name", "sku_code"],
							as_dict=True,
						)
						if ol_data and ol_data.get("sku_code"):
							output_pairs.append(
								(ol_data["sku_code"], ol_data.get("output_level_name") or ol_name)
							)
			if output_pairs:
				options = [
					{
						"attribute_type": "Output Level",
						"attribute_doctype": "ilL-Attribute-Output Level",
						"code": pair[0],
						"display_label": pair[1],
					}
					for pair in output_pairs
				]
				append_spec(
					self,
					"Performance",
					"Output Options",
					", ".join(pair[1] for pair in output_pairs),
					"lm/ft",
					10,
					"ilL-Attribute-Output Level",
					options,
				)
				record(
					debug,
					"Output Options",
					len(output_pairs),
					[pair[1] for pair in output_pairs],
					appended=True,
				)
			else:
				record(debug, "Output Options", 0, skip_reason="No output_level values resolved")

			wpf_values = set()
			run_values = set()

			for ts in tape_specs:
				spec_data = frappe.db.get_value(
					"ilL-Spec-LED Tape",
					ts,
					["watts_per_foot", "voltage_drop_max_run_length_ft"],
					as_dict=True,
				)
				if spec_data:
					if spec_data.get("watts_per_foot"):
						wpf_values.add(float(spec_data["watts_per_foot"]))
					if spec_data.get("voltage_drop_max_run_length_ft"):
						run_values.add(float(spec_data["voltage_drop_max_run_length_ft"]))

			if wpf_values:
				sorted_wpf = sorted(wpf_values)
				append_spec(
					self, "Electrical", "Watts per Foot", ", ".join(f"{v:g}" for v in sorted_wpf), "W/ft", 20
				)
				record(
					debug, "Watts per Foot", len(sorted_wpf), [f"{v:g}" for v in sorted_wpf], appended=True
				)

				calc_footage = sorted([ceil_val(80.0 / v) for v in wpf_values if v > 0], reverse=True)
				if calc_footage:
					append_spec(
						self,
						"Electrical",
						"Max Footage per 100W Supply",
						", ".join(f"{v} ft" for v in calc_footage),
						"",
						40,
					)
					record(
						debug,
						"Max Footage per 100W Supply",
						len(calc_footage),
						[f"{v} ft" for v in calc_footage],
						appended=True,
					)
			else:
				record(debug, "Watts per Foot", 0, skip_reason="No watts_per_foot values resolved")
				record(
					debug,
					"Max Footage per 100W Supply",
					0,
					skip_reason="No watts_per_foot values resolved for footage calculation",
				)

			if run_values:
				sorted_run = sorted(run_values, reverse=True)
				append_spec(
					self, "Electrical", "Max Run Length", ", ".join(f"{v:g} ft" for v in sorted_run), "", 30
				)
				record(
					debug, "Max Run Length", len(sorted_run), [f"{v:g} ft" for v in sorted_run], appended=True
				)
			else:
				record(
					debug,
					"Max Run Length",
					0,
					skip_reason="No voltage_drop_max_run_length_ft values resolved",
				)

			cct_pairs = []
			seen_cct = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "CCT" and o_row.get("cct"):
					cct_val = o_row.get("cct")
					if cct_val not in seen_cct:
						seen_cct.add(cct_val)
						cct_data = frappe.db.get_value(
							"ilL-Attribute-CCT", cct_val, ["cct_name", "code"], as_dict=True
						)
						if cct_data:
							cct_pairs.append(
								(cct_data.get("code") or "", cct_data.get("cct_name") or cct_val)
							)
			if cct_pairs:
				options = [
					{
						"attribute_type": "CCT",
						"attribute_doctype": "ilL-Attribute-CCT",
						"code": pair[0],
						"display_label": pair[1],
					}
					for pair in cct_pairs
				]
				append_spec(
					self,
					"Optical",
					"Light Color (CCT)",
					", ".join(pair[1] for pair in cct_pairs),
					"",
					50,
					"ilL-Attribute-CCT",
					options,
				)
				record(
					debug, "Light Color (CCT)", len(cct_pairs), [pair[1] for pair in cct_pairs], appended=True
				)
			else:
				record(debug, "Light Color (CCT)", 0, skip_reason="No CCT values resolved")

			cri_values = set()
			for ts in tape_specs:
				cri = frappe.db.get_value("ilL-Spec-LED Tape", ts, "cri_typical")
				if cri:
					cri_values.add(str(cri))
			if cri_values:
				append_spec(
					self, "Optical", "Color Rendering (CRI)", ", ".join(sorted(cri_values)), "CRI", 60
				)
				record(debug, "Color Rendering (CRI)", len(cri_values), sorted(cri_values), appended=True)
			else:
				record(debug, "Color Rendering (CRI)", 0, skip_reason="No cri_typical values resolved")

			beam_angle = template_doc.get("beam_angle")
			if beam_angle:
				try:
					ba_int = int(float(beam_angle))
					append_spec(self, "Optical", "Beam Spread", f"{ba_int}°", "", 70)
					record(debug, "Beam Spread", 1, [f"{ba_int}°"], appended=True)
				except (ValueError, TypeError):
					record(debug, "Beam Spread", 0, skip_reason="Invalid beam_angle format")
			else:
				record(debug, "Beam Spread", 0, skip_reason="Template has no beam_angle")

			mount_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Mounting Method" and o_row.get("mounting_method"):
					mount_values.add(o_row.get("mounting_method"))
			if mount_values:
				append_spec(
					self,
					"Physical",
					"Mounting Options",
					", ".join(sorted(mount_values)),
					"",
					80,
					"ilL-Attribute-Mounting Method",
				)
				record(debug, "Mounting Options", len(mount_values), sorted(mount_values), appended=True)
			else:
				record(debug, "Mounting Options", 0, skip_reason="No Mounting Method values resolved")

			finish_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Finish" and o_row.get("finish"):
					disp = frappe.db.get_value(
						"ilL-Attribute-Finish", o_row.get("finish"), "finish_name"
					) or o_row.get("finish")
					finish_values.add(disp)
			if finish_values:
				append_spec(
					self,
					"Physical",
					"Finish Options",
					", ".join(sorted(finish_values)),
					"",
					90,
					"ilL-Attribute-Finish",
				)
				record(debug, "Finish Options", len(finish_values), sorted(finish_values), appended=True)
			else:
				record(debug, "Finish Options", 0, skip_reason="No Finish values resolved")

			voltage_values = set()
			for ts in tape_specs:
				iv = frappe.db.get_value("ilL-Spec-LED Tape", ts, "input_voltage")
				if iv:
					voltage_values.add(str(iv))
			if voltage_values:
				append_spec(
					self,
					"Electrical",
					"Input Voltage",
					", ".join(sorted(voltage_values)),
					"",
					100,
					"ilL-Attribute-Output Voltage",
				)
				record(debug, "Input Voltage", len(voltage_values), sorted(voltage_values), appended=True)
			else:
				record(debug, "Input Voltage", 0, skip_reason="No input_voltage values resolved")

			dimming_values = set()
			for ts in tape_specs:
				tape_doc = frappe.get_doc("ilL-Spec-LED Tape", ts)

				ip = tape_doc.get("input_protocol")
				if ip:
					label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", ip, "label")
					dimming_values.add(label or ip)

				for row in tape_doc.get("supported_dimming_protocols") or []:
					protocol_name = row.get("protocol")
					if protocol_name:
						label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", protocol_name, "label")
						dimming_values.add(label or protocol_name)
			if dimming_values:
				append_spec(
					self,
					"Control",
					"Dimming",
					", ".join(sorted(dimming_values)),
					"",
					110,
					"ilL-Attribute-Dimming Protocol",
				)
				record(debug, "Dimming", len(dimming_values), sorted(dimming_values), appended=True)
			else:
				record(debug, "Dimming", 0, skip_reason="No dimming protocols resolved")

			dimensions = template_doc.get("spec_sheet_dimensions")
			if dimensions:
				append_spec(self, "Physical", "Dimensions", dimensions, "", 120)
				record(debug, "Dimensions", 1, [dimensions], appended=True)
			else:
				record(debug, "Dimensions", 0, skip_reason="Template has no spec_sheet_dimensions")

			side_mm = template_doc.get("minimum_side_bend_diameter_mm")
			top_mm = template_doc.get("minimum_top_bend_diameter_mm")
			bend_parts = []

			if side_mm:
				side_in = float(side_mm) / 25.4
				bend_parts.append(f'Side Bend: {side_in:.2f}" ({float(side_mm):g}mm)')
			if top_mm:
				top_in = float(top_mm) / 25.4
				bend_parts.append(f'Top Bend: {top_in:.2f}" ({float(top_mm):g}mm)')

			if bend_parts:
				val = ", ".join(bend_parts)
				append_spec(self, "Physical", "Minimum Bending Diameter", val, "", 125)
				record(debug, "Minimum Bending Diameter", len(bend_parts), [val], appended=True)
			else:
				record(
					debug, "Minimum Bending Diameter", 0, skip_reason="Template has no side/top bend values"
				)

			is_free_cutting = template_doc.get("is_free_cutting")
			template_pi = template_doc.get("production_interval_mm")
			cut_increments = set()

			def format_pi(mm_val):
				inches = float(mm_val) / 25.4
				return f'{inches:.2f}" ({float(mm_val):.1f}mm)'

			if is_free_cutting and not template_pi:
				cut_increments.add("Free Cutting")
			elif template_pi:
				cut_increments.add(format_pi(template_pi))
			else:
				for ts in tape_specs:
					cut_mm = frappe.db.get_value("ilL-Spec-LED Tape", ts, "cut_increment_mm")
					if is_free_cutting and not cut_mm:
						cut_increments.add("Free Cutting")
					elif cut_mm:
						cut_increments.add(format_pi(cut_mm))
			if cut_increments:
				append_spec(
					self, "Physical", "Production Interval", ", ".join(sorted(cut_increments)), "", 130
				)
				record(
					debug, "Production Interval", len(cut_increments), sorted(cut_increments), appended=True
				)
			else:
				record(debug, "Production Interval", 0, skip_reason="No cut increments resolved")

			temp_values = set()
			for ts in tape_specs:
				op_temp = frappe.db.get_value("ilL-Spec-LED Tape", ts, "operating_temp")
				if op_temp:
					temp_values.add(str(op_temp).strip())
			if temp_values:
				append_spec(
					self, "Environmental", "Operating Temperature", ", ".join(sorted(temp_values)), "", 140
				)
				record(debug, "Operating Temperature", len(temp_values), sorted(temp_values), appended=True)
			else:
				record(debug, "Operating Temperature", 0, skip_reason="No operating_temp values resolved")

			warranty = template_doc.get("warranty_years")
			if warranty:
				append_spec(self, "Performance", "Warranty", f"{warranty} years", "", 150)
				record(debug, "Warranty", 1, [f"{warranty} years"], appended=True)
			else:
				record(debug, "Warranty", 0, skip_reason="Template has no warranty_years")

		elif self.product_type == "LED Sheet":
			sheet_rows = template_doc.get("allowed_specs") or []
			debug["sheet_rows_checked"] = len(sheet_rows)

			sheet_specs = []
			for r in sheet_rows:
				s = r.get("spec")
				if s:
					sheet_specs.append(s)

			seen_output = set()
			output_pairs = []
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Output Level":
					ol_name = o_row.get("attribute_link") or o_row.get("output_level")
					if ol_name and ol_name not in seen_output:
						seen_output.add(ol_name)
						ol_data = frappe.db.get_value(
							"ilL-Attribute-Output Level",
							ol_name,
							["output_level_name", "sku_code"],
							as_dict=True,
						)
						if ol_data and ol_data.get("sku_code"):
							output_pairs.append(
								(ol_data["sku_code"], ol_data.get("output_level_name") or ol_name)
							)
			if output_pairs:
				options = [
					{
						"attribute_type": "Output Level",
						"attribute_doctype": "ilL-Attribute-Output Level",
						"code": pair[0],
						"display_label": pair[1],
					}
					for pair in output_pairs
				]
				append_spec(
					self,
					"Performance",
					"Output Options",
					", ".join(pair[1] for pair in output_pairs),
					"lm/ft",
					10,
					"ilL-Attribute-Output Level",
					options,
				)

			wps_values = set()
			for s in sheet_specs:
				wps = frappe.db.get_value("ilL-Spec-LED-Sheet", s, "watts_per_sqft")
				if wps:
					wps_values.add(float(wps))
			if wps_values:
				sorted_wps = sorted(wps_values)
				append_spec(
					self,
					"Electrical",
					"Watts per Square Foot",
					", ".join(f"{v:g}" for v in sorted_wps),
					"W/sqft",
					20,
				)

				calc_footage = sorted([ceil_val(80.0 / v) for v in wps_values if v > 0], reverse=True)
				if calc_footage:
					append_spec(
						self,
						"Electrical",
						"Max Footage per 100W Supply",
						", ".join(f"{v} sqft" for v in calc_footage),
						"",
						35,
					)

			cct_pairs = []
			seen_cct = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "CCT":
					cct_val = o_row.get("attribute_link") or o_row.get("cct")
					if cct_val and cct_val not in seen_cct:
						seen_cct.add(cct_val)
						cct_data = frappe.db.get_value(
							"ilL-Attribute-CCT", cct_val, ["cct_name", "code"], as_dict=True
						)
						if cct_data:
							cct_pairs.append(
								(cct_data.get("code") or "", cct_data.get("cct_name") or cct_val)
							)
			if cct_pairs:
				options = [
					{
						"attribute_type": "CCT",
						"attribute_doctype": "ilL-Attribute-CCT",
						"code": pair[0],
						"display_label": pair[1],
					}
					for pair in cct_pairs
				]
				append_spec(
					self,
					"Optical",
					"Light Color (CCT)",
					", ".join(pair[1] for pair in cct_pairs),
					"",
					40,
					"ilL-Attribute-CCT",
					options,
				)

			cri_values = set()
			for s in sheet_specs:
				cri = frappe.db.get_value("ilL-Spec-LED-Sheet", s, "cri")
				if cri:
					cri_values.add(str(cri))
			if cri_values:
				append_spec(
					self, "Optical", "Color Rendering (CRI)", ", ".join(sorted(cri_values)), "CRI", 50
				)

			beam_angle = template_doc.get("beam_angle")
			if beam_angle:
				try:
					ba_int = int(float(beam_angle))
					append_spec(self, "Optical", "Beam Spread", f"{ba_int}°", "", 65)
				except (ValueError, TypeError):
					pass

			mount_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Mounting Method":
					mv = o_row.get("attribute_link") or o_row.get("mounting_method")
					if mv:
						mount_values.add(mv)
			if mount_values:
				append_spec(
					self,
					"Physical",
					"Mounting",
					", ".join(sorted(mount_values)),
					"",
					70,
					"ilL-Attribute-Mounting Method",
				)

			finish_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Finish":
					fv = o_row.get("attribute_link") or o_row.get("finish")
					if fv:
						disp = frappe.db.get_value("ilL-Attribute-Finish", fv, "finish_name") or fv
						finish_values.add(disp)
			if finish_values:
				append_spec(
					self,
					"Physical",
					"Finish",
					", ".join(sorted(finish_values)),
					"",
					80,
					"ilL-Attribute-Finish",
				)

			voltage_values = set()
			for s in sheet_specs:
				iv = frappe.db.get_value("ilL-Spec-LED-Sheet", s, "input_voltage")
				if iv:
					voltage_values.add(str(iv))
			if voltage_values:
				append_spec(
					self,
					"Electrical",
					"Input Voltage",
					", ".join(sorted(voltage_values)),
					"",
					90,
					"ilL-Attribute-Output Voltage",
				)

			append_spec(self, "Control", "Dimming", "TBD", "", 100)

			dims_list = set()
			for s in sheet_specs:
				spec_data = frappe.db.get_value(
					"ilL-Spec-LED-Sheet", s, ["sheet_width_ft", "sheet_height_ft"], as_dict=True
				)
				if spec_data and spec_data.get("sheet_width_ft") and spec_data.get("sheet_height_ft"):
					w_ft = float(spec_data["sheet_width_ft"])
					h_ft = float(spec_data["sheet_height_ft"])
					w_in = w_ft * 12
					h_in = h_ft * 12
					w_mm = w_ft * 304.8
					h_mm = h_ft * 304.8
					dims_list.add(f'{w_in:.2f}" ({w_mm:.1f}mm) × {h_in:.2f}" ({h_mm:.1f}mm)')  # noqa: RUF001
			if dims_list:
				append_spec(self, "Physical", "Dimensions (ft)", ", ".join(sorted(dims_list)), "", 95)

			cut_list = set()
			for s in sheet_specs:
				spec_data = frappe.db.get_value(
					"ilL-Spec-LED-Sheet", s, ["cut_interval_width_in", "cut_interval_height_in"], as_dict=True
				)
				if (
					spec_data
					and spec_data.get("cut_interval_width_in")
					and spec_data.get("cut_interval_height_in")
				):
					w_in = float(spec_data["cut_interval_width_in"])
					h_in = float(spec_data["cut_interval_height_in"])
					w_mm = w_in * 25.4
					h_mm = h_in * 25.4
					cut_list.add(f'{w_in:.2f}" ({w_mm:.1f}mm) × {h_in:.2f}" ({h_mm:.1f}mm)')  # noqa: RUF001
			if cut_list:
				append_spec(self, "Physical", "Cut Interval", ", ".join(sorted(cut_list)), "", 105)

			temp_list = set()
			for s in sheet_specs:
				spec_data = frappe.db.get_value(
					"ilL-Spec-LED-Sheet", s, ["operating_temp_min_c", "operating_temp_max_c"], as_dict=True
				)
				if (
					spec_data
					and spec_data.get("operating_temp_min_c") not in (None, "")
					and spec_data.get("operating_temp_max_c") not in (None, "")
					# D43: 0 to 0 means "not set".
					and (float(spec_data["operating_temp_min_c"]) or float(spec_data["operating_temp_max_c"]))
				):
					min_c = float(spec_data["operating_temp_min_c"])
					max_c = float(spec_data["operating_temp_max_c"])
					min_f = round(min_c * 9 / 5 + 32)
					max_f = round(max_c * 9 / 5 + 32)
					temp_list.add(f"{min_f}°F ({int(min_c)}°C) to {max_f}°F ({int(max_c)}°C)")
			if temp_list:
				append_spec(
					self, "Environmental", "Operating Temperature", ", ".join(sorted(temp_list)), "", 120
				)

			warranty = template_doc.get("warranty_years")
			if warranty:
				append_spec(self, "Performance", "Warranty", f"{warranty} years", "", 130)

		elif self.product_type == "Driver":
			variants = frappe.get_all(
				"ilL-Child-Driver-Template-Variant",
				filters={"parent": template_doc.name, "parenttype": "ilL-Driver-Template", "is_active": 1},
				fields=["driver_spec"],
			)

			spec_names = []
			for v in variants:
				if v.get("driver_spec"):
					spec_names.append(v.get("driver_spec"))

			iv_list = set()
			pf_list = set()
			eff_list = set()
			dims_list = set()
			inrush_list = set()
			max_input_list = set()
			out_v_list = set()
			dimming_list = set()

			for s in spec_names:
				d_spec = frappe.get_doc("ilL-Spec-Driver", s)

				v_min = d_spec.get("input_voltage_min")
				v_max = d_spec.get("input_voltage_max")
				v_type = d_spec.get("input_voltage_type")
				if v_min and v_max and v_type:
					iv_list.add(f"{v_min} - {v_max} {v_type}")

				pf = d_spec.get("power_factor")
				if pf:
					pf_list.add(str(pf))

				eff = d_spec.get("efficiency")
				if eff:
					eff_list.add(str(eff))

				w_mm = d_spec.get("width_mm")
				h_mm = d_spec.get("height_mm")
				d_mm = d_spec.get("depth_mm")
				if w_mm and h_mm and d_mm:
					w_in = format_inches(w_mm)
					h_in = format_inches(h_mm)
					d_in = format_inches(d_mm)
					dims_list.add(f"{w_in} ({w_mm}mm) × {h_in} ({h_mm}mm) × {d_in} ({d_mm}mm)")  # noqa: RUF001

				inrush = d_spec.get("inrush_aA") or d_spec.get("inrush_aa") or d_spec.get("inrush_a")
				if inrush:
					inrush_list.add(f"{inrush}A")

				max_in = d_spec.get("max_input_aA") or d_spec.get("max_input_aa") or d_spec.get("max_input_a")
				if max_in:
					max_input_list.add(f"{max_in}A")

				out_v = d_spec.get("voltage_output")
				if out_v:
					out_v_list.add(str(out_v))

				for p in d_spec.get("input_protocols") or []:
					proto = p.get("protocol")
					if proto:
						lbl = frappe.db.get_value("ilL-Attribute-Dimming Protocol", proto, "label")
						dimming_list.add(lbl or proto)

			if iv_list:
				append_spec(self, "Electrical", "Input Voltage", ", ".join(sorted(iv_list)), "", 10)
			if pf_list:
				append_spec(self, "Electrical", "Power Factor", ", ".join(sorted(pf_list)), "", 20)

			append_spec(self, "Electrical", "Total Harmonic Distortion", "TBD", "", 30)

			if eff_list:
				append_spec(self, "Electrical", "Efficiency", ", ".join(sorted(eff_list)), "", 40)

			append_spec(self, "Electrical", "Start Up Time", "TBD", "", 50)
			append_spec(self, "Electrical", "Minimum Load", "TBD", "", 60)

			if dims_list:
				append_spec(self, "Physical", "Dimensions", ", ".join(sorted(dims_list)), "", 70)
			if inrush_list:
				append_spec(self, "Electrical", "Inrush Current", ", ".join(sorted(inrush_list)), "", 80)
			if max_input_list:
				append_spec(
					self, "Electrical", "Max Input Current", ", ".join(sorted(max_input_list)), "", 90
				)
			if out_v_list:
				append_spec(self, "Electrical", "Output Voltage", ", ".join(sorted(out_v_list)), "", 100)

			append_spec(self, "Electrical", "Max Output Current", "TBD", "", 110)

			if dimming_list:
				append_spec(
					self,
					"Control",
					"Dimming",
					", ".join(sorted(dimming_list)),
					"",
					120,
					"ilL-Attribute-Dimming Protocol",
				)

			append_spec(self, "Compliance", "Certifications", "TBD", "", 130)
			append_spec(self, "Environmental", "Operating Temperature", "TBD", "", 140)

			warranty = template_doc.get("warranty_years") or template_doc.get("warranty")
			if warranty:
				append_spec(self, "Performance", "Warranty", f"{warranty} years", "", 150)

		elif self.product_type == "Extrusion Kit":
			# 1. Lenses
			lens_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Lens Appearance" and o_row.get("lens_appearance"):
					lens_values.add(o_row.get("lens_appearance"))
			if lens_values:
				append_spec(
					self,
					"",
					"Lenses",
					", ".join(sorted(lens_values)),
					"",
					10,
					"ilL-Attribute-Lens Appearance",
				)
				record(debug, "Lenses", len(lens_values), sorted(lens_values), appended=True)
			else:
				record(debug, "Lenses", 0, skip_reason="No Lens Appearance rows in allowed_options")

			# 2. Mounting
			mount_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Mounting Method" and o_row.get("mounting_method"):
					mount_values.add(o_row.get("mounting_method"))
			if mount_values:
				append_spec(
					self,
					"",
					"Mounting",
					", ".join(sorted(mount_values)),
					"",
					20,
					"ilL-Attribute-Mounting Method",
				)
				record(debug, "Mounting", len(mount_values), sorted(mount_values), appended=True)
			else:
				record(debug, "Mounting", 0, skip_reason="No Mounting Method rows in allowed_options")

			# 3. Finish
			finish_values = set()
			for o_row in template_doc.get("allowed_options") or []:
				if o_row.get("option_type") == "Finish" and o_row.get("finish"):
					disp = frappe.db.get_value(
						"ilL-Attribute-Finish", o_row.get("finish"), "finish_name"
					) or o_row.get("finish")
					finish_values.add(disp)
			if finish_values:
				append_spec(
					self, "", "Finish", ", ".join(sorted(finish_values)), "", 30, "ilL-Attribute-Finish"
				)
				record(debug, "Finish", len(finish_values), sorted(finish_values), appended=True)
			else:
				record(debug, "Finish", 0, skip_reason="No Finish rows in allowed_options")

			# 4. Dimensions (From default_profile_spec)
			profile_spec_name = template_doc.get("default_profile_spec")
			if not profile_spec_name:
				frappe.throw(
					f"Template '{template_doc.name}' is missing a Default Profile Spec. Dimensions are required for Extrusion Kits."
				)

			profile = frappe.db.get_value(
				"ilL-Spec-Profile",
				profile_spec_name,
				["dimensions", "width_mm", "height_mm"],
				as_dict=True,
			)
			# Owner, 2026-11-12: width x height in the fixtures' style, e.g. 0.63" (16mm) x 0.63" (16mm).
			dims = (
				dimensions_text(
					profile.get("width_mm"), profile.get("height_mm"), None, profile.get("dimensions")
				)
				if profile
				else None
			)

			if dims:
				append_spec(self, "", "Dimensions", dims, "", 40)
				record(debug, "Dimensions", 1, [dims], appended=True)
			else:
				frappe.throw(
					f"Profile Spec '{profile_spec_name}' is missing dimension values (width/height or dimensions string)."
				)

			# 4.5 Additional Profile Specs
			if profile_spec_name:
				try:
					profile_doc = frappe.get_doc("ilL-Spec-Profile", profile_spec_name)

					# Stock Length (Order 31)
					if profile_doc.stock_length_mm:
						stock_in = float(profile_doc.stock_length_mm) / 25.4
						stock_str = f'{stock_in:.1f}" ({profile_doc.stock_length_mm}mm)'
						append_spec(self, "Physical", "Stock Length", stock_str, "", 31)
						record(debug, "Stock Length", 1, [stock_str], appended=True)

					# Max Assembled Length (Order 32)
					if profile_doc.max_assembled_length_mm:
						max_in = float(profile_doc.max_assembled_length_mm) / 25.4
						max_str = f'{max_in:.1f}" ({profile_doc.max_assembled_length_mm}mm)'
						append_spec(self, "Physical", "Max Assembled Length", max_str, "", 32)
						record(debug, "Max Assembled Length", 1, [max_str], appended=True)

					# Environment Ratings (Order 49)
					env_ratings = []
					for env_row in profile_doc.get("supported_environment_ratings") or []:
						if env_row.environment_rating:
							env_ratings.append(env_row.environment_rating)

					if env_ratings:
						sorted_env = order_environment_ratings(env_ratings)
						append_spec(
							self,
							"Environmental",
							"Environment Rating(s)",
							", ".join(sorted_env),
							"",
							49,
							"ilL-Attribute-Environment Rating",
						)
						record(debug, "Environment Rating(s)", len(sorted_env), sorted_env, appended=True)
				except frappe.DoesNotExistError:
					record(
						debug,
						"Additional Profile Specs",
						0,
						skip_reason=f"Profile doc {profile_spec_name} not found",
					)

			# 5. Operating Temperature (Auto-calculated F to C)
			temp_min_c = template_doc.get("operating_temp_min_c")
			temp_max_c = template_doc.get("operating_temp_max_c")

			# D43: an unset Int field reads 0, so 0 to 0 means "not set".
			if (
				temp_min_c not in (None, "")
				and temp_max_c not in (None, "")
				and (float(temp_min_c) or float(temp_max_c))
			):
				min_c = float(temp_min_c)
				max_c = float(temp_max_c)
				min_f = round(min_c * 9 / 5 + 32)
				max_f = round(max_c * 9 / 5 + 32)
				temp_str = f"{min_f}°F ({int(min_c)}°C) to {max_f}°F ({int(max_c)}°C)"

				append_spec(self, "", "Operating Temperature", temp_str, "", 50)
				record(debug, "Operating Temperature", 1, [temp_str], appended=True)
			else:
				record(debug, "Operating Temperature", 0, skip_reason="Missing min/max temp on template")
		else:
			for label in MANAGED_LABELS:
				record(
					debug, label, skip_reason=f"Not yet implemented for product_type '{self.product_type}'"
				)

	# ------------------------------------------------------------ configurator

	def configurator_rows(self):
		"""The template's configurator steps (the calculation for its type)."""
		for field, method in CONFIGURATOR_METHODS.items():
			if self.get(field):
				getattr(self, method)()
				break
		return self.configurator_options or []

	def populate_configurator_options(self):
		"""Populate configurator options from template's allowed options.

		Step numbering aligns with CONFIGURATOR_STEPS in webflow_configurator.py:
		0-Series (locked), 1-Environment, 2-CCT, 3-Lens, 4-Output,
		5-Mounting, 6-Finish, 7-Length, 8-Start Feed Dir, 9-Start Feed Len,
		10-End Feed Dir, 11-End Feed Len.

		LED Package is part of the locked Series step (not a separate step).
		Endcap Color is auto-resolved from Finish via ilL-Rel-Finish Endcap Color.
		"""
		template = self._template_doc("ilL-Fixture-Template", self.fixture_template)

		# Configurator flow aligned with webflow_configurator.py CONFIGURATOR_STEPS
		# (step, option_type, label, depends_on_step)
		option_flow = [
			(1, "Environment Rating", "Dry/Wet", 0),
			(2, "CCT", "CCT", 1),
			(3, "Lens Appearance", "Lens", 0),
			(4, "Output Level", "Output", 3),
			(5, "Mounting Method", "Mounting", 0),
			(6, "Finish", "Finish", 0),
			(7, "Length", "Length", 0),
			(8, "Feed Direction", "Start Feed Direction", 0),
			(9, "Feed Direction", "Start Feed Length", 8),
			(10, "Feed Direction", "End Feed Direction", 0),
			(11, "Feed Direction", "End Feed Length", 10),
		]

		# Clear existing and rebuild
		self.configurator_options = []

		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_allowed_values_for_option(template, option_type, step=step)
			if allowed_values:
				self.append(
					"configurator_options",
					{
						"option_step": step,
						"option_type": option_type,
						"option_label": label,
						"is_required": 1,
						"depends_on_step": depends_on,
						"allowed_values_json": frappe.as_json(allowed_values),
					},
				)

		# Append Finish→Endcap Color mapping as metadata step
		finish_endcap_map = self._get_finish_endcap_color_mapping()
		if finish_endcap_map:
			self.append(
				"configurator_options",
				{
					"option_step": 99,
					"option_type": "Endcap Color",
					"option_label": "Finish→Endcap Color Mapping",
					"is_required": 0,
					"depends_on_step": 6,
					"allowed_values_json": frappe.as_json(finish_endcap_map),
				},
			)

		# Append fixture-level output level lookup table as metadata
		fixture_output_levels = self._get_fixture_output_level_table()
		if fixture_output_levels:
			self.append(
				"configurator_options",
				{
					"option_step": 98,
					"option_type": "Fixture Output Level",
					"option_label": "Fixture Output Level Lookup",
					"is_required": 0,
					"depends_on_step": 4,
					"allowed_values_json": frappe.as_json(fixture_output_levels),
				},
			)

	def populate_led_sheet_configurator_options(self):
		"""Populate configurator options from LED Sheet template allowed options."""
		template = self._template_doc("ilL-LED-Sheet-Template", self.led_sheet_template)
		option_flow = [
			(1, "CCT", "CCT", 0),
			(2, "Output Level", "Output", 1),
			(3, "Environment Rating", "Environment", 0),
			(4, "Mounting", "Mounting", 0),
			(5, "Finish", "Finish", 0),
			(6, "Coverage", "Coverage", 0),
		]

		existing_is_required = self._get_existing_is_required()

		self.configurator_options = []
		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_led_sheet_allowed_values(template, option_type)
			if allowed_values:
				self.append(
					"configurator_options",
					{
						"option_step": step,
						"option_type": option_type,
						"option_label": label,
						"is_required": existing_is_required.get(step, 1),
						"depends_on_step": depends_on,
						"allowed_values_json": frappe.as_json(allowed_values),
					},
				)

	def _get_led_sheet_allowed_values(self, template, option_type: str) -> list:
		if option_type == "Coverage":
			return [{"value": "__coverage_metadata__", "label": "Coverage", "code": ""}]
		values = []
		seen = set()
		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) != option_type or not getattr(opt, "is_active", 1):
				continue
			val = getattr(opt, "attribute_link", None)
			if not val or val in seen:
				continue
			seen.add(val)
			values.append(
				{
					"value": val,
					"label": val,
					"code": getattr(opt, "option_code", "") or "",
					"is_default": getattr(opt, "is_default", False),
				}
			)
		return values

	def populate_driver_configurator_options(self):
		"""Populate configurator options from the linked Driver template.

		Driver flow: Wattage → Voltage Output → Input Protocol → Output Protocol.
		Every axis is independent; the configurator resolves the full selection
		to exactly one ilL-Child-Driver-Template-Variant row.
		"""
		template = self._template_doc("ilL-Driver-Template", self.driver_template)
		option_flow = [
			(1, "Wattage", "Wattage", 0),
			(2, "Voltage Output", "Output Voltage", 0),
			(3, "Input Protocol", "Dimming Input", 0),
			(4, "Output Protocol", "Output Protocol", 0),
		]
		self._populate_variant_configurator_options(template, option_flow)

	def populate_controller_configurator_options(self):
		"""Populate configurator options from the linked Controller template.

		Controller flow: Controller Type → Channels → Zones → Input Protocol →
		Output Protocol → Wireless Protocol → Mounting Type. Channels and Zones
		depend on Controller Type; the rest are independent.
		"""
		template = self._template_doc("ilL-Controller-Template", self.controller_template)
		option_flow = [
			(1, "Controller Type", "Controller Type", 0),
			(2, "Channels", "Channels", 1),
			(3, "Zones", "Zones", 1),
			(4, "Input Protocol", "Input Protocol", 0),
			(5, "Output Protocol", "Output Protocol", 0),
			(6, "Wireless Protocol", "Wireless Protocol", 0),
			(7, "Mounting Type", "Mounting Type", 0),
		]
		self._populate_variant_configurator_options(template, option_flow)

	def populate_extrusion_kit_configurator_options(self):
		"""Populate configurator options for Extrusion Kits from linked ilL-Extrusion-Kit-Template.

		Steps:
		1. Lens Appearance (label: 'Lens')
		2. Mounting Method (label: 'Mounting')
		3. Finish (label: 'Finish')
		4. Length (label: 'Length', e.g., '2M (6.56ft)')
		"""
		if not self.kit_template:
			return

		try:
			template = self._template_doc("ilL-Extrusion-Kit-Template", self.kit_template)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Extrusion Kit template {self.kit_template} not found for product {self.name}",
				title="Extrusion Kit Template Not Found",
			)
			return

		existing_is_required = self._get_existing_is_required()
		self.configurator_options = []

		# Steps 1 to 3: Lens Appearance, Mounting Method, Finish
		option_flow = [
			(1, "Lens Appearance", "Lens", "lens_appearance", "ilL-Attribute-Lens Appearance"),
			(2, "Mounting Method", "Mounting", "mounting_method", "ilL-Attribute-Mounting Method"),
			(3, "Finish", "Finish", "finish", "ilL-Attribute-Finish"),
		]

		for step, option_type, label, field_name, attr_doctype in option_flow:
			values = []
			seen = set()

			for opt in template.allowed_options or []:
				if getattr(opt, "option_type", None) != option_type:
					continue
				if hasattr(opt, "is_active") and not opt.is_active:
					continue

				attr_val = getattr(opt, field_name, None)
				if not attr_val or attr_val in seen:
					continue
				seen.add(attr_val)

				code_field = _resolve_attribute_code_field(attr_doctype) or "code"
				code = frappe.db.get_value(attr_doctype, attr_val, code_field) or ""
				is_default = 1 if getattr(opt, "is_default", 0) else 0

				values.append(
					{
						"code": code,
						"is_default": is_default,
						"label": attr_val,
					}
				)

			if values:
				self.append(
					"configurator_options",
					{
						"option_step": step,
						"option_type": option_type,
						"option_label": label,
						"is_required": existing_is_required.get(step, 1),
						"depends_on_step": 0,
						"allowed_values_json": frappe.as_json(values),
					},
				)

		# Step 4: Length (Single stock length on template or fallback to default profile spec)
		stock_length_mm = (
			template.get("profile_stock_length_mm")
			or getattr(template, "profile_stock_length_mm", None)
			or template.get("default_profile_stock_len_mm")
		)
		if not stock_length_mm and template.get("default_profile_spec"):
			stock_length_mm = frappe.db.get_value(
				"ilL-Spec-Profile", template.default_profile_spec, "stock_length_mm"
			)

		if stock_length_mm:
			try:
				length_mm = float(stock_length_mm)
				meters = length_mm / 1000.0
				meters_str = f"{int(meters)}M" if meters.is_integer() else f"{meters:g}M"
				feet = length_mm / 304.8
				feet_str = f"{feet:.2f}ft"
				length_label = f"{meters_str} ({feet_str})"

				length_values = [
					{
						"code": meters_str,
						"is_default": 1,
						"label": length_label,
					}
				]

				self.append(
					"configurator_options",
					{
						"option_step": 4,
						"option_type": "Length",
						"option_label": "Length",
						"is_required": existing_is_required.get(4, 1),
						"depends_on_step": 0,
						"allowed_values_json": frappe.as_json(length_values),
					},
				)
			except (ValueError, TypeError):
				pass

	def _populate_variant_configurator_options(self, template, option_flow):
		"""Shared rebuild of configurator_options for variant-matched templates.

		Used by the Driver and Controller flows, whose allowed_options child
		tables share the same shape (option_type / attribute_link / option_value
		/ option_label / option_code / is_default / is_active).
		"""
		existing_is_required = self._get_existing_is_required()

		self.configurator_options = []
		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_variant_allowed_values(template, option_type)
			if not allowed_values:
				continue
			self.append(
				"configurator_options",
				{
					"option_step": step,
					"option_type": option_type,
					"option_label": label,
					"is_required": existing_is_required.get(step, 1),
					"depends_on_step": depends_on,
					"allowed_values_json": frappe.as_json(allowed_values),
				},
			)

	def _get_variant_allowed_values(self, template, option_type: str) -> list:
		"""Extract allowed values for one option type from a template's allowed_options.

		Attribute-backed rows resolve through ``attribute_link``; scalar rows
		(Wattage, Channels, Zones, Wireless Protocol) use ``option_value``.
		"""
		values = []
		seen = set()

		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) != option_type:
				continue
			if hasattr(opt, "is_active") and not opt.is_active:
				continue

			val = getattr(opt, "attribute_link", None) or getattr(opt, "option_value", None)
			if not val or val in seen:
				continue
			seen.add(val)

			code = getattr(opt, "option_code", "") or ""
			attribute_doctype = getattr(opt, "attribute_doctype", None)
			if not code and attribute_doctype:
				code_field = _resolve_attribute_code_field(attribute_doctype)
				if code_field:
					code = frappe.db.get_value(attribute_doctype, val, code_field) or ""

			values.append(
				{
					"value": val,
					"label": getattr(opt, "option_label", None) or val,
					"code": code,
					"is_default": bool(getattr(opt, "is_default", False)),
				}
			)

		return values

	def populate_tape_neon_configurator_options(self):
		"""Populate configurator options from tape/neon template's allowed options.

		LED Tape / COB Tape flow: Environment → CCT → Output → Power Feed Type → Length.
		LED Neon flow: CCT → Output → Finish → IP Rating → Feed Direction → Length.

		Mounting selection (PCB Mounting for tape, Mounting Method for neon) has been
		moved to a post-configuration mounting accessory step.

		User-overridden is_required values are preserved across saves so that, for
		example, Feed Direction can be marked as optional by unchecking the checkbox.
		"""
		template = self._template_doc("ilL-Tape-Neon-Template", self.tape_neon_template)

		if is_tape_category(self.product_type):
			option_flow = [
				(1, "Environment Rating", "Environment", 0),
				(2, "CCT", "CCT", 1),
				(3, "Output Level", "Output", 2),
				(4, "Power Feed Type", "Power Feed Type", 0),
				(5, "Length", "Length", 0),
			]
		else:
			# LED Neon
			# Feed Direction is split into Start/End so Webflow can render two
			# distinct cards. The values are filtered by ``feed_position`` on each
			# ilL-Child-Tape-Neon-Allowed-Option row (Both | Start | End).
			option_flow = [
				(1, "CCT", "CCT", 0),
				(2, "Output Level", "Output", 1),
				(3, "Finish", "Finish", 0),
				(4, "IP Rating", "IP Rating", 0),
				(5, "Start Feed Direction", "Start Feed Direction", 0),
				(6, "End Feed Direction", "End Feed Direction", 0),
				(7, "Length", "Length", 0),
			]

		# Preserve any user-modified is_required values from the database
		existing_is_required = self._get_existing_is_required()

		# Clear existing and rebuild
		self.configurator_options = []

		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_tape_neon_allowed_values(template, option_type)
			if allowed_values:
				# Use the previously saved is_required value if present; default to 1
				is_required = existing_is_required.get(step, 1)
				self.append(
					"configurator_options",
					{
						"option_step": step,
						"option_type": option_type,
						"option_label": label,
						"is_required": is_required,
						"depends_on_step": depends_on,
						"allowed_values_json": frappe.as_json(allowed_values),
					},
				)

	def _get_tape_neon_allowed_values(self, template, option_type: str) -> list:
		"""Extract allowed values from tape/neon template's allowed_options child table.

		Filters by is_active, maps to [{value, label, code, is_default}] format.
		For the Length step, returns length metadata instead.

		``Start Feed Direction`` / ``End Feed Direction`` resolve to the
		template's Feed Direction rows filtered by ``feed_position`` (rows
		marked Both appear in both buckets) so Webflow can render distinct
		Start vs End cards in the part-number builder.
		"""
		if option_type == "Length":
			return self._get_tape_neon_length_metadata(template)

		# Map option types to (child-table field, attribute doctype)
		option_field_map = {
			"CCT": ("cct", "ilL-Attribute-CCT"),
			"Output Level": ("output_level", "ilL-Attribute-Output Level"),
			"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
			"IP Rating": ("ip_rating", "ilL-Attribute-IP Rating"),
			"Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"Start Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"End Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
			"PCB Mounting": ("pcb_mounting", "ilL-Attribute-PCB Mounting"),
			"PCB Finish": ("pcb_finish", "ilL-Attribute-PCB Finish"),
			"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
			"Finish": ("finish", "ilL-Attribute-Finish"),
			"Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style"),
		}

		if option_type not in option_field_map:
			return []

		# Position filter for the Start/End feed-direction buckets.
		position_filter = None
		template_option_type = option_type
		if option_type == "Start Feed Direction":
			position_filter = "Start"
			template_option_type = "Feed Direction"
		elif option_type == "End Feed Direction":
			position_filter = "End"
			template_option_type = "Feed Direction"

		field, doctype = option_field_map[option_type]
		values = []
		seen = set()

		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) != template_option_type:
				continue
			if hasattr(opt, "is_active") and not opt.is_active:
				continue

			# For Start/End Feed Direction, include rows whose feed_position is
			# "Both" OR matches the requested side.
			if position_filter is not None:
				row_position = getattr(opt, "feed_position", None) or "Both"
				if row_position not in (position_filter, "Both"):
					continue

			val = getattr(opt, field, None)
			if not val or val in seen:
				continue
			seen.add(val)

			is_default = getattr(opt, "is_default", False) if hasattr(opt, "is_default") else False
			code = ""
			code_field = _resolve_attribute_code_field(doctype)
			if code_field:
				code = frappe.db.get_value(doctype, val, code_field) or ""

			# Build label
			label = val
			if option_type == "CCT":
				cct_data = frappe.db.get_value("ilL-Attribute-CCT", val, ["label", "kelvin"], as_dict=True)
				if cct_data:
					label = cct_data.get("label") or val
			elif option_type == "Output Level":
				level_data = frappe.db.get_value("ilL-Attribute-Output Level", val, ["value"], as_dict=True)
				if level_data and level_data.get("value"):
					label = f"{level_data['value']} lm/ft"

			values.append(
				{
					"value": val,
					"label": label,
					"code": code,
					"is_default": is_default,
				}
			)

		return values

	def _get_tape_neon_length_metadata(self, template) -> list:
		"""Get length constraints for tape/neon configurator Length step."""
		min_mm = getattr(template, "min_length_mm", None)
		max_mm = getattr(template, "max_length_mm", None)
		default_mm = getattr(template, "default_length_mm", None)
		increment_mm = getattr(template, "cut_increment_mm", None)

		# Convert to inches with sensible defaults
		min_inches = round(min_mm / 25.4, 1) if min_mm else 12
		max_inches = round(max_mm / 25.4, 1) if max_mm else 120
		default_inches = round(default_mm / 25.4, 1) if default_mm else 48
		increment_inches = round(increment_mm / 25.4, 2) if increment_mm else 0.5

		return [
			{
				"value": "__length_metadata__",
				"label": "Length",
				"code": "",
				"min_inches": min_inches,
				"max_inches": max_inches,
				"default_inches": default_inches,
				"increment_inches": increment_inches,
			}
		]

	def _get_allowed_values_for_option(self, template, option_type: str, step: int = 0) -> list:
		"""Get allowed values for a given option type.

		Each value includes {value, label, code, is_default} so the Webflow
		CMS JSON has attribute codes needed for part number building.
		"""
		values = []

		# Map option types to (template child-table field, attribute doctype)
		option_field_map = {
			"Finish": ("finish", "ilL-Attribute-Finish"),
			"Lens Appearance": ("lens_appearance", "ilL-Attribute-Lens Appearance"),
			"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
			"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
			"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
			"Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style"),
		}

		if option_type in option_field_map:
			field, doctype = option_field_map[option_type]
			for opt in template.allowed_options or []:
				if hasattr(opt, "option_type") and opt.option_type == option_type:
					if hasattr(opt, "is_active") and not opt.is_active:
						continue
					val = getattr(opt, field, None)
					if val:
						is_default = (
							getattr(opt, "is_default", False) if hasattr(opt, "is_default") else False
						)
						code_field = _resolve_attribute_code_field(doctype)
						code = (frappe.db.get_value(doctype, val, code_field) or "") if code_field else ""
						values.append({"value": val, "label": val, "code": code, "is_default": is_default})

		# Special handling for LED Package, CCT, Output Level (from tape offerings)
		elif option_type == "LED Package":
			values = self._get_led_packages_from_tapes(template)
		elif option_type == "CCT":
			values = self._get_ccts_from_tapes(template)
		elif option_type == "Output Level":
			values = self._get_output_levels_lens_map(template)
		elif option_type == "Endcap Color":
			# Get all endcap colors (globally available)
			colors = frappe.get_all(
				"ilL-Attribute-Endcap Color",
				filters={"is_active": 1}
				if frappe.db.has_column("ilL-Attribute-Endcap Color", "is_active")
				else {},
				fields=["name", "code", "display_name"]
				if frappe.db.has_column("ilL-Attribute-Endcap Color", "display_name")
				else ["name", "code"],
			)
			for c in colors:
				values.append(
					{"value": c.name, "label": c.get("display_name") or c.name, "code": c.get("code", "")}
				)
		elif option_type == "Feed Direction":
			values = self._get_feed_direction_values(step)
		elif option_type == "Length":
			values = self._get_length_metadata(template)

		return values

	def _get_feed_direction_values(self, step: int) -> list:
		"""Get feed direction or feed length values depending on step.

		Steps 8 (start feed), 10 (end feed) = directions (End, Back, etc.);
		steps 9 (start leader), 11 (end leader) = standard leader lengths.
		"""
		if step in (8, 10):
			# Direction options
			if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
				directions = frappe.get_all(
					"ilL-Attribute-Feed-Direction",
					filters={"is_active": 1}
					if frappe.db.has_column("ilL-Attribute-Feed-Direction", "is_active")
					else {},
					fields=["direction_name as name", "code", "description"],
					order_by="direction_name",
				)
				values = [{"value": d.name, "label": d.name, "code": d.get("code", "")} for d in directions]
			else:
				values = [
					{"value": "End", "label": "End", "code": "E"},
					{"value": "Back", "label": "Back", "code": "B"},
				]
			# End feed direction can also be "Endcap" (no leader)
			if step == 10:
				values.append({"value": "Endcap", "label": "Endcap", "code": "CAP"})
			return values
		else:
			# Leader length options (steps 9, 11)
			standard_lengths = [2, 4, 6, 8, 10, 15, 20, 25, 30]
			return [{"value": str(l), "label": f"{l} ft", "code": str(l)} for l in standard_lengths]

	def _get_length_metadata(self, template) -> list:
		"""Get length constraints as metadata for the Length step."""
		max_length_mm = getattr(template, "assembled_max_len_mm", None)
		default_stock_mm = getattr(template, "default_profile_stock_len_mm", None)

		min_inches = 12
		max_inches = round(max_length_mm / 25.4, 1) if max_length_mm else 120
		default_inches = round(default_stock_mm / 25.4, 1) if default_stock_mm else 50

		return [
			{
				"value": "__length_metadata__",
				"label": "Length",
				"code": "",
				"min_inches": min_inches,
				"max_inches": max_inches,
				"default_inches": default_inches,
				"increment_inches": 0.5,
			}
		]

	def _get_finish_endcap_color_mapping(self) -> list:
		"""Get Finish→Endcap Color mapping from ilL-Rel-Finish Endcap Color.

		Returns a list of {finish, endcap_color, endcap_color_code, is_default}
		so Webflow JS can filter endcap colors by the selected finish.
		"""
		mappings = frappe.get_all(
			"ilL-Rel-Finish Endcap Color",
			filters={"is_active": 1},
			fields=["finish", "endcap_color", "is_default"],
			order_by="is_default DESC, modified DESC",
		)
		result = []
		for m in mappings:
			ec_code = frappe.db.get_value("ilL-Attribute-Endcap Color", m.endcap_color, "code") or ""
			ec_label = ""
			if frappe.db.has_column("ilL-Attribute-Endcap Color", "display_name"):
				ec_label = (
					frappe.db.get_value("ilL-Attribute-Endcap Color", m.endcap_color, "display_name") or ""
				)
			result.append(
				{
					"finish": m.finish,
					"endcap_color": m.endcap_color,
					"endcap_color_code": ec_code,
					"endcap_color_label": ec_label or ec_code or m.endcap_color,
					"is_default": m.is_default,
				}
			)
		return result

	def _get_fixture_output_level_table(self) -> list:
		"""Get fixture-level output levels for client-side tape x lens→fixture mapping.

		The client multiplies tape output x lens transmission and finds the closest
		fixture-level output level to get the correct sku_code for the part number.
		"""
		fixture_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code"],
			order_by="value asc",
		)
		return [
			{
				"value": fl.name,
				"label": f"{fl.value} lm/ft",
				"code": fl.sku_code or "",
				"numeric_value": fl.value or 0,
			}
			for fl in fixture_levels
		]

	def _get_led_packages_from_tapes(self, template) -> list:
		"""Get unique LED packages from allowed tape offerings."""
		packages = {}
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, "tape_offering") and tape_row.tape_offering:
				led_package = frappe.db.get_value(
					"ilL-Rel-Tape Offering", tape_row.tape_offering, "led_package"
				)
				if led_package and led_package not in packages:
					code = frappe.db.get_value("ilL-Attribute-LED Package", led_package, "code")
					packages[led_package] = {"value": led_package, "label": led_package, "code": code or ""}
		return list(packages.values())

	def _get_ccts_from_tapes(self, template) -> list:
		"""Get unique CCTs from allowed tape offerings with details."""
		ccts = {}
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, "tape_offering") and tape_row.tape_offering:
				cct = frappe.db.get_value("ilL-Rel-Tape Offering", tape_row.tape_offering, "cct")
				if cct and cct not in ccts:
					cct_data = frappe.db.get_value(
						"ilL-Attribute-CCT", cct, ["code", "kelvin", "label"], as_dict=True
					)
					if cct_data:
						ccts[cct] = {
							"value": cct,
							"label": cct_data.get("label") or cct,
							"code": cct_data.get("code") or "",
							"kelvin": cct_data.get("kelvin") or 0,
						}
		return sorted(list(ccts.values()), key=lambda x: x.get("kelvin", 0))

	def _get_output_levels_from_tapes(self, template) -> list:
		"""Get unique output levels from allowed tape offerings with details.

		Each value includes tape_output_lm_ft so Webflow JS can compute
		delivered output (tape x lens transmission) client-side.
		"""
		levels = {}
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, "tape_offering") and tape_row.tape_offering:
				output_level = frappe.db.get_value(
					"ilL-Rel-Tape Offering", tape_row.tape_offering, "output_level"
				)
				if output_level and output_level not in levels:
					level_data = frappe.db.get_value(
						"ilL-Attribute-Output Level", output_level, ["sku_code", "value"], as_dict=True
					)
					if level_data:
						tape_lm_ft = level_data.get("value") or 0
						levels[output_level] = {
							"value": output_level,
							"label": f"{tape_lm_ft} lm/ft",
							"code": level_data.get("sku_code") or "",
							"lm_per_ft": tape_lm_ft,
							"tape_output_lm_ft": tape_lm_ft,
						}
		return sorted(list(levels.values()), key=lambda x: x.get("lm_per_ft", 0))

	def _get_output_levels_lens_map(self, template) -> dict:
		"""Build lens-keyed output mapping matrix for the Output step.

		Returns a dict with 'lensMap' keyed by lens code (e.g. WH, WL, WX).
		Each entry is a sorted list of output options showing delivered lumens
		(tape output x lens transmission) matched to fixture-level output levels.

		This lets the Webflow script dynamically rebuild Output radio buttons
		whenever the user changes the Lens selection.
		"""
		# Gather allowed lenses for this template
		lenses = []
		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) == "Lens Appearance" and getattr(opt, "is_active", True):
				lens_name = getattr(opt, "lens_appearance", None)
				if lens_name:
					lens_data = frappe.db.get_value(
						"ilL-Attribute-Lens Appearance",
						lens_name,
						["name", "code", "transmission"],
						as_dict=True,
					)
					if lens_data and lens_data.get("code"):
						lenses.append(lens_data)

		if not lenses:
			return {}

		# Get flat raw tape output levels
		raw_outputs = self._get_output_levels_from_tapes(template)
		if not raw_outputs:
			return {}

		# Get fixture-level output levels for closest-match snapping
		fixture_output_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code"],
			order_by="value asc",
		)

		lens_map = {}
		for lens in lenses:
			lens_code = lens.get("code")
			transmission = transmission_fraction(lens.get("transmission"))

			options = []
			by_level = {}
			for raw in raw_outputs:
				tape_lm = raw.get("tape_output_lm_ft") or raw.get("lm_per_ft") or 0
				delivered = tape_lm * transmission

				if fixture_output_levels:
					closest = min(fixture_output_levels, key=lambda x: abs((x.value or 0) - delivered))
					by_level.setdefault(closest.name, (closest, []))[1].append(
						{**raw, "output_value_lm_ft": tape_lm}
					)
				else:
					delivered_rounded = int(round(delivered))  # noqa: RUF046
					options.append(
						{
							"value": raw.get("value"),
							"label": f"{delivered_rounded} lm/ft",
							"code": raw.get("code", ""),
							"tape_output_lm_ft": tape_lm,
							"delivered_lm_ft": delivered_rounded,
						}
					)

			# Same rule as the configurator engine: of the tapes that round to a
			# level, the one whose delivered output is closest builds it.
			for level, candidates in by_level.values():
				raw = closest_tape(candidates, level.value or 0, transmission)
				options.append(
					{
						"value": raw.get("value"),
						"label": f"{level.value} lm/ft",
						"code": level.sku_code or raw.get("code", ""),
						"tape_output_lm_ft": raw["output_value_lm_ft"],
						"delivered_lm_ft": level.value,
					}
				)

			lens_map[lens_code] = sorted(options, key=lambda x: x.get("delivered_lm_ft", 0))

		return {"lensMap": lens_map}


# ---------------------------------------------------------------- hand-set Tape/Neon steps


def refresh_hand_set_tape_neon(template):
	"""A Tape/Neon template whose steps are set up by hand takes its current allowed options.

	Moved from the Webflow Product's save ("PART 2" of ``sync_custom_template_data``; owner,
	2026-11-05: the template's own refresh). Call from ``template_listing.refresh_template``,
	before the steps are renumbered. Each step's allowed values are rebuilt from the template's
	active Allowed Options (Start/End Feed Direction by feed position, feed lengths from the
	template's Feed Lengths, Length as the standard length metadata); an option type with no
	step gets a step 99, and a Length step is added when there is none.
	"""
	if template.doctype != TAPE or product_type_for(template) not in TAPE_NEON_TYPES:
		return
	template_doc = template

	LENGTH_METADATA_JSON = json.dumps(
		[
			{
				"code": "",
				"default_inches": 48,
				"increment_inches": 0.5,
				"label": "Length",
				"max_inches": 120,
				"min_inches": 12,
				"value": "__length_metadata__",
			}
		],
		indent=1,
	)

	OPTION_LINK_MAP = {
		"CCT": {"field": "cct", "doctype": "ilL-Attribute-CCT", "code_field": "code"},
		"Output Level": {
			"field": "output_level",
			"doctype": "ilL-Attribute-Output Level",
			"code_field": "sku_code",
		},
		"Lens Appearance": {
			"field": "lens_appearance",
			"doctype": "ilL-Attribute-Lens Appearance",
			"code_field": "code",
		},
		"Environment Rating": {
			"field": "environment_rating",
			"doctype": "ilL-Attribute-Environment Rating",
			"code_field": "code",
		},
		"IP Rating": {"field": "ip_rating", "doctype": "ilL-Attribute-IP Rating", "code_field": "code"},
		"Feed Direction": {
			"field": "feed_direction",
			"doctype": "ilL-Attribute-Feed-Direction",
			"code_field": "code",
		},
		"PCB Mounting": {
			"field": "pcb_mounting",
			"doctype": "ilL-Attribute-PCB Mounting",
			"code_field": "code",
		},
		"PCB Finish": {"field": "pcb_finish", "doctype": "ilL-Attribute-PCB Finish", "code_field": "code"},
		"Mounting Method": {
			"field": "mounting_method",
			"doctype": "ilL-Attribute-Mounting Method",
			"code_field": "code",
		},
		"Finish": {"field": "finish", "doctype": "ilL-Attribute-Finish", "code_field": "code"},
		"Endcap Style": {
			"field": "endcap_style",
			"doctype": "ilL-Attribute-Endcap Style",
			"code_field": "code",
		},
	}

	SPECIAL_TYPES = {"Feed Direction", "Length", "Power Feed Type"}

	def build_value(code, label, is_default):
		return {"code": code or "", "is_default": is_default or 0, "label": label, "value": label}

	def build_simple_values(template_rows, mapping_entry):
		values = []
		for t_row in template_rows:
			attr_name = t_row.get(mapping_entry["field"])
			if not attr_name:
				continue
			code_value = (
				frappe.db.get_value(mapping_entry["doctype"], attr_name, mapping_entry["code_field"]) or ""
			)
			disp = t_row.custom_value_label or attr_name
			values.append(
				{
					"code": code_value or "",
					"is_default": t_row.is_default or 0,
					"label": disp,
					"value": disp,
				}
			)
		return values

	options_by_type = {}
	for t_row in template_doc.allowed_options or []:
		if not t_row.is_active:
			continue
		if t_row.option_type not in options_by_type:
			options_by_type[t_row.option_type] = []
		options_by_type[t_row.option_type].append(t_row)

	feed_lengths_by_step = {}
	for fl in template_doc.feed_lengths or []:
		if fl.step not in feed_lengths_by_step:
			feed_lengths_by_step[fl.step] = []
		feed_lengths_by_step[fl.step].append(fl)

	existing_by_type = {}
	for cfg_row in template.get(CONFIGURATOR_FIELD) or []:
		if cfg_row.option_type not in existing_by_type:
			existing_by_type[cfg_row.option_type] = []
		existing_by_type[cfg_row.option_type].append(cfg_row)

	for cfg_row in template.get(CONFIGURATOR_FIELD) or []:
		label = cfg_row.option_label
		otype = cfg_row.option_type

		if otype == "Length":
			cfg_row.allowed_values_json = LENGTH_METADATA_JSON
			continue

		if label == "Start Feed Direction" or label == "End Feed Direction":
			is_end = label == "End Feed Direction"
			wanted = {"Both", "End"} if is_end else {"Both", "Start"}
			entry = OPTION_LINK_MAP["Feed Direction"]
			values = []
			for t_row in options_by_type.get("Feed Direction", []):
				if (t_row.feed_position or "Both") not in wanted:
					continue
				attr_name = t_row.get(entry["field"])
				if not attr_name:
					continue
				code_value = frappe.db.get_value(entry["doctype"], attr_name, entry["code_field"]) or ""
				disp = t_row.custom_value_label or attr_name
				values.append(build_value(code_value, disp, t_row.is_default))
			if is_end:
				values.append(build_value("C", "Endcap", 0))
			cfg_row.allowed_values_json = json.dumps(values, indent=1)
			continue

		if label == "Start Feed Length" or label == "End Feed Length":
			values = [build_value("", "Endcap", 0)]
			for fl in sorted(
				feed_lengths_by_step.get(cfg_row.option_step, []),
				key=lambda r: (r.display_order or 0, r.idx or 0),
			):
				values.append(build_value(fl.code, fl.label, 0))
			cfg_row.allowed_values_json = json.dumps(values, indent=1)
			continue

		entry = OPTION_LINK_MAP.get(otype)
		if entry:
			values = build_simple_values(options_by_type.get(otype, []), entry)
			cfg_row.allowed_values_json = json.dumps(values, indent=1)

	for template_type in options_by_type.keys():
		if template_type in SPECIAL_TYPES:
			continue
		if template_type in existing_by_type:
			continue
		entry = OPTION_LINK_MAP.get(template_type)
		if not entry:
			continue
		values = build_simple_values(options_by_type.get(template_type, []), entry)
		template.append(
			CONFIGURATOR_FIELD,
			{
				"option_type": template_type,
				"option_label": template_type,
				"option_step": 99,
				"allowed_values_json": json.dumps(values, indent=1),
			},
		)

	has_length = False
	finish_step = None
	max_step = 0
	for cfg_row in template.get(CONFIGURATOR_FIELD) or []:
		if cfg_row.option_type == "Length":
			has_length = True
		if cfg_row.option_type == "Finish":
			finish_step = cfg_row.option_step
		if cfg_row.option_step and cfg_row.option_step > max_step:
			max_step = cfg_row.option_step

	if not has_length:
		if finish_step:
			length_step = finish_step + 1
		elif max_step:
			length_step = max_step + 1
		else:
			length_step = 99
		template.append(
			CONFIGURATOR_FIELD,
			{
				"option_type": "Length",
				"option_label": "Length",
				"option_step": length_step,
				"allowed_values_json": LENGTH_METADATA_JSON,
			},
		)
