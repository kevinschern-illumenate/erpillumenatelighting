**Configurator grouping and alignment — investigation and implementation handoff**

Prepared September 23, 2026, against local HEAD `845979669b3760fa49a80dd7000892a3a327838e`.

This is a plan, not an implementation. No application code or database records were changed during the investigation. Source references below use repository-relative paths and baseline line numbers; locate by function name if the code moves. Existing local changes to AGENTS.md, .claude, and .repowise were present before this work and must be preserved.

**1. Confirmed product decisions**

| Question | User's decision |
|---|---|
| What can be grouped? | One product family with shared specifications. No mixed-family or mixed-electrical-specification groups. |
| Power inclusion | One choice for the entire group. |
| Quantity | Schedule/order quantity multiplies the entire group, including its fixtures, cables, accessories, and included supplies. |
| Insufficient capacity in one supply | Allow multiple supplies within the same line, with a clear explanation. Prefer one compatible supply when it can serve the group. |
| Power excluded | Show requirements. The dealer adds power separately; do not automatically add another supply line. |
| Preserve existing behavior | Keep individual fixture lines and jumper-connected fixtures. Grouping is an additional level above those fixtures. |
| Categories | Linear fixtures, LED tape, LED neon, LED sheets. |
| Shared controls | Include power supplies for all four. Override max run length for linear, tape, and neon only. |
| Reported checkbox symptom | In the configurator opened from Quotation/Sales Order, the user could not uncheck power-supply inclusion. This is an interaction defect, distinct from the persistence and BOM defects found below. |

An independent fixture may itself contain jumper-connected segments. A grouped line must support both independent fixtures and those internal connections. A new fixture begins a new feed path; adding a jumper segment continues the current fixture's path. Never represent independent fixtures by concatenating them into the existing flat segment array.

Example: fixture type L1 contains three members with 6 ft / 20 ft, 3 ft / 5 ft, and 2 ft / 25 ft leader/fixture lengths. Requested fixture length totals 50 ft; explicitly entered leaders total 11 ft. These are separate measurements. Quantity 2 means six member fixtures, 100 ft requested fixture length, 22 ft of those entered leaders, and two copies of the per-group supply plan. Run splitting can require additional feeds; show those explicitly rather than hiding them in these totals. Manufacturing rounding and allowances determine the final illuminated length and wattage.

**2. Investigation scope and verification**

Traced portal routing, the coordinator and scoped JavaScript classes, the Quotation/Sales Order dialog, API payload adapters, family engines, configured-record identity, schedule saves, Item/BOM construction, transaction conversion, pricing, and the dispatch points for stock, exports, submittals, and manufacturing.

Repowise supplied the architecture, recent history, and change-risk context. Its broad answers were low confidence, so the findings below were checked against source. The index and local HEAD matched. Historic plans and inferred decision associations are background only; this request and the decisions above govern this work.

Verification performed:

- `python -B -m unittest illumenate_lighting.illumenate_lighting.api.test_led_sheet_math`: **34 tests passed**.
- Read-only AST/schema probes confirmed the linear hash omissions and missing tape/neon driver query fields.
- Executed the actual tape/neon BOM function in isolation with a stubbed Item UOM lookup: a 72-inch leader with stock UOM `Foot` produced quantity `72.0 Foot`. The correct unit conversion for that leader alone is 6 Foot.
- Frappe is not installed in this workspace. The repository CI provisions Frappe/ERPNext version 15 and runs Bench tests. No database-backed tests were run locally.
- Browser inventory returned no connected browser session. The reported deployed checkbox interaction was not reproduced on the live site; its likely causes and required reproduction steps are separated below.

**3. Current implementation and feature gaps**

| Area | Linear | LED tape | LED neon | LED sheets |
|---|---|---|---|---|
| Portal implementation | Inline coordinator in `configure.html`; scoped `Fixture` class for wizard | Inline coordinator, including jumper segments and bulk reels | Inline coordinator with jumper segments | Scoped `LedSheet` class |
| Quotation/Sales Order implementation | Scoped `Fixture` class | Scoped `TapeNeon` class, still using flat tape length | Scoped `TapeNeon` class | Scoped `LedSheet` class |
| Portal mode switch | Wizard/coordinator supported | Forced to coordinator | Forced to coordinator | Forced to coordinator, even though the content is a guided form |
| Independent fixtures under one configuration | No parent/member model | No parent/member model | No parent/member model | One coverage layout with electrical groups; these are not independent fixture members |
| Include power control | Present in both linear views | Ordinary portal and scoped forms lack it; bulk reels have their own control | Ordinary portal and scoped forms lack it | Present and passed through |
| Max-run override | Visible and passed to engine | Backend supports it; scoped JS looks for missing markup; ordinary portal does not send it | Same gap as tape | Not applicable |
| Persisted power plan | Driver child rows | No persisted driver-plan table | No persisted driver-plan table | Electrical group rows reference drivers |
| Manufacturing/schedule treatment | Drivers in fixture BOM; leader BOM section disabled | BOM omits drivers; cable handling needs repair | BOM omits drivers; cable accounting needs audit | BOM includes cables/supplies, while schedule/desk also create accessory rows |
| Edit restoration | Incomplete parity across surfaces | Incomplete parity across surfaces | Incomplete parity across surfaces | Existing schedule configuration is explicitly loaded |

