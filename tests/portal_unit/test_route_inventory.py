"""Hardening plan 0.5: every portal address the code links to resolves to a page."""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "illumenate_lighting"
PAGES = APP / "templates" / "pages"
LITERAL = re.compile(r"""["'`](/portal(?:/[A-Za-z0-9_.-]*)*/?)""")
SKIP_DIRS = {"node_modules", "dist", "__pycache__"}


def _hooks():
	values = {}
	for node in ast.parse((APP / "hooks.py").read_text(encoding="utf-8")).body:
		if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
			if node.targets[0].id in {"website_route_rules", "website_redirects"}:
				values[node.targets[0].id] = ast.literal_eval(node.value)
	return values["website_route_rules"], values["website_redirects"]


def _pattern(from_route):
	return re.compile("^" + re.sub(r"<[^>]+>", "[^/]+", re.escape(from_route).replace(r"\<", "<").replace(r"\>", ">")) + "$")


def _resolves(path, rules, redirects):
	if any(_pattern(rule["from_route"]).match(path) for rule in rules):
		return True
	return any(re.fullmatch(redirect["source"], path) for redirect in redirects)


def _referenced_paths():
	found = {}
	for source in APP.rglob("*"):
		if source.suffix not in {".py", ".js", ".html"} or SKIP_DIRS & set(source.parts):
			continue
		if source.name.startswith("test_"):
			continue
		for match in LITERAL.finditer(source.read_text(encoding="utf-8", errors="ignore")):
			path = match.group(1)
			# A trailing slash is followed by a dynamic segment (a record name).
			found.setdefault(path + "x" if path.endswith("/") and path != "/portal/" else path, source)
	return found


class RouteInventory(unittest.TestCase):
	def setUp(self):
		self.rules, self.redirects = _hooks()

	def test_every_rule_targets_an_existing_page(self):
		missing = [
			rule["to_route"]
			for rule in self.rules
			if not (PAGES / f"{rule['to_route']}.html").exists() and not (PAGES / f"{rule['to_route']}.py").exists()
		]
		self.assertEqual(missing, [])

	def test_every_referenced_portal_path_resolves(self):
		paths = _referenced_paths()
		self.assertGreater(len(paths), 20)
		unresolved = {path: str(source.relative_to(ROOT)) for path, source in paths.items() if not _resolves(path, self.rules, self.redirects)}
		self.assertEqual(unresolved, {})

	def test_known_dealer_links_resolve(self):
		for path in (
			"/portal/projects/P-1",
			"/portal/schedules/S-1",
			"/portal/quote-requests/QR-1",
			"/portal/quotes/QO-1",
			"/portal/orders/SO-1",
			"/portal/drawings/DR-1",
			"/portal/support/ISS-1",
			"/portal/schedules/S-1/lines/abc/edit",
			"/portal/schedules/S-1/design",
		):
			with self.subTest(path=path):
				self.assertTrue(_resolves(path, self.rules, self.redirects))

	def test_retired_configurator_addresses_redirect(self):
		for path in ("/portal/configure-kit", "/portal/configure-kit/KIT-1", "/portal/configure-webflow/T-1"):
			with self.subTest(path=path):
				self.assertTrue(any(re.fullmatch(r["source"], path) for r in self.redirects))
				self.assertFalse(any(_pattern(r["from_route"]).match(path) for r in self.rules))

	def test_unknown_paths_do_not_resolve(self):
		self.assertFalse(_resolves("/portal/no-such-page", self.rules, self.redirects))


if __name__ == "__main__":
	unittest.main()
