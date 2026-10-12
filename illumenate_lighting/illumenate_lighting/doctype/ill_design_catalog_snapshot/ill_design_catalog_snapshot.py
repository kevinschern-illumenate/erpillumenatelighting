# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLDesignCatalogSnapshot(Document):
	"""Immutable: ``system_design.catalog.build_snapshot`` inserts one per catalog hash."""