Routing evidence: `illumenate_lighting/templates/pages/configure.py`, `get_context` around lines 57–66 and `get_configurator_markup`; `templates/pages/configure.html` around lines 284–355 and 1090–1120. Desk mounting: `public/js/desk/desk_dialog.js::mountConfigurator`, around line 883. These files are beneath `illumenate_lighting/` unless the full path is given.

The React application under `tools/configurator_ui` is a product-selection/handoff surface. It is not the implementation of the portal coordinator. Preserve its handoff and update its payload adapter only if required; do not start this work by rewriting that application.

**4. Findings that must be addressed before grouping is considered complete**

| ID | Finding and evidence | Required treatment |
|---|---|---|
| F1 | **Likely desk checkbox interaction cause:** reusable forms use fixed IDs such as `includePowerSupply` and labels with `for="includePowerSupply"`. `Base.instanceId` exists but does not namespace those IDs. Dialog close calls `teardownConfigurator`; `Base.destroy` removes registry entries without removing markup or handlers. Sources: `templates/includes/configurator_fixture_form.html:144`, `public/js/configurator/shared_configurator.js:27–67`, `public/js/desk/desk_dialog.js:245–254,923–928`. | Reproduce fresh/open-close-reopen and multiple dialogs. Unique DOM IDs and matching label targets, scoped field selectors, complete teardown, and native checkbox interaction tests. Duplicate-label targeting is a strong source-based hypothesis; do not claim it is the verified live root cause. If first-open fails too, inspect actual Desk CSS, hit testing, disabled ancestors, and loaded asset versions. |
| F2 | **Portal/scoped feature drift:** tape/neon controls are absent in `configurator_tape_neon_form.html`; JS `_getOverrideMaxRunFt` references missing controls. `configure.html:393–428` restricts the power section to linear; `tnValidateAndQuote:3703–3756` sends neither power inclusion nor override. Ordinary tape/neon results hide `driverResults` at line 3936. | One shared power section and payload contract. Show a power plan or external-power requirements for every family. Keep bulk reels as a distinct ordering mode. |
| F3 | **Stale calculation risk:** linear coordinator has no change handler for power inclusion; its `updateUI` does not invalidate `currentResult`. The scoped fixture class does invalidate it (`fixture_steps.js:205–231`). | Any configuration-changing input clears save/build eligibility. Ignore out-of-order responses and responses for a destroyed or changed instance. |
| F4 | **Linear configuration identity is incomplete:** `_build_singlesegment_config_data`, `_compute_candidate_multisegment`, and `_create_or_update_multisegment_fixture` omit `include_power_supply` and `override_max_run_ft`. Existing hash matches are then updated, including driver rows. Sources: `api/configurator_engine.py:208–224,351–364,2514–2543,2726–2755`. | Canonical, versioned identity must include all manufacturing/power-affecting inputs. Same geometry with power included/excluded must not mutate the same historical configured record. Also audit dimming/control selection in identity. |
| F5 | **Tape/neon power choice/plan are not persisted:** `_create_or_reuse_configured_tape_neon` omits inclusion from the hash, immediately reuses matching records, and has no power/driver persistence. Direct validators attempt record creation before adding their driver plan to the response. Sources: `api/tape_neon_configurator.py:850–896,1380–1423,2854–2925,2932–3069`; configured tape/neon DocType JSON. | Calculate the complete result before persistence. Persist inclusion, requirements, allocations, and related manufacturing inputs. Included/excluded configurations must have distinct build identities. |
| F6 | **Tape/neon driver selector does not match current schema:** it queries eligibility `driver`, and driver `voltage`, `cost_msrp`, `supported_dimming_protocols`. Current fields are `driver_spec`, `voltage_output`, `cost`, and child table `input_protocols`. It also reads voltage/protocol from the offering rather than resolving the linked tape spec. Sources: `api/tape_neon_configurator.py:2744–2783`; `doctype/ill_rel_driver_eligibility/*.json`, `doctype/ill_spec_driver/*.json`. These field mismatches were locally verified. | Replace duplicated driver loading with one schema-correct eligibility/spec adapter. Exceptions currently become warnings, so a superficially valid fixture can have no included supply. Included-power saves must require a complete supported plan. |
| F7 | **Sizing algorithms disagree:** linear uses load factor, output count, and total watts; tape/neon chooses a driver for `total_watts / runs_count` then orders one per run; sheets use rated watts without the same load factor/compatibility filters. Linear selection takes the first unit-cost candidate and may use several even when one larger supply works. It does not allocate actual run watts against `max_wattage_per_output`. Sources: `configurator_engine.py::_select_driver_plan`, `tape_neon_configurator.py::select_driver_plan_for_tape_neon`, `led_sheet_configurator.py::_get_eligible_drivers`, `led_sheet_math.py::build_groups`. | Shared planner based on actual circuit loads, rated/usable capacity, per-output limits, compatibility, and supported wiring. Prefer one feasible supply for a group, then minimize supply count. An average run wattage is insufficient for unequal members. |
| F8 | **Power lost in desk adapters:** tape/neon builder dispatch uses `bool(payload.get(...))`, which treats string `"false"` and `"0"` as true. `_tape_neon_payload_from_portal_selections` only forwards segments for neon. Scoped tape/neon stores override in request kwargs, but not in its saved `lastCalcSelections`; builder dispatch does not forward a top-level override. Sources: `configured_product_builder.py:493–506,824–849,853–910`; `tape_neon_steps.js:440–501,741 onward`. | Central boolean/numeric normalization and one canonical request for calculate, save, and reopen. Forward tape segments and override on every path. |
| F9 | **Linear leader cables are absent from the BOM:** the leader block is commented out with a TODO at `manufacturing_generator.py:852–862`, despite lengths/items being stored on segments/runs. | Implement leader resolution and quantity/UOM accounting. Do not merely sum current member BOMs, or the requested 6 ft, 3 ft, and 2 ft leads will still be missing. |
| F10 | **Tape/neon cable BOM defects:** tape BOM uses top-level leader length even with segmented tape; neon sums incoming/outgoing cable fields and needs ownership/double-counting validation. Leader quantity is in inches but is labeled with the Item stock UOM without conversion. `api/tape_neon_bom.py::build_tape_neon_bom_items`. | Model each physical cable once, preserve cut lengths, convert units explicitly, distinguish bulk cable from preassembled cable Items, and include every member's leader and every internal jumper exactly once. |
| F11 | **Tape/neon BOM explicitly excludes drivers:** `tape_neon_bom.py:29–37`. Its comment points to row-level handling, but `_apply_artifact_to_row` only stamps power metadata; the inspected configured-product builder has no corresponding tape/neon supply-row creation. | Use persisted power allocations as the single source for included supply components and price. For grouped lines, supplies belong to the combined BOM, with no duplicate transaction rows. |
| F12 | **Sheet schedule/BOM representation conflicts with the requested bundle:** `_apply_multi_line_schedule` adds cable/supply rows, while `led_sheet_bom.py` also includes those materials. Sheet saved MSRP is panels/options only. Sources: `led_sheet_configurator.py:253–269,388–442`; `desk_configurator.py::_led_sheet_accessory_rows`. | New grouped sheet lines must bundle components and price them once. Specify the same bundled behavior for new single-sheet configurations in the aligned flow; retain an explicit legacy presentation mode for old exploded lines. |
| F13 | **Sheet Item identity can collapse distinct builds:** sheet configuration hash includes dimensions and inclusion, but `part_number` does not. `_ensure_configured_artifacts` uses `sheet.configured_item or sheet.part_number`, then reuses the Item/default BOM. Sources: `led_sheet_configurator.py:146–158,240–251`; `quote_order_configurator.py:335–347`. | Include a configuration/build identity suffix in configured Item identity. Same catalog code with different areas or power choices must have different configured Items/BOMs. Do not rename historical Items automatically. |
| F14 | **Sheet accessory ownership is too broad:** generated markers identify the configured sheet, not its schedule line. Two lines reusing one configuration can remove/rescale each other's generated accessories. `led_sheet_math.py::generated_accessory_marker`, `led_sheet_configurator.py::resync_led_sheet_line_accessories`. | Grouped/new bundled saves create no sibling accessories. If legacy accessory synchronization remains, attach ownership to a stable schedule-line key; never remove accessories by configuration name alone. |
| F15 | **Pricing has separate notions of fixture and supply total:** linear `_calculate_pricing` adds supply display entries while returned `msrp_unit` remains fixture MSRP; driver quantity is embedded in description rather than a numeric breakdown quantity. Tape/neon prices are calculated before driver selection. Sheet prices deliberately split panel and accessories. | Define a per-group unit price and numeric component breakdown. Include supplies once when requested; exclude their price when not requested. Apply group quantity exactly once. Preserve ERPNext customer/price-list behavior. |
| F16 | **Existing contracts are singular end to end:** schedule status checks, conversions, desk artifact dispatch, stock rendering, exports, and submittals switch on the three configured-record links. A front-end-only array will not survive them. | Add explicit aggregate dispatch before family-specific branches and carry a pinned build/BOM snapshot through all consumers. |

