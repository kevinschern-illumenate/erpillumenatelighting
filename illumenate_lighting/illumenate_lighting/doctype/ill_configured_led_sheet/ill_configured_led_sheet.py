# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import hashlib
import json
import math

import frappe
from frappe.model.document import Document


OPTION_FIELD_BY_TYPE = {
	"CCT": "selected_cct",
	"Output Level": "selected_output_level",
	"Environment Rating": "selected_environment_rating",
	"Mounting": "selected_mounting",
	"Finish": "selected_finish",
}
SKU_FIELD_BY_TYPE = {
	"CCT": "sku_cct_code",
	"Output Level": "sku_output_code",
	"Environment Rating": "sku_environment_code",
	"Mounting": "sku_mounting_code",
	"Finish": "sku_finish_code",
}


class ilLConfiguredLEDSheet(Document):
	def validate(self):
		self._validate_template_spec()
		self._validate_allowed_options()

	def before_save(self):
		self._compute_from_links()
		self._compute_quantities()
		self._compute_msrp()
		self._assemble_part_number()
		self._compute_config_hash()

	def _compute_from_links(self):
		if self.sheet_template:
			template = frappe.get_doc("ilL-LED-Sheet-Template", self.sheet_template)
			self.sku_series_code = template.sku_series_code
			self.jumper_cable_item = template.jumper_cable_item
			self.leader_cable_item = template.leader_cable_item
			for row in template.allowed_options or []:
				field = OPTION_FIELD_BY_TYPE.get(row.option_type)
				sku_field = SKU_FIELD_BY_TYPE.get(row.option_type)
				if field and sku_field and row.attribute_link == self.get(field):
					self.set(sku_field, row.option_code)

	def _compute_quantities(self):
		width = float(self.coverage_width_ft or 0)
		height = float(self.coverage_height_ft or 0)
		self.total_coverage_sqft = width * height
		if self.sheet_spec:
			spec = frappe.get_doc("ilL-Spec-LED-Sheet", self.sheet_spec)
			sheet_width = float(spec.sheet_width_ft or 0)
			sheet_height = float(spec.sheet_height_ft or 0)
			watts = float(spec.total_sheet_watts or 0)
			# Panel count uses actual sheet dimensions (per-axis ceil tiling),
			# not area-only division, to match the configurator engine.
			if sheet_width > 0 and sheet_height > 0 and width > 0 and height > 0:
				self.sheets_needed = math.ceil(width / sheet_width) * math.ceil(height / sheet_height)
			else:
				area = float(spec.sheet_area_sqft or 0)
				self.sheets_needed = math.ceil(self.total_coverage_sqft / area) if area else 0
			self.total_system_watts = self.sheets_needed * watts
		self.total_groups = len(self.groups or [])
		if not self.total_groups and self.sheets_needed:
			self.total_groups = 1
		self.jumper_cables_included = int(self.sheets_needed or 0) * 2
		self.jumper_cables_needed = max(0, (int(self.sheets_needed or 0) - int(self.total_groups or 0)) * 2)
		self.jumper_cables_extra = max(0, int(self.jumper_cables_needed or 0) - int(self.jumper_cables_included or 0))
		self.leader_cable_qty = int(self.total_groups or 0)

	def _assemble_part_number(self):
		segments = [
			self.sku_series_code,
			self.sku_environment_code,
			self.sku_cct_code,
			self.sku_output_code,
			self.sku_mounting_code,
			self.sku_finish_code,
		]
		if all(segments):
			self.part_number = "-".join(segments)
		else:
			missing = [label for label, value in zip(
				["series", "environment", "cct", "output", "mounting", "finish"],
				segments,
			) if not value]
			frappe.logger().warning(
				"Configured LED Sheet %s part number not assembled; missing SKU segment(s): %s",
				self.name or "(new)",
				", ".join(missing),
			)

	def _compute_msrp(self):
		if not self.sheet_template:
			return
		template = frappe.get_doc("ilL-LED-Sheet-Template", self.sheet_template)
		sheets_needed = int(self.sheets_needed or 0)
		# The configured LED Sheet MSRP represents the panel line only. Jumper,
		# leader, and power-supply cables/drivers are saved as their own
		# accessory schedule lines priced from Item Price, so they are excluded
		# here to avoid double-counting.
		msrp = sheets_needed * float(template.price_per_sheet_msrp or 0)
		for row in template.allowed_options or []:
			field = OPTION_FIELD_BY_TYPE.get(row.option_type)
			if row.is_active and field and row.attribute_link == self.get(field):
				msrp += sheets_needed * float(row.msrp_adder or 0)
		self.msrp = msrp

	def _item_price(self, item_code):
		if not item_code:
			return 0.0
		price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "selling": 1},
			"price_list_rate",
			order_by="valid_from desc, modified desc",
		)
		return float(price or 0)

	def _compute_config_hash(self):
		payload = {
			"sheet_template": self.sheet_template,
			"sheet_spec": self.sheet_spec,
			"selected_cct": self.selected_cct,
			"selected_output_level": self.selected_output_level,
			"selected_environment_rating": self.selected_environment_rating,
			"selected_mounting": self.selected_mounting,
			"selected_finish": self.selected_finish,
			"coverage_width_ft": self.coverage_width_ft,
			"coverage_height_ft": self.coverage_height_ft,
			"include_power_supply": bool(self.include_power_supply),
		}
		self.config_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

	def _validate_template_spec(self):
		if not (self.sheet_template and self.sheet_spec):
			return
		allowed = {row.spec for row in frappe.get_doc("ilL-LED-Sheet-Template", self.sheet_template).allowed_specs if row.is_active}
		if allowed and self.sheet_spec not in allowed:
			frappe.throw(f"LED Sheet Spec '{self.sheet_spec}' is not allowed for template '{self.sheet_template}'")

	def _validate_allowed_options(self):
		if not self.sheet_template:
			return
		template = frappe.get_doc("ilL-LED-Sheet-Template", self.sheet_template)
		for option_type, field in OPTION_FIELD_BY_TYPE.items():
			selected = self.get(field)
			if not selected:
				continue
			matches = [row for row in template.allowed_options if row.is_active and row.option_type == option_type and row.attribute_link == selected]
			if not matches:
				frappe.throw(f"Selected {option_type} '{selected}' is not allowed for template '{self.sheet_template}'")
