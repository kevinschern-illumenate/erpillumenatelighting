"""Plan 8.3: every portal badge tone meets WCAG 2.2 AA text contrast (4.5:1).

Badges carry status text at 11-12px, so the large-text 3:1 allowance never applies.
Colours come from the --ill-* tokens, read straight from the stylesheets.
"""

import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parents[2] / "illumenate_lighting/public/css"
AA_TEXT = 4.5


def tokens():
	values = {}
	for match in re.finditer(r"--(ill-[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b", (CSS / "portal.css").read_text()):
		values[match.group(1)] = match.group(2)
	return values


def luminance(hex_colour):
	channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
	linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
	return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
	high, low = sorted((luminance(first), luminance(second)), reverse=True)
	return (high + 0.05) / (low + 0.05)


RULE = re.compile(
	r"(?P<selector>[^{}]*\.(?:ill-)?badge-[\w-]+[^{}]*)\{\s*background(?:-color)?:\s*(?P<bg>var\(--[\w-]+\)|#[0-9A-Fa-f]{3,6})"
	r";\s*color:\s*(?P<fg>var\(--[\w-]+\)|#[0-9A-Fa-f]{3,6})"
)


def colour(value, palette):
	if value.startswith("var("):
		return palette[value[6:-1]]
	if len(value) == 4:
		return "#" + "".join(ch * 2 for ch in value[1:])
	return value


def badge_rules():
	rules = []
	for name in ("_portal_brand.scss", "portal.css", "pages/_schedule.scss"):
		for match in RULE.finditer((CSS / name).read_text()):
			rules.append((name, " ".join(match.group("selector").split()), match.group("bg"), match.group("fg")))
	return rules


class BadgeContrast(unittest.TestCase):
	def test_contrast_maths_matches_the_wcag_reference_points(self):
		self.assertAlmostEqual(contrast("#000000", "#FFFFFF"), 21.0, places=2)
		self.assertAlmostEqual(contrast("#777777", "#FFFFFF"), 4.48, places=2)

	def test_every_badge_colour_pair_meets_aa_for_text(self):
		palette = tokens()
		rules = badge_rules()
		self.assertGreaterEqual(len(rules), 10, "the badge rules moved; update this test's search")
		for source, selector, bg, fg in rules:
			with self.subTest(source=source, selector=selector):
				ratio = contrast(colour(bg, palette), colour(fg, palette))
				self.assertGreaterEqual(ratio, AA_TEXT, f"{selector}: {ratio:.2f}:1")

	def test_every_server_badge_tone_has_a_styled_rule(self):
		status = (CSS.parents[1] / "illumenate_lighting/portal/status.py").read_text()
		tones = set(re.findall(r'"(\w+)"', re.search(r"BADGE_TONES = frozenset\(\{([^}]*)\}\)", status).group(1)))
		styled = {
			tone
			for _source, selector, _bg, _fg in badge_rules()
			for tone in re.findall(r"\.badge-(\w+)", selector)
		}
		self.assertEqual(tones - styled, set())


if __name__ == "__main__":
	unittest.main()
