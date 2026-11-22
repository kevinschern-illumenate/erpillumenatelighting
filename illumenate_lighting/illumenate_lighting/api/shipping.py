# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Outbound shipping on the native Shipment: defaults, EasyPost labels through n8n, tracking.

* ``make_shipment``: Create Shipment on a Delivery Note returns an unsaved Shipment with
  the warehouse, address, contact, value, pickup and parcel defaults filled in.
* Shipment hooks: split rows with Count above 1 into one row per box, flag surcharges,
  refuse submit without usable parcels, refuse cancel while labels are bought.
* ``quote_labels`` / ``buy_labels`` / ``void_labels``: the Create Labels and Void Label
  buttons. ERPNext posts a signed request to the n8n label webhook, n8n calls EasyPost
  and answers in the same request, and ERPNext writes the numbers, labels and cost back
  and mirrors the master number to the Delivery Notes.
* ``receive_tracking_event``: n8n forwards EasyPost tracker events here, signed.

The contract and setup are in docs/SHIPPING_EASYPOST_INTEGRATION.md.
"""

import hashlib
import hmac
import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, get_url_to_form, nowdate

from illumenate_lighting.illumenate_lighting.api import shipping_rules as rules

SETTINGS = "ilL-Shipping-Settings"
SIGNATURE_HEADER = "X-ilL-Signature"
SECRET_CONF = "shipping_webhook_secret"
# n8n answers in the same request; EasyPost multi-box orders take a few seconds.
LABEL_TIMEOUT = 60
MAX_BODY_BYTES = 64 * 1024
MAX_LABEL_BYTES = 5 * 1024 * 1024
DN_CARRIERS = ("UPS", "FedEx", "USPS")
DEFAULT_DESCRIPTION = "LED lighting fixtures and components"
SERVICE_PROVIDER = "EasyPost"


class ShippingError(Exception):
	"""Business-rule failure on a tracker event; ``code`` goes back to n8n."""

	def __init__(self, code, message):
		super().__init__(message)
		self.code = code
		self.message = message


def get_settings():
	try:
		return frappe.get_cached_doc(SETTINGS)
	except Exception:
		return frappe._dict()


# ---------------------------------------------------------------------------
# Phase 1: Create Shipment from a Delivery Note
# ---------------------------------------------------------------------------


@frappe.whitelist()
def make_shipment(delivery_note):
	"""``{"existing": name}`` when a Shipment already lists the note, else ``{"doc": unsaved Shipment}``."""
	dn = frappe.get_doc("Delivery Note", delivery_note)
	dn.check_permission("read")
	frappe.has_permission("Shipment", "create", throw=True)
	if dn.docstatus == 2:
		frappe.throw(_("Delivery Note {0} is cancelled.").format(dn.name))
	existing = shipments_for_delivery_note(dn.name)
	if existing:
		return {"existing": existing[0]}
	return {"doc": build_shipment(dn, get_settings()).as_dict()}


def shipments_for_delivery_note(delivery_note):
	"""Draft and submitted Shipments that list the Delivery Note, oldest first."""
	parents = frappe.get_all(
		"Shipment Delivery Note",
		filters={"delivery_note": delivery_note, "parenttype": "Shipment"},
		pluck="parent",
	)
	if not parents:
		return []
	return frappe.get_all(
		"Shipment",
		filters={"name": ["in", list(set(parents))], "docstatus": ["<", 2]},
		pluck="name",
		order_by="creation asc",
	)


def build_shipment(dn, settings):
	doc = frappe.new_doc("Shipment")
	doc.pickup_from_type = "Company"
	doc.pickup_company = dn.company
	doc.pickup_address_name = settings.get("pickup_address") or dn.get("company_address")
	doc.pickup_address = _address_display(doc.pickup_address_name)
	user = (
		frappe.db.get_value(
			"User", frappe.session.user, ["email", "full_name", "phone", "mobile_no"], as_dict=True
		)
		or frappe._dict()
	)
	doc.pickup_contact_person = frappe.session.user
	doc.pickup_contact_email = user.email
	doc.pickup_contact = "<br>".join(filter(None, [user.full_name, user.email, user.phone or user.mobile_no]))

	doc.delivery_to_type = "Customer"
	doc.delivery_customer = dn.customer
	doc.delivery_address_name = dn.get("shipping_address_name") or dn.get("customer_address")
	doc.delivery_address = (
		dn.get("shipping_address") or dn.get("address_display") or _address_display(doc.delivery_address_name)
	)
	contact_name = dn.get("contact_person") or _default_contact(dn.customer)
	if contact_name:
		contact = (
			frappe.db.get_value(
				"Contact", contact_name, ["full_name", "email_id", "phone", "mobile_no"], as_dict=True
			)
			or frappe._dict()
		)
		doc.delivery_contact_name = contact_name
		doc.delivery_contact_email = dn.get("contact_email") or contact.email_id
		doc.delivery_contact = "<br>".join(
			filter(None, [contact.full_name, doc.delivery_contact_email, contact.phone or contact.mobile_no])
		)

	doc.append("shipment_delivery_note", {"delivery_note": dn.name, "grand_total": flt(dn.grand_total)})
	doc.value_of_goods = flt(dn.grand_total)
	doc.pickup_date = nowdate()
	doc.pickup_from = settings.get("pickup_from") or "09:00:00"
	doc.pickup_to = settings.get("pickup_to") or "17:00:00"
	doc.description_of_content = settings.get("description_of_content") or DEFAULT_DESCRIPTION
	doc.shipment_type = "Goods"
	doc.pickup_type = "Pickup"

	pounds, _unknown = rules.suggested_weight(dn.get("items") or [])
	if pounds > 0:
		box = {"weight": pounds, "count": 1}
		template = settings.get("default_parcel_template")
		if template:
			dims = frappe.db.get_value(
				"Shipment Parcel Template", template, ["length", "width", "height"], as_dict=True
			)
			if dims:
				box.update(length=dims.length, width=dims.width, height=dims.height)
		doc.append("shipment_parcel", box)
	return doc


def _address_display(address_name):
	if not address_name:
		return None
	from frappe.contacts.doctype.address.address import get_address_display

	return get_address_display(address_name)


def _default_contact(customer):
	if not customer:
		return None
	from frappe.contacts.doctype.contact.contact import get_default_contact

	return get_default_contact("Customer", customer)


# ---------------------------------------------------------------------------
# Shipment hooks
# ---------------------------------------------------------------------------


def shipment_validate(doc, method=None):
	"""One row per box, and the Special Handling flag kept current while the Shipment is open."""
	boxes = rules.expand_counts([row.as_dict() for row in doc.get("shipment_parcel") or []])
	if boxes is not None:
		doc.set("shipment_parcel", [])
		for box in boxes:
			row = doc.append("shipment_parcel", box)
			row.docstatus = doc.docstatus
	limits = rules.thresholds(get_settings())
	found = rules.check_parcels([row.as_dict() for row in doc.get("shipment_parcel") or []], limits)
	for row, special in zip(doc.get("shipment_parcel") or [], found["special"], strict=False):
		row.ill_special_handling = 1 if special else 0
	if doc.is_new() and not doc.get("ill_label_status"):
		doc.ill_label_status = "Not bought"


def shipment_before_submit(doc, method=None):
	found = rules.check_parcels(
		[row.as_dict() for row in doc.get("shipment_parcel") or []], rules.thresholds(get_settings())
	)
	if found["errors"]:
		frappe.throw("<br>".join(found["errors"]), title=_("Check the parcels"))
	if found["flags"]:
		frappe.msgprint(
			"<br>".join(found["flags"]), title=_("Surcharges likely"), indicator="orange", alert=True
		)


def shipment_before_cancel(doc, method=None):
	if doc.get("ill_label_status") == "Bought":
		frappe.throw(_("Void the label before cancelling this Shipment."))


# ---------------------------------------------------------------------------
# Phase 2: labels through n8n and EasyPost
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def quote_labels(shipment):
	"""Create Labels, step 1: rate the boxes (nothing is bought) and return what to confirm."""
	doc, settings = _label_doc(shipment)
	if doc.get("ill_label_status") == "Bought":
		frappe.throw(_("Labels are already bought for {0}. Void them first.").format(doc.name))
	limits = rules.thresholds(settings)
	found = rules.check_parcels([row.as_dict() for row in doc.shipment_parcel], limits)
	if found["errors"]:
		frappe.throw("<br>".join(found["errors"]), title=_("Check the parcels"))

	result = _call_label_service(label_payload(doc, settings, "rate"), settings)
	if not result.get("ok"):
		return _label_failed(doc, result)
	easypost_id = str(result.get("easypost_id") or "").strip()
	rate = result.get("rate") or {}
	if not easypost_id or not rate.get("service"):
		return _label_failed(
			doc, {"error": "easypost_error", "message": _("The label service returned no rate.")}
		)
	frappe.db.set_value(
		"Shipment",
		doc.name,
		{"ill_easypost_shipment_id": easypost_id, "ill_label_message": None},
		update_modified=False,
	)
	return {
		"ok": True,
		"easypost_id": easypost_id,
		"rate": rate,
		"address": result.get("address") or {},
		"messages": result.get("messages") or [],
		"flags": found["flags"],
		"boxes": len(doc.shipment_parcel),
	}


@frappe.whitelist(methods=["POST"])
def buy_labels(shipment, easypost_id, service=None):
	"""Create Labels, step 2: buy the rate the user confirmed."""
	# Row lock: a second click waits here, then sees Bought and stops.
	frappe.db.get_value("Shipment", shipment, "name", for_update=True)
	doc, settings = _label_doc(shipment)
	if doc.get("ill_label_status") == "Bought":
		frappe.throw(_("Labels are already bought for {0}.").format(doc.name))
	if not easypost_id or easypost_id != doc.get("ill_easypost_shipment_id"):
		frappe.throw(_("This rate is out of date. Click Create Labels again."))

	payload = label_payload(doc, settings, "buy")
	payload["easypost_id"] = easypost_id
	payload["service_selected"] = service or None
	result = _call_label_service(payload, settings)
	if not result.get("ok"):
		return _label_failed(doc, result)
	if not str(result.get("master_tracking") or "").strip():
		return _label_failed(
			doc, {"error": "easypost_error", "message": _("The label service returned no tracking number.")}
		)
	write_labels(doc, result)
	return {
		"ok": True,
		"tracking_number": doc.awb_number,
		"label_url": doc.get("ill_label_url"),
		"amount": doc.shipment_amount,
	}


@frappe.whitelist(methods=["POST"])
def void_labels(shipment):
	"""Void Label: refund every box at EasyPost and clear the numbers here."""
	frappe.db.get_value("Shipment", shipment, "name", for_update=True)
	doc, settings = _label_doc(shipment)
	if doc.get("ill_label_status") != "Bought":
		frappe.throw(_("{0} has no bought labels to void.").format(doc.name))
	result = _call_label_service(
		{"action": "void", "shipment": doc.name, "easypost_id": doc.get("ill_easypost_shipment_id")}, settings
	)
	if not result.get("ok") and result.get("error") != "already_refunded":
		message = result.get("message") or _("The label service could not void this label.")
		frappe.db.set_value("Shipment", doc.name, "ill_label_message", message, update_modified=False)
		return {"ok": False, "message": message}
	clear_labels(doc)
	return {"ok": True}


def _label_doc(shipment):
	settings = get_settings()
	doc = frappe.get_doc("Shipment", shipment)
	frappe.has_permission("Shipment", "submit", doc=doc, throw=True)
	if not cint(settings.get("enabled")):
		frappe.throw(_("Label buying is switched off in ilL-Shipping-Settings."))
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Shipment before buying labels."))
	return doc, settings


def label_payload(doc, settings, action):
	return {
		"action": action,
		"shipment": doc.name,
		"reference": doc.name,
		"easypost_id": doc.get("ill_easypost_shipment_id") or None,
		"carrier": settings.get("carrier") or "FedEx",
		"service": settings.get("service") or "FEDEX_GROUND",
		"residential_service": settings.get("residential_service") or "GROUND_HOME_DELIVERY",
		"carrier_account_id": settings.get("carrier_account_id") or None,
		"from_address": easypost_address(
			doc.pickup_address_name,
			company=doc.get("pickup_company"),
			person=frappe.db.get_value("User", doc.get("pickup_contact_person"), "full_name")
			if doc.get("pickup_contact_person")
			else None,
			email=doc.get("pickup_contact_email"),
		),
		"to_address": easypost_address(
			doc.delivery_address_name,
			company=frappe.db.get_value("Customer", doc.delivery_customer, "customer_name")
			if doc.get("delivery_customer")
			else None,
			contact=doc.get("delivery_contact_name"),
			email=doc.get("delivery_contact_email"),
		),
		"parcels": [
			{
				"row": row.name,
				"length_in": flt(row.length),
				"width_in": flt(row.width),
				"height_in": flt(row.height),
				"weight_lb": flt(row.weight),
				"additional_handling": bool(cint(row.get("ill_special_handling"))),
			}
			for row in doc.shipment_parcel
		],
		"delivery_notes": [row.delivery_note for row in doc.get("shipment_delivery_note") or []],
	}


def easypost_address(address_name, company=None, person=None, contact=None, email=None):
	address = frappe.get_doc("Address", address_name) if address_name else frappe._dict()
	phone = address.get("phone")
	if contact:
		details = (
			frappe.db.get_value(
				"Contact", contact, ["full_name", "email_id", "phone", "mobile_no"], as_dict=True
			)
			or frappe._dict()
		)
		person = person or details.full_name
		email = email or details.email_id
		phone = details.phone or details.mobile_no or phone
	country = address.get("country")
	code = frappe.db.get_value("Country", country, "code") if country else None
	return {
		"name": person or company or address.get("address_title"),
		"company": company or address.get("address_title"),
		"street1": address.get("address_line1"),
		"street2": address.get("address_line2") or "",
		"city": address.get("city"),
		"state": address.get("state") or "",
		"zip": address.get("pincode"),
		"country": (code or "US").upper(),
		"phone": phone or "",
		"email": email or address.get("email_id") or "",
	}


def _label_failed(doc, result):
	message = result.get("message") or _("The label service failed ({0}).").format(
		result.get("error") or "unknown"
	)
	extra = [m for m in result.get("messages") or [] if isinstance(m, str)]
	if extra:
		message = message + "\n" + "\n".join(extra)
	frappe.db.set_value(
		"Shipment",
		doc.name,
		{"ill_label_status": "Error", "ill_label_message": message[:1000]},
		update_modified=False,
	)
	return {"ok": False, "error": result.get("error"), "message": message}


def write_labels(doc, result):
	"""Write a bought EasyPost order back to the Shipment, its boxes and its Delivery Notes."""
	from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import tracking_url

	master = str(result["master_tracking"]).strip()
	carrier = result.get("carrier") or "FedEx"
	by_row = {str(p.get("row")): p for p in result.get("parcels") or [] if p.get("row")}
	label_urls = []
	for row in doc.shipment_parcel:
		box = by_row.get(row.name) or {}
		number = str(box.get("tracking_number") or "").strip() or None
		url = box.get("label_url") or None
		if url:
			label_urls.append(url)
		frappe.db.set_value(
			"Shipment Parcel",
			row.name,
			{"ill_tracking_number": number, "ill_label_url": url, "ill_tracking_status": None},
			update_modified=False,
		)
	label_file = attach_labels(doc.name, label_urls)
	values = {
		"awb_number": master,
		"carrier": carrier,
		"carrier_service": result.get("service"),
		"service_provider": SERVICE_PROVIDER,
		"shipment_id": result.get("easypost_id"),
		"shipment_amount": flt(result.get("amount")),
		"tracking_url": result.get("tracking_url") or tracking_url(carrier, master),
		"tracking_status": "In Progress",
		"status": "Booked",
		"ill_label_status": "Bought",
		"ill_label_message": None,
		"ill_label_url": label_file or (label_urls[0] if label_urls else None),
		"ill_easypost_shipment_id": result.get("easypost_id") or doc.get("ill_easypost_shipment_id"),
	}
	frappe.db.set_value("Shipment", doc.name, values)
	doc.update(values)
	mirror_to_delivery_notes(doc, carrier, master)
	doc.add_comment(
		"Info",
		_("Labels bought: {0} {1}, {2} box(es), {3}. Master tracking {4}.").format(
			carrier,
			result.get("service") or "",
			len(doc.shipment_parcel),
			frappe.format_value(flt(result.get("amount")), {"fieldtype": "Currency"}),
			master,
		),
	)


def attach_labels(shipment, urls):
	"""One private PDF with every box's label, attached to the Shipment. None when that fails."""
	urls = [u for u in urls if isinstance(u, str) and u.startswith("https://")]
	if not urls:
		return None
	try:
		import io

		import requests
		from pypdf import PdfReader, PdfWriter

		writer = PdfWriter()
		for url in urls:
			response = requests.get(url, timeout=20)
			response.raise_for_status()
			content = response.content
			if len(content) > MAX_LABEL_BYTES or not content.startswith(b"%PDF"):
				return None
			for page in PdfReader(io.BytesIO(content)).pages:
				writer.add_page(page)
		out = io.BytesIO()
		writer.write(out)
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{shipment}-labels.pdf",
				"attached_to_doctype": "Shipment",
				"attached_to_name": shipment,
				"content": out.getvalue(),
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		return file_doc.file_url
	except Exception:
		frappe.log_error(
			title=f"Shipping: label PDF merge failed ({shipment})", message=frappe.get_traceback()
		)
		return None


