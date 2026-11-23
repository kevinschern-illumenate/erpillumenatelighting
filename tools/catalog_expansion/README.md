# Catalog expansion

Tools that find the products the price list sells but the site cannot configure, build
version 2 catalogs for them from records already on the site, and import them through the
Catalog Builder API. They also make the Catalog Builder's starter library.

The November 2026 run is committed in [`catalogs/`](catalogs/); [`catalogs/SUMMARY.md`](catalogs/SUMMARY.md)
lists every template, the price basis and what was skipped. It added 136 templates and
5,722 records, and changed nothing that already existed.

## Workflow

```bash
# 1. Snapshot the live records the generator reads (read-only)
python -m tools.catalog_expansion.fetch_live --site https://<site> --out /tmp/snapshot

# 2. Build one catalog per family from the snapshot and the price list workbook
python -m tools.catalog_expansion.build --snapshot /tmp/snapshot \
    --price-list ilLumenate_Price_List_10-2026.xlsx --out tools/catalog_expansion/catalogs

# 3. Validate locally (the committed reference snapshot can be stale, so skip it)
python -m tools.fixture_builder --config tools/catalog_expansion/catalogs/fixture_ca01.yaml --output /tmp/csv --no-reference

# 4. Server Check (always rolls back), then Import (only after a Passed Check)
python -m tools.catalog_expansion.submit --site https://<site> tools/catalog_expansion/catalogs/*.yaml
python -m tools.catalog_expansion.submit --site https://<site> --import tools/catalog_expansion/catalogs/*.yaml

# 5. Dry-run quote every new fixture template (no ilL-Configured-Fixture is saved)
python -m tools.catalog_expansion.verify --site https://<site> tools/catalog_expansion/catalogs/fixture_*.yaml
```

The API calls authenticate with whatever the HTTP client sends (an API key header, or an
authenticating proxy). The user needs **ilL Catalog Publisher**. Records that already exist
are declared as `external_links`, and an Import never updates them. Re-running the build
after an import skips everything already imported.

## What the generator assumes

**Linear fixtures** (`fixtures.py`). Every price-listed family with profile specs but
without all four `ILL-<family>-<SW|DW|TW|FS>` templates gets the missing ones:

- Options (finishes, lenses, mounting methods, endcap styles) come from the family's
  extrusion kit, the same components the kit ships with. A family without a kit (Tower
  [OP]) takes them from its profile specs, Profile-Lens relationships, accessory specs and
  price-list kit line.
- Price per foot is the cheapest standard-output Dry price-list line for the package. The
  price list builds a fixture as kit MSRP ÷ 6.56 ft + tape MSRP/ft, so a lens or mounting
  upgrade adds the same amount per foot to every package. Those differences become per-foot
  `msrp_adder`s. Damp is +$0.50/ft. High output is charged by the existing tape offerings'
  pricing class.
- Environment ratings are Dry and Damp, like the active Rainier templates. Wet is not
  offered (most profile specs only declare Dry).
- Tape offerings, feed lengths, driver eligibility and the 30 spec submittal field
  mappings are copied from the active Rainier [SF] / St. Helens [SF] template of the same
  package. Endcap and mounting maps come from the kit maps, with quantity rules from the
  accessory specs.
- A family whose endcaps or clips are stocked in packs (Chimney [DR-2]: `ACC-CH02-WC` /
  `ACC-CH02-CC` as "Pack of 6") fails every fixture quote, so its templates are set to
  **Internal Only** until the Item's stock UOM is changed to Ea.
- New templates have no Webflow Product, spec sheet or submittal PDF. The configurator
  works without them; attach files and link a listing before publishing.

**Tape, neon, kits, drivers, controllers** (`others.py`). Each new template is patterned
on the closest active template of its kind (listed in `TAPES`, `KITS`, `DRIVERS`,
`CONTROLLERS`). The Items already exist; specs copy a sibling spec with package, lumens,
watts (scaled with lumens) and CRI replaced. Single-channel white tape gets the universal
dimming drivers; multi-channel tape gets the non-dimming drivers used behind decoders, as on
the site today.

## Starter library

`starters.py` copies complete product families from the site and renames them to code
`DEMO` and series `Example Series`. They are written to `tools/fixture_builder/templates/starters/`,
and `python -m tools.fixture_builder.catalog_starters` validates them and refreshes
`tools/yaml_builder_ui/src/catalog-starters.json`. The Catalog Builder's **New product**
dialog lists them before the minimal examples:

```bash
python -m tools.catalog_expansion.starters --snapshot /tmp/snapshot
python -m tools.fixture_builder.catalog_starters
cd tools/yaml_builder_ui && npm test && npm run build:erp
```