Additional behavior to retain or tighten: sheet validation currently requires eligible drivers even when inclusion is false (`led_sheet_configurator.py:232`); max-run override currently replaces the default run-length threshold, including the calculated watt-based limit (`configurator_engine.py:1827–1834`). Separate run partition policy from driver capacity validation. Selecting an override must never cause the new power planner to ignore the actual selected supply's capacity.

**5. Target user flow**

Use the same vocabulary, controls, state, and review output in portal and Desk. Guided wizard and coordinator become views over the same state and API; their difference is pacing/layout.

1. Select product category and family. Use the existing template cards, cascading options, and product imagery.
2. Set shared specifications once: the family's valid light engine/output/CCT, environment, finish, mounting, lens where applicable, and control requirements. Preserve multi-CCT behavior. Family-specific choices remain visible only where applicable.
3. Choose **Single fixture** or **Group of independent fixtures**. Single starts with one member. Group preserves that member and exposes **Add fixture**, **Duplicate**, and **Remove**. This is separate from the guided/coordinator view switch.
4. Edit members. Linear/tape/neon members have their own leader/feed and fixture lengths. **Add jumper segment** operates only inside the selected member. Sheet members represent independent coverage areas with width/height, a panel layout, and the template-supported feed/cable choices. Do not invent linear length fields or a max-run override for sheets.
5. Choose **Include power supplies** once. If enabled, show selected supplies, usable capacity, actual group load, and which member/run uses each output. If more than one is needed, explain the limiting factor. If disabled, show load, voltage/control requirements, and feed requirements; do not create supply Items/BOM rows/schedule lines.
6. For linear/tape/neon, expose one optional group-wide max-run override. Apply it independently within every member's electrical path, including that member's jumper chain. Do not test the sum of all independent member lengths against a single serial-path max run. Show per-member splits and the existing override disclosure consistently.
7. Review one line: fixture type/location, member list, requested versus manufacturable dimensions, total watts, included/excluded supply status, component breakdown, unit price per complete group, group quantity, and extended total.
8. Save through the same path whether invoked from portal, Quotation, or Sales Order. Reopen restores the exact member hierarchy, power choice, override, and family options. Switching views preserves unsaved selections and invalidates only calculations affected by actual data changes.

