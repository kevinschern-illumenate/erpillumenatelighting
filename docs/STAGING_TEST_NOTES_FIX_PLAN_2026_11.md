# Staging test notes: fix plan (2026-11)

Each note from the staging walkthrough with its cause, what was changed on `staging`, and what
is still open. "Done" items have unit tests; the Frappe bench tests were not run in this pass.

| # | Note | Status |
|---|------|--------|
| 1 | Dealer portal: requesting an address change gives a 500 | Done (errors now readable); root cause to confirm from the Error Log |
| 2 | Dealer portal: inviting a company member gives a 500 | Done (errors now readable); root cause to confirm from the Error Log |
| 3 | Import Lines CSV template is too bare | Done |
| 4 | Linear build preview draws runs wrongly | Done (preview); engine decision open (4b) |
| 5 | Fixture template MSRP adder should be per foot | Done |
| 6 | Multi-segment build description stretches the lines table | Done |
| 7 | "Add by part number" leaves length, feed and leader blank | Done |
| 8 | Profile "Finish" dropdown is empty in Add Fixture Line | Done (code); catalog data clean-up open |
| 9 | LED sheet preview shows one group while the supply has two outputs | Preview done; driver data to check |

## 1-2. Account requests and invitations return HTTP 500

**Cause.** `portal/accounts.py` signals problems with plain `ValueError`. Examples are "This record
changed. Reload before requesting a change." and "Valid email and first name are required".
Frappe answers any exception that is not a Frappe exception with a bare 500. The portal therefore
only logged `POST / 500` to the console, and the dialog had nothing to show. Adding a contact works
because that path inserts a Contact directly. Requesting a change and inviting someone go through
`_new_request` and `invite`, which raise.

Nothing in the code or the unit tests reproduces a failure on valid input. So the specific reason
the staging call failed is still unknown and has to be read from staging.

**Changed.**
- `portal/errors.py` has a new decorator, `service_endpoint`. It turns a raised error into
  `{"success": false, "error": ...}`:
  - Expected errors (validation, permission, `ValueError`) keep their message.
  - Anything else is written to the Error Log, and the reply carries the Error Log reference.
  - Partial writes are rolled back.
- Every dealer-facing endpoint in `accounts.py` uses it: request change, save, archive, purchasing
  contact, dealer logo, invite, resend, accept, revoke, disable member, reply. The portal dialogs
  already show `error` to the dealer.
- `api/portal.py` contact creation now passes a refusal from `save_record` back instead of failing
  on `receipt["name"]`.

**Next step on staging.**
1. Deploy, then repeat both actions.
2. The dialog now shows either the reason or "Something went wrong … (reference ERR-…)".
3. If it shows a reference, open that Error Log in Desk; the traceback gives the root cause.
4. If it shows a reason such as "This record changed", the dealer can act on it.

The invitation path has two places to look first. One is user creation (`_create_invited_user`
inserts a Website User). The other is the outbox records (`ilL-Portal-Event` and
`ilL-Portal-Delivery`).

## 3. Import Lines CSV template

**Changed.**
- The template now has every importable column, not just the first seven.
- It opens with guidance rows explaining:
  - ILLUMENATE, OTHER and ACCESSORY, and how a blank type is inferred;
  - which columns each kind needs;
  - quantity and length rules.
- It has example rows:
  - ilLumenate linear fixture with a part number;
  - ilLumenate linear fixture without a part number;
  - LED tape or neon;
  - LED sheet;
  - another manufacturer's fixture with its model, lamp, dimming, voltage and finish;
  - an accessory by Item Code.
- Every guidance and example row starts with `#`. The importer now skips rows whose first cell
  starts with `#`, so a dealer can type their lines under the examples and upload the file
  unchanged.
- The file carries a UTF-8 byte-order mark so Excel opens it correctly.

Files: `portal/schedule_import.py` (`TEMPLATE_ROWS`, comment rows), `templates/pages/schedule.py`
and `schedule.html` (context), `public/js/portal/schedule/line_import.js` (download).

## 4. Build preview (all families)

**Cause.**
- Single-segment linear builds return runs without a `segment_index`.
- Multi-segment runs carry the first piece of the user segment they start in.
- The preview placed each run on "its" piece and shrank it to fit. Every run of a long segment
  therefore landed on piece 1, as in the reported HTML: two 149.6" runs drawn inside the first
  78.7" piece.
- Every physical piece of one segment was also labelled "Segment 1".

**Changed** (`public/js/configurator/build_preview.js`):
- Runs are laid end to end along the tape and mapped onto the pieces. A run that crosses a field
  joint or a jumper is drawn on every piece it covers.
- Each run gets a feed point where it really starts. In the reported build, run 2 now starts part
  of the way along the second piece.
- Pieces are labelled "Segment N, piece k of n".
- The summary reads, for example, "1 segment, 4 pieces, 2 runs…".
- A jumper's tooltip now says whether the run continues into the next segment or the next segment
  starts a new run with its own feed. Segments without a jumper show a dotted break.
- Tape and neon keep their per-segment runs, laid out the same way.
- LED sheet: see item 9.

### 4b. Decision needed: multi-segment linear run boundaries

The linear engine (`_compute_multisegment_outputs`, phase 2) splits runs by **total tape
length**:
- full-length runs first, then the remainder;
- regardless of where one segment ends and the next begins.

With four jumpered segments and two runs, run 2 can therefore start part of the way along
segment 3. The preview now draws that faithfully. The note describes what should be supplied
instead: segments 1–2 joined by a jumper on one feed, and segments 3–4 on their own feed.

