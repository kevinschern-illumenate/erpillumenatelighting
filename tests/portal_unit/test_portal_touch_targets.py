"""Plan 8.4: touch devices get 44px targets on the portal's interactive controls."""

import re
import unittest
from pathlib import Path

SCSS = Path(__file__).resolve().parents[2] / "illumenate_lighting/public/css/_portal_components.scss"


def coarse_block(text):
	start = text.index("@media (pointer: coarse)")
	depth, i = 0, text.index("{", start)
	for j in range(i, len(text)):
		depth += {"{": 1, "}": -1}.get(text[j], 0)
		if depth == 0:
			return text[i : j + 1]
	raise AssertionError("unbalanced @media (pointer: coarse) block")


class TouchTargetTests(unittest.TestCase):
	def setUp(self):
		self.block = coarse_block(SCSS.read_text(encoding="utf8"))

	def test_controls_reach_44px_on_coarse_pointers(self):
		rule = re.search(r"([^{}]+)\{\s*min-height:\s*44px;", self.block)
		self.assertIsNotNone(rule)
		selectors = {s.strip() for s in rule.group(1).split(",")}
		for selector in (".btn", ".dropdown-item", ".nav-link", ".drag-handle-btn", ".ill-pager a", "input.form-control"):
			self.assertIn(selector, selectors)

	def test_rule_is_scoped_to_the_portal_and_keeps_block_buttons_full_width(self):
		self.assertIn('body:is([data-path^="portal"]', self.block)
		self.assertIn(".btn:not(.btn-block)", self.block)
		self.assertNotRegex(self.block, r"(?m)^\s*\.btn,\s*\n\s*\.drag-handle-btn")


if __name__ == "__main__":
	unittest.main()
