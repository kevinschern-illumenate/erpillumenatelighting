"""Hardening plan 0.3: one manifest for the local test tools, matching CI."""

import re
import unittest
from pathlib import Path

try:
	import tomllib
except ModuleNotFoundError:  # Python 3.10 has no tomllib; CI runs 3.11+.
	tomllib = None

ROOT = Path(__file__).resolve().parents[2]


def _names(requirements):
	return {re.split(r"[<>=~! \[]", requirement, maxsplit=1)[0].lower() for requirement in requirements}


@unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
class DevDependencies(unittest.TestCase):
	def test_test_extra_matches_the_ci_install_step(self):
		project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
		extra = _names(project["optional-dependencies"]["test"])
		workflow = (ROOT / ".github/workflows/b2b-contracts.yml").read_text(encoding="utf-8")
		line = next(row for row in workflow.splitlines() if "python -m pip install ruff" in row)
		self.assertEqual(extra, _names(line.split("pip install", 1)[1].split()))

	def test_runtime_dependencies_are_part_of_the_test_extra(self):
		project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
		self.assertLessEqual(_names(project["dependencies"]), _names(project["optional-dependencies"]["test"]))


if __name__ == "__main__":
	unittest.main()
