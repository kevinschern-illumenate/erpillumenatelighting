# Phase 1 schema and seed decisions

## Explicit power semantics

Kevin confirmed: **use maximum operating watts/ft; record channel limits separately** for tunable-white tape. The example TW tape therefore uses `wPerFtMax: 4.4`, `powerBasis: max-operating`, `channelWPerFtMax: [4.4, 4.4]`, WW/CW, and `maxSimultaneousPct: 100`. Its future PSU load for 20 ft is 88 W; either channel conductor must accommodate 4.4 W/ft at full channel output. Do not halve that PSU load or double it. These numbers are synthetic examples, not ilLumenate specifications.

`all-channel-max` remains a distinct basis for libraries whose rating explicitly assumes all channels simultaneously on. The engine must branch on the recorded basis rather than infer it from channel count. Limited-simultaneous `max-operating` records require explicit per-channel maxima.

## Complete data shapes

`Project` version 1 includes metadata, all requested settings, sources, equipment, loads, control links, wire/layout overrides, notes, revisions and persistent W-tag assignments. Stable UUID identity and the Phase 0 scratchpad are retained. All stored `*Ft` fields remain feet; the units setting is a future display/import conversion preference. Drawing coordinates remain paper inches.

Unresolved tags, graph cycles and electrical overloads belong to Phase 4 QA and must remain persistable. Structural errors (duplicate IDs/tag aliases, ambiguous quantity versus length, reversed ranges, missing fields) are rejected at schema boundaries. Repeated load type tags are allowed; unique load IDs distinguish instances.

Catalog specs have an explicit `kind` discriminator for PSU, driver, decoder, controller, tape, fixture and accessory. Driver/controller/accessory shapes fill gaps in the supplied skeleton. Partial spec overrides retain the discriminator and are validated after merging with the full catalog item. Other extensions include rated-input-current voltage, CC compliance range, controller ports and segment behavior, terminal bounds, tape reels/channel limits, optional terminator presence, wire verification/provenance and conductor-group resistance.

AWG terminal comparisons use an explicit physical-size order, not lexicographic or enum-key order. Parallel cable sets and doubled commons are represented separately. Automatic acceptance of parallel conductors is not implied; the setting requires manual review.

## Code reference data

The three populated tables reproduce the values supplied in the implementation plan. Every record cites NFPA 70, 2023 edition, table identifier, units, source and verification status. The source landing page is a reference pointer, not evidence that all numerical values were independently verified. Only the requested 2023 seed edition is included. 2020/2026 settings must produce unavailable-data handling later unless separate verified data is provided; never relabel the 2023 values.

Table 8 uses uncoated copper resistance at 75 °C, in ohm/kft, preserving separate solid and stranded columns. #22/#24 are not inferred from that table and require explicit wire or conductor-group resistance.

Table 310.16 uses 30 °C ambient and no more than three current-carrying conductors. Its #14/#12/#10 temperature-column values are separate from the 15/20/30 A small-conductor OCPD limits. The supplied values were corroborated with [Southwire's THHN/THWN copper specification](https://www.southwire.com/wire-cable/building-wire/thhn-thwn-copper-silicone-free/p/SPEC10003); adopted-code verification and installation corrections remain necessary. Cable methods can impose lower temperature limits.

Table 402.5 holds the supplied #18 = 6 A and #16 = 8 A fixture-wire fallback, explicitly labelled for that application. It is not a generic cable listing or permission to use those values for every Class 2 cable.

Chapter 9 Table 9 has metadata for 75 °C, 60 Hz, PF 0.85 and PVC raceway, but **no values**: status is `unavailable`. The engine must report missing data when effective-Z is requested. The editor can accept values only with consistent metadata/status; it cannot substitute resistance silently.

The UI validates JSON and locks the selected table's ID, kind, edition and table reference. Numeric values, review status and provenance remain editable. Overrides persist separately from shipped seeds; Restore seed deletes the override. The editor's unit literals prevent a value being silently reinterpreted as ohm/ft or another unit. Additional editions/tables require separate records in a later library workflow.

