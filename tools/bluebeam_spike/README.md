# Bluebeam Revu spike (draw-to-quote WP 2.1–2.7)

ilLumenate plans a Bluebeam Revu front end for the draw-to-quote import: an estimator
marks up a plan in Revu, the dealer uploads the result, and the portal turns the markups
into an `ilq/2` package the same way the AutoCAD toolkit does. Before building it we need
evidence from real Revu files about what Revu actually writes. This folder holds the
spike tooling. The findings go in [`docs/BLUEBEAM_SPIKE_REPORT.md`](../../docs/BLUEBEAM_SPIKE_REPORT.md)
(WP 2.7, Gate C).

| WP | Question | How this folder helps |
|---|---|---|
| 2.1 | Build a sample corpus with ground truth | Corpus layout below |
| 2.2 | How are vertices and scale stored (viewports, measures, multi-viewport pages)? | `probe_pdf` dumps `/VP`, `/Measure`, vertices |
| 2.3 | Where do Subject, layer and custom columns live? Readable without Revu? | `probe_pdf` `Subj`, `layer`, `extra_keys` |
| 2.4 | Curves, and Revu's own stored length | `probe_pdf` `path`, `length_basis`, `Contents`, `contents_length_in` |
| 2.5 | Tool Set, custom-column profile, Markups List CSV/XML | Exported files in the corpus; read by hand |
| 2.6 | Length accuracy against AutoCAD | `compare_lengths` |
| 2.7 | Report and Gate C decision | `docs/BLUEBEAM_SPIKE_REPORT.md` |

Revu runs on Windows only, so the corpus is built by staff on a Windows machine. The
tools here run anywhere with Python 3.10+ and `pypdf` (already a server dependency).

## 1. Build the sample corpus (WP 2.1)

Three plan sets:

| Job folder | Content | What it exercises |
|---|---|---|
| `residential-simple` | One sheet, one scale, a kitchen and a bath: under-cabinet, toe-kick, one cove | The happy path |
| `commercial-multisheet` | 3+ sheets, at least one sheet with two viewports at different scales (plan plus enlarged detail), one rotated sheet | Viewport selection, scale per viewport, rotation |
| `curved-coves` | Curved and arced coves, a circle, one run that turns through 270° | Curves (arc segments, splines) versus chords |

For each plan set:

1. **Ground truth first, in AutoCAD.** Draw the runs with the ilLumenate CAD toolkit
   (see `docs/CAD_TOOLKIT_IMPLEMENTATION.md`), give each run its id, and export the
   `ilq/2` package. Save it as `truth.ilq.json`. Plot the same layout to PDF with the
   correct scale; this PDF is what gets marked up in Revu.
2. **Calibrate in Revu.** Open the plotted PDF, set the scale (Measure → Calibrate or the
   scale dropdown). On sheets with more than one scale, create one **viewport** per scale
   (Measurements → Viewports) and name it.
3. **Mark up with these tools**, one Tool Set named `ilLumenate`:

   | Tool | Use | Subject (one tool per style) |
   |---|---|---|
   | **Polylength** | Every tape/linear run, one tool per product style | Product style code, e.g. `HD27-DRY`, `HD27-DAMP` |
   | **Length** | Short straight runs and jumpers | Same style codes |
   | **Area** | Each room (gives room name and environment) | `Room` |
   | **Count** | Power supplies, drivers, fixtures | `PSU`, `Driver`, fixture type code |

   Draw each run in the same direction as the toolkit run starts (feed end first).
   Draw at least two runs with arcs (Polylength arc segments) in `curved-coves`.
4. **Custom columns** (Markups List → Manage Columns → Add):

   | Column | Type | Content |
   |---|---|---|
   | `Run ID` | Text | The toolkit run id, e.g. `L1-01` (this is how `compare_lengths` matches runs) |
   | `Type` | Choice | Fixture type tag from the schedule, e.g. `L1` |
   | `Feed` | Choice | `End`, `Center`, `Both`, `Jumper` |

   Fill them in for every markup. Leave a few markups without `Run ID` on purpose so the
   order fallback is exercised.
5. **Export** (all from the same saved markup state):
   - the marked-up PDF, saved normally (not flattened): `plan.pdf`;
   - Markups List → Export Markups Summary as **CSV**: `markups.csv`;
   - Markups Summary as **XML**: `markups.xml`;
   - the Tool Set: `toolset.btx`;
   - the Revu profile that holds the custom columns (Revu → Profiles → Export), if the
     columns are not in the Tool Set: `profile.bpx`.
