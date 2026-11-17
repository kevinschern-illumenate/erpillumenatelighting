"""copy_minimum_bend_to_side_bend uses frappe.qb, not f-string SQL — plan item 1.5."""

import pathlib
import unittest
from unittest.mock import MagicMock

from test_services import load_service

PATCH = "illumenate_lighting.patches.copy_minimum_bend_to_side_bend"
SOURCE = pathlib.Path(__file__).resolve().parents[2] / "illumenate_lighting" / "patches" / "copy_minimum_bend_to_side_bend.py"


class Expr(str):
	"""Renders query-builder expressions as SQL-ish text for assertions."""

	def isnull(self):
		return Expr(f"{self} IS NULL")

	def isnotnull(self):
		return Expr(f"{self} IS NOT NULL")

	def __eq__(self, other):
		return Expr(f"{self} = {other}")

	def __ne__(self, other):
		return Expr(f"{self} != {other}")

	def __or__(self, other):
		return Expr(f"({self} OR {other})")

	__hash__ = str.__hash__


class Table:
	def __init__(self, name):
		self.name = name

	def __getattr__(self, field):
		return Expr(field)


class Update:
	def __init__(self, table, log):
		self.query = {"table": table.name, "set": [], "where": []}
		log.append(self.query)

	def set(self, field, value):
		self.query["set"].append((str(field), str(value)))
		return self

	def where(self, criterion):
		self.query["where"].append(str(criterion))
		return self

	def run(self):
		self.query["ran"] = True


class BendPatch(unittest.TestCase):
	def run_patch(self, has_column):
		with load_service(PATCH) as (patch, frappe):
			log = []
			frappe.qb = MagicMock()
			frappe.qb.DocType = Table
			frappe.qb.update = lambda table: Update(table, log)
			frappe.db.has_column.side_effect = has_column
			patch.execute()
			return log, frappe

	def test_copies_only_non_zero_generic_values_into_empty_side_bend(self):
		log, frappe = self.run_patch(lambda doctype, column: True)
		self.assertEqual([q["table"] for q in log], ["ilL-Fixture-Template", "ilL-Tape-Neon-Template"])
		for query in log:
			self.assertTrue(query["ran"])
			self.assertEqual(query["set"], [("minimum_side_bend_diameter_mm", "minimum_bend_diameter_mm")])
			self.assertEqual(
				query["where"],
				[
					"minimum_bend_diameter_mm IS NOT NULL",
					"minimum_bend_diameter_mm != 0",
					"(minimum_side_bend_diameter_mm IS NULL OR minimum_side_bend_diameter_mm = 0)",
				],
			)
		frappe.db.commit.assert_called_once_with()
		frappe.db.sql.assert_not_called()

	def test_missing_columns_skip_the_doctype(self):
		log, _ = self.run_patch(
			lambda doctype, column: not (doctype == "ilL-Tape-Neon-Template" and column == "minimum_side_bend_diameter_mm")
		)
		self.assertEqual([q["table"] for q in log], ["ilL-Fixture-Template"])
		log, _ = self.run_patch(lambda doctype, column: False)
		self.assertEqual(log, [])

	def test_no_interpolated_sql(self):
		source = SOURCE.read_text(encoding="utf-8")
		self.assertNotIn("frappe.db.sql", source)
		self.assertNotIn('f"""', source)


if __name__ == "__main__":
	unittest.main()
