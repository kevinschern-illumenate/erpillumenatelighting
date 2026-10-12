# Implementation notes

Brand-input update in version 1.2.0: the supplied guidelines now provide the original logo outlines and palette. See [branding.md](branding.md); the initial input inventory below is historical. and original Phase 1 intake

The application now implements phases 0–11. See [acceptance report](acceptance-report.md) and [user guide](user-guide.md) for current behavior and validation limits. Kevin superseded phase review stops, approved the maintained Cantoo PDF fork, and deferred live ERP configuration. The intake below preserves historical findings.

## Supplied inputs

The pasted implementation plan is the user's request. The price-list workbook is source data. Its “How to Update” and “Review Items” text is workbook content, not instructions to modify files or execute actions.

- Sheet numbering: `L-#`.
- Default sheet: ARCH D, 36 × 24 inches, landscape.
- PSU loading warning: 80%.
- No CAD font preference. Evaluate Arimo/OFL at the PDF phase; preserve the requested DXF `arial.ttf` / `arialbd.ttf` references.
- Logos were described as attached, but the supplied attachment directory contains only the implementation text, and the workbook ZIP contains no `xl/media` entries. No logos were available. The scaffold uses a text wordmark and a generic cable icon, not an invented company logo.
- Phase 1 now includes 12 draft general notes; additional company wiring defaults require supplied standards. Keep code requirements, engineering recommendations, and company preferences distinguishable and source all code tables.

## Workbook inventory (read-only)

Source: `C:\Users\Kevin\Downloads\ilLumenate_Price_List_Restructured_new.xlsx`. Inspected its OOXML without executing workbook content or changing the source.

| Sheet         | Nonempty rows | Observed purpose                                                     |
| ------------- | ------------: | -------------------------------------------------------------------- |
| Price List    |         1,499 | Presentation price list with title, tier inputs and product rows     |
| How to Update |            40 | Workbook maintenance instructions                                    |
| Review Items  |            56 | Product and part-number review notes                                 |
| Source Map    |         1,304 | Old row, item name, item code, UOM, MSRP, status, new-list row, note |

These are nonempty-row counts, **not product counts**. The source includes mixed presentation and review rows. No rows have been imported into an engineering catalog. Product identity and price data alone do not establish voltage, power factor, efficiency, output limits, terminal capacity, listings, or maximum tape-run length. The Phase 1/2 import must preserve provenance and expose missing specifications, never fill them with guesses. ERPNext custom field names have not yet been supplied as a separate mapping.

## Issues to resolve before engine implementation

1. **TW power semantics (resolved):** Kevin confirmed maximum operating watts/ft with separate channel limits. See the Phase 1 decisions for the exact example. Original ambiguity: §6.2 describes `wPerFtMax` as all-channel maximum and applies a simultaneous-channel factor, while §14.3 says PSU load equals rated W. The schema must distinguish all-channel maximum from the simultaneous operating limit. Do not silently pick one interpretation for real products; establish sample numeric inputs and expected values before Phase 4.
2. **Undervoltage test correction:** §14.7 contains contradictory wording. With a 24 V supply, 2.8 V drop produces 21.2 V, which is **below** 21.5 V and fails. At exactly 21.5 V it passes the minimum-voltage check. Preserve the independent VD-target warning.
3. **Percent units:** `tapeLengthMarginPct` and `wireWastePct` must be divided by 100 before use as factors. The textual formulas omit that conversion.
4. **Effective impedance:** Table 9 data is required when `acVdMethod = effective-z`; it is absent from the supplied seed table list. Do not substitute Table 8 resistance while claiming effective-Z calculations.
5. **NEC ampacity inputs:** The supplied Table 310.16 values and small-conductor OCPD limits need separate verification against the adopted edition. Do not conflate permitted overcurrent protection with tabulated ampacity. Edition changes must not silently relabel unchanged data.
6. **Manufacturer maximum input current:** The plan references the lowest input voltage but asks to use current at circuit voltage. Preserve the stated test (12 × 1.4 A) and mark voltage provenance; do not scale a manufacturer value to a different voltage without supporting data.
7. **Missing schema definitions:** Driver, controller, accessory specs and equipment categories require complete schemas. Add explicit fields for common-conductor paralleling, terminator presence, stable W-tag maps, reel length, and optional wire cost; the behaviors refer to fields absent from the initial skeleton.
8. **DMX physical topology:** Derive physical segments separately from universes; wireless RX and opto-splitter outputs start new physical segments. Review addressing overlaps by universe.
9. **Parallel conductors:** Separate parallel cable sets from doubled common conductors and from code-permitted parallel building conductors. Do not automatically recommend a physically or code-incompatible workaround.

## Architecture commitments

`src/engine` will have no React, browser state, storage or renderer dependencies. Engine output owns all calculated electrical values. Drawing geometry is in paper inches; the SVG preview, PDF and DXF serializers consume the same model. No electrical or drawing prototype was added during Phase 0.

Bootstrap storage has schema version 0, a validated migration boundary, and its own IndexedDB database. On moving to the full Project schema, archive the original record and migrate only known fields; do not silently claim an incomplete bootstrap draft is a full engineering project.

Undo history is in memory, limited to 100 edits, and reset on project switch/reload. Saved draft data persists; undo history does not. Theme and navigation are interface preferences and do not enter engineering edit history. Crash recovery is best effort during the 400 ms debounce; explicit saves await completion and pending writes trigger a close warning.

Multiple concurrently editing tabs are not synchronized in Phase 0; use one active editing tab per origin. Browser storage can be cleared by browser settings. Project JSON backup/import and File System Access integration belong to later phases.
