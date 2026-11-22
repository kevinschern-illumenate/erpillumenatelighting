# Module 03: Quotes

**Audience:** sales, sales review, order approvers, owner. **Length:** 90-120 minutes.
**Roles used:** ilL Sales Review (prepare, submit), ilL Order Approver, Dealer (portal side), Command Center Editor.

## Purpose

Trainees can create a quote every way the business does it, choose the right tool for the situation, issue it to the dealer, follow it up, and handle revisions, declines and expiry.

## Where to go

| What | Where |
|---|---|
| Quotes stage | `/command-center#quotes` |
| New quotation | `/app/quotation/new` (or Quotes stage quick link "+ New quotation") |
| Quotations list | `/app/quotation` |
| Quote requests (from dealers) | `/app/ill-quote-request` |
| Quote offers (what the dealer received; read-only) | `/app/ill-quote-offer` |
| Staff queues | `/app/ill-portal-operations` → Quote requests, Offers expiring soon, Sales inbox |
| Dealer side | `/portal/quotes`, `/portal/quotes/<offer>`, `/portal/quote-requests/<QR>` |

## Which tool when

| Situation | Tool | Lesson |
|---|---|---|
| A dealer clicked "Request a quote" on their schedule | Quote request → **Prepare Quotation** | 3.2 |
| You're building a quote from scratch for a dealer, by phone or email | Desk Quotation + **Configure & Add Fixture** | 3.3 |
| A schedule already exists and you want its lines on a desk quote | Desk Quotation → **Get Items From → Fixture Schedule** | 3.4 |
| The dealer wants to explore products themselves first | Portal configurators / Product Finder | 3.5 |
| The dealer's client needs a retail-price copy | Print format **ilL Quotation - MSRP** | 3.6 |

> **Important:** only a Quotation prepared from a **quote request** creates a portal offer and marks the schedule QUOTED when submitted. A desk Quotation made any other way does neither; email it to the dealer instead (Lesson 3.7, decision 11).

---

### Lesson 3.1: The Quotes stage in the Command Center

**Objective:** see every quote that needs you and every quote waiting on a dealer.

- Stats: **Quote requests** (our move; red when older than 2 business days), **Waiting on dealer**, **Quotes out** ($), **Expiring in 7 days**.
- Lanes: Requested · Under review · Information needed · Issued · **Dealer responded** (last 30 days: accepted, declined, revision requested). Accepted offers carry a "Continues in Sales orders" chip.
- Each card: **Reassign**, **Details**, **+ To-do**, ↗ (open in desk).
- Quotation tickets board; "Quotes waiting on dealers" table with an "Include drafts" toggle.
- Quote **stage** on each Quotation (refreshed every 15 minutes): Drafting, Waiting on Info, Waiting on Vendor, Sent, Revising, **Follow Up** (after 7 days, set in ilL-Production-Settings), Won, Lost, Expired, Cancelled.

**SS-03-01** · Quotes stage, full page
**URL:** `/command-center#quotes` · **Role:** Editor + Finance
**Highlight:** the four stats; the five lanes; Reassign on a card

**SS-03-02** · "Quotes waiting on dealers" table with Include drafts on
**URL:** `/command-center#quotes`

**SS-03-03** · Quotation list showing the stage pill colours
**URL:** `/app/quotation` · **Highlight:** Follow Up and Expired stages

**DATA-03-01** · Quote pipeline snapshot: count and value by stage
**API:** `GET /api/resource/Quotation?filters=[["docstatus","=",1]]&fields=["ill_stage","count(name) as n","sum(grand_total) as total"]&group_by=ill_stage`
**Use:** opening slide. Check the stage field name with the doctype meta first.

---

### Lesson 3.2: The main path: dealer quote request → issued offer

**Objective:** take a quote request from "Received" to "Quote issued".

