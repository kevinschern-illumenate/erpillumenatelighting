# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Carrier, tracking number and tracking link for a Delivery Note (DESK-8).

``ill_carrier`` / ``ill_tracking_number`` come first; notes recorded before
those fields existed fall back to ``transporter_name`` and ``vehicle_no`` /
``lr_no``. Only the parcel carriers get a link; Freight and Other show the
number alone.
"""

from urllib.parse import quote

CARRIERS = ("UPS", "FedEx", "USPS", "Freight", "Other")
TRACKING_URLS = {
	"UPS": "https://www.ups.com/track?tracknum={0}",
	"FedEx": "https://www.fedex.com/fedextrack/?trknbr={0}",
	"USPS": "https://tools.usps.com/go/TrackConfirmAction?tLabels={0}",
}


def tracking(delivery_note):
	"""{"carrier", "number", "url"} for a Delivery Note document or dict."""
	carrier = delivery_note.get("ill_carrier") or delivery_note.get("transporter_name") or None
	number = (
		delivery_note.get("ill_tracking_number")
		or delivery_note.get("vehicle_no")
		or delivery_note.get("lr_no")
		or None
	)
	number = str(number).strip() if number else None
	template = TRACKING_URLS.get(delivery_note.get("ill_carrier"))
	url = template.format(quote(number, safe="")) if template and number else None
	return {"carrier": carrier, "number": number, "url": url}
