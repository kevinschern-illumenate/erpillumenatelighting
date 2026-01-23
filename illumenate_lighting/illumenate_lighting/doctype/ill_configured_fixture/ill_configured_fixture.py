# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import hashlib
import json

import frappe
from frappe.model.document import Document


class ilLConfiguredFixture(Document):
	def autoname(self):
		"""
		Generate part number in format:
		ILL-{Profile Series}-{LED Package Code}-{Environment Code}-{CCT Code}-{Fixture Output Code}-{Lens Code}-{Mounting Code}-{Finish Code}-{Length in inches}
		
		If the document already has a name (e.g., loaded from database or name pre-set),
		keep the existing name to avoid duplicate errors.
		"""
		# If name is already set and exists in database, keep it
		if self.name and frappe.db.exists("ilL-Configured-Fixture", self.name):
			return
		
		# Generate new part number
		self.name = self._generate_part_number()

	def before_save(self):
		"""Compute config_hash and estimated_delivered_output before saving.

		The config_hash is normally set by the configurator engine when creating
		fixtures. This method only computes it if not already set (e.g., for
		manually created fixtures).
		"""
		if not self.config_hash:
			self.config_hash = self._compute_config_hash()
		
		# Always calculate estimated delivered output
		self._calculate_estimated_delivered_output()

	def _calculate_estimated_delivered_output(self):
		"""
		Calculate and store the estimated delivered output (lm/ft).
		
		Formula: tape_output_lm_ft × lens_transmission (decimal)
		
		This pulls the tape's output level value (lm/ft) and multiplies by
		the lens transmission (stored as decimal, e.g., 0.56 = 56%).
		"""
		if not self.tape_offering or not self.lens_appearance:
			self.estimated_delivered_output = None
			return

		# Get tape output level data
		output_level_name = frappe.db.get_value(
			"ilL-Rel-Tape Offering", self.tape_offering, "output_level"
		)
		if not output_level_name:
			self.estimated_delivered_output = None
			return

		tape_output_data = frappe.db.get_value(
			"ilL-Attribute-Output Level",
			output_level_name,
			["value"],
			as_dict=True
		)
		if not tape_output_data or not tape_output_data.value:
			self.estimated_delivered_output = None
			return

		tape_output_lm_ft = tape_output_data.value

		# Get lens transmission as decimal (stored as 0.56 = 56%)
		lens_transmission = frappe.db.get_value(
			"ilL-Attribute-Lens Appearance", self.lens_appearance, "transmission"
		)
		# Default to 1.0 (100%) if not specified
		if not lens_transmission:
			lens_transmission = 1.0

		# Calculate: tape output × transmission (decimal)
		self.estimated_delivered_output = round(tape_output_lm_ft * lens_transmission, 1)

	def _generate_part_number(self) -> str:
		"""Build the part number from linked doctypes."""
		parts = ["ILL"]

		# Profile Series from Fixture Template's default_profile_family
		profile_family = ""
		if self.fixture_template:
			profile_family = frappe.db.get_value(
				"ilL-Fixture-Template", self.fixture_template, "default_profile_family"
			) or ""
		parts.append(profile_family or "XX")

		# LED Package Code - get from tape_offering -> led_package -> code
		led_package_code = ""
		if self.tape_offering:
			led_package_name = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "led_package"
			)
			if led_package_name:
				led_package_code = frappe.db.get_value(
					"ilL-Attribute-LED Package", led_package_name, "code"
				) or ""
		parts.append(led_package_code or "XX")

		# Environment Code from environment_rating
		environment_code = ""
		if self.environment_rating:
			environment_code = frappe.db.get_value(
				"ilL-Attribute-Environment Rating", self.environment_rating, "code"
			) or ""
		parts.append(environment_code or "XX")

		# CCT Code from tape_offering -> cct -> code
		cct_code = ""
		if self.tape_offering:
			cct_name = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "cct"
			)
			if cct_name:
				cct_code = frappe.db.get_value("ilL-Attribute-CCT", cct_name, "code") or ""
		parts.append(cct_code or "XX")

		# Fixture Output Code = Output Level sku_code based on (tape output level * lens transmission %)
		fixture_output_code = self._get_fixture_output_code()
		parts.append(fixture_output_code or "XX")

		# Lens Code from lens_appearance
		lens_code = ""
		if self.lens_appearance:
			lens_code = frappe.db.get_value(
				"ilL-Attribute-Lens Appearance", self.lens_appearance, "code"
			) or ""
		parts.append(lens_code or "XX")

		# Mounting Code from mounting_method
		mounting_code = ""
		if self.mounting_method:
			mounting_code = frappe.db.get_value(
				"ilL-Attribute-Mounting Method", self.mounting_method, "code"
			) or ""
		parts.append(mounting_code or "XX")

		# Finish Code from finish
		finish_code = ""
		if self.finish:
			finish_code = frappe.db.get_value(
				"ilL-Attribute-Finish", self.finish, "code"
			) or ""
		parts.append(finish_code or "XX")

		# Requested Length in inches (convert from mm)
		length_inches = "0"
		if self.requested_overall_length_mm:
			length_inches = f"{self.requested_overall_length_mm / 25.4:.1f}"
		parts.append(length_inches)

		# Add suffix based on fixture complexity
		if self.is_multi_segment:
			# Multi-segment (jointed) fixtures: -J({hash})
			# Add a short hash suffix in parentheses to differentiate different segment
			# configurations with the same total length (e.g., 3x4ft vs 1x12ft vs 4x3ft all equal 120")
			if self.user_segments:
				segment_config_hash = self._compute_segment_config_hash()
				if segment_config_hash:
					parts.append(f"J({segment_config_hash})")
				else:
					parts.append("J")
			else:
				parts.append("J")
		else:
			# Single-segment fixtures: {feed_type}{cable_length_ft}-C
			# Get power feed type code
			feed_type_code = ""
			if self.power_feed_type:
				feed_type_code = frappe.db.get_value(
					"ilL-Attribute-Power Feed Type", self.power_feed_type, "code"
				) or self.power_feed_type or ""
			
			# Get leader cable length in feet (from first segment or leader_cable_length_mm field)
			cable_length_ft = 0
			if self.user_segments and len(self.user_segments) > 0:
				first_seg = self.user_segments[0]
				if first_seg.start_leader_cable_length_mm:
					cable_length_ft = round(first_seg.start_leader_cable_length_mm / 304.8, 1)
			elif hasattr(self, 'leader_cable_length_mm') and self.leader_cable_length_mm:
				cable_length_ft = round(self.leader_cable_length_mm / 304.8, 1)
			
			# Format cable length (remove .0 if whole number)
			if cable_length_ft == int(cable_length_ft):
				cable_length_str = str(int(cable_length_ft))
			else:
				cable_length_str = f"{cable_length_ft:.1f}"
			
			# Build suffix: {feed_type}{cable_length}-C
			parts.append(f"{feed_type_code}{cable_length_str}")
			parts.append("C")

		return "-".join(parts)

	def _compute_segment_config_hash(self) -> str:
		"""
		Compute a short hash of the segment configuration for part number uniqueness.

		This ensures that fixtures with the same options and total length but different
		segment layouts (e.g., 3x4ft vs 1x12ft) get unique part numbers.

		Returns:
			str: First 4 characters of the SHA-256 hash of segment configuration
		"""
		if not self.user_segments:
			return ""

		# Build segment config data for hashing
		segment_data = []
		for seg in self.user_segments:
			segment_data.append({
				"segment_index": seg.segment_index,
				"requested_length_mm": seg.requested_length_mm,
				"end_type": seg.end_type,
				"start_power_feed_type": seg.start_power_feed_type,
				"end_power_feed_type": seg.end_power_feed_type,
			})

		config_str = json.dumps(segment_data, sort_keys=True)
		# Use first 4 hex characters for brevity in part number
		return hashlib.sha256(config_str.encode()).hexdigest()[:4].upper()

	def _get_fixture_output_code(self) -> str:
		"""
		Calculate fixture output code based on tape output level value * lens transmission %.
		Returns the sku_code of the matching fixture-level output level.
		Falls back to the tape output level's sku_code if no fixture-level outputs are defined.
		"""
		if not self.tape_offering or not self.lens_appearance:
			return ""

		# Get tape output level data
		output_level_name = frappe.db.get_value(
			"ilL-Rel-Tape Offering", self.tape_offering, "output_level"
		)
		if not output_level_name:
			return ""

		tape_output_data = frappe.db.get_value(
			"ilL-Attribute-Output Level", 
			output_level_name, 
			["value", "sku_code"],
			as_dict=True
		)
		if not tape_output_data:
			return ""
		
		tape_output_value = tape_output_data.get("value") or 0
		tape_output_sku = tape_output_data.get("sku_code") or ""

		# Get lens transmission as decimal (0.56 = 56%)
		lens_transmission = frappe.db.get_value(
			"ilL-Attribute-Lens Appearance", self.lens_appearance, "transmission"
		) or 1.0

		# Calculate fixture output = tape output * transmission (decimal)
		fixture_output_value = int(round(tape_output_value * lens_transmission))

		# Find the closest fixture-level output level by value
		fixture_output_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code"],
			order_by="value asc"
		)

		if not fixture_output_levels:
			# Fallback: no fixture-level outputs defined, use tape output sku_code
			return tape_output_sku

		# Find closest match
		closest = min(fixture_output_levels, key=lambda x: abs((x.value or 0) - fixture_output_value))
		return closest.sku_code or tape_output_sku

	def _compute_config_hash(self) -> str:
		"""Return a SHA-256 hash of the configuration fields for deduplication.

		For multi-segment fixtures, this includes the user segment configuration
		to differentiate fixtures with the same total length but different segment
		layouts (e.g., 3x4ft vs 1x12ft).
		"""
		config_data = {
			"fixture_template": self.fixture_template,
			"tape_offering": self.tape_offering,
			"lens_appearance": self.lens_appearance,
			"mounting_method": self.mounting_method,
			"finish": self.finish,
			"environment_rating": self.environment_rating,
			"power_feed_type": self.power_feed_type,
			"endcap_style_start": self.endcap_style_start,
			"endcap_style_end": self.endcap_style_end,
			"endcap_color": self.endcap_color,
			"requested_overall_length_mm": self.requested_overall_length_mm,
			"is_multi_segment": 1 if self.is_multi_segment else 0,
		}

		# Include user segment configuration for multi-segment fixtures
		if self.is_multi_segment and self.user_segments:
			segment_data = []
			for seg in self.user_segments:
				segment_data.append({
					"segment_index": seg.segment_index,
					"requested_length_mm": seg.requested_length_mm,
					"end_type": seg.end_type,
					"start_power_feed_type": seg.start_power_feed_type,
					"end_power_feed_type": seg.end_power_feed_type,
					"start_leader_cable_length_mm": seg.start_leader_cable_length_mm,
					"end_jumper_cable_length_mm": seg.end_jumper_cable_length_mm,
				})
			config_data["user_segments"] = segment_data

		config_str = json.dumps(config_data, sort_keys=True)
		return hashlib.sha256(config_str.encode()).hexdigest()
