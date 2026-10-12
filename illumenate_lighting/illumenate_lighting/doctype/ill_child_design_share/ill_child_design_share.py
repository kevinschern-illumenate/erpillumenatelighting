# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildDesignShare(Document):
	"""A read-only share link; only the SHA-256 of its secret is stored (D10)."""
