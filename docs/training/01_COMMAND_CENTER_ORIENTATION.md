# Module 01: Command Center orientation

**Audience:** everyone. **Length:** 60-75 minutes. **Prerequisite:** an ERPNext login with at least the Command Center Viewer role.

## Purpose

By the end, a new team member can open the Command Center, find their stage of the pipeline, find their own to-dos, open any record in the side sheet, and know when to leave the Command Center for the ERPNext desk, the dealer portal or Helpdesk.

## Where to go

| What | URL |
|---|---|
| Command Center | `/command-center` |
| ERPNext desk home (ilLumenate Lighting workspace) | `/app/illumenate-lighting` |
| Portal Operations (staff queues for dealer requests) | `/app/ill-portal-operations` |
| Helpdesk (agent view) | `/helpdesk/tickets` |
| Dealer portal (what dealers see) | `/portal` |
| HR self-service | `/hrms` |
| Kevin's Desk (owner only) | `/kd/<private slug>` |

---

## Lesson 1.1: The four places you work, and when to use each

**Objective:** know which screen to use for each kind of task.

- **Command Center** (`/command-center`): see the whole pipeline, triage, make quick edits, create drafts. It never submits, cancels or deletes ERPNext documents.
- **ERPNext desk** (`/app/...`): create, submit, cancel and amend documents. Run reports. Change settings.
- **Dealer portal** (`/portal/...`): the dealer's side. Staff use it to see what the dealer sees, and to test.
- **Helpdesk** (`/helpdesk/tickets`): write replies to customer tickets.
- **Rule of thumb:** look and decide in the Command Center; commit in the desk.

📸 **SS-01-01** · Command Center landing page, full width
**URL:** `/command-center` · **Role:** Command Center Editor + Finance · **State:** default landing (Sales pipeline › Overview)
**Highlight:** the top tab bar; the pipeline stepper; the Refresh button

📸 **SS-01-02** · ERPNext desk, ilLumenate Lighting workspace
**URL:** `/app/illumenate-lighting` · **Role:** System Manager
**Highlight:** "Needs Attention" number cards; "Start Here" shortcuts; "New Product Setup Guide" cards

📸 **SS-01-03** · Dealer portal home as a dealer
**URL:** `/portal` · **Role:** Dealer (sample dealer user)
**Highlight:** the main navigation (Projects, Quotes, Orders, Drawings, Support)

📸 **SS-01-04** · Helpdesk ticket list, agent view
**URL:** `/helpdesk/tickets` · **Role:** support agent

---

## Lesson 1.2: The top tabs

**Objective:** know what each top tab is for.

| Tab | Route | What it is for |
|---|---|---|
| Sales pipeline | `#pipeline` | The 8 business stages (Lesson 1.3) |
| Executive | `#exec` | KPIs, pipeline value, break-even, "Decisions this week" |
| Inbox | `#inbox` | Helpdesk triage: needs a reply, routing, linking |
| Finance | `#finance` | Invoiced vs break-even, receivables, aging (Module 09) |
| Projects & tasks | `#work`, `#tasks` | Company projects, every to-do and task in one list |
| Review | `#review` | The Tuesday walk-through, one page per project |
| Agenda | `#agenda` | The weekly meeting agenda (replaces the Google Doc) |
| Workbench | `#wb` | Browse and edit any record type |
| Catalog | `#catalog` | Catalog Builder, embedded (Catalog Publisher only, 🔒) |
| Recommendations | `#rec` | "This week" and "Recommendations" notes |

- A coloured dot on a tab means it needs attention (red bad, amber warning). The number is the count of open items.
- The page remembers the last tab you used, per browser.

📸 **SS-01-05** · Close-up of the top tab bar with dots and counts
**URL:** `/command-center` · **Role:** Editor + Finance · **State:** at least one overdue task and open tickets so counts show
**Highlight:** an Inbox count, a coloured dot, the Catalog tab present

