# User guide

## Project and backups

Start `Start Riser.cmd` or `npm run dev`; open `http://127.0.0.1:5173/#/project`. Enter project identity, drawing/checking names, date, brand, stamp and sheet prefix. Advanced settings include sheet/flow, thresholds, reference edition, ft/m display, notes, revisions and Arimo/Roboto Condensed fonts.

Changes autosave after a 400 ms debounce. Wait for **Saved locally** before closing; **Save now** waits for the write. Recent projects appear in the sidebar. Ctrl/Cmd+Z undoes; Ctrl/Cmd+Shift+Z or Ctrl+Y redoes; Ctrl/Cmd+S saves locally. Libraries have separate toolbar history. The JSON editor uses native text history. History resets on reload/switch; saved data remains.

Save `.riser.json` from Project or Export for portable backup. Chromium uses a file picker; other browsers download. Open validates/migrates before activation. Also export a **library backup**: project files reference catalog IDs rather than embedding the catalog. Use one active editing tab per origin; concurrent tabs do not merge changes. Different browsers, `localhost`, `127.0.0.1` and different ports have separate storage.

## Libraries

Products and Wires support search, new/duplicate/edit/delete, CSV export and category templates. **New item** and **Edit selected** open a form with labeled fields, unit hints, protocol choices and repeatable rows for outputs, ports, channels and conductors. Sections follow the product category. New products start with blank ratings and can be saved incomplete. **Advanced JSON** remains available; changes carry across when switching between the two modes. Keep stable IDs on existing records. Manual edits mark changed fields as local ERP overrides; edit `localOverrides` in Advanced JSON to release protection intentionally.

CSV flow: choose file → adjust automatic column mapping → inspect per-row errors and new/updated/unchanged counts → commit. Invalid batches cannot commit. Products match by SKU; wires by ID. Nested specs use dotted names; arrays are JSON strings. CSV exports escape spreadsheet formulas.

Incomplete imported products are saved as **Needs specifications** with their known values, missing-field list and source notes. They remain searchable and editable but are excluded from project product choices. Select one and choose **Edit selected** to see known values already filled in. Use **Save incomplete product** to keep work in progress. Supply verified missing fields, review and resolve the imported source notes, then choose **Save as complete**. Validation identifies the fields that still need attention. This does not copy example ratings. Original ERPNext data is available in a read-only section. A project referencing an incomplete product is blocked from calculation and drawing until it is completed. Unused incomplete products do not affect existing projects.

CSV imports can map a whole `specs` JSON object, or its individual dotted fields, but not both. `sourceData` retains original ERP fields and child-table rows as JSON through import, export and library backups. Reimporting source CSVs can replace previously completed specs; inspect updated rows before committing.

The supplied price list has identities/prices but lacks complete electrical ratings. No real product ratings were invented. Templates are synthetic **EXAMPLE** data. Replace ratings, provenance and example flags only with verified manufacturer information. All wire construction/listing/environment seeds also require verification.

Code tables expose source, edition, units and editable values. Populated seeds are the supplied 2023 copper resistance, ampacity and fixture-wire tables. Missing Table 9 impedance or other editions produce errors; no silent fallback relabels 2023 values. Additional sourced editions can be included in a library JSON backup. Restore seed is undoable.

Tunable-white `wPerFtMax` means **maximum operating watts/ft**. Separate channel maxima size each conductor. The 4.4 W/ft TW example consumes 88 W over 20 ft, neither half nor twice that. `all-channel-max` is a separate explicit rating basis.

**Free-cutting tape:** choose **Free-cutting tape → Yes** in Tape ratings. The form removes the fixed cut interval. In Advanced JSON use `"freeCutting": true` inside `specs` (or `specs.available` for an incomplete product) and omit `cutIntervalIn`. Do not use zero as a substitute for an unknown interval. Fixed-cut tape requires a positive `cutIntervalIn`; older records without `freeCutting` retain fixed-cut behavior. Changing back to No requires entering the interval again.

