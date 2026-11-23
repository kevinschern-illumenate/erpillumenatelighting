# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api import reels


class ilLReel(Document):
	"""One physical reel. Lengths change only through ilL-Reel-Movement rows (api/reels.py)."""

	def validate(self):
		reels.validate_reel(self)