Treat shared specifications as one selected template and compatible resolved light-engine/spec set. Preserve legitimate per-segment choices, such as feed direction and existing neon endcap/IP choices; ensure the final members still meet group compatibility. Changing shared specs recalculates every member and identifies any now-invalid field.

Bulk tape reels remain a catalog/reel ordering workflow. Keep their existing behavior and power-option normalization; do not silently convert reels into cut-to-length group members. Grouping applies to configured fixtures/coverage areas in this phase.

**6. Recommended data and service design**

Introduce a normal parent DocType, provisionally **`ilL-Configured-Fixture-Group`**, for grouped lines. Keep `product_type` as Linear Fixture / LED Tape / LED Neon / LED Sheet; “grouped” is configuration mode, not a fifth product category. Keep existing configured family DocTypes for single fixtures and as optional member links.

The parent should own: schema/engine version, product type, template identity, normalized shared selections, normalized request JSON, immutable computed/build snapshot, input hash, build hash, include-power flag, override policy where supported, total load/length or coverage metrics, members, supply plan/allocations, configured Item/BOM links, and lineage/source metadata. Customer-specific discounts and schedule labels do not belong in manufacturing identity.

Add a group-member child table with stable member ID, display order/label, optional typed family-configured link, normalized member input, computed snapshot, and summary quantities. Frappe child tables cannot be nested arbitrarily: store a schema-validated member snapshot containing its segments/runs, or use the existing standalone family record for those child tables. Do not attempt a child-table-within-child-table design. The parent build snapshot must remain sufficient to reproduce the BOM even if a linked member document later changes.

Persist the supply selection and typed driver/run allocations at the parent. Each allocation must identify member ID, run/circuit ID, driver instance, output, load, and relevant capacity. Include distribution accessories in the component manifest when the selected wiring arrangement requires them.

Add `configuration_mode` and `configured_group` to schedule lines, plus a group reference on transaction rows. Existing `ill_configured_product_doctype` / `ill_configured_product` / `ill_configuration_json` can carry the generic source and snapshot. Keep explicit family fields clear on a group line so legacy code does not accidentally treat one member as the entire line. Dispatch on the aggregate first. Preserve fixture type, Section / Room, notes, stable schedule-line identity, and quantity independently of the reusable build.

Proposed canonical request (field names are a contract proposal, not existing APIs):

```json
{
  "schema_version": 2,
  "product_type": "Linear Fixture",
  "configuration_mode": "grouped",
  "template_code": "<one selected family>",
  "shared_selections": {"<family option>": "<selected value>"},
  "power": {"include_power_supply": true, "dimming_protocol_code": null},
  "run_policy": {"override_max_run_enabled": false, "override_max_run_ft": null},
  "members": [
    {"member_id": "m1", "label": "Fixture 1", "input": {"segments": ["<normalized segment object>"]}},
    {"member_id": "m2", "label": "Fixture 2", "input": {"segments": ["<normalized segment object>"]}}
  ]
}
```

Define the actual segment schema once: requested fixture length, start feed and leader length, end type, and outgoing jumper fields. Use normalized millimeters with a documented precision; retain display units separately. A sheet member instead has normalized coverage width/height and its supported feed inputs. Do not send client-computed watts, BOM quantities, prices, or validity as authoritative input.

Keep schedule target, line identity, optimistic-lock version, and group quantity in the save envelope. Calculate one group's manufacturing requirements; multiply for display/ordering separately. Do not use schedule quantity to choose a larger shared supply spanning multiple copies of a group.