That is an engine change, not a preview change:
1. Pack whole segments into runs up to the maximum run length. Split a segment only when it alone
   exceeds that length.
2. Where a run boundary falls between segments, replace that segment's end jumper with a leader
   for the next run.

This changes BOM cable lines, leader quantities, driver plans, prices and build identities for
existing multi-segment builds, so it needs sign-off before implementation.

## 5. MSRP adder per foot

**Changed** (`api/configurator_engine.py::_calculate_pricing`):
- A fixture template option's `msrp_adder` (Finish, Lens Appearance, Mounting Method, Power Feed
  Type, Environment Rating) is now per foot. It is multiplied by the same priced length as the
  template's $/ft (`pricing_length_basis`).
- The breakdown shows, for example, "Finish (Black): 3.12ft x $25.00/ft".
- Endcap Style adders stay a flat amount per endcap, because they are already charged once per end.
- The field is relabelled "MSRP Adder ($/ft)" and its description explains this.
- Tape/neon and LED sheet adders are unchanged.

**Check before deploying.** Any adder already entered as a flat amount on a fixture template will
now be multiplied by the length. Review fixture templates with non-zero adders and convert them to
$/ft. Saved builds keep their pinned price snapshot; live re-estimates use the new rule.

## 6. Build description width on the lines table

**Cause.** The multi-segment "Build" text was one Bootstrap `.badge`, which is `white-space: nowrap`,
with every segment joined by "; ".

**Changed.** Each segment is now on its own line, and the badge wraps (`.ill-build-lines` in
`_schedule.scss`). The table grows taller instead of wider.

## 7. Add by part number

**Cause.** The decoder reads length, start feed type and leader length from the part number but
only showed them in the review banner. `configure.py` passed only the option selections, so the
segment card kept its blank defaults.

**Changed.**
- `portal/part_number.py` returns a `segments` entry for a single-segment part number:
  - length;
  - start power feed type;
  - leader length, converted from feet;
  - end type, `C` → Endcap.
- `configure.py` passes it to the configurator.
- `fixture_steps.js` restores the segment and lights the matching feed pills.

**Limits** (the review banner now says so):
- Feed direction is not encoded in a part number, so it is still chosen (it auto-selects when only
  one direction is offered).
- A jointed (`J`) part number does not record its segment lengths.
- A non-`C` end code asks the dealer to choose the end.

## 8. Profile "Finish" dropdown empty

**Cause.** This is a data problem, not a broken endpoint.
- `get_item_variant_attributes` lists only the values that the item's variants actually use.
- In the 2026-10-04 catalog snapshot, some variants store a blank `attribute_value`:
  - Finish on CH-SH01 and CH-SH02;
  - Lens Color on LNS-SH01;
  - Endcap Color and Type on EC-SH01;
  - Finish on several LED neon templates.
- Those dropdowns therefore had no options.
- 60 of 62 profile templates are fine, so this does not affect every accessory.
- A variant value whose spelling differs from the Item Attribute list (case or spacing) was also
  dropped.

**Changed** (`api/portal.py`):
- Matching against the Item Attribute list ignores case and spacing.
- Values keep the variant's own spelling, because variant matching compares those strings exactly.
- Blank values are skipped.
- A value used by variants but missing from the list is still offered.
- When an attribute has no usable values, the response lists the variants and the modal offers
  them directly ("Options for this item are not fully set up (Finish). Choose the item directly.").
  Otherwise matching on the remaining attributes would silently pick an arbitrary variant.

**Still to do (data).**
- Fill in the blank variant attribute values for the templates above.
- Add an importer check that variant (not template) rows carry a value. `catalog_authoring/schema.py`
  shares the table with template rows, which legitimately have no value, so the field cannot simply
  be made required.

## 9. LED sheet groups vs. supply outputs

**What the code does.**
- `led_sheet_bundle.resolve` sizes each group by the **largest per-output capacity** among the
  eligible drivers.
- The planner then gives each group its own output. It never puts a group on an output smaller
  than the group.
- So a supply sold as "2 × 100 W" should only produce one 180 W group if its driver record says one
  output can carry it. That happens when `max_wattage_per_output` is 200, or
  `independent_outputs_count` is 1.

**Changed.**
- The sheet preview now names the supply and output feeding each group, for example "driver group 2
  (power supply 1, output 2)".
- The summary counts supplies, for example "2 driver groups on 1 power supply".
- The drawing and the supply table can no longer disagree silently.

**Next step.**
1. Note the template, coverage and supply from the reported build.
2. Open that supply's `ilL-Spec-Driver` and check `max_wattage`, `max_wattage_per_output`,
   `outputs_count` and `independent_outputs_count`.
3. If the per-output wattage is the total, correct it. The groups will then split per output, with
   one leader each.
4. If the data is right and it still shows one group, send the build and it will be traced in the
   planner.

## Tests

- `tests/portal_unit` (Python, with Frappe doubles): 1,752 tests pass. There are new tests for:
  - the account endpoint error replies;
  - template rows being skipped on import;
  - part-number segments;
  - per-foot adders;
  - variant attribute values.
- `tests/portal_ui/build_preview.test.cjs`: all pass. It covers the reported 4-piece build, the
  jumpered 4-segment build and sheet feed labels.
- The other `tests/portal_ui` suites need `jsdom`/`jquery`. With them installed, the same tests
  pass and fail before and after these changes; the existing failures are environmental.
- The bench test `api/test_configurator_engine.py` was updated for per-foot adders but not run here.
