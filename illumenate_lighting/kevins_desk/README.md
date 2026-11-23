# Kevin's Desk

A private daily operating page for Kevin at `/kd/<slug>`, built on the Command Center (its styles, its gateway, its links). Not a separate app.

## Access

- **Only the desk owner** (ilL-Desk-Settings → Desk Owner, an enabled System User) can open the page or call its endpoints. Everyone else, a guest included, gets **404**: the page raises the website 404, the endpoints raise `DoesNotExistError`. Nobody is offered a login prompt.
- **The slug** is random (`secrets.token_urlsafe(24)`), generated on the site by the `seed_desk_settings` patch, and compared in constant time. It is not in the repo. Clear it in ilL-Desk-Settings and save to issue a new link. The owner check is the real gate; the slug only keeps the URL out of reach.
- **Only the current owner** (or Administrator) can change the owner or turn the page off.
- **Endpoints** are `allow_guest` so a guest gets our 404, not Frappe's "not whitelisted" 403. `access.require_owner()` is the first statement of each; a unit test enforces it.
- **Not indexed:** `noindex` meta, `sitemap = 0`, `no_cache = 1`. CSS and JS are inlined into the gated response (nothing under `/assets`).
- **Workbench:** ilL-Desk-Settings is in the gateway's `EXCLUDED`, so the Workbench never lists it.

## Files

| File | What |
|---|---|
| `templates/pages/kevins_desk.{py,html}` | The page: gate, boot data, inlines `command_center/page/cc.css` + `page/kd.css` + `page/kd.js` |
| `kevins_desk/access.py` | Owner and slug checks |
| `kevins_desk/schedule.py` | Daily blocks, day themes, hats (Pacific). The one place to change a block |
| `kevins_desk/cc.py` | Calls the Command Center gateway (`ill_cc_gateway`) in process, as the current user |
| `kevins_desk/pipeline.py` | Phase 2 widgets (via the gateway) and the owner's ToDos (direct) |
| `kevins_desk/api.py` | `today` (pipeline + ToDos + mailboxes + the ranked list), `signals`, `connect_mailbox` (POST), `mark_done` (POST). Cached per user (pipeline 5 min, mail 10 min); `refresh=1` rebuilds |
| `kevins_desk/done.py` | The Done button: closes a ToDo, or records a Gmail thread as done (`ilL-Desk-Done`) |
| `kevins_desk/gmail.py` | Minimal Gmail client: read thread metadata, list/create labels, add/remove only @Action/@Waiting/@Quote. No send, trash, delete or archive |
| `kevins_desk/mail.py` | Reads each connected mailbox, works out thread state, keeps the labels, turns threads into items |
| `kevins_desk/mailboxes.py` | Mailbox list, connection state, and the Google connect flow (one Connected App per mailbox) |
| `kevins_desk/ranking.py` | Topic detection, priority-stack placement, the merged ranked list grouped by hat (pure) |
| `kevins_desk/team.py` | Jay, Charlotte, Ryan, Regina: who they are and what they own |
| `kevins_desk/tasks.py` | `warm`: rebuilds the caches as the owner every 10 min, 6:00-17:59 weekdays |
| `doctype/ill_desk_settings` | Enabled, Desk Owner, Link Slug, Google App, Mailboxes (System Manager only; owner-locked) |
| `doctype/ill_desk_done` | Gmail threads marked done: mailbox, thread, and its last message at the time (System Manager read/delete; not in the Command Center) |

## What the page shows

- **NOW bar:** current block, hat, time left, next block. Always on Pacific time.
- **Decisions:** the Command Center's "Decisions this week" counts (gateway `overview`), each linking into the Workbench.
- **Pipeline, in priority-stack order:**
  1. Sales orders past their delivery date, and purchase orders past their ETA (`ill_eta`, else Required By)
  2. Quotations still Open more than 3 days after their date
  3. Sales orders to deliver by Sunday
  4. Help desk tickets waiting on us (HD Ticket status Open)

  Every row links to its record. "All in the Command Center" opens the Workbench list.
- **My ToDos:** open ToDos allocated to the owner. Overdue and due today come first; upcoming and undated ones are folded. Each shows its tags, the linked record and the Gmail thread when the description has one.

Every item uses one shape (`id, dt, name, title, party, date, amount, status, flag, url, hat, stack`).