## Wire provenance and corrections

All 61 wire entries are **example templates requiring verification**, including listing and environmental suitability flags. They are not manufacturer approvals. Each manufacturer reference is paired with `verify: true`; verified manufacturer catalog conversion belongs to a later import/review step. #22/#24 explicit resistance may be illustrative and is labelled accordingly. No engine should treat `isExample` or `verify` records as approved installation choices.

- [Belden 9841](https://catalog.belden.com/techdata/EN/9841_techdata.pdf): nominal 120 Ω, 24 Ω/kft, CM. Its reference is not applied to a generic plenum template.
- [Belden 9729](https://catalog.belden.com/techdata/EN/9729_techdata.pdf): the current specification is **100 Ω and 28.8 Ω/kft**, not the implementation plan's 120 Ω. The requested two-pair 120 Ω construction remains generic; 9729 is not listed as an equivalent.
- [Lutron control-cable construction](https://assets.lutron.com/a/documents/cables_nonplenum.pdf) supports the mixed-gauge GRX-CBL-346S reference. The seed's 22 AWG resistance of 18 Ω/kft is an explicit illustrative placeholder, not a Lutron resistance specification. Device-specific QS wire-size/length instructions must govern final selection.
- Legacy purple/gray 0–10 V colors from the plan remain labelled for identification review; do not infer approval for a new installation.
- NM/UF and MC temperature caps are carried separately from conductor insulation temperature. THHN raceway sets represent individual conductor quantities for later BOM handling.
- `conductors[].count` is the number of individual conductors: a two-pair cable has four data conductors. Wireless has no conductors and zero rated cable voltage.

The workbook supplies useful product identities and prices but does not provide the full electrical specs needed to convert rows into valid engineering products. It is unmodified and no guessed product ratings were imported.

## Drawing and notes

All 16 required layers have muted color, ACI color, line type and lineweight data. The QA overlay has `export: false`, enforced by Zod. Seven line types are expressed in paper inches. Four right-strip title blocks cover ANSI B, ARCH C, ARCH D and ANSI D; all required named fields, borders, drawing regions, minimum 3/32-inch text and a 1-inch reference square validate. Logos remain explicit placeholders awaiting supplied SVG files. These are templates, not finished drawing exports.

Twelve authored draft general notes distinguish coordination, manufacturer instructions, code verification and company defaults. Their source records identify them as authored drafts; linked references provide context and do not claim to be the verbatim source of every note. All require review. New and migrated projects receive copies; subsequent template edits do not retroactively rewrite project notes. The [DALI Alliance design guide](https://www.dali-alliance.org/data/downloadables/4/3/6/diiase001a-specifying-with-dali-a-lighting-designers-guide.pdf) informs the insulation/routing caution.

## Migration and persistence

IndexedDB database `illumenate-riser-scaffold` retains its name/origin and advances to database version 2. The original `drafts` store remains. New `projects`, `legacyArchives` and `codeTableOverrides` stores are added. Each valid Phase 0 record is archived unchanged and migrated atomically; IDs, timestamps, metadata, custom sheet/flow/PSU settings and scratchpad are preserved. Empty engineering arrays do not invent a system. Repeated migration does not overwrite already edited version-1 projects. Any invalid original record aborts the migration transaction and surfaces an error while preserving originals.

Project edits retain bounded in-memory undo/redo. Code-table JSON uses native text undo before saving; saved table overrides can be restored to seeds. Full library CRUD, import preview and edit history are Phase 2. Multiple active editing tabs remain unsynchronized; local project-file backup/open arrives in a later phase.

## Carry-forward engine corrections

At 24 V minus 2.8 V, delivered voltage is 21.2 V: it fails a 21.5 V minimum despite the contradictory wording in §14.7. Percent margin/waste fields must be divided by 100. Manufacturer input current must preserve its measurement voltage. Physical DMX segments and universe addressing are separate. These corrections are documented now and become engine tests in Phase 4.
