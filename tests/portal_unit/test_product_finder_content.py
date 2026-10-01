"""Product Finder content managed in Desk: registry, validation, seed, definition, coverage."""

import json
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.portal.product_finder import content, facets

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting"
DOCTYPES = APP / "illumenate_lighting/doctype"
SEED = APP / "illumenate_lighting/portal/product_finder/seed/content.json"
PUBLIC = APP / "public"
FINDER = ROOT + ".portal.product_finder"


def schema(stem):
	return json.loads((DOCTYPES / stem / f"{stem}.json").read_text(encoding="utf-8"))


def field_options(stem, fieldname):
	return next(f["options"] for f in schema(stem)["fields"] if f["fieldname"] == fieldname).split("\n")


def seed():
	return json.loads(SEED.read_text(encoding="utf-8"))


def others_for(questions, current):
	return [
		{
			"name": q["question_key"],
			"sequence": q["sequence"],
			"is_active": q["is_active"],
			"question_type": q["question_type"],
		}
		for q in questions
		if q is not current
	]


class RegistryMatchesDocTypes(unittest.TestCase):
	def test_select_options_follow_the_facet_registry(self):
		self.assertEqual(field_options("ill_finder_question", "facet"), ["", *facets.FACETS])
		self.assertEqual(
			field_options("ill_child_finder_value_map", "attribute_doctype"), ["", *facets.MAPPABLE_DOCTYPES]
		)
		self.assertEqual(field_options("ill_child_finder_family", "family"), ["Any", *facets.FAMILIES])
		comparisons = {c for allowed in facets.COMPARISONS.values() for c in allowed}
		self.assertEqual(set(field_options("ill_finder_question", "comparison")) - {""}, comparisons)

	def test_every_facet_that_needs_value_maps_names_real_attribute_doctypes(self):
		names = {
			schema(path.name)["name"] for path in DOCTYPES.iterdir() if (path / f"{path.name}.json").exists()
		}
		for name, spec in facets.FACETS.items():
			with self.subTest(facet=name):
				self.assertTrue(set(spec["doctypes"]) <= names)
				self.assertTrue(set(spec["families"]) <= set(facets.FAMILIES))


