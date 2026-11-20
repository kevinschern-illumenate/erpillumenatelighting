"""The AutoCAD toolkit bundle and layer script (draw-to-quote plan 1.6, 3.11)."""

import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cad_toolkit import package_bundle
from tools.cad_toolkit.build import checklist_pdf, layers
from tools.cad_toolkit.test import mini_lisp


class LayerScript(unittest.TestCase):
	def test_committed_script_matches_the_layer_standard(self):
		committed = layers.TARGET.read_bytes().decode("ascii").replace("\r\n", "\n")
		self.assertEqual(committed, layers.script())

	def test_every_layer_is_made_and_the_issue_layer_never_plots(self):
		data = json.loads(layers.LAYERS.read_text(encoding="utf-8"))
		text = layers.script(data)
		for layer in layers.layer_rows(data):
			self.assertIn(f"_Make\n{layer['name']}\n", text)
		issue = text.split("_Make\nE-ANNO-ISSU\n", 1)[1].split("\n\n", 1)[0]
		self.assertIn("_Plot\n_No\nE-ANNO-ISSU", issue)


class Checklist(unittest.TestCase):
	def test_checklist_items_and_committed_pdf(self):
		items = checklist_pdf.blocks(checklist_pdf.SOURCE.read_text(encoding="utf-8"))
		self.assertEqual(items[0][0], "title")
		self.assertEqual(sum(1 for kind, _text in items if kind == "item"), 13)
		self.assertIn("ILM-TAPE-<template code>", next(text for kind, text in items if text.startswith("5.")))
		self.assertTrue(checklist_pdf.TARGET.read_bytes().startswith(b"%PDF"))


class Bundle(unittest.TestCase):
	def test_bundle_layout_manifest_and_lisp(self):
		with tempfile.TemporaryDirectory() as folder:
			bundle, archive = package_bundle.build(folder)
			manifest = ET.parse(bundle / "PackageContents.xml").getroot()
			entry = manifest.find("./Components/ComponentEntry")
			self.assertEqual(entry.get("ModuleName"), "./Contents/ilLumenate.lsp")
			self.assertEqual(entry.get("LoadOnAutoCADStartup"), "True")
			commands = {node.get("Global") for node in manifest.iter("Command")}
			lisp = (bundle / "Contents/ilLumenate.lsp").read_text(encoding="ascii")
			defined = {name.upper() for name in package_bundle.COMMANDS}
			for name in defined:
				self.assertIn(f"(defun c:{name} ", lisp, name)
			self.assertEqual(commands, defined)
			# The whole bundle parses and loads (defuns and data only at top level).
			interp = mini_lisp.Interpreter()
			interp.set("getvar", lambda name: None)
			interp.run(lisp.replace('(princ (strcat "\\nilLumenate CAD toolkit " *il-version* " loaded. Type ILHELP."))', ""))
			self.assertEqual(interp.get("*il-version*"), package_bundle.version())
			self.assertTrue(interp.get("*il-asset-blocks*"))
			with zipfile.ZipFile(archive) as handle:
				self.assertIn("ilLumenate.bundle/Contents/ilLumenate.lsp", handle.namelist())

	def test_every_command_is_listed(self):
		lisp = package_bundle.joined_lisp()
		defined = {line.split("(defun c:", 1)[1].split(" ", 1)[0] for line in lisp.splitlines() if line.startswith("(defun c:")}
		self.assertEqual(defined, set(package_bundle.COMMANDS))


if __name__ == "__main__":
	unittest.main()
