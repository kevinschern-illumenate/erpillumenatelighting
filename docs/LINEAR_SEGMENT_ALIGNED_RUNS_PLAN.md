# Linear fixtures: segment-aligned runs (investigation and implementation plan)

Status: **plan only, not implemented.** Section 9 lists the decisions needed before work starts.
Paths are relative to `illumenate_lighting/illumenate_lighting/` unless they start with `tests/`
or `public/`. CE = `api/configurator_engine.py`.

## 1. Target behaviour

A multi-segment linear fixture is a chain of customer segments joined by jumper cables. Each
electrical run must be made of **whole segments**:

- The engine packs segments in order into runs. A run never exceeds the maximum run length, which
  comes from the watts limit, voltage drop, or the override.
- Inside a run, segments are joined by jumpers, as entered.
- Where one run ends and the next begins, between segments N and N+1:
  - there is **no jumper**;
  - segment N+1 gets its **own leader cable / power feed**.
- One segment longer than the maximum run on its own is still split into runs inside that segment,
  as today. How that extra feed is built is decision D1.

Example from the walkthrough: four jumpered segments, two runs. Today segments 1–4 are all
jumpered, and run 2 starts partway along segment 3. After the change:

- Run 1 is segments 1–2 joined by a jumper, fed by leader 1.
- Run 2 is segments 3–4 joined by a jumper, fed by its own leader at the start of segment 3.

## 2. How it works today

### Engine — `_compute_multisegment_outputs` (CE:1782-2275)

**Phase 1: per user segment** (CE:1902-2135)
- Takes the endcap and leader allowances, works out the tape cut, then the profile/lens pieces.
- Segment 1 alone gets the start leader and the leader allowance (CE:1988, 2081).
- Every `end_type == "Jumper"` sets `end_jumper_len_mm` on that segment's last piece (CE:2082).
- Segments after the first always start with a Feed-Through endcap; a Jumper end is Feed-Through
  too (CE:1959-1968).

**Phase 2: runs** (CE:2137-2205)
- Runs cover the *total* tape length: full maximum-length runs, then the remainder, or
  `linear_power.equal_run_lengths` over the total.
- Segment boundaries are ignored.
- Each run's `segment_index` is the first physical piece of the segment where the run starts.
- Each run's `leader_len_mm` is the template's `leader_allowance_mm_per_fixture` (default 15 mm).
  That is an allowance, not a cable length.
- `leader_qty = runs_count`.

**Items** — `_resolve_multisegment_items` (CE:2277-2559)
- One leader item for the whole fixture, taken from `ilL-Rel-Leader-Cable-Map` using segment 1's
  power feed type.

**Inputs** (the `segments_json` contract)
- `segment_index`
- `requested_length_mm`
- `end_type`
- `start_feed_direction`, `start_power_feed_type`
- `start_leader_cable_length_mm`. For segments after the first this holds the *previous segment's
  jumper length*, not a leader.
- `end_feed_direction`, `end_power_feed_type`, `end_jumper_cable_length_mm`

### Build sealing — `api/linear_build.py`

`finish()` fingerprints all of the following into `config_hash` (`ILL-CF-<hash>`):
- `ENGINE_VERSION` (`"linear-2"`)
- the part number and inputs
- `computed`, `resolved_items`, `components` and `cables`

`snapshot()` refuses a build whose JSON no longer matches its hash. `current_estimate()` re-prices
the pinned build and never recomputes it.

`cable_manifest()` (linear_build.py:126-171) is the only cable cut list for BOMs, stock and
travelers:
- **Run 1:** segment 1's real leader.
- **Runs 2..n:** an "additional feed" cut at `run.leader_len_mm`, which is the 15 mm allowance.
  This happens on both the single-segment and multi-segment paths. **This is an existing defect.**
  For a count-UOM cable assembly the cut either raises (no matching assembly length) or orders
  the wrong part.
- **Every `end_jumper_len_mm`:** one jumper cut.

### Downstream consumers

**Documents that only read the sealed snapshot**
These never recompute, so existing records are safe:
- Quotation/SO configured items (`configured_product_builder._fixture_configuration_snapshot`,
  `build_links`)
- `ensure_bom` / `assert_bom`, Work Orders and the `manufacturing_order` traveler
- `pricing_utils` availability
- `order_review` fingerprints and `drawing_impact.on_build_update`
- spec submittals (segment 1 leader only)
- exports (`build_description`)

