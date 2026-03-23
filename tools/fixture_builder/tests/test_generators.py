"""Unit tests for the Fixture Builder CLI tool.

Tests config parsing, each generator's output format, header accuracy,
multi-line continuation rows, and convention derivation.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import unittest

from tools.fixture_builder.config_schema import (
    FixtureBuilderConfig,
    ProfileDef,
    LensDef,
    AccessoryDef,
    EndcapDef,
    ProfileLensMapping,
    FixtureTemplateDef,
    TemplateAllowedOptions,
    DriverDef,
    SubmittalMappingDef,
    WebflowDef,
    load_config,
    save_config,
)
from tools.fixture_builder.generators import (
    gen_item_csv,
    gen_spec_profile,
    gen_spec_lens,
    gen_spec_accessory,
    gen_rel_profile_lens,
    gen_fixture_template,
    gen_rel_mounting_map,
    gen_rel_endcap_map,
    gen_rel_driver_eligibility,
    gen_spec_submittal_mapping,
    gen_webflow_product,
)
from tools.fixture_builder.__main__ import validate_config, generate_all


def _castle_config() -> FixtureBuilderConfig:
    """Build a Castle series (CA01/CA02) config for testing."""
    return FixtureBuilderConfig(
        mode="new-family",
        series_name="Castle",
        series_code="CA",
        profiles=[
            ProfileDef(
                family="CA02", variant_label="[WD]",
                finishes=["WH", "BK", "SV"],
                width_mm=30.5, height_mm=12.8,
                stock_length_mm=2000, max_assembled_length_mm=2500,
                is_cuttable=True, supports_joiners=False,
                lens_interface="Snap-in", environment_ratings=["Dry"],
            ),
            ProfileDef(
                family="CA01", variant_label="[NR]",
                finishes=["WH", "BK", "SV"],
                width_mm=23.5, height_mm=12.8,
                stock_length_mm=2000, max_assembled_length_mm=2500,
                is_cuttable=True, supports_joiners=False,
                lens_interface="Snap-in", environment_ratings=["Dry"],
            ),
        ],
        lenses=[
            LensDef(
                family="CAXX",
                appearances=["Black", "Clear", "Frosted", "White"],
                shape="WH", stock_type="Stick", stock_length_mm=2000,
            ),
        ],
        profile_lens_mappings=[
            ProfileLensMapping(profile_families=["CA01", "CA02"], lens_family="CAXX"),
        ],
        accessories=[
            AccessoryDef(item_code="ACC-CA01-PV", accessory_type="Mounting",
                         profile_family="CA01", mounting_method="Pivot Clip",
                         qty_rule_type="Per x mm", qty_rule_value=304.8),
            AccessoryDef(item_code="ACC-CAXX-MC", accessory_type="Mounting",
                         profile_family="CAXX", mounting_method="Mounting Clip",
                         qty_rule_type="Per x mm", qty_rule_value=304.8),
        ],
        endcaps=[
            EndcapDef(profile_family="CA02", colors=["WH", "BK", "GR"],
                      styles=["Solid", "Feed Through"], allowance_override_per_side_mm=2.0),
            EndcapDef(profile_family="CA01", colors=["WH", "BK", "GR"],
                      styles=["Solid", "Feed Through"], allowance_override_per_side_mm=2.0),
        ],
        fixture_templates=FixtureTemplateDef(
            led_packages=["FS", "SW", "TW"],
            allowed_finishes=["White", "Black", "Anodized Silver"],
            allowed_lenses=["White", "Frosted", "Clear", "Black"],
            allowed_mountings=["Mounting Clip", "Pivot Clip"],
            allowed_endcap_styles=["Solid", "Feed Through"],
            allowed_environment_ratings=["Dry"],
        ),
        drivers=DriverDef(driver_specs=["PS-UNIV-24V-100W-IP66"]),
        submittal_mapping=SubmittalMappingDef(clone_from_template="ILL-AX01-FS"),
        webflow=WebflowDef(product_category="linear-fixtures"),
    )


def _read_csv(filepath: str) -> tuple[list[str], list[list[str]]]:
    """Read a CSV and return (headers, data_rows)."""
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)
    return headers, rows


class TestConfigParsing(unittest.TestCase):
    """Test YAML config loading and saving."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_round_trip(self):
        """Config should survive save → load cycle."""
        config = _castle_config()
        path = os.path.join(self.tmpdir, "test.yaml")
        save_config(config, path)
        loaded = load_config(path)
        self.assertEqual(loaded.series_name, "Castle")
        self.assertEqual(len(loaded.profiles), 2)
        self.assertEqual(loaded.profiles[0].family, "CA02")
        self.assertEqual(loaded.profiles[1].finishes, ["WH", "BK", "SV"])

    def test_load_castle_yaml(self):
        """Load the Castle template YAML."""
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "castle_series.yaml"
        )
        if os.path.exists(yaml_path):
            config = load_config(yaml_path)
            self.assertEqual(config.series_name, "Castle")
            self.assertEqual(len(config.profiles), 2)


