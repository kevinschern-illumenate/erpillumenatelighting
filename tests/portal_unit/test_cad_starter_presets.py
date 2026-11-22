"""CAD plan WP 1.2: the starter run style seed script (tools/seed_imports/cad_starter_presets.py)."""

import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = "tools.seed_imports.cad_starter_presets"
EXAMPLE = Path(__file__).resolve().parents[2] / "tools/seed_imports/cad_starter_presets.example.csv"
HEADER = "customer,user,label,family,template,selections_json,cad_code,shared_with_company\n"


class StarterPresets(unittest.TestCase):
	def setUp(self):
		self.users = {
			"drafter@dealer.test": Record(
				customer="CUST-A", is_internal=False, is_dealer=True, is_guest=False
			),
			"staff@illumenate.test": Record(customer=None, is_internal=True, is_dealer=False, is_guest=False),
		}
		self.prepared = []
		self.saved = []
		self.existing = {}

		def actor(user=None):
			return Record(user=user, **self.users.get(user, {"is_guest": True}))

		def prepare(
			actor, label, request, shared_with_company=None, preset=None, cad_code=None, cad_enabled=None
		):
			self.prepared.append((actor.user, label, request, shared_with_company, cad_code))
			if request["template"] == "GONE":
				raise ValueError("GONE is no longer offered")
			values = {
				"label": label,
				"family": request["family"],
				"template": request["template"],
				"request_json": json.dumps(request),
				"customer": actor.customer if not actor.is_internal else None,
				"shared_with_company": 1 if shared_with_company == "1" else 0,
			}
			if cad_code:
				values["cad_code"] = cad_code.upper()
			return self.existing.get((actor.user, label)), values

		def revalidate(request):
			if request["selections"].get("finish_code") == "Silver":
				return request, ["Finish Silver is no longer offered; choose it again"]
			return request, []

		self.extras = {
			ROOT + ".portal.presets": types.SimpleNamespace(
				prepare=prepare,
				revalidate=revalidate,
				save=lambda *args, **kwargs: self.saved.append((args, kwargs)),
			),
			ROOT + ".portal.access": types.SimpleNamespace(Actor=actor),
		}

	def run_csv(self, text, **kwargs):
		with tempfile.TemporaryDirectory() as folder:
			path = Path(folder) / "presets.csv"
			path.write_text(HEADER + text, encoding="utf-8")
			with load_service(MODULE, self.extras) as (module, frappe):
				frappe.db.exists.side_effect = lambda doctype, name: name in self.users
				frappe.set_user = MagicMock()
				out = io.StringIO()
				result = module.run(str(path), out=out, **kwargs)
				return result, out.getvalue(), frappe

	def test_example_csv_has_the_columns_and_placeholder_rows(self):
		with load_service(MODULE) as (module, _frappe):
			rows = module.read_rows(EXAMPLE)
		self.assertEqual(len(rows), 2)
		for _line, row in rows:
			self.assertIn("EXAMPLE", row["template"], "example templates are clearly placeholders")
			self.assertIsInstance(module.request_for(row)["selections"], dict)
			self.assertTrue(row["cad_code"])

	def test_dry_run_checks_every_row_as_its_user_and_saves_nothing(self):
		result, out, frappe = self.run_csv(
			'CUST-A,drafter@dealer.test,Cove,LED Tape,TN-1,"{""cct"": ""2700K""}",cove-27,1\n'
			",staff@illumenate.test,Lobby,Linear Fixture,FT-1,,LOBBY,0\n"
		)
		self.assertEqual((result["created"], result["errors"], result["dry_run"]), (2, [], True))
		self.assertEqual(self.saved, [])
		frappe.db.commit.assert_not_called()
		frappe.db.rollback.assert_called_once()
		self.assertEqual(
			self.prepared[0][2], {"family": "LED Tape", "template": "TN-1", "selections": {"cct": "2700K"}}
		)
		self.assertEqual(self.prepared[0][3:], ("1", "cove-27"))
		self.assertEqual(
			[call.args[0] for call in frappe.set_user.call_args_list][:2],
			["drafter@dealer.test", "staff@illumenate.test"],
		)
		self.assertIn(
			"line 2: would create shared preset 'Cove' for drafter@dealer.test (LED Tape TN-1, code COVE-27)",
			out,
		)
		self.assertIn("nothing saved", out)

	def test_bad_rows_are_reported_by_line(self):
		self.existing[("drafter@dealer.test", "Cove")] = "P1"
		result, out, _frappe = self.run_csv(
			"CUST-A,drafter@dealer.test,Cove,LED Tape,TN-1,,COVE,0\n"
			"CUST-A,drafter@dealer.test,Cove 2,LED Tape,TN-1,,cove,0\n"
			"CUST-A,drafter@dealer.test,Cove,LED Tape,TN-2,,,0\n"
			"CUST-B,drafter@dealer.test,Other,LED Tape,TN-1,,,0\n"
			"CUST-A,nobody@dealer.test,Ghost,LED Tape,TN-1,,,0\n"
			"CUST-A,drafter@dealer.test,Bad,LED Tape,TN-1,{nope,,0\n"
			"CUST-A,drafter@dealer.test,Gone,LED Tape,GONE,,,0\n"
			'CUST-A,drafter@dealer.test,Silver,Linear Fixture,FT-1,"{""finish_code"": ""Silver""}",,0\n'
		)
		self.assertEqual(result["replaced"], 1)
		self.assertIn("would replace preset 'Cove'", out)
		errors = dict(result["errors"])
		self.assertIn("also on line 2", errors[3])
		self.assertIn("same user and label as line 2", errors[4])
		self.assertIn("belongs to company CUST-A, not CUST-B", errors[5])
		self.assertIn("does not exist", errors[6])
		self.assertIn("not valid JSON", errors[7])
		self.assertIn("no longer offered", errors[8])
		self.assertIn("Finish Silver", errors[9])

	def test_commit_saves_all_rows_or_none(self):
		row = "CUST-A,drafter@dealer.test,Cove,LED Tape,TN-1,,COVE,1\n"
		result, out, frappe = self.run_csv(row, dry_run=False)
		self.assertEqual(result["created"], 1)
		((args, kwargs),) = self.saved
		self.assertEqual(args[1:], ("Cove", {"family": "LED Tape", "template": "TN-1", "selections": {}}))
		self.assertEqual(kwargs, {"shared_with_company": "1", "cad_code": "COVE"})
		frappe.db.commit.assert_called_once()
		self.assertIn("Saved: 1 created", out)
		self.saved.clear()
		result, out, frappe = self.run_csv(
			row + "CUST-A,drafter@dealer.test,Gone,LED Tape,GONE,,,0\n", dry_run=False
		)
		self.assertEqual((result["created"], len(result["errors"])), (0, 1))
		frappe.db.commit.assert_not_called()
		frappe.db.rollback.assert_called_once()
		self.assertIn("nothing saved", out)


if __name__ == "__main__":
	unittest.main()