Free-cutting tapes use the entered length and configured tape-length margin for power and BOM calculations; no artificial cut increment is introduced. Pixel products still retain their whole-pixel current calculation. CSV exports and JSON backups preserve the cutting method. Earlier incomplete ERP imports with `sourceData.fields.is_free_cutting` explicitly set to 1 are recognized on import, restore or reload when no local cutting choice or positive interval has been entered. The obsolete cut-interval warning is removed; other missing specifications remain required.

## System tables

Work through Sources, Equipment, Loads and Control Links. Double-click to edit; Tab/Enter commits. Searchable catalog and connection pickers filter compatible voltages, drive modes, protocols and port directions.

- Sources describe actual branch voltage, phase, breaker/poles and switching. Model individual line-neutral/line-line branches as 1PH at actual voltage; a 3PH feed requires verified 3PH equipment input data.
- Equipment includes PSUs, CC drivers, decoders/controllers and accessories, with one-way feed lengths, location/enclosure, outputs, control source and chain order. Supply ports use names such as `OUT1`; decoder ports use `CH1`, `CH1-2`, `CH1-4`. Quantity creates grouped identical units with explicit per-unit allocation warnings.
- Matching **Enclosure** values group components together in the drawing, including controllers and converters supplied by different circuits. Changing those values recalculates the arrangement. Each fitting enclosure stays together under one outline; oversized or congested enclosures continue onto additional sheets. Manual pins retain their coordinates; use **Reset all pins** in Drawing if an old pin prevents the new grouping.
- In the DMX decoder Library form, **Power input and output** selects DC LED decoding or AC line-voltage phase dimming. For a 120 V AC dimmer, enter its verified input range, channel and total current ratings, and configured forward- or reverse-phase output method. Optional watt limits can capture separate LED-load ratings. Feed it from a 120 V branch and connect only line-voltage fixtures whose catalog dimming method matches the decoder. Set the fixture run environment to `raceway` when specifying the included building-wire sets. Older decoder records default to DC. The resulting output is treated as a grounded line-voltage branch, while the DMX control cable remains separate.
- Loads use tape length or fixture quantity, upstream port, home-run/interfixture length, feed method and environment. Fixture quantity produces an `xN` symbol. Separate rows retain individual runs and IDs. Repeated type tags are allowed; explicit control links to individual loads use their stable IDs.
- Control Links describe individual signal cables. For a DMX daisy chain, connect the controller's DATA OUT to device 1's DMX IN, then device 1's **DMX THRU (daisy chain)** to device 2's DMX IN, continuing in physical cable order. Enter each cable's length. An explicit incoming Control Link replaces Equipment's shorthand `controlFrom` for that receiver and protocol, so it does not also create a controller home run. Equipment displays those explicit connections and directs length edits back to Control Links. Pixel tape accepts SPI. Addresses/universes, physical segments and termination are checked separately.

DMX decoders include **Allow DMX daisy chaining / THRU** in the Library's Control section. Existing decoder records default to Yes; verify the device's THRU or loop-through terminal arrangement and choose No for an end-only receiver. A THRU connection continues the same physical DMX segment, accumulates its cable length and unit loads, and moves the end-termination check to the final device. Use separate isolated outputs when branching into new segments.

In **Control Links**, **Add row** opens a cable form: choose the signal protocol, source output, receiving input, physical cable length and environment. **Add 0–10 V link** opens that form with `0-10V` selected. Choose a converter/dimmer output such as `DIM1` and the downlight's **DIM IN**; its zone and model distinguish repeated fixture tags. The receiving product must list `0-10V` as a supported dimming protocol in Libraries. Select a saved row and choose **Edit control link** to review or change those details. Length follows the project's ft/m units. No output channel or cable length is guessed, and a fixture's dimming capability alone does not create a cable.

For DMX-to-0–10 V devices, choose **DMX to 0–10 V converter** in the Library. Enter the device's own power consumption and AC, DC, or **AC or DC** input rating. A shared voltage range applies to both supply types unless separate AC/DC ranges are supplied. A manufacturer maximum input current for a dual-supply device also needs its AC/DC type and rated voltage. AC power factor is applied only when the actual feed is AC.