6. **Round-trip variants** for the `/NM` stability question (WP 2.5), saved next to the
   main files: `plan.saved-again.pdf` (open, move one markup, save), `plan.copy-paste.pdf`
   (copy a markup and paste it), `plan.duplicated-page.pdf` (duplicate a page),
   `plan.flattened.pdf` (Flatten Markups).

### Where the files go

```
tools/system_designer/fixtures/cad/bluebeam/<job>/
  plan.pdf
  markups.csv
  markups.xml
  toolset.btx
  truth.ilq.json
  profile.bpx               (optional)
  plan.<variant>.pdf        (optional round-trip variants)
  NOTES.md                  (Revu version and edition, scale per sheet, anything odd)
```

Keep each job folder **under 5 MB** (crop or simplify the plan if needed) and use **no
confidential data**: no client names, addresses, title blocks or real project numbers.
Redraw or replace the title block before plotting.

## 2. Run the probe

From the repository root:

```
python3 -m tools.bluebeam_spike.probe_pdf tools/system_designer/fixtures/cad/bluebeam/<job>/plan.pdf \
	--out /tmp/<job>.probe.json
```

- Exit code 0: report written. Exit code 2: refused (encrypted, document JavaScript or
  open action, more than 500 pages, over 200 MB, not a PDF, or strict parsing failed).
- `--lenient` retries a file that fails strict parsing and records why in
  `portal_checks.strict_parse`. **The portal parses strictly**, so a Revu file that
  needs `--lenient` is itself a finding for the report.
- The probe never executes, renders or writes the PDF. It only walks the object graph.

What to look at in the report:

| Field | Question |
|---|---|
| `document.info.Producer` / `Creator` | Revu version that wrote the file |
| `pages[].viewports[]` (`Name`, `BBox`, `Measure.R`, `Measure.X/D[].U/C`) | Where scale lives; one per viewport? |
| `pages[].UserUnit`, `rotation` | Do large or rotated sheets change anything? |
| `annotations[].Subtype`, `IT` | Polylength = `/PolyLine` + `/PolyLineDimension`? Area = `/Polygon` + `/PolygonDimension`? Count? |
| `annotations[].vertices`, `vertex_source`, `path`, `length_basis` | How vertices and curves are stored |
| `annotations[].Measure`, `measure_source` | Measure on the annotation or from the viewport |
| `annotations[].computed_length`, `computed_unit`, `computed_length_in` | Length from the ISO 32000 measure model |
| `annotations[].Contents`, `contents_length_in` | Revu's own displayed/stored length |
| `annotations[].Subj`, `layer`, `T` | Subject, layer (optional content), author |
| `annotations[].extra_keys` | Non-standard keys: custom columns and other Revu private data |
| `annotations[].NM` | Markup id (compare across the round-trip variants) |
| `summary` | Counts by Subtype/IT/Subj, `flattened_or_empty`, `has_viewports`, `has_measures` |
| `pages[].errors` | Malformed values (the probe records instead of crashing) |

The length formula is documented in the module docstring of `probe_pdf.py`
(ISO 32000-1 §12.9). Whether Revu follows it exactly is one of the things the spike
confirms.

## 3. Compare lengths with ground truth (WP 2.6)

```
python3 -m tools.bluebeam_spike.compare_lengths /tmp/<job>.probe.json \
	tools/system_designer/fixtures/cad/bluebeam/<job>/truth.ilq.json --markdown
```

Markups are matched to runs by a run id found in `extra_keys` (the `Run ID` column),
then `/Contents`, `/Subj`, `/T`; the rest by order. Several markups with the same id are
summed. The table (per run: truth, computed, error in inches and %, how it was matched)
and the summary line (mean, max |%|, p95 |%|) paste straight into the report. Options:
`--subtypes /PolyLine,/Line` (default), `--assume-unit ft` when the probe could not read
the unit label, `--tolerance-pct 1.0`, `--out result.json`.

## 4. Tests

```
python3 -B -m unittest discover -s tests/portal_unit -p test_bluebeam_probe.py
```

The tests build synthetic PDFs with pypdf (no Revu files are checked in yet).