Recommended service boundaries, as new modules under `illumenate_lighting/illumenate_lighting/api/`:

- `configuration_contract.py`: validation, aliases, booleans, numeric/unit normalization, canonical identity, old-payload adapters.
- `fixture_group_configurator.py`: member orchestration, pure preview, group save, group edit payload.
- `power_planner.py`: schema-correct eligibility loading and common deterministic selection/allocation. Keep pure allocation math separable from database lookup.
- `fixture_group_bom.py`: manifest aggregation, configured Item/BOM creation, and traceability.

Keep family geometry, cut increments, profile splitting, sheet tiling, and valid option mappings in the existing engines. Add a preview/member-compute boundary rather than calling today's record-creating endpoints in a loop. Existing `_skip_record_creation` hooks help, but direct tape/neon persistence calls include commits and are unsuitable inside a group transaction.

For single mode, use the same request/state/power services with one member, while retaining the family configured-record persistence adapter. Fix their identity, power persistence, and BOM defects as part of this work. New sheet single-mode saves in this aligned flow should use bundled pricing/BOM output; legacy exploded sheet configurations retain a versioned legacy mode until explicitly reconfigured.

**7. Calculation, power selection, and BOM rules**

Compute each independent member separately, with family rules intact. Aggregate results afterward. A single segment may be split into physical stock pieces and electrical runs; these are different from user-defined jumper segments and from independent members. Use explicit IDs for all four concepts in the snapshot and manufacturing output.

Normalize power decisions centrally. Support real JSON booleans and legacy numeric/string representations (`false`, `0`, `"false"`, `"0"`); apply defaults only to absent values. Validate finite positive lengths and overrides, reject NaN/infinity, and do not quietly turn an enabled but invalid override into a disabled one. Reject sheet overrides at the API boundary.

The shared power planner should:

1. Resolve voltage, load, light-engine output protocol, requested dimming inputs, eligible drivers, usable load factor, output count, and `max_wattage_per_output` from the actual DocTypes. Explicitly handle missing catalog data.
2. Receive each actual run/circuit load. Never replace unequal loads with `total_watts / runs_count`. Track branch/feed topology separately from total load.
3. Try eligible single-supply allocations first. For feasible single-supply choices, use deterministic cost/capacity/priority tie breakers. If none works, find a feasible allocation with the fewest supplies, then apply the documented cost/capacity tie breakers. Cost means total selected cost, not the first driver's unit price. Do not describe a greedy fallback as globally minimal unless it has been proved for the supported candidate set.
4. Respect both total usable capacity and per-output capacity on every assigned output. Driver color/control channels must not be mistaken for interchangeable independent power outputs.
5. Model allowed parallel branches explicitly. Existing `outputs_count >= runs_count` can unnecessarily require several supplies for independent fixtures that may legally share a supported output, but removing that check blindly is also wrong. Use template/driver wiring capabilities or add a narrowly scoped distribution-capability mapping. If the catalog cannot establish supported fan-out or connector capacity, return an actionable configuration-data error; do not invent the wiring. Add required distribution hardware to the BOM.
6. Preserve member run limits and topology. Sharing a larger power supply does not erase a member's run-length split. If a single load cannot fit any supported output, use an existing supported split/feed operation or return an error; do not divide its watts across outputs without a corresponding connection plan.
7. Return selected supplies, assignments, required external-power specifications, limiting reasons, and a stable manufacturing snapshot. With inclusion off, continue calculating requirements; an unavailable catalog supply should not by itself prevent an otherwise valid externally powered configuration. Actual product geometry/feed constraints still apply.

Sheets need a member/area calculation before group power planning: round panel counts per area with `compute_panel_layout`, then plan the combined electrical load without merging separate areas into one rectangle. Preserve the existing two-jumpers-per-panel rule unless catalog rules supersede it. Derive leaders from actual feed groups/areas, not merely from supply count: three independent areas may still need three leaders when they share one supply. Do not add a dealer max-run override to sheets.

Build one flat combined BOM for one complete group. Generate each member's non-power materials, include every member's feeds/cables/accessories, and add the parent supply/distribution plan once. Preserve member cut/assembly instructions even when identical stock Items are merged. Merge only compatible rows with consistent Item, UOM/conversion, warehouse and manufacturing semantics; do not erase distinctions required for cut lengths or assembly operations. Use a component manifest plus per-member cut schedule so “132 inches of cable” still documents the required 72/36/24-inch pieces.

Repair the existing BOM helpers before reuse: enable and accurately resolve linear leaders; account for segmented tape cables; give each jumper one physical owner so inherited starts do not duplicate it; convert length units to the actual stock/billing unit; distinguish fixed-length assembled cables from bulk cable. Required missing material mappings are save-blocking errors, not silently omitted BOM rows.

Group BOM quantity is 1. A transaction with quantity 2 references that BOM with quantity 2. Do not build a doubled BOM and then multiply it again. Included supplies appear once in the parent BOM and bundled price. Excluded supplies appear in neither, and do not create separate schedule/order rows.

