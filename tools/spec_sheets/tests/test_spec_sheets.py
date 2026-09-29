"""Spec sheet generation contracts: measurement, page primitives, renderer and InDesign fidelity.

The fidelity test renders the St. Helens page 1 fixture with headless Chromium and
compares it with the InDesign golden. It needs ``ILL_SPEC_SHEET_CHROMIUM`` (a
Chromium or Chrome executable) and PyMuPDF; it is skipped without them.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from illumenate_lighting.illumenate_lighting.api.spec_sheets import render, tokens
from illumenate_lighting.illumenate_lighting.api.spec_sheets.pages import build_html
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import (
	DirectoryAssets,
	Page,
	svg_size,
)
from illumenate_lighting.illumenate_lighting.api.spec_sheets.text import text_width

FIXTURE = ROOT / "illumenate_lighting/illumenate_lighting/api/spec_sheets/fixtures/st_helens_sf_sw"
GOLDEN_CONFIG = ROOT / "tests/fixtures/spec_sheets/st_helens_sf_sw/fidelity.json"


def _chromium():
	executable = os.environ.get(render.CHROMIUM_ENV)
	return executable if executable and (shutil.which(executable) or Path(executable).is_file()) else None


def _pymupdf():
	try:
		import pymupdf

		return pymupdf
	except ImportError:
		return None


class TextWidthTest(unittest.TestCase):
	def test_widths_match_indesign_for_untracked_text(self):
		# Widths of spans in the golden PDF, which use no tracking.
		self.assertAlmostEqual(
			text_width("PO BOX 297, Bothell, WA 98041  ", "Poppins-Light", 7), 105.01, delta=0.02
		)
		self.assertAlmostEqual(text_width("Static White", "Manrope-Bold", 20), 120.89, delta=0.02)
		self.assertAlmostEqual(text_width("031026RY", "Poppins-Light", 7), 31.23, delta=0.02)

	def test_kerning_and_standard_ligatures_are_applied(self):
		plain = text_width("W", "Manrope-SemiBold", 100) + text_width("a", "Manrope-SemiBold", 100)
		self.assertLess(text_width("Wa", "Manrope-SemiBold", 100), plain)
		separate = 2 * text_width("t", "Manrope-SemiBold", 100)
		self.assertNotAlmostEqual(text_width("tt", "Manrope-SemiBold", 100), separate, places=2)

	def test_tracking_is_per_character_in_thousandths_of_an_em(self):
		base = text_width("ABC", "Manrope-Regular", 8)
		self.assertAlmostEqual(text_width("ABC", "Manrope-Regular", 8, tracking=50), base + 3 * 0.4, places=6)

	def test_unsupported_characters_fail_loudly(self):
		with self.assertRaisesRegex(ValueError, "do not cover"):
			text_width("中", "Poppins-Light", 7)


class PagePrimitiveTest(unittest.TestCase):
	def setUp(self):
		self.page = Page(tokens.brand_colors(), DirectoryAssets(FIXTURE / "assets"))

	def test_text_is_escaped_and_positioned_by_baseline(self):
		self.page.text(10, 20.5, "<Clip & Pivot>", "spec_value", anchor="middle")
		svg = self.page.svg()
		self.assertIn('x="10" y="20.5" text-anchor="middle"', svg)
		self.assertIn("&lt;Clip &amp; Pivot&gt;", svg)
		self.assertIn("Poppins-Light", self.page.fonts)

	def test_fpo_magenta_artwork_is_rejected(self):
		from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import reject_fpo

		for marked in (
			b'<path fill="#EC008C"/>',
			b"<g style='fill:#ff00ff'/>",
			b'<path fill="rgb(236, 0, 140)"/>',
		):
			with self.assertRaisesRegex(ValueError, "FPO"):
				reject_fpo(marked, "drawing.svg")
		reject_fpo(b'<path fill="#231f20"/><path fill="#0b598d"/>', "drawing.svg")

	def test_fixture_artwork_has_no_fpo_marks(self):
		from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import reject_fpo

		for path in (FIXTURE / "assets").glob("*.svg"):
			reject_fpo(path.read_bytes(), path.name)

	def test_svg_natural_size_uses_points(self):
		self.assertEqual(svg_size(b'<svg xmlns="x" width="24.6" height="24.6pt">'), (24.6, 24.6))
		with self.assertRaises(ValueError):
			svg_size(b'<svg width="2in" height="1in">')

	def test_assets_cannot_escape_their_directory(self):
		with self.assertRaisesRegex(ValueError, "outside"):
			DirectoryAssets(FIXTURE / "assets").get("../model.json")

	def test_model_builds_one_self_contained_page(self):
		model = json.loads((FIXTURE / "model.json").read_text(encoding="utf-8"))
		html = build_html(model, DirectoryAssets(FIXTURE / "assets"))
		self.assertEqual(html.count('<svg class="page"'), 1)
		self.assertNotIn("/files/", html)
		self.assertIn("@page{size:612pt 792pt;margin:0}", html)


class SpecLineTest(unittest.TestCase):
	def test_every_product_line_has_ordered_stops(self):
		for code in ("SW", "DW", "TW", "FS", "CC", "PS", "OTHER"):
			stops = tokens.spec_line_stops(code)
			offsets = [offset for _, _, offset in stops]
			self.assertEqual((offsets[0], offsets[-1]), (0.0, 100.0), code)
			self.assertEqual(offsets, sorted(offsets), code)
			for color, opacity, _ in stops:
				self.assertRegex(color, r"^#[0-9a-f]{6}$")
				self.assertTrue(0 < opacity <= 1)

	def test_static_white_line_is_the_cct_swatches(self):
		# 27K -> 30K -> 35K -> 40K, as built in InDesign.
		stops = tokens.spec_line_stops("SW")
		self.assertEqual(stops[0][0], "#ffc35a")
		self.assertEqual(stops[-1][0], "#f6fbff")

	def test_unknown_line_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "Unknown spec line"):
			tokens.spec_line_stops("XX")

	def test_fit_reproduces_a_gradient_within_tolerance(self):
		from tools.spec_sheets.extract_indesign import fit_stops

		row = [(round(255 * x / 99), 0, 255 - round(255 * x / 99), 255) for x in range(100)]
		row += [(255, round(255 * x / 99), 0, 255) for x in range(100)]
		stops = fit_stops(row, 1.0)
		self.assertLessEqual(len(stops), 4)
		self.assertEqual((stops[0], stops[-1]), (0, 199))

	def test_mirrored_gradient_reverses_offsets(self):
		page = Page(tokens.brand_colors(), DirectoryAssets(FIXTURE / "assets"))
		page.gradient_rect(0, 0, 10, 1, [("#000000", 1.0, 0.0), ("#ffffff", 0.5, 30.0)], reverse=True)
		svg = page.svg()
		self.assertIn('<stop offset="70%" stop-color="#ffffff" stop-opacity="0.5"/>', svg)
		self.assertIn('<stop offset="100%" stop-color="#000000"/>', svg)


class ChromiumResolutionTest(unittest.TestCase):
	def test_environment_override_wins(self):
		previous = os.environ.get(render.CHROMIUM_ENV)
		os.environ[render.CHROMIUM_ENV] = "/opt/example/chrome"
		try:
			self.assertEqual(render.find_chromium(), "/opt/example/chrome")
		finally:
			if previous is None:
				del os.environ[render.CHROMIUM_ENV]
			else:
				os.environ[render.CHROMIUM_ENV] = previous

	def test_pinned_build_is_a_version_that_embeds_web_fonts(self):
		# Chrome 136 and earlier embed @font-face fonts as Type 3 glyph procedures.
		self.assertGreaterEqual(int(render.PINNED_CHROMIUM["version"].split(".")[0]), 137)
		self.assertRegex(render.PINNED_CHROMIUM["sha256"], r"^[0-9a-f]{64}$")
		self.assertTrue(render.PINNED_CHROMIUM["url"].startswith("https://storage.googleapis.com/"))


class SecurityPolicyTest(unittest.TestCase):
	def test_policy_is_first_in_head_and_blocks_scripts_and_network(self):
		html = render.with_security_policy("<!doctype html><html><head><title>x</title></head></html>")
		self.assertIn('<head><meta http-equiv="Content-Security-Policy"', html)
		self.assertIn("script-src 'none'", html)
		self.assertIn("img-src data:", html)

	def test_html_without_head_is_rejected(self):
		with self.assertRaises(render.RenderError):
			render.with_security_policy("<p>no head</p>")


@unittest.skipUnless(_chromium() and _pymupdf(), "needs ILL_SPEC_SHEET_CHROMIUM and PyMuPDF")
class FidelityTest(unittest.TestCase):
	def test_st_helens_page_one_matches_indesign_golden(self):
		from tools.spec_sheets.fidelity import compare, extract_words
		from tools.spec_sheets.render_fixture import render_fixture

		report_dir = ROOT / ".tools/spec-sheet-fidelity/st_helens_sf_sw"
		with tempfile.TemporaryDirectory() as workdir:
			generated = Path(workdir, "st_helens_p1.pdf")
			render_fixture(FIXTURE / "model.json", generated)
			result = compare(GOLDEN_CONFIG, generated, report_dir)
			page = _pymupdf().open(generated)[0]
			text = " ".join(word.text for word in extract_words(page))
			# Real TrueType fonts, not Type 3 glyph procedures (Chrome <= 136 with web fonts).
			fonts = {font[3].split("+")[-1] for font in page.get_fonts()}
		self.assertTrue(result["passed"], json.dumps(result["words"]["failures"][:10], indent=1))
		self.assertEqual(result["words"]["matched"], result["words"]["golden_words"])
		self.assertIn("sales@ilLumenate.lighting", text)
		self.assertTrue({"Manrope-Bold", "Poppins-Light"} <= fonts, fonts)

	def test_scripts_and_external_resources_do_not_run(self):
		html = (
			"<!doctype html><html><head></head><body><p id=t>static</p>"
			"<img src='https://example.com/x.png'><script>document.getElementById('t').textContent='ran'</script>"
			"</body></html>"
		)
		page = _pymupdf().open(stream=render.render_pdf(html))[0]
		self.assertIn("static", page.get_text())
		self.assertNotIn("ran", page.get_text())


if __name__ == "__main__":
	unittest.main()
