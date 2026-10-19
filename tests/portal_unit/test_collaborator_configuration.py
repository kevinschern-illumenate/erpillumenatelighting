"""FLOW-6: an EDIT collaborator configures for their schedule, without pricing."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

SCHEDULE = Record(
	doctype="ilL-Project-Fixture-Schedule",
	name="S1",
	owner="dealer@acme.test",
	ill_project="P1",
	inherits_project_privacy=1,
	customer="ACME",
	is_private=0,
	modified="rev-1",
	lines=[],
)
PROJECT = Record(
	name="P1",
	owner="dealer@acme.test",
	owner_customer="ACME",
	is_private=0,
	collaborators=[
		Record(user="designer@studio.test", access_level="EDIT", is_active=1),
		Record(user="viewer@studio.test", access_level="VIEW", is_active=1),
	],
)
DEALERS = {"dealer@acme.test"}
CUSTOMERS = {"dealer@acme.test": "ACME", "stranger@other.test": "OTHER"}

ENGINE_RESULT = {
	"is_valid": True,
	"part_number": "ILL-LIN-1",
	"computed": {"total_watts": 42, "manufacturable_length_mm": 1200},
	"resolved_items": {"profile": {"item_code": "PRO-1", "msrp_unit": 12.5, "unit_cost": 3}},
	"pricing": {"msrp_unit": 100, "tier_unit": 80, "adder_breakdown": [{"amount": 5}]},
	"options": [{"code": "WHT", "label": "White", "msrp_adder": 4, "price_per_ft_msrp": 2}],
	"runs": ({"run": 1, "line_total": 9, "watts": 21},),
	"discount_percentage": 20,
	"base_price_msrp": 50,
}
PRICE_FREE = {
	"is_valid": True,
	"part_number": "ILL-LIN-1",
	"computed": {"total_watts": 42, "manufacturable_length_mm": 1200},
	"resolved_items": {"profile": {"item_code": "PRO-1"}},
	"options": [{"code": "WHT", "label": "White"}],
	"runs": ({"run": 1, "watts": 21},),
}


def access_module():
	"""The real access policy with identity and staff boundaries stubbed."""
	identity = types.SimpleNamespace(
		_is_internal_user=lambda user: False,
		_is_dealer_user=lambda user: user in DEALERS,
		_get_user_customer=lambda user: CUSTOMERS.get(user),
	)
	package = types.ModuleType("ill_project_package")
	package.ill_project = identity
	return load_service(
		ROOT + ".portal.access",
		{
			ROOT + ".doctype.ill_project": package,
			ROOT + ".doctype.ill_project.ill_project": identity,
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda capability, user=None: False),
		},
	)


class ConfiguratorGrant(unittest.TestCase):
	def setUp(self):
		context = access_module()
		self.access, outer = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		outer.db.get_value.return_value = 1  # every test user is enabled
		outer.get_doc.side_effect = lambda doctype, name: PROJECT
		inner = load_service(ROOT + ".portal.configurator_access", {ROOT + ".portal.access": self.access})
		self.grants, self.frappe = inner.__enter__()
		self.addCleanup(inner.__exit__, None, None, None)
		self.frappe.db.exists.side_effect = lambda doctype, name: name == "S1"
		self.frappe.get_doc.side_effect = lambda doctype, name: SCHEDULE
		self.frappe.form_dict = Record()
		self.outer = outer

	def as_user(self, user, **form):
		self.frappe.session = Record(user=user)
		self.outer.session = Record(user=user)
		self.frappe.form_dict = Record(form)

	def test_edit_collaborator_may_configure_for_that_schedule(self):
		self.as_user("designer@studio.test", config_schedule="S1")
		self.grants.require_configurator()
		self.assertTrue(self.grants.can_configure())
		self.assertTrue(self.grants.schedule_grant("S1"))
		self.assertFalse(self.grants.pricing_allowed())
		# A server path that already authorised the schedule passes it by flag.
		self.as_user("designer@studio.test")
		self.frappe.flags["ill_config_schedule"] = "S1"
		self.grants.require_configurator()

	def test_view_collaborator_and_unrelated_user_cannot_configure(self):
		for user in ("viewer@studio.test", "stranger@other.test"):
			self.as_user(user, config_schedule="S1")
			with self.assertRaises(PermissionError):
				self.grants.require_configurator()
			self.assertFalse(self.grants.can_configure())

	def test_collaborator_needs_an_existing_schedule(self):
		for form in ({}, {"config_schedule": "S-MISSING"}, {"config_schedule": ["S1"]}):
			self.as_user("designer@studio.test", **form)
			with self.assertRaises(PermissionError):
				self.grants.require_configurator()

	def test_dealer_keeps_catalog_access_and_pricing(self):
		self.as_user("dealer@acme.test")
		self.grants.require_configurator()
		self.assertTrue(self.grants.pricing_allowed())
		self.frappe.db.exists.assert_not_called()

	def endpoint(self):
		def validate_and_quote(**kwargs):
			return {**ENGINE_RESULT, "runs": tuple(dict(run) for run in ENGINE_RESULT["runs"])}

		validate_and_quote.__module__ = ROOT + ".api.configurator_engine"
		return self.grants.price_scoped(validate_and_quote)

	def test_collaborator_responses_carry_no_price_fields(self):
		endpoint = self.endpoint()
		self.as_user("designer@studio.test", config_schedule="S1", cmd=ROOT + ".api.configurator_engine.validate_and_quote")
		self.assertEqual(endpoint(), PRICE_FREE)
		# The page's request path names the method when cmd is absent.
		self.frappe.form_dict = Record(config_schedule="S1")
		self.frappe.local.request = types.SimpleNamespace(
			path="/api/method/" + ROOT + ".api.configurator_engine.validate_and_quote"
		)
		self.assertEqual(endpoint(), PRICE_FREE)

	def test_dealers_and_internal_callers_keep_the_full_result(self):
		endpoint = self.endpoint()
		self.as_user("dealer@acme.test", cmd=ROOT + ".api.configurator_engine.validate_and_quote")
		self.assertEqual(endpoint()["pricing"]["msrp_unit"], 100)
		# A save calling the engine internally reads its pricing.
		self.as_user("designer@studio.test", config_schedule="S1", cmd=ROOT + ".portal.configuration.save")
		self.assertEqual(endpoint()["pricing"]["tier_unit"], 80)

	def test_price_keys(self):
		for key in ("msrp_unit", "price_per_ft_msrp", "pricing", "tier_unit", "unit_cost", "msrp_adder", "line_total"):
			self.assertTrue(self.grants.is_price_key(key), key)
		for key in ("total_watts", "item_code", "segment_count", "qty", "lumens_per_ft", "spec_name"):
			self.assertFalse(self.grants.is_price_key(key), key)


class ConfigurationGate(unittest.TestCase):
	def test_validation_endpoints_accept_the_schedule_grant(self):
		gate = MagicMock()
		deps = {
			ROOT + ".portal.configurator_access": types.SimpleNamespace(require_configurator=gate),
			ROOT + ".portal.site_flags": types.SimpleNamespace(conf_list=lambda key: None),
		}
		with load_service(ROOT + ".portal.rollout", deps) as (rollout, frappe):
			rollout.require_configuration("Linear Fixture")
			gate.assert_called_once_with()
			gate.reset_mock()
			gate.side_effect = PermissionError("no")
			with self.assertRaises(PermissionError):
				rollout.require_configuration("Linear Fixture")
			frappe.flags["ill_product_download"] = True
			rollout.require_configuration("LED Sheet")


class DriverSaveGate(unittest.TestCase):
	def run_save(self, can_edit):
		reached = MagicMock(side_effect=LookupError("reached the schedule write check"))
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(
				require_catalog_access=MagicMock(side_effect=PermissionError("catalog")),
				can_edit_schedule=MagicMock(return_value=can_edit),
			),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				RECEIPT="Receipt",
				object_value=lambda value, label: value or {},
				resolve_line=MagicMock(),
				schedule_context=reached,
			),
			ROOT + ".portal.rollout": types.SimpleNamespace(require_family=MagicMock()),
			ROOT + ".api.driver_controller_configurator": types.SimpleNamespace(
				DRIVER_STEPS=[{"name": "wattage"}], _validate_configuration=MagicMock()
			),
			ROOT + ".portal.product_finder.sessions": types.SimpleNamespace(),
			ROOT + ".portal.product_finder.verification": types.SimpleNamespace(),
		}
		with load_service(ROOT + ".portal.driver_configuration", deps) as (service, frappe):
			frappe.session = Record(user="designer@studio.test")
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = SCHEDULE
			service.save(
				schedule_name="S1",
				template="DRV-A",
				selections={"wattage": "96"},
				idempotency_key="retry-key",
				expected_modified="rev-1",
			)

	def test_schedule_editor_reaches_the_save_and_others_are_refused(self):
		with self.assertRaisesRegex(LookupError, "schedule write check"):
			self.run_save(can_edit=True)
		with self.assertRaisesRegex(PermissionError, "catalog"):
			self.run_save(can_edit=False)


class Context(Record):
	__setattr__ = dict.__setitem__


class ConfigurePage(unittest.TestCase):
	def run_page(self, user, can_view_catalog, can_edit, form):
		stubs = {}
		for name, attributes in {
			".portal.access": {
				"can_view_catalog": lambda user=None: can_view_catalog,
				"can_edit_schedule": lambda doc, user=None: can_edit,
			},
			".portal.site_flags": {"fixture_groups_enabled": lambda: False},
			".portal.rollout": {"require_family": lambda family: None},
			".portal.configuration": {"family_for_template": lambda family, template: family},
			".portal.product_finder.presentation": {
				"chooser": lambda query: [
					{"value": "Linear Fixture", "href": "/portal/configure?category=Linear+Fixture&schedule=S1"},
					{"value": "Accessory", "href": "/portal/products?type=Accessory&schedule=S1"},
				]
			},
			".api.configuration_contract": {
				"finite_number": lambda value, **kwargs: float(value),
				"TAPE_CATEGORIES": ("LED Tape", "COB Tape"),
				"TAPE_NEON_CATEGORIES": ("LED Tape", "COB Tape", "LED Neon"),
			},
			".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": {
				"has_permission": lambda doc, ptype, user: can_edit or ptype == "read"
			},
		}.items():
			stubs[ROOT + name] = types.ModuleType(ROOT + name)
			stubs[ROOT + name].__dict__.update(attributes)
		with load_service("illumenate_lighting.templates.pages.configure", stubs) as (module, frappe):
			frappe.session = Record(user=user)
			frappe.form_dict = Record(form)
			frappe.local.flags = Record()
			frappe.Redirect = type("Redirect", (Exception,), {})
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = SCHEDULE
			frappe.get_all.return_value = []
			module.require_login = lambda: None
			context = Context()
			try:
				module.get_context(context)
			except frappe.Redirect:
				return frappe.local.flags.redirect_location, None, frappe
			return None, context, frappe

	def test_edit_collaborator_opens_the_configurator_without_pricing(self):
		redirect, context, frappe = self.run_page(
			"designer@studio.test", False, True, {"category": "Linear Fixture", "schedule": "S1"}
		)
		self.assertIsNone(redirect)
		self.assertFalse(context.show_pricing)
		self.assertFalse(context.show_stock_qty)
		self.assertEqual(context.config_schedule, "S1")
		self.assertTrue(context.can_save)
		self.assertEqual(frappe.flags["ill_config_schedule"], "S1")

	def test_collaborator_chooser_hides_catalog_routes(self):
		_redirect, context, _frappe = self.run_page("designer@studio.test", False, True, {"schedule": "S1"})
		self.assertEqual([option["value"] for option in context.chooser_options], ["Linear Fixture"])

	def test_view_collaborator_and_unrelated_users_are_sent_to_dealer_access(self):
		for form in ({"category": "Linear Fixture", "schedule": "S1"}, {"category": "Linear Fixture"}):
			redirect, _context, _frappe = self.run_page("viewer@studio.test", False, False, form)
			self.assertEqual(redirect, "/portal/request-dealer-access")

	def test_dealer_page_is_unchanged(self):
		redirect, context, _frappe = self.run_page("dealer@acme.test", True, True, {"category": "Linear Fixture"})
		self.assertIsNone(redirect)
		self.assertTrue(context.show_pricing)
		self.assertTrue(context.show_stock_qty)
		self.assertEqual(context.config_schedule, "")


if __name__ == "__main__":
	unittest.main()