def mirror_to_delivery_notes(doc, carrier, number):
	"""Carrier and master number onto each linked Delivery Note (allow-on-submit fields)."""
	carrier = carrier if carrier in DN_CARRIERS else "Other"
	for row in doc.get("shipment_delivery_note") or []:
		if row.delivery_note and frappe.db.get_value("Delivery Note", row.delivery_note, "docstatus") != 2:
			frappe.db.set_value(
				"Delivery Note", row.delivery_note, {"ill_carrier": carrier, "ill_tracking_number": number}
			)


def clear_labels(doc):
	"""After a refund: numbers off the Shipment, its boxes and the Delivery Notes still showing them."""
	old = [doc.awb_number] + [row.get("ill_tracking_number") for row in doc.shipment_parcel]
	old = list(dict.fromkeys(n for n in old if n))
	for row in doc.shipment_parcel:
		frappe.db.set_value(
			"Shipment Parcel",
			row.name,
			{"ill_tracking_number": None, "ill_label_url": None, "ill_tracking_status": None},
			update_modified=False,
		)
	frappe.db.set_value(
		"Shipment",
		doc.name,
		{
			"awb_number": None,
			"tracking_url": None,
			"tracking_status": None,
			"tracking_status_info": None,
			"shipment_amount": 0,
			"status": "Submitted",
			"ill_label_status": "Voided",
			"ill_label_message": None,
			"ill_label_url": None,
		},
	)
	for row in doc.get("shipment_delivery_note") or []:
		if not row.delivery_note:
			continue
		current = frappe.db.get_value("Delivery Note", row.delivery_note, "ill_tracking_number")
		if current and current in old:
			frappe.db.set_value("Delivery Note", row.delivery_note, "ill_tracking_number", None)
	doc.add_comment("Info", _("Labels voided. Refund requested for {0}.").format(", ".join(old) or "-"))


