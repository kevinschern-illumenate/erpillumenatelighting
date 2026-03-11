# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Shared utility functions for ilLumenate Lighting.

This module provides common helper functions used across the application,
including input validation, parsing utilities, and CORS handling.
"""

import frappe

# ---------------------------------------------------------------------------
# CORS – Allowed Webflow origins
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = [
	"https://www.illumenatelighting.com",
	"https://illumenatelighting.com",
	"https://illumenatelighting.webflow.io",
	"https://illumenate-staging.webflow.io",
	"https://illumenate.lighting",
	"https://www.illumenate.lighting",
]


def after_request(response):
	"""Frappe after_request hook – inject CORS headers for allowed Webflow origins.

	Args:
		response: The werkzeug Response object passed by Frappe's after_request hook.
	"""
	origin = frappe.request.headers.get("Origin") if frappe.request else None
	if not origin or origin not in ALLOWED_ORIGINS:
		return

	response.headers["Access-Control-Allow-Origin"] = origin
	response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
	response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Frappe-Token"
	response.headers["Access-Control-Allow-Credentials"] = "true"
	response.headers["Vary"] = "Origin"


def parse_positive_int(value, default: int = 1, minimum: int = 1) -> int:
	"""
	Parse a value as a positive integer with bounds checking.

	This function is designed for defensive input handling where invalid
	or out-of-range values should be silently corrected rather than raising errors.

	Args:
		value: Value to parse
		default: Default value if parsing fails
		minimum: Minimum allowed value (result will be clamped to this)

	Returns:
		int: Parsed integer, at least the minimum value. If parsing fails,
		     returns the default value.
	"""
	try:
		return max(minimum, int(value))
	except (ValueError, TypeError):
		return default


# Pagination constants
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Access level constants
VALID_ACCESS_LEVELS = ["VIEW", "EDIT"]


def get_compatible_lenses_for_profile(
	profile_spec_name: str,
	lens_appearance_code: str | None = None,
	environment_rating_code: str | None = None,
	active_only: bool = True,
) -> list[dict]:
	"""
	Look up compatible lenses for a profile via ilL-Rel-Profile Lens.

	This is the single source of truth for profile↔lens compatibility.
	Used by the configurator engine, BOM generation, and any other code
	that needs to know which lenses fit a given profile.

	Args:
		profile_spec_name: The name (primary key) of the ilL-Spec-Profile record.
		lens_appearance_code: Optional filter – only return lenses with this appearance.
		environment_rating_code: Optional filter – only return lenses whose
			ilL-Child-Lens Environments child table includes this rating.
		active_only: If True (default), only consider active ilL-Rel-Profile Lens records.

	Returns:
		list[dict]: Each dict has keys:
			- lens_spec (str): Name of the ilL-Spec-Lens record
			- lens_item (str): The linked ERPNext Item code
			- lens_appearance (str): Lens appearance attribute
			- is_default (bool): Whether this row is flagged as the preferred lens
	"""
	import frappe

	filters: dict = {"profile_spec": profile_spec_name}
	if active_only:
		filters["is_active"] = 1

	rel_docs = frappe.get_all(
		"ilL-Rel-Profile Lens",
		filters=filters,
		fields=["name"],
		limit=1,
	)

	if not rel_docs:
		return []

	# Fetch child rows
	child_filters: dict = {
		"parent": rel_docs[0].name,
		"parenttype": "ilL-Rel-Profile Lens",
	}

	child_rows = frappe.get_all(
		"ilL-Child-Compatible Lens",
		filters=child_filters,
		fields=["lens_spec", "lens_item", "lens_appearance", "is_default"],
		order_by="is_default DESC, idx ASC",
	)

	if not child_rows:
		return []

	# Filter by lens appearance if provided
	if lens_appearance_code:
		child_rows = [r for r in child_rows if r.lens_appearance == lens_appearance_code]

	# Filter by environment rating if provided
	if environment_rating_code and child_rows:
		lens_names = [r.lens_spec for r in child_rows]
		lens_envs = frappe.get_all(
			"ilL-Child-Lens Environments",
			filters={"parent": ["in", lens_names], "parenttype": "ilL-Spec-Lens"},
			fields=["parent", "environment_rating"],
		)
		# Build lookup: {lens_name: set(ratings)}
		lens_env_map: dict[str, set] = {}
		for env in lens_envs:
			lens_env_map.setdefault(env.parent, set()).add(env.environment_rating)

		filtered = []
		for row in child_rows:
			supported = lens_env_map.get(row.lens_spec, set())
			# If no environment ratings listed, assume universally compatible
			if not supported or environment_rating_code in supported:
				filtered.append(row)
		child_rows = filtered

	return child_rows
