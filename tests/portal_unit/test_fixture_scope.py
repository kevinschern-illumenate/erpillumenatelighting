"""Fixtures overwrite their records on every migrate, so only app-owned config belongs there."""

import ast
import unittest
from pathlib import Path

APP_OWNED = {"Role", "Workflow", "Custom Field", "Workspace", "Number Card"}


def fixture_entries():
	tree = ast.parse(Path("illumenate_lighting/hooks.py").read_text())
	node = next(
		n for n in tree.body if isinstance(n, ast.Assign) and any(t.id == "fixtures" for t in n.targets)
	)
	return ast.literal_eval(node.value)


class FixtureScope(unittest.TestCase):
	def test_only_app_owned_config_is_listed(self):
		# Team-maintained data here would be reset on every migrate once exported.
		# Seed it with an insert-if-missing patch instead.
		self.assertLessEqual({entry["dt"] for entry in fixture_entries()}, APP_OWNED)

	def test_every_entry_is_filtered_to_app_records(self):
		for entry in fixture_entries():
			with self.subTest(entry["dt"]):
				self.assertTrue(entry.get("filters"))


if __name__ == "__main__":
	unittest.main()