class QuestionValidation(unittest.TestCase):
	def question(self, **changes):
		doc = {
			"question_key": "moisture",
			"question_type": "Single",
			"is_active": 1,
			"sequence": 40,
			"options": [{"value": "Dry", "is_active": 1}, {"value": "Wet", "is_active": 1}],
			"conditions": [],
			"value_maps": [],
			"facet": "environment_rating",
			"match_mode": "Hard",
			"comparison": "Meets or exceeds",
		}
		doc.update(changes)
		return doc

	def errors(self, doc, others=()):
		return " | ".join(content.validate_question(doc, list(others)))

	def test_a_valid_question_has_no_errors(self):
		self.assertEqual(content.validate_question(self.question(), []), [])

	def test_keys_option_values_and_swatches(self):
		self.assertIn("Question Key", self.errors(self.question(question_key="Moisture Level")))
		self.assertIn(
			"unique: Dry", self.errors(self.question(options=[{"value": "Dry", "is_active": 1}] * 2))
		)
		bad = self.question(
			options=[{"value": "Dry", "is_active": 1, "swatch_color": "red;background:url(x)"}]
		)
		self.assertIn("swatch color", self.errors(bad))
		good = self.question(
			options=[
				{
					"value": "Dry",
					"is_active": 1,
					"swatch_color": "linear-gradient(135deg, #fff 0%, #000 100%)",
				}
			]
		)
		self.assertEqual(content.validate_question(good, []), [])
		self.assertIn(
			"at least one active option",
			self.errors(self.question(options=[{"value": "Dry", "is_active": 0}])),
		)
		self.assertIn(
			"do not use options",
			self.errors(self.question(question_type="Number", facet=None, match_mode="None")),
		)

	def test_product_type_question_rules(self):
		chooser = self.question(
			question_key="product_family",
			question_type="Family chooser",
			sequence=10,
			facet="family",
			comparison="Any of",
			options=[{"value": "Linear Fixture", "is_active": 1}, {"value": "Lamps", "is_active": 1}],
		)
		self.assertIn("'Lamps' must be a product type", self.errors(chooser))
		chooser["options"][1] = {"value": "accessories", "is_active": 1, "routes_to": "Catalog only"}
		self.assertEqual(content.validate_question(chooser, []), [])
		others = [{"name": "intro", "sequence": 5, "is_active": 1, "question_type": "Single"}]
		self.assertIn("must come first", self.errors(chooser, others))
		others = [{"name": "old_family", "sequence": 50, "is_active": 1, "question_type": "Family chooser"}]
		self.assertIn("Only one active product-type question", self.errors(chooser, others))
		first = [
			{"name": "product_family", "sequence": 10, "is_active": 1, "question_type": "Family chooser"}
		]
		self.assertIn("must come first", self.errors(self.question(sequence=5), first))
		self.assertEqual(content.validate_question(self.question(sequence=20), first), [])

	def test_conditions_point_backwards_at_active_questions(self):
		others = [
			{"name": "indoor_outdoor", "sequence": 30, "is_active": 1, "question_type": "Single"},
			{"name": "later", "sequence": 90, "is_active": 1, "question_type": "Single"},
			{"name": "retired", "sequence": 20, "is_active": 0, "question_type": "Single"},
		]
		cases = (
			(
				{"depends_on_question": "moisture", "operator": "equals", "value": "x"},
				"cannot depend on itself",
			),
			({"depends_on_question": "missing", "operator": "equals", "value": "x"}, "does not exist"),
			({"depends_on_question": "later", "operator": "equals", "value": "x"}, "must come earlier"),
			({"depends_on_question": "retired", "operator": "equals", "value": "x"}, "not active"),
			({"depends_on_question": "indoor_outdoor", "operator": "equals", "value": ""}, "enter a value"),
			(
				{"depends_on_question": "indoor_outdoor", "operator": "at least", "value": "lots"},
				"needs a number",
			),
			(
				{
					"depends_on_question": "indoor_outdoor",
					"operator": "equals",
					"value": "Outdoor",
					"applies_to": "Hide option when",
					"option_value": "Damp",
				},
				"'Damp' is not an option",
			),
		)
		for condition, message in cases:
			with self.subTest(message=message):
				self.assertIn(message, self.errors(self.question(conditions=[condition]), others))
		answered = {"depends_on_question": "indoor_outdoor", "operator": "answered"}
		self.assertEqual(content.validate_question(self.question(conditions=[answered]), others), [])

	def test_matching_and_value_maps(self):
		rating = "ilL-Attribute-Environment Rating"
		self.assertIn("Choose the Product Fact", self.errors(self.question(facet=None)))
		self.assertIn("does not apply", self.errors(self.question(comparison="At least")))
		self.assertIn(
			"read from product data",
			self.errors(
				self.question(
					facet="light_type",
					comparison="Any of",
					value_maps=[
						{
							"option_value": "Dry",
							"attribute_doctype": "ilL-Attribute-LED Package",
							"attribute_value": "SW",
						}
					],
				)
			),
		)
		maps = [
			{"option_value": "Damp", "attribute_doctype": rating, "attribute_value": "Damp"},
			{"option_value": "Dry", "attribute_doctype": "ilL-Attribute-CCT", "attribute_value": "3000K"},
			{"option_value": "Wet", "attribute_doctype": rating, "attribute_value": "Wet"},
			{"option_value": "Wet", "attribute_doctype": rating, "attribute_value": "Wet"},
		]
		errors = self.errors(self.question(value_maps=maps))
		self.assertIn("'Damp': that is not an option", errors)
		self.assertIn("maps to ilL-Attribute-Environment Rating", errors)
		self.assertIn("listed twice", errors)
		no_preference = self.question(
			options=[
				{"value": "Dry", "is_active": 1},
				{"value": "any", "is_active": 1, "is_no_preference": 1},
			],
			value_maps=[{"option_value": "any", "attribute_doctype": rating, "attribute_value": "Dry"}],
		)
		self.assertIn("No Preference option matches every product", self.errors(no_preference))


