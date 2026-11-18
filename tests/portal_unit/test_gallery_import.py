"""Import of the existing Webflow galleries (docs/WEBFLOW_GALLERY_SYNC.md section 9a), stubbed Frappe."""

import copy
import json
import os
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

MODULE = ROOT + ".api.gallery_import"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_previous_cwd = None
ODE_PRODUCT = "6" * 24
CDN = "https://cdn.prod.website-files.com/site/"

SERIES = {
	"custom": "Custom",
	"st. helens": "St. Helens",
	"led tape": "LED Tape",
	"rainier": "Rainier",
}
PRODUCTS = {ODE_PRODUCT: "rainier-sf"}


def setUpModule():
	global _previous_cwd
	_previous_cwd = os.getcwd()
	os.chdir(REPO)


def tearDownModule():
	os.chdir(_previous_cwd)


def image(name, alt=""):
	return {"fileId": "f" + name, "url": f"{CDN}{name}.jpg", "alt": alt}


def item(slug, name, **fields):
	data = {"name": name, "slug": slug}
	data.update(fields)
	return {"id": "i" * 23 + slug[0], "isDraft": False, "isArchived": False, "fieldData": data}


def ode():
	return item(
		"ode-wellness",
		"Ode Wellness",
		featured=True,
		**{
			"featured-image": image("ode1"),
			"gallery": [image(f"ode{n}", f"Ode {n}") for n in range(1, 6)],
			"short-description": "A calm spa.",
			"about": "Soft light.",
			"case-study": "<p>Case &amp; study</p>",
			"project-type": "healthcare",
			"applications": "Cove, Backlighting",
			"services-provided": "Takeoff Drawings",
			"products-used": [ODE_PRODUCT],
			"owner": "Ode Owner",
			"owner-website": "https://owner.example",
			"client-integrator": "Integrator Co",
			"photo-credit": "Pat Photo",
			"architect": "",
			"architect-website": "https://ignored.example",
			"completion-date": "2025-03-04T00:00:00.000Z",
		},
	)


def holodeck():
	return item(
		"holodeck-wall",
		"Holodeck Wall",
		**{
			"gallery": [image("h1"), image("h2")],
			"series-used": "Custom LED Tape, Custom Extrusion Kit",
			"products-used": [],
			"videos": "https://www.youtube.com/watch?v=abc",
			"quote": "Great.",
			"quote-attribution": "Someone",
			"custom-items": (
				'<p>Wall panel: Powder coated</p><p><img src="' + CDN + 'panel.jpg" alt=""></p>'
				"<p>Bracket: Steel &amp; brass</p>"
			),
		},
	)


def lowlander():
	return item(
		"lowlander-brewing",
		"Lowlander Brewing",
		**{
			"gallery": [image("l1"), image("l2")],
			"series-used": "St. Helens",
			"architect": "Arch",
			"architect-website": "https://arch.example",
			"designer": "Des",
			"contractor": "Con",
			"contractor-website": None,
			"owner": "Own",
		},
	)


def map_item(module, raw, **overrides):
	args = {"series_by_name": SERIES, "product_by_webflow_id": PRODUCTS}
	args.update(overrides)
	return module.map_webflow_item(raw, **args)