- **One list** (default view): every ERPNext item, ToDo and Gmail thread in a single list. Items are ranked by the priority stack: within a level, things Kevin owes come before threads he's waiting on, then late items, then items due today, then the oldest. They're grouped by hat, and the hat with the most urgent item comes first. Each item links to its record or thread. The Pipeline tab keeps the Phase 2 widgets.
- **Done** (on every ToDo and Gmail row, in the One list and My ToDos): the row strikes through with Undo for 5 seconds, then:
  - a **ToDo** is closed (status Closed), the same as closing it in ERPNext;
  - a **Gmail thread** is hidden while its last message is still the one Kevin saw, and loses @Action/@Waiting. A new message from either side brings it back if it's owed again. Gmail itself isn't archived or marked read. To bring a thread back sooner, delete its `ilL-Desk-Done` record. Records are pruned after 60 days.

  ERPNext rows (orders, quotes, tickets) have no Done: they leave the list when the record itself changes.

## Gmail (Phase 3)

**Connecting a mailbox (once each).** ilL-Desk-Settings → Mailboxes lists the mailboxes; the seed patch adds the owner's mailbox and sales@.

1. In Google Cloud → APIs & Services → Credentials → the OAuth client used by ilL-Desk-Settings → Google App, add each mailbox's redirect URI to Authorized redirect URIs. The URIs are shown on the desk's Mailboxes card, e.g. `…/connected_app.callback/kevins-desk-sales`.
2. On the desk, click **Connect** and sign in to Google as that mailbox.

The desk creates `kevins-desk-<name>` Connected Apps by copying the Google App's client, and adds `access_type=offline`, `prompt=consent` and `login_hint`. The original Google App is not changed. Frappe stores the tokens encrypted in Token Cache and refreshes them. After connecting, the desk checks Gmail's profile; if you signed in as the wrong account, the card says "Wrong account".

**What's read.** Metadata only, never message bodies:
- the inbox for the last 21 days, without promotions, social and forums, and without mail from GitHub, Frappe Cloud, Vercel, Amazon, Intuit/QuickBooks, LinkedIn or Google
- sent mail for the last 30 days
- threads already labelled @Action or @Waiting

**Thread state** (from the last message):

| State | Meaning | Label |
|---|---|---|
| Needs reply | someone else wrote last, and the thread is in the inbox | @Action |
| Waiting | we wrote last, 3+ days ago | @Waiting |
| Recent | we wrote last, under 3 days ago | none |
| Handled | someone else wrote last, and the thread is no longer in the inbox | none |

"We" means the mailbox and the desk owner. A teammate counts as "we" on any thread that includes someone outside the company, as sender or recipient (they answered or wrote to the customer). A teammate writing internally is asking for something, so it lands in "Unblocking the team". Shared boxes map to a teammate (accounting@ is Charlotte). Any other company address (info@, notifications@) is a system sender, and Helpdesk tickets already cover those messages.

**Also not owed** (tuned on the first live run, Nov 23):
- A reply that only says thanks, with no question before the signature.
- Cold pitches (promotions, new products, partnerships, funding, trade fairs) from senders who aren't a customer, supplier, lead or teammate.
- Mail from vendor-system subdomains (`notice.`, `service.` …).
- Threads waiting more than 30 days (stale).

Automated mail is dropped and loses @Action/@Waiting: list headers, bulk precedence, Auto-Submitted, no-reply-style senders, and the skipped domains. @Quote is added to quote threads and never removed. Nothing is archived, marked read, trashed or sent.

**Placement on the stack:**
1. Risk words (damaged, not working, late, missing, urgent, …) → 1
2. A teammate → 5
3. A supplier → 3
4. Quote words → 2
5. Order words → 3
6. Support words → 4
7. Any other customer, dealer or new sender → 2

Senders are matched to a Customer, Supplier or Lead through Contact emails, by exact address or by company domain (not for gmail.com and the like).

ToDos are placed by their linked record:
- Quotation or Lead → 2
- Sales Order or Purchase Order → 3
- Ticket → 4
- Project or Task → 6

A ToDo assigned by a teammate goes to 5. A ToDo about our own systems (deploy, sync, QBO, Frappe, Webflow …) goes to 6 under Systems, even when it says "failed". Otherwise the same words as for threads decide, and anything left is 7 (admin).

## Tests

- `tests/portal_unit/test_kevins_desk.py`: the gate, the page context, the schedule.
- `tests/portal_unit/test_kevins_desk_pipeline.py`: endpoints and their 404s, the cache, the gateway adapter, and the widgets. The widget filters are checked against the gateway's own column registry, because the gateway silently drops filters on columns it doesn't list.
- `tests/portal_unit/test_kevins_desk_mail.py`: the Gmail client can't send or touch other labels; thread state; label changes; mailbox states without tokens; the connect flow; ranking; the warm job.
- `tests/portal_ui/kevins_desk.test.cjs`: the Pacific clock, block lookup, the page render, the one list, the Connect button (CSRF, Google-only redirect) and the view switch.
