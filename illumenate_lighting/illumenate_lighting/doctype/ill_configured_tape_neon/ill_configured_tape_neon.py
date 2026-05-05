# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import hashlib
import json

import frappe
from frappe.model.document import Document


class ilLConfiguredTapeNeon(Document):
	"""A fully configured LED Tape or LED Neon product.

	Analogous to ilL-Configured-Fixture but for tape/neon product categories.
	Stores the complete set of user selections, computed lengths, resolved items,
	and the resulting part number.

	The config_hash is a unique hash of all configuration inputs to enable
	dedup / cache - if someone configures the exact same product, we reuse the
	existing record.
	"""

	def before_insert(self):
		if not self.config_hash:
			self.config_hash = self._compute_config_hash()

	def before_save(self):
		"""Populate SKU code fields from the linked attribute records."""
		self._populate_sku_codes()

	def validate(self):
		self._ensure_config_hash()

	def _populate_sku_codes(self):
		"""
		Pull SKU codes from the linked attribute / template / offering records
		so that downstream consumers (PDF submittal mapping, Webflow exports)
		can read them off the configured doc directly.

		Mirrors ilLConfiguredFixture._populate_sku_codes() but only covers the
		sku_* fields that exist on ilL-Configured-Tape-Neon.
		"""
		# Series Code — from the tape/neon template's default profile family
		# when present (otherwise leave blank — neon templates do not always
		# carry a series code).
		series_code = ""
		if self.tape_neon_template:
			series_code = (
				frappe.db.get_value(
					"ilL-Tape-Neon-Template", self.tape_neon_template,
					"default_profile_family"
				) or ""
			)
		self.sku_series_code = series_code

		# LED Package Code — tape_offering → led_package → code
		led_package_code = ""
		if self.tape_offering:
			led_package_name = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "led_package"
			)
			if led_package_name:
				led_package_code = frappe.db.get_value(
					"ilL-Attribute-LED Package", led_package_name, "code"
				) or ""
		self.sku_led_package_code = led_package_code

		# CCT Code — prefer the configured doc's own cct link, fall back to
		# the linked tape_offering's cct.
		cct_code = ""
		cct_name = self.cct
		if not cct_name and self.tape_offering:
			cct_name = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "cct"
			)
		if cct_name:
			cct_code = frappe.db.get_value(
				"ilL-Attribute-CCT", cct_name, "code"
			) or ""
		self.sku_cct_code = cct_code

		# Output Code — output_level uses sku_code (not "code") on its
		# attribute doctype, matching ilL-Configured-Fixture.sku_tape_output_code.
		output_code = ""
		output_level_name = self.output_level
		if not output_level_name and self.tape_offering:
			output_level_name = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "output_level"
			)
		if output_level_name:
			output_code = frappe.db.get_value(
				"ilL-Attribute-Output Level", output_level_name, "sku_code"
			) or ""
		self.sku_output_code = output_code

		# Environment Code — environment_rating → code
		env_code = ""
		if self.environment_rating:
			env_code = frappe.db.get_value(
				"ilL-Attribute-Environment Rating", self.environment_rating, "code"
			) or ""
		self.sku_environment_code = env_code

		# PCB Mounting Code — pcb_mounting → code
		pcb_mounting_code = ""
		if getattr(self, "pcb_mounting", None):
			pcb_mounting_code = frappe.db.get_value(
				"ilL-Attribute-PCB Mounting", self.pcb_mounting, "code"
			) or ""
		self.sku_pcb_mounting_code = pcb_mounting_code

		# PCB Finish Code — pcb_finish → code (uses the Finish attribute)
		pcb_finish_code = ""
		if getattr(self, "pcb_finish", None):
			pcb_finish_code = frappe.db.get_value(
				"ilL-Attribute-Finish", self.pcb_finish, "code"
			) or ""
		self.sku_pcb_finish_code = pcb_finish_code

		# Feed Type Code — feed_type → code
		feed_type_code = ""
		if self.feed_type:
			feed_type_code = frappe.db.get_value(
				"ilL-Attribute-Power Feed Type", self.feed_type, "code"
			) or ""
		self.sku_feed_type_code = feed_type_code

	def _ensure_config_hash(self):
		if not self.config_hash:
			self.config_hash = self._compute_config_hash()

	def _compute_config_hash(self):
		"""Create a deterministic hash from the configuration inputs."""
		parts = [
			self.tape_neon_template or "",
			self.product_category or "",
			self.tape_spec or "",
			self.tape_offering or "",
			self.cct or "",
			self.output_level or "",
			self.environment_rating or "",
			self.pcb_mounting or "",
			self.pcb_finish or "",
			self.mounting_method or "",
			self.finish or "",
			self.feed_type or "",
			str(self.requested_length_mm or 0),
		]
		# Include neon segment data if multi-segment
		if self.product_category == "LED Neon" and self.segments:
			for seg in self.segments:
				parts.append(
					f"{seg.segment_index}:{seg.ip_rating or ''}:"
					f"{seg.start_feed_direction or ''}:{seg.start_lead_length_inches or 0}:"
					f"{seg.requested_length_mm or 0}:"
					f"{seg.end_type or ''}:{seg.end_feed_direction or ''}:"
					f"{seg.end_cable_length_inches or 0}"
				)
		raw = "|".join(parts)
		return hashlib.sha256(raw.encode()).hexdigest()[:16]