class TestValidation(unittest.TestCase):
    """Test config validation."""

    def test_valid_config(self):
        errors = validate_config(_castle_config())
        self.assertEqual(errors, [])

    def test_missing_series_name(self):
        config = _castle_config()
        config.series_name = ""
        errors = validate_config(config)
        self.assertIn("series_name is required", errors)

    def test_missing_profiles_new_family(self):
        config = _castle_config()
        config.profiles = []
        errors = validate_config(config)
        self.assertTrue(any("profile" in e.lower() for e in errors))


class TestItemCSV(unittest.TestCase):
    """Test Item CSV.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_item_csv.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_item_csv.HEADERS)

    def test_profile_templates(self):
        """Should have a profile template for each profile family."""
        path = gen_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        profile_rows = [r for r in rows if r[0].startswith("CH-CA")]
        self.assertEqual(len(profile_rows), 2)  # CA02, CA01
        self.assertEqual(profile_rows[0][0], "CH-CA02")
        self.assertEqual(profile_rows[0][5], "1")  # Has Variants

    def test_lens_template_with_continuation(self):
        """Lens template should have primary row + continuation for Lens Color."""
        path = gen_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        lens_primary = [r for r in rows if r[0] == "LNS-CAXX"]
        self.assertEqual(len(lens_primary), 1)
        # Next row should be continuation (blank item code, Lens Color attribute)
        lens_idx = rows.index(lens_primary[0])
        cont_row = rows[lens_idx + 1]
        self.assertEqual(cont_row[0], "")  # Blank primary key
        self.assertEqual(cont_row[10], "Lens Color")  # Attribute

    def test_endcap_template_with_continuation(self):
        """Endcap templates should have primary + continuation rows."""
        path = gen_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        ec_rows = [r for r in rows if r[0].startswith("EC-CA")]
        self.assertEqual(len(ec_rows), 2)  # CA02, CA01
        # Check both have continuation rows
        for ec_row in ec_rows:
            idx = rows.index(ec_row)
            self.assertEqual(rows[idx + 1][10], "Endcap Type")

    def test_accessory_non_variant(self):
        """Accessories should not have Has Variants."""
        path = gen_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        acc_rows = [r for r in rows if r[0].startswith("ACC-")]
        for r in acc_rows:
            self.assertEqual(r[5], "0")  # Has Variants = 0


class TestSpecProfile(unittest.TestCase):
    """Test ilL-Spec-Profile.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_spec_profile.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_spec_profile.HEADERS)

    def test_row_count(self):
        """Should have 6 rows: 2 families × 3 finishes."""
        path = gen_spec_profile.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 6)

    def test_item_code_format(self):
        path = gen_spec_profile.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        codes = [r[0] for r in rows]
        self.assertIn("CH-CA02-WH", codes)
        self.assertIn("CH-CA01-BK", codes)

    def test_dimensions(self):
        path = gen_spec_profile.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        ca02_row = [r for r in rows if r[0] == "CH-CA02-WH"][0]
        self.assertEqual(ca02_row[5], "30.5")  # Width
        self.assertEqual(ca02_row[6], "12.8")  # Height

    def test_environment_rating(self):
        path = gen_spec_profile.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        ca02_row = [r for r in rows if r[0] == "CH-CA02-WH"][0]
        self.assertEqual(ca02_row[13], "Dry")

    def test_multi_env_ratings(self):
        """If multiple env ratings, continuation rows should appear."""
        self.config.profiles[0].environment_ratings = ["Dry", "Wet"]
        path = gen_spec_profile.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # CA02-WH should be followed by a continuation row for "Wet"
        ca02_wh_idx = next(i for i, r in enumerate(rows) if r[0] == "CH-CA02-WH")
        cont_row = rows[ca02_wh_idx + 1]
        self.assertEqual(cont_row[0], "")  # Blank primary
        self.assertEqual(cont_row[13], "Wet")


