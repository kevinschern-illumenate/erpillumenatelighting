"""Is Discontinued follows the status table (plan 4.3 rows 10 to 17, 4.8, D48)."""

import unittest

from test_services import ROOT, load_service


class Discontinued(unittest.TestCase):
	def test_the_status_table(self):
		with load_service(ROOT + ".webflow_state") as (module, _frappe):
			cases = [
				# (webflow status, template status, published before, expected)
				("Discontinued", "Active + Live", True, True),  # row 10
				("Discontinued", "Active", False, True),
				("Published", "Active + Live", True, False),  # row 9
				("Webflow Draft", "Internal Only", True, True),  # row 12
				("Webflow Draft", "Internal Only", False, False),  # row 13
				("Published", "Discontinued", True, True),  # row 14
				("Published", "Discontinued", False, False),  # row 15
				("Archived", "Active + Live", True, True),  # row 11, owner 2026-11-02
				("Archived", "Active + Live", False, False),
				("Discontinued", "Archived", True, False),  # row 16
				("Webflow Draft", None, False, False),
			]
			for status, template, published, expected in cases:
				with self.subTest(status=status, template=template, published=published):
					self.assertEqual(module.discontinued(status, template, published), expected)


if __name__ == "__main__":
	unittest.main()
