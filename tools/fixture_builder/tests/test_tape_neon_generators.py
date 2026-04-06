"""Unit tests for Tape/Neon generators in the Fixture Builder CLI."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import unittest

from tools.fixture_builder.config_schema import (
    FixtureBuilderConfig,
    TapeSpecDef,
    TapeOfferingDef,
    TapeNeonAllowedOptionDef,
    TapeNeonAllowedSpecDef,
    TapeNeonTemplateDef,
    NeonSubmittalMappingDef,
    TapeNeonWebflowDef,
    load_config,
    save_config,
)
from tools.fixture_builder.generators import (
    gen_tape_item_csv,
    gen_spec_led_tape,
    gen_rel_tape_offering,
    gen_tape_neon_template,
    gen_neon_submittal_mapping,
    gen_tape_neon_webflow,
)
from tools.fixture_builder.__main__ import (
    validate_config,
    generate_all,
    generate_all_tape_neon,
)


def _tape_config() -> FixtureBuilderConfig:
    """Build a minimal LED Tape config for testing."""
    return FixtureBuilderConfig(
        mode="new-family",
        product_type="tape",
        series_name="Flex",
        series_code="FX",
        tape_specs=[
            TapeSpecDef(
                item_code="TAPE-FS-24V-4.4W",
                led_package="FS",
                product_category="LED Tape",
                input_voltage="24V DC",
                watts_per_foot=4.4,
                lumens_per_foot=400,
                cri_typical=97,
                led_pitch_mm=11.1,
                pcb_mounting="Adhesive Backed",
                pcb_finish="White",
                cut_increment_mm=55.55,
                dimming_protocols=["TRIAC", "0-10V", "DALI"],
            ),
            TapeSpecDef(
                item_code="TAPE-SW-24V-2.2W",
                led_package="SW",
                product_category="LED Tape",
                input_voltage="24V DC",
                watts_per_foot=2.2,
                lumens_per_foot=200,
                cri_typical=90,
                led_pitch_mm=22.2,
                cut_increment_mm=66.66,
                dimming_protocols=["TRIAC"],
            ),
        ],
        tape_offerings=[
            TapeOfferingDef(tape_spec="TAPE-FS-24V-4.4W", cct="2700K", cri=97, sdcm=3,
                            led_package="FS", output_level="Standard"),
            TapeOfferingDef(tape_spec="TAPE-FS-24V-4.4W", cct="3000K", cri=97, sdcm=3,
                            led_package="FS", output_level="Standard"),
            TapeOfferingDef(tape_spec="TAPE-SW-24V-2.2W", cct="3000K", cri=90, sdcm=3,
                            led_package="SW", output_level="Standard"),
        ],
        tape_neon_templates=[
            TapeNeonTemplateDef(
                template_code="ILL-FX-FS",
                template_name="Flex Full Spectrum",
                product_category="LED Tape",
                series="Flex",
                default_tape_spec="TAPE-FS-24V-4.4W",
                base_price_msrp=25.0,
                price_per_ft_msrp=8.5,
                leader_allowance_mm=15,
                allowed_tape_specs=[
                    TapeNeonAllowedSpecDef(tape_spec="TAPE-FS-24V-4.4W",
                                           is_default=True, environment_rating="Dry"),
                ],
                allowed_options=[
                    TapeNeonAllowedOptionDef(option_type="CCT", value="2700K",
                                             is_default=True, msrp_adder=0),
                    TapeNeonAllowedOptionDef(option_type="CCT", value="3000K",
                                             msrp_adder=0),
                    TapeNeonAllowedOptionDef(option_type="Output Level", value="Standard",
                                             is_default=True, msrp_adder=0),
                    TapeNeonAllowedOptionDef(option_type="Environment Rating", value="Dry",
                                             is_default=True, msrp_adder=0),
                    TapeNeonAllowedOptionDef(option_type="Feed Direction", value="Single Feed",
                                             is_default=True, msrp_adder=0),
                ],
            ),
        ],
        neon_submittal_mapping=NeonSubmittalMappingDef(),
        tape_neon_webflow=TapeNeonWebflowDef(product_category="led-tape"),
    )


def _neon_config() -> FixtureBuilderConfig:
    """Build a minimal LED Neon config for testing."""
    return FixtureBuilderConfig(
        mode="new-family",
        product_type="neon",
        series_name="NeonFlex",
        series_code="NF",
        tape_specs=[
            TapeSpecDef(
                item_code="NEON-FS-24V-6W",
                led_package="FS",
                product_category="LED Neon",
                input_voltage="24V DC",
                watts_per_foot=6.0,
                lumens_per_foot=500,
                cri_typical=95,
                led_pitch_mm=8.3,
                pcb_mounting="Channel Mounted",
                pcb_finish="White",
                cut_increment_mm=50.0,
                dimming_protocols=["TRIAC", "0-10V"],
            ),
        ],
        tape_offerings=[
            TapeOfferingDef(tape_spec="NEON-FS-24V-6W", cct="2700K", cri=95, sdcm=3,
                            led_package="FS", output_level="Standard"),
            TapeOfferingDef(tape_spec="NEON-FS-24V-6W", cct="3000K", cri=95, sdcm=3,
                            led_package="FS", output_level="Standard"),
        ],
        tape_neon_templates=[
            TapeNeonTemplateDef(
                template_code="ILL-NF-FS",
                template_name="NeonFlex Full Spectrum",
                product_category="LED Neon",
                series="NeonFlex",
                default_tape_spec="NEON-FS-24V-6W",
                base_price_msrp=50.0,
                price_per_ft_msrp=15.0,
                leader_allowance_mm=20,
                allowed_tape_specs=[
                    TapeNeonAllowedSpecDef(tape_spec="NEON-FS-24V-6W",
                                           is_default=True, environment_rating="Wet"),
                ],
                allowed_options=[
                    TapeNeonAllowedOptionDef(option_type="CCT", value="2700K",
                                             is_default=True),
                    TapeNeonAllowedOptionDef(option_type="CCT", value="3000K"),
                    TapeNeonAllowedOptionDef(option_type="Output Level", value="Standard",
                                             is_default=True),
                    TapeNeonAllowedOptionDef(option_type="Environment Rating", value="Wet",
                                             is_default=True),
                    TapeNeonAllowedOptionDef(option_type="IP Rating", value="IP67",
                                             is_default=True),
                    TapeNeonAllowedOptionDef(option_type="Mounting Method",
                                             value="Surface Mount", is_default=True),
                    TapeNeonAllowedOptionDef(option_type="Finish", value="White",
                                             is_default=True),
                    TapeNeonAllowedOptionDef(option_type="Endcap Style", value="Solid",
                                             is_default=True),
                    TapeNeonAllowedOptionDef(option_type="Feed Direction",
                                             value="Single Feed", is_default=True),
                ],
            ),
        ],
        neon_submittal_mapping=NeonSubmittalMappingDef(),
        tape_neon_webflow=TapeNeonWebflowDef(product_category="led-neon"),
    )


def _read_csv(filepath: str) -> tuple[list[str], list[list[str]]]:
    """Read a CSV and return (headers, data_rows)."""
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)
    return headers, rows


# ── Validation Tests ──────────────────────────────────────────────────

class TestTapeNeonValidation(unittest.TestCase):
    """Test validate_config for tape/neon product types."""

    def test_valid_tape_config(self):
        errors = validate_config(_tape_config())
        self.assertEqual(errors, [])

    def test_valid_neon_config(self):
        errors = validate_config(_neon_config())
        self.assertEqual(errors, [])

    def test_missing_series_name(self):
        config = _tape_config()
        config.series_name = ""
        errors = validate_config(config)
        self.assertIn("series_name is required", errors)

    def test_missing_tape_specs_new_family(self):
        config = _tape_config()
        config.tape_specs = []
        errors = validate_config(config)
        self.assertTrue(any("tape_spec" in e.lower() for e in errors))

    def test_missing_templates(self):
        config = _tape_config()
        config.tape_neon_templates = []
        errors = validate_config(config)
        self.assertTrue(any("tape_neon_template" in e.lower() for e in errors))

    def test_invalid_offering_reference(self):
        config = _tape_config()
        config.tape_offerings.append(
            TapeOfferingDef(tape_spec="NONEXISTENT", cct="2700K", led_package="FS")
        )
        errors = validate_config(config)
        self.assertTrue(any("NONEXISTENT" in e for e in errors))

    def test_invalid_template_spec_reference(self):
        config = _tape_config()
        config.tape_neon_templates[0].allowed_tape_specs.append(
            TapeNeonAllowedSpecDef(tape_spec="NONEXISTENT")
        )
        errors = validate_config(config)
        self.assertTrue(any("NONEXISTENT" in e for e in errors))

    def test_wrong_product_category(self):
        config = _tape_config()
        config.tape_neon_templates[0].product_category = "LED Neon"  # Should be LED Tape
        errors = validate_config(config)
        self.assertTrue(any("product_category" in e for e in errors))

    def test_fixture_mode_ignores_tape_validation(self):
        """Fixture product type should not trigger tape validation."""
        config = FixtureBuilderConfig(
            product_type="fixture",
            mode="new-variant",
            series_name="Test",
        )
        errors = validate_config(config)
        # Should not complain about missing tape_specs
        self.assertFalse(any("tape" in e.lower() for e in errors))


# ── Item CSV Tests ────────────────────────────────────────────────────

class TestTapeItemCSV(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_tape_item_csv.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_tape_item_csv.HEADERS)

    def test_row_count(self):
        """Should have 2 rows (one per tape spec)."""
        path = gen_tape_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 2)

    def test_item_codes(self):
        path = gen_tape_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        codes = [r[0] for r in rows]
        self.assertIn("TAPE-FS-24V-4.4W", codes)
        self.assertIn("TAPE-SW-24V-2.2W", codes)

    def test_item_group(self):
        path = gen_tape_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        for r in rows:
            self.assertEqual(r[1], "LED Tape")

    def test_not_variant(self):
        path = gen_tape_item_csv.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        for r in rows:
            self.assertEqual(r[5], "0")  # Has Variants = 0


# ── Spec LED Tape Tests ──────────────────────────────────────────────

class TestSpecLedTape(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_spec_led_tape.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_spec_led_tape.HEADERS)

    def test_primary_rows(self):
        """Should have 2 primary rows."""
        path = gen_spec_led_tape.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        primary = [r for r in rows if r[0] != ""]
        self.assertEqual(len(primary), 2)

    def test_dimming_continuation_rows(self):
        """First spec has 3 protocols → 1 primary + 2 continuation = 3 rows.
        Second spec has 1 protocol → 1 row. Total = 4."""
        path = gen_spec_led_tape.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 4)

    def test_continuation_row_format(self):
        """Continuation rows should have blank item code and only protocol populated."""
        path = gen_spec_led_tape.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        # Row 1 is continuation of first spec (0-10V)
        self.assertEqual(rows[1][0], "")   # Blank item code
        self.assertEqual(rows[1][13], "0-10V")  # Protocol

    def test_spec_fields(self):
        path = gen_spec_led_tape.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        first = rows[0]
        self.assertEqual(first[0], "TAPE-FS-24V-4.4W")
        self.assertEqual(first[1], "FS")        # LED Package
        self.assertEqual(first[2], "LED Tape")   # Product Category
        self.assertEqual(first[4], "4.4")        # Watts per Foot
        self.assertEqual(first[6], "97")         # CRI
        self.assertEqual(first[13], "TRIAC")     # First dimming protocol


# ── Rel Tape Offering Tests ──────────────────────────────────────────

class TestRelTapeOffering(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_rel_tape_offering.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_rel_tape_offering.HEADERS)

    def test_row_count(self):
        """Should have 3 offerings."""
        path = gen_rel_tape_offering.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 3)

    def test_offering_data(self):
        path = gen_rel_tape_offering.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        first = rows[0]
        self.assertEqual(first[0], "TAPE-FS-24V-4.4W")
        self.assertEqual(first[1], "2700K")
        self.assertEqual(first[2], "97")
        self.assertEqual(first[4], "FS")


# ── Tape Neon Template Tests ─────────────────────────────────────────

class TestTapeNeonTemplate(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_tape_neon_template.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_tape_neon_template.HEADERS)

    def test_template_code(self):
        path = gen_tape_neon_template.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        primary = [r for r in rows if r[0] != ""]
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0][0], "ILL-FX-FS")

    def test_has_child_rows(self):
        """Should have continuation rows for allowed specs and options."""
        path = gen_tape_neon_template.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        total = len(rows)
        primary = sum(1 for r in rows if r[0] != "")
        self.assertGreater(total, primary)

    def test_child_row_count(self):
        """1 allowed_spec + 5 allowed_options = 6 child rows.
        First child goes on primary row, so total = 1 primary + 5 continuation = 6."""
        path = gen_tape_neon_template.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        self.assertEqual(len(rows), 6)

    def test_neon_template_with_more_options(self):
        """Neon config has more option types."""
        config = _neon_config()
        path = gen_tape_neon_template.generate(config, self.tmpdir)
        _, rows = _read_csv(path)
        primary = [r for r in rows if r[0] != ""]
        self.assertEqual(primary[0][0], "ILL-NF-FS")
        self.assertEqual(primary[0][3], "LED Neon")
        # 1 spec + 9 options = 10 children, total rows = 10
        self.assertEqual(len(rows), 10)


# ── Neon Submittal Mapping Tests ─────────────────────────────────────

class TestNeonSubmittalMapping(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_neon_submittal_mapping.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_neon_submittal_mapping.HEADERS)

    def test_uses_defaults(self):
        """With no source CSV, should use DEFAULT_MAPPINGS."""
        path = gen_neon_submittal_mapping.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        expected_count = len(gen_neon_submittal_mapping.DEFAULT_MAPPINGS)
        self.assertEqual(len(rows), expected_count)

    def test_template_code_in_rows(self):
        path = gen_neon_submittal_mapping.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        for r in rows:
            self.assertEqual(r[0], "ILL-FX-FS")

    def test_multiple_templates(self):
        """Multiple templates should multiply the rows."""
        config = _neon_config()
        # Add a second template
        config.tape_neon_templates.append(TapeNeonTemplateDef(
            template_code="ILL-NF-SW",
            template_name="NeonFlex Static White",
            product_category="LED Neon",
        ))
        path = gen_neon_submittal_mapping.generate(config, self.tmpdir)
        _, rows = _read_csv(path)
        expected = len(gen_neon_submittal_mapping.DEFAULT_MAPPINGS) * 2
        self.assertEqual(len(rows), expected)


# ── Tape Neon Webflow Tests ──────────────────────────────────────────

class TestTapeNeonWebflow(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_headers(self):
        path = gen_tape_neon_webflow.generate(self.config, self.tmpdir)
        headers, _ = _read_csv(path)
        self.assertEqual(headers, gen_tape_neon_webflow.HEADERS)

    def test_product_type(self):
        path = gen_tape_neon_webflow.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        primary = [r for r in rows if r[0] != ""]
        self.assertEqual(primary[0][2], "Tape Neon Template")

    def test_has_configurator_steps(self):
        """Should have continuation rows for configurator steps."""
        path = gen_tape_neon_webflow.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        total = len(rows)
        primary = sum(1 for r in rows if r[0] != "")
        self.assertGreater(total, primary)

    def test_product_category(self):
        path = gen_tape_neon_webflow.generate(self.config, self.tmpdir)
        _, rows = _read_csv(path)
        primary = [r for r in rows if r[0] != ""]
        self.assertEqual(primary[0][3], "led-tape")

    def test_neon_webflow(self):
        config = _neon_config()
        path = gen_tape_neon_webflow.generate(config, self.tmpdir)
        _, rows = _read_csv(path)
        primary = [r for r in rows if r[0] != ""]
        self.assertEqual(primary[0][3], "led-neon")


# ── Full Generation Tests ────────────────────────────────────────────

class TestTapeFullGeneration(unittest.TestCase):
    """Test that generate_all produces the correct files for tape mode."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _tape_config()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_new_family_generates_all_6(self):
        results = generate_all(self.config, self.tmpdir)
        self.assertIn("Item CSV.csv", results)
        self.assertIn("ilL-Spec-LED Tape.csv", results)
        self.assertIn("ilL-Rel-Tape Offering.csv", results)
        self.assertIn("ilL-Tape-Neon-Template.csv", results)
        self.assertIn("ilL-Neon-Submittal-Mapping.csv", results)
        self.assertIn("ilL-Webflow-Product.csv", results)
        self.assertEqual(len(results), 6)

    def test_new_variant_generates_3(self):
        self.config.mode = "new-variant"
        results = generate_all(self.config, self.tmpdir)
        self.assertNotIn("Item CSV.csv", results)
        self.assertNotIn("ilL-Spec-LED Tape.csv", results)
        self.assertNotIn("ilL-Rel-Tape Offering.csv", results)
        self.assertIn("ilL-Tape-Neon-Template.csv", results)
        self.assertIn("ilL-Neon-Submittal-Mapping.csv", results)
        self.assertIn("ilL-Webflow-Product.csv", results)
        self.assertEqual(len(results), 3)

    def test_fixture_mode_does_not_generate_tape_csvs(self):
        """Fixture product type should not produce tape CSVs."""
        from tools.fixture_builder.config_schema import (
            ProfileDef, LensDef, ProfileLensMapping, EndcapDef,
            FixtureTemplateDef, DriverDef, SubmittalMappingDef,
        )
        config = FixtureBuilderConfig(
            product_type="fixture",
            mode="new-family",
            series_name="Test",
            series_code="TS",
            profiles=[ProfileDef(family="TS01", finishes=["WH"])],
            lenses=[LensDef(family="TSXX", appearances=["White"])],
            profile_lens_mappings=[ProfileLensMapping(
                profile_families=["TS01"], lens_family="TSXX")],
            endcaps=[EndcapDef(profile_family="TS01", colors=["WH"],
                               styles=["Solid"])],
            fixture_templates=FixtureTemplateDef(
                led_packages=["FS"],
                allowed_finishes=["White"],
                allowed_lenses=["White"],
                allowed_mountings=[],
                allowed_endcap_styles=["Solid"],
                allowed_environment_ratings=["Dry"],
            ),
            drivers=DriverDef(driver_specs=["PS-UNIV-24V-100W-IP66"]),
            submittal_mapping=SubmittalMappingDef(clone_from_template="ILL-AX01-FS"),
        )
        results = generate_all(config, self.tmpdir)
        self.assertNotIn("ilL-Spec-LED Tape.csv", results)
        self.assertNotIn("ilL-Rel-Tape Offering.csv", results)
        self.assertNotIn("ilL-Tape-Neon-Template.csv", results)


