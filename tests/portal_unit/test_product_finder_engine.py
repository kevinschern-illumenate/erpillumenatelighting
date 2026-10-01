"""Browser/server branching parity, stale-answer pruning and catalog routing."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from illumenate_lighting.illumenate_lighting.portal.product_finder import engine

DEF = {
	"questions": [
		{
			"id": "family",
			"type": "family",
			"options": [
				{"value": "Linear Fixture"},
				{"value": "Driver"},
				{"value": "accessories", "routes_to": "Catalog only"},
			],
		},
		{
			"id": "moisture",
			"type": "single",
			"families": ["Linear Fixture"],
			"options": [{"value": "Dry"}, {"value": "Wet"}],
		},
		{
			"id": "ip",
			"type": "multi",
			"families": ["Linear Fixture"],
			"visibleWhen": {"all": [{"q": "moisture", "eq": "Wet"}]},
			"options": [
				{"value": "67"},
				{"value": "68", "hideWhen": {"all": [{"q": "hide", "exists": True}]}},
			],
		},
		{"id": "load", "type": "number", "families": ["Driver"]},
	]
}


class Engine(unittest.TestCase):
	def test_all_operators_and_groups(self):
		for op, threshold, answer, expected in [
			("eq", "a", "a", True),
			("eq", 1, True, False),
			("ne", "a", "b", True),
			("in", ["a"], "a", True),
			("exists", True, "", False),
			("exists", False, None, True),
			("gt", 2, 3, True),
			("gte", 2, 2, True),
			("lt", 2, 1, True),
			("lte", 2, 2, True),
			("gt", 2, "bad", False),
			("gt", 2, float("inf"), False),
		]:
			with self.subTest(op=op, answer=answer):
				self.assertEqual(engine.test_clause({"q": "q", op: threshold}, {"q": answer}), expected)
		self.assertFalse(
			engine.eval_condition({"all": [{"q": "a", "eq": 1}], "any": [{"q": "b", "eq": 2}]}, {"a": 1})
		)
		self.assertTrue(engine.eval_condition(None, {}))
		self.assertFalse(engine.eval_condition({"any": []}, {}))

	def test_prune_hidden_questions_options_and_stale_values(self):
		self.assertEqual(
			engine.prune(DEF, {"family": "Driver", "moisture": "Wet", "ip": ["67"], "load": 10}),
			{"family": "Driver", "load": 10},
		)
		self.assertEqual(
			engine.prune(DEF, {"family": "Linear Fixture", "moisture": "Wet", "ip": ["67", "old"]})["ip"],
			["67"],
		)
		self.assertEqual(
			[o["value"] for o in engine.visible_options(DEF["questions"][2], {"hide": True})], ["67"]
		)
		self.assertEqual(engine.route(DEF, {"family": "accessories"})["query"]["type"], "Accessory,Component")

	@unittest.skipUnless(shutil.which("node"), "node is required for browser parity")
	def test_ten_answer_sets_match_the_real_browser_engine(self):
		path = Path("tools/configurator_ui/src/lib/engine.js")
		source = path.read_text().replace(
			"import questionsData from '../content/questions.json';",
			"const questionsData = globalThis.definition;",
		)
		answers = [
			{},
			{"family": "Driver"},
			{"family": "Linear Fixture"},
			{"family": "accessories"},
			{"family": "Linear Fixture", "moisture": "Wet"},
			{"family": "Linear Fixture", "moisture": "Dry"},
			{"family": "Driver", "moisture": "Wet"},
			{"moisture": "Wet"},
			{"family": "Driver", "load": 100},
			{"family": "Linear Fixture", "moisture": "Wet", "ip": ["67", "old"]},
		]
		script = f"globalThis.definition={json.dumps(DEF)};const e=await import('data:text/javascript,'+encodeURIComponent({json.dumps(source)}));if(e.setDefinition)e.setDefinition(globalThis.definition);console.log(JSON.stringify({json.dumps(answers)}.map(a=>({{visible:e.visibleQuestions(a).map(q=>q.id),pruned:e.pruneHiddenAnswers(a)}}))));"
		result = subprocess.run(
			["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True
		)
		for answer, browser in zip(answers, json.loads(result.stdout), strict=True):
			self.assertEqual(
				browser["visible"],
				[
					q["id"]
					for q in DEF["questions"]
					if engine.is_visible(q, answer, engine.family_of(DEF, answer))
				],
			)
			self.assertEqual(browser["pruned"], engine.prune(DEF, answer))