class SeedContent(unittest.TestCase):
	def test_every_seed_question_passes_desk_validation(self):
		questions = seed()["questions"]
		for question in questions:
			with self.subTest(question=question["question_key"]):
				doc = dict(question)
				if doc.get("facet") and not doc.get("comparison"):
					doc["comparison"] = content.default_comparison(doc["facet"])
				self.assertEqual(content.validate_question(doc, others_for(questions, question)), [])

	def test_product_type_comes_first_with_linear_fixture_featured(self):
		questions = sorted(seed()["questions"], key=lambda q: q["sequence"])
		first = questions[0]
		self.assertEqual(first["question_type"], "Family chooser")
		featured = [o for o in first["options"] if o.get("is_featured")]
		self.assertEqual([o["value"] for o in featured], ["Linear Fixture"])
		self.assertIn("not sure", featured[0]["badge_text"].lower())
		self.assertEqual(
			{o["value"] for o in first["options"] if not o.get("routes_to")}, set(facets.FAMILIES)
		)
		asked = {f["family"] for q in questions for f in q["families"]}
		self.assertTrue(set(facets.FAMILIES) - {"LED Sheet"} <= asked)

	def test_images_ship_and_glossary_references_resolve(self):
		data = seed()
		terms = {term["term_key"] for term in data["glossary"]}
		for question in data["questions"]:
			references = [question.get("glossary_term")] + [
				o.get("glossary_term") for o in question.get("options", [])
			]
			for reference in filter(None, references):
				self.assertIn(reference, terms)
			for option in question.get("options", []):
				if option.get("image"):
					path = PUBLIC / option["image"].removeprefix("/assets/illumenate_lighting/")
					self.assertTrue(path.is_file(), option["image"])
					self.assertLess(path.stat().st_size, 60_000)


