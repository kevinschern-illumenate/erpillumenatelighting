# Bluebeam Revu spike report (WP 2.7, Gate C)

> **TEMPLATE: TO BE FILLED IN.** Nothing below is a finding yet. Replace every
> `_TBD_` with evidence from the corpus, and cite the file and probe field each answer
> comes from (for example `commercial-multisheet/plan.pdf`, page 2, `viewports[1].Measure.R`).
> Tooling and corpus instructions: [`tools/bluebeam_spike/README.md`](../tools/bluebeam_spike/README.md).

| | |
|---|---|
| Author | _TBD_ |
| Date | _TBD_ |
| Corpus | `tools/system_designer/fixtures/cad/bluebeam/` (jobs: _TBD_) |
| Revu version(s) and edition(s) used | _TBD_ (from Help → About, and `document.info.Producer` in the probe) |
| Toolkit version for ground truth | _TBD_ |
| Probe report files | _TBD_ |

## 1. Summary

_TBD: three to five sentences. Can the portal read Revu markups from the PDF alone, with
what accuracy, and what does the team recommend at Gate C?_

## 2. Corpus (WP 2.1)

| Job | Sheets | Viewports | Runs (truth) | Markups (by tool) | Variants saved | Size | Notes |
|---|---:|---:|---:|---|---|---:|---|
| `residential-simple` | | | | | | | |
| `commercial-multisheet` | | | | | | | |
| `curved-coves` | | | | | | | |

Probe `summary` per job (paste `by_subtype`, `by_intent`, `by_subject`, `flattened_or_empty`,
`has_viewports`, `has_measures`, `errors`, and `portal_checks.strict_parse`):

_TBD_

## 3. Geometry and scale (WP 2.2)

1. **Vertex storage.** How does Revu store Polylength, Length, Area and Count geometry
   (`/PolyLine /Vertices`, `/Line /L`, `/Polygon /Vertices`, something else)? What `/IT`
   values appear? _TBD_
2. **Scale location.** Is scale on the page `/VP` viewports, on each annotation's
   `/Measure`, or both? What do `/R`, `X[].U/C`, `D[].U/C`, `A[].U/C` look like? _TBD_
3. **Multi-viewport pages.** With two scales on one sheet, does each markup take the
   viewport whose `/BBox` contains its first vertex? What happens to a markup that crosses
   viewports, or lies outside all of them? _TBD_
4. **Page size, `/UserUnit` and rotation.** Any effect on vertices or `/C`? _TBD_
5. **Does the ISO 32000-1 §12.9 formula reproduce Revu's displayed length?** (Compare
   `computed_length` with `Contents` / Markups List length.) _TBD_

## 4. Subject, layer and custom columns (WP 2.3)

| Item | Where it is stored in the PDF (key, format) | Readable without Revu? | Evidence |
|---|---|---|---|
| Subject | `/Subj`? | | |
| Layer | `/OC` (optional content)? `document.layers`? | | |
| Author / label / comments | `/T`, `/Contents`, `/RC`? | | |
| Custom column `Run ID` | `extra_keys` key: _TBD_ | | |
| Custom column `Type` | | | |
| Custom column `Feed` | | | |
| Column definitions (names, types, choices) | in the PDF? catalog `extra_keys`? only in the profile? | | |
| Other Revu private keys seen | list from `summary.extra_key_names` | | |

## 5. Curves and Revu's own length (WP 2.4)

1. **Curves.** How are Polylength arcs and Area curves stored (`/Path` with Bézier
   segments, extra vertices, private keys)? Is `length_basis` `/Path` or `/Vertices`? _TBD_
2. **Chord error.** On `curved-coves`, how far is the chord (vertex) length from the
   AutoCAD arc length? _TBD_
3. **Revu's stored length.** Does Revu store the measured value anywhere other than
   `/Contents` (private key, appearance stream text only)? Does `contents_length_in` match
   the Markups List value? Rounding and display units? _TBD_
4. **Recommendation:** compute from geometry, trust Revu's stored value, or both with a
   cross-check? _TBD_

## 6. Tool Set, profile and Markups List exports (WP 2.5)

1. **Tool Set format (`.btx`).** Container and encoding (XML? compressed? signed?), what it
   holds (tool appearance, subject, measurement settings, custom column values). _TBD_
2. **Can the portal generate a `.btx`** for a dealer's styles (one Polylength tool per
   product style with the right Subject and colour)? What would break on a Revu update? _TBD_
3. **Custom-column definitions and profile import.** Do columns travel in the Tool Set, the
   PDF, or only in a profile (`.bpx`)? Can a dealer import them in one step? _TBD_
4. **Markups List CSV fields.** Column names, units and number format (e.g. `12'-6"` vs
   decimal), custom columns present, page/label references, an id column? _TBD_
5. **Markups Summary XML fields.** Same questions; is it easier to parse than CSV? _TBD_
6. **`/NM` stability.**

   | Action | `/NM` kept? | Other changes | Evidence |
   |---|---|---|---|
   | Save, reopen, save again | | | |
   | Move a markup and save | | | |
   | Copy / paste a markup | | | |
   | Duplicate a page | | | |
   | Flatten markups | | | |
   | Markups List export id matches `/NM`? | | | |

## 7. Length accuracy (WP 2.6)

Paste the `compare_lengths --markdown` output per job. Tolerance used: _TBD_ %.

| Job | Runs | Matched (id / order) | Mean error % | Mean abs % | Max abs % | p95 abs % | Within tolerance |
|---|---:|---|---:|---:|---:|---:|---:|
| `residential-simple` | | | | | | | |
| `commercial-multisheet` | | | | | | | |
| `curved-coves` | | | | | | | |

Per-run tables:

_TBD_

Outliers and their cause (wrong viewport, curve chord, drawing error, calibration): _TBD_

## 8. Supported Revu versions and editions

| Revu version | Edition (Basics / Core / Complete) | Polylength / custom columns / Tool Sets available? | Tested? | Notes |
|---|---|---|---|---|
| _TBD_ | | | | |

Minimum supported version: _TBD_. Edition requirement for dealers: _TBD_.

## 9. Final markup conventions (for the dealer guide)

| Convention | Decision |
|---|---|
| Subjects (one per product style) | _TBD_ |
| Tools per item (Polylength, Length, Area, Count) | _TBD_ |
| Custom columns (name, type, allowed values) | `Run ID`: _TBD_; `Type`: _TBD_; `Feed`: _TBD_ |
| Feed point marker | _TBD_ (Count symbol? Polylength start? column value?) |
| Jumper marker | _TBD_ |
| Rooms and environment | _TBD_ (Area markup Subject/label/column) |
| Calibration and viewports | _TBD_ |
| Direction of drawing (feed end first?) | _TBD_ |
| What dealers upload (PDF, CSV, XML) | _TBD_ |

## 10. Risks and open questions

- _TBD_

## 11. Gate C decision

Choose one and give the reason:

- [ ] **Go: PDF ingest.** The portal reads markups, scale and custom columns from the
  marked-up PDF (strict parsing passes; lengths within tolerance; `Run ID`/`Type`/`Feed`
  readable without Revu).
- [ ] **CSV only.** The PDF is not reliable enough to read directly; dealers upload the
  Markups List CSV/XML export, and the PDF is attached for reference only.
- [ ] **Stop.** Neither path meets the accuracy or effort bar; stay with AutoCAD/DXF.

Reason: _TBD_

Conditions or follow-up work packages: _TBD_

### Sign-off

| Role | Name | Decision | Date | Signature |
|---|---|---|---|---|
| Estimating lead | | | | |
| Engineering lead | | | | |
| Product owner | | | | |
