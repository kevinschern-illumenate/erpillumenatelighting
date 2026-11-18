# Manufacturing difficulty points and Production Board: implementation plan

Date: 2026-11-18. Status: proposed, nothing built yet.

## Goal

Put the warehouse manager's "Schedule Wizard" workbook into the ERP. Each configured build gets a difficulty score from its conductor count, wet rating, jumpers (FMC), loose parts and assembly. Those scores are summed per Sales Order and shown in the Command Center Manufacturing view with the same layout, statuses and capacity math he uses today. The numbers come from live BOMs, Work Orders, Sales Orders and Delivery Notes.

This document covers four things:

- what the workbook actually computes (part 1);
- how BOMs are built today and what's missing (part 2);
- the metric and where it's stored, including the BOM changes (part 3);
- the Production Board in the Command Center and the order to build it (parts 4 and 5).

---

## 1. What the Schedule Wizard computes

The dates in the workbook are from February 2026. Only the formulas and data structure matter here.

### 1.1 Difficulty score: `Warehouse!Q` ("CapFinal")

Each order row has hand-entered counts. The score is a weighted sum (a `LET` formula in Excel):

| Column | Meaning | Weight (Warehouse sheet) | Weight (ESPR sheet) |
|---|---|---|---|
| 2c | runs with 2 conductors (static white) | 1.00 | 1.00 |
| 3c | 3-conductor runs (tunable white) | 1.30 | 1.30 |
| *(4c)* | **No column in the workbook.** RGB runs would need one. | *(proposed 1.40)* | — |
| 5c | 5-conductor runs (RGBW) | 1.50 | 1.50 |
| 6c | 6-conductor runs (RGBTW) | 1.75 | 1.75 |
| Loose | loose / pieces-only items | 0.75 | 0.50 |
| WR | wet-rated adder | 1.75 | 2.00 |
| FMC | jumper / FMC adder | 2.00 | 2.50 |
| Assembly | assembly adder | 2.50 | 4.00 |

```
points = 2c + 1.3·3c + 1.5·5c + 1.75·6c + 0.75·Loose + 1.75·WR + 2·FMC + 2.5·Assembly
```

The ESPR sheet has its own "Capacity Calculator" with heavier weights. ESPR is the expected-release list (hold-for-release / hold-for-confirmation). Its `Days = points / Capacity!D25` gives a quick "how many person-days is this release" estimate. So the weights are **settings, not constants**, and there are at least two weight sets.

The adders are **counts, not flags**. They can be larger than the run count:

- SO 67312: 23 2c runs, WR 92, FMC 69, giving **322 pts**.
- SO 68793: 25 runs, FMC 75 (3 per run), giving **175 pts**.

So WR counts wet-rated *terminations or segments*, not runs, and FMC counts *each jumper*. Part 3 is built on that reading.

### 1.2 Value per point: `Warehouse!S` ("Worth")

```
Com $ = $ × Com %
Worth = ($ − Com $) / points        → net dollars earned per difficulty point
```

Conditional formatting turns `Com %` red when it is above **22%**. The Dashboard goal row also uses 22%. That points to `Com %` being sales commission, where higher is worse, with `$ − Com $` as the net kept. **This needs confirming with him** (see open questions). The board will let us switch the source between commission and gross margin.

Checked against the workbook: 67312 is worth $63.5 per point and 68101 is worth $259.6 per point. Those are exactly the rows a planner would rank by.

### 1.3 Status codes, shared by every sheet

| Code | Meaning (from Dashboard and ESD Sheet labels) |
|---|---|
| 1 | Pend-Prod: released, not started |
| 2 | In-Prod |
| 3 | Pend-Ship: built, waiting to ship |
| 5 | Held / at risk (counted in Reporting "At Risk") |
| 7 | Paint / outside processing (on Pro & WC, 7 = complete) |
| 8–9 | WFP: waiting for parts |

### 1.4 Capacity and burn-down: `Capacity` sheet

