"""Moving to main: the published_on backfill rules (plan Phase 5, 10.4)."""

import unittest

from test_services import ROOT, load_service


class Backfill(unittest.TestCase):
	def rows(self, products, sync_rows=None, publications=None):
		with load_service(ROOT + ".webflow_promotion") as (module, _frappe):
			return module.backfill_rows(products, sync_rows or {}, publications or {}, "illumenate")

	def test_public_products_with_an_item_are_marked_published(self):
		products = [
			{"name": "kit-ra01", "webflow_status": "Published", "webflow_item_id": "a" * 24, "brands": []},
			{"name": "kit-ra02", "webflow_status": "Discontinued", "brands": ["illumenate"]},
		]
		sync = {
			("kit-ra02", "illumenate"): {"webflow_item_id": "b" * 24, "last_synced_at": "2026-10-01 10:00:00"}
		}
		publications = {("kit-ra02", "illumenate"): {"name": "P2", "published_on": None}}
		rows = self.rows(products, sync, publications)
		self.assertEqual(
			[(row["product"], row["action"]) for row in rows], [("kit-ra01", "create"), ("kit-ra02", "set")]
		)
		self.assertEqual(rows[1]["published_on"], "2026-10-01 10:00:00")
		self.assertEqual(rows[0]["item"], "a" * 24)  # the legacy item ID counts for the default brand

	def test_drafts_items_missing_or_already_set_are_left_alone(self):
		products = [
			{"name": "draft", "webflow_status": "Webflow Draft", "webflow_item_id": "a" * 24, "brands": []},
			{"name": "no-item", "webflow_status": "Published", "brands": ["illumenate"]},
			{"name": "done", "webflow_status": "Published", "webflow_item_id": "c" * 24, "brands": []},
			{
				"name": "other-brand",
				"webflow_status": "Published",
				"webflow_item_id": "d" * 24,
				"brands": ["lighting_206"],
			},
		]
		publications = {("done", "illumenate"): {"name": "P", "published_on": "2026-09-01"}}
		rows = self.rows(products, publications=publications)
		self.assertEqual(
			[(row["product"], row["action"]) for row in rows],
			[("no-item", "skip"), ("done", "already"), ("other-brand", "skip")],
		)


class History(unittest.TestCase):
	def test_job_rows_read_plainly(self):
		with load_service(ROOT + ".publication_history") as (module, _frappe):
			done = module.job_row(
				{
					"name": "J1",
					"operation": "STAGE",
					"state": "COMPLETE",
					"requested_by": "auto",
					"started_by": "owner",
				}
			)
			self.assertEqual(
				(done["what"], done["result"], done["ok"], done["by"]), ("Sync", "Done", True, "owner")
			)
			retry = module.job_row(
				{"operation": "PUBLISH", "state": "FAILED", "next_attempt_on": "x", "last_error": "429"}
			)
			self.assertEqual(
				(retry["what"], retry["result"], retry["error"]), ("Publish", "Failed, retrying", "429")
			)
			old = module.job_row({"operation": "STAGE", "state": "SUPERSEDED", "requested_by": "a"})
			self.assertEqual((old["result"], old["by"]), ("Replaced by a newer save", "a"))


if __name__ == "__main__":
	unittest.main()