class Definition(unittest.TestCase):
	def build(self, questions, options=(), conditions=(), families=(), include_inactive=False):
		tables = {
			"ilL-Finder-Question": questions,
			"ilL-Child-Finder-Option": list(options),
			"ilL-Child-Finder-Condition": list(conditions),
			"ilL-Child-Finder-Family": list(families),
			"ilL-Finder-Glossary-Term": [
				Record(name="ip_rating", label="IP Rating", tooltip="Dust and water", learn_more="")
			],
		}
		with load_service(FINDER + ".definition") as (service, frappe):
			frappe.get_all.side_effect = lambda doctype, **kwargs: tables[doctype]
			frappe.get_cached_doc = MagicMock(
				return_value=Record(banner_headline="Not sure?", verification_text="{reasons}")
			)
			return service.build_definition(7, include_inactive=include_inactive)

	def test_questions_conditions_and_options_use_the_engine_shape(self):
		questions = [
			Record(
				name="moisture",
				question_key="moisture",
				label="Moisture?",
				question_type="Single",
				required=1,
				is_active=1,
			),
			Record(
				name="ip_rating",
				question_key="ip_rating",
				label="IP?",
				question_type="Single",
				required=1,
				is_active=1,
				glossary_term="ip_rating",
			),
			Record(
				name="watts",
				question_key="watts",
				label="Watts?",
				question_type="Number",
				required=0,
				is_active=0,
				number_min=1,
				number_max=2000,
				unit="W",
			),
		]
		options = [
			Record(parent="moisture", value="Dry", label="Dry", is_active=1),
			Record(
				parent="moisture",
				value="Wet",
				label="Wet",
				is_active=1,
				is_featured=1,
				image="/assets/x.webp",
			),
			Record(parent="moisture", value="Old", label="Old", is_active=0),
		]
		conditions = [
			Record(
				parent="ip_rating",
				applies_to="Show question when",
				match_group="Any",
				depends_on_question="moisture",
				operator="in",
				value="Damp, Wet",
			),
			Record(
				parent="ip_rating",
				applies_to="Show question when",
				match_group="Any",
				depends_on_question="indoor",
				operator="equals",
				value="Outdoor",
			),
			Record(
				parent="ip_rating",
				applies_to="Skip question when",
				match_group="All",
				depends_on_question="watts",
				operator="at least",
				value="100",
			),
			Record(
				parent="moisture",
				applies_to="Hide option when",
				match_group="All",
				depends_on_question="indoor",
				operator="answered",
				option_value="Dry",
			),
		]
		result = self.build(
			questions,
			options,
			conditions,
			[Record(parent="moisture", family="Linear Fixture")],
			include_inactive=True,
		)
		by_id = {q["id"]: q for q in result["questions"]}
		self.assertEqual(result["version"], 7)
		self.assertEqual(by_id["moisture"]["families"], ["Linear Fixture"])
		self.assertEqual(by_id["ip_rating"]["families"], ["Any"])
		self.assertEqual([o["value"] for o in by_id["moisture"]["options"]], ["Dry", "Wet"])
		self.assertEqual(
			by_id["moisture"]["options"][0]["hideWhen"], {"all": [{"q": "indoor", "exists": True}]}
		)
		self.assertTrue(by_id["moisture"]["options"][1]["featured"])
		self.assertEqual(
			by_id["ip_rating"]["visibleWhen"],
			{"any": [{"q": "moisture", "in": ["Damp", "Wet"]}, {"q": "indoor", "eq": "Outdoor"}]},
		)
		self.assertEqual(by_id["ip_rating"]["skipWhen"], {"all": [{"q": "watts", "gte": 100.0}]})
		self.assertEqual(by_id["ip_rating"]["glossaryKey"], "ip_rating")
		self.assertEqual(
			(by_id["watts"]["type"], by_id["watts"]["max"], by_id["watts"]["draft"]), ("number", 2000, True)
		)
		self.assertNotIn("options", by_id["watts"])
		self.assertEqual(result["glossary"]["ip_rating"]["tooltip"], "Dust and water")
		self.assertEqual(result["settings"]["banner_headline"], "Not sure?")

	def test_empty_condition_groups_are_omitted(self):
		# engine.js treats {"all": []} as true, which would silently skip a question.
		questions = [
			Record(name="q", question_key="q", label="Q", question_type="Single", required=1, is_active=1)
		]
		result = self.build(questions, [Record(parent="q", value="A", label="A", is_active=1)])
		self.assertNotIn("visibleWhen", result["questions"][0])
		self.assertNotIn("skipWhen", result["questions"][0])
		self.assertNotIn("hideWhen", result["questions"][0]["options"][0])

	def test_definition_is_cached_per_content_version(self):
		with load_service(FINDER + ".definition") as (service, frappe):
			frappe.db.get_single_value.return_value = 4
			cache = MagicMock()
			cache.get_value.return_value = None
			frappe.cache = MagicMock(return_value=cache)
			with patch.object(service, "build_definition", return_value={"version": 4}) as build:
				service.load_definition()
			build.assert_called_once_with(4, include_inactive=False)
			self.assertEqual(cache.set_value.call_args.args[0], "ill_product_finder:definition:4:0")
			service.content_changed()
			frappe.db.set_single_value.assert_called_once_with(
				"ilL-Product-Finder-Settings", "definition_version", 5
			)


class FakeDocument(Record):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def __setattr__(self, key, value):
		self[key] = value

	def append(self, table, row):
		self.setdefault(table, []).append(Record(row))

	def as_dict(self):
		return dict(self)


def controller(stem, extras=None):
	document = types.ModuleType("frappe.model.document")
	document.Document = FakeDocument
	deps = {
		"frappe.model": types.ModuleType("frappe.model"),
		"frappe.model.document": document,
		**(extras or {}),
	}
	return load_service(f"{ROOT}.doctype.{stem}.{stem}", deps)