**Code that counts jumpers from the *input* `end_type == "Jumper"`**
These will overcount jumpers once a boundary becomes a feed:
- Item name `{n}seg+{j}J` (`manufacturing_generator.py:693-702`)
- `_generate_item_description` (1395-1403)
- BOM remarks (1433-1441)
- Traveler notes (1537-1545)
- `fixture_group_configurator.run_summary` (~151-165)
- `fixture_group_bom.py:59-71` description

**Code that reads `end_jumper_len_mm`**
Correct automatically once that is zeroed:
- `_calculate_jumper_cable_items` (legacy, 1907-1957)
- Cut-list "End Jumper" lines (1463-1486, 1558-1580)

None of these print a "Start: Leader" line for a segment after the first.

**Endcap quantities** — `_calculate_endcap_quantities` (1814-1850)
- Segments after the first are always counted Feed-Through at the start. That stays true.
- A segment's end counts as Feed-Through when its end endcap type is Feed-Through or it has a jumper.

**Power**
- One circuit per run. Each feeds the driver planner (`linear_power.select` →
  `tape_neon_power.select_plan` → `power_planner.plan_power`, per run or grouped).
- `select_plan` requires `len(run_loads) == runs_count` and run watts summing to `total_watts`.
- Driver qty becomes the separate power-supply ACCESSORY lines (`power_supply_lines.py`). The
  quantity is frozen per schedule line until it is reconfigured.

**Fixture groups and system design**
- `fixture_group_configurator.py:117-121`: one circuit per member run.
- `group_contract.py:136-148` keeps an allowlist of segment input keys.
- `system_design/expansion.py:216-235` creates one design run per `doc.runs` row. Run keys change
  if the run count changes.

**Pricing**
- `_calculate_pricing` does not price leader or jumper cables.
- The change moves price only through the driver plan: more or fewer supplies or outputs.

### Configurator UI

**Segment cards** (`configurator_fixture_form.html:317-420`, coordinator copy 371-500)
- Only segment 1 has a start feed type, feed direction and leader length.
- Later segments show read-only "Continues from segment N" text, filled by
  `_propagateInheritedStarts` (`fixture_steps.js:696-712`) from the previous jumper.

**Results** (`fixture_steps.js:1060-1141`, `coordinator.js:1348-1449`)
- Shows the run table (Run / Segment / Length / Watts), counts and `build_description_display`.
- `leader_qty` is not shown.

**Reopen** (`restoreGeometry` / `_restoreRequest`)
- Calls `_propagateInheritedStarts`, which **overwrites** any saved later-segment start with the
  previous jumper.
- A new per-segment leader would therefore be lost on reopen unless this is changed.

**Other entry points**
- The Desk Quotation/SO dialog mounts the same portal classes. It goes through
  `desk_configurator.py:642` → `configured_product_builder._fixture_payload_from_portal_selections`
  → `validate_and_quote_multisegment`.
- Webflow is single-segment only; complex fixtures are handed to the portal.
- The build preview (`build_preview.js`) already draws a break plus a new feed when a boundary
  has no jumper and the next segment has `start_leader_len_mm`.

## 3. Engine design

### 3.1 Packing algorithm (new `api/linear_runs.py`, pure and unit-tested)

**Input**
- The ordered segments' tape lengths (`tape_cut_len`), `max_run_mm`, `cut_increment_mm` and
  `equal_length_runs`.

**Output**
- An ordered list of runs. Each run has:
  - `start_user_segment`
  - `start_offset_mm` (0 unless the run is inside an oversized segment)
  - `run_len_mm`
  - the segments it covers

**Default mode: fewest runs**
- Go through the segments in order and add each to the open run while the run stays at or under
  `max_run_mm`.
- Otherwise close the run and start a new one at that segment.
- This greedy packing is optimal for contiguous packing: it gives the fewest runs.

**Oversized segment** (tape longer than `max_run_mm`)
- Close any open run.
- Split that segment on its own using the current rule (full runs then remainder, or
  `equal_run_lengths` when equal runs are chosen).
- The last internal piece of the segment does not continue into the next segment; the next
  segment starts a new run.
- Decision D1 confirms this.

**Equal-length runs** (decision D5)
- Keep the fewest-runs count from the greedy pass.
- Choose the contiguous split that minimizes the longest run (a small dynamic-programming search
  over at most 50 segments).
- An oversized segment still splits internally into equal parts.