**Step 1, dealer requests (portal).** On a DRAFT or READY, unlocked schedule, the dealer clicks **Request a quote**, adds notes, contact instructions, requested timing and up to 10 files.
- Creates **ilL-Quote-Request** `QR-#####`, state REQUESTED ("Received" to the dealer), with a frozen snapshot of the lines.
- Staff are notified (desk bell, optional shared inbox email) and an assignee is set from **ilL-Portal-Routing-Settings** (queue "quotes"), with a due date from its SLA hours.

**Step 2, prepare.** Open `/app/ill-quote-request/<QR>` → **Prepare Quotation** → choose the selling company.
- Builds a **draft Quotation** with the configured items, BOMs and tape lines, linked to the schedule and the request.
- The request moves to UNDER_REVIEW and is assigned to you. Running it again opens the same draft.

**Step 3, review.** Rates, discounts, taxes, exclusions, **Valid Till**, terms, payment schedule.
- Need something from the dealer? **Portal conversation → Request info**. The request goes to INFORMATION_NEEDED ("Needs your reply" for the dealer); their reply moves it back.

**Step 4, submit.** Submitting checks that the customer matches, the request is open, the schedule isn't locked or ordered, Valid Till isn't past, there are no zero-quantity or alternative rows, and product verification is done.
- On submit: **ilL-Quote-Offer** `OFFER-#####` is created (ISSUED), a PDF is rendered, any earlier issued offer is superseded, request → ISSUED, schedule → **QUOTED**, and the dealer is emailed "Quote ready".

**Request states:** DRAFT · REQUESTED (Received) · UNDER_REVIEW · INFORMATION_NEEDED (Needs your reply) · ISSUED (Quote issued) · CLOSED.

**SS-03-04** · Dealer: Request a quote dialog
**URL:** `/portal/schedules/<schedule>` · **Role:** Dealer

**SS-03-05** · Desk quote request with Prepare Quotation button and conversation panel
**URL:** `/app/ill-quote-request/<QR>` · **Role:** ilL Sales Review · **State:** REQUESTED
**Highlight:** Prepare Quotation; state; assigned to; due date

**SS-03-06** · The draft Quotation it creates
**URL:** `/app/quotation/<name>` · **Highlight:** linked fixture schedule and quote request fields; configured item rows; Valid Till

**SS-03-07** · Request info in the Portal conversation, and the dealer's "Needs your reply" view (pair)
**Role:** -a ilL Sales Review, -b Dealer

**SS-03-08** · Submit blocked: example validation message (e.g. Valid Till in the past)

**SS-03-09** · Portal Operations → Quote requests queue, Mine / Unassigned / Overdue
**URL:** `/app/ill-portal-operations`

**SS-03-10** · Routing settings: quotes queue (assignee, fallback role, SLA hours)
**URL:** `/app/ill-portal-routing-settings` · **Role:** System Manager

**DATA-03-02** · A real quote request that went REQUESTED → ISSUED → accepted
**API:** `GET /api/resource/ilL-Quote-Offer?filters=[["state","=","ACCEPTED"]]&fields=["name","quotation","valid_until","modified"]&order_by=modified desc&limit_page_length=5`
**Use:** the worked example; pair with DATA-02-01 if possible

---

### Lesson 3.3: Building a quote in the desk with Configure & Add Fixture

**Objective:** quote a configured product from scratch without a dealer request.

