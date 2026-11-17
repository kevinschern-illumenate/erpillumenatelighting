"""Plan 8.1: schedule.html's repeated inline styles live in pages/_schedule.scss classes."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "illumenate_lighting"
MOVED = {
	"font-weight:normal;": "ill-weight-normal",
	"font-size:0.6em;vertical-align:middle;": "ill-stock-dot",
	"padding:2px 4px;": "ill-tight",
}


class ScheduleInlineStyles(unittest.TestCase):
	def test_moved_styles_do_not_come_back_inline(self):
		html = (ROOT / "templates/pages/schedule.html").read_text(encoding="utf8")
		scss = (ROOT / "public/css/pages/_schedule.scss").read_text(encoding="utf8")
		for style, cls in MOVED.items():
			with self.subTest(cls=cls):
				self.assertNotIn(f'style="{style}"', html)
				self.assertIn(cls, html)
				self.assertIn(f".{cls}", scss)


if __name__ == "__main__":
	unittest.main()
