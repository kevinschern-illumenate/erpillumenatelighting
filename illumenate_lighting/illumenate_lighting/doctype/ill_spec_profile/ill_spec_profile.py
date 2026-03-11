# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document

MM_PER_INCH = 25.4


def _format_dimension(mm):
	"""Format a single dimension as xx.xx" (xx.xxmm)."""
	inches = mm / MM_PER_INCH
	return f'{inches:.2f}" ({mm:.2f}mm)'


def compute_profile_dimensions(width_mm, height_mm):
	"""Return the combined dimensions string for a profile.

	Formats the given width and height values (in mm) into the canonical
	'xx.xx" (xx.xxmm) x xx.xx" (xx.xxmm)' string used in the
	specification-json that syncs with Webflow.  Either value may be
	``None`` or ``0`` (treated as absent).

	This function is the single source of truth for profile dimensions
	formatting and is called:
	- by ``ilLSpecProfile.before_save`` to populate the stored field, and
	- by the Webflow sync paths when a profile has not yet been re-saved
	  with the computed ``dimensions`` field (on-the-fly fallback).
	"""
	width = width_mm or 0
	height = height_mm or 0

	if width and height:
		return f"{_format_dimension(width)} x {_format_dimension(height)}"
	if width:
		return f"{_format_dimension(width)} (W)"
	if height:
		return f"{_format_dimension(height)} (H)"
	return ""


class ilLSpecProfile(Document):
	def before_save(self):
		"""Calculate combined dimensions before saving."""
		self._calculate_dimensions()

	def _calculate_dimensions(self):
		"""Populate the ``dimensions`` field from ``width_mm`` and ``height_mm``."""
		self.dimensions = compute_profile_dimensions(self.width_mm, self.height_mm)