- `/app/quotation/new` → choose the customer → **Configure & Add Fixture** (toolbar or Items grid).
- Steps: **Project & Schedule** → **Line Details** (Fixture Type, Section/Room, qty, notes) → **Configure**.
- Families: linear, LED tape, COB, neon, LED sheet, plus catalog kits, drivers and controllers.
- Writes the schedule line **and** a priced row (MSRP less the dealer's pricing rule). "Add another" loops back to Line Details.
- **Reconfigure Row** changes an existing configured row.
- If the schedule is QUOTED or locked, the dialog offers **Create New Version**.
- **Tools → Set Section / Room** tags rows; print formats group by it.
- **Two-way sync:** while the Quotation is a draft and the schedule is DRAFT/READY and unlocked, lines, qty, Fixture Type, Section/Room and notes stay in step both ways. Rates, discounts and taxes are never synced. Deleting a row's last item removes the schedule line (an orange alert warns you).
- Internal roles only (System Manager, ilL Sales Review, ilL Order Approver).

**SS-03-11** · Configure & Add Fixture: Project & Schedule step
**URL:** `/app/quotation/new` · **Role:** ilL Sales Review

**SS-03-12** · Line Details step

**SS-03-13** · Configure step (linear) with price preview

**SS-03-14** · Quotation items after adding three configured lines, grouped by Section/Room
**Highlight:** Reconfigure Row; Tools → Set Section / Room

**SS-03-15** · Orange "schedule line removed" alert after deleting a row

---

### Lesson 3.4: Get Items From → Fixture Schedule

**Objective:** pull an existing schedule onto a desk Quotation.

- Save the Quotation first, then **Get Items From → Fixture Schedule**.
- Preview shows counts per line type. Options: include accessories / power supplies; "LED Tape / Neon As" a single configured item or raw components.
- One schedule per document (other versions of the same schedule are allowed). Running it again only adds missing lines.
- Lines awaiting product verification are listed as a warning.

**SS-03-16** · Get Items From → Fixture Schedule dialog with preview counts and options
**URL:** `/app/quotation/<draft>`

**SS-03-17** · Verification warning listing unverified lines

---

### Lesson 3.5: Configurators and the Product Finder (dealer self-service)

**Objective:** know what dealers can do on their own before they ask for a quote.

| Tool | URL |
|---|---|
| Configurator (category chooser; `?category=`, `?pn=`, `?preset=`, `mode=wizard`) | `/portal/configure` |
| Tape | `/portal/configure-tape` |
| Neon (multi-segment) | `/portal/configure-neon` |
| LED sheet | `/portal/configure-sheet` |
| Product Finder | `/portal/product-finder` |

- Each shows an estimate: "Estimate — confirmed on your quote". Presets save common builds.
- **Product Finder "Verify with our team" lines** must be verified by staff before a quote is issued and an order placed (the default gate in Product Finder Settings; alternatives "Before order only" and "Warning only"). Queue: Portal Operations → Product verification (due in 2 business days).

**SS-03-18** · Configurator category chooser
**URL:** `/portal/configure` · **Role:** Dealer

**SS-03-19** · Neon multi-segment configurator
**URL:** `/portal/configure-neon`

**SS-03-20** · Product Finder with a "Verify with our team" result
**URL:** `/portal/product-finder`

**SS-03-21** · Portal Operations → Product verification queue

---

### Lesson 3.6: Pricing, tiers and print formats

**Objective:** understand where a quote's prices come from and which print to send.

- **MSRP** = Standard Selling Item Price.
- **Dealer tier** = the customer's **Customer Group**. The highest-priority enabled selling **Pricing Rule** for that group sets the discount (by brand).
- Sales partners (reps) are tracked for commission but **never print** on customer documents.
- **Print formats:**
  - **ilL Quotation**: dealer pricing (List, Disc, Net), savings, payment schedule, ilL Sales Terms, acceptance signature.
  - **ilL Quotation - MSRP**: for the dealer's client. No discounts, freight or tax; ilL Retail Terms.
  - Rows group by Section/Room and Fixture Type; a row's Page Break is honoured.
- Print format edits in the desk are overwritten on deploy; ask the admin to change them in the repo.
- Terms text is a draft pending counsel review.

**SS-03-22** · Customer form showing Customer Group (tier)
**URL:** `/app/customer/<name>`

**SS-03-23** · Pricing Rule for a customer group
**URL:** `/app/pricing-rule/<name>` · **Role:** Sales Manager / System Manager

**SS-03-24** · (pair) Print preview: ilL Quotation vs ilL Quotation - MSRP
**URL:** `/app/quotation/<name>` → Print · **Highlight:** List / Disc / Net columns in -a; none in -b

---

### Lesson 3.7: Sending, following up and expiry

**Objective:** make sure no quote goes quiet.

- **Portal-issued quotes:** the dealer is emailed automatically. Daily reminders go to buyers 3 days and 1 day before **Valid Till**. Portal Operations → "Offers expiring soon" lists those within 3 days.
- **Desk-only quotes:** send from the email composer with the template **"ilL - Quotation - Quote sent"** (attaches the ilL Quotation PDF). Others: "Quote revised", "Quote lost check-in".
- Follow-up, expiring and expired Notifications exist but are **disabled** (decision 2 recommends keeping them off).
- The shared **sales@** inbox: Portal Operations → Sales inbox. Reply, **Relink** to the Quotation, Assign To.
- After 7 days with no answer, the quote's stage becomes **Follow Up**.

**SS-03-25** · Email composer with "ilL - Quotation - Quote sent" selected and PDF attached
**URL:** `/app/quotation/<name>` → New Email

**SS-03-26** · Portal Operations → Offers expiring soon

**SS-03-27** · Sales inbox with Relink
**URL:** `/app/ill-portal-operations` → Sales inbox

---

### Lesson 3.8: Dealer responses: accept, decline, revise

**Objective:** know what each dealer response does and what you do next.

- The dealer opens `/portal/quotes/<offer>`, ticks "I have reviewed this quotation, its exclusions, and its terms", then:
  - **Accept and request order** (requested delivery date, optional PO number): creates a **draft Sales Order** and an **order request** (`ilL-Order-Intake`). Offer ACCEPTED, request CLOSED, schedule ORDER_REQUESTED. **Nothing is submitted or built yet** → Module 04.
  - **Decline** (note required): offer DECLINED, request CLOSED.
  - **Request revision** (note required): offer REVISION_REQUESTED, request back to UNDER_REVIEW. Revise the Quotation (cancel and amend), submit again; the new offer supersedes the old.
- Acceptance is refused if the offer expired, the schedule or customer changed, the Quotation was cancelled, or an order request already exists.
- Only a company **Dealer** (buyer) can respond. Collaborators never see prices or offers.
- **Cancelling a Quotation** cancels its offer, reopens the request (UNDER_REVIEW), and returns the schedule to READY if nothing else quotes it.
- An ACCEPTED offer can't be silently replaced; use the order change workflow (Module 04).

**Offer states:** ISSUED · ACCEPTED · DECLINED · REVISION_REQUESTED · SUPERSEDED · CANCELLED (dealer list also shows "Expired").

**SS-03-28** · Dealer offer page with the acknowledgement box and three buttons
**URL:** `/portal/quotes/<offer>` · **Role:** Dealer

**SS-03-29** · Accept dialog (requested delivery date, PO number)

**SS-03-30** · Quotes stage "Dealer responded" lane with an accepted card and its "Continues in Sales orders" chip
**URL:** `/command-center#quotes`

**SS-03-31** · Dealer quotes list showing Issued, Accepted and Expired
**URL:** `/portal/quotes`

---

## Slide deck beats

1. Five ways a quote starts, and which tool to use (table)
2. The main path: request → prepare → review → submit → offer (diagram)
3. What submitting checks, and what it creates
4. Building from scratch: Configure & Add Fixture
5. Pulling a schedule onto a quote
6. Pricing: MSRP, tier, pricing rule
7. Two print formats and who gets which
8. Follow-up and expiry: nothing goes quiet
9. Dealer responses and what each triggers
10. Worked example: our job's quote (DATA-03-02)

## Check yourself

1. You built a quote in the desk with Configure & Add Fixture and submitted it. Why didn't the dealer get a "Quote ready" email?
2. Where does a dealer's discount come from?
3. The dealer asked for a revision. What do you do in ERPNext?
4. Which print format do you send to the dealer's end client?
5. A dealer accepted a quote. Is anything being built yet? What happens next?
