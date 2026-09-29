"""Regression coverage for app directories blocking Frappe backup cleanup."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_services import ROOT, load_service

from illumenate_lighting.private_storage import private_state_directory


class PrivateStorage(unittest.TestCase):
	def test_legacy_directories_move_intact_and_retry_without_recreating_backup_children(self):
		for name in ("ill-workspace", "b2b-release"):
			with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
				private = Path(temporary) / "private"
				legacy = private / "backups" / name
				legacy.mkdir(parents=True)
				(legacy / "pending.json").write_bytes(b'{"backup":"snapshot.json"}')
				(legacy / "snapshot.json").write_bytes(b'{"content":"customized"}')
				archive = private / "backups" / "database.sql.gz"
				archive.write_bytes(b"existing backup")
				original = {path.name: path.read_bytes() for path in legacy.iterdir()}
				directory = private_state_directory(private, name)
				self.assertEqual(directory, private / name)
				self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, original)
				self.assertFalse(legacy.exists())
				self.assertEqual(private_state_directory(private, name), directory)
				# Frappe cleanup unlinks entries in private/backups as files. The
				# relocated snapshots must survive even when every entry is expired.
				for path in (private / "backups").iterdir():
					path.unlink()
				self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, original)

	def test_conflicting_directories_preserve_both_and_clear_backup_cleanup_path(self):
		with tempfile.TemporaryDirectory() as temporary:
			private = Path(temporary)
			legacy = private / "backups" / "ill-workspace"
			directory = private / "ill-workspace"
			for path, snapshot in ((legacy, b"original snapshot"), (directory, b"another snapshot")):
				path.mkdir(parents=True)
				(path / "pending.json").write_bytes(snapshot)
			(legacy / "snapshot.json").write_bytes(b"legacy workspace")
			messages = []
			self.assertEqual(
				private_state_directory(private, "ill-workspace", log=messages.append), directory
			)
			# Frappe's backup cleanup can no longer trip over the legacy directory.
			self.assertFalse(legacy.exists())
			self.assertEqual((directory / "pending.json").read_bytes(), b"another snapshot")
			(moved,) = directory.glob("legacy-*")
			self.assertEqual((moved / "pending.json").read_bytes(), b"original snapshot")
			self.assertEqual((moved / "snapshot.json").read_bytes(), b"legacy workspace")
			self.assertEqual(len(messages), 1)
			self.assertIn(str(moved), messages[0])
			# A second conflict gets its own destination instead of merging.
			legacy.mkdir(parents=True)
			(legacy / "pending.json").write_bytes(b"third snapshot")
			private_state_directory(private, "ill-workspace")
			self.assertEqual(
				sorted((path / "pending.json").read_bytes() for path in directory.glob("legacy-*")),
				[b"original snapshot", b"third snapshot"],
			)

	def test_unexpected_file_is_preserved(self):
		for relative in ("backups/ill-workspace", "ill-workspace"):
			with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
				private = Path(temporary)
				path = private / relative
				path.parent.mkdir(parents=True, exist_ok=True)
				path.write_bytes(b"retain me")
				with self.assertRaisesRegex(ValueError, "not a file or symlink"):
					private_state_directory(private, "ill-workspace")
				self.assertEqual(path.read_bytes(), b"retain me")

	def test_legacy_pending_workspace_is_restored_after_relocation(self):
		with (
			load_service("illumenate_lighting.portal_workspace") as (module, frappe),
			tempfile.TemporaryDirectory() as temporary,
		):
			private = Path(temporary) / "private"
			legacy = private / "backups" / "ill-workspace"
			legacy.mkdir(parents=True)
			original = json.dumps({"content": '[{"id":"custom","type":"header"}]'}).encode()
			(legacy / "snapshot.json").write_bytes(original)
			(legacy / "pending.json").write_text('{"backup":"snapshot.json"}', encoding="utf-8")
			frappe.get_site_path = lambda *parts: str(Path(temporary).joinpath(*parts))
			shipped = Path(
				"illumenate_lighting/illumenate_lighting/workspace/illumenate_lighting/illumenate_lighting.json"
			)
			frappe.get_app_path = lambda *parts: str(shipped)
			frappe.get_doc.return_value.as_dict.return_value = json.loads(shipped.read_text(encoding="utf-8"))
			applied = {}
			frappe.get_doc.return_value.set.side_effect = applied.__setitem__
			module.before_migrate()
			directory = private / "ill-workspace"
			self.assertFalse(legacy.exists())
			self.assertEqual((directory / "snapshot.json").read_bytes(), original)
			module.after_migrate()
			self.assertEqual(json.loads(applied["content"])[0]["id"], "custom")
			self.assertEqual(applied["type"], "Workspace")
			self.assertTrue((directory / "pending.json").exists())
			frappe.db.after_commit.add.call_args.args[0]()
			self.assertFalse((directory / "pending.json").exists())
			self.assertEqual((directory / "snapshot.json").read_bytes(), original)
			self.assertEqual(
				json.loads((directory / "last-merge.json").read_text())["backup"], "snapshot.json"
			)

	def test_new_workspace_snapshots_leave_backup_cleanup_directory_empty(self):
		with (
			load_service("illumenate_lighting.portal_workspace") as (module, frappe),
			tempfile.TemporaryDirectory() as temporary,
		):
			backups = Path(temporary) / "private" / "backups"
			backups.mkdir(parents=True)
			frappe.get_site_path = lambda *parts: str(Path(temporary).joinpath(*parts))
			frappe.get_doc.return_value.as_dict.return_value = {"content": "[]"}
			module.before_migrate()
			self.assertEqual(list(backups.iterdir()), [])
			self.assertTrue((backups.parent / "ill-workspace" / "pending.json").is_file())

	def test_release_capture_and_comparison_reuse_legacy_checkpoints(self):
		with (
			load_service(ROOT + ".portal.release_evidence") as (module, frappe),
			tempfile.TemporaryDirectory() as temporary,
		):
			private = Path(temporary) / "private"
			legacy = private / "backups" / "b2b-release"
			legacy.mkdir(parents=True)
			evidence = {"records": {"Sales Order": {"SO-1": "unchanged-hash"}}}
			(legacy / "before.json").write_text(json.dumps(evidence), encoding="utf-8")
			frappe.get_site_path = lambda *parts: str(Path(temporary).joinpath(*parts))
			frappe.only_for = MagicMock()
			with patch.object(module, "collect", return_value=evidence):
				result = module.capture("after")
			self.assertEqual(Path(result["private_checkpoint"]), private / "b2b-release" / "after.json")
			self.assertTrue(module.compare_checkpoints("before", "after")["historical_records_unchanged"])
			self.assertFalse(legacy.exists())
			with patch.object(module, "collect", return_value=evidence), self.assertRaises(FileExistsError):
				module.capture("after")


class MigrationHooksNeverAbort(unittest.TestCase):
	def workspace_module(self, temporary):
		context = load_service("illumenate_lighting.portal_workspace")
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_site_path = lambda *parts: str(Path(temporary).joinpath(*parts))
		frappe.log_error = MagicMock()
		frappe.get_traceback = MagicMock(return_value="traceback")
		return module, frappe

	def test_before_migrate_failure_is_logged_not_raised(self):
		with tempfile.TemporaryDirectory() as temporary:
			module, frappe = self.workspace_module(temporary)
			frappe.get_doc.side_effect = RuntimeError("workspace unreadable")
			module.before_migrate()
			self.assertIn("before_migrate", frappe.log_error.call_args.kwargs["title"])

	def test_missing_snapshot_keeps_pending_and_rolls_back(self):
		with tempfile.TemporaryDirectory() as temporary:
			module, frappe = self.workspace_module(temporary)
			directory = Path(temporary) / "private" / "ill-workspace"
			directory.mkdir(parents=True)
			(directory / "pending.json").write_text('{"backup":"missing.json"}', encoding="utf-8")
			module.after_migrate()
			self.assertTrue((directory / "pending.json").exists())
			frappe.db.savepoint.assert_called_once_with(module.SAVEPOINT)
			frappe.db.rollback.assert_called_once_with(save_point=module.SAVEPOINT)
			frappe.db.after_commit.add.assert_not_called()
			self.assertIn("after_migrate", frappe.log_error.call_args.kwargs["title"])

	def test_failed_workspace_save_is_rolled_back_and_retried_later(self):
		with tempfile.TemporaryDirectory() as temporary:
			module, frappe = self.workspace_module(temporary)
			frappe.get_doc.return_value.as_dict.return_value = {"content": "[]"}
			module.before_migrate()
			frappe.get_doc.return_value.save.side_effect = RuntimeError("MandatoryError: type")
			module.after_migrate()
			pending = Path(temporary) / "private" / "ill-workspace" / "pending.json"
			self.assertTrue(pending.exists())
			frappe.db.rollback.assert_called_once_with(save_point=module.SAVEPOINT)

	def test_legacy_directory_moves_even_without_workspace_record(self):
		with tempfile.TemporaryDirectory() as temporary:
			module, frappe = self.workspace_module(temporary)
			legacy = Path(temporary) / "private" / "backups" / "ill-workspace"
			legacy.mkdir(parents=True)
			(legacy / "pending.json").write_text('{"backup":"snapshot.json"}', encoding="utf-8")
			frappe.db.exists.return_value = False
			module.before_migrate()
			self.assertFalse(legacy.exists())
			self.assertTrue((Path(temporary) / "private" / "ill-workspace" / "pending.json").exists())
			frappe.log_error.assert_not_called()