| Cell | Formula | Value in file |
|---|---|---|
| D25 Capacity per person | input (points per person per day) | 57.54 |
| D26 Head count | input | 5.5 |
| D27 Prod. capacity per day | `D25 × D26` | 316.49 |
| A29 Whse cap | Σ points, status 1–2 | 1,058.5 ✔ recomputed |
| A31 In-Prod cap | Σ points, status 2 | 1,018.5 ✔ recomputed |
| A27 This-month WFP cap | Σ WFP `Cap.` where This Month = "x" | 731.55 |
| D28 Total workload | `A29 + A27` | 1,790.05 |
| D29 Days to complete | `D28 / D27` | 5.66 |
| D35 Capacity left today | `D27 × (time left until 4:30 pm / 8 h)` | — |
| Row 21 burn-down | for each workday (`WORKDAY` with Holidays): `prev − D27 − OT`. Day 1 uses D35, Mondays add weekend OT | — |
| D30 Date clear | first workday where remaining < one day's capacity | — |
| G25–K28 Overtime | daily and weekend OT head count × hours → `D25 × hours/8` extra points | — |
| Named `CapacityHr` | `D25 / 8.5` (points per person-hour) | 6.77 |
| A48:B53 Crew roster | names with present-today checkboxes | 6 names, 5 checked |
| N31:N38 `Holidays` | holiday list used by every `WORKDAY` / `NETWORKDAYS` | — |

### 1.5 Other sheets the Dashboard reads

| Sheet | What it does | ERP source |
|---|---|---|
| **Warehouse** | Open in-house queue: SO, $, Com %, ESD, Status, run and adder counts, Notes, WFP/BIC flag, Com $, CapFinal, Worth. KPIs: totals by status, due today, due tomorrow (or Monday on a Friday), past due | Sales Order + Work Order + BOM points |
| **Shipped** | MTD shipments: SO, $, ESD, ship date, on time = `ESD ≥ Shipped`, BIC flag, "not warehouse fault", late reason. Weekly on-time % (P/Q/S columns) | Delivery Note (submitted) |
| **WFP** | Waiting-for-parts list: ETA (XLOOKUP to an external purchasing workbook, so a manual link), "This Month?" (x / t = tentative / n = next / r = release), Going-to-miss = `ESD < ETA`, Cap. (points) | Work Order shortages + open PO / Material Request dates |
| **Paint** | Outside paint/finish jobs: date sent, PO#, channel, qty, color | Subcontracting / Purchase Order linked to SO |
| **Pro & WC** | Proforma and Will-Call orders, completed vs not | SO payment terms / shipping method |
| **ESPR / HFS** | Expected-release (Likely Ship) and hold-for-ship lists, with monthly revenue roll-ups | SO on hold + likely-ship date |
| **Inbound(RR)** | New orders per day (run rate) and WFP intake; $0 orders, same-day, next-day and rush (ESD ≤ 3 workdays) counts; 30-day average | Sales Order `transaction_date` |
| **Daily Dollars** | Shipped $ per workday this month vs average and needed per day | Delivery Note |
| **Reporting** | Monthly goal vs shipped MTD, available to ship, run rate, at risk, projected releases; week-over-week deltas | Roll-up of the above + goal settings |
| **Dashboard** | Summary. Pipeline cards (Run Rate · Paint · Pend-Prod · In-Prod · Pend-Ship: $, count, avg Com %); Shipped today / MTD / Available; Goal, Gap, Needed per day = `Gap / RR days left`; on-time %; due tomorrow and this week; next-month WFP | Everything above |
| **ESD Graph / ESD Sheet** | Late / today / next 10 workdays as `FILTER` lists by ESD, counted by status bucket | Sales Order + status |

---

## 2. How BOMs are built today

### 2.1 Flow

1. **Configuring at quote or order time** (`api/configured_product_builder.py:308 save_and_apply`). The engine builds an immutable, content-addressed build:
   - Linear: `linear_build.finish` (`api/linear_build.py:225`) writes `build_snapshot_json`, `component_manifest_json`, `cable_manifest_json` and `config_hash`.
   - Item and BOM: `manufacturing_generator._create_or_get_configured_item` → `_create_or_get_bom` → `build_artifacts.ensure_bom` (`api/build_artifacts.py:121`).
   - Tape/neon: `tape_neon_bom.create_or_get_tape_neon_bom`. LED sheet: `led_sheet_bom` / `led_sheet_bundle`. Groups: `fixture_group_bom.ensure_artifacts`.
   - The Sales Order Item gets `ill_configured_*`, `ill_configured_item`, `ill_bom` (the pinned BOM), `ill_runs_count` and `ill_total_watts`.