**Invariants** (asserted in tests)
- Runs cover every millimetre of tape exactly once.
- Every run is at or under `max_run_mm`.
- Run watts sum to `total_watts` (within 0.1 W).
- `run_index` is 1..n.

### 3.2 Boundaries, endcaps and cables

At a **run break** between segments N and N+1:

| | Today | After |
|---|---|---|
| Segment N end cable | jumper (`end_jumper_len_mm` = input) | **none** (`end_jumper_len_mm = 0`, `end_jumper_item = None`) |
| Segment N end endcap | Feed-Through | **Solid** (decision D2) |
| Segment N+1 start cable | (jumper received) | **leader**: `start_leader_len_mm`, `start_leader_item` |
| Segment N+1 start endcap | Feed-Through | Feed-Through (unchanged) |
| Segment N+1 feed type / direction | inherited from segment N's jumper end | same inherited values (or override, D3) |

- Inside a run, segment boundaries are unchanged (jumper, Feed-Through both sides).
- **Leader item per feed:** resolve `ilL-Rel-Leader-Cable-Map` for each feed's power feed type (a
  small cache keyed by feed type). Today there is one item per fixture.
- **Run rows:**
  - `segment_index` = the first physical piece of the segment where the run starts (meaning
    unchanged).
  - `leader_item` / `leader_len_mm` = the **real** feed cable, not the allowance.
  - New snapshot-only keys: `start_user_segment`, `start_offset_mm` and
    `feed: "leader" | "segment feed" | "internal feed"`.
  - These live in `build_snapshot_json`/`computed`; no child-table schema change is required.
    An optional `start_user_segment` Int column on `ilL-Child-Configured-Run` would make it
    visible in Desk.

### 3.3 Allowances and the circular dependency

Run packing depends on tape lengths. Tape lengths depend on endcap allowances, and on a leader
allowance if one applies (decision D4). Endcap types depend on where the runs break.

