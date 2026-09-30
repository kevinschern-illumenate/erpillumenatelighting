# Portal operations

Open **ilLumenate Lighting → Portal Operations** (`/app/ill-portal-operations`). Counts and drilldowns call the same permission-aware server query. “Unavailable” means missing native read permission; it is not a zero count. No users are automatically assigned new roles.

| Staff role | Work |
|---|---|
| ilL Sales Review | Quote requests and draft order review. Prepare an ERP Quotation from the intake; submit it to issue an offer. Request information or propose a revision before order approval. |
| ilL Order Approver | Review the current buyer acknowledgment and pinned build/BOM, then submit the Sales Order. Drawing review is a separate manufacturing gate. |
| ilL Engineering | Drawing requests, unassigned/overdue work, reapproval tasks and incomplete technical exports. Open a request and use **Portal conversation** to ask for information or leave a staff-only note. Publish a new private deliverable with an explicit revision. Only the named reviewer records approval. |
| ilL Support | Issue response queue. Open **Portal conversation**, read the request, reply, request information, resolve with an explanation, or reopen. Returns remain requests; this flow does not issue credits. |
| ilL Operations | Read manufacturing drawing holds. Obtain a current technical approval before submitting the Work Order; this queue never releases work automatically. |
| ilL Integration | Publication and email failures. Inspect publication job errors before retrying. For email, distinguish failed queue creation from an existing Email Queue attempt. Never create a replacement email when delivery is uncertain. |
| ilL Catalog Publisher | Product, template/specification/compatibility/mapping authoring and approved Item literature. Run Engineering preflight on templates and Channel preflight on products, then approve/stage and explicitly publish the inspected revision. |

Engineering also receives master authoring and Item-literature permissions. Item creation, pricing maintenance, stock/manufacturing execution and accounting still require the corresponding native ERP job roles. The Operations role by itself supplies a drawing-hold view; it does not grant Work Order submission. See the [authoring field register](B2B_AUTHORING_FIELD_REGISTER.md) for setup/import order and public Sheet markup.

## Role assignment checklist

No user receives these roles automatically, and only System Manager is treated as internal staff everywhere. Staff who did this work with standard ERPNext roles before the B2B portal (Sales User, Sales Manager, Stock User…) lose it until they hold the matching ilL role. Assign roles on staging first, then on production right after the deploy ([recovery plan §7.1](DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md)).

1. List every enabled System User, the capabilities each has or lacks, and the capabilities nobody but a System Manager covers (`uncovered`):
   `bench --site <site> execute illumenate_lighting.illumenate_lighting.portal.role_audit.report`
2. Map each person using the table below. The ilL role adds to, and never replaces, the native ERP role (for example, approving a portal order also needs Sales Order submit permission).
3. List Dealer users the portal cannot place in exactly one company (`unresolved`: fix their Contact → Customer links), and Dealer users who would lose Desk the next time their User record is saved (`desk_access_at_risk`):
   `bench --site <site> execute illumenate_lighting.illumenate_lighting.portal.role_audit.dealers`
4. Run step 1 again and confirm `uncovered` is empty, or that a System Manager intentionally covers the rest.

| Work they did before | Assign | What it restores |
|---|---|---|
| Quotes, dealer projects and fixture schedules; Desk **Configure & Add Fixture** | ilL Sales Review | All-company project and schedule visibility, the Desk configurator, quote request and draft order review |
| Submitting Sales Orders that came from the portal | ilL Order Approver | Portal order approval (includes the Sales Review work above) |
| Drawings and technical review | ilL Engineering | Drawing requests, technical exports, master authoring |
| Webflow **Mark Pending**, product and catalog authoring | ilL Catalog Publisher | Webflow sync, publication, Item literature |
| Publication and email failures | ilL Integration | Publication job and outbox retries |
| Customer issues and account requests | ilL Support | Issue queue and account change requests |
| Work Order drawing holds | ilL Operations | Read-only drawing-hold view |

| Person | ilL roles assigned | Staging verified | Production assigned |
|---|---|---|---|
| | | | |

Use **Mine**, **Unassigned** or **Overdue** where offered. Department leads must assign an enabled System User and arrange absence coverage; no random fallback assignee is selected by the new queue service. Drawing request types continue to provide their existing default assignee, SLA and optional Task behavior.

Customer-visible replies appear in the portal and may generate a link-only notification. **Staff only** messages and their attachments do not appear in the customer thread or email. Reply retry keys avoid duplicate messages after a network interruption. Attachments are verified PDF/JPEG/PNG files, at most 20 MiB each and ten per reply.

Drawing impact uses physical rows, quantities, configured builds and BOMs. Price or terms edits do not create drawing reapproval work. A physical change creates a retained Task for that request/build. Review the task, revise the drawing as necessary, obtain a current decision, and close the task after completing the work. The manufacturing guard always checks the actual revision and build; the queue is an operational view.

A drawing associated only with a schedule can release an order only while the actual order rows still match that schedule. If staff changes the physical order scope, Engineering binds the request to that same-customer/same-schedule order, publishes a new revision and obtains a current review. Moving a requirement to a different existing order/schedule or waiving it still requires System Manager. Disabled reviewers and assignees are rejected.

Shipment/invoice rows copy designation, room, notes, configured links, BOM and engineering request from their exact submitted source row, with customer/company/Item checks. Use **ilL Delivery Note** for the unpriced delivery/return print, **ilL Sales Invoice** for invoices, and the existing ilL Quotation/Sales Order formats. The new print is additive and does not change site print defaults.

Notification Event/Delivery records retain recipient outcomes: pending, suppressed by preference, skipped for unavailable access, queued, failed, or delivered. “Delivered” means the native Email Queue reports SMTP acceptance; inbox delivery is not verified. Every five minutes the dispatcher creates bounded native queue batches and reconciles results. It performs no SMTP during the business request. Recipient preferences and current access are checked again by the Email Queue class immediately before sending, including native retries.

For failed queue creation, an integration user may call the approved `portal.outbox.retry` service or use its Desk action. A linked Email Queue must be inspected and retried using the native Email Queue workflow by a user with that permission. Missing historical Email Queue records are **unknown**, never evidence of delivery or permission to send a duplicate. Escalate to the site's email administrator when the integration role lacks native Email Queue access.

Workspace upgrades back up the existing record under the site's `private/ill-workspace` directory before the exported record is imported. The merge preserves site blocks and destinations and adds missing shipped shortcuts. Backups are retained; `last-merge.json` names the applied backup. Retain a separate private copy of this directory through site restores and moves; it is outside the standard files archive. Any migration moves an old `private/backups/ill-workspace` directory out of Frappe's backup cleanup path automatically ([recovery plan §6.3](DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md); history in the [backup cleanup repair](FRAPPE_CLOUD_BACKUP_REPAIR_2026_09_28.md)). Rehearse this on a restored Cloud site before release. A customized layout may position the new shortcuts after existing content; it is not replaced wholesale.

Local service/DOM tests cover predicates, forbidden states, retry behavior and merge preservation. Actual ordinary-role Desk walkthroughs, asset loading, scheduler execution and fresh/upgraded Cloud migrations remain deployment acceptance tasks.

Use [Cloud acceptance](B2B_CLOUD_ACCEPTANCE.md) for fixture secrets, historical checksums, concurrent-session tests, the mandatory role walkthrough matrix, legacy private-copy rehearsal, restore and rollout. Department leads must record named ownership and absence coverage there before release.