def _call_label_service(payload, settings):
	"""POST a signed request to the n8n label webhook. Always returns a dict with ``ok``."""
	url = (settings.get("label_webhook_url") or "").strip()
	if not url:
		return {
			"ok": False,
			"error": "bad_request",
			"message": _("Set the Label Webhook URL in ilL-Shipping-Settings."),
		}
	secret = get_secret(settings)
	if not secret:
		return {
			"ok": False,
			"error": "bad_request",
			"message": _("Set the Webhook Shared Secret in ilL-Shipping-Settings."),
		}
	body = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
	headers = {"Content-Type": "application/json", SIGNATURE_HEADER: sign(secret, body)}

	import requests

	try:
		response = requests.post(url, data=body, headers=headers, timeout=LABEL_TIMEOUT)
	except requests.Timeout:
		return {
			"ok": False,
			"error": "easypost_error",
			"message": _(
				"No answer from the label service in {0} seconds. Check EasyPost before trying again."
			).format(LABEL_TIMEOUT),
		}
	except Exception:
		frappe.log_error(title=f"Shipping: label service unreachable ({payload.get('shipment')})")
		return {
			"ok": False,
			"error": "easypost_error",
			"message": _("The label service could not be reached."),
		}
	try:
		result = response.json()
	except ValueError:
		result = None
	if response.status_code != 200 or not isinstance(result, dict):
		frappe.log_error(
			title=f"Shipping: label service error ({payload.get('shipment')})",
			message=f"HTTP {response.status_code}: {response.text[:2000]}",
		)
		return {
			"ok": False,
			"error": "easypost_error",
			"message": _("The label service returned HTTP {0}.").format(response.status_code),
		}
	return result