2. **Sales Order submit** (`hooks.py` → `manufacturing_generator.on_sales_order_submit`). `manufacturing_order.create_for_line` makes **one draft Work Order per SO line**, with `sales_order`, `sales_order_item`, `bom_no` (pinned) and a traveler in `remarks`. Groups get one WO per member run.

### 2.2 Data that already exists for the metric

| Need | Already in the ERP |
|---|---|
| Runs | `ilL-Child-Configured-Run` rows (`run_index`, `run_len_mm`, `leader_item`) and `ilL-Configured-Fixture.runs_count`. Tape/neon: `segments` + feeds from `tape_neon_build.physical_manifest`. LED sheet: `groups` |
| Conductors | `ilL-Attribute-LED Package.spectrum_type` + `channels` (via `tape_offering.led_package`). `ilL-Attribute-Leader Cable.no_conductors` (via `ilL-Rel-Leader-Cable-Map`, **never read today**). `ilL-Spec-Wire.conductors` |
| Wet | `environment_rating` → `api/environment_codes.py ip_number()`, with `WET_IP = 67`. Neon segments have their own `ip_rating` |
| Jumpers / FMC | `cable_manifest_json` cuts with `role` = leader / additional feed / jumper / end leader (`linear_build.py:126`). Tape/neon component rows with `role` |
| Assembly / loose | `assembly_mode` = ASSEMBLED / SHIP_PIECES (tape/neon also has BULK_REEL). Non-configured SO lines (drivers, accessories) |

### 2.3 Gaps and needed corrections

1. **No difficulty data is stored anywhere.** Not on the BOM, Work Order or SO.
2. **`merge_bom_rows` drops cable roles** (`build_artifacts.py:81`). The BOM shows "12 m of leader cable", not "4 leaders + 6 jumpers". Roles survive only in `cable_manifest_json`. The jumper (FMC) count must come from the manifest, not from BOM rows.
3. **Builds are hashed.** Adding the metric to `build_snapshot_json` or to components would change `config_hash` and fork every Item and BOM. `assert_bom` also requires BOM rows to match the pinned build exactly. **Store points in separate, unhashed fields.**
4. **Leader-cable conductor count is never read.** `configurator_engine.py:2524-2546` takes only `leader_item` from the cable map. The `no_conductors` attribute is the most direct conductor source and should be used.
5. **No BOM operations.** Every BOM has `with_operations: 0`. `OPERATIONS_TEMPLATE` (`manufacturing_generator.py:62`) is defined but never used. This is why the Command Center capacity card says hours can't be calculated.
6. **The legacy WO path doesn't set `sales_order_item`** (`manufacturing_generator.py:1296-1311`), so those WOs can't be tied to an SO line. Fix it so roll-ups per line are reliable.
7. **Latent bug:** `_get_default_jumper_item` (`manufacturing_generator.py:1960`) queries map fields that don't exist (`fixture_template`, `jumper_cable_item`).
8. **No ESD, no production status, no WFP.** ESD has to be read as `ill_confirmed_delivery_date` or `delivery_date`. WO status is stock ERPNext. The only shortage logic is `pricing_utils._compute_stock_for_fixture` / `get_bom_stock_for_items`.

---

## 3. The metric: "Build Points"

### 3.1 Per-unit profile of a pinned build

New pure module: `illumenate_lighting/illumenate_lighting/api/build_points.py`.

```python
def profile(configured_doctype, configured_name) -> dict:
    """Per-unit manufacturing profile of one pinned build (no DB writes)."""
    return {
        "runs_2c": 0, "runs_3c": 0, "runs_4c": 0, "runs_5c": 0, "runs_6c": 0,
        "loose": 0, "wet": 0, "fmc": 0, "assembly": 0,
        "points": 0.0, "basis": "v1", "warnings": [],
    }

def score(counts, weights) -> float: ...   # the CapFinal formula, weights from settings
```

