# ilLumenate CAD toolkit (draw-to-quote)

A thin AutoCAD front end to the fixture schedule and the System Designer
(`docs/CAD_TOOLKIT_IMPLEMENTATION.md`). AutoCAD draws the geometry; the portal builds the products.

```
AutoCAD (this toolkit)          Portal (illumenate_lighting)                 System Designer
ILSTYLE / ILTAPE / ILROOM  ->   Import Drawing (portal/drawing_import.py) -> new design starts from
ILCAB / ILPSU / ILWIRE          plans every run through the configurators     the drawing's rooms,
ILCHECK -> ILQUOTE (ilq/2)      saves configured builds on the schedule       cabinets and measured
ILRECEIPT <- receipt            keeps package + receipt (ilL-CAD-Import)      home runs
```

## Layout

| Path | What |
| --- | --- |
| `lisp/il-util.lsp`, `il-json.lsp`, `il-math.lsp`, `il-sha256.lsp`, `il-catalog.lsp`, `il-model.lsp`, `il-controls.lsp` | Pure AutoLISP: helpers, JSON, hint math, SHA-256, catalog lookups, model, ILCHECK rules, `ilq/2` writer, receipt. CI runs them. |
| `lisp/il-assets.lsp` | **Generated** layers, linetypes and blocks (riser symbols, plan symbols, title blocks): `npm run cad:export --prefix tools/system_designer`. |
| `lisp/il-core.lsp`, `il-blocks.lsp`, `il-commands.lsp` | AutoCAD side: command wrapper (undo, sysvars, `*error*`), XData (`ILLUMENATE`, schema version and migration), drawing dictionary, `entmake` blocks, the `IL*` commands. |
| `reference/cad_subset.py` | Python reference for the hint math, tested against the configurator's own functions. |
| `test/mini_lisp.py` | A small AutoLISP interpreter so CI can run the pure files (`tests/portal_unit/test_cad_lisp.py`). |
| `test/il-tests.lsp`, `run_tests.scr`, `run_tests.bat` | The golden-case runner for real AutoCAD (`accoreconsole`), plan 3.10. |
| `build/layers.py`, `build/ilLumenate-layers.scr` | DWT layer script from `packages/data/src/layers.json`. |
| `package_bundle.py` | Builds `ilLumenate.bundle` (one joined `ilLumenate.lsp`, `PackageContents.xml`, layer script, README) and a reproducible zip; `--publish` copies it to `illumenate_lighting/public/cad_toolkit/`. |

Golden cases and fixtures live with the System Designer's so Python, TypeScript and LISP share them:
`tools/system_designer/fixtures/cad/` (`lisp-subset.json`, `catalog-records.json` → `catalog.sample.json`,
`packages/valid|invalid/*.json`).

## Rules

- **Hints only.** LISP mirrors cut snap, percent of max run, the equal split and a provisional PSU load sum.
  No PSU sizing, voltage drop, stick packing or BOM math. The import's server numbers always win.
- **No network, no prices.** The catalog is a file downloaded from the portal (`cad-catalog/1`, cost-free,
  checked by `forbidden_keys`). The package never carries prices; the import strips price keys anyway.
- **LT 2024+ and Mac safe core.** Only `entget`/`entmod`/`entmake`, dictionaries and command-line prompts.
  No `vlax-`/`vla-`/`vlr-` and no DCL; the CI source check refuses them.
