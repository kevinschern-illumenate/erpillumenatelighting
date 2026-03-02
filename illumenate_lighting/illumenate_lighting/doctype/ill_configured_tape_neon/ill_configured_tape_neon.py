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

	def validate(self):
		self._ensure_config_hash()

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