Counting rules, one set per product type. These are the defaults; each needs his confirmation.

| Field | Linear fixture | Tape / COB / Neon | LED sheet | Group | Non-configured line |
|---|---|---|---|---|---|
| `runs_Nc` | 1 per `runs` row, bucketed by conductor count | 1 per feed (segment leader + additional feeds) | 1 per `groups` row | Sum of member profiles | 0 |
| conductor count *N* | `leader_cable.no_conductors` if set; otherwise `led_package.channels + 1` (2C static/DTW, 3C TW, 4C RGB, 5C RGBW, 6C RGBTW). Pixel tape: configurable bucket (default 4C) | same | same | — | — |
| `wet` | Wet when `ip_number(environment_rating) ≥ 67`. Count **segments** (each one is sealed). Matches WR > runs in the workbook | Segments whose `ip_rating ≥ 67` | Groups when wet | Sum | 0 |
| `fmc` | Manifest cuts with role `jumper` | Rows with role `jumper` | `jumper_cables_needed` | Sum | 0 |
| `assembly` | 1 when `assembly_mode = ASSEMBLED` | 1 when ASSEMBLED | 0 | Sum | 0 |
| `loose` | 1 when `SHIP_PIECES` | 1 when `BULK_REEL` / `SHIP_PIECES` | 1 | — | 1 per line that needs picking (drivers, accessories) |

`score()` applies the weights from the settings doctype (3.4). Unknown conductor counts fall back to 2C and add a warning. The board shows those warnings so bad data is visible instead of being scored as easy.

### 3.2 Where it is stored (BOM first, as asked)

Put **per-unit** values on the **BOM**. The BOM is the pinned build shared by every SO that uses it. Then multiply by quantity on the order.

| Doctype | New custom fields (patch `patches/add_build_points_fields.py`) | Notes |
|---|---|---|
| **BOM** | Section "Build Points": `ill_runs_2c`, `ill_runs_3c`, `ill_runs_4c`, `ill_runs_5c`, `ill_runs_6c`, `ill_loose`, `ill_wet`, `ill_fmc`, `ill_assembly` (Int), `ill_build_points` (Float), `ill_points_basis` (Data), `ill_points_warnings` (Small Text) | **`allow_on_submit = 1`**, because BOMs are submitted at creation and the backfill writes to existing ones. Not part of `assert_bom` or the hash |
| **Sales Order Item** | Same counts × `qty`, plus `ill_build_points` | Set in `quote_order_configurator._apply_artifact_to_row` and refreshed in SO `validate` |
| **Sales Order** | Totals of the same fields, plus `ill_build_points`, `ill_points_per_dollar` (or `ill_worth_per_point`) | Header totals, so the board reads one row per SO (cheap `get_list`) |
| **Work Order** | `ill_build_points` (= BOM points × WO qty), `ill_points_done` (= points × produced_qty / qty) | Gives in-process burn-down by produced quantity |

Hooks:

- `build_artifacts.ensure_bom`, and the legacy `_create_or_get_bom`, `tape_neon_bom`, `led_sheet_bom` and `fixture_group_bom`, call `build_points.stamp_bom(bom, doctype, name)` right after insert/submit.
- `hooks.py` doc_events:
  - Sales Order `validate` → `build_points.roll_up_sales_order`. Line = BOM per-unit × qty; non-configured lines = Loose.
  - Work Order `before_insert` / `on_update` → copy points from the BOM.
- `bench execute illumenate_lighting.illumenate_lighting.api.build_points.backfill` stamps every existing BOM linked from an `ill_configured_*` doc, then re-rolls open Sales Orders.

### 3.3 BOM corrections in the same pass

