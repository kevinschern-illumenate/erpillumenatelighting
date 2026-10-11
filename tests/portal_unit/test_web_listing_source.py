"""Product data is read from templates; marketing content from the Webflow Product."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service

PRODUCT = "ilL-Webflow-Product"
FIXTURE = "ilL-Fixture-Template"


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)

	def as_dict(self):
		return dict(self)


class Doc(Row):
	def __init__(self, before=None, **values):
		super().__init__(values)
		self.before = before

	def get(self, key, default=None):
		value = super().get(key, default)
		return [Row(row) for row in value] if isinstance(value, list) else value

	def as_dict(self):
		return {key: self.get(key) for key in self}

	def get_doc_before_save(self):
		return self.before


def product(**values):
	return Doc(
		**{
			"name": "ill-el01-sw",
			"product_name": "Elevate [SW]",
			"product_type": "Linear Fixture",
			"is_active": 1,
			"fixture_template": "ILL-EL01-SW",
			"short_description": "Listing copy",
			"min_length_mm": 300,
			"product_badge": "",
			"feed_lengths": [{"code": "06"}],
			"gallery_images": [{"image": "/files/a.jpg"}],
			**values,
		}
	)


def template(**values):
	return Doc(
		**{
			"doctype": FIXTURE,
			"name": "ILL-EL01-SW",
			"template_name": "Elevate SW",
			"webflow_product": "ill-el01-sw",
			"min_length_mm": 600,
			"beam_angle": None,
			"feed_lengths": [{"code": "08"}],
			**values,
		}
	)


def listing(source, migrated=True, **template_values):
	with load_service(ROOT + ".web_listing_source") as (module, frappe):
		module.template_for = MagicMock(return_value=(FIXTURE, "ILL-EL01-SW") if migrated else (None, None))
		frappe.get_doc.return_value = template(**template_values)
		return module.Listing(source)


class Reading(unittest.TestCase):
	def test_product_data_comes_from_the_template(self):
		view = listing(product())
		self.assertEqual(view.min_length_mm, 600)
		self.assertEqual(view.feed_lengths[0].code, "08")

	def test_marketing_content_and_identity_stay_on_the_webflow_product(self):
		view = listing(product())
		self.assertEqual(view.short_description, "Listing copy")
		self.assertEqual(view.product_name, "Elevate [SW]")
		self.assertEqual(view.gallery_images[0].image, "/files/a.jpg")
		self.assertEqual(view.source.name, "ill-el01-sw")

	def test_an_equal_empty_value_keeps_the_webflow_product_form(self):
		view = listing(product(beam_angle=0))
		self.assertEqual(view.beam_angle, 0)

	def test_unmigrated_listing_reads_the_webflow_product(self):
		view = listing(product(), migrated=False)
		self.assertEqual(view.min_length_mm, 300)
		self.assertEqual(view.as_dict()["feed_lengths"], [{"code": "06"}])

	def test_legacy_read_switch_sends_readers_back_to_the_webflow_product(self):
		with load_service(ROOT + ".web_listing_source") as (module, frappe):
			module.template_for = MagicMock(return_value=(FIXTURE, "ILL-EL01-SW"))
			frappe.conf["web_listing_legacy_read"] = 1
			view = module.Listing(product())
		self.assertIsNone(view.template)
		self.assertEqual(view.min_length_mm, 300)

	def test_overlay_replaces_only_product_data(self):
		data = listing(product()).overlay(
			{"name": "ill-el01-sw", "min_length_mm": 1, "short_description": "x"}
		)
		self.assertEqual(data, {"name": "ill-el01-sw", "min_length_mm": 600, "short_description": "x"})

	def test_as_dict_carries_template_tables(self):
		self.assertEqual(listing(product()).as_dict()["feed_lengths"], [{"code": "08"}])


def sync(saved, current_listing, linked=True):
	with load_service(ROOT + ".web_listing_source") as (module, frappe):
		module.template_for = MagicMock(return_value=(FIXTURE, "ILL-EL01-SW") if linked else (None, None))
		module._listing = MagicMock(return_value=current_listing)
		events = MagicMock()
		module_events = MagicMock(on_product_update=events)
		with unittest.mock.patch.dict(
			"sys.modules",
			{"illumenate_lighting.illumenate_lighting.api.webflow_sync_events": module_events},
		):
			changed = module.sync_to_listing(saved)
		return changed, frappe, events


class SyncingToTheListing(unittest.TestCase):
	def test_a_template_edit_reaches_its_webflow_product(self):
		current = {"min_length_mm": 300, "feed_lengths": [{"code": "08"}]}
		changed, frappe, events = sync(template(), current)
		self.assertEqual(changed, ["min_length_mm"])
		frappe.db.set_value.assert_called_once_with(
			PRODUCT, "ill-el01-sw", {"min_length_mm": 600}, update_modified=False
		)
		events.assert_called_once()

	def test_a_changed_table_is_replaced(self):
		current = {"min_length_mm": 600, "feed_lengths": [{"code": "06"}]}
		changed, frappe, _events = sync(template(), current)
		self.assertEqual(changed, ["feed_lengths"])
		frappe.db.delete.assert_called_once_with(
			"ilL-Child-Webflow-Feed-Length",
			{"parent": "ill-el01-sw", "parenttype": PRODUCT, "parentfield": "feed_lengths"},
		)

	def test_nothing_changes_when_already_in_step(self):
		current = {"min_length_mm": 600, "beam_angle": 0, "feed_lengths": [{"code": "08"}]}
		changed, frappe, events = sync(template(), current)
		self.assertEqual(changed, [])
		frappe.db.set_value.assert_not_called()
		events.assert_not_called()

	def test_a_template_that_does_not_hold_the_listing_is_ignored(self):
		changed, frappe, _events = sync(template(), {}, linked=False)
		self.assertEqual(changed, [])
		frappe.db.set_value.assert_not_called()


class TopUp(unittest.TestCase):
	def run_top_up(self, saved):
		with load_service(ROOT + ".web_listing_source") as (module, _frappe):
			module._migrate_one_safely = MagicMock(return_value={"action": "migrated"})
			return module.top_up_template(saved), module._migrate_one_safely

	def test_a_newly_linked_template_gets_the_listing_data(self):
		row, migrate = self.run_top_up(product(before=product(fixture_template=None)))
		self.assertEqual(row, {"action": "migrated"})
		self.assertEqual(migrate.call_args[0][1:3], (FIXTURE, "ILL-EL01-SW"))

	def test_an_unchanged_link_is_left_alone(self):
		row, migrate = self.run_top_up(product(before=product()))
		self.assertIsNone(row)
		migrate.assert_not_called()


class PayloadParity(unittest.TestCase):
	def test_reports_keys_that_differ_between_the_two_reads(self):
		with load_service(ROOT + ".web_listing_source") as (module, frappe):
			frappe.only_for = MagicMock()
			module.template_for = MagicMock(side_effect=[(FIXTURE, "A"), (None, None)])
			frappe.get_all.side_effect = [["ill-a", "ill-b"], ["illumenate"]]
			module._export = MagicMock(
				side_effect=lambda name, brand: (
					{"min_length_mm": 300, "name": name}
					if getattr(frappe.flags, "web_listing_legacy_read", None)
					else {"min_length_mm": 600, "name": name}
				)
			)
			report = module.payload_parity()
		self.assertEqual(
			report, [{"listing": "ill-a", "brand": "illumenate", "differences": ["min_length_mm"]}]
		)


if __name__ == "__main__":
	unittest.main()