Resolution:
1. Compute tape lengths from the user's end types (Jumper means a Feed-Through end).
2. Pack runs.
3. Re-derive the endcap types at each break (Solid at segment N's end) and recompute the tape for
   the affected segments.
4. If any run now exceeds the maximum, pack again.

The result never oscillates: a Solid endcap's allowance only changes tape at a break, and the loop
is capped at 3 passes with a hard error. If D4 says no extra leader allowance on fed segments and
D2's Solid allowance equals Feed-Through's, a single pass is exact.

### 3.4 Fixing `cable_manifest` for both paths

- Build feed cuts from runs:
  - **Run 1:** segment 1's leader. Role `leader`.
  - **A run starting at a segment boundary:** that segment's `start_leader_len_mm`/item. Role
    `segment feed`. Add `segment: N` to the cut; the traveler already prints `cable.segment`.
  - **A run starting inside a segment:** role `internal feed`, length per D1.
- Jumper cuts come from `end_jumper_len_mm > 0` only, so they are never also counted as a feed.
- Single-segment builds keep their roles (`leader`, `additional feed`, `end leader`). The
  additional feed now uses a real length (D1) instead of the 15 mm allowance.

### 3.5 Inputs (backward compatible)

- New optional per-segment field `feed_leader_cable_length_mm`: the leader length to use **if**
  this segment starts a new run.
  - Default when absent: segment 1's `start_leader_cable_length_mm`, then the template default
    (decision D3).
  - `start_leader_cable_length_mm` keeps its meaning for every segment, so saved payloads,
    presets, drafts and reopen data keep working.
- Optional `feed_power_feed_type` / `feed_direction` per segment (D3). Absent means inherited from
  the previous jumper end.
- Add the new keys to:
  - `_normalize_user_segments_for_hash` (CE:174-195)
  - `group_contract.py:136-148` allowlist
  - `ilL-Child-User-Segment` (new Int and Link fields; schema change)
  - `configuration_reopen.py:61-64`
  - `api/portal.py:3664-3702`
- **Part number:** `J(hash)` covers the input segments only. Adding a key changes the hash only
  when a value is given, because absent keys normalize away. Existing part numbers are unchanged.

### 3.6 Text outputs

`build_description` / `_display` (CE:2110-2135):
- At a fed boundary write `Seg N: … | Start: <feed> <type>, <len> leader (run k)` instead of the
  previous segment's `End: … jumper`.
- Add a closing line: `Runs: k (feeds at Seg 1, Seg 3)`.

## 4. Changes by layer (file list)

| Layer | File | Change |
|---|---|---|
| Engine | new `api/linear_runs.py` | Packing and equal partition (3.1), pure functions |
| Engine | CE `_compute_multisegment_outputs` | Use the packer; per-boundary jumper/leader/endcap (3.2); fixed-point loop (3.3); real run leader lengths; new snapshot keys; descriptions (3.6); site flag gate (6) |
| Engine | CE `_resolve_multisegment_items` | Leader item per feed type |
| Engine | CE `_create_or_update_multisegment_fixture` | Persist per-segment feed items; run leader item/length |
| Engine | CE `_compute_manufacturable_outputs` + persistence (~4211) | Real length for additional feeds (D1) |
| Build | `api/linear_build.py` | `ENGINE_VERSION = "linear-3"`; `cable_manifest` per 3.4 |
| Manufacturing | `api/manufacturing_generator.py` | Jumper count from `segments.end_jumper_len_mm>0` (item name 693-702, description 1395, BOM remarks 1433, traveler 1537); "Start: Leader" line for fed segments (1463-1486, 1558-1580); endcap quantities read explicit `end_endcap_type` |
| Manufacturing | `api/manufacturing_order.py:44-83` | Traveler reads segment and feed data from the snapshot (fixes an existing `None` output) |
| Groups | `api/fixture_group_configurator.py` `run_summary`; `api/fixture_group_bom.py:59-71`; `api/group_contract.py` | Jumper/feed counts from the build, not inputs; allowlist the new keys |
| System design | `system_design/expansion.py:216-235` | Carry each run's feed segment into the design run; run keys stay `run_index` |
| Compare | `portal/compare.py:150-195` | Show each run's feed segment |
| UI | `public/js/configurator/fixture_steps.js`, `coordinator.js`, both form templates | Results: a "Runs and feeds" list (Run k: Seg a–b, fed at Seg a, leader X in), showing `leader_qty`; for each fed segment an editable leader length (and feed type/direction if D3), which re-calculates. Inherited-start text says "New run: own feed" when the result says so. `_propagateInheritedStarts` must not overwrite `feed_*` keys; `_collectSegments` / `collectSegments` send them |
| UI | `public/js/configurator/build_preview.js` | Nothing new; it already handles a break plus a feed. Update the test that assumed jumpers at breaks |
| Desk | `configured_product_builder._fixture_payload_from_portal_selections` | Forward the new keys (it forwards `segments` already; check nothing filters them) |
| Docs | `fixtures/print_format.json` | "Leader Qty = runs_count" stays correct |

## 5. Existing records (Quotation, Sales Order, schedules)

- **Nothing existing changes.**
  - Sealed builds keep their hash.
  - Quotations and SOs keep their configured Item, BOM and rate.
  - `drawing_impact` and `order_review` fingerprints stay stable.
  - Power-supply lines stay at their frozen quantity.
- **Reconfiguring a line** (reopen → calculate → save) creates a new `linear-3` build:
  - The part number is the same.
  - The Item code gets a hash suffix (`build_item_code`).
  - The power-supply lines are re-reconciled.
  - The reopen notice should say the runs were re-planned.
- **A submitted SO that later reconfigures goes through the existing order-change flow.** Nothing
  is applied silently.
- **Draft Quotations synced from a schedule** (`schedule_sync`) follow the line only when the line
  is reconfigured.
- **Audit report before switching on:** a read-only script
  (`api/reports/segment_run_impact.py`) runs every unsubmitted schedule line and draft quote with
  a multi-segment linear build through the new packer in memory (`_skip_record_creation`). It
  lists the run count, supply and price differences, so Sales knows which open quotes would
  change if reconfigured.

## 6. Rollout

1. A site flag `linear_segment_runs` (in `portal/site_flags.py`) chooses the old or new Phase 2.
   - The engine version follows the flag (`linear-2` / `linear-3`), so each build's identity says
     which rules made it.
   - Default **on** for staging, **off** for production until sign-off.
2. Ship the engine, `cable_manifest`, manufacturing text and UI together behind the flag.
   - The `cable_manifest` additional-feed length fix (3.4) is a correctness fix. It could ship
     first, on its own, if D1 is answered.
3. Run the audit report on staging data, review it with Sales and Production, then turn the flag
   on in production.
4. After a release cycle, remove the old Phase 2.

## 7. Tests

**New**
- `tests/portal_unit/test_linear_runs.py` (packer). Cases:
  - the walkthrough's four segments into two runs;
  - two 6 ft segments fit one run;
  - four 6 ft segments at a 10 ft limit give four runs;
  - an oversized middle segment;
  - equal mode minimizes the longest run;
  - every invariant in 3.1;
  - property-style random cases (coverage, limit, run count no worse than any contiguous
    alternative).
- Engine cases in `test_equal_length_runs.py` / a new `test_segment_runs.py`:
  - break jumpers are zeroed;
  - fed segments carry a leader and item;
  - endcaps are Solid/Feed-Through;
  - `leader_qty == runs_count`;
  - run watts sum to total;
  - driver plan circuit count;
  - the flag off reproduces the old output byte for byte (same `config_hash` as before).
- `test_linear_builds.py`:
  - cable roles `leader`, `segment feed`, `jumper`, with no double count;
  - additional-feed length fix;
  - count-UOM assembly match for feeds.
- Manufacturing text: jumper counts and "Start: Leader" lines.
- Group run summary and description.
- System design run keys.
- UI (`configurator.test.cjs`):
  - feeds list renders;
  - leader edits round-trip through `_collectSegments`, `exportRequest` and reopen;
  - `_propagateInheritedStarts` keeps `feed_*` keys.

**Expected value updates** (the new rule changes their outcome)
- `test_equal_length_runs.py:149` (first run 4572 becomes 3048), `:155`, `:166` (3 runs become 4)
- `api/test_configurator_engine.py:2205` (override 5 ft: 3 runs become 4), `:2329`/`:2386` (a
  boundary that becomes a feed loses its jumper)
- `test_linear_builds.py:47`
- `test_count_uoms.py:35,82`
- `test_fixture_groups.py:189,265,314`
- `test_system_design_expansion.py:83`
- `tests/portal_ui/build_preview.test.cjs:68` (jumper count 3 becomes 2 when the engine drops the
  break jumper)

**Manual staging pass**
1. Configure the walkthrough fixture in the portal (Add Fixture Line).
2. Check the preview, the results feed list and the build description.
3. Save to a schedule.
4. Create a Quotation from the schedule, then a Sales Order. Submit it.
5. Check the generated Item, BOM cable rows (leaders, jumpers, solid/feed-through endcaps), Work
   Order traveler, power-supply lines and spec submittal.
6. Repeat from the Desk Quotation dialog.
7. Reopen an older `linear-2` line and confirm its documents are unchanged until it is saved.

## 8. Effort and order

1. `linear_runs.py` and its tests (packer only).
2. Engine Phase 2 behind the flag, plus boundary cables and endcaps, plus the fixed-point loop and
   engine tests.
3. `cable_manifest`, manufacturing text, groups, system design, compare.
4. UI feed list and leader inputs, reopen/allowlist plumbing, UI tests.
5. Audit report, staging pass, sign-off, flag on.

Roughly 4–6 working days of engineering, plus the staging review.

## 9. Decisions needed

- **D1 – Oversized single segment.**
  - When one segment's tape exceeds the maximum run, it must be fed again partway along. How is
    that built: a second leader through the back of the profile, or a feed-through at a field joint?
  - What leader length should that internal feed get? Proposal: the same as the fixture's leader
    length, with the cut recorded at its offset.
  - This also fixes today's 15 mm "additional feed" cuts on single-segment fixtures.
- **D2 – End of the segment before a break.**
  - With no jumper leaving, should that end take a **Solid** endcap (proposed), or stay Feed-Through?
- **D3 – Feed at a break.**
  - Default proposal: the new leader uses the feed type and direction already entered for that
    boundary's jumper.
  - Length default: segment 1's leader length, editable per fed segment in the results after
    calculation.
  - Should the dealer instead enter a feed type and direction for every potential break up front?
- **D4 – Leader allowance.**
  - Today only segment 1 deducts the template's leader allowance from the tape.
  - Should a segment that starts a new run also deduct it? Proposal: no, if a jumper entry and a
    leader entry use the same space in the endcap.
- **D5 – "Equal length runs" with whole segments.**
  - Proposal: the same number of runs as the default, with the split that makes the longest run as
    short as possible.
- **D6 – Rollout.**
  - Is the flagged rollout and audit report acceptable?
  - Should open (unsubmitted) quotes be left alone until someone reconfigures them? That is the
    proposal.