📸 **SS-01-06** · (pair) Top tab bar as Viewer-only vs as Catalog Publisher
**Role:** -a Viewer, -b Catalog Publisher · **Highlight:** the Catalog tab appears only in -b

---

## Lesson 1.3: The sales pipeline stepper

**Objective:** follow one job through the eight stages and know who owns each.

Overview → Design → Quotes → Sales orders → Purchasing → Manufacturing → Shipping → Service

| Stage | Route | Owner (typical) | Module |
|---|---|---|---|
| Overview | `#pipeline` | Owner | 01 |
| Design | `#design` | Sales / applications engineering | 02 |
| Quotes | `#quotes` | Sales | 03 |
| Sales orders | `#orders` | Sales review / order approver | 04 |
| Purchasing | `#purch` | Buyer | 07, 08 |
| Manufacturing | `#mfg` | Production lead | 05 |
| Shipping | `#ship` | Shipping lead | 06 |
| Service | `#service` | Support | 10 |

- Each fixture schedule sits in exactly one stage: the furthest one it has reached. Earlier steps show as chips.
- The stepper mirrors the dealer portal's own steps, so staff and dealers talk about the same stages.
- Each stage has **quick links** to the ERPNext lists behind it.

📸 **SS-01-07** · Pipeline stepper with counts on each stage
**URL:** `/command-center#pipeline` · **Role:** Editor + Finance
**Highlight:** the 8 stages; the count on each

📸 **SS-01-08** · Overview stage body
**URL:** `/command-center#pipeline` · **Highlight:** SPIF candidates panel; stage lanes

📸 **SS-01-09** · Quick links strip on any stage (use Purchasing; it has the most)
**URL:** `/command-center#purch` · **Highlight:** the quick-link buttons

---

## Lesson 1.4: Opening a record: the side sheet

**Objective:** open, read and edit a record without leaving the Command Center.

- Click any document link to open the **Workbench side sheet**. Ctrl/⌘/Shift-click opens the desk instead.
- The sheet shows details, child tables (read-only, first 25 rows), editable fields, the activity feed, and buttons: **+ To-do**, **+ Add to agenda**, **Open in ERPNext**.
- **Saving** needs Command Center Editor and leaves a "Command Center:" comment on the record's timeline, so everyone can see who changed what.
- **Submitted documents** are read-only except a short list of fields that ERPNext allows after submit:
  - Sales Order: estimated ship date, stage override, hold reason, likely ship date, proforma / will call, floor notes
  - Work Order: planned start, expected delivery date
  - Delivery Note: carrier, tracking number, "late, not warehouse fault", why late
  - Purchase Order: vendor status, sent / confirmed dates, ack #, lead time, ETA, promised ship date, freight mode, notes
- Anything else on a submitted document: amend it in the desk.

📸 **SS-01-10** · Side sheet open on a submitted Sales Order
**URL:** `/command-center#orders` then click an SO · **Role:** Editor
**Highlight:** the editable fields (estimated ship date, hold reason); the read-only fields greyed; + To-do, + Add to agenda, Open in ERPNext

📸 **SS-01-11** · The "Command Center:" comment on the record's desk timeline after a save
**URL:** `/app/sales-order/<name>` · **Highlight:** the timeline comment

---

## Lesson 1.5: Roles: what you can see and do

**Objective:** understand why two people see different things on the same page.

| Role | Unlocks |
|---|---|
| Command Center Viewer | Read everything the gateway shows (still limited by your ERPNext permissions) |
| Command Center Editor | Save edits, create drafts, reassign, agenda changes |
| Command Center Finance | Dollar figures on Executive, Manufacturing and Purchasing |
| ilL Catalog Publisher | Catalog tab |
| Standard ERPNext roles (Purchase, Stock, Accounts, Manufacturing...) | Purchasing, Manufacturing and Shipping boards, and the desk documents behind them |