def get_secret(settings=None):
	secret = frappe.conf.get(SECRET_CONF)
	if secret and str(secret).strip():
		return str(secret)
	settings = settings if settings is not None else get_settings()
	try:
		return settings.get_password("webhook_secret", raise_exception=False)
	except Exception:
		return None


def sign(secret, body):
	return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify(secret, body, provided):
	provided = (provided or "").strip().lower()
	if provided.startswith("sha256="):
		provided = provided[7:]
	# A blank secret would let anyone sign, so it never verifies.
	if not secret or not str(secret).strip() or not provided:
		return False
	return hmac.compare_digest(sign(secret, body), provided)


# ---------------------------------------------------------------------------
# Phase 3: tracker events from n8n
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def receive_tracking_event():
	"""Signed EasyPost tracker event, forwarded by n8n (contract section 5)."""
	declared = getattr(frappe.request, "content_length", None)
	if isinstance(declared, int) and declared > MAX_BODY_BYTES:
		return _refuse(413, "payload_too_large")
	raw_body = frappe.request.get_data() or b""
	if len(raw_body) > MAX_BODY_BYTES:
		return _refuse(413, "payload_too_large")
	if not verify(get_secret(), raw_body, frappe.get_request_header(SIGNATURE_HEADER)):
		frappe.log_error(
			title="Shipping webhook: signature verification failed",
			message=f"ip={getattr(frappe.local, 'request_ip', None)} bytes={len(raw_body)}",
		)
		return _refuse(401, "unauthorized")
	try:
		payload = json.loads(raw_body.decode("utf-8") or "{}")
		if not isinstance(payload, dict):
			raise ValueError("payload must be a JSON object")
	except (ValueError, UnicodeDecodeError) as e:
		return _refuse(400, "invalid_json", message=str(e))

	from illumenate_lighting.illumenate_lighting.portal.service_users import service_user

	user = service_user("shipping")
	if not frappe.db.get_value("User", user, "enabled"):
		frappe.log_error(
			title="Shipping webhook: integration user unavailable", message=f"{user} is missing or disabled."
		)
		return _refuse(503, "integration_user_unavailable")
	frappe.set_user(user)
	try:
		result = apply_tracking_event(payload)
	except ShippingError as e:
		return _refuse(404 if e.code == "not_found" else 400, e.code, message=e.message)
	result["success"] = True
	return result


