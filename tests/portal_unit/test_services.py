"""Service unit tests with explicit Frappe boundary doubles; not Bench tests."""

import importlib.util
import io
import json
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

ROOT = "illumenate_lighting.illumenate_lighting"


class Record(dict):
	def __getattr__(self, key):
		return self.get(key)


def throwing(message, exception=ValueError):
	raise exception(message)


@contextmanager
def load_service(relative, extras=None):
	frappe = types.ModuleType("frappe")
	frappe.whitelist = lambda **kwargs: lambda function: function
	frappe._ = lambda value: value
	frappe.throw = throwing
	frappe.PermissionError = PermissionError
	frappe.ValidationError = ValueError
	frappe.DoesNotExistError = LookupError
	frappe.as_json = lambda value: json.dumps(value, default=str)
	frappe.has_permission = MagicMock(return_value=True)
	frappe.session = Record(user="buyer@example.com")
	frappe.db = MagicMock()
	frappe.local = types.SimpleNamespace()
	frappe.conf = Record()
	frappe.get_all = MagicMock()
	frappe.get_doc = MagicMock()
	frappe.get_roles = MagicMock(return_value=["Dealer"])
	frappe.flags = Record()
	frappe.msgprint = MagicMock()
	utils = types.ModuleType("frappe.utils")
	utils.flt = lambda value: float(value or 0)
	utils.cint = lambda value: int(value or 0)
	utils.now_datetime = lambda: "2026-09-25 12:00:00"
	utils.now = utils.now_datetime
	utils.nowdate = lambda: "2026-09-25"
	utils.getdate = lambda value: str(value)[:10]
	utils.get_datetime = lambda value: value if isinstance(value, datetime) else datetime.fromisoformat(value)
	frappe.utils = utils
	modules = {"frappe": frappe, "frappe.utils": utils, **(extras or {})}
	path = relative.replace(".", "/") + ".py"
	spec = importlib.util.spec_from_file_location("isolated_service", path)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, modules):
		spec.loader.exec_module(module)
		yield module, frappe


class WarehouseScope(unittest.TestCase):
	def test_company_is_mandatory(self):
		with load_service(ROOT + ".api.pricing_utils") as (module, frappe):
			frappe.db.get_single_value.return_value = None
			with self.assertRaisesRegex(ValueError, "stock company"):
				module._eligible_warehouses()
			frappe.get_all.assert_not_called()

	def test_missing_scope_never_queries_all_bins(self):
		with load_service(ROOT + ".api.pricing_utils") as (module, frappe):
			frappe.conf["ill_portal_stock_company"] = "Company A"
			frappe.get_all.return_value = []
			with self.assertRaisesRegex(ValueError, "ilL-Stores"):
				module._bulk_stock_query(["TAPE"])
			frappe.db.sql.assert_not_called()
			self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["company"], "Company A")

	def test_scope_sql_always_has_warehouse_predicate(self):
		with load_service(ROOT + ".api.pricing_utils") as (module, frappe):
			frappe.conf["ill_portal_stock_company"] = "Company A"
			frappe.get_all.return_value = ["ilL-Stores - A"]
			sql, warehouses = module._available_qty_sql("%s")
			self.assertIn("AND warehouse IN (%s)", sql)
			self.assertEqual(warehouses, ["ilL-Stores - A"])
			self.assertNotIn("all", module.stock_scope_info()["warehouse_scope"])


