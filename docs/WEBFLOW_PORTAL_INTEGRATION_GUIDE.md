# Webflow Portal Integration Guide

## Overview

This guide describes the authentication, pricing, and project management
integration between Webflow and ERPNext. ERPNext is the single source of
truth for user accounts, roles, and project data.

## Architecture

```
Webflow (browser)                ERPNext
──────────────────             ──────────────
Login form ──────────────────► /api/method/login
                                    │
get_user_context ◄──────────── Returns session + API key
                                    │
get_projects ────────────────► ilL-Project (filtered by Customer)
get_fixture_schedules ───────► ilL-Project-Fixture-Schedule
get_line_ids ────────────────► ilL-Child-Fixture-Schedule-Line
add_fixture_to_schedule ─────► Create/overwrite schedule line
get_pricing ─────────────────► Item Price (Dealer only)
```

## Authentication Flow

1. User submits credentials on Webflow login form.
2. `POST /api/method/login` authenticates against ERPNext.
3. On success, call `get_user_context` to retrieve:
   - Linked Customer (via Contact → Dynamic Link → Customer)
   - Dealer role status
   - API key/secret pair for subsequent requests
4. Credentials are stored in `sessionStorage` (cleared on tab close).
5. Logout calls `/api/method/logout` and clears stored credentials.

### Security Notes

- API key/secret are stored in `sessionStorage` (not `localStorage`) to
  reduce exposure.
- For production deployments, consider a Cloudflare Worker proxy or
  `httpOnly` cookie approach to avoid client-side credential storage.
- All API endpoints verify the requesting user's linked Customer matches
  the project's Customer (ownership check).

## Dealer-Gated Pricing

- The `get_pricing` endpoint only returns price data if the user has the
  **Dealer** role or is an internal (System Manager) user.
- On Webflow product pages, pricing elements should use the
  `data-dealer-pricing` attribute. The `webflow_portal.js` script
  automatically hides/shows them based on the user's role.
- On the ERPNext portal `/configure` page, pricing visibility is controlled
  by the same Dealer role check.

## Cascading Selection (Project → Schedule → Line)

When a logged-in user visits a Webflow product page:

1. **On page load** → `get_projects` returns the user's customer's projects.
2. **User selects a Project** → `get_fixture_schedules(project)` returns
   schedules for that project.
3. **User selects a Schedule** → `get_line_ids(project, fixture_schedule)`
   returns existing line items with their current part numbers.
4. **User chooses action:**
   - **Overwrite:** Select an existing Line ID and replace its part number.
   - **New Line:** Create a new line with auto-generated Line ID.
5. **Submit** → `add_fixture_to_schedule(...)` persists the change.

## CORS Configuration

ERPNext `hooks.py` includes CORS settings allowing requests from:
- `https://www.illumenatelighting.com`
- `https://illumenatelighting.webflow.io`

Allowed headers include `Authorization` and `X-Frappe-Token`.

## API Endpoints Summary

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `webflow_auth.get_user_context` | Required | Return role, customer, API keys |
| `webflow_portal.get_pricing` | Dealer only | Return item price |
| `webflow_portal.get_projects` | Required | List user's projects |
| `webflow_portal.get_fixture_schedules` | Required | List schedules for a project |
| `webflow_portal.get_line_ids` | Required | List lines for a schedule |
| `webflow_portal.add_fixture_to_schedule` | Required | Add/overwrite a fixture line |

## Client-Side Setup

Include `webflow_portal.js` on Webflow pages:

```html
<script src="https://your-erpnext.com/assets/illumenate_lighting/js/webflow_portal.js"></script>
<script>
  IllumenatePortal.init({ erpnextUrl: "https://your-erpnext.com" });
</script>
```

See `WEBFLOW_API_DOCUMENTATION.md` for full endpoint reference and examples.

## Related Documentation

- [DEALER_ROLE.md](DEALER_ROLE.md) — Dealer role setup
- [MVP_CONSTRAINTS.md](MVP_CONSTRAINTS.md) — Known limitations
- [WEBFLOW_INTEGRATION_GUIDE.md](WEBFLOW_INTEGRATION_GUIDE.md) — Product/CMS integration
- [WEBFLOW_API_DOCUMENTATION.md](../illumenate_lighting/illumenate_lighting/api/WEBFLOW_API_DOCUMENTATION.md) — Full API reference
