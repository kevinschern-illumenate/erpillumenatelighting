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
| `kevins_desk/api.py` | `pipeline`, `signals` endpoints, cached per user for 5 minutes; `refresh=1` rebuilds |
| `doctype/ill_desk_settings` | Enabled, Desk Owner, Link Slug (System Manager only) |

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

Every item uses one shape (`id, dt, name, title, party, date, amount, status, flag, url, hat, stack`). Phase 3 merges these items with Gmail threads and ranks them.

## Tests

- `tests/portal_unit/test_kevins_desk.py`: the gate, the page context, the schedule.
- `tests/portal_unit/test_kevins_desk_pipeline.py`: endpoints and their 404s, the cache, the gateway adapter, and the widgets. The widget filters are checked against the gateway's own column registry, because the gateway silently drops filters on columns it doesn't list.
- `tests/portal_ui/kevins_desk.test.cjs`: the Pacific clock, block lookup, and the page render with stubbed endpoints.
