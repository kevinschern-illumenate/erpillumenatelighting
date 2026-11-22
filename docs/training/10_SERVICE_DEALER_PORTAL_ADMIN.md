# Module 10: Service & dealer portal administration

**Audience:** support, sales, accounts, systems administrator. **Length:** 75 minutes.
**Roles used:** ilL Support, ilL Sales Review, System Manager, Dealer (portal side).

## Purpose

Trainees can work the Portal Operations queues, onboard a new dealer, process account requests, handle portal support issues and after-sale service, and understand what dealers can and can't see.

## Where to go

| What | Where |
|---|---|
| Service stage | `/command-center#service` |
| Portal Operations (all staff queues) | `/app/ill-portal-operations` |
| Account requests | `/app/ill-account-request` |
| Portal support issues | `/app/issue` |
| Helpdesk / knowledge base | `/helpdesk/tickets`, `/helpdesk/kb` |
| Customers and groups (tiers) | `/app/customer`, `/app/customer-group` |
| Public dealer application | the dealer-access page on the website |
| Dealer side | `/portal`, `/portal/support`, `/portal/account/notifications` |

---

### Lesson 10.1: Portal Operations: the staff queue hub

**Objective:** know which queues are yours and work them daily.

| Queue | Capability (roles) |
|---|---|
| Quote requests, Offers expiring, Order review, Order changes, Product verification | sales (ilL Sales Review / Order Approver) |
| Drawing responses, Drawing reapproval, Incomplete exports | engineering (ilL Engineering) |
| Support responses | support (ilL Support) |
| Account review, New customers to set up, Bills not in QuickBooks | accounts |
| Publication failures, Email failures | integration |
| Manufacturing drawing holds, Materials to order | operations (ilL Operations) |
| Sales inbox | inbox |

- Views: **Mine**, **Unassigned**, **Overdue**. A daily digest emails overdue items.
- "Unavailable" means you lack permission, not zero items.
- The workspace "Needs Attention" cards show the same signals.

**SS-10-01** · Portal Operations as ilL Sales Review
**URL:** `/app/ill-portal-operations` · **Highlight:** queue counts; Mine / Unassigned / Overdue
**SS-10-02** · Same page as ilL Support (different queues; "Unavailable" on others)

---

### Lesson 10.2: The Service stage

- `#service` is the last pipeline stage: "Service after Shipping". Starts with the **Customer requests** lane (dealer applications and address, contact, profile and company changes).
- Quick links: Help desk, Account requests, Knowledge base.

**SS-10-03** · Service stage
**URL:** `/command-center#service`

---

### Lesson 10.3: Onboarding a new dealer

**Objective:** take a dealer from application to first login.

1. **Application** arrives (public dealer-access page or a logged-in request) as an **ilL-Account-Request**, type Dealer application, state Pending.
2. **Set up the Customer** (if new): Customer Group (tier), default payment terms template, addresses. Portal Operations → "New customers to set up" lists won deals without payment terms.
3. **Decide:** Approve (choose the approved Customer; a note is required), Reject, or Request information.
   - Approving links the Contact and adds the **Dealer** role.
   - **Guest applications** (no logged-in user) are approved by **inviting** the applicant to the Customer. Invitations expire after 7 days.
4. **Manual setup when needed:** create the User, add the Dealer role, create a Contact, link it to the Customer.
5. Optional: tick **Can View Pricing** for buyers who should see prices and priced exports.
6. Welcome the dealer; check their first login lands on `/portal`.

**SS-10-04** · Public dealer application form (local instance)
**SS-10-05** · Account request (Dealer application) with Approve / Reject / Request information
**URL:** `/app/ill-account-request/<name>` · **Role:** ilL Sales Review
**SS-10-06** · Approve dialog: choose approved Customer + note
**SS-10-07** · Customer form: Customer Group, payment terms, linked contacts
**SS-10-08** · Invitation flow for a guest application

---

### Lesson 10.4: Other account requests

| Type | What happens on approval |
|---|---|
| Company linkage | Links the user's Contact to the Customer, adds Dealer role |
| Address change / Contact change | Applied automatically (with conflict checks) |
| Profile change | Apply by hand in the native record, then mark **Resolved** |
| Account closure | Disables the User |

- States: Pending, Information needed, Approved, Rejected, Resolved. Every decision needs a note. Use **staff_note** for internal remarks.

**SS-10-09** · Account request list filtered by type and state

---

### Lesson 10.5: Portal support issues and after-sale service

- The portal's **Support** page (`/portal/support`) creates ERPNext **Issue** records (linked to project and order), **not** Helpdesk tickets. Work them in Portal Operations → **Support responses**.
- Email tickets to sales@ land in **Helpdesk** (Module 02, Lessons 2.9-2.10).
- Mark a reply **Staff only** to keep it internal. Attachments: PDF, JPEG, PNG; 20 MiB; 10 per reply.
- Service after shipping: check the order's shipments and tracking (Module 06, Lesson 6.7), send "Delivery check-in" / "Return received" templates, raise a return delivery note for returns.
- (Planned) Knowledge base content and Helpdesk ticket types are configured in Helpdesk itself, not in the app; agree a list before rollout.

**SS-10-10** · Dealer: portal support form
**URL:** `/portal/support` · **Role:** Dealer
**SS-10-11** · The resulting Issue in Portal Operations → Support responses
**SS-10-12** · Helpdesk knowledge base
**URL:** `/helpdesk/kb`

---

### Lesson 10.6: What dealers can and can't see

- **Dealer** role: no desk access, home page `/portal`. Can create, read and print their own company's sales orders; read their own Customer, Contacts, Addresses and Items.
- **Collaborators** (designers, GCs): Website User, VIEW or EDIT per project. Never see prices or offers.
- **Can View Pricing** controls priced exports and price changes in the System Designer.
- Dealers manage email preferences at `/portal/account/notifications` (quotes, shipping…).
- **Role audits** (admin): `portal.role_audit.report` (capabilities only a System Manager covers), `.dealers` (unresolved company links, desk-access risk), `.hr`.

**SS-10-13** · (pair) A project as the dealer buyer vs as a VIEW collaborator (no prices, no quotes)
**SS-10-14** · Dealer notification settings page

---

### Lesson 10.7: Shared sales inbox and CRM (brief)

- sales@ is a shared Email Account with an assignment rule; filed mail is relinked to its document from Portal Operations → Sales inbox.
- Website forms create **Frappe CRM Leads** (per brand). A Deal marked **Won** creates the ERPNext Customer.

**SS-10-15** · CRM lead from a Webflow form
**URL:** `/crm/leads`

---

## Slide deck beats

1. Portal Operations: one hub, many queues
2. Which queues are yours (by role)
3. Onboarding a dealer, step by step
4. Other account requests
5. Portal support issues vs Helpdesk tickets
6. What dealers and collaborators can see
7. From website lead to customer

## Check yourself

1. A guest applied for dealer access. How do you give them a login?
2. A dealer changed their shipping address in the portal. What do you need to do?
3. Where do portal support requests appear?
4. A lighting designer on a project asks for prices. Can they see them?
