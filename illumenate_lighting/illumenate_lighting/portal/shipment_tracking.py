# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Carrier, tracking numbers and tracking links for a Delivery Note (DESK-8, shipping plan phase 3).

Every box on the submitted Shipments that list the note comes first: the master number
(``awb_number``) and then each box's ``ill_tracking_number``. Voided labels are left out.
Notes without such a Shipment fall back to ``ill_carrier`` / ``ill_tracking_number``,
then to ``transporter_name`` and ``vehicle_no`` / ``lr_no`` for notes recorded before
those fields existed. Only the parcel carriers get a link; Freight and Other show the
number alone.

``tracking()`` keeps its old keys (the first package) and adds ``packages``, the full list.
"""

from urllib.parse import quote

CARRIERS = ("UPS", "FedEx", "USPS", "Freight", "Other")
TRACKING_URLS = {
	"UPS": "https://www.ups.com/track?tracknum={0}",
	"FedEx": "https://www.fedex.com/fedextrack/?trknbr={0}",
	"USPS": "https://tools.usps.com/go/TrackConfirmAction?tLabels={0}",
}
# Carrier names as EasyPost and staff spell them -> the key above.
_ALIASES = {"ups": "UPS", "fedex": "FedEx", "usps": "USPS"}


def tracking_url(carrier, number):
	template = TRACKING_URLS.get(_ALIASES.get(str(carrier or "").strip().lower()))
	number = str(number).strip() if number else None
	return template.format(quote(number, safe="")) if template and number else None


def _package(carrier, number):
	number = str(number).strip() if number else None
	return {"carrier": carrier or None, "number": number, "url": tracking_url(carrier, number)}


def tracking(delivery_note, shipment_packages=None):
	"""{"carrier", "number", "url", "packages"} for a Delivery Note document or dict.

	``shipment_packages`` is this note's entry from ``packages_by_delivery_note``; pass it
	when tracking many notes at once. Otherwise the Shipments are looked up by name.
	"""
	if shipment_packages is None:
		name = delivery_note.get("name")
		shipment_packages = packages_by_delivery_note([name]).get(name, []) if name else []
	packages = list(shipment_packages)
	if not packages:
		legacy = _legacy(delivery_note)
		packages = [legacy] if legacy["carrier"] or legacy["number"] else []
	first = packages[0] if packages else {"carrier": None, "number": None, "url": None}
	return {**first, "packages": packages}


def _legacy(delivery_note):
	carrier = delivery_note.get("ill_carrier") or delivery_note.get("transporter_name") or None
	number = (
		delivery_note.get("ill_tracking_number")
		or delivery_note.get("vehicle_no")
		or delivery_note.get("lr_no")
		or None
	)
	number = str(number).strip() if number else None
	# Only the curated carrier field gets a link; free-text transporter names never do.
	url = tracking_url(delivery_note.get("ill_carrier"), number) if delivery_note.get("ill_carrier") else None
	return {"carrier": carrier, "number": number, "url": url}


def packages_by_delivery_note(names):
	"""{delivery_note: [package, ...]} from submitted Shipments with labels that are not voided."""
	import frappe

	names = [n for n in dict.fromkeys(names or []) if n]
	if not names:
		return {}
	links = frappe.get_all(
		"Shipment Delivery Note",
		filters={"delivery_note": ["in", names], "parenttype": "Shipment"},
		fields=["parent", "delivery_note"],
	)
	if not links:
		return {}
	shipments = {
		row.name: row
		for row in frappe.get_all(
			"Shipment",
			filters={
				"name": ["in", list({link.parent for link in links})],
				"docstatus": 1,
				"awb_number": ["is", "set"],
			},
			fields=["name", "carrier", "awb_number", "ill_label_status", "creation"],
			order_by="creation asc",
		)
		if row.get("ill_label_status") != "Voided"
	}
	if not shipments:
		return {}
	boxes = {}
	for row in frappe.get_all(
		"Shipment Parcel",
		filters={"parent": ["in", list(shipments)], "parenttype": "Shipment"},
		fields=["parent", "ill_tracking_number", "idx"],
		order_by="idx asc",
	):
		boxes.setdefault(row.parent, []).append(row.get("ill_tracking_number"))

	per_shipment = {}
	for name, shipment in shipments.items():
		numbers = [shipment.awb_number, *boxes.get(name, [])]
		numbers = [str(n).strip() for n in numbers if n and str(n).strip()]
		per_shipment[name] = [_package(shipment.carrier, n) for n in dict.fromkeys(numbers)]

	order = list(shipments)  # oldest Shipment first
	result = {}
	for link in sorted(
		links, key=lambda row: order.index(row.parent) if row.parent in shipments else len(order)
	):
		if link.parent in per_shipment:
			result.setdefault(link.delivery_note, []).extend(per_shipment[link.parent])
	return result