class MapCase(unittest.TestCase):
	def setUp(self):
		cm = load_service(MODULE)
		self.module, self.frappe = cm.__enter__()
		self.addCleanup(cm.__exit__, None, None, None)
		from illumenate_lighting.illumenate_lighting.api import gallery_projection

		self.projection = gallery_projection

	def test_skips_boutique_hotel_lounge(self):
		gallery, report = map_item(self.module, item("boutique-hotel-lounge", "Boutique Hotel Lounge"))
		self.assertIsNone(gallery)
		self.assertTrue(any("boutique-hotel-lounge" in line and "skipped" in line for line in report))

	def test_skip_slugs_can_be_overridden(self):
		gallery, _ = map_item(
			self.module, item("boutique-hotel-lounge", "Boutique"), skip_slugs=frozenset()
		)
		self.assertEqual(gallery["slug"], "boutique-hotel-lounge")

	def test_ode_series_is_custom(self):
		# Rei: an item with no series-used text is "Custom", whatever the products' own series.
		self.assertNotIn("series-used", ode()["fieldData"])
		for own in (None, {"rainier-sf": "Rainier"}):
			gallery, report = map_item(self.module, ode(), product_series=own)
			rows = gallery["products_used"]
			self.assertEqual(rows, [{"product": "rainier-sf", "series": "Custom", "note": None}], own)
			self.assertEqual({row["series"] for row in rows}, {"Custom"})
			payload = self.projection.build_payload(gallery, base_url="", product_refs={})
			self.assertEqual(payload["series_used"], ["Custom"])
		self.assertEqual(gallery["featured"], 1)
		self.assertEqual(gallery["gallery_type"], "Healthcare")
		self.assertEqual(gallery["completion_date"], "2025-03-04")
		self.assertEqual(gallery["case_study"], "<p>Case &amp; study</p>")
		self.assertEqual(gallery["seo_description"], "A calm spa.")
		self.assertEqual(gallery["applications"], [{"application": "Cove"}, {"application": "Backlighting"}])
		self.assertEqual(gallery["services_provided"], [{"service": "Takeoff Drawings"}])
		self.assertEqual(gallery["webflow_item_id"], ode()["id"])
		self.assertEqual(report, [])

	def test_product_takes_series_of_same_name(self):
		raw = ode()
		raw["fieldData"]["series-used"] = "Rainier, led tape"
		gallery, _ = map_item(self.module, raw, product_series={"rainier-sf": "Rainier"})
		self.assertEqual(gallery["products_used"], [
			{"product": "rainier-sf", "series": "Rainier", "note": None},
			{"product": None, "series": "LED Tape", "note": None},
		])

	def test_product_series_not_in_text_falls_back_to_its_own_series(self):
		raw = ode()
		raw["fieldData"]["series-used"] = "LED Tape"
		gallery, report = map_item(self.module, raw, product_series={"rainier-sf": "Rainier"})
		self.assertEqual(gallery["products_used"], [
			{"product": "rainier-sf", "series": "Rainier", "note": None},
			{"product": None, "series": "LED Tape", "note": None},
		])
		self.assertEqual(report, [])

	def test_two_products_of_one_series_both_keep_it(self):
		raw = ode()
		raw["fieldData"]["series-used"] = "Rainier"
		raw["fieldData"]["products-used"] = [ODE_PRODUCT, "7" * 24]
		gallery, _ = map_item(
			self.module,
			raw,
			product_by_webflow_id={ODE_PRODUCT: "rainier-sf", "7" * 24: "rainier-wall"},
			product_series={"rainier-sf": "Rainier", "rainier-wall": "Rainier"},
		)
		self.assertEqual([r["series"] for r in gallery["products_used"]], ["Rainier", "Rainier"])

	def test_product_without_series_among_other_series_is_left_out_and_reported(self):
		raw = ode()
		raw["fieldData"]["series-used"] = "LED Tape"
		gallery, report = map_item(self.module, raw)
		self.assertEqual(gallery["products_used"], [{"product": None, "series": "LED Tape", "note": None}])
		self.assertTrue(any("rainier-sf" in line and "left out" in line for line in report), report)
		self.assertTrue(all(row["series"] for row in gallery["products_used"]))

	def test_custom_led_tape_and_extrusion_kit_map_to_custom(self):
		gallery, report = map_item(self.module, holodeck())
		self.assertEqual(gallery["products_used"], [{"product": None, "series": "Custom", "note": None}])
		self.assertEqual(report, [])
		self.assertEqual(gallery["videos"], "https://www.youtube.com/watch?v=abc")
		self.assertEqual(gallery["quote"], "Great.")
		self.assertEqual(gallery["quote_attribution"], "Someone")

	def test_mixed_custom_and_named_series_keep_listed_order(self):
		raw = item(
			"mio-oh-mio-seattle", "Mio Oh Mio Seattle", **{"series-used": "Custom Extrusion Kit, LED Tape"}
		)
		gallery, report = map_item(self.module, raw)
		self.assertEqual([r["series"] for r in gallery["products_used"]], ["Custom", "LED Tape"])
		self.assertEqual(report, [])

	def test_custom_items_parse_with_images(self):
		gallery, _ = map_item(self.module, holodeck())
		self.assertEqual(gallery["custom_items"], [
			{"item_name": "Wall panel", "detail": "Powder coated", "image": CDN + "panel.jpg"},
			{"item_name": "Bracket", "detail": "Steel & brass", "image": None},
		])

	def test_series_text_matched_case_insensitively_and_deduplicated(self):
		raw = lowlander()
		raw["fieldData"]["series-used"] = "st. helens, ST. HELENS, Mystery"
		gallery, report = map_item(self.module, raw)
		self.assertEqual(gallery["products_used"], [{"product": None, "series": "St. Helens", "note": None}])
		self.assertEqual(len(report), 1)
		self.assertIn("Mystery", report[0])

	def test_credit_pairs_become_rows_only_when_filled(self):
		gallery, _ = map_item(self.module, lowlander())
		self.assertEqual(gallery["credits"], [
			{"credit_type": "Architect", "credit_name": "Arch", "website": "https://arch.example"},
			{"credit_type": "Designer", "credit_name": "Des", "website": None},
			{"credit_type": "Contractor", "credit_name": "Con", "website": None},
			{"credit_type": "Owner", "credit_name": "Own", "website": None},
		])
		ode_gallery, _ = map_item(self.module, ode())
		self.assertEqual(
			[row["credit_type"] for row in ode_gallery["credits"]], ["Integrator", "Owner", "Photographer"]
		)

	def test_gallery_rows_keep_order_hero_first(self):
		raw = ode()
		gallery, _ = map_item(self.module, raw)
		alts = [row["alt_text"] for row in gallery["gallery_images"]]
		self.assertEqual(alts, [f"Ode {n}" for n in range(1, 6)])
		self.assertEqual(gallery["gallery_images"][0]["image"], CDN + "ode1.jpg")
		self.assertEqual(len(gallery["gallery_images"]), 5)

	def test_unmapped_product_reported_not_dropped(self):
		raw = ode()
		raw["fieldData"]["products-used"] = [ODE_PRODUCT, "9" * 24]
		gallery, report = map_item(self.module, raw)
		self.assertEqual([r["product"] for r in gallery["products_used"] if r["product"]], ["rainier-sf"])
		self.assertTrue(any("9" * 24 in line for line in report))

	def test_existing_webflow_id_is_kept_for_sync_state(self):
		gallery, _ = map_item(self.module, lowlander())
		self.assertEqual(gallery["webflow_item_id"], lowlander()["id"])

	def test_unknown_values_are_reported(self):
		raw = ode()
		raw["fieldData"].update(
			{"project-type": "Spaceport", "applications": "Cove, Teleport", "services-provided": "Magic"}
		)
		gallery, report = map_item(self.module, raw)
		self.assertIsNone(gallery["gallery_type"])
		self.assertEqual(gallery["applications"], [{"application": "Cove"}])
		self.assertEqual(gallery["services_provided"], [])
		text = "\n".join(report)
		for needle in ("Spaceport", "Teleport", "Magic"):
			self.assertIn(needle, text)

	def test_product_notes_attach_by_name_and_report_unmatched(self):
		raw = ode()
		raw["fieldData"]["product-notes"] = (
			"<p>Rainier SF: White &amp; warm</p><p>Other Thing: nope</p><p>No colon here</p>"
		)
		gallery, report = map_item(self.module, raw, product_names={"rainier-sf": "Rainier SF"})
		self.assertEqual(gallery["products_used"][0]["note"], "White & warm")
		text = "\n".join(report)
		self.assertIn("Other Thing", text)
		self.assertIn("No colon here", text)

	def test_null_and_missing_fields_are_tolerated(self):
		raw = {"id": "a" * 24, "fieldData": {"name": None, "slug": "bare", "gallery": None, "featured": None}}
		gallery, _ = map_item(self.module, raw, series_by_name={})
		self.assertEqual(gallery["gallery_images"], [])
		self.assertEqual(gallery["featured"], 0)
		self.assertEqual(gallery["gallery_title"], "bare")

	def test_no_series_and_no_custom_record_is_reported(self):
		_, report = map_item(self.module, ode(), series_by_name={})
		self.assertTrue(any("Custom" in line for line in report))

	def test_archived_item_is_skipped(self):
		raw = lowlander()
		raw["isArchived"] = True
		gallery, report = map_item(self.module, raw)
		self.assertIsNone(gallery)
		self.assertTrue(report)