class TestSpecLens(unittest.TestCase):
    """Test ilL-Spec-Lens.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_spec_lens.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_spec_lens.HEADERS)

    def test_row_count(self):
        """4 appearances → 4 rows."""
        path = gen_spec_lens.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 4)

    def test_item_codes(self):
        path = gen_spec_lens.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        codes = [r[0] for r in rows]
        self.assertIn("LNS-CAXX-WH-BK", codes)
        self.assertIn("LNS-CAXX-WH-CL", codes)
        self.assertIn("LNS-CAXX-WH-FR", codes)
        self.assertIn("LNS-CAXX-WH-WH", codes)


class TestSpecAccessory(unittest.TestCase):
    """Test ilL-Spec-Accessory.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_spec_accessory.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_spec_accessory.HEADERS)

    def test_mounting_accessories(self):
        path = gen_spec_accessory.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        mounting_rows = [r for r in rows if r[1] == "Mounting"]
        self.assertEqual(len(mounting_rows), 2)

    def test_endcap_accessories(self):
        """Endcaps should expand: 2 families × 3 colors × 2 styles = 12."""
        path = gen_spec_accessory.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        endcap_rows = [r for r in rows if r[1] == "Endcap"]
        self.assertEqual(len(endcap_rows), 12)

    def test_endcap_item_codes(self):
        path = gen_spec_accessory.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        codes = [r[0] for r in rows if r[1] == "Endcap"]
        self.assertIn("EC-CA02-WH-NO", codes)
        self.assertIn("EC-CA02-BK-HO", codes)
        self.assertIn("EC-CA01-GR-NO", codes)


class TestRelProfileLens(unittest.TestCase):
    """Test ilL-Rel-Profile Lens.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_rel_profile_lens.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_rel_profile_lens.HEADERS)

    def test_multiline_format(self):
        """Each profile variant should have 1 primary + 3 continuation rows (4 lenses)."""
        path = gen_rel_profile_lens.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # 6 profile variants × 4 lens rows each = 24 total rows
        # But: 6 primary + 18 continuation = 24
        primary_count = sum(1 for r in rows if r[0] != "")
        self.assertEqual(primary_count, 6)
        total = len(rows)
        self.assertEqual(total, 24)  # 6 × 4

    def test_continuation_blank_key(self):
        path = gen_rel_profile_lens.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # Row after first primary should be continuation
        self.assertEqual(rows[0][0], "CH-CA02-WH")
        self.assertEqual(rows[1][0], "")  # Continuation
        self.assertNotEqual(rows[1][3], "")  # Has lens spec


class TestFixtureTemplate(unittest.TestCase):
    """Test ilL-Fixture-Template.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_fixture_template.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_fixture_template.HEADERS)

    def test_template_codes(self):
        """2 families × 3 LED packages = 6 templates."""
        path = gen_fixture_template.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        primary_codes = [r[0] for r in rows if r[0] != ""]
        self.assertEqual(len(primary_codes), 6)
        self.assertIn("ILL-CA02-FS", primary_codes)
        self.assertIn("ILL-CA01-TW", primary_codes)

    def test_has_child_rows(self):
        """Should have continuation rows for allowed options."""
        path = gen_fixture_template.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        total = len(rows)
        primary = sum(1 for r in rows if r[0] != "")
        self.assertGreater(total, primary)  # Has continuation rows