class Controllers(unittest.TestCase):
	def test_question_defaults_and_errors_block_saving(self):
		with controller("ill_finder_question") as (module, frappe):
			frappe.get_all.return_value = []
			frappe.utils = types.SimpleNamespace(escape_html=lambda value: value)

			def throw(message, exception=ValueError, title=None):
				raise exception(message)

			frappe.throw = throw
			doc = module.ilLFinderQuestion(
				question_key=" product_family ",
				question_type="Family chooser",
				is_active=1,
				sequence=10,
				options=[Record(value="Linear Fixture", is_active=1)],
			)
			doc.before_validate()
			self.assertEqual(
				(doc.question_key, doc.facet, doc.match_mode, doc.comparison),
				("product_family", "family", "Hard", "Any of"),
			)
			self.assertEqual(doc.families, [{"family": "Any"}])
			doc.validate()
			soft = module.ilLFinderQuestion(
				question_key="cri",
				question_type="Single",
				facet="cri_min",
				options=[Record(value="90+", is_active=1)],
				families=[Record(family="Any")],
			)
			soft.before_validate()
			self.assertEqual(soft.comparison, "At least")
			broken = module.ilLFinderQuestion(
				question_key="Bad Key",
				question_type="Single",
				options=[Record(value="a", is_active=1)],
				families=[Record(family="Any")],
			)
			with self.assertRaisesRegex(ValueError, "Question Key"):
				broken.validate()

	def test_settings_bump_from_the_stored_version_and_check_copy(self):
		with controller("ill_product_finder_settings") as (module, frappe):
			frappe.db.get_single_value.return_value = 9
			doc = module.ilLProductFinderSettings(
				results_limit=60,
				session_expiry_days=30,
				verification_text="Check {reasons}",
				definition_version=3,
			)
			doc.validate()
			doc.before_save()
			self.assertEqual(doc.definition_version, 10)
			for changes, message in (
				({"verification_text": "Check this"}, "{reasons}"),
				({"results_limit": 0}, "Maximum Results"),
				({"public_enabled": 1, "public_brands": []}, "brand"),
			):
				with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
					module.ilLProductFinderSettings({**doc, **changes}).validate()


class SeedPatch(unittest.TestCase):
	def test_seed_inserts_missing_content_in_order_maps_clear_answers_and_keeps_staff_edits(self):
		inserted = []
		records = {
			"ilL-Attribute-Environment Rating": [
				Record(name="Damp Location", label="Damp", code="DP"),
				Record(name="Wet Location", label="Wet", code="W"),
			],
		}

		def get_doc(data, *args):
			if isinstance(data, dict):
				doc = MagicMock()
				doc.insert.side_effect = lambda **kwargs: inserted.append(data)
				doc.set.side_effect = lambda field, value: data.__setitem__(field, value)
				return doc
			settings = MagicMock()
			return settings

		existing = {("ilL-Finder-Question", "indoor_outdoor"), ("ilL-Finder-Glossary-Term", "ip_rating")}
		with load_service("illumenate_lighting.patches.seed_product_finder") as (patch_module, frappe):
			frappe.db.exists.side_effect = lambda doctype, name=None: (doctype, name) in existing
			frappe.db.table_exists.return_value = True
			frappe.get_doc.side_effect = get_doc
			frappe.get_meta = MagicMock(
				return_value=types.SimpleNamespace(has_field=lambda field: field in ("label", "code"))
			)
			frappe.get_all.side_effect = lambda doctype, **kwargs: records.get(doctype, [])
			settings = Record(
				meta=types.SimpleNamespace(
					fields=[
						Record(fieldname="banner_headline", default="Hi"),
						Record(fieldname="portal_enabled", default="0"),
					]
				),
				banner_headline=None,
				portal_enabled=0,
			)
			settings.set = lambda key, value: settings.__setitem__(key, value)
			settings.save = MagicMock()
			frappe.get_single = MagicMock(return_value=settings)
			patch_module.execute()
		questions = [row for row in inserted if row["doctype"] == "ilL-Finder-Question"]
		terms = [row for row in inserted if row["doctype"] == "ilL-Finder-Glossary-Term"]
		self.assertNotIn("indoor_outdoor", [q["question_key"] for q in questions])
		self.assertNotIn("ip_rating", [t["term_key"] for t in terms])
		self.assertEqual([q["sequence"] for q in questions], sorted(q["sequence"] for q in questions))
		moisture = next(q for q in questions if q["question_key"] == "moisture")
		self.assertEqual(
			{(m["option_value"], m["attribute_value"]) for m in moisture["value_maps"]},
			{("Damp", "Damp Location"), ("Wet", "Wet Location")},
		)
		finish = next(q for q in questions if q["question_key"] == "finish")
		self.assertEqual(finish["value_maps"], [])
		light = next(q for q in questions if q["question_key"] == "light_type")
		self.assertEqual(light["value_maps"], [])
		self.assertEqual(settings.banner_headline, "Hi")
		self.assertEqual(settings.portal_enabled, 0)
		settings.save.assert_called_once()