1. Keep the cable **roles** without changing BOM rows: the profile reads `cable_manifest_json`, and the BOM gets `ill_fmc`. Item rows stay as they are, so `assert_bom` still passes.
2. Read `ilL-Attribute-Leader Cable.no_conductors` through the leader-cable map in `build_points`. Optionally also record it in the fixture's `cable_manifest_json` for new builds. That is **not** hashed (check before relying on it).
3. Fix the legacy WO path so it sets `sales_order_item`.
4. Fix or remove `_get_default_jumper_item`.
5. **Optional phase 4:** turn on operations. Use `with_operations = 1` and one "Build" operation with `time_in_mins = points × minutes_per_point`, where minutes per point = `60 / CapacityHr` ≈ 8.9 min. This makes ERPNext capacity planning, Job Cards and workstation load work natively. It changes how BOMs are created, so it is a separate decision.

### 3.4 Settings doctype: `ilL Production Settings` (Single)

| Field | Default (from workbook) |
|---|---|
| `points_per_person_day` | 57.54 |
| `shift_hours` / `shift_end` | 8 / 16:30 (`CapacityHr` divides by 8.5, so keep `paid_hours = 8.5` too) |
| `holiday_list` (Link Holiday List) | the Company default |
| Child table `weights` (profile name, 2c, 3c, 4c, 5c, 6c, loose, wet, fmc, assembly) | **Standard**: 1 / 1.3 / 1.4 / 1.5 / 1.75 / 0.75 / 1.75 / 2 / 2.5. **Release (ESPR)**: 1 / 1.3 / 1.4 / 1.5 / 1.75 / 0.5 / 2 / 2.5 / 4 |
| Child table `crew` (employee or name, `present_today` Check, `fte` Float) | Head count = Σ fte where present, plus `headcount_adjustment` (the workbook uses 5.5 by hand) |
| `ot_daily_headcount`, `ot_daily_hours`, `ot_weekend_headcount`, `ot_weekend_hours` | 0 |
| `margin_basis` Select (Commission / Gross Margin) and `margin_flag_pct` | Commission, 22% |
| Child table `monthly_goals` (month, revenue goal, run-rate goal) | Feb 2,477,000; Mar 3,180,000; Apr 3,319,000 (example) |
| `pixel_conductor_bucket` | 4 |

---

## 4. Production Board in the Command Center

### 4.1 Where it fits

The Command Center is a **Web Page** (`/command-center`). Its JavaScript (`command_center/page/cc.js`) is synced on migrate by `command_center_sync.py`. Data comes from:

- a read-only Server Script `ill_command_center`, which is **not in the repo**;
- the gateway `ss/cc_gateway.py`, which runs under RestrictedPython: no `_` names, closures only, and v15/v16 aggregate fallbacks.

The current Manufacturing view `V.mfg` (`cc.js:233-242`) shows a placeholder capacity ring ("— of 30 hrs") and lists of draft/duplicate WOs.

**Recommendation:** compute the board in a normal whitelisted app module, `api/production_board.py` (`@frappe.whitelist()`). Don't put it in the sandboxed gateway. That gives us full Python (holiday math, shortage checks, `frappe.db` aggregates), pytest coverage, and no RestrictedPython workarounds.

- It checks the "Command Center Viewer" role, the same way `gate()` does.
- Dollar and margin columns also require "Command Center Finance".
- `cc.js` fetches it with the existing `call()` helper.
- Cache: `frappe.cache` with a 60-second TTL, keyed by user's finance role.

### 4.2 Status mapping (workbook code → derived live, nothing typed by hand)

| Code | Rule (first match wins) |
|---|---|
| 5 Held | SO `status = On Hold` **or** any WO `Stopped` |
| 7 Paint | SO has an open subcontract / outside-processing PO (phase 3), or manual override |
| 9 WFP | Any open WO for the SO has a shortage: required − (transferred + projected available) > 0 for any `required_items` row. Uses `get_bom_stock_for_items` / Bin projected qty |
| 1 Pend-Prod | WOs are Draft or Not Started and materials are OK |
| 2 In-Prod | Any WO In Process (or `material_transferred_for_manufacturing > 0`) |
| 3 Pend-Ship | All WOs Completed (`produced_qty ≥ qty`) and SO `per_delivered < 100` |
| (shipped) | Delivery Note submitted, so the order moves to the Shipped table |