def _refuse(status, error, **extra):
	frappe.local.response["http_status_code"] = status
	return {"success": False, "error": error, **extra}


def find_tracking_number(code):
	"""``(shipment, parcel_row or None)`` for a tracking number on a bought, submitted Shipment."""
	rows = frappe.get_all(
		"Shipment Parcel",
		filters={"ill_tracking_number": code, "parenttype": "Shipment"},
		fields=["name", "parent"],
	)
	for row in rows:
		if _live(row.parent):
			return row.parent, row.name
	for name in frappe.get_all("Shipment", filters={"awb_number": code, "docstatus": 1}, pluck="name"):
		if _live(name):
			return name, None
	return None, None


def _live(shipment):
	values = frappe.db.get_value("Shipment", shipment, ["docstatus", "ill_label_status"], as_dict=True)
	return bool(values) and values.docstatus == 1 and values.ill_label_status != "Voided"


def apply_tracking_event(payload):
	code = str(payload.get("tracking_code") or "").strip()
	if not code:
		raise ShippingError("missing_fields", "tracking_code is required")
	shipment, parcel = find_tracking_number(code)
	if not shipment:
		raise ShippingError("not_found", f"No open Shipment has tracking number {code}")

	easypost_status = str(payload.get("status") or "").strip().lower()
	box = rules.box_status(easypost_status)
	doc = frappe.get_doc("Shipment", shipment)
	previous_box = None
	if parcel:
		previous_box = next(
			(r.get("ill_tracking_status") for r in doc.shipment_parcel if r.name == parcel), None
		)
		frappe.db.set_value("Shipment Parcel", parcel, "ill_tracking_status", box, update_modified=False)
	numbered = [row for row in doc.shipment_parcel if row.get("ill_tracking_number")]
	statuses = (
		[box if row.name == parcel else row.get("ill_tracking_status") for row in numbered]
		if numbered
		else [box]
	)

	before = doc.get("tracking_status")
	after = rules.shipment_status(statuses, before)
	info = " · ".join(filter(None, [box, str(payload.get("message") or "").strip()]))[:140]
	values = {"tracking_status": after, "tracking_status_info": info}
	if payload.get("public_url") and not doc.get("tracking_url"):
		values["tracking_url"] = payload["public_url"]
	if after == "Delivered" and doc.status != "Completed":
		values["status"] = "Completed"
	frappe.db.set_value("Shipment", shipment, values)

	if easypost_status in rules.EXCEPTIONS and previous_box != box:
		alert_exception(doc, code, box, payload)
	if after == "Delivered" and before != "Delivered":
		notify_delivered(doc)
	return {"shipment": shipment, "tracking_status": after, "box_status": box}


