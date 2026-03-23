# Fixture Builder CLI

Standalone Python CLI tool that generates all **11 CSV import files** needed to onboard a new fixture profile family (or LED package variant) into ERPNext.

## Requirements

- Python 3.10+
- `pyyaml` — `pip install pyyaml`

No Frappe/ERPNext runtime dependency.

## Quick Start

```bash
# From the repo root:

# 1. Generate CSVs from a YAML config file
python -m tools.fixture_builder --config tools/fixture_builder/templates/castle_series.yaml --output ./output/castle/

# 2. Interactive mode (prompts for all values)
python -m tools.fixture_builder --interactive --output ./output/my_series/

# 3. New LED variant mode (reuses existing profiles/lenses, generates 6 of 11 CSVs)
python -m tools.fixture_builder --mode new-variant --config variant.yaml --output ./output/

# 4. Clone submittal mappings from an existing CSV
python -m tools.fixture_builder --config config.yaml --output ./output/ \
    --source-submittal-csv "h:/My Drive/Data Import Templates/ilL-Spec-Submittal-Mapping.csv"
```

## Modes

| Mode | CSVs Generated | Use Case |
|------|---------------|----------|
| `new-family` (default) | All 11 | New profile family from scratch |
| `new-variant` | 6 of 11 | New LED package for existing profiles |

### New Family (all 11 CSVs)

1. `Item CSV.csv` — ERPNext Item master (profiles, lenses, accessories, endcaps)
2. `ilL-Spec-Profile.csv` — Profile spec with environment ratings
3. `ilL-Spec-Lens.csv` — Lens specs
4. `ilL-Spec-Accessory.csv` — Mounting, joiner, and endcap accessories
5. `ilL-Rel-Profile Lens.csv` — Profile → lens compatibility

### Both Modes (6 CSVs)

6. `ilL-Fixture-Template.csv` — Template definitions with child tables
7. `ilL-Rel-Mounting-Accessory-Map.csv` — Mounting accessory mapping
8. `ilL-Rel-Endcap-Map.csv` — Endcap mapping
9. `ilL-Rel-Driver-Eligibility.csv` — Driver eligibility
10. `ilL-Spec-Submittal-Mapping.csv` — Submittal field mappings (cloned from source)
11. `ilL-Webflow-Product.csv` — Webflow product skeleton

## Configuration

See `templates/example_config.yaml` for a full annotated example.

### Key Sections

- **series_name / series_code** — Series identity
- **profiles** — Profile family definitions (family code, finishes, dimensions)
- **lenses** — Lens family definitions (appearances, shape code)
- **profile_lens_mappings** — Which lens families are compatible with which profiles
- **accessories** — Mounting clips, joiners (non-variant items)
- **endcaps** — Endcap definitions per profile (auto-expanded into color × style variants)
- **fixture_templates** — LED packages, allowed options, pricing
- **drivers** — Driver eligibility specs
- **submittal_mapping** — Template to clone mappings from
- **webflow** — Webflow product skeleton settings

### Convention-Based Item Codes

Item codes are auto-derived from family/finish/lens patterns:

| Type | Pattern | Example |
|------|---------|---------|
| Profile template | `CH-{FAMILY}` | `CH-CA01` |
| Profile variant | `CH-{FAMILY}-{FINISH}` | `CH-CA01-WH` |
| Lens template | `LNS-{FAMILY}` | `LNS-CAXX` |
| Lens variant | `LNS-{FAMILY}-{SHAPE}-{COLOR}` | `LNS-CAXX-WH-FR` |
| Endcap template | `EC-{FAMILY}` | `EC-CA01` |
| Endcap variant | `EC-{FAMILY}-{COLOR}-{STYLE}` | `EC-CA01-WH-NO` |
| Accessory | `ACC-{FAMILY}-{SUFFIX}` | `ACC-CAXX-MC` |
| Fixture template | `ILL-{FAMILY}-{LED_PKG}` | `ILL-CA01-FS` |

### Endcap Color Mapping

| Profile Finish | Endcap Color |
|---------------|-------------|
| WH (White) | WH (White) |
| BK (Black) | BK (Black) |
| SV (Silver) | GR (Grey) |

## Testing

```bash
python -m pytest tools/fixture_builder/tests/ -v
```

## Project Structure

```
tools/fixture_builder/
├── __init__.py
├── __main__.py          # CLI entry point
├── config_schema.py     # YAML config dataclasses
├── prompts.py           # Interactive input functions
├── generators/
│   ├── common.py        # Shared utilities
│   ├── gen_item_csv.py
│   ├── gen_spec_profile.py
│   ├── gen_spec_lens.py
│   ├── gen_spec_accessory.py
│   ├── gen_rel_profile_lens.py
│   ├── gen_fixture_template.py
│   ├── gen_rel_mounting_map.py
│   ├── gen_rel_endcap_map.py
│   ├── gen_rel_driver_eligibility.py
│   ├── gen_spec_submittal_mapping.py
│   └── gen_webflow_product.py
├── templates/
│   ├── example_config.yaml
│   └── castle_series.yaml
└── tests/
    ├── __init__.py
    └── test_generators.py
```