class TestRelMountingMap(unittest.TestCase):
    """Test ilL-Rel-Mounting-Accessory-Map.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_rel_mounting_map.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_rel_mounting_map.HEADERS)

    def test_wildcard_matching(self):
        """ACC-CAXX-MC should match both CA01 and CA02."""
        path = gen_rel_mounting_map.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # CAXX-MC should appear for all CA01 + CA02 templates
        caxx_rows = [r for r in rows if r[4] == "ACC-CAXX-MC"]
        # 2 families × 3 LED packages = 6
        self.assertEqual(len(caxx_rows), 6)

    def test_family_specific(self):
        """ACC-CA01-PV should only match CA01 templates."""
        path = gen_rel_mounting_map.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        ca01_pv = [r for r in rows if r[4] == "ACC-CA01-PV"]
        self.assertEqual(len(ca01_pv), 3)  # 3 LED packages
        for r in ca01_pv:
            self.assertTrue(r[1].startswith("ILL-CA01-"))


class TestRelEndcapMap(unittest.TestCase):
    """Test ilL-Rel-Endcap-Map.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_rel_endcap_map.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_rel_endcap_map.HEADERS)

    def test_row_count(self):
        """2 families × 3 LED pkgs × 3 colors × 2 styles = 36."""
        path = gen_rel_endcap_map.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 36)

    def test_endcap_item_code(self):
        path = gen_rel_endcap_map.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        items = [r[5] for r in rows]
        self.assertIn("EC-CA02-WH-NO", items)
        self.assertIn("EC-CA01-BK-HO", items)


class TestRelDriverEligibility(unittest.TestCase):
    """Test ilL-Rel-Driver-Eligibility.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_rel_driver_eligibility.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_rel_driver_eligibility.HEADERS)

    def test_row_count(self):
        """2 families × 3 LED pkgs × 1 driver = 6."""
        path = gen_rel_driver_eligibility.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 6)

    def test_template_type(self):
        path = gen_rel_driver_eligibility.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        for r in rows:
            self.assertEqual(r[0], "ilL-Fixture-Template")


class TestSpecSubmittalMapping(unittest.TestCase):
    """Test ilL-Spec-Submittal-Mapping.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_spec_submittal_mapping.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_spec_submittal_mapping.HEADERS)

    def test_uses_defaults(self):
        """Without source CSV, should use default mappings."""
        path = gen_spec_submittal_mapping.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # 6 templates × 29 default mappings = 174
        expected = 6 * len(gen_spec_submittal_mapping.DEFAULT_MAPPINGS)
        self.assertEqual(len(rows), expected)

    def test_all_templates_present(self):
        path = gen_spec_submittal_mapping.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        templates = set(r[0] for r in rows)
        self.assertIn("ILL-CA02-FS", templates)
        self.assertIn("ILL-CA01-TW", templates)


class TestWebflowProduct(unittest.TestCase):
    """Test ilL-Webflow-Product.csv generator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_webflow_product.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_webflow_product.HEADERS)

    def test_has_primary_rows(self):
        path = gen_webflow_product.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        primary_names = [r[0] for r in rows if r[0] != ""]
        self.assertEqual(len(primary_names), 6)  # 2 × 3

    def test_product_slug_format(self):
        path = gen_webflow_product.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        slugs = [r[1] for r in rows if r[1] != ""]
        self.assertIn("ill-ca02-fs", slugs)
        self.assertIn("ill-ca01-tw", slugs)

    def test_is_configurable(self):
        path = gen_webflow_product.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # Primary rows should have Is Configurable = 1
        primary_rows = [r for r in rows if r[0] != ""]
        for r in primary_rows:
            self.assertEqual(str(r[13]), "1")


class TestGenerateAll(unittest.TestCase):
    """Test the full generation pipeline."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _castle_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_new_family_generates_11_files(self):
        results = generate_all(self.config, self.tmpdir)
        self.assertEqual(len(results), 11)

    def test_new_variant_generates_6_files(self):
        self.config.mode = "new-variant"
        results = generate_all(self.config, self.tmpdir)
        self.assertEqual(len(results), 6)

    def test_all_files_exist(self):
        results = generate_all(self.config, self.tmpdir)
        for filename, filepath in results.items():
            self.assertTrue(os.path.exists(filepath), f"{filename} not found at {filepath}")

    def test_all_files_have_headers(self):
        results = generate_all(self.config, self.tmpdir)
        for filename, filepath in results.items():
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)
                self.assertGreater(len(headers), 0, f"{filename} has no headers")


class TestEndcapDefExpansion(unittest.TestCase):
    """Test EndcapDef.generate_items()."""

    def test_expansion(self):
        ed = EndcapDef(
            profile_family="CA01",
            colors=["WH", "BK", "GR"],
            styles=["Solid", "Feed Through"],
            allowance_override_per_side_mm=2.0,
        )
        items = ed.generate_items()
        self.assertEqual(len(items), 6)
        codes = [i.item_code for i in items]
        self.assertIn("EC-CA01-WH-NO", codes)
        self.assertIn("EC-CA01-BK-HO", codes)
        self.assertIn("EC-CA01-GR-NO", codes)