# ── YAML Round-Trip Tests ────────────────────────────────────────────

class TestTapeNeonYamlRoundTrip(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_tape_config_round_trip(self):
        config = _tape_config()
        path = os.path.join(self.tmpdir, "tape.yaml")
        save_config(config, path)
        loaded = load_config(path)
        self.assertEqual(loaded.product_type, "tape")
        self.assertEqual(loaded.series_name, "Flex")
        self.assertEqual(len(loaded.tape_specs), 2)
        self.assertEqual(loaded.tape_specs[0].item_code, "TAPE-FS-24V-4.4W")
        self.assertEqual(len(loaded.tape_offerings), 3)
        self.assertEqual(len(loaded.tape_neon_templates), 1)
        self.assertEqual(loaded.tape_neon_templates[0].template_code, "ILL-FX-FS")

    def test_neon_config_round_trip(self):
        config = _neon_config()
        path = os.path.join(self.tmpdir, "neon.yaml")
        save_config(config, path)
        loaded = load_config(path)
        self.assertEqual(loaded.product_type, "neon")
        self.assertEqual(loaded.series_name, "NeonFlex")
        self.assertEqual(len(loaded.tape_specs), 1)
        self.assertEqual(loaded.tape_specs[0].product_category, "LED Neon")

    def test_load_example_tape_yaml(self):
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "example_tape_config.yaml"
        )
        if os.path.exists(yaml_path):
            config = load_config(yaml_path)
            self.assertEqual(config.product_type, "tape")
            self.assertEqual(config.series_name, "Flex")
            self.assertEqual(len(config.tape_specs), 2)

    def test_load_example_neon_yaml(self):
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "templates", "example_neon_config.yaml"
        )
        if os.path.exists(yaml_path):
            config = load_config(yaml_path)
            self.assertEqual(config.product_type, "neon")
            self.assertEqual(config.series_name, "NeonFlex")


if __name__ == "__main__":
    unittest.main()