- **Known gap:** the older Finance tab and finance figures on the Sales pipeline page come from an older feed that shows them to every Viewer. Tell trainees not to share screenshots of those pages outside the company.
- Roles are never assigned automatically. Ask the systems administrator.

📸 **SS-01-12** · (pair) Executive tab as Viewer vs as Finance
**URL:** `/command-center#exec` · **Role:** -a Viewer, -b Editor + Finance
**Highlight:** locked finance tiles in -a; dollar figures in -b

---

## Lesson 1.6: Executive tab and "Decisions this week"

**Objective:** use the Executive tab as the daily start page for leads.

- KPI row: new dealers (out of 8), quotes out, open sales orders, invoiced and receivables (Finance only), tickets waiting over 2 days.
- Pipeline value by stage, break-even ring.
- **Decisions this week** cards: late orders, late POs, late material requests, expiring quotes, stale tickets, overdue tasks, draft work orders, overdue invoices, drawings past SLA, quote and order requests waiting on us, pending account requests. Each opens the Workbench with the status pre-selected.
- Ticket age, the "This week" note, recent changes (the activity feed). Print button.
- Refreshes every 2 minutes.

📸 **SS-01-13** · Executive tab, full page
**URL:** `/command-center#exec` · **Role:** Editor + Finance
**Highlight:** KPI row; Decisions this week cards; activity feed

📸 **SS-01-14** · (pair) Click a Decisions card → Workbench list filtered to that status
**Highlight:** the pre-selected status filter in -b

🔌 **DATA-01-01** · Real counts for a worked example of "Decisions this week"
**API:** `GET /api/resource/Sales Order?filters=[["docstatus","=",1],["status","in",["To Deliver","To Deliver and Bill"]],["delivery_date","<","<today>"]]&fields=["count(name) as n"]`
**Use:** "This morning we had N late orders" talking point

---

## Lesson 1.7: Projects & tasks: your to-do list

**Objective:** find everything assigned to you in one place and close it out.

- `#work` lists company projects. Click one for its board and timeline.
- `#tasks` is the master list: ERPNext ToDos, project Tasks and open Helpdesk tickets together.
- **Source filter:** ERPNext/project, sales@ (help desk), ad hoc, meeting, kevins@ (email-derived; hidden in meeting mode).
- Filters: person, **My items**. Tick ✓ **Done** to close.
- **Saved views:** name and reuse a filter set. Stored in your browser only; they don't follow you to another computer.
- Tags in to-do descriptions tell you where a to-do came from: `[ad-hoc]`, `[meeting]`, `[review]`, `[cleanup]`, `[email]`.

📸 **SS-01-15** · Tasks list filtered to My items
**URL:** `/command-center#tasks` · **Role:** Editor
**Highlight:** source filter; My items; ✓ Done; Save view

📸 **SS-01-16** · Saving a view (the name prompt) and the saved view chip
**URL:** `/command-center#tasks`

📸 **SS-01-17** · Projects list and one project board
**URL:** `/command-center#work` then a project

---

## Lesson 1.8: Review (Tuesday walk-through) and Agenda (weekly meeting)

**Objective:** run the weekly review and meeting in the Command Center.

**Review (`#review`)**
- Overview of every active project, then one page per project: overdue, due this week, no owner, blocked, team load, recent changes, notes.
- Arrow keys move between projects. Tasks open the edit sheet. **Print / PDF** prints one project per page.

**Agenda (`#agenda`)**
- One agenda per meeting, stored in ERPNext (`ilL-Meeting-Agenda`). Everyone sees the same one; it re-reads every 30 seconds.
- Add items as free text or with **+ Add from ERPNext**: the *Suggested* tab (overdue to-dos and tasks, at-risk sales orders, quotes expiring this week, tickets waiting over 2 days) or *Search all records*.
- Any Workbench sheet has **+ Add to agenda** (adds to the next open meeting).
- In the meeting: tick **Discussed**, type the **outcome**, reorder with ↑ ↓. A discussed linked item gets a timeline comment on its record.
- **+ To-do** turns an outcome into ToDos, one per owner, due a week out by default, tagged `[meeting]`.
- **+ New meeting** defaults to a week after the last and can carry open items over.
- **Copy as text** for email/chat; **Print / PDF**.