Pricing must return a numeric breakdown with `qty`, `unit_msrp`, and `extended_msrp`, plus group unit MSRP, customer-tier group unit price, and line extended price. Sum member assembly prices, applicable cable/accessory adders, and included group supplies once. Preserve template base-charge semantics per independent manufactured fixture; do not use a single 50-ft fixture's base charge for three independently built fixtures. Retain existing price-list and customer-group Pricing Rule handling and test discount application exactly once.

**8. Identity, persistence, and historical compatibility**

Use one canonical identity implementation for preview, save, lookup, variant creation, and rehydration. Include template/spec selections, member geometry/topology, leader/jumper dimensions, mounting/accessory choices, power inclusion, dimming, normalized active override, and schema/engine version. Presentation labels, random member IDs, schedule/location, view mode, and group quantity do not make a different manufactured configuration. Normalize aliases and units before hashing.

Distinguish the normalized input hash from a build hash/fingerprint that includes resolved component quantities and the chosen power plan. Catalog or engine changes may produce a different build for the same request. Reuse only an identical pinned build; never rewrite a build/BOM referenced by an existing quote/order. Price-list changes should not masquerade as manufacturing changes. Store customer-specific prices on the appropriate pricing/transaction snapshot, not in a globally shared manufacturing identity.

Use a group-specific Item code, for example `ILL-GRP-<build-hash-prefix>`, with collision handling. L1 remains the schedule fixture-type label; the member descriptions remain readable. For sheet singles, preserve the readable product part number but give each distinct configured Item a build-specific identity. A part-number match alone is not a configuration match.

Saving must revalidate canonical inputs on the server and atomically persist the group, member snapshots, supply allocations, Item/BOM/price artifacts, and schedule attachment as appropriate. Do not trust client `is_valid`, supplied computed totals, or the client BOM. Use request-scoped transaction handling and idempotency; remove/avoid lower-level explicit commits on this path. Failures must not leave a half-configured schedule line, orphan group members, or a saved row with no usable BOM.

Preserve existing permissions, configured-record provenance/handoff checks, editable status checks, and parent-document restrictions. Extend `portal/access.py` and configured-record dispatch deliberately for the new parent. Reuse of a global catalog build does not grant access to another customer's schedule/member metadata. Use a stable schedule child-row ID and optimistic concurrency check so a row reorder or concurrent edit cannot overwrite a different line; keep legacy zero-based `line_idx` adapters for compatibility.

Do not mass-rehash/rename old configured records or rebuild/deactivate all submitted BOMs. Introduce versioned fields and additive migrations. Existing records continue to render and convert with their pinned snapshots. When a user edits an old configuration, normalize it into the new request and create a new build if manufacturing choices differ. Do not silently overwrite historical records whose old hash omitted power inclusion. Provide an audit/report for potentially affected configurations; repair requires identifiable expected configuration, not guessing from today's defaults.

For existing exploded sheet accessories, preserve historical rows. On explicit conversion to the new bundled form, remove only generated accessories owned by that exact schedule line, preserve manual accessories, and do not rewrite already-submitted transactions. Update legacy marker ownership to a stable parent-line key where needed.

**9. Implementation sequence and acceptance gates**

| Phase | Concrete work | Gate before proceeding |
|---|---|---|
| A — Reproduce and repair current defects | Desk checkbox interaction; instance IDs/labels; teardown; canonical false parsing; result invalidation; missing controls/payloads; tape/neon driver schema; power/override identity and sheet Item identity; targeted regression tests. | Checkbox toggles by box, label, and keyboard on first use and after reopen in both Quotation and Sales Order. False survives calculate/save/reopen/BOM. Existing jumper fixtures still work. |
| B — Contract and aggregate schema | Versioned normalized request/result; capability metadata; group parent/member/allocation schema; schedule/transaction links; permission and migration support; canonical input/build identity. | Single and grouped payload round trips; incompatible members rejected; one-member single adapter matches intended existing geometry; no historical record changes. |
| C — Member calculation and shared power | Pure previews for all four families; real run loads; common eligibility; usable and per-output capacity; one-supply preference and multi-supply fallback; external-power requirements; sheet areas/feed groups. | Unequal-run tests, per-output overload tests, split/topology tests, and missing-catalog tests pass. Parent power includes no per-member duplicates. |
| D — Manufacturing and pricing | Fix cable BOM helpers; generate member manifests/cut instructions; flattened group BOM; group Item/price; sheet bundled mode; failure rollback/idempotency. | L1 example produces all three leaders and fixtures, correct supply/distribution components, one line/one parent BOM, quantity scaling once. |
| E — Shared UI | Extract inline portal coordination into reusable scoped modules; use one state/store and payload adapter in wizard/coordinator/Desk; member editor; shared power panel; capability-driven family fields; consistent review and edit restoration. | Same normalized request in all applicable views produces the same build hash, BOM and price. Mode switches preserve work. All four families have the correct controls. |
| F — Downstream integration | Schedule save/edit/status/version/duplicate; Quotation/Sales Order conversion; pinned BOM/work-order generation; dealer pricing; stock allocation; exports/submittals/labels/travelers. | A group survives the complete business workflow with one commercial line, correct group quantity, all member instructions, and no dropped/duplicated power or materials. |
| G — Rollout | Bench migration/build/cache refresh on a test site; catalog capability checks; staging UI/data tests; opt-in rollout/feature flag, then enable for dealers. | Fresh and upgraded-site tests pass; old single, jumper, reel, and exploded-sheet workflows remain readable and correct; no stale assets or duplicate IDs after repeated dialog use. |

