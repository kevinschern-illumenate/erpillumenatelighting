# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api import purchasing


class ilLInboundShipment(Document):
	"""Status-driven (not submittable): totals and cost defaults on validate, PO write-back on update."""

	def validate(self):
		purchasing.validate_shipment(self)

	def on_update(self):
		# Best-effort: a PO that can't be updated is logged, never blocks the shipment.
		purchasing.shipment_write_back(self)
