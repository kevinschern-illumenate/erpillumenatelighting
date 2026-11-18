# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Pure validation rules for ilL-Webflow-Gallery (no Frappe needed)."""

from illumenate_lighting.illumenate_lighting.api.gallery_schema import SLUG_RE


def validate_gallery(doc: dict, *, slug_locked: bool, slug_taken: bool) -> list[str]:
	"""Return blocking error messages for a gallery; an empty list means valid.

	`doc["_old_slug"]` carries the saved slug so a locked slug can be detected as changed.
	"""
	errors = []
	slug = doc.get("slug")
	if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
		errors.append("Slug must use lowercase letters, numbers and single hyphens only.")
	else:
		if slug_taken:
			errors.append(f"Slug {slug} is already used by another gallery.")
		old_slug = doc.get("_old_slug")
		if slug_locked and old_slug and old_slug != slug:
			errors.append("Slug cannot change once the gallery has been staged in Webflow.")

	seen = set()
	for row in doc.get("credits") or []:
		credit_type = row.get("credit_type")
		if credit_type in seen:
			errors.append(f"Credit type {credit_type} appears more than once.")
		seen.add(credit_type)
	return errors