def alert_exception(doc, code, box, payload):
	recipient = (get_settings().get("exception_email") or "").strip()
	if not recipient:
		return
	escape = frappe.utils.escape_html
	notes = ", ".join(r.delivery_note for r in doc.get("shipment_delivery_note") or [] if r.delivery_note)
	frappe.sendmail(
		recipients=[recipient],
		subject=_("Shipping exception: {0} ({1})").format(doc.name, box),
		message=(
			f"<p>{escape(_('Tracking number'))} <strong>{escape(code)}</strong>: {escape(box)}</p>"
			f"<p>{escape(str(payload.get('message') or ''))}</p>"
			f"<p>{escape(_('Delivery Note'))}: {escape(notes or '-')}<br>"
			f'<a href="{escape(get_url_to_form("Shipment", doc.name))}">{escape(doc.name)}</a></p>'
		),
		reference_doctype="Shipment",
		reference_name=doc.name,
	)


def notify_delivered(doc):
	if not cint(get_settings().get("send_delivered_email")):
		return
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_delivered as send

	for row in doc.get("shipment_delivery_note") or []:
		if row.delivery_note:
			try:
				send(frappe.get_doc("Delivery Note", row.delivery_note), doc.name)
			except Exception:
				frappe.log_error(title=f"Shipping: delivered email failed ({doc.name})")
