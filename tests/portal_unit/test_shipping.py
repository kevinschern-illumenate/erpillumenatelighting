"""Shipping plan phases 1 to 3: EasyPost labels through n8n and signed tracker events (api/shipping.py)."""

import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

SECRET = "s3cret"


class Doc(Record):
	"""A Shipment stand-in with the Document methods the module calls."""

	def add_comment(self, kind, text):
		self.setdefault("comments", []).append(text)

	def update(self, values):
		dict.update(self, values)


def shipment(**values):
	base = {
		"name": "SHIP-1",
		"docstatus": 1,
		"ill_label_status": "Not bought",
		"ill_easypost_shipment_id": "order_1",
		"awb_number": None,
		"status": "Submitted",
		"tracking_status": None,
		"tracking_url": None,
		"shipment_parcel": [
			Record(name="row-1", ill_tracking_number=None, ill_tracking_status=None),
			Record(name="row-2", ill_tracking_number=None, ill_tracking_status=None),
		],
		"shipment_delivery_note": [Record(delivery_note="DN-1"), Record(delivery_note="DN-2")],
	}
	base.update(values)
	return Doc(base)


@contextmanager
def loaded(requests_module=None, enabled_user=True):
	users = types.ModuleType(ROOT + ".portal.service_users")
	users.service_user = lambda key: "shipping-integration@illumenate.lighting"
	extras = {ROOT + ".portal.service_users": users}
	if requests_module is not None:
		extras["requests"] = requests_module
	with load_service(ROOT + ".api.shipping", extras=extras) as (module, frappe):
		frappe._dict = Record
		frappe.log_error = MagicMock()
		frappe.get_traceback = lambda: "traceback"
		frappe.format_value = lambda value, df=None: f"${value:,.2f}"
		frappe.set_user = MagicMock()
		frappe.local.response = {}
		frappe.conf[module.SECRET_CONF] = SECRET
		frappe.get_cached_doc = MagicMock(return_value=Record(enabled=1))
		frappe.db.get_value.side_effect = lambda *a, **kw: 1 if a[0] == "User" and enabled_user else None
		yield module, frappe


def fake_requests(response=None, raises=None):
	module = types.ModuleType("requests")
	module.Timeout = type("Timeout", (Exception,), {})
	module.post = MagicMock()
	if raises == "timeout":
		module.post.side_effect = module.Timeout()
	elif raises:
		module.post.side_effect = raises
	else:
		module.post.return_value = response
	return module


def response(status=200, body=None, text=None):
	result = MagicMock()
	result.status_code = status
	result.text = text if text is not None else json.dumps(body)
	if body is None:
		result.json.side_effect = ValueError("no json")
	else:
		result.json.return_value = body
	return result


class Signing(unittest.TestCase):
	def test_verify_accepts_the_prefix_and_refuses_blank_or_wrong(self):
		with loaded() as (module, _frappe):
			body = b'{"a":1}'
			good = module.sign(SECRET, body)
			self.assertTrue(module.verify(SECRET, body, good))
			self.assertTrue(module.verify(SECRET, body, "sha256=" + good.upper()))
			self.assertFalse(module.verify(SECRET, body, "0" * 64))
			self.assertFalse(module.verify(" ", body, module.sign(" ", body)))
			self.assertFalse(module.verify(SECRET, body, ""))


