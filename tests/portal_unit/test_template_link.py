"""Phase 1a: the template owns its link to a Webflow Product (plan 4.2)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

KIT = "ilL-Extrusion-Kit-Template"
TAPE = "ilL-Tape-Neon-Template"


class Flags(dict):
	__getattr__ = dict.get

	def __setattr__(self, key, value):
		self[key] = value


class Doc(dict):
	"""Just enough of a Frappe Document for the link rules."""

	def __init__(self, doctype, name, before=None, new=False, **values):
		super().__init__(values)
		self.__dict__.update(doctype=doctype, name=name, before=before, new=new, flags=Flags())
		self.save = MagicMock()

	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		if key in ("doctype", "name", "before", "new", "flags", "save"):
			self.__dict__[key] = value
		else:
			self[key] = value

	def is_new(self):
		return self.new

	def get_doc_before_save(self):
		return self.before

	def set(self, key, value):
		self[key] = value


def brand(code="illumenate", enabled=1):
	return Record(brand=code, enabled=enabled)


class LinkRules(unittest.TestCase):
	def setUp(self):
		staff = types.ModuleType(ROOT + ".portal.staff")
		staff.allowed = MagicMock(return_value=True)
		self.staff = staff
		context = load_service(ROOT + ".template_link", {staff.__name__: staff})
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.frappe.PermissionError = PermissionError
		self.products = {}  # product -> {fieldname: value}
		self.frappe.db.get_value.side_effect = self.get_value
		self.frappe.get_all.return_value = []
		self.frappe.db.sql.return_value = []

	def get_value(self, doctype, name, fields=None, as_dict=False):
		if doctype == "User":
			return "System User"
		if doctype == "ilL-Webflow-Product":
			row = self.products.get(name)
			if row is None:
				return None
			if isinstance(fields, list):
				return Record({field: row.get(field) for field in fields})
			return row.get(fields)
		if doctype == KIT and fields == "webflow_product":
			return getattr(self, "claimed", {}).get(name)
		if doctype == "ilL-Product-Publication":
			return (
				self.published.get((name["product"], name["brand"])) if hasattr(self, "published") else None
			)
		return None

	def template(self, before=None, **values):
		values.setdefault("target_brands", [brand()])
		values.setdefault("product_status", "Internal Only")
		return Doc(KIT, "KIT-RA01", before=before, **values)

	# ---- names

	def test_a_new_template_cannot_reuse_another_doctypes_name_in_any_case(self):
		doc = Doc(KIT, "KIT-RA01", new=True, target_brands=[])
		self.frappe.db.sql.return_value = [("kit-ra01",)]
		with self.assertRaisesRegex(ValueError, "unique across all template types"):
			self.module.validate_unique_name(doc)
		# Its own doctype is not queried; existing records are not re-checked.
		queried = [call.args[0] for call in self.frappe.db.sql.call_args_list]
		self.assertFalse(any(f"`tab{KIT}`" in sql for sql in queried))
		self.frappe.db.sql.reset_mock()
		self.module.validate_unique_name(Doc(KIT, "KIT-RA01", before=Doc(KIT, "KIT-RA01")))
		self.frappe.db.sql.assert_not_called()

	# ---- brands

	def test_only_one_target_brand_may_be_enabled(self):
		with self.assertRaisesRegex(ValueError, "Enable only one"):
			self.module.validate_target_brands(self.template(target_brands=[brand(), brand("lighting_206")]))
		self.module.validate_target_brands(
			self.template(target_brands=[brand(), brand("lighting_206", enabled=0)])
		)

	def test_the_brand_is_locked_once_published_on_the_old_brand(self):
		before = self.template(webflow_product="kit-ra01")
		after = self.template(
			before=before, webflow_product="kit-ra01", target_brands=[brand("lighting_206")]
		)
		self.module.validate_target_brands(after)  # never published: allowed
		self.published = {("kit-ra01", "illumenate"): "PUB-1"}
		with self.assertRaisesRegex(ValueError, "brand cannot change"):
			self.module.validate_target_brands(after)

	# ---- the link itself

	def test_linking_checks_type_existing_links_and_brand(self):
		self.products = {
			"kit-ra01": {"product_type": "Extrusion Kit"},
			"tape-1": {"product_type": "LED Tape"},
		}
		before = self.template()
		self.module.validate_webflow_product(self.template(before=before, webflow_product="kit-ra01"))
		with self.assertRaisesRegex(ValueError, "does not exist"):
			self.module.validate_webflow_product(self.template(before=before, webflow_product="nope"))
		with self.assertRaisesRegex(ValueError, "can only link a product of type Extrusion Kit"):
			self.module.validate_webflow_product(self.template(before=before, webflow_product="tape-1"))
		with self.assertRaisesRegex(ValueError, "exactly one Target Brand"):
			self.module.validate_webflow_product(
				self.template(before=before, webflow_product="kit-ra01", target_brands=[])
			)
		self.products["kit-ra01"]["kit_template"] = "KIT-OTHER"
		with self.assertRaisesRegex(ValueError, "already linked to ilL-Extrusion-Kit-Template KIT-OTHER"):
			self.module.validate_webflow_product(self.template(before=before, webflow_product="kit-ra01"))

	def test_a_set_link_changes_only_through_the_unlink_action(self):
		self.products = {"kit-ra02": {"product_type": "Extrusion Kit"}}
		before = self.template(webflow_product="kit-ra01")
		with self.assertRaisesRegex(ValueError, "Unlink Webflow Product"):
			self.module.validate_webflow_product(self.template(before=before, webflow_product="kit-ra02"))
		with self.assertRaisesRegex(ValueError, "Unlink Webflow Product"):
			self.module.validate_webflow_product(self.template(before=before, webflow_product=None))
		cleared = self.template(before=before, webflow_product=None)
		cleared.flags.webflow_link_action = True
		self.module.validate_webflow_product(cleared)

	def test_active_live_needs_a_product_and_cannot_be_unlinked(self):
		LIVE = "Active + Live"
		with self.assertRaisesRegex(ValueError, "before setting the Product Status to Active \\+ Live"):
			self.module.validate_webflow_product(self.template(before=self.template(), product_status=LIVE))
		# Plain Active is offered in ERPNext and the portal only: no Webflow Product needed (D60).
		self.module.validate_webflow_product(self.template(before=self.template(), product_status="Active"))
		active = self.template(
			before=self.template(webflow_product="kit-ra01", product_status="Active"),
			webflow_product=None,
			product_status="Active",
		)
		active.flags.webflow_link_action = True
		self.module.validate_webflow_product(active)
		# A Live template saved before this rule existed is reported, not blocked.
		self.module.validate_webflow_product(
			self.template(before=self.template(product_status=LIVE), product_status=LIVE)
		)
		unlink = self.template(
			before=self.template(webflow_product="kit-ra01", product_status=LIVE),
			webflow_product=None,
			product_status=LIVE,
		)
		unlink.flags.webflow_link_action = True
		with self.assertRaisesRegex(ValueError, "needs its Webflow Product"):
			self.module.validate_webflow_product(unlink)

	def test_linking_needs_the_catalog_role_and_write_access(self):
		self.products = {"kit-ra01": {"product_type": "Extrusion Kit"}}
		doc = self.template(before=self.template(), webflow_product="kit-ra01")
		self.staff.allowed.return_value = False
		with self.assertRaisesRegex(PermissionError, "ilL Catalog Publisher"):
			self.module.validate_webflow_product(doc)
		self.staff.allowed.return_value = True
		self.frappe.has_permission.return_value = False
		with self.assertRaises(PermissionError):
			self.module.validate_webflow_product(doc)

	# ---- writing the product side

	def test_linking_saves_the_product_with_its_mirror_field(self):
		product = Doc("ilL-Webflow-Product", "kit-ra01")
		self.frappe.get_doc.return_value = product
		self.module.on_template_update(self.template(before=self.template(), webflow_product="kit-ra01"))
		self.assertEqual(product["kit_template"], "KIT-RA01")
		self.assertTrue(product.flags.from_template_link)
		product.save.assert_called_once_with(ignore_permissions=True)

	def test_unlinking_clears_only_a_product_that_points_back(self):
		self.products = {"kit-ra01": {"kit_template": "KIT-RA01"}}
		self.frappe.db.set_value = MagicMock()
		self.module.on_template_update(
			self.template(before=self.template(webflow_product="kit-ra01"), webflow_product=None)
		)
		self.frappe.db.set_value.assert_called_once_with(
			"ilL-Webflow-Product", "kit-ra01", "kit_template", None
		)
		self.frappe.db.set_value.reset_mock()
		self.products = {"kit-ra01": {"kit_template": "KIT-OTHER"}}
		self.module.on_template_trash(self.template(webflow_product="kit-ra01"))
		self.frappe.db.set_value.assert_not_called()

	# ---- product side

	def test_product_link_fields_are_mirrors(self):
		before = Doc("ilL-Webflow-Product", "kit-ra01", product_type="Extrusion Kit")
		changed = Doc(
			"ilL-Webflow-Product",
			"kit-ra01",
			before=before,
			product_type="Extrusion Kit",
			kit_template="KIT-RA01",
		)
		with self.assertRaisesRegex(ValueError, "linked from the template"):
			self.module.validate_product_links(changed)
		changed.flags.from_template_link = True
		self.module.validate_product_links(changed)

	def test_a_duplicate_product_drops_the_template_link(self):
		copy = Doc("ilL-Webflow-Product", "new", new=True, kit_template="KIT-RA01")
		copy.flags.in_copy = True
		self.module.validate_product_links(copy)
		self.assertIsNone(copy["kit_template"])

	def test_a_linked_product_cannot_change_to_a_type_its_template_does_not_serve(self):
		before = Doc("ilL-Webflow-Product", "kit-ra01", product_type="Extrusion Kit", kit_template="KIT-RA01")
		moved = Doc(
			"ilL-Webflow-Product",
			"kit-ra01",
			before=before,
			product_type="Component",
			kit_template="KIT-RA01",
		)
		with self.assertRaisesRegex(ValueError, "Unlink it from the template first"):
			self.module.validate_product_links(moved)

	def test_a_new_product_may_be_created_for_an_unclaimed_template(self):
		new = Doc(
			"ilL-Webflow-Product", "kit-ra01", new=True, product_type="Extrusion Kit", kit_template="KIT-RA01"
		)
		self.module.validate_product_links(new)
		self.frappe.db.set_value = MagicMock()
		self.module.on_product_insert(new)
		self.frappe.db.set_value.assert_called_once_with(
			KIT, "KIT-RA01", "webflow_product", "kit-ra01", update_modified=False
		)
		self.claimed = {"KIT-RA01": "kit-other"}
		with self.assertRaisesRegex(ValueError, "already linked to kit-other"):
			self.module.validate_product_links(new)
		self.claimed = {}
		wrong = Doc("ilL-Webflow-Product", "x", new=True, product_type="Driver", kit_template="KIT-RA01")
		with self.assertRaisesRegex(ValueError, "can only link a product of type Extrusion Kit"):
			self.module.validate_product_links(wrong)
		both = Doc(
			"ilL-Webflow-Product", "x", new=True, product_type="Driver", kit_template="K", driver_template="D"
		)
		with self.assertRaisesRegex(ValueError, "exactly one template"):
			self.module.validate_product_links(both)
		self.staff.allowed.return_value = False
		with self.assertRaises(PermissionError):
			self.module.validate_product_links(new)

	# ---- endpoints

	def test_unlink_action_saves_with_the_action_flag(self):
		doc = self.template(webflow_product="kit-ra01")
		self.frappe.get_doc.return_value = doc
		self.module.unlink_webflow_product(KIT, "KIT-RA01")
		self.assertIsNone(doc["webflow_product"])
		self.assertTrue(doc.flags.webflow_link_action)
		doc.save.assert_called_once_with()
		with self.assertRaisesRegex(ValueError, "not a product template"):
			self.module.unlink_webflow_product("ilL-Webflow-Product", "x")

	def test_link_action_refuses_an_already_linked_template(self):
		self.frappe.get_doc.return_value = self.template(webflow_product="kit-ra01")
		with self.assertRaisesRegex(ValueError, "Unlink it first"):
			self.module.link_webflow_product(KIT, "KIT-RA01", "kit-ra02")


if __name__ == "__main__":
	unittest.main()