📸 **SS-01-18** · Review overview, then one project page
**URL:** `/command-center#review` · **Highlight:** overdue / no owner / blocked sections

📸 **SS-01-19** · Agenda during a meeting: items with Discussed ticks and outcomes
**URL:** `/command-center#agenda` · **State:** an agenda with 5+ items, 2 linked to records
**Highlight:** live status on a linked item; Discussed; outcome; + To-do

📸 **SS-01-20** · "+ Add from ERPNext" dialog, Suggested tab
**URL:** `/command-center#agenda`

📸 **SS-01-21** · "+ New meeting" with carry-over option

---

## Lesson 1.9: Workbench: browse any record

**Objective:** find, filter and edit any record type from one place.

- Two areas: **Pipeline** (`#wb/~pipeline`, one card per stage) and **ilLumenate** (`#wb/~ill`, every app doctype grouped like the desk workspace).
- Per list: browse, search, sort, status mix, saved views, side sheet.
- **+ New** creates **drafts only**. Product templates, specs, maps, submittal mappings and Items are created in the Catalog Builder instead (+ New opens the Catalog tab).
- Generated and audit records (configured products, receipts, logs) are read-only.
- Masters with an Active checkbox get one-click Activate / Deactivate.

📸 **SS-01-22** · Workbench Pipeline area
**URL:** `/command-center#wb/~pipeline`

📸 **SS-01-23** · Workbench ilLumenate area with the filter box in use
**URL:** `/command-center#wb/~ill` · **Highlight:** group cards; filter box; Settings card

📸 **SS-01-24** · A Workbench list with status mix and a saved view
**URL:** `/command-center#wb/...` (Tasks or Quotation)

---

## Lesson 1.10: Recommendations and Kevin's Desk

- **Recommendations (`#rec`):** two editable notes, "Command Center – This week" and "Command Center – Recommendations". Leads write what the team must decide and what the data suggests, each with an owner and a reason.
- **Kevin's Desk** (`/kd/<slug>`, 🔒 owner only; everyone else gets a 404): Kevin's personal cockpit. NOW bar (current time block and "hat"), Decisions, a priority pipeline (late SOs/POs, quotes open over 3 days, SOs to deliver by Sunday, tickets waiting on us), My ToDos, and one ranked list that mixes ERPNext items, ToDos and Gmail threads (metadata only). Mention it so the team knows why Kevin's to-dos carry `[email]` tags; don't train on it.

📸 **SS-01-25** · Recommendations tab with both notes filled
**URL:** `/command-center#rec`

---

## Slide deck beats

1. Title: "The Command Center: where the whole business lives"
2. Four places you work (Command Center, desk, portal, Helpdesk) and the rule of thumb
3. The top tabs at a glance (table)
4. The 8-stage pipeline with owners
5. One job's journey across the stepper (use a real schedule from DATA-02-01)
6. The side sheet: open, edit, comment trail
7. Roles: why your screen looks different from your colleague's
8. Executive and Decisions this week: the daily start page
9. Your to-dos: Tasks, sources, saved views
10. The weekly rhythm: Tuesday Review → Agenda → meeting to-dos

## Check yourself

1. You need to change the ship date on a submitted sales order. Where can you do it, and what record of the change is left?
2. Where would you find every to-do assigned to you, including ones from the last meeting?
3. A colleague sees dollar figures on the Purchasing board and you don't. Why?
4. What does the Command Center never do to an ERPNext document?
5. Which tab do you use to add a late PO to Tuesday's meeting?