class Coverage(unittest.TestCase):
	def test_reports_unmapped_answers_unreachable_values_and_broken_conditions(self):
		tables = {
			"ilL-Finder-Question": [
				Record(name="moisture", is_active=1, facet="environment_rating", match_mode="Hard"),
				Record(name="ip_rating", is_active=1, facet="ip_rating", match_mode="Hard"),
				Record(name="light_type", is_active=1, facet="light_type", match_mode="Hard"),
				Record(name="retired", is_active=0, facet=None, match_mode="None"),
			],
			"ilL-Child-Finder-Option": [
				Record(parent="moisture", value="Dry", label="Dry", is_active=1, is_no_preference=0),
				Record(parent="moisture", value="Wet", label="Wet", is_active=1, is_no_preference=0),
				Record(parent="moisture", value="any", label="Not sure", is_active=1, is_no_preference=1),
			],
			"ilL-Child-Finder-Value-Map": [
				Record(
					parent="moisture",
					option_value="Wet",
					attribute_doctype="ilL-Attribute-Environment Rating",
					attribute_value="Wet",
				),
			],
			"ilL-Child-Finder-Condition": [Record(parent="ip_rating", depends_on_question="retired")],
		}
		usage = [
			Record(attribute_doctype="ilL-Attribute-Environment Rating", attribute_name="Wet", products=3),
			Record(attribute_doctype="ilL-Attribute-Environment Rating", attribute_name="Damp", products=5),
			Record(attribute_doctype="ilL-Attribute-LED Package", attribute_name="Mystery", products=2),
		]

		def get_all(doctype, **kwargs):
			if doctype == "ilL-Attribute-LED Package":
				return ["Mystery", "Unused"]
			return tables[doctype]

		with load_service(ROOT + ".report.product_finder_coverage.product_finder_coverage") as (
			report,
			frappe,
		):
			frappe._dict = Record
			frappe.get_all.side_effect = get_all
			frappe.db.sql.return_value = usage
			_columns, rows = report.execute({})
		issues = {(row["issue"], row["question"], row["erp_value"], row["products"]) for row in rows}
		self.assertIn(("Answer not mapped", "moisture", None, None), issues)
		self.assertIn(("ERP value not reachable", None, "Damp", 5), issues)
		self.assertNotIn(("ERP value not reachable", None, "Wet", 3), issues)
		self.assertIn(("Condition on inactive question", "ip_rating", None, None), issues)
		self.assertIn(("LED package without spectrum type", None, "Mystery", 2), issues)
		self.assertEqual(len([row for row in rows if row["issue"] == "Answer not mapped"]), 1)


if __name__ == "__main__":
	unittest.main()