Phases are delivery boundaries, not independent rewrites. Family engines remain the source for product-specific geometry. Do not release a visible group toggle before persistence, BOM, conversion, and edit-restoration gates are complete.

**10. File-level implementation map**

All paths in this table are relative to `illumenate_lighting/`.

| Files / symbols | Work |
|---|---|
| `templates/pages/configure.py::get_context`, `get_configurator_markup` | Category capability metadata; consistent mode support; existing/group edit payloads; shared markup entry point. |
| `templates/pages/configure.html` and `templates/includes/configurator_{form,fixture_form,tape_neon_form,led_sheet_form}.html` | Extract inline state/validation/save logic; common member/power/review UI; correct accessible checkbox markup. |
| `public/js/configurator/shared_configurator.js` | Instance identity, lifecycle, canonical state/request handling, pending-response guards, common schedule/edit context. |
| `public/js/configurator/{fixture_steps,tape_neon_steps,led_sheet_steps}.js` | Family adapters and shared member editor; tape segments in Desk; power/override plumbing; invalidation; consistent restore/save. |
| New `public/js/configurator/fixture_group_editor.js` and shared power/review components | Independent-member editing around the existing family/segment controls. Names are proposals. |
| `public/js/desk/desk_dialog.js`, `public/js/quote_order_configurator.js` | Correct disposal/remounting, canonical payload, grouped row insertion, document-only and unsaved-document support. |
| `public/css/configurator/*.css` | Scoped controls that work in Desk and portal, keyboard/focus states, responsive member list, no reliance on ambiguous label targets. |
| `illumenate_lighting/api/configurator_engine.py` | Geometry preview boundary, complete identity, common power adapter, computed requirements independent of inclusion. |
| `illumenate_lighting/api/tape_neon_configurator.py` | Correct schema loading, full payload/persistence, tape segments through adapters, no record writes during preview, run/cable ownership. |
| `illumenate_lighting/api/led_sheet_configurator.py`, `led_sheet_math.py` | Independent areas, external requirements without forced supply selection, new bundled schedule mode, legacy accessory ownership. |
| Existing configured DocTypes/controllers and new group/member/allocation DocTypes | Inclusion/override/control fields, snapshots, hashes, build identity, immutable lineage, validations. Audit DocType fallback hash methods too. |
| `illumenate_lighting/api/manufacturing_generator.py`, `tape_neon_bom.py`, `led_sheet_bom.py` | Correct leaders/jumpers/UOM, persisted drivers, member manifests, parent BOM, Item identity and work-order dispatch. |
| `illumenate_lighting/api/configured_product_builder.py`, `desk_configurator.py`, `quote_order_configurator.py` | Shared calculate/save/lookup/preview paths, robust false parsing, all segment/override fields, group artifact dispatch, bundled pricing. |
| `illumenate_lighting/api/portal.py` and `illumenate_lighting/portal/access.py` | Group attach/read/edit/provenance, status checks, server-authoritative totals, stable line target and quantity updates. |
| `illumenate_lighting/doctype/ill_child_fixture_schedule_line/*` and `ill_project_fixture_schedule/*` | Group link/mode, complete-status validation, version/copy handling, aggregate-first conversion, quantity semantics. |
| `templates/pages/schedule.py`, `schedule.html` | Group summaries, expanded members, correct edit links, price/stock totals, configuration status. |
| `illumenate_lighting/api/pricing_utils.py` | Components from the same canonical manifest as the BOM; stock shared across members/lines; correct tier price aggregation. |
| `illumenate_lighting/api/exports.py`, `spec_submittal.py`, relevant spec/drawing/traveler and print-format consumers | Group summary plus member dimensions/feed schedule and included supply information; avoid displaying a sum as one physical fixture. |
| `patches/`, `patches.txt`, transaction custom-field installation, `hooks.py` | Additive schema/custom fields, asset inclusion in Desk and website, migration/feature flag, event dispatch. |

Legacy `/portal/configure-multisegment`, `/portal/configure-tape`, `/portal/configure-sheet` and Webflow handoff entry points must either adapt into the common controller or redirect with category/template/schedule context preserved. Do not leave active legacy pages calling an incomplete second grouping implementation. Preserve existing sheet redirect index translation.

**11. Required regression and acceptance scenarios**