class TrackerEndpoint(unittest.TestCase):
	def call(self, body, signature=None, enabled_user=True):
		with loaded(enabled_user=enabled_user) as (module, frappe):
			raw = json.dumps(body).encode()
			frappe.request = types.SimpleNamespace(content_length=len(raw), get_data=lambda: raw)
			frappe.get_request_header = lambda name: (
				signature if signature is not None else module.sign(SECRET, raw)
			)
			with patch.object(module, "apply_tracking_event", return_value={"shipment": "SHIP-1"}) as apply:
				result = module.receive_tracking_event()
			return result, frappe, apply

	def test_bad_signature_is_refused_before_anything_runs(self):
		result, frappe, apply = self.call({"tracking_code": "1"}, signature="bad")
		self.assertEqual(result["error"], "unauthorized")
		self.assertEqual(frappe.local.response["http_status_code"], 401)
		apply.assert_not_called()
		frappe.set_user.assert_not_called()

	def test_disabled_integration_user_asks_n8n_to_retry(self):
		_result, frappe, apply = self.call({"tracking_code": "1"}, enabled_user=False)
		self.assertEqual(frappe.local.response["http_status_code"], 503)
		apply.assert_not_called()

	def test_signed_event_runs_as_the_integration_user(self):
		result, frappe, apply = self.call({"tracking_code": "1"})
		self.assertEqual(result, {"shipment": "SHIP-1", "success": True})
		frappe.set_user.assert_called_once_with("shipping-integration@illumenate.lighting")
		apply.assert_called_once_with({"tracking_code": "1"})

	def test_unknown_number_is_a_404(self):
		with loaded() as (module, frappe):
			raw = b'{"tracking_code":"X"}'
			frappe.request = types.SimpleNamespace(content_length=len(raw), get_data=lambda: raw)
			frappe.get_request_header = lambda name: module.sign(SECRET, raw)
			with patch.object(module, "find_tracking_number", return_value=(None, None)):
				result = module.receive_tracking_event()
			self.assertEqual(result["error"], "not_found")
			self.assertEqual(frappe.local.response["http_status_code"], 404)


class TrackingEvents(unittest.TestCase):
	def apply(self, doc, payload, parcel="row-1"):
		with loaded() as (module, frappe):
			frappe.get_doc.return_value = doc
			with (
				patch.object(module, "find_tracking_number", return_value=("SHIP-1", parcel)),
				patch.object(module, "alert_exception") as alert,
				patch.object(module, "notify_delivered") as delivered,
			):
				result = module.apply_tracking_event(payload)
			shipment_writes = [
				c.args[2] for c in frappe.db.set_value.call_args_list if c.args[0] == "Shipment"
			]
			return result, shipment_writes, alert, delivered

	def two_boxes(self, first=None, second=None, tracking_status="In Progress"):
		return shipment(
			ill_label_status="Bought",
			tracking_status=tracking_status,
			shipment_parcel=[
				Record(name="row-1", ill_tracking_number="A", ill_tracking_status=first),
				Record(name="row-2", ill_tracking_number="B", ill_tracking_status=second),
			],
		)

	def test_first_box_delivered_leaves_the_shipment_in_progress(self):
		result, writes, alert, delivered = self.apply(
			self.two_boxes(second="In Transit"),
			{"tracking_code": "A", "status": "delivered", "message": "Front door"},
		)
		self.assertEqual(result["tracking_status"], "In Progress")
		self.assertNotIn("status", writes[0])
		self.assertEqual(writes[0]["tracking_status_info"], "Delivered · Front door")
		delivered.assert_not_called()
		alert.assert_not_called()

	def test_last_box_delivered_completes_and_emails_once(self):
		result, writes, _alert, delivered = self.apply(
			self.two_boxes(second="Delivered"), {"tracking_code": "A", "status": "delivered"}
		)
		self.assertEqual(result["tracking_status"], "Delivered")
		self.assertEqual(writes[0]["status"], "Completed")
		delivered.assert_called_once()
		# A repeated event for an already delivered Shipment sends nothing new.
		_r, _w, _a, again = self.apply(
			self.two_boxes(first="Delivered", second="Delivered", tracking_status="Delivered"),
			{"tracking_code": "A", "status": "delivered"},
		)
		again.assert_not_called()

	def test_return_alerts_the_shipping_lead_once(self):
		result, _writes, alert, _d = self.apply(
			self.two_boxes(), {"tracking_code": "A", "status": "return_to_sender"}
		)
		self.assertEqual(result["tracking_status"], "Returned")
		alert.assert_called_once()
		_r, _w, alert_again, _d = self.apply(
			self.two_boxes(first="Returned"), {"tracking_code": "A", "status": "return_to_sender"}
		)
		alert_again.assert_not_called()

	def test_missing_code_and_unknown_number_raise(self):
		with loaded() as (module, _frappe):
			with self.assertRaises(module.ShippingError) as missing:
				module.apply_tracking_event({})
			self.assertEqual(missing.exception.code, "missing_fields")
			with patch.object(module, "find_tracking_number", return_value=(None, None)):
				with self.assertRaises(module.ShippingError) as unknown:
					module.apply_tracking_event({"tracking_code": "Z"})
			self.assertEqual(unknown.exception.code, "not_found")


