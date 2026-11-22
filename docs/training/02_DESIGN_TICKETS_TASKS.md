# Module 02: Design, tickets & tasks

**Audience:** sales, applications engineering, support, owner. **Length:** 90 minutes (split into two sessions: Design, then Tickets).
**Roles used:** ilL Sales Review, ilL Engineering, ilL Applications Engineer, ilL Support, Command Center Editor.

## Purpose

Trainees learn where design work starts (a dealer's project and fixture schedule), how drawing requests and reviews move, how the System Designer and spec submittals fit in, and how Helpdesk tickets are triaged and linked to the right job.

## Where to go

| What | Where |
|---|---|
| Design board | `/command-center#design` |
| One schedule's drill-down | `/command-center#design/<schedule>` |
| Help desk triage | `/command-center#inbox` |
| Projects (desk) | `/app/ill-project` |
| Fixture schedules (desk) | `/app/ill-project-fixture-schedule` |
| Drawing / document requests | `/app/ill-document-request` |
| Drawing reviews (read-only) | `/app/ill-drawing-review` |
| Request types (setup) | `/app/ill-request-type` |
| Staff queues | `/app/ill-portal-operations` |
| Submittal readiness | `/app/submittal-readiness` |
| Helpdesk | `/helpdesk/tickets` |
| Dealer side | `/portal/projects`, `/portal/schedules/<schedule>`, `/portal/drawings`, `/portal/schedules/<schedule>/design` |

---

## Part A: Design

### Lesson 2.1: Projects and fixture schedules, the spine of every job

**Objective:** explain how a project and its fixture schedule carry a job from design to order.

- **Project** (`ILL-PROJ-YYYY-#####`): customer (the dealer company), end client, architect, lighting designer, general contractor, project manager, collaborators. Status ACTIVE / ON_HOLD / COMPLETED / ARCHIVED.
  - Public projects are visible to everyone at the dealer company. **Private** projects only to the owner and active collaborators.
  - External collaborators (designers, GCs) get Website User access, VIEW or EDIT, per project.
- **Fixture schedule** (`ILL-SCHED-YYYY-#####`): the list of lines for a project. It has a version, a lock, and a status.
- **Status path:** DRAFT → READY → QUOTED → ORDER_REQUESTED → ORDERED. Exceptions: ISSUE, CLOSED.

| Status | Who sets it |
|---|---|
| DRAFT ↔ READY | Dealer or staff. READY needs every line fully configured (a dialog lists unconfigured lines) |
| QUOTED | System, when a portal offer is issued (Module 03) |
| ORDER_REQUESTED | System, when the dealer accepts an offer |
| ORDERED | System, on Sales Order submit |
| ISSUE | System, on SO cancel or a deleted order request. Dealer is told to contact sales@ |

- **Versions:** leaving QUOTED automatically makes a new version. The quoted copy is locked and its issued offer is marked superseded. **Create New Version** does the same by hand. A locked version can't be edited or converted.

📸 **SS-02-01** · Dealer portal: project list, then one project page
**URL:** `/portal/projects` and `/portal/projects/<project>` · **Role:** Dealer
**Highlight:** schedules on the project; collaborators link

📸 **SS-02-02** · Dealer portal schedule page with lines
**URL:** `/portal/schedules/<schedule>` · **Role:** Dealer · **State:** READY schedule, 6+ lines across families
**Highlight:** Change Status; Request a quote; Request drawings; Exports menu; Version History

📸 **SS-02-03** · Desk fixture schedule form
**URL:** `/app/ill-project-fixture-schedule/<schedule>` · **Role:** ilL Sales Review
**Highlight:** status, version, lock fields; Actions menu (Convert to Sales Order); Support → Link Helpdesk Tickets; CAD → Import Drawing

📸 **SS-02-04** · "Cannot Set Status to Ready" dialog listing unconfigured lines
**URL:** desk schedule form · **State:** a DRAFT schedule with one unconfigured line

📸 **SS-02-05** · (pair) Create New Version: before (v1 unlocked) and after (v1 locked, v2 DRAFT)
**URL:** desk schedule form

🔌 **DATA-02-01** · A real schedule that has reached ORDERED, with its project, for the end-to-end example used across Modules 02-06
**API:** `GET /api/resource/ilL-Project-Fixture-Schedule?filters=[["status","=","ORDERED"]]&fields=["name","ill_project","customer","version","sales_order","modified"]&order_by=modified desc&limit_page_length=5`
**Use:** pick one with a submitted SO, a delivery note and a tracking number. This is "our job" for every later module. Redact the dealer name.

🔌 **DATA-02-02** · Count of schedules by status (pipeline snapshot)
**API:** `GET /api/resource/ilL-Project-Fixture-Schedule?fields=["status","count(name) as n"]&group_by=status`

---

### Lesson 2.2: Adding and configuring lines

**Objective:** add lines to a schedule the way a dealer does, and the way staff do from the desk.

- **Dealer portal:** Add Fixture Line → category → template card → **Add** (configure later) or **Configure now**. Lines then show **Configure** / **Edit Config**.
- Other ways in: add by part number, start from a saved preset, **Import Lines** (CSV/XLSX), copy/move from another schedule.
- Line families: Linear fixture, LED tape / COB tape / LED neon, LED sheet, extrusion kit, power supply / driver, accessory, other manufacturer.
- Bulk edit, compare two lines, 10-second Undo, "Catalog updated – review" badge.
- **Staff (desk):** the Configure & Add Fixture dialog on Quotation and Sales Order (Module 03, Lesson 3.3) writes the schedule line too.
- A physical change to a line that already has approved drawings creates a **drawing reapproval** task automatically.

📸 **SS-02-06** · Add Fixture Line: category chooser and template cards
**URL:** `/portal/schedules/<schedule>` · **Role:** Dealer

📸 **SS-02-07** · Linear configurator mid-configuration
**URL:** `/portal/configure?category=...` · **Role:** Dealer · **Highlight:** the "Estimate — confirmed on your quote" panel

📸 **SS-02-08** · Tape configurator steps (Environment → CCT → Output → Feed → Lead → Length)
**URL:** `/portal/configure-tape`

📸 **SS-02-09** · Import Lines dialog (CSV/XLSX)
**URL:** portal schedule page

---

### Lesson 2.3: The Command Center Design board

**Objective:** use `#design` to see every schedule in design and act on the stuck ones.

- Stats: active projects, schedules in design, open drawing requests, drawings past SLA.
- Kanban columns: **Drafting** · **Ready for quote** (READY, no quote request yet) · **Drawing in progress** · **Waiting on customer** · **Review** (changes requested, ISSUE, or a drawing delivered with no review yet).
- Cards show project, dealer, architect / lighting designer / GC, version, lock and line count.
- Below: the drawing and document requests table (red age = over 2 business days) and Design-type help desk tickets.
- `#design/<schedule>` drill-down: project card, "Where it is" (drawing requests, quote requests, offers, order requests, SO, tickets), drawing reviews, lines (read-only). Buttons: **+ To-do**, **Details**, **Open in ERPNext**, and "Now on Quotes →" once it has moved on.

📸 **SS-02-10** · Design board, full page
**URL:** `/command-center#design` · **Role:** Editor
**Highlight:** the five columns; drawings past SLA stat; the requests table

📸 **SS-02-11** · Schedule drill-down
**URL:** `/command-center#design/<schedule>` · **Highlight:** "Where it is" chips; + To-do; Open in ERPNext

---

### Lesson 2.4: Drawing and document requests

**Objective:** take a drawing request from submitted to completed inside its SLA.

- Record: `ilL-Document-Request` (`ILL-REQ-YYYY-#####`). Priority Normal / High / Rush.
- **Status:** Draft → Submitted → In Progress ↔ Waiting on Customer → Completed (also Closed, Cancelled).
- **On submit:** SLA deadline set from the request type (default 72 / 48 / 24 hours by priority), auto-assigned (default user, or least-loaded person in the default role), optional Task created, assignee emailed "New Document Request".
- **Working it:** in the desk, use the **Portal conversation** panel: Reply, **Request info** (→ Waiting on Customer), **Resolve** (→ Completed), Reopen. Tick **Staff only** for internal notes.
  - Attachments: PDF, JPEG or PNG, up to 20 MiB, 10 per reply.
- **Publishing a deliverable:** private file, unique revision. Published files can't be changed; publish a new revision. The requester gets "New File Available".
- **On complete:** requester emailed "Your Request … is Complete".
- Staff fields: assigned_to, technical_reviewer, **required_for_manufacturing**, sales order / schedule binding, hide_from_portal.
- **Setup gotcha:** only the "System Design Review" type is seeded. Every other request type must be created at `/app/ill-request-type`, or the portal says "Drawing requests are not available right now."

📸 **SS-02-12** · Dealer: new drawing request form
**URL:** `/portal/drawings` → New · **Role:** Dealer · **Highlight:** type-driven fields; priority "High – Needed within 2 business days"

📸 **SS-02-13** · Desk document request with the Portal conversation panel
**URL:** `/app/ill-document-request/<name>` · **Role:** ilL Engineering
**Highlight:** SLA deadline; assigned_to; required_for_manufacturing; Reply / Request info / Resolve; Staff only toggle

📸 **SS-02-14** · Request type setup form
**URL:** `/app/ill-request-type/<name>` · **Role:** System Manager · **Highlight:** SLA hours per priority; default assignee / role; auto_create_task

📸 **SS-02-15** · Dealer: drawing request detail with status timeline and Download Latest
**URL:** `/portal/drawings/<request>` · **Role:** Dealer

🔌 **DATA-02-03** · Recent drawing requests with SLA outcome
**API:** `GET /api/resource/ilL-Document-Request?filters=[["status","=","Completed"]]&fields=["name","request_type","priority","creation","completed_on","assigned_to"]&order_by=completed_on desc&limit_page_length=20`
**Use:** "average turnaround" slide

---

### Lesson 2.5: Drawing reviews and the manufacturing drawing hold

**Objective:** understand why a work order can be blocked by a drawing, and how to release it.

- The named **technical reviewer** (a dealer-side person) approves or requests changes **in the portal**: **Approve drawing** / **Request changes** (a note is required).
- A review (`DR-#####`) is tied to one revision. One decision per revision; to get another, publish a new revision.
- **Work Order submit is blocked** until every request marked **required for manufacturing** has an APPROVED review of its current revision.
- A pending drawing never blocks **sales order** approval. It only blocks building.
- Moving or waiving a manufacturing drawing requirement needs System Manager.
- Desk review records are read-only for everyone.
- Queue: Portal Operations → "Drawing responses", "Drawing reapproval", "Manufacturing drawing holds" (ilL Operations sees the hold queue).

📸 **SS-02-16** · Dealer reviewer view: Approve drawing / Request changes
**URL:** `/portal/drawings/<request>` · **Role:** Dealer user who is the named reviewer

📸 **SS-02-17** · Work Order submit refused because of a drawing hold (the error message)
**URL:** `/app/work-order/<name>` · **Role:** Manufacturing Manager · **State:** WO linked to an SO with an unapproved required drawing

📸 **SS-02-18** · Portal Operations with drawing queues
**URL:** `/app/ill-portal-operations` · **Highlight:** Drawing responses; Drawing reapproval; Manufacturing drawing holds

---

### Lesson 2.6: System Designer ⚠️

**Objective:** know what the System Designer produces and how its review request reaches applications engineering.

- Routes: `/portal/schedules/<schedule>/design`, `/portal/design`.
- Available when enabled in ilL-System-Designer-Settings, for pilot customers, or for staff with engineering / design review capability.
- Guided steps: spaces, cabinets and distances → runs → power board → checks → riser outputs → **Finish**.
- **Finish** writes power supply, control, wire and accessory lines back onto the schedule (price change shown only with "Can View Pricing") and files a **System Design Review** request, assigned round-robin to Applications Engineers (SLA 16 / 8 / 4 hours).
- Finish is blocked while a power-supply overload, voltage mismatch or tape undervoltage check is open, unless overridden.
- **Reviewer (ilL Applications Engineer):** pinned comments, override a check with a reason, then Approve (request Completed) or Request changes (Waiting on Customer). The riser PDF is published as a deliverable.
- The schedule page shows a review chip: Review required / In review / Approved / Overridden.
- 🚧 Not built yet: Spaces/Runs and Power reworks, auto-plan, review workspace, design share links.
- The "review gate" that blocks ordering DMX or phase-cut designs is **off by default**.

📸 **SS-02-19** · System Designer, runs step
**URL:** `/portal/schedules/<schedule>/design` · **Role:** Dealer (pilot) or ilL Engineering

📸 **SS-02-20** · System Designer Finish step with checks and write-back preview

📸 **SS-02-21** · Reviewer mode with a pinned comment and Approve / Request changes
**Role:** ilL Applications Engineer

📸 **SS-02-22** · Review chip on the schedule page

---

### Lesson 2.7: Spec sheets and submittal packages

**Objective:** produce a submittal package for a schedule and check it before it goes out.

- Schedule exports (portal or desk): PDF / CSV, priced or not, **Spec Submittal** (cover + filled submittals), **Spec Submittal (Full)** (adds spec sheets). Priced exports need "Can View Pricing".
- Packages never fail on a bad line: the line falls back to its spec sheet or is left out, and a **warning goes on the manifest**. Read the warnings before sending.
- `/app/submittal-readiness` shows which products have complete submittal mappings.
- Spec sheet links are stable: `/spec-sheets/<brand>_<template>.pdf` always points to the current file.
- Send with the manual email template "ilL - Quotation - Submittal package ready".

📸 **SS-02-23** · Exports menu on the schedule page
**URL:** `/portal/schedules/<schedule>` · **Highlight:** Spec Submittal; Spec Submittal (Full)

📸 **SS-02-24** · Export job manifest showing a warning
**URL:** `/app/ill-export-job/<name>` · **State:** a packet with at least one fallback line

📸 **SS-02-25** · Submittal readiness page
**URL:** `/app/submittal-readiness`

---

### Lesson 2.8: CAD drawing import ⚠️ (behind a site flag, off by default)

- AutoCAD toolkit commands (ILSETUP, ILCATALOG, ILSTYLE, ILTAPE...) export an `.ilq.json` package. DXF and plotted PDF are also accepted.
- **Import Drawing** on the portal schedule page or desk form (CAD › Import Drawing): preview, then commit to configured lines. Re-importing updates lines in place. A locked or quoted schedule imports into a new version.
- A drawing-imported schedule with an unverified scale **can't request a quote**.
- Staff first; dealers only when piloted.

📸 **SS-02-26** · Import Drawing preview screen (local instance with the flag on)

---

## Part B: Tickets and tasks

### Lesson 2.9: Helpdesk tickets and how they link to jobs

**Objective:** make sure every ticket is linked to the project, schedule, quote, order or invoice it is about.

- Tickets live in **Frappe Helpdesk** (`/helpdesk/tickets`). Replies are written there.
- Each ticket has link fields: project, fixture schedule, quotation, sales order, sales invoice (in the agent sidebar).
- **Automatic linking:** a new ticket whose subject contains a `SAL-QTN-`, `SAL-ORD-` or `ACC-SINV-` number links itself. Upstream links (invoice → order → quote → schedule → project) fill in automatically. Existing links are never overwritten.
- Project, schedule, quotation, SO and invoice forms list their tickets under **Connections**, and have **Support → Link Helpdesk Tickets**.
- Saved replies named "ilL - …" (six of them), e.g. "ilL - Quote copy".
- **Ticket types used by the Command Center:** Quotation, Design, Sales Order, Service, Issue. They are **not created automatically**; set them up at `/app/hd-ticket-type`.
- **Gotcha:** the dealer portal's Support page creates ERPNext **Issue** records, not Helpdesk tickets. Those appear in Portal Operations → "Support responses" (Module 10).

📸 **SS-02-27** · Helpdesk ticket with the ilL link fields in the sidebar
**URL:** `/helpdesk/tickets/<id>` · **Highlight:** quotation / sales order / project links

📸 **SS-02-28** · Sales order form, Connections showing linked tickets; Support → Link Helpdesk Tickets
**URL:** `/app/sales-order/<name>`

📸 **SS-02-29** · Ticket type list
**URL:** `/app/hd-ticket-type`

---

### Lesson 2.10: Inbox triage in the Command Center

**Objective:** clear the Inbox every morning.

- Views: **All tickets** (filter by status, type, owner, linked or not; sort), **Needs a reply** (Open tickets, i.e. the customer wrote last), **Routing** (unassigned or untyped tickets, one-click type and owner).
- **Manage** opens a ticket sheet: reassign; link or unlink a quotation, sales order, project or schedule; change status, priority, type and team.
- Every ticket shows its pipeline stage.
- **Reply in Helpdesk** opens `/helpdesk/tickets/<id>`.
- Reassigning and linking need Command Center Editor. Assignments create a ToDo for the owner, just like the desk.
- Open tickets appear on the Tasks page as source "sales@ (help desk)" and go overdue after 2 days.

**Morning routine:** Routing view to zero → Needs a reply view → link anything unlinked → reply in Helpdesk.

📸 **SS-02-30** · Inbox, Routing view
**URL:** `/command-center#inbox` · **Role:** Editor · **Highlight:** one-click type and owner

📸 **SS-02-31** · Inbox, Needs a reply view

📸 **SS-02-32** · Manage ticket sheet with the "Link quotation" control
**Highlight:** link / unlink; status; priority; Reply in Helpdesk

🔌 **DATA-02-04** · Ticket age distribution for the "why we triage daily" slide
**API:** `GET /api/resource/HD Ticket?filters=[["status","=","Open"]]&fields=["name","ticket_type","opening_date","_assign"]&limit_page_length=100`

---

### Lesson 2.11: Tasks and to-dos for design work

- Design work creates Tasks and ToDos automatically: drawing requests (if the type has auto_create_task), drawing reapproval tasks, assignments.
- Add your own from any record with **+ To-do** (Command Center) or **Assign To** (desk).
- Track them on `#tasks` (Module 01, Lesson 1.7).

📸 **SS-02-33** · Tasks list filtered to design-related items (source ERPNext, a drawing reapproval task visible)

---

## Slide deck beats

1. Project → schedule → lines: the spine of every job (diagram)
2. Schedule statuses and who moves them (table)
3. Versions and locking: why the quoted copy freezes
4. Dealer view: adding and configuring lines
5. The Design board: five columns and what "stuck" looks like
6. Drawing requests: SLA, assignment, conversation, revisions
7. Drawing reviews and the manufacturing hold
8. System Designer and the review request (rolling out)
9. Submittal packages: read the manifest warnings
10. Tickets: link everything; morning Inbox routine

## Check yourself

1. A dealer can't set their schedule to READY. What is the most likely cause, and where do they see it?
2. What happens to an issued quote if the dealer moves the schedule from QUOTED back to DRAFT?
3. A work order won't submit and mentions a drawing. What do you check?
4. A dealer says they opened a support ticket in the portal, but you can't find it in Helpdesk. Why?
5. Where do you set the SLA hours for a new drawing request type?