Add one physical DMX512 input port and one named 0–10 V output port for each independent dimming channel (`DIM1`, `DIM2`, etc.). Record the device's actual DMX footprint and unit load. A DMX thru port is optional. Each output can have a verified **Maximum controlled devices** limit; counts include fixture/equipment quantities. New converter items start incomplete with a DMX input and first dimming output, ready to rename or extend.

In Equipment, select the converter, assign **Fed from** to its low-voltage power supply, and **Control from** to its DMX source. Selecting this category initializes automatic DMX addressing in universe 1; change that to suit the project. Add **Control Links** with protocol `0-10V` from the converter's named outputs to the fixtures or drivers. Keep each fixture/driver's actual power feed in its own row. The converter's supply is sized for its own consumption only. Signal cables, DMX patch/termination, the BOM and the drawing include the converter and its links. It cannot be selected as a fixture power source. Verify electrical source/sink compatibility and dim-to-off behavior against the connected products; those properties are not inferred from the protocol name.

**Paste from Excel** accepts headers and tab-separated rows. Correct validation errors before adding the atomic batch. Selected-row Fill Down, bulk edit, duplicate and delete are explicit commands. AG Grid Community is used without paid Enterprise range-fill handles.

Grid length entry and TSV paste follow ft/m display preferences and convert to canonical feet. Project JSON, product/wire specs and engineering CSV schedules retain explicit feet fields. Paper always uses inches. Review's issue links open the relevant table row; the mini drawing updates after edits.

## Engineering review

Derived runs show stable W-tags, physical endpoints, selected cable, current, drop and end voltage. Inspect rejected candidate reasons and apply manual wire/parallel-set/doubled-common overrides. Failing overrides remain visible and retain QA. Loading lists branch demand, PSU output watts and channel amps. Apply split-feed suggestions to derive multiple feed runs. Auto-patch writes proposed addresses and is undoable; manual DMX reservations are honored first.

The model includes efficiency/PF or manufacturer maximum input current at the specified voltage, continuous-load checks, per-output/decoder capacity, CV/CC compliance, environment and conductor roles, OCPD limits, terminal warnings, common/return voltage drop, and distributed fixture drops. Mixed conductor resistance uses the highest current-carrying resistance conservatively. Parallel overrides require verification. Installation-specific ampacity corrections are not inferred from absent inputs; verify adopted-code and manufacturer requirements.

At 24 V, a 2.8 V drop leaves 21.2 V and fails a 21.5 V minimum. Exactly 21.5 V passes that minimum; the independent drop target can still warn. This corrects contradictory wording in the original plan.

Each wired DMX segment has an end terminator. Isolated outputs and wireless receivers start new physical segments. Device pixel/universe/bus-count limits and Ethernet/SPI/device-specific link lengths are checked. The BOM totals tape feet/reels, equipment, cable with waste and individual building-wire conductor feet.

## Drawing

Turn off **Show schedules** in Drawing to reclaim the reserved schedule space before equipment is placed and wired. The column layout fits more receivers beside their sources and reduces page count where possible. Text and symbols retain their printed size. Devices on the same sheet connect directly; paired X references identify connections to other sheets. Existing pins retain their absolute positions; **Reset all pins** allows a fully automatic arrangement. Turning schedules back on restores the layout with schedules.

The matching Export option controls the same saved project setting, so PDF, DXF and SVG use the arranged diagrams and title blocks. Schedule CSV exports remain available. Crowded multi-output devices expand only as needed to keep continuation leads in ordered rows, with channel names, X references and TO/FROM sheet labels.

Automatic layout uses invisible columns: panels, enclosures, downstream power supplies, controls, then loads. Each enclosure has its own supply, controls and load columns. Use the **Enclosure** field in Equipment or Loads to assign a component; leave it blank for equipment outside a cabinet. Multiple receiver columns are used on continuation sheets when space permits, while preserving readable printed text. Continuation circles reserve clear space for their TO/FROM sheet references and cable tags. Blank areas below diagrams can hold schedules. Existing manual pins stay in place; **Reset all pins** applies the current automatic arrangement throughout the project.