class PrivateUploadAccess(unittest.TestCase):
	def artifact(self, **values):
		return Record(
			requested_by="buyer@example.com",
			state="FINALIZED",
			parent_type="ilL-Project-Fixture-Schedule",
			parent_name="S1",
			**values,
		)

	def test_revoked_uploader_does_not_keep_project_access(self):
		with (
			load_service(ROOT + ".portal.files") as (module, _frappe),
			patch.object(module, "_context_access", return_value=False),
		):
			self.assertFalse(module.has_permission(self.artifact()))

	def test_unrelated_user_cannot_read_staging(self):
		with (
			load_service(ROOT + ".portal.files") as (module, _frappe),
			patch.object(module, "_context_access", return_value=True),
		):
			artifact = self.artifact()
			artifact["state"] = "STAGING"
			self.assertFalse(module.has_permission(artifact, user="other@example.com"))

	def test_no_url_or_public_file_adoption(self):
		with (
			load_service(ROOT + ".portal.files") as (module, frappe),
			patch.object(module, "_context_access", return_value=True),
		):
			frappe.get_doc.return_value = Record(is_private=0, attached_to_doctype="ilL-Portal-Upload")
			with self.assertRaises(PermissionError):
				module.verify_upload("FILE1", "Issue", "ISSUE1")

	def test_foreign_owner_or_parent_rejected(self):
		for mismatch in ("owner", "parent"):
			with (
				self.subTest(mismatch=mismatch),
				load_service(ROOT + ".portal.files") as (module, frappe),
				patch.object(module, "_context_access", return_value=True),
			):
				file = Record(
					name="FILE1", is_private=1, attached_to_doctype="ilL-Portal-Upload", attached_to_name="U1"
				)
				artifact = self.artifact(file="FILE1")
				artifact["requested_by" if mismatch == "owner" else "parent_name"] = "foreign"
				frappe.get_doc.side_effect = [file, artifact]
				with self.assertRaises(PermissionError):
					module.verify_upload("FILE1", "ilL-Project-Fixture-Schedule", "S1")

	def test_finalize_validates_whole_set_before_mutating(self):
		with (
			load_service(ROOT + ".portal.files") as (module, frappe),
			patch.object(module, "_context_access", return_value=True),
		):
			frappe.get_all.return_value = []
			artifact = MagicMock()
			with patch.object(
				module, "verify_upload", side_effect=[(artifact, MagicMock()), PermissionError("foreign")]
			) as verify:
				with self.assertRaises(PermissionError):
					module.finalize_files(["A", "B"], "Issue", "ISSUE1")
				self.assertEqual(verify.call_count, 2)
			artifact.save.assert_not_called()

	def test_intake_limit_counts_previously_finalized_files(self):
		with (
			load_service(ROOT + ".portal.files") as (module, frappe),
			patch.object(module, "_context_access", return_value=True),
			patch.object(module, "verify_upload") as verify,
		):
			frappe.get_all.return_value = [str(index) for index in range(10)]
			with self.assertRaisesRegex(ValueError, "at most 10"):
				module.finalize_files(["new"], "Issue", "ISSUE1")
			verify.assert_not_called()
			self.assertIn("for update", frappe.db.sql.call_args.args[0])


class FileValidation(unittest.TestCase):
	def test_invalid_formats_empty_and_oversized(self):
		for name, content in (
			("x.pdf", b"wrong"),
			("x.exe", b"%PDF-1.5"),
			("x.png", b""),
			("x.pdf", b"x" * (20 * 1024 * 1024 + 1)),
		):
			with self.subTest(name=name), self.assertRaises(ValueError):
				validate_content(name, content)

	def test_png_checksum_and_spoofed_extension(self):
		from PIL import Image

		stream = io.BytesIO()
		Image.new("RGB", (2, 2)).save(stream, format="PNG")
		content = stream.getvalue()
		metadata = validate_content("../../image.png", content)
		self.assertEqual(metadata["filename"], "image.png")
		self.assertEqual(len(metadata["sha256"]), 64)
		with self.assertRaises(ValueError):
			validate_content("image.jpg", content)

	def test_pdf_pages_and_encryption(self):
		from pypdf import PdfWriter

		writer = PdfWriter()
		writer.add_blank_page(width=100, height=100)
		stream = io.BytesIO()
		writer.write(stream)
		self.assertEqual(validate_content("example.pdf", stream.getvalue())["pages"], 1)
		writer.encrypt("secret")
		stream = io.BytesIO()
		writer.write(stream)
		with self.assertRaisesRegex(ValueError, "Encrypted"):
			validate_content("example.pdf", stream.getvalue())


class OrderRetry(unittest.TestCase):
	def test_authorized_existing_request_precedes_create_eligibility(self):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		orders = types.ModuleType(ROOT + ".portal.orders")
		orders.load_accessible_sales_order = MagicMock(return_value=Record(name="SO1"))
		with load_service(
			ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule",
			{"frappe.model.document": document, ROOT + ".portal.orders": orders},
		) as (module, frappe):
			schedule = MagicMock(name="schedule")
			schedule.name = "S1"
			schedule.get_linked_sales_order.return_value = "SO1"
			with (
				patch.object(module, "can_request_schedule_order", return_value=(True, "")),
				patch.object(
					module, "can_convert_schedule_to_order", return_value=(False, "already requested")
				) as guard,
			):
				result = module.ilLProjectFixtureSchedule.create_sales_order_result(schedule)
			self.assertTrue(result["already_existed"])
			self.assertEqual(result["sales_order"], "SO1")
			self.assertIn("for update", frappe.db.sql.call_args.args[0])
			schedule.reload.assert_called_once()
			guard.assert_not_called()
			schedule._build_and_insert_sales_order.assert_not_called()

	def test_denied_actor_never_gets_existing_request(self):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		with load_service(
			ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule",
			{"frappe.model.document": document},
		) as (module, _frappe):
			schedule = MagicMock()
			with (
				patch.object(module, "can_request_schedule_order", return_value=(False, "denied")),
				self.assertRaises(PermissionError),
			):
				module.ilLProjectFixtureSchedule.create_sales_order_result(schedule)
			schedule.get_linked_sales_order.assert_not_called()


if __name__ == "__main__":
	unittest.main()