class LabelService(unittest.TestCase):
	def call(self, requests_module, settings=None):
		settings = Record(label_webhook_url="https://n8n.test/hook", **(settings or {}))
		with loaded(requests_module=requests_module) as (module, frappe):
			return module._call_label_service({"action": "rate", "shipment": "SHIP-1"}, settings), frappe

	def test_missing_url_never_posts(self):
		requests = fake_requests()
		with loaded(requests_module=requests) as (module, _frappe):
			result = module._call_label_service({"action": "rate"}, Record())
		self.assertEqual(result["error"], "bad_request")
		requests.post.assert_not_called()

	def test_request_is_signed_over_the_exact_body(self):
		requests = fake_requests(response(200, {"ok": True, "easypost_id": "order_1"}))
		result, _frappe = self.call(requests)
		self.assertTrue(result["ok"])
		kwargs = requests.post.call_args.kwargs
		with loaded() as (module, _f):
			self.assertEqual(kwargs["headers"][module.SIGNATURE_HEADER], module.sign(SECRET, kwargs["data"]))
			self.assertEqual(kwargs["timeout"], module.LABEL_TIMEOUT)
		self.assertEqual(json.loads(kwargs["data"]), {"action": "rate", "shipment": "SHIP-1"})

	def test_timeout_tells_staff_to_check_easypost(self):
		result, _frappe = self.call(fake_requests(raises="timeout"))
		self.assertFalse(result["ok"])
		self.assertIn("Check EasyPost", result["message"])

	def test_http_error_and_non_json_are_logged_failures(self):
		for reply in (response(500, {"message": "boom"}), response(200, None, text="<html>")):
			with self.subTest(status=reply.status_code):
				result, frappe = self.call(fake_requests(reply))
				self.assertEqual(result["error"], "easypost_error")
				frappe.log_error.assert_called_once()