class ImportCase(unittest.TestCase):
	def setUp(self):
		self.staff = types.ModuleType(ROOT + ".portal.staff")
		self.staff.require = MagicMock()
		self.inserted = []
		self.files = []
		self.existing = set()
		self.write_calls = []
		self.products = {"rainier-sf": {"series": "Rainier", "product_name": "Rainier SF"}}
		self.sync_rows = {("rainier-sf", "staging2"): ODE_PRODUCT}
		self.publications = {}

	def service(self):
		brand = types.ModuleType(ROOT + ".api.webflow_brand")
		brand.get_default_brand = lambda: "illumenate"
		return load_service(MODULE, {self.staff.__name__: self.staff, brand.__name__: brand})

	def prepare(self, frappe):
		def exists(doctype, filters=None):
			if doctype == "ilL-Webflow-Brand":
				return filters == "staging2"
			if doctype == "ilL-Webflow-Gallery":
				return filters["slug"] in self.existing
			return None

		def get_all(doctype, **kwargs):
			if doctype == "ilL-Attribute-Series":
				return [Record(name=n) for n in SERIES.values()]
			if doctype == "ilL-Webflow-Product":
				return [Record(name=n, **row) for n, row in self.products.items()]
			return []

		def get_value(doctype, filters=None, field=None, *args, **kwargs):
			# Spec 6a order: publication record, then the sync row (any status), then the own field.
			if doctype == "ilL-Product-Publication":
				return next(
					(item for (product, code), item in self.publications.items()
					if filters == {"scope_key": fingerprint([product, code])}),
					None,
				)
			if doctype == "ilL-Child-Webflow-Sync-State" and "sync_status" not in filters:
				return self.sync_rows.get((filters["parent"], filters["brand"]))
			return None

		def get_doc(data):
			doc = Record(copy.deepcopy(data))
			doc.name = data.get("slug")
			doc.append = lambda table, row: doc.setdefault(table, []).append(row)
			doc.insert = lambda **kw: (self.inserted.append(doc), doc)[1]
			doc.save = lambda **kw: doc
			doc.set = lambda key, value: doc.__setitem__(key, value)
			if data["doctype"] == "File":
				doc.insert = lambda **kw: self.attach(doc)
			return doc

		frappe.db.exists.side_effect = exists
		frappe.db.get_value.side_effect = get_value
		frappe.get_all.side_effect = get_all
		frappe.get_doc.side_effect = get_doc
		frappe.delete_doc = MagicMock()
		frappe.get_site_path = lambda *parts: os.path.join(self.tmp, *parts)
		frappe.generate_hash = lambda length=8: "abcd1234"

	def attach(self, doc):
		doc.name = "FILE-%d" % (len(self.files) + 1)
		self.files.append(doc)
		doc["file_url"] = "/files/" + doc["file_name"]
		return doc

	def run_import(self, items, commit, **kwargs):
		import tempfile

		with tempfile.TemporaryDirectory() as tmp, self.service() as (module, frappe):
			self.tmp = tmp
			self.prepare(frappe)
			with patch.object(module, "_download", return_value=b"bytes") as download:
				result = module.import_galleries(items, "staging2", commit, **kwargs)
			self.download = download
			self.frappe = frappe
			self.report_files = [os.path.join(d, f) for d, _, fs in os.walk(tmp) for f in fs]
			return result

	def test_dry_run_writes_nothing(self):
		result = self.run_import(json.dumps([ode(), holodeck()]), 0)
		self.assertEqual(self.inserted, [])
		self.assertEqual(self.files, [])
		self.download.assert_not_called()
		self.assertEqual(result["committed"], 0)
		self.assertEqual(result["would_create"], ["ode-wellness", "holodeck-wall"])
		self.frappe.db.commit.assert_not_called()
		self.staff.require.assert_called_with("catalog")

	def test_commit_creates_gallery_with_sync_state_and_brand_target(self):
		result = self.run_import([ode()], "1")
		self.assertEqual(result["created"], ["ode-wellness"])
		gallery = self.inserted[0]
		self.assertEqual(gallery["sync_targets"], [{
			"brand": "staging2", "webflow_item_id": ode()["id"], "sync_status": "Pending",
		}])
		self.assertEqual(gallery["target_brands"], [{"brand": "staging2", "enabled": 1}])
		self.assertEqual(len(self.files), 5)
		self.assertTrue(all(f["is_private"] == 0 for f in self.files))
		self.assertEqual(
			[r["image"] for r in gallery["gallery_images"]], ["/files/" + f["file_name"] for f in self.files]
		)
		self.assertEqual(self.files[0]["attached_to_name"], "ode-wellness")
		self.assertEqual(len(self.report_files), 1)

	def test_existing_slug_is_never_overwritten(self):
		self.existing.add("ode-wellness")
		result = self.run_import([ode(), lowlander()], 1)
		self.assertEqual(result["created"], ["lowlander-brewing"])
		self.assertIn("ode-wellness: exists, skipped", result["report"])

	def test_download_failure_skips_row_and_still_imports(self):
		import tempfile

		with tempfile.TemporaryDirectory() as tmp, self.service() as (module, frappe):
			self.tmp = tmp
			self.prepare(frappe)
			calls = []

			def flaky(url):
				calls.append(url)
				if url.endswith("ode2.jpg"):
					raise OSError("boom")
				return b"x"

			with patch.object(module, "_download", side_effect=flaky):
				result = module.import_galleries([ode()], "staging2", 1)
		self.assertEqual(result["created"], ["ode-wellness"])
		self.assertEqual(len(self.inserted[0]["gallery_images"]), 4)
		self.assertTrue(any("ode2.jpg" in line for line in result["report"]))

	def test_unknown_brand_is_refused(self):
		with self.service() as (module, frappe):
			self.prepare(frappe)
			with self.assertRaises(ValueError):
				module.import_galleries([ode()], "nope", 0)

	def test_product_known_only_by_its_publication_record_is_mapped(self):
		"""A product staged by the publication process has no Synced sync row (spec 6a)."""
		self.sync_rows = {}
		self.publications = {("rainier-sf", "staging2"): ODE_PRODUCT}
		result = self.run_import([ode()], 0)
		self.assertFalse(any("not synced" in line for line in result["report"]), result["report"])
		with self.service() as (module, frappe):
			self.prepare(frappe)
			_series, by_id, product_series, names = module._lookups("staging2")
		self.assertEqual(by_id, {ODE_PRODUCT: "rainier-sf"})
		self.assertEqual(product_series, {"rainier-sf": "Rainier"})
		self.assertEqual(names, {"rainier-sf": "Rainier SF"})

	def test_skipped_gallery_is_in_report_not_created(self):
		result = self.run_import([item("boutique-hotel-lounge", "Boutique")], 1)
		self.assertEqual(result["created"], [])
		self.assertTrue(any("skipped" in line for line in result["report"]))