Add an optional SO field `ill_production_status_override` (Select) for Paint and Hold until those flows exist in the ERP. **ESD** = `ill_confirmed_delivery_date` or else `delivery_date`. If "ship date" and "delivery date" really differ (transit days), add `ill_estimated_ship_date`.

### 4.3 Layout: same blocks as his workbook, top to bottom

1. **Pipeline cards** (Dashboard row 10–13): Run Rate · Paint · Pend-Prod · In-Prod · Pend-Ship · Total less RR. Each shows $, # orders, avg Com % (red when > flag).
2. **Shipping strip**:
   - Shipped today / MTD / Available to ship ($, Com %, Com $);
   - Goal, Gap, Shipping days left;
   - Needed per day = Gap ÷ days left;
   - Projection after run rate;
   - On-time % this month (warehouse-fault adjusted).
3. **Due panel**: Past due · Due today · Tomorrow/Monday · This week (count and $), using the Warehouse X/Y and Dashboard S/T logic.
4. **Capacity card**, which replaces the "30 hrs" placeholder:
   - Workload (Whse + this-month WFP), Daily capacity, Days to complete, **Date clear**;
   - capacity left today (time-of-day aware);
   - a **burn-down chart** over the next 22 workdays, skipping holidays, with Monday weekend OT. Use the existing `vbars` helper with the capacity line as `target`.
   - The crew roster with present toggles (editors only, writes to settings) drives head count.
5. **Warehouse queue table** (the main table): SO · Customer · $ · Com % · ESD · Status · 2c · 3c · 4c · 5c · 6c · Loose · WR · FMC · Assy · **Points** · **Hrs** (= points ÷ CapacityHr) · **Worth $/pt** · Notes (SO `ill_shipping_instructions` or a new `ill_floor_notes`).
   - Rows are colored like his conditional formatting: ESD past due red, ESD today amber, status 2/3 shading.
   - Sortable by ESD / Worth / Points. Row click opens the SO in the existing drawer.
   - Data-quality warnings are badges.
6. **WFP table**: SO · $ · ESD · short items · **ETA** · Going to miss · Points · This month?
   - ETA = latest `schedule_date` of open PO lines (or Material Request) for the short items. That replaces his XLOOKUP into another workbook.
   - "This month?" = ETA ≤ end of month, so it's derived; a manual "tentative" override is optional.
7. **Shipped (MTD) table**: SO · $ · ESD · Shipped (DN `posting_date`) · On time · Late reason · Not-warehouse-fault, plus weekly on-time % rows.
   - New Delivery Note fields: `ill_late_reason` (Small Text), `ill_not_warehouse_fault` (Check).
8. **Run rate (Inbound)**, phase 3: orders received per workday (SO `transaction_date`), with $0, same-day, next-day and rush counts, a 30-day average, and Daily Dollars bars.
9. **Holds / Releases (ESPR + HFS), Proforma & Will Call, Paint**, phase 3. These need a `likely_ship_date` on held SOs and a subcontract link. Revenue by month uses the same SUMIFS-by-month logic.

### 4.4 Response shape (`production_board.get_board`)

```json
{
  "as_of": "2026-11-18T10:05:00",
  "settings": {"points_per_person_day": 57.54, "headcount": 5.5, "capacity_per_day": 316.5,
               "capacity_hr": 6.77, "shift_end": "16:30", "margin_flag_pct": 0.22},
  "pipeline": {"pend_prod": {"amount": 0, "count": 0, "com_pct": 0}, "in_prod": {}, "pend_ship": {},
               "wfp": {}, "paint": {}, "held": {}},
  "due": {"past_due": {"count": 0, "amount": 0}, "today": {}, "next_day": {}, "this_week": {}},
  "capacity": {"whse_points": 1058.5, "in_prod_points": 1018.5, "wfp_month_points": 731.55,
               "workload": 1790.05, "days_to_complete": 5.66, "date_clear": "2026-11-25",
               "left_today": 13.2, "burndown": [{"date": "2026-11-18", "remaining": 1776.9}]},
  "queue": [{"so": "SO-0001", "customer": "", "amount": 0, "com_pct": 0, "esd": "", "status": 2,
             "runs": {"2c": 23, "3c": 0, "4c": 0, "5c": 0, "6c": 0}, "loose": 0, "wet": 92, "fmc": 69,
             "assembly": 0, "points": 322, "hours": 47.6, "worth": 63.5, "notes": "", "warnings": []}],
  "wfp": [], "shipped": {"mtd": {}, "today": {}, "on_time_pct": 0, "weekly": [], "rows": []},
  "goal": {"month_goal": 0, "gap": 0, "needed_per_day": 0, "days_left": 0}
}
```