class EngineContract(unittest.TestCase):
	"""The definition built from the seed drives the quiz's own engine.js branching."""

	def definition(self):
		questions = [q for q in seed()["questions"] if q["is_active"]]
		rows = [
			Record(name=q["question_key"], **{k: v for k, v in q.items() if not isinstance(v, list)})
			for q in questions
		]
		options = [Record(parent=q["question_key"], **o) for q in questions for o in q.get("options", [])]
		conditions = [
			Record(parent=q["question_key"], **c) for q in questions for c in q.get("conditions", [])
		]
		families = [Record(parent=q["question_key"], **f) for q in questions for f in q["families"]]
		return Definition().build(rows, options, conditions, families)

	def test_branching_follows_the_seeded_conditions(self):
		import shutil
		import subprocess

		node = shutil.which("node")
		if not node:
			self.skipTest("node is not installed")
		engine = (APP.parent / "tools/configurator_ui/src/lib/engine.js").read_text(encoding="utf-8")
		engine = engine.replace(
			"import questionsData from '../content/questions.json';",
			"const questionsData = globalThis.__DEF__;",
		)
		script = (
			"globalThis.__DEF__ = "
			+ json.dumps(self.definition())
			+ ";\n"
			+ "const engine = await import('data:text/javascript,' + encodeURIComponent("
			+ json.dumps(engine)
			+ "));\n"
			+ "engine.setDefinition(globalThis.__DEF__);\n"
			+ "const ids = (answers) => engine.visibleQuestions(answers).map((q) => q.id);\n"
			+ "const options = (id, answers) => engine.visibleOptions(engine.QUESTIONS.find((q) => q.id === id), answers).map((o) => o.value);\n"
			+ "console.log(JSON.stringify({\n"
			+ " indoorDry: ids({indoor_outdoor: 'Indoor', moisture: 'Dry'}),\n"
			+ " indoorWet: ids({indoor_outdoor: 'Indoor', moisture: 'Wet', light_type: 'Full-color'}),\n"
			+ " outdoorMoisture: options('moisture', {indoor_outdoor: 'Outdoor'}),\n"
			+ " pixelDimming: options('dimming_protocol', {color_mode: 'Addressable pixel (SPI)'}),\n"
			+ " wireless: ids({control_method: 'Wireless Receiver'}),\n"
			+ "}));\n"
		)
		result = subprocess.run(
			[node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30
		)
		self.assertEqual(result.returncode, 0, result.stderr)
		seen = json.loads(result.stdout)
		self.assertNotIn("ip_rating", seen["indoorDry"])
		self.assertNotIn("color_mode", seen["indoorDry"])
		self.assertIn("ip_rating", seen["indoorWet"])
		self.assertIn("color_mode", seen["indoorWet"])
		self.assertNotIn("Dry", seen["outdoorMoisture"])
		self.assertEqual(seen["pixelDimming"], ["DMX512", "SPI", "not_sure"])
		self.assertIn("wireless_protocol", seen["wireless"])
		self.assertNotIn("wireless_protocol", seen["indoorDry"])


class FinderRuntimeContent(unittest.TestCase):
	def test_manager_capability_and_controller_facets(self):
		with load_service(ROOT+'.portal.staff') as (staff,_):
			self.assertIn('ilL Product Finder Manager',staff.CAPABILITIES['finder'])
		self.assertIn('ilL-Attribute-Controller Type',facets.FACETS['controller_type']['doctypes'])
		self.assertIn('ilL-Attribute-Mounting Type',facets.FACETS['controller_mounting']['doctypes'])

	def test_client_option_no_preference_and_sanitized_help(self):
		with load_service(FINDER+'.definition') as (definition,frappe):
			frappe.utils.sanitize_html=lambda value:'<p>Safe</p>'
			self.assertEqual(definition.safe_learn_more('<script>unsafe()</script>'),'<p>Safe</p>')
			option=Record(value='any',label='Any',is_no_preference=1)
			self.assertTrue(definition.option_payload(option,[])['noPreference'])
