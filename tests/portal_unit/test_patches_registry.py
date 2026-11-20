"""patches.txt must parse the way `bench migrate` parses it: a duplicate entry stops every migrate."""

import configparser
import unittest
from pathlib import Path

PATCHES = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "patches.txt"


class PatchesRegistryTest(unittest.TestCase):
	def test_no_patch_is_listed_twice_in_a_section(self):
		parser = configparser.ConfigParser(allow_no_value=True, delimiters=("=",))
		parser.optionxform = str
		try:
			parser.read_string(PATCHES.read_text())
		except configparser.DuplicateOptionError as error:
			self.fail(f"patches.txt lists a patch twice: {error.option} (section {error.section})")
		self.assertEqual(set(parser.sections()), {"pre_model_sync", "post_model_sync"})

	def test_every_listed_patch_has_a_module(self):
		parser = configparser.ConfigParser(allow_no_value=True, delimiters=("=",))
		parser.optionxform = str
		parser.read_string(PATCHES.read_text())
		patches_dir = PATCHES.parent / "patches"
		for section in parser.sections():
			for entry in parser.options(section):
				dotted = entry.split("#")[0].strip()
				if not dotted.startswith("illumenate_lighting.patches."):
					continue
				module = dotted.rsplit(".", 1)[1]
				self.assertTrue((patches_dir / f"{module}.py").exists(), f"{module} is listed but has no module")


if __name__ == "__main__":
	unittest.main()