class BuyAndVoid(unittest.TestCase):
	def run_buy(self, doc, easypost_id="order_1", result=None):
		with loaded() as (module, frappe):
			with (
				patch.object(module, "_label_doc", return_value=(doc, Record(enabled=1))),
				patch.object(module, "label_payload", return_value={"action": "buy"}),
				patch.object(module, "_call_label_service", return_value=result or {}) as service,
				patch.object(module, "write_labels") as write,
			):
				outcome = module.buy_labels("SHIP-1", easypost_id, "FEDEX_GROUND")
			return outcome, service, write, frappe

	def test_stale_rate_and_double_purchase_are_refused_without_calling_n8n(self):
		with self.assertRaisesRegex(ValueError, "out of date"):
			self.run_buy(shipment(), easypost_id="order_old")
		with self.assertRaisesRegex(ValueError, "already bought"):
			self.run_buy(shipment(ill_label_status="Bought"))

	def test_buy_sends_the_chosen_service_and_writes_back(self):
		result = {"ok": True, "master_tracking": "M1", "parcels": []}
		outcome, service, write, frappe = self.run_buy(shipment(), result=result)
		payload = service.call_args.args[0]
		self.assertEqual((payload["easypost_id"], payload["service_selected"]), ("order_1", "FEDEX_GROUND"))
		write.assert_called_once()
		self.assertTrue(outcome["ok"])
		frappe.db.get_value.assert_any_call("Shipment", "SHIP-1", "name", for_update=True)

	def test_failed_or_numberless_purchase_records_an_error(self):
		for result in ({"ok": False, "error": "no_rate", "message": "No FedEx rate"}, {"ok": True}):
			with self.subTest(result=result):
				outcome, _service, write, frappe = self.run_buy(shipment(), result=result)
				self.assertFalse(outcome["ok"])
				write.assert_not_called()
				values = frappe.db.set_value.call_args.args[2]
				self.assertEqual(values["ill_label_status"], "Error")

	def test_write_labels_maps_boxes_by_row_and_mirrors_to_delivery_notes(self):
		doc = shipment()
		with loaded() as (module, frappe):
			frappe.db.get_value.side_effect = lambda *a, **kw: 1 if a[0] == "Delivery Note" else None
			with patch.object(module, "attach_labels", return_value="/private/files/SHIP-1-labels.pdf"):
				module.write_labels(
					doc,
					{
						"master_tracking": "M1",
						"carrier": "FedEx",
						"service": "FEDEX_GROUND",
						"amount": "41.27",
						"easypost_id": "order_1",
						"parcels": [
							{"row": "row-2", "tracking_number": "B2", "label_url": "https://x/2.pdf"},
							{"row": "row-1", "tracking_number": "M1", "label_url": "https://x/1.pdf"},
						],
					},
				)
			writes = {(c.args[0], c.args[1]): c.args[2] for c in frappe.db.set_value.call_args_list}
		self.assertEqual(writes[("Shipment Parcel", "row-2")]["ill_tracking_number"], "B2")
		self.assertEqual(writes[("Shipment Parcel", "row-1")]["ill_label_url"], "https://x/1.pdf")
		values = writes[("Shipment", "SHIP-1")]
		self.assertEqual(values["awb_number"], "M1")
		self.assertEqual(values["ill_label_status"], "Bought")
		self.assertEqual(values["shipment_amount"], 41.27)
		self.assertEqual(values["ill_label_url"], "/private/files/SHIP-1-labels.pdf")
		self.assertTrue(values["tracking_url"].startswith("https://www.fedex.com/"))
		for dn in ("DN-1", "DN-2"):
			self.assertEqual(
				writes[("Delivery Note", dn)], {"ill_carrier": "FedEx", "ill_tracking_number": "M1"}
			)
		self.assertIn("Master tracking M1", doc.comments[0])

	def test_unknown_carrier_is_mirrored_as_other(self):
		with loaded() as (module, frappe):
			frappe.db.get_value.side_effect = lambda *a, **kw: 1
			module.mirror_to_delivery_notes(shipment(), "DHL", "W1")
			self.assertEqual(frappe.db.set_value.call_args.args[2]["ill_carrier"], "Other")

	def test_void_clears_only_delivery_notes_still_showing_the_voided_number(self):
		doc = shipment(
			ill_label_status="Bought",
			awb_number="M1",
			shipment_parcel=[Record(name="row-1", ill_tracking_number="M1")],
		)
		with loaded() as (module, frappe):
			frappe.db.get_value.side_effect = lambda doctype, name, field, **kw: {
				"DN-1": "M1",
				"DN-2": "MANUAL",
			}.get(name)
			module.clear_labels(doc)
			writes = [(c.args[0], c.args[1], c.args[2]) for c in frappe.db.set_value.call_args_list]
		self.assertIn(("Delivery Note", "DN-1", "ill_tracking_number"), [w[:3] for w in writes])
		self.assertNotIn("DN-2", [w[1] for w in writes if w[0] == "Delivery Note"])
		shipment_values = next(w[2] for w in writes if w[0] == "Shipment")
		self.assertEqual(shipment_values["ill_label_status"], "Voided")
		self.assertIsNone(shipment_values["awb_number"])

	def test_failed_void_keeps_the_labels(self):
		with loaded() as (module, _frappe):
			doc = shipment(ill_label_status="Bought")
			with (
				patch.object(module, "_label_doc", return_value=(doc, Record(enabled=1))),
				patch.object(
					module, "_call_label_service", return_value={"ok": False, "message": "Too late"}
				),
				patch.object(module, "clear_labels") as clear,
			):
				outcome = module.void_labels("SHIP-1")
				clear.assert_not_called()
				self.assertEqual(outcome, {"ok": False, "message": "Too late"})
				with patch.object(
					module, "_call_label_service", return_value={"ok": False, "error": "already_refunded"}
				):
					self.assertEqual(module.void_labels("SHIP-1"), {"ok": True})
				clear.assert_called_once()


class ShipmentHooks(unittest.TestCase):
	def test_cancel_is_blocked_while_labels_are_bought(self):
		with loaded() as (module, _frappe):
			with self.assertRaisesRegex(ValueError, "Void the label"):
				module.shipment_before_cancel(shipment(ill_label_status="Bought"))
			module.shipment_before_cancel(shipment(ill_label_status="Voided"))

	def test_create_shipment_opens_the_existing_one(self):
		with loaded() as (module, frappe):
			dn = MagicMock(docstatus=0)
			dn.name = "DN-1"
			frappe.get_doc.return_value = dn
			with (
				patch.object(module, "shipments_for_delivery_note", return_value=["SHIP-9"]),
				patch.object(module, "build_shipment") as build,
			):
				self.assertEqual(module.make_shipment("DN-1"), {"existing": "SHIP-9"})
			build.assert_not_called()
			dn.check_permission.assert_called_once_with("read")


if __name__ == "__main__":
	unittest.main()