- **Copies are allowed.** COPY, ARRAY and paste duplicate XData, id included. `il-fix-copies` (run by
  ILUPDATE, ILCHECK and ILQUOTE) keeps the id on the entity still on its own handle (`self`, else the
  oldest), renumbers the rest, drops what a copy must not inherit (a run's portal line key and part
  number, a PSU's fed runs, a fixed DMX address) and hands copied room and wire tags to the nearer owner.
- **Feeds and jumpers.** A run's feed is its first vertex: ILFEED turns the polyline round when it is
  picked near the other end (bulges and break indexes follow). ILJUMPER toggles a break at a vertex, or
  adds a vertex where a line or arc is picked. Feed and jumper markers are owned by the run and redrawn
  by ILUPDATE; the run tag sits halfway along the path.
- **Snapped points.** ILJUMPER and ILFEED ask for points (`getpoint`), so object snaps work, and find the
  run at the point within the pickbox (`il-run-at`; runs meeting there ask which). Placement is exact:
  within `*il-snap-tolerance*` (0.01 in) of a vertex is that vertex, anywhere else adds a vertex at the
  nearest point on the run, and a point off the run says how far off it was.
- **Jumper spans.** A run's `spans` (segment indexes) are drawn across a gap but are jumper cable, not
  tape: `il-run-pieces` splits the run into lit pieces and gives the jumper after each piece its length
  (a span's drawn length, or `jumper_in` at a break). Spans at either end join nothing and are left out
  (ILCHECK `JUMPER_SPAN_AT_END`). Closed runs are walked round to their first vertex, so a jumper on a
  closed run keeps the closing side.
- **Prompts.** `il-choose` asks again on a number outside the list; `il-ask-id` keeps typed ids unique.
  Settings and styles are parsed once per command (`*il-json-cache*`); tags go on their owner's layout
  (`*il-layout*`).
- **Symbol scale.** Plan symbols are drawn in paper inches and inserted at the ILSETUP scale factor;
  changing it in ILSETUP resizes every placed `IL-*` symbol (not title blocks) about its insertion point.
- **Package source and sheets (0.5.0).** `ilq/2` packages say who wrote them
  (`source: {tool: "autocad", version, platform, input: "ilq"}`) and list one sheet per layout that owns a
  run (`sheets[]`: id is a CadId slug of the layout name, `Model` for model space; label is the layout
  name). Runs carry `sheet` and `identity: "xdata"`; rooms carry `sheet` when their layout has runs. A
  sheet's scale is `verified` after ILSCALE, else `declared` (AutoCAD drawings always have units), so it
  always agrees with `drawing.scale_verified`. The content hash (`il-package-content`) leaves source,
  sheets and layouts out, so hashes match 0.4.x for an unchanged drawing.
- **Multi-run groups (0.6.0).** A group is runs quoted as one multi-run group line (the portal's
  `ilL-Configured-Group`): one schedule Type, room, style and power plan, shared supplies on their own
  lines. `ILGROUP` gathers drawn runs under a group tag (`IL-GROUPTAG`, XData kind `GROUP`, run ids in
  `runs`); `ILSTACK` makes one drawn run stand for N identical runs (`copies`, label stem `label`), for
  shelves stacked above each other, and gives it a group when it has none. The package writes `groups`
  and a run's `copies`/`label` only when used, so drawings without groups keep their 0.5.x content
  hash. ILCHECK adds `GROUP_*` and `COPIES_NOT_IN_GROUP`; PSU loads count every stacked copy. ILUPDATE
  gives a stacked run in no group its own group, drops deleted runs from group lists and keeps a
  group's room with its first run. A copied group tag lists the nearest copy of each of its runs, so
  ARRAY of a whole bay (runs and tag) makes independent groups. ILRECEIPT stamps each group's line key
  and part number; ILOUT lists each group's runs and shared supplies.
- **Minimum toolkit version.** A catalog's optional `settings.min_toolkit_version` (dotted integers,
  `il-version<`) newer than `*il-version*` prints a warning on ILCATALOG and the first catalog load (and in
  ILVERSION) to download the current toolkit from the portal Resources page; ILCHECK adds the warning
  `TOOLKIT_OUTDATED` (ref `drawing`).
- **AutoLISP shares one namespace** for variables and functions: no local may be named after a function
  (CI checks it), and every call must be AutoLISP or defined in the toolkit (CI checks that too).

## Commands

`ILSETUP` `ILCATALOG` `ILSTYLE` `ILTAPE` `ILCONVERT` `ILJUMPER` `ILFEED` `ILSCALE` `ILROOM` `ILCAB` `ILPSU`
`ILCONNECT` `ILGROUP` `ILSTACK` `ILCTRL` `ILZONE` `ILDMX` `ILWIRE` `ILOTHER` `ILOVERRIDE` `ILUPDATE` `ILCHECK` `ILQUOTE` `ILRECEIPT` `ILOUT` `ILRISER`
`ILSTRIP` `ILVERSION` `ILHELP` (see `ILHELP` in AutoCAD).

## Release checklist

1. `python -B -m unittest discover -s tests/portal_unit -p "test_cad_*.py"` and `npm test --prefix tools/system_designer`.
2. On a staff Windows machine: `tools\cad_toolkit\test\run_tests.bat "<path>\accoreconsole.exe"`; commit `test/report.txt`.
3. Bump `*il-version*` in `lisp/il-util.lsp` with every release.
4. `python -m tools.cad_toolkit.package_bundle --out dist --publish` and commit
   `illumenate_lighting/public/cad_toolkit/ilLumenate-cad-toolkit-<version>.zip` (the build is byte-for-byte
   reproducible; `test_cad_bundle.py` fails when the committed zip's name or version is not `*il-version*`).
   Link it from the portal Resources page.
