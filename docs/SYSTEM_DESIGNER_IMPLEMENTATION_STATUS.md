# ilLumenate System Designer — Implementation Status

Tracks work packages from [SYSTEM_DESIGNER_PRODUCT_PLAN.md](SYSTEM_DESIGNER_PRODUCT_PLAN.md) (Part II, H11).
Each entry records what landed, where, and any place the code disagreed with the plan (H1 rule 1).

| WP | Title | Status |
|---|---|---|
| WP-0.1 | Portal access audit for designer surfaces | Done (no code change needed, see below) |
| WP-0.2 | Workspace scaffold and bundle pipeline | Done |
| WP-0.3 | Import riser source | Done (see notes) |
| WP-0.4 | Commit the visualizer as a reference asset | Done |
| WP-0.5 | Applications Engineer role, capability and Settings | Done |
| WP-0.6 | Python package skeleton and error contract | Done |

## WP-0.1 — Portal access audit

Checked every P0 item from `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md` §5 that touches
schedules, document requests or drawing requests against the current code. All were already fixed when
the access layer was consolidated into `portal/access.py`; each has a regression test in
`illumenate_lighting/illumenate_lighting/api/test_portal_access_matrix.py` (installed-site suite).

| Item | Status | Evidence |
|---|---|---|
| P0.1 Non-dealer company users receive write/delete | Fixed earlier | `portal/access.py project_permission` grants company members read-like ptypes only (`_is_read(ptype) and not project.is_private`); schedules delegate through `schedule_permission`. Tests: `test_same_company_member_is_read_only`, `test_same_company_member_cannot_mutate_via_api` |
| P0.2 Schedule list visibility disagrees with direct access | Fixed earlier | `ill_project_fixture_schedule.get_permission_query_conditions` returns `access.schedule_query_conditions`, which mirrors `schedule_permission` including the collaborator branch. Tests: `test_schedule_list_matches_direct_access`, `test_collaborator_discovers_inherited_schedule` |
| P0.3 Document request list/count globally scoped | Fixed earlier | `api/document_requests._scoped_request_conditions` applies the doctype's `get_permission_query_conditions` to both `list_requests` and `get_request_counts`. Test: `test_request_list_and_counts_are_scoped` |
| P0.4 Drawing request accepts an arbitrary project | Fixed earlier | Both `api/portal.create_drawing_request` and `api/document_requests.create_request` go through `create_portal_document_request`, which requires `can_read_project` and resolves only active request types (never creates masters). Tests: `test_request_creation_requires_project_access`, `test_drawing_request_never_creates_request_type`, `test_request_creation_rejects_guest` |
| P0.6 Collaborator mutation policy inconsistent | Fixed earlier | `access.can_manage_project_collaborators` is the single rule, used by `update_project_collaborators`, the remove endpoint, `invite_project_collaborator` and `portal/accounts.py`. Tests: `test_collaborator_management_policy`, `test_edit_collaborator_cannot_manage_collaborators_or_privacy`, `test_other_company_dealer_cannot_invite` |

Note for WP-4.2: `ill_document_request._is_request_staff` grants request staff through the `engineering`
capability, not an explicit role list, so H4.4's "add the new role" step does not apply as written. An
Applications Engineer reaches a review request as its `technical_reviewer` (read) — WP-4.2 decides whether
`design_review` should also count as request staff.

## WP-0.5 / WP-0.6 — Role, Settings, package skeleton

- Role `ilL Applications Engineer` is created by `patches/create_applications_engineer_role.py` in
  `[pre_model_sync]`; `portal/staff.py` maps capability `design_review` to it.
- `ilL-System-Designer-Settings` (Single) holds the H4.1 defaults. The pilot list is a Table MultiSelect
  over the new child doctype `ilL-Child-Designer-Pilot-Customer` (one `customer` Link).
- `system_design/settings.py` returns the H4.1 defaults for any value the Single has never stored.
- `system_design/api.py` defines the response contract (`respond`, `fail`, `DesignError`, `endpoint`);
  `system_design/access.py` wraps `portal/access.py` and `portal/staff.py`. Unreadable and missing
  schedules both return `NOT_FOUND`.
- Discrepancy: the plan's `require_read(schedule)` takes a name; `portal/access.schedule_permission`
  takes a document, so the wrappers load the schedule and return it.

## WP-0.2 — Workspace and mount

- `tools/system_designer` is an npm workspace (`packages/*`, `app`). `npm run build` writes
  `illumenate_lighting/public/system_designer/{designer.js,designer.css}`; CI checks it is fresh.
- Routes `/portal/schedules/<schedule>/design` and `/portal/design` render `templates/pages/system_design`.
  The share route (`/portal/design-share/<token>`) is added with WP-7.4, when its page exists.
- Who sees the page: logged-in users who can read the schedule **and** for whom the designer is enabled —
  Settings `enabled`, the user's Customer in `pilot_customers`, or staff (`engineering` / `design_review`
  capability or System Manager) so the team can test before the pilot. Everyone else is redirected
  to the schedule page (or `/portal/projects` from `/portal/design`).

## WP-0.3 — Riser source

See the WP-0.3 section of the pull request: the riser repository is imported under
`tools/system_designer/vendor/riser` with history (subtree), and its engine, schemas, drawing,
serializers and data move into workspace packages with the riser test suite running in this repo's CI.

## WP-0.4 — Visualizer reference

`tools/system_designer/reference/led-tape-system-visualizer.html` is the supplied file, unchanged.
