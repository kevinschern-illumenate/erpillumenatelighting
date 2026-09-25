"""Frozen approval PDF; subsequent ERP changes never regenerate the issued bytes."""

import hashlib
import html
import json

import frappe


def create(intake):
	from frappe.utils.pdf import get_pdf

	from illumenate_lighting.illumenate_lighting.api.exports import _save_file_ignore_permissions

	if intake.get("acknowledgment_file"):
		return
	data = json.loads(intake.approved_snapshot)

	def escape(value):
		return html.escape(str(value if value is not None else ""))

	rows = "".join(
		"<tr>"
		+ "".join(
			"<td>" + escape(row.get(key)) + "</td>"
			for key in ("item_code", "description", "qty", "uom", "rate", "amount")
		)
		+ "</tr>"
		for row in data["items"]
	)
	context = "".join(
		"<p><strong>" + escape(label) + ":</strong> " + escape(data.get(key)) + "</p>"
		for key, label in (
			("customer", "Customer"),
			("po_no", "Purchase order"),
			("ill_requested_delivery_date", "Requested delivery"),
			("ill_confirmed_delivery_date", "Confirmed delivery"),
			("address_display", "Billing address"),
			("shipping_address", "Shipping address"),
			("contact_display", "Purchasing contact"),
			("ill_receiving_instructions", "Receiving instructions"),
			("ill_shipping_instructions", "Shipping instructions"),
		)
	)
	content = get_pdf(
		"<html><head><style>body{font:10pt Arial;color:#222}table{width:100%;border-collapse:collapse}td,th{padding:6px;border-bottom:1px solid #ccc;vertical-align:top;overflow-wrap:break-word}thead{display:table-header-group}tr{page-break-inside:avoid}p{white-space:pre-wrap}</style></head><body><h1>Order acknowledgment</h1><p>"
		+ escape(intake.sales_order)
		+ " / "
		+ escape(intake.name)
		+ "</p><p>Approved "
		+ escape(intake.approved_on)
		+ " by "
		+ escape(intake.approved_by)
		+ "</p>"
		+ context
		+ "<table><thead><tr><th>Item</th><th>Description</th><th>Qty</th><th>UOM</th><th>Rate</th><th>Amount</th></tr></thead><tbody>"
		+ rows
		+ "</tbody></table><p><strong>Total: "
		+ escape(data.get("currency"))
		+ " "
		+ escape(data.get("grand_total"))
		+ "</strong></p><h2>Terms</h2>"
		+ frappe.utils.sanitize_html(data.get("terms") or "")
		+ "<p>OTHER manufacturer specifications remain outside the sellable order unless explicitly included by Sales. Drawing approval governs manufacturing release separately.</p></body></html>"
	)
	file = _save_file_ignore_permissions(
		"Acknowledgment_" + intake.sales_order + ".pdf", content, "ilL-Order-Intake", intake.name
	)
	intake.acknowledgment_file = file.name
	intake.acknowledgment_sha256 = hashlib.sha256(content).hexdigest()


@frappe.whitelist()
def download(order_name):
	from illumenate_lighting.illumenate_lighting.portal.order_intake import can_access

	intake = frappe.get_doc("ilL-Order-Intake", {"sales_order": order_name})
	if not can_access(intake):
		frappe.throw("Order acknowledgment unavailable", frappe.PermissionError)
	if not intake.acknowledgment_file or intake.state != "APPROVED":
		raise ValueError("This order has no issued acknowledgment")
	file = frappe.get_doc("File", intake.acknowledgment_file)
	if (
		not file.is_private
		or file.attached_to_doctype != intake.doctype
		or file.attached_to_name != intake.name
	):
		frappe.throw("Acknowledgment ownership mismatch", frappe.PermissionError)
	content = file.get_content()
	if hashlib.sha256(content).hexdigest() != intake.acknowledgment_sha256:
		raise ValueError("Issued acknowledgment bytes no longer match their checksum")
	frappe.local.response.update(type="download", filename=file.file_name, filecontent=content)