Use sheet tabs, fit/zoom, blank-paper pan, QA/wire/DMX toggles and the symbol gallery. Drag a device to pin its paper-inch position, wait for reroute/autosave, then undo or **Reset all pins** as needed. Invalid pins generate notes; impossible routing gives an actionable error.

Body letters plot at 3/32 inch, tags at 1/8 inch and section titles at 3/16 inch. PDF/SVG use cap-height correction. Layout never shrinks text to fit. Long schedules wrap and continue. Power pagination groups by panel, circuit and PSU, then subdivides. Paired `X#` continuations and a continuation index identify destination sheets and all included W-tags. Power cables from the same output can share an outgoing continuation callout; each remains separate at its destination and in the wire schedule. Every control cable has its own paired reference, with its signal protocol, W-tag, remote device/port and TO/FROM sheet. These details remain visible when schedules are hidden and update when sections move to different sheets.

Equipment uses plain labeled blocks in aligned functional columns within enclosure groups. Open circles on an equipment outline mark cable connections; port labels retain physical output identities, including AC-THRU. A bridge means two cables cross without connecting. Enclosed control sources stay with their enclosure's equipment; separate controls occupy the control column. DMX daisy-chain order helps arrange controls, while supplies and loads align with their connected devices. Top-to-bottom flow uses the corresponding row sequence. Enclosure outlines have room for their headings and cable entry, and cables running parallel to an outline maintain at least 0.20 plotted inch of clearance. Cables may cross enclosure boundaries at right angles. These are drawing clearances, not physical installation dimensions. Pins that separate enclosure members can require separate outlines to avoid enclosing unrelated devices. Compact W-tags refer to full wire-schedule details; unplaced power labels produce layout notes. Control labels retain both protocol and W-tag on the drawing; congested automatic layouts subdivide if necessary instead of silently dropping the label. Pins that prevent a clear control label produce an actionable layout error. Separate load rows retain their identities. ilLumenate Lighting sheets use the supplied monochrome vector logo, centered with clear space in the title block. The 206 Lighting option retains its text identifier. Drafting text remains Arimo or Roboto Condensed for predictable plotting and CAD exchange.

## Exports

- **PDF:** all sheets, monochrome vectors, fully embedded TrueType fonts and named optional-content layers. QA overlays are omitted. Print at actual size; each page has a 1.000-inch reference square. See `cad-import-test.md` for AutoCAD behavior.
- **DXF ZIP:** one native inch-unit R2007 file per sheet with blocks and eight attributes for extraction. MAIN/BOLD reference Arial by default. Condensed exports include TTFs and OFL license; install them before opening. Tiled DXF places sheets left to right with two-inch gaps and needs the same fonts installed.
- **SVG ZIP:** vector sheets with embedded fonts and license. **CSV schedules:** equipment, loads, wire, loading, DMX, BOM and issues. Project and library JSON remain editable sources.

Resolve engineering errors and verify the issue stamp before issuing drawings. Exports preserve the current design and stamp, including unresolved conditions.

## ERPNext demo and later connection

Libraries → ERPNext Sync defaults to **Demo**. Preview three synthetic items, inspect counts/conflicts, commit and undo. Repeating the pull upserts by ERP item code. Protected local fields, including nested overrides, are preserved and reported.

For a real endpoint later:

1. Copy `.env.example` to `.env` locally and set URL/API key/secret. Never use front-end `VITE_*` credentials or project fields.
2. Run `npm run proxy` separately; it listens on loopback port 8787. Vite forwards `/api/erp` from development/preview.
3. Choose the proxy source, item groups and actual JSON field mapping. The temporary map expects schema-valid specs JSON. Unfinished records must use the explicit incomplete specification structure; missing full-spec ratings are rejected.
4. Preview, resolve invalid rows, then commit. Library changes after preview require a new preview.

Transport performs Frappe Item GET requests in pages of 200, capped at 20,000 records, with timeouts and redacted failures. It never pushes data. Real ERP credentials and endpoint validation are intentionally deferred per Kevin's instruction.