class FakeResponse:
	def __init__(self, status=200, content_type="image/jpeg", chunks=(b"abc",)):
		self.status_code = status
		self.headers = {"Content-Type": content_type}
		self._chunks = chunks
		self.closed = False

	def iter_content(self, chunk_size=0):
		return iter(self._chunks)

	def close(self):
		self.closed = True


class DownloadCase(unittest.TestCase):
	def download(self, url, response=None):
		fake = types.ModuleType("requests")
		fake.get = MagicMock(return_value=response or FakeResponse())
		with load_service(MODULE) as (module, _frappe), patch.dict("sys.modules", {"requests": fake}):
			try:
				return module._download(url), fake
			except ValueError as error:
				return error, fake

	def test_cdn_https_image_is_fetched_without_redirects(self):
		result, fake = self.download(CDN + "a.jpg")
		self.assertEqual(result, b"abc")
		kwargs = fake.get.call_args.kwargs
		self.assertFalse(kwargs["allow_redirects"])
		self.assertEqual(kwargs["timeout"], 30)

	def test_non_cdn_host_is_refused_without_a_request(self):
		for url in ("https://evil.example/a.jpg", "https://website-files.com.evil.example/a.jpg"):
			error, fake = self.download(url)
			self.assertIsInstance(error, ValueError)
			fake.get.assert_not_called()

	def test_http_url_is_refused(self):
		error, fake = self.download("http://cdn.prod.website-files.com/a.jpg")
		self.assertIsInstance(error, ValueError)
		fake.get.assert_not_called()

	def test_redirect_is_a_failure(self):
		error, _ = self.download(CDN + "a.jpg", FakeResponse(status=302))
		self.assertIn("302", str(error))

	def test_oversize_body_is_refused(self):
		big = FakeResponse(chunks=(b"x" * (8 * 1024 * 1024),) * 2)
		error, _ = self.download(CDN + "a.jpg", big)
		self.assertIn("15 MB", str(error))
		self.assertTrue(big.closed)

	def test_non_image_content_type_is_refused(self):
		error, _ = self.download(CDN + "a.jpg", FakeResponse(content_type="text/html"))
		self.assertIn("not an image", str(error))


