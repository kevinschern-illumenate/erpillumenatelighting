# ilLumenate YAML Builder

Interactive web UI for authoring `tools.fixture_builder` config files for
**LED Tape**, **LED Neon**, and **Linear Fixtures**.

## Quick start

```powershell
cd tools/yaml_builder_ui
npm install
npm run dev
```

Open the printed URL (default http://localhost:5173). Pick a product type from
the header pills, fill in sections, then click **Download YAML**.

Generated files plug directly into the CLI:

```powershell
python -m tools.fixture_builder --product-type fixture --config <file>.yaml --output ./output/<series>/
```

## Layout

- `src/App.jsx` — main app, tape/neon sections + global shell
- `src/fixtures.jsx` — Linear Fixture sections, serializer, validator, example
- `src/main.jsx` — Vite entrypoint