The example numbers are his February data, used as a golden test (4.6).

### 4.5 Front-end changes (`cc.js` / `cc.css`)

- Replace `V.mfg` with the board. Follow the `EX` fetch-and-cache pattern (`EX.mount`, 120-second refresh) and the existing `stat` / `card` / `tableCard` / `vbars` / `ring` / `badge` helpers, with no new chart library.
- Keep the current "Active work orders / Needs WO / Duplicate drafts" tables as a collapsed "WO hygiene" card at the bottom.
- Add a "Shipped" sub-tab and a "Releases" sub-tab later, through the existing stepper and `PIPE` routing.
- Update `tests/smoke.js` with a mock `production_board` reply. The existing smoke test loops every view, including `mfg`.

### 4.6 Tests

- `api/test_build_points.py`:
  - per product type (linear single/multi-segment, wet, TW, RGBW, tape with jumpers, LED sheet, group, plain item);
  - `score()` against the workbook rows: 67312 → 322, 68793 → 175, 68221 → 140, 68101 → 190;
  - status 1+2 total = 1,058.5.
- `api/test_production_board.py`:
  - status derivation;
  - burn-down and date clear across a holiday and a Monday;
  - "tomorrow" means Monday on a Friday;
  - on-time and weekly %;
  - finance columns hidden without the role.
- Backfill run in a dry-run mode that reports counts and warnings before writing.

---

## 5. Order of work

| Phase | Scope | Rough size |
|---|---|---|
| **1 – Data** | `build_points.py` (profile + score); settings doctype; custom fields patch (BOM / SO / SOI / WO / DN); stamping hooks in the BOM builders; SO and WO roll-up hooks; legacy WO `sales_order_item` fix; jumper-item bug fix; backfill command; tests | 3–4 days |
| **2 – Board MVP** | `production_board.py`: status, queue, pipeline cards, due panel, capacity and burn-down, WFP with ETA, shipped MTD and on-time. `cc.js` Manufacturing view rebuilt; smoke test | 3–4 days |
| **3 – Rest of the workbook** | Run rate / inbound, Daily Dollars, monthly goals and Reporting deltas, Holds/Releases (likely-ship date), Proforma & Will Call, Paint (subcontract PO link) | 3–5 days |
| **4 – Optional** | BOM operations from points (native ERPNext capacity and Job Cards); calibrate weights against actual WO start-to-complete times | 2–3 days + calibration |

Phase 1 is useful on its own: every SO will show its point total and per-conductor breakdown on the form even before the board exists.

## 6. Questions for the warehouse manager

1. **Com %:** is it the rep commission (higher is worse, net = $ − Com $) or the margin? The red-above-22% format suggests commission.
2. **WR and FMC counts:** per wet *segment/termination* and per *jumper*? The counts are larger than the run count in his data.
3. **4C (RGB) weight:** the workbook has no 4C column. Is 1.4 right?
4. **Assembly vs Loose:** do our ASSEMBLED linear fixtures count as "Assembly" (+2.5 each), and SHIP_PIECES / bulk reels as "Loose"? Should drivers and accessories lines count as Loose?
5. **Which weight set** for the main board: Warehouse (Loose 0.75 / WR 1.75 / FMC 2 / Assy 2.5) or ESPR (0.5 / 2 / 2.5 / 4)? Plan: Warehouse for the queue, ESPR for release estimates.
6. **57.54 points per person per day:** carry it over, or re-baseline after a few weeks of ERP data (phase 4)?
7. **ESD:** ship date or customer delivery date? Is a separate estimated-ship-date field needed?