class RichTextAndFailureCase(ImportCase):
	def test_zero_width_paragraphs_make_no_rows_and_no_reports(self):
		for junk in ("<p>&zwj;</p>", "<p>\u200d</p>", "<p>&#8205; &nbsp;</p>"):
			raw = ode()
			raw["fieldData"]["product-notes"] = junk
			raw["fieldData"]["custom-items"] = junk
			with load_service(MODULE) as (module, _frappe):
				gallery, report = map_item(module, raw)
			self.assertEqual(gallery["custom_items"], [], junk)
			self.assertFalse(any("note" in line.lower() for line in report), junk)

	def test_exception_rolls_back_and_deletes_created_files(self):
		with self.service() as (module, frappe):
			self.tmp = "/nonexistent"
			self.prepare(frappe)
			frappe.generate_hash = lambda length=8: "abcd1234"
			with (
				patch.object(module, "_download", return_value=b"x"),
				patch.object(module, "_write_report", return_value="r.txt"),
				patch.object(module, "_discard_files", wraps=module._discard_files) as discard,
			):
				original = frappe.get_doc.side_effect

				def get_doc(data):
					doc = original(data)
					if data["doctype"] == "ilL-Webflow-Gallery":
						doc.save = MagicMock(side_effect=RuntimeError("save broke"))
					return doc

				frappe.get_doc.side_effect = get_doc
				result = module.import_galleries([ode()], "staging2", 1)
		frappe.db.rollback.assert_called_once()
		self.assertEqual(result["created"], [])
		self.assertEqual(frappe.delete_doc.call_count, 5)
		frappe.delete_doc.assert_any_call("File", "FILE-1", ignore_permissions=True, force=True)
		self.assertTrue(any("import failed" in line and "save broke" in line for line in result["report"]))
		frappe.db.commit.assert_not_called()

	def test_all_images_failed_imports_inactive_and_flags(self):
		with self.service() as (module, frappe):
			self.tmp = "/nonexistent"
			self.prepare(frappe)
			with (
				patch.object(module, "_download", side_effect=OSError("down")),
				patch.object(module, "_write_report", return_value="r.txt"),
			):
				result = module.import_galleries([ode()], "staging2", 1)
		self.assertEqual(result["created"], ["ode-wellness"])
		gallery = self.inserted[0]
		self.assertEqual(gallery["gallery_images"], [])
		self.assertEqual(gallery["is_active"], 0)
		self.assertTrue(any("NEEDS ATTENTION: all images failed" in line for line in result["report"]))


if __name__ == "__main__":
	unittest.main()
