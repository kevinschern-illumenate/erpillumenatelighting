"""Readable part-number Item codes for immutable linear and tape/neon builds."""

import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

HASH = "ab" * 32
OTHER_HASH = "cd" * 32


def build(doctype="ilL-Configured-Tape-Neon", name="ILL-CTN-00001", config_hash=HASH, **extra):
	return Record(doctype=doctype, name=name, config_hash=config_hash, build_schema_version=2, **extra)


def items(frappe, owners):
	"""Items that exist, each mapped to the configured record its link field names."""

	def get_value(doctype, key, field):
		if isinstance(key, dict):  # The Item whose link field names this build.
			(owner,) = key.values()
			return next((code for code, linked in owners.items() if linked == owner), None)
		return owners.get(key)

	frappe.db.exists.side_effect = lambda doctype, code: code in owners
	frappe.db.get_value.side_effect = get_value


class ItemCodeAllocation(unittest.TestCase):
	def test_first_build_takes_the_part_number(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, frappe):
			items(frappe, {})
			self.assertEqual(artifacts.build_item_code(build(), "NEON-24V-150-E2-C"), "NEON-24V-150-E2-C")

	def test_other_builds_sharing_a_part_number_get_a_hash_suffix(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, frappe):
			items(frappe, {"PN": "ILL-CTN-00007"})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "PN-ABABAB")
			items(frappe, {"PN": "ILL-CTN-00007", "PN-ABABAB": "ILL-CTN-00008"})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "PN-ABABABABABAB")
			items(frappe, {"PN": "A", "PN-ABABAB": "B", "PN-ABABABABABAB": "C"})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "ILL-TN-" + HASH)

	def test_an_existing_item_is_reused_only_by_its_own_build(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, frappe):
			items(frappe, {"PN": "ILL-CTN-00001"})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "PN")
			items(frappe, {"PN": "ILL-CTN-00007", "PN-ABABAB": "ILL-CTN-00001"})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "PN-ABABAB")
			# A build that already has a legacy build-ID Item keeps it.
			items(frappe, {"ILL-TN-" + HASH: "ILL-CTN-00001"})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "ILL-TN-" + HASH)
			# A stock Item that happens to share the code links to no build.
			items(frappe, {"PN": None})
			self.assertEqual(artifacts.build_item_code(build(), "PN"), "PN-ABABAB")

	def test_missing_or_unusable_part_numbers_fall_back_to_the_build_id(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, frappe):
			items(frappe, {})
			linear = build("ilL-Configured-Fixture", "ILL-CF-" + HASH)
			self.assertEqual(artifacts.build_item_code(linear, None), "ILL-CF-" + HASH)
			self.assertEqual(artifacts.build_item_code(build(), "  "), "ILL-TN-" + HASH)
			self.assertEqual(artifacts.build_item_code(build(), "A" * 141), "ILL-TN-" + HASH)
			self.assertEqual(artifacts.build_item_code(build(), "PN<script>"), "ILL-TN-" + HASH)
			with self.assertRaisesRegex(ValueError, "complete build hash"):
				artifacts.build_item_code(build(config_hash="short"), "PN")


class ItemOwnership(unittest.TestCase):
	def test_legacy_hash_codes_and_back_linked_items_belong_to_their_build(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, frappe):
			items(frappe, {"PN": "ILL-CTN-00001", "FOREIGN": "ILL-CTN-00009"})
			doc = build()
			self.assertTrue(artifacts.item_belongs_to_build("ILL-TN-" + HASH, doc))
			self.assertTrue(artifacts.item_belongs_to_build("PN", doc))
			self.assertFalse(artifacts.item_belongs_to_build("FOREIGN", doc))
			self.assertFalse(artifacts.item_belongs_to_build("ILL-TN-" + OTHER_HASH, doc))
			self.assertFalse(artifacts.item_belongs_to_build(None, doc))


@contextmanager
def generator():
	stub = types.SimpleNamespace(snapshot=lambda doc: {"components": [{"item_code": "TAPE"}]})
	with load_service(ROOT + ".api.build_artifacts") as (artifacts, _):
		with load_service(
			ROOT + ".api.manufacturing_generator",
			{
				ROOT + ".api.build_artifacts": artifacts,
				ROOT + ".api.linear_build": stub,
				ROOT + ".api.tape_neon_build": stub,
			},
		) as (engine, frappe):
			artifacts.frappe = frappe
			with patch.object(artifacts, "ensure_bom", MagicMock(return_value={"success": True})) as ensure:
				yield engine, frappe, ensure, artifacts


class BuildGuards(unittest.TestCase):
	def test_linear_bom_accepts_the_builds_own_readable_item_only(self):
		with generator() as (engine, frappe, ensure, _):
			fixture = build("ilL-Configured-Fixture", "ILL-CF-" + HASH)
			items(frappe, {"ILL-SH01-120-C": fixture.name, "FOREIGN": "ILL-CF-" + OTHER_HASH})
			self.assertTrue(engine._create_or_get_bom(fixture, "ILL-SH01-120-C")["success"])
			self.assertEqual(ensure.call_args.args[1], "ILL-SH01-120-C")
			self.assertTrue(engine._create_or_get_bom(fixture, "ILL-CF-" + HASH)["success"])
			frappe.throw = MagicMock(side_effect=ValueError("mismatch"))
			with self.assertRaises(ValueError):
				engine._create_or_get_bom(fixture, "FOREIGN")

	def test_tape_neon_bom_accepts_the_builds_own_readable_item_only(self):
		with generator() as (engine, frappe, _, artifacts):
			with load_service(
				ROOT + ".api.tape_neon_bom",
				{ROOT + ".api.manufacturing_generator": engine, ROOT + ".api.build_artifacts": artifacts},
			) as (bom, _):
				doc = build()
				items(frappe, {"NEON-150-C": doc.name, "FOREIGN": "ILL-CTN-00009"})
				bom.build_tape_neon_bom_items = lambda configured: [{"item_code": "TAPE"}]
				self.assertTrue(bom.create_or_get_tape_neon_bom(doc, "NEON-150-C")["success"])
				self.assertTrue(bom.create_or_get_tape_neon_bom(doc, "ILL-TN-" + HASH)["success"])
				with self.assertRaisesRegex(ValueError, "build identity"):
					bom.create_or_get_tape_neon_bom(doc, "FOREIGN")

	def test_a_pinned_item_from_another_build_is_rejected(self):
		with generator() as (engine, frappe, _, _artifacts):
			doc = build(configured_item="FOREIGN", part_number="PN")
			items(frappe, {"FOREIGN": "ILL-CTN-00009"})
			frappe.throw = MagicMock(side_effect=ValueError("mismatch"))
			with self.assertRaises(ValueError):
				engine._create_or_get_configured_tape_neon_item(doc)


if __name__ == "__main__":
	unittest.main()