class TestTemplateOverrideResolution(unittest.TestCase):
    """Test per-template override resolution via get_options_for_template."""

    def test_fallback_to_global(self):
        """Without overrides, should return global fixture_templates values."""
        config = _castle_config()
        opts = config.get_options_for_template("CA01", "FS")
        self.assertEqual(opts.allowed_finishes, ["White", "Black", "Anodized Silver"])
        self.assertEqual(opts.allowed_lenses, ["White", "Frosted", "Clear", "Black"])

    def test_override_takes_precedence(self):
        """With an override present, it should be returned instead of globals."""
        config = _castle_config()
        config.template_overrides.append(TemplateAllowedOptions(
            profile_family="CA01", led_package="FS",
            allowed_finishes=["White"],
            allowed_lenses=["Frosted"],
            allowed_mountings=["Pivot Clip"],
            allowed_endcap_styles=["Solid"],
            allowed_environment_ratings=["Dry"],
        ))
        opts = config.get_options_for_template("CA01", "FS")
        self.assertEqual(opts.allowed_finishes, ["White"])
        self.assertEqual(opts.allowed_lenses, ["Frosted"])
        self.assertEqual(opts.allowed_mountings, ["Pivot Clip"])

    def test_non_overridden_template_uses_global(self):
        """Templates without overrides still use global."""
        config = _castle_config()
        config.template_overrides.append(TemplateAllowedOptions(
            profile_family="CA01", led_package="FS",
            allowed_finishes=["White"],
        ))
        opts = config.get_options_for_template("CA02", "FS")
        self.assertEqual(opts.allowed_finishes, ["White", "Black", "Anodized Silver"])

    def test_override_used_in_fixture_template_csv(self):
        """CSV generator should pick up per-template overrides."""
        config = _castle_config()
        config.template_overrides.append(TemplateAllowedOptions(
            profile_family="CA01", led_package="FS",
            allowed_finishes=["White"],
            allowed_lenses=["Frosted"],
            allowed_mountings=["Pivot Clip"],
            allowed_endcap_styles=["Solid"],
            allowed_environment_ratings=["Dry"],
        ))
        tmpdir = tempfile.mkdtemp()
        try:
            path = gen_fixture_template.generate(config, tmpdir)
            _, rows = _read_csv(path)
            # Find ILL-CA01-FS rows — primary + its child continuation rows
            ca01_fs_idx = next(i for i, r in enumerate(rows) if r[0] == "ILL-CA01-FS")
            child_options = []
            # Primary row first
            option_type = rows[ca01_fs_idx][12]
            if option_type:
                r = rows[ca01_fs_idx]
                child_options.append((option_type, r[13] or r[14] or r[15] or r[16] or r[17] or r[18]))
            # Then continuation rows (blank primary key) until next primary
            for r in rows[ca01_fs_idx + 1:]:
                if r[0] != "":
                    break  # Hit next template primary row
                option_type = r[12]
                if option_type:
                    child_options.append((option_type, r[13] or r[14] or r[15] or r[16] or r[17] or r[18]))
            finish_opts = [v for t, v in child_options if t == "Finish"]
            self.assertEqual(finish_opts, ["White"])
            lens_opts = [v for t, v in child_options if t == "Lens Appearance"]
            self.assertEqual(lens_opts, ["Frosted"])
        finally:
            shutil.rmtree(tmpdir)


class TestConventionDerivation(unittest.TestCase):
    """Test convention-based code derivation."""

    def test_template_codes(self):
        config = _castle_config()
        codes = config.get_template_codes()
        self.assertEqual(len(codes), 6)
        self.assertIn("ILL-CA02-FS", codes)
        self.assertIn("ILL-CA01-TW", codes)

    def test_wildcard_matching(self):
        from tools.fixture_builder.generators.gen_rel_mounting_map import _matches_family
        self.assertTrue(_matches_family("CAXX", "CA01", "CA"))
        self.assertTrue(_matches_family("CAXX", "CA02", "CA"))
        self.assertFalse(_matches_family("CAXX", "TW01", "CA"))
        self.assertTrue(_matches_family("CA01", "CA01", "CA"))
        self.assertFalse(_matches_family("CA01", "CA02", "CA"))


if __name__ == "__main__":
    unittest.main()