| Scenario | Expected result |
|---|---|
| User's L1 example, all four applicable family flows | Independent member boundaries retained; leaders 72/36/24 inches retained; aggregate load uses manufactured member output; one supply when feasible. Sheet equivalent uses three independent areas rather than lengths. |
| Same geometry expressed in inches/feet/mm | Same normalized manufacturing identity and BOM within defined precision. |
| Group quantity 2 | Two complete groups; no supply upsizing across groups; no double multiplication of BOM or price. |
| One grouped member has two jumper-connected segments | Exactly one internal jumper; independent members still have separate leaders and reset their own run accounting. |
| One member exceeds normal max run | That member splits according to existing rules; other members do not inherit its serial-path position. Additional feeds appear in review/BOM. |
| Override enabled/changed/disabled | Correct per-member splits; true/false policy survives every adapter, save, reopen and view switch; build identity changes as appropriate. Sheets offer no override. |
| Unequal loads, e.g. 20 W and 100 W | No selection based on 60 W average; actual output assignment respects capacity. |
| Total capacity passes but an output would overload | Planner rejects that allocation or selects a feasible alternative. |
| Several low-cost supplies versus one suitable larger supply | One supply preferred per confirmed requirement; fallback minimizes count and explains why multiple are necessary. |
| Parallel branches share a supported output | Valid distribution mapping and any needed hardware retained. Unsupported/unknown fan-out is not assumed. |
| Include false in boolean/numeric/string forms | No supply components, supply cost, or automatically added supply lines; requirements remain visible. |
| Included power but no compatible driver | Clear blocking error; no half-built Item/BOM/schedule attachment. External-power mode remains available when geometry/feed requirements are otherwise valid. |
| Toggle inclusion after calculation | Save/build disabled until recalculation; stale response cannot re-enable saving a previous choice. |
| Desk checkbox first open, close/reopen, Add another, Back/forward, multiple modals | Box/label/Space all toggle only the intended instance; no duplicate IDs or detached callbacks change another instance. Test Quotation and Sales Order, new and existing documents. |
| Saved included and excluded variants with same geometry | Different build/Item/BOM identities; earlier records/orders remain unchanged. |
| Same sheet part number, different dimensions or inclusion | Distinct configured Items/BOMs, correct bundle prices; no accidental default-BOM reuse. |
| Two schedule rows reuse one sheet/group configuration | Independent quantities and ownership; editing one does not remove the other's accessories or change its build. |
| Cable Item stock UOM Foot/Meter/Inch/Nos | Correct converted quantities; Nos requires an appropriate fixed-length cable mapping; jumper counted once. |
| Compare wizard/coordinator/Desk | Identical inputs yield identical normalized requests, manufacturing results and pricing; controls and edit restoration are consistent. |
| Schedule → Quotation → Sales Order → Work Order | One commercial group line with correct quantity and pinned BOM; complete member cut/feed instructions; no implicit raw-component explosion for group lines. |
| Exports, stock, submittals, travelers | All members represented; shared supply counted once; stock consumption matches BOM and group quantity; excluded power is clearly described. |
| Failed member validation or BOM save, retry/double click, concurrent line edit | No partial group; idempotent artifacts; no duplicate line; clear concurrency error instead of overwriting the wrong row. |
| Legacy records and entry points | Existing single fixtures, jumper chains, tape reels, sheet lines, approved overrides, variants, and handoffs retain intended behavior. |

Extend existing relevant tests: `test_configurator_engine.py`, `test_tape_neon_configurator.py`, `test_led_sheet_math.py`, `test_manufacturing_generator.py`, `test_desk_configurator.py`, `test_quote_order_configurator.py`, `test_dealer_order_conversion.py`, `test_portal_access_matrix.py`, `test_portal_status_and_stock.py`, `test_exports.py`, and `doctype/ill_project_fixture_schedule/test_ill_project_fixture_schedule.py`. Add focused group/power-planner tests and real browser interaction tests; backend-only tests cannot verify the reported checkbox defect.

Use pure unit tests for normalization, identity, circuit allocation, and component aggregation. Use a Frappe test site for schema, permissions, transactional persistence, Item/BOM reuse, pricing, and conversion. Browser tests must run against the actual Desk and portal asset stack, including repeated modal lifecycle and keyboard interaction. Do not replace browser interaction assertions with source-string checks.

Implementation validation commands should include scoped `ruff check` and `ruff format --check`, `node --check` for changed JS, pure Python tests, and the repository CI-equivalent `bench --site <test-site> run-tests --app illumenate_lighting` after migration/build. Run on both a fresh test site and an upgraded copy with representative historical configurations. Do not install Frappe into this Windows workspace merely to simulate Bench.

**12. Completion criteria for the implementing chatbot**

The feature is complete when a dealer can choose single or grouped configuration in each requested family, keep internal jumpers, select shared specifications and one power policy, save a complete group as one commercial line with one combined buildable BOM, reopen it losslessly, multiply its quantity correctly, and carry it through quote/order/manufacturing without missing or duplicated materials or power. The Desk checkbox must work through mouse, label, and keyboard on repeated use, and its false value must reach the saved build.

Begin implementation with Phase A's reproduction and the normalized contract. Treat the source-confirmed defects as work items and the deployed checkbox explanation as a hypothesis requiring UI confirmation. Keep catalog-data limitations explicit in planner errors rather than hiding them behind successful validation. Report actual tests run, remaining environment limitations, and migration impact at handoff.
