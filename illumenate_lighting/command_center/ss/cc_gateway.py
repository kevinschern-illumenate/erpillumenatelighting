# Server Script: "ilL Command Center Gateway"
#   Script Type: API      API Method: ill_cc_gateway      Allow Guest: NO
#
# One role-gated endpoint the Command Center page uses to list, inspect, create and edit
# records in every pipeline doctype, plus the aggregates for the Executive page.
#
# Call:  /api/method/ill_cc_gateway   (POST, JSON body, CSRF token like any desk call)
#   action=config [lite]               -> what THIS user may see/do (lite: tabs only, no doctypes); incl.
#                                        catalog.allowed (Catalog tab: ilL Catalog Publisher / System Manager)
#   action=counts [area, section]      -> record count per available doctype (workbench landing); area
#                                        "pipeline" (default) or "ill", or just one section/group
#   action=list   dt, filters, search, limit, start, order_by
#   action=meta   dt                   -> editable form fields (so the UI builds forms itself)
#   action=get    dt, name             -> full doc + recent audit entries
#   action=save   dt, name, values     -> update an existing DRAFT/non-submitted doc
#   action=create dt, values           -> insert a new doc (draft)
#   action=overview                    -> per-stage counts/values by status + "decision" signals
#   action=feed   [dts], [limit]       -> recent Command Center changes the user may see
#   action=stages                      -> lanes for Design / Quotes / Sales orders / Service (portal
#                                        requests, schedules, projects, offers) + ticket links
#   action=assign dt, name, add[], remove[] -> add/remove owners (open ToDos) on a record
#   action=note   dt, name, text       -> "Command Center:" comment on a record (after a change)
#   action=agenda_list                 -> weekly meetings (newest first) with item counts
#   action=agenda_get  name            -> one meeting, its items, live columns of linked records
#   action=agenda_create values{title, meeting_date, carry}  -> new meeting (+ carry Open items over)
#   action=agenda_save_meeting name, values{title, meeting_date, status, notes}
#   action=agenda_add  agenda, values{item_title, details, presenter, reference_doctype, reference_name}
#   action=agenda_update name, values{item_title, details, presenter, status, outcome}
#   action=agenda_order agenda, names[] -> save the item order
#   action=agenda_remove name          -> delete one agenda item (never the record it links to)
#   action=agenda_todo name, values{title, owners[], date, priority, notes} -> one ToDo per owner from
#                                        the item's outcome, linked to the item's record (or the item)
#
# Guarantees
#   * Needs role "Command Center Viewer" (reads) / "Command Center Editor" (writes).
#   * Each section additionally needs its own role when listed in SECTIONS below.
#   * Acts as the signed-in user (no ignore_permissions on data), so ERPNext's own
#     role/permission rules remain the final authority.
#   * Never submits, cancels or deletes (the only delete is removing an agenda item;
#     unassigning someone cancels their open ToDo on the record, as the desk does).
#     Submitted docs (docstatus 1/2) are read-only.
#   * Only doctypes in ALLOWED (pipeline) or ILL_GROUPS (ilLumenate area) can be touched; only non-system,
#     permlevel-0 fields can be written. READ_ONLY doctypes are never saved or created; CREATE_VIA_BUILDER
#     doctypes are created in the Catalog Builder (Check -> Import with an audit receipt), not here.
#   * Doctypes/columns that don't exist on this site are skipped, not errors.
#   * Every create/save writes an "Info" comment on the record (visible in its timeline).
#
# Sandbox notes (Frappe Server Scripts run under RestrictedPython):
#   * No names may start with "_" (the v4 draft used _gate, _roles ... and did not compile).
#   * Top-level functions cannot see each other or top-level constants (separate globals and
#     locals), so EVERYTHING lives inside main() and the helpers are closures.
#   * frappe.get_roles / frappe.has_permission are not exposed, so roles come from the
#     "Has Role" table, read access from frappe.get_list (raises if not allowed) and create
#     access from Document.has_permission() on a blank in-memory doc.
#   * Frappe v16 rejects SQL functions as strings in get_list fields; aggregates use the dict form
#     ({"COUNT": "*", "as": "n"}) with the v15 string form as a fallback.


def main():
    VIEW_ROLE = "Command Center Viewer"
    EDIT_ROLE = "Command Center Editor"

    # section -> (label, extra role required IN ADDITION to the viewer role; "" = none)
    # In pipeline order: Design -> Quotes -> Sales orders -> Purchasing -> Manufacturing -> Shipping -> Service.
    SECTIONS = {
        "sales": ("Sales", ""), "design": ("Design", ""), "quotes": ("Quotes", ""),
        "orders": ("Sales orders", ""), "purchasing": ("Purchasing", ""),
        "manufacturing": ("Manufacturing", ""), "shipping": ("Shipping", ""),
        "service": ("Service", ""), "projects": ("Projects & tasks", ""),
        "finance": ("Finance", "Command Center Finance"),
    }

    # doctype -> (section, [preferred list columns]).  Columns missing on the site are dropped.
    # "status" is a logical column: for doctypes in STATE_FIELD it reads/filters/sorts that field.
    ALLOWED = {
        "Customer":          ("sales",         ["name", "customer_name", "customer_group", "territory", "modified"]),
        "ilL-Project":       ("design",        ["name", "project_name", "customer", "status", "architect",
                                                "lighting_designer", "general_contractor", "erp_project", "modified"]),
        "ilL-Project-Fixture-Schedule": ("design", ["name", "schedule_name", "ill_project", "customer", "status",
                                                    "version", "is_locked", "sales_order", "modified"]),
        "ilL-Document-Request": ("design",     ["name", "request_type", "status", "priority", "requester_customer",
                                                "fixture_schedule", "sales_order", "assigned_to", "sla_deadline",
                                                "requested_due_date", "creation", "modified"]),
        "ilL-Drawing-Review": ("design",       ["name", "request", "revision", "status", "reviewed_by",
                                                "reviewed_on", "creation"]),
        "Quotation":         ("quotes",        ["name", "party_name", "status", "grand_total", "transaction_date", "modified"]),
        "ilL-Quote-Request": ("quotes",        ["name", "customer", "status", "schedule", "project", "assigned_to",
                                                "due_date", "latest_offer", "creation", "modified"]),
        "ilL-Quote-Offer":   ("quotes",        ["name", "customer", "status", "quotation", "quote_request", "schedule",
                                                "valid_until", "sales_order", "creation", "modified"]),
        "Sales Order":       ("orders",        ["name", "customer", "status", "grand_total", "delivery_date", "modified"]),
        "ilL-Order-Intake":  ("orders",        ["name", "customer", "status", "schedule", "sales_order", "assigned_to",
                                                "due_date", "creation", "modified"]),
        "ilL-Order-Change":  ("orders",        ["name", "customer", "status", "request_type", "sales_order",
                                                "assigned_to", "due_date", "creation", "modified"]),
        "Material Request":  ("purchasing",    ["name", "material_request_type", "status", "schedule_date", "modified"]),
        "Request for Quotation": ("purchasing", ["name", "status", "transaction_date", "schedule_date", "modified"]),
        "Supplier Quotation": ("purchasing",   ["name", "supplier", "status", "grand_total", "valid_till",
                                                "transaction_date", "modified"]),
        "Purchase Order":    ("purchasing",    ["name", "supplier", "status", "ill_vendor_status", "grand_total",
                                                "ill_eta", "schedule_date", "modified"]),
        "Purchase Receipt":  ("purchasing",    ["name", "supplier", "status", "grand_total", "posting_date", "per_billed",
                                                "modified"]),
        "ilL-Inbound-Shipment": ("purchasing", ["name", "status", "supplier", "freight_mode", "tracking_no", "eta",
                                                "actual_cost_total", "modified"]),
        "Supplier":          ("purchasing",    ["name", "supplier_name", "supplier_group", "country",
                                                "ill_default_lead_time_days", "modified"]),
        "Work Order":        ("manufacturing", ["name", "production_item", "status", "qty", "planned_start_date", "modified"]),
        "Delivery Note":     ("shipping",      ["name", "customer", "status", "posting_date", "modified"]),
        "HD Ticket":         ("service",       ["name", "subject", "status", "priority", "ticket_type", "modified"]),
        "ilL-Account-Request": ("service",     ["name", "request_type", "customer", "status", "requested_by",
                                                "assigned_to", "creation", "modified"]),
        "Sales Invoice":     ("finance",       ["name", "customer", "status", "grand_total", "outstanding_amount", "due_date", "modified"]),
        "Purchase Invoice":  ("finance",       ["name", "supplier", "status", "grand_total", "outstanding_amount", "due_date",
                                                "modified"]),
        "Landed Cost Voucher": ("finance",     ["name", "posting_date", "total_taxes_and_charges", "docstatus", "modified"]),
        "Project":           ("projects",      ["name", "project_name", "status", "percent_complete", "expected_end_date", "modified"]),
        "Task":              ("projects",      ["name", "subject", "status", "priority", "project", "exp_end_date", "modified"]),
        "ToDo":              ("projects",      ["name", "description", "status", "allocated_to", "date", "modified"]),
    }

    # ---- ilLumenate area (v8): every app doctype, grouped like the Desk workspace ----
    # [key, label, extra role ("" = none), [doctypes]]. Keys start with "ill_" so they never clash with a
    # pipeline section. A doctype may sit in a pipeline section AND a group (lists, views and counts are
    # keyed by doctype, so they are shared). Columns are derived from meta (title + in_list_view fields).
    # tests/portal_unit/test_cc_workbench_registry.py fails when an app doctype is in no group, SETTINGS or
    # EXCLUDED, so a new doctype can't silently go missing.
    ILL_GROUPS = [
        ["ill_templates", "Product templates", "", [
            "ilL-Fixture-Template", "ilL-Extrusion-Kit-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template",
            "ilL-Driver-Template", "ilL-Controller-Template"]],
        ["ill_specs", "Specifications", "", [
            "ilL-Spec-Accessory", "ilL-Spec-Colorimetry", "ilL-Spec-Controller", "ilL-Spec-Driver", "ilL-Spec-LED-Sheet",
            "ilL-Spec-LED Tape", "ilL-Spec-Lens", "ilL-Spec-Photometry", "ilL-Spec-Profile", "ilL-Spec-Wire"]],
        ["ill_attributes", "Attributes", "", [
            "ilL-Attribute-CCT", "ilL-Attribute-CRI", "ilL-Attribute-Certification", "ilL-Attribute-Controller Type",
            "ilL-Attribute-Dimming Protocol", "ilL-Attribute-Endcap Color", "ilL-Attribute-Endcap Style",
            "ilL-Attribute-Environment Rating", "ilL-Attribute-Feed-Direction", "ilL-Attribute-Finish",
            "ilL-Attribute-IP Rating", "ilL-Attribute-Joiner Angle", "ilL-Attribute-Joiner System",
            "ilL-Attribute-LED Package", "ilL-Attribute-Lead Time Class", "ilL-Attribute-Leader Cable",
            "ilL-Attribute-Lens Appearance", "ilL-Attribute-Lens Interface Type", "ilL-Attribute-Mounting Method",
            "ilL-Attribute-Mounting Type", "ilL-Attribute-Output Level", "ilL-Attribute-Output Voltage",
            "ilL-Attribute-PCB Finish", "ilL-Attribute-PCB Mounting", "ilL-Attribute-Power Feed Type",
            "ilL-Attribute-Pricing Class", "ilL-Attribute-SDCM", "ilL-Attribute-Series", "ilL-Job-Title-Master"]],
        ["ill_rels", "Relationships & maps", "", [
            "ilL-Rel-Driver-Eligibility", "ilL-Rel-Endcap-Map", "ilL-Rel-Finish Endcap Color", "ilL-Rel-Kit-Endcap-Map",
            "ilL-Rel-Kit-Lens-Map", "ilL-Rel-Kit-Mounting-Map", "ilL-Rel-Kit-Profile-Map", "ilL-Rel-Leader-Cable-Map",
            "ilL-Rel-Mounting-Accessory-Map", "ilL-Rel-Profile Lens", "ilL-Rel-Tape Offering"]],
        ["ill_submittals", "Submittal mappings", "", [
            "ilL-Spec-Submittal-Mapping", "ilL-Driver-Submittal-Mapping", "ilL-Controller-Submittal-Mapping",
            "ilL-Kit-Submittal-Mapping", "ilL-LED-Sheet-Submittal-Mapping", "ilL-Neon-Submittal-Mapping"]],
        ["ill_configured", "Configured products", "", [
            "ilL-Configured-Fixture", "ilL-Configured-Group", "ilL-Configured-LED-Sheet", "ilL-Configured-Tape-Neon",
            "ilL-Configuration-Preset"]],
        ["ill_projects", "Projects & design", "", [
            "ilL-Project", "ilL-Project-Fixture-Schedule", "ilL-Project-Party", "ilL-Document-Request",
            "ilL-Drawing-Review", "ilL-Line-Document", "ilL-Request-Type", "ilL-System-Design"]],
        ["ill_portal", "Dealer portal", "", [
            "ilL-Quote-Request", "ilL-Quote-Offer", "ilL-Order-Intake", "ilL-Order-Change", "ilL-Account-Request",
            "ilL-Portal-Invitation", "ilL-Portal-User-Settings"]],
        ["ill_purchasing", "Purchasing & inbound", "", ["ilL-Inbound-Shipment"]],
        ["ill_publishing", "Catalog & Webflow publishing", "", [
            "ilL-Catalog-Import", "ilL-Product-Publication", "ilL-Publish-Job", "ilL-Item-Literature",
            "ilL-Image-Derivative", "ilL-Webflow-Product", "ilL-Webflow-Category", "ilL-Webflow-Brand",
            "ilL-Webflow-Approval", "ilL-Webflow-Auto-Push"]],
        ["ill_finder", "Product finder", "", [
            "ilL-Finder-Question", "ilL-Finder-Glossary-Term", "ilL-Product-Verification-Request"]],
        ["ill_meetings", "Meetings", "", ["ilL-Meeting-Agenda", "ilL-Meeting-Agenda-Item"]],
        # logs and generated records: System Manager only (most are System Manager-only in ERPNext anyway)
        ["ill_logs", "Logs & system (read-only)", "System Manager", [
            "ilL-Portal-Event", "ilL-Portal-Message", "ilL-Portal-Delivery", "ilL-Portal-Upload",
            "ilL-Configurator-Session", "ilL-Configuration-Receipt", "ilL-Design-Catalog-Snapshot",
            "ilL-Webflow-Configurator-Cache", "ilL-Export-Job", "ilL-QBO-Sync-Log"]],
    ]
    # single (settings) doctypes: plain Desk links on the ilLumenate landing; the desk enforces permission
    SETTINGS = ["ilL-Purchasing-Settings", "ilL-Production-Settings", "ilL-Portal-Routing-Settings",
                "ilL-Product-Finder-Settings", "ilL-System-Designer-Settings", "Email Campaign Benchmark Settings",
                "ilL-Email-Settings"]
    # never exposed: session tokens and singles holding credentials
    EXCLUDED = ["ilL-Webflow-Session", "ilL-Webflow-Settings", "ilL-QBO-Settings"]
    # generated or audit records: listed and opened, never saved or created here
    READ_ONLY = [
        "ilL-Configured-Fixture", "ilL-Configured-Group", "ilL-Configured-LED-Sheet", "ilL-Configured-Tape-Neon",
        "ilL-Configuration-Receipt", "ilL-Configurator-Session", "ilL-Design-Catalog-Snapshot", "ilL-Catalog-Import",
        "ilL-Portal-Event", "ilL-Portal-Message", "ilL-Portal-Delivery", "ilL-Portal-Upload", "ilL-Publish-Job",
        "ilL-Export-Job", "ilL-QBO-Sync-Log", "ilL-Image-Derivative", "ilL-Webflow-Configurator-Cache",
        # approvals are decided and auto pushes queued from the Webflow Product (plan 4.19)
        "ilL-Webflow-Approval", "ilL-Webflow-Auto-Push",
    ]
    # structural catalog records: created (and restructured) in the Catalog Builder, so every change gets a
    # Check, a single-transaction Import and an ilL-Catalog-Import receipt. "+ New" opens the Catalog tab.
    CREATE_VIA_BUILDER = ["Item"]
    for g in ILL_GROUPS:
        if g[0] in ("ill_templates", "ill_specs", "ill_rels", "ill_submittals"):
            for d in g[3]:
                CREATE_VIA_BUILDER.append(d)

    # doctypes whose status lives in another field (the portal doctypes use "state").
    # Masters with no status but an is_active Check are exposed as status "Active"/"Inactive" (see skind).
    STATE_FIELD = {
        "ilL-Quote-Request": "state", "ilL-Quote-Offer": "state", "ilL-Order-Intake": "state",
        "ilL-Order-Change": "state", "ilL-Account-Request": "state", "ilL-Drawing-Review": "decision",
        "ilL-Portal-Delivery": "state", "ilL-Portal-Invitation": "state", "ilL-Portal-Upload": "state",
        "ilL-Product-Publication": "state", "ilL-Publish-Job": "state",
        "ilL-Product-Verification-Request": "state",
    }

    # the effective registry: doctype -> [section keys] and doctype -> preferred columns (None = from meta)
    AREA = {}
    for s in SECTIONS:
        AREA[s] = "pipeline"
    SECTION_OF = {}
    COLUMNS = {}
    for d in ALLOWED:
        SECTION_OF[d] = [ALLOWED[d][0]]
        COLUMNS[d] = ALLOWED[d][1]
    for g in ILL_GROUPS:
        SECTIONS[g[0]] = (g[1], g[2])
        AREA[g[0]] = "ill"
        for d in g[3]:
            if d in EXCLUDED:
                continue
            if d not in SECTION_OF:
                SECTION_OF[d] = []
                COLUMNS[d] = None
            SECTION_OF[d].append(g[0])

    STD_COLS = {"name": ("ID", "Data"), "owner": ("Created by", "Link"),
                "creation": ("Created", "Datetime"), "modified": ("Modified", "Datetime"),
                "docstatus": ("Doc status", "Int")}

    # never writable from the page, whatever the doctype says
    BLOCKED_WRITE = [
        "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "naming_series",
        "amended_from", "parent", "parenttype", "parentfield", "workflow_state",
    ]
    SKIP_FIELD_TYPES = ["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table",
                        "Table MultiSelect", "Attach", "Attach Image", "Image", "Heading", "Fold",
                        "Text Editor", "HTML Editor", "Markdown Editor", "Code", "JSON", "Signature",
                        "Geolocation", "Password"]
    TEXT_TYPES = ["Data", "Link", "Small Text", "Text", "Long Text", "Select"]

    user = frappe.session.user
    roles = []
    if user != "Guest":
        for r in frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, fields=["role"]):
            roles.append(r["role"])

    def deny(msg):
        frappe.throw(msg)

    def gate():
        if user == "Guest":
            deny("Please log in.")
        if VIEW_ROLE not in roles:
            deny("You don't have Command Center access.")

    def section_ok(section):
        need = SECTIONS[section][1]
        return (not need) or (need in roles)

    memo = {}

    def can(dt, ptype):
        key = dt + "|" + ptype
        if key in memo:
            return memo[key]
        ok = False
        try:
            if ptype == "read":
                # frappe.get_list raises PermissionError when the user can't read the doctype,
                # and it applies the same rules (incl. app permission hooks) as the desk list
                frappe.get_list(dt, fields=["name"], limit_page_length=1)
                ok = True
            else:
                # same check ERPNext runs on insert, done on a blank in-memory doc (nothing saved)
                ok = bool(frappe.get_doc({"doctype": dt}).has_permission(ptype))
        except Exception:
            ok = False
        memo[key] = ok
        return ok

    def sections_ok(dt):
        out = []
        for sec in SECTION_OF.get(dt) or []:
            if section_ok(sec):
                out.append(sec)
        return out

    def exists_dt(dt):
        # one query for every registry doctype the first time, instead of one per doctype
        if "|exists" not in memo:
            names = []
            for d in SECTION_OF:
                names.append(d)
            have = {}
            for r in frappe.get_all("DocType", filters={"name": ["in", names]}, fields=["name"],
                                    limit_page_length=len(names) + 5):
                have[r["name"]] = 1
            memo["|exists"] = have
        return dt in memo["|exists"] or bool(frappe.db.exists("DocType", dt))

    def available(dt):
        # in the registry + a section the user may open + exists on this site + the user may read it in ERPNext
        key = dt + "|avail"
        if key not in memo:
            memo[key] = (dt in SECTION_OF and len(sections_ok(dt)) > 0 and exists_dt(dt) and can(dt, "read"))
        return memo[key]

    def doctype(dt):
        if dt not in SECTION_OF:
            deny("That doctype isn't available in the Command Center.")
        if not sections_ok(dt):
            deny("You don't have access to the " + SECTIONS[SECTION_OF[dt][0]][0] + " section.")
        if not exists_dt(dt):
            deny(dt + " doesn't exist on this site.")
        if not can(dt, "read"):
            deny("Your ERPNext user can't read " + dt + ".")
        return sections_ok(dt)[0]

    def can_edit():
        return EDIT_ROLE in roles

    def need_edit():
        if not can_edit():
            deny("You have view-only access. Ask Kevin for the Command Center Editor role.")

    def skind(dt):
        # how this doctype holds its status: "state" (another field), "status", "bool" (is_active) or ""
        key = dt + "|skind"
        if key not in memo:
            meta = frappe.get_meta(dt)
            if dt in STATE_FIELD and meta.get_field(STATE_FIELD[dt]):
                memo[key] = "state"
            elif meta.get_field("status"):
                memo[key] = "status"
            elif meta.get_field("is_active"):
                memo[key] = "bool"
            else:
                memo[key] = ""
        return memo[key]

    def sfield(dt):
        k = skind(dt)
        if k == "state":
            return STATE_FIELD[dt]
        if k == "bool":
            return "is_active"
        return "status"

    def real(dt, c):
        # logical column -> the field that holds it on this doctype
        return sfield(dt) if c == "status" else c

    def preferred(dt):
        # the registry's columns, or (C4) name + title + up to 4 in_list_view fields + status + modified
        if COLUMNS.get(dt):
            return COLUMNS[dt]
        key = dt + "|cols"
        if key not in memo:
            meta = frappe.get_meta(dt)
            out = ["name"]
            skip = ["name", "status", "is_active", "modified"]
            if dt in STATE_FIELD:
                skip.append(STATE_FIELD[dt])
            tf = meta.title_field
            if tf and tf not in skip and meta.get_field(tf):
                out.append(tf)
                skip.append(tf)
            n = 0
            for f in meta.fields:
                if n >= 4:
                    break
                if f.in_list_view and f.fieldname not in skip and f.fieldtype not in SKIP_FIELD_TYPES:
                    out.append(f.fieldname)
                    skip.append(f.fieldname)
                    n = n + 1
            if skind(dt):
                out.append("status")
            out.append("modified")
            memo[key] = out
        return memo[key]

    def cols(dt):
        # logical columns (may include "status") that exist on this site
        meta = frappe.get_meta(dt)
        out = []
        for c in preferred(dt):
            if c in STD_COLS or (c == "status" and skind(dt)) or meta.get_field(real(dt, c)):
                if c not in out:
                    out.append(c)
        return out

    def qfields(dt, logical):
        out = []
        for c in logical:
            out.append(real(dt, c))
        return out

    def fixrows(dt, rows):
        # expose the doctype's state field (or its active flag) under the logical name "status"
        k = skind(dt)
        sf = sfield(dt)
        if k == "bool":
            for r in rows:
                r["status"] = "Active" if r.get("is_active") else "Inactive"
        elif sf != "status":
            for r in rows:
                r["status"] = r.get(sf)
        return rows

    def qfilters(dt, filters):
        out = {}
        for k in filters:
            v = filters[k]
            if k == "status" and skind(dt) == "bool":
                v = 0 if str(v) == "Inactive" else 1
            out[real(dt, k)] = v
        return out

    def colinfo(dt):
        meta = frappe.get_meta(dt)
        info = []
        for c in cols(dt):
            if c in STD_COLS:
                info.append({"fieldname": c, "label": STD_COLS[c][0], "type": STD_COLS[c][1]})
            elif c == "status" and skind(dt) == "bool":
                info.append({"fieldname": "status", "label": "Status", "type": "Select"})
            else:
                f = meta.get_field(real(dt, c))
                info.append({"fieldname": c, "label": f.label or c, "type": f.fieldtype})
        return info

    def writable_fields(dt):
        out = {}
        for f in frappe.get_meta(dt).fields:
            if f.fieldtype in SKIP_FIELD_TYPES or f.read_only or f.hidden or f.fieldname in BLOCKED_WRITE:
                continue
            # C11: higher permlevel fields need their own permission; Frappe would silently drop the edit
            if f.permlevel and f.permlevel > 0:
                continue
            out[f.fieldname] = f
        return out

    def create_kind(dt):
        # "+ New" behaviour: "builder" (Catalog tab), "inline" (gateway create) or "" (not here)
        if dt in READ_ONLY:
            return ""
        if dt in CREATE_VIA_BUILDER:
            return "builder"
        return "inline"

    def audit(dt, name, text):
        frappe.get_doc({
            "doctype": "Comment", "comment_type": "Info",
            "reference_doctype": dt, "reference_name": name,
            "content": "Command Center: " + text,
        }).insert(ignore_permissions=True)   # audit trail only, never user data

    def jsonarg(key):
        # the page posts a JSON body, so these normally arrive already parsed
        v = frappe.form_dict.get(key)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                deny("Could not read the '" + key + "' argument.")
        return v or {}

    def clean(dt, values):
        allowed = writable_fields(dt)
        bad = []
        for k in values:
            if k not in allowed:
                bad.append(k)
        if bad:
            deny("Not editable from the Command Center: " + ", ".join(bad))
        return values

    def total(dt, filters, orf):
        # Frappe v16 only accepts SQL functions in dict form ({"COUNT": "*"}); v15 only as strings.
        # Both forms are permission-aware and honour or_filters (the search box).
        for f in ({"COUNT": "*", "as": "total"}, "count(name) as total"):
            try:
                r = frappe.get_list(dt, fields=[f], filters=filters, or_filters=orf)
                return int(r[0]["total"] or 0)
            except Exception:
                pass
        return frappe.db.count(dt, filters)

    gate()
    action = frappe.form_dict.get("action") or "config"
    dt = frappe.form_dict.get("dt")

    if action == "config":
        sections = []
        for s in SECTIONS:
            sections.append({"key": s, "label": SECTIONS[s][0], "locked": not section_ok(s),
                             "needs": SECTIONS[s][1], "area": AREA.get(s) or "pipeline"})
        catalog = {"allowed": user == "Administrator" or "System Manager" in roles
                   or "ilL Catalog Publisher" in roles, "url": "/catalog-builder"}
        out = {"user": user, "can_edit": can_edit(), "sections": sections, "catalog": catalog,
               "today": frappe.utils.nowdate()}
        if not frappe.form_dict.get("lite"):
            # "lite" is the page's startup call (top tabs only); the Workbench asks for the full config
            dts = {}
            for d in SECTION_OF:
                if available(d):
                    ck = create_kind(d)
                    dts[d] = {"section": sections_ok(d)[0], "sections": sections_ok(d), "columns": colinfo(d),
                              "can_create": can_edit() and ck != "" and can(d, "create"),
                              "create": ck, "read_only": d in READ_ONLY, "status_kind": skind(d) or None,
                              "builder": d in CREATE_VIA_BUILDER}
            settings = []
            for d in SETTINGS:
                if exists_dt(d):
                    settings.append({"doctype": d, "url": "/app/" + d.lower().replace(" ", "-")})
            out["doctypes"] = dts
            out["settings"] = settings
        frappe.response["message"] = out

    elif action == "counts":
        # area "pipeline" (default, the Workbench landing as before) or "ill"; optional one section
        area = frappe.form_dict.get("area") or "pipeline"
        sec = frappe.form_dict.get("section") or ""
        counts = {}
        for d in SECTION_OF:
            if sec:
                if sec not in SECTION_OF[d] or not section_ok(sec):
                    continue
            else:
                inarea = False
                for x in SECTION_OF[d]:
                    if (AREA.get(x) or "pipeline") == area:
                        inarea = True
                if not inarea:
                    continue
            if available(d):
                try:
                    counts[d] = total(d, {}, None)
                except Exception:
                    counts[d] = None
        frappe.response["message"] = {"counts": counts}

    elif action == "list":
        doctype(dt)
        dcols = cols(dt)
        filters = jsonarg("filters")
        limit = min(int(frappe.form_dict.get("limit") or 50), 200)
        start = int(frappe.form_dict.get("start") or 0)
        order = frappe.form_dict.get("order_by") or "modified desc"
        parts = order.split(" ")
        direction = "asc" if len(parts) > 1 and parts[1].lower() == "asc" else "desc"
        order = real(dt, parts[0] if parts[0] in dcols else "modified") + " " + direction
        clean_filters = {}
        for k in filters:
            if k in dcols:
                clean_filters[k] = filters[k]
        clean_filters = qfilters(dt, clean_filters)
        or_filters = None
        q = frappe.form_dict.get("search")
        if q:
            meta = frappe.get_meta(dt)
            or_filters = [["name", "like", "%" + q + "%"]]
            for c in dcols:
                f = meta.get_field(real(dt, c))
                if f and f.fieldtype in TEXT_TYPES:
                    or_filters.append([real(dt, c), "like", "%" + q + "%"])
        rows = frappe.get_list(dt, fields=qfields(dt, dcols), filters=clean_filters, or_filters=or_filters,
                               order_by=order, limit_start=start, limit_page_length=limit)
        # total honours the user's permissions and the search box (v4 ignored both)
        frappe.response["message"] = {"rows": fixrows(dt, rows), "columns": colinfo(dt),
                                      "total": total(dt, clean_filters, or_filters)}

    elif action == "meta":
        doctype(dt)
        fields = []
        wf = writable_fields(dt)
        for fn in wf:
            f = wf[fn]
            fields.append({"fieldname": f.fieldname, "label": f.label, "type": f.fieldtype,
                           "options": f.options, "reqd": f.reqd, "default": f.default})
        tables = []
        meta = frappe.get_meta(dt)
        for f in meta.fields:
            if f.fieldtype == "Table" and f.reqd:
                tables.append(f.label or f.fieldname)
        frappe.response["message"] = {"dt": dt, "fields": fields, "required_tables": tables,
                                      "can_edit": can_edit(), "autoname": str(meta.autoname or ""),
                                      "read_only": dt in READ_ONLY, "create": create_kind(dt),
                                      "status_kind": skind(dt) or None}

    elif action == "get":
        doctype(dt)
        name = frappe.form_dict.get("name")
        doc = frappe.get_doc(dt, name)
        doc.check_permission("read")
        log = frappe.get_all("Comment", filters={"reference_doctype": dt, "reference_name": name,
                                                 "comment_type": "Info",
                                                 "content": ["like", "Command Center:%"]},
                             fields=["creation", "owner", "content"], order_by="creation desc",
                             limit_page_length=10)
        out = doc.as_dict()
        if skind(dt) == "bool":
            out["status"] = "Active" if out.get("is_active") else "Inactive"
        elif sfield(dt) != "status":
            out["status"] = out.get(sfield(dt))
        # C5: child tables, read-only (first 25 rows, the child's in_list_view columns, max 5)
        tables = []
        for f in frappe.get_meta(dt).fields:
            if f.fieldtype != "Table" or not f.options:
                continue
            rows = out.get(f.fieldname) or []
            tcols = []
            try:
                for cf in frappe.get_meta(f.options).fields:
                    if len(tcols) >= 5:
                        break
                    if cf.in_list_view and cf.fieldtype not in SKIP_FIELD_TYPES:
                        tcols.append({"fieldname": cf.fieldname, "label": cf.label or cf.fieldname,
                                      "type": cf.fieldtype})
            except Exception:
                tcols = []
            trows = []
            for r in rows:
                if len(trows) >= 25:
                    break
                row = {}
                for c in tcols:
                    row[c["fieldname"]] = r.get(c["fieldname"])
                trows.append(row)
            tables.append({"fieldname": f.fieldname, "label": f.label or f.fieldname, "count": len(rows),
                           "columns": tcols, "rows": trows})
        frappe.response["message"] = {"doc": out, "audit": log, "tables": tables,
                                      "read_only": dt in READ_ONLY, "create": create_kind(dt),
                                      "builder": dt in CREATE_VIA_BUILDER, "status_kind": skind(dt) or None,
                                      "editable": can_edit() and doc.docstatus == 0 and dt not in READ_ONLY}

    elif action == "save":
        doctype(dt)
        need_edit()
        if dt in READ_ONLY:
            deny(dt + " records are generated or audit records, so they are read-only here.")
        doc = frappe.get_doc(dt, frappe.form_dict.get("name"))
        doc.check_permission("write")
        if doc.docstatus != 0:
            deny("This document is submitted or cancelled and is read-only here.")
        values = clean(dt, jsonarg("values"))
        changed = []
        for k in values:
            newv = values[k] if values[k] is not None else ""
            if str(doc.get(k) or "") != str(newv):
                changed.append(k + ": " + str(doc.get(k)) + " -> " + str(values[k]))
                doc.set(k, values[k])
        if changed:
            doc.save()
            audit(dt, doc.name, "edited by " + user + " (" + "; ".join(changed)[:900] + ")")
        frappe.response["message"] = {"name": doc.name, "changed": len(changed)}

    elif action == "create":
        doctype(dt)
        need_edit()
        if dt in READ_ONLY:
            deny(dt + " records are generated or audit records, so they can't be created here.")
        if dt in CREATE_VIA_BUILDER:
            deny("Create " + dt.replace("ilL-", "") + " in the Catalog Builder so it's checked and logged.")
        values = jsonarg("values")
        newname = ""
        if "__newname" in values:
            # C7: "prompt"-named doctypes take the typed name, nothing else may set a name
            newname = str(values["__newname"] or "").strip()
            rest = {}
            for k in values:
                if k != "__newname":
                    rest[k] = values[k]
            values = rest
        autoname = str(frappe.get_meta(dt).autoname or "").lower()
        if newname and autoname != "prompt":
            deny(dt + " is named automatically; leave the name out.")
        if autoname == "prompt" and not newname:
            deny("Give the new " + dt.replace("ilL-", "") + " a name.")
        values = clean(dt, values)
        values["doctype"] = dt
        if newname:
            values["__newname"] = newname
            values["name"] = newname
        doc = frappe.get_doc(values)
        doc.check_permission("create")
        doc.insert()
        audit(dt, doc.name, "created by " + user)
        frappe.response["message"] = {"name": doc.name}

    elif action == "overview":
        today = frappe.utils.nowdate()
        in7 = frappe.utils.add_days(today, 7)
        ago2 = frappe.utils.add_days(today, -2)
        ago3 = frappe.utils.add_days(today, -3)
        ago14 = frappe.utils.add_days(today, -14)
        # purchase orders: the team-edited ETA when the purchasing fields are installed, else Required By
        po_date = "schedule_date"
        try:
            if frappe.get_meta("Purchase Order").get_field("ill_eta"):
                po_date = "ill_eta"
        except Exception:
            po_date = "schedule_date"

        sections = []
        for s in SECTIONS:
            if AREA.get(s) != "pipeline":
                continue
            sections.append({"key": s, "label": SECTIONS[s][0], "locked": not section_ok(s),
                             "needs": SECTIONS[s][1]})

        # per doctype: record count and value, grouped by status
        stats = {}
        for d in ALLOWED:
            if not available(d):
                continue
            dcols = cols(d)
            has_status = "status" in dcols
            sf = sfield(d)
            valf = ""
            if d == "Sales Invoice":
                valf = "outstanding_amount"
            elif "grand_total" in dcols:
                valf = "grand_total"
            # v16 dict form first, then the v15 string form
            variants = [[{"COUNT": "*", "as": "n"}], ["count(name) as n"]]
            if valf:
                variants[0].append({"SUM": valf, "as": "v"})
                variants[1].append("sum(" + valf + ") as v")
            statuses = []
            rows = None
            for fields in variants:
                try:
                    if has_status:
                        rows = frappe.get_list(d, fields=[sf] + fields, group_by=sf,
                                               order_by=sf + " asc")
                    else:
                        rows = frappe.get_list(d, fields=fields)
                    break
                except Exception:
                    rows = None
            if rows is not None:
                for r in rows:
                    statuses.append([r.get(sf) or "", int(r.get("n") or 0), float(r.get("v") or 0)])
            else:
                # fallback for Frappe versions that refuse SQL aggregates in get_list:
                # pull the plain columns (capped) and add them up here
                statuses = []
                try:
                    plain = ["name"]
                    if has_status:
                        plain.append(sf)
                    if valf:
                        plain.append(valf)
                    agg = {}
                    order = []
                    for r in frappe.get_list(d, fields=plain, limit_page_length=5000):
                        k = (r.get(sf) or "") if has_status else ""
                        if k not in agg:
                            agg[k] = [k, 0, 0.0]
                            order.append(k)
                        agg[k][1] = agg[k][1] + 1
                        if valf:
                            agg[k][2] = agg[k][2] + float(r.get(valf) or 0)
                    for k in order:
                        statuses.append(agg[k])
                except Exception:
                    statuses = []
            count = 0
            value = 0
            for st in statuses:
                count = count + st[1]
                value = value + st[2]
            stats[d] = {"section": ALLOWED[d][0], "count": count, "value": value,
                        "value_field": valf, "statuses": statuses}

        # "decisions this week": things that are late, expiring or stuck.
        # [id, label, doctype, filters, single status for the drill-down ("" = none), tone]
        defs = [
            ["dr_sla", "Drawing requests past their SLA", "ilL-Document-Request",
             [["status", "in", ["Submitted", "In Progress"]], ["sla_deadline", "<", frappe.utils.now()]], "", "bad"],
            ["qr_waiting", "Quote requests waiting on us", "ilL-Quote-Request",
             [["state", "in", ["REQUESTED", "UNDER_REVIEW"]], ["creation", "<", ago2]], "", "warn"],
            ["oi_waiting", "Order requests waiting on us", "ilL-Order-Intake",
             [["state", "in", ["SUBMITTED", "UNDER_REVIEW"]], ["creation", "<", ago2]], "", "warn"],
            ["ar_pending", "Customer account requests pending", "ilL-Account-Request",
             [["state", "=", "Pending"]], "Pending", "warn"],
            ["quote_expiring", "Quotes expiring within 7 days", "Quotation",
             [["status", "=", "Open"], ["valid_till", "between", [today, in7]]], "Open", "warn"],
            ["so_late", "Open orders past delivery date", "Sales Order",
             [["status", "in", ["To Deliver and Bill", "To Deliver"]], ["delivery_date", "<", today]], "", "bad"],
            ["po_late", "Purchase orders past their date", "Purchase Order",
             [["status", "in", ["To Receive and Bill", "To Receive"]], [po_date, "<", today]], "", "bad"],
            # purchasing (v8): simple filters; the precise versions live in the purchasing board
            ["po_not_sent", "Purchase orders not sent to the vendor", "Purchase Order",
             [["docstatus", "=", 1], ["status", "in", ["To Receive and Bill", "To Receive"]],
              ["ill_vendor_status", "=", "Not sent"]], "", "warn"],
            ["po_unconfirmed", "Purchase orders the vendor hasn't confirmed", "Purchase Order",
             [["docstatus", "=", 1], ["ill_vendor_status", "=", "Sent"], ["ill_sent_on", "<", ago3]], "", "warn"],
            ["sq_expiring", "Supplier quotes expiring within 7 days", "Supplier Quotation",
             [["docstatus", "=", 1], ["status", "=", "Submitted"], ["valid_till", "between", [today, in7]]],
             "Submitted", "warn"],
            ["receipt_no_bill", "Receipts with no vendor bill after 14 days", "Purchase Receipt",
             [["status", "=", "To Bill"], ["posting_date", "<", ago14]], "To Bill", "warn"],
            ["needs_lcv", "Delivered shipments waiting for landed cost", "ilL-Inbound-Shipment",
             [["status", "=", "Delivered"]], "Delivered", "warn"],
            ["mr_late", "Material requests past required date", "Material Request",
             [["status", "in", ["Pending", "Partially Ordered"]], ["schedule_date", "<", today]], "", "warn"],
            ["wo_draft", "Work orders still in Draft", "Work Order",
             [["status", "=", "Draft"]], "Draft", "warn"],
            ["tk_old", "Tickets open more than 2 days", "HD Ticket",
             [["status", "=", "Open"], ["creation", "<", ago2]], "Open", "bad"],
            ["task_late", "Overdue project tasks", "Task",
             [["status", "not in", ["Completed", "Cancelled"]], ["exp_end_date", "<", today]], "", "warn"],
            ["si_overdue", "Overdue invoices", "Sales Invoice",
             [["status", "=", "Overdue"]], "Overdue", "bad"],
        ]
        signals = []
        for sd in defs:
            if not available(sd[2]):
                continue
            try:
                n = total(sd[2], sd[3], None)
            except Exception:
                continue
            signals.append({"id": sd[0], "label": sd[1], "dt": sd[2], "count": n,
                            "status": sd[4], "tone": sd[5]})

        frappe.response["message"] = {"today": today, "sections": sections, "stats": stats,
                                      "signals": signals, "can_edit": can_edit(),
                                      "finance_ok": section_ok("finance")}

    elif action == "feed":
        dts = jsonarg("dts")
        limit = min(int(frappe.form_dict.get("limit") or 40), 100)
        filters = {"comment_type": "Info", "content": ["like", "Command Center:%"]}
        if dts:
            filters["reference_doctype"] = ["in", dts]
        rows = frappe.get_all("Comment", filters=filters,
                              fields=["creation", "owner", "content", "reference_doctype", "reference_name"],
                              order_by="creation desc", limit_page_length=200)
        # one permission-aware query per doctype: keep only records this user can read
        names = {}
        for r in rows:
            d = r["reference_doctype"]
            if d in SECTION_OF and available(d):
                if d not in names:
                    names[d] = []
                if r["reference_name"] not in names[d]:
                    names[d].append(r["reference_name"])
        readable = {}
        for d in names:
            try:
                for x in frappe.get_list(d, filters={"name": ["in", names[d]]}, fields=["name"],
                                         limit_page_length=len(names[d])):
                    readable[d + "|" + x["name"]] = 1
            except Exception:
                pass
        out = []
        for r in rows:
            if len(out) >= limit:
                break
            if (r["reference_doctype"] + "|" + r["reference_name"]) in readable:
                out.append(r)
        frappe.response["message"] = {"rows": out}

    elif action == "stages":
        # Lanes for the pipeline stages, in one call: Design (projects, fixture schedules, drawing
        # requests, reviews), Quotes (quote requests, offers), Sales orders (order intakes) and
        # Service (account requests), plus the project/schedule/quote/order links on recent tickets.
        # Each list is permission-aware; a doctype that is missing or unreadable comes back empty
        # and is named in "missing".
        today = frappe.utils.nowdate()
        cutoff = frappe.utils.add_days(today, -30)
        missing = []

        def fetch(d, fields, filters=None, or_filters=None, order_by="modified desc", limit=500):
            if not available(d):
                missing.append(d)
                return []
            meta = frappe.get_meta(d)
            keep = []
            for f in fields:
                if f in STD_COLS or meta.get_field(f):
                    keep.append(f)
            try:
                return frappe.get_list(d, fields=keep, filters=filters or {}, or_filters=or_filters,
                                       order_by=order_by, limit_page_length=limit)
            except Exception:
                missing.append(d)
                return []

        def recent(field, done):
            # still open, or finished within the last 30 days
            return [[field, "not in", done], ["modified", ">=", cutoff]]

        schedules = fetch("ilL-Project-Fixture-Schedule",
                          ["name", "schedule_name", "ill_project", "customer", "status", "version", "is_locked",
                           "sales_order", "status_note", "owner", "creation", "modified"],
                          or_filters=recent("status", ["CLOSED"]))
        snames = []
        pnames = []
        for r in schedules:
            snames.append(r["name"])
            if r.get("ill_project") and r["ill_project"] not in pnames:
                pnames.append(r["ill_project"])
        lines = {}
        if snames:
            try:
                for r in frappe.get_all("ilL-Child-Fixture-Schedule-Line",
                                        filters={"parent": ["in", snames],
                                                 "parenttype": "ilL-Project-Fixture-Schedule"},
                                        fields=["parent"], limit_page_length=20000):
                    lines[r["parent"]] = (lines.get(r["parent"]) or 0) + 1
            except Exception:
                lines = {}
        for r in schedules:
            r["lines"] = lines.get(r["name"]) or 0
        pfields = ["name", "project_name", "customer", "status", "architect", "lighting_designer",
                   "general_contractor", "location", "erp_project", "estimated_start_date", "modified"]
        projects = fetch("ilL-Project", pfields, filters={"status": ["in", ["ACTIVE", "ON_HOLD"]]})
        have = []
        for r in projects:
            have.append(r["name"])
        extra = []
        for n in pnames:
            if n not in have:
                extra.append(n)
        if extra:
            projects = projects + fetch("ilL-Project", pfields, filters={"name": ["in", extra]})

        doc_requests = fetch("ilL-Document-Request",
                             ["name", "request_type", "status", "priority", "fixture_schedule", "sales_order", "project",
                              "requester_customer", "owner_customer", "assigned_to", "sla_deadline",
                              "requested_due_date", "required_for_manufacturing", "fixture_or_product_text",
                              "completed_on", "creation", "modified"],
                             filters={"status": ["not in", ["Closed", "Cancelled"]]},
                             or_filters=[["status", "!=", "Completed"], ["modified", ">=", cutoff]])
        rnames = []
        for r in doc_requests:
            rnames.append(r["name"])
        reviews = []
        if rnames:
            reviews = fixrows("ilL-Drawing-Review", fetch(
                "ilL-Drawing-Review", ["name", "request", "revision", "decision", "reviewed_by", "reviewed_on",
                                       "note", "creation"],
                filters={"request": ["in", rnames]}, order_by="creation desc"))

        quote_requests = fixrows("ilL-Quote-Request", fetch(
            "ilL-Quote-Request", ["name", "schedule", "project", "customer", "state", "assigned_to", "due_date",
                                  "latest_offer", "latest_issued_offer", "ill_next_action_by", "requested_by",
                                  "owner", "creation", "modified"],
            filters={"state": ["!=", "DRAFT"]}, or_filters=recent("state", ["CLOSED"])))
        offers = fixrows("ilL-Quote-Offer", fetch(
            "ilL-Quote-Offer", ["name", "quotation", "quote_request", "schedule", "customer", "state", "valid_until",
                                "issued_on", "sales_order", "responded_on", "response_note", "creation", "modified"],
            filters={"state": ["not in", ["SUPERSEDED", "CANCELLED"]],
                     "modified": [">=", frappe.utils.add_days(today, -120)]}))
        intakes = fixrows("ilL-Order-Intake", fetch(
            "ilL-Order-Intake", ["name", "sales_order", "schedule", "customer", "state", "assigned_to", "due_date",
                                 "ill_next_action_by", "customer_message", "requested_by", "creation", "modified"],
            or_filters=recent("state", ["APPROVED", "REJECTED", "WITHDRAWN"])))
        account_requests = fixrows("ilL-Account-Request", fetch(
            "ilL-Account-Request", ["name", "request_type", "customer", "requested_by", "state", "assigned_to",
                                    "staff_note", "reviewed_on", "creation", "modified"],
            or_filters=recent("state", ["Approved", "Rejected", "Resolved"])))
        tickets = fetch("HD Ticket", ["name", "ill_project", "ill_fixture_schedule", "ill_quotation",
                                      "ill_sales_order", "ill_sales_invoice", "priority", "agent_group",
                                      "ticket_type", "status"],
                        or_filters=recent("status", ["Resolved", "Closed"]), limit=1000)

        frappe.response["message"] = {
            "today": today, "can_edit": can_edit(), "missing": missing,
            "projects": fixrows("ilL-Project", projects), "schedules": schedules,
            "doc_requests": doc_requests, "reviews": reviews, "quote_requests": quote_requests,
            "offers": offers, "intakes": intakes, "account_requests": account_requests, "tickets": tickets,
        }

    elif action == "assign":
        # add/remove owners on a record (help desk tickets from the Inbox, drawing and quote requests)
        # the way the desk does it: one open ToDo per owner on the record. Editors only.
        doctype(dt)
        need_edit()
        name = frappe.form_dict.get("name")
        doc = frappe.get_doc(dt, name)
        doc.check_permission("write")
        add = jsonarg("add")
        remove = jsonarg("remove")
        if not add and not remove:
            deny("Pick someone to add or remove.")
        title = str(doc.get("subject") or doc.get("title") or name)
        done_add = []
        done_remove = []
        for u in add:
            if not frappe.db.exists("User", {"name": u, "enabled": 1}):
                deny(str(u) + " isn't an active user.")
            if frappe.get_all("ToDo", filters={"reference_type": dt, "reference_name": name,
                                               "allocated_to": u, "status": "Open"}, fields=["name"],
                              limit_page_length=1):
                continue
            frappe.get_doc({"doctype": "ToDo", "status": "Open", "allocated_to": u, "assigned_by": user,
                            "reference_type": dt, "reference_name": name,
                            "description": str(title)[:500]}).insert()
            done_add.append(u)
        for u in remove:
            for t in frappe.get_list("ToDo", filters={"reference_type": dt, "reference_name": name,
                                                      "allocated_to": u, "status": "Open"},
                                     fields=["name"], limit_page_length=20):
                td = frappe.get_doc("ToDo", t["name"])
                td.status = "Cancelled"
                try:
                    td.save()
                except Exception:
                    deny("Your ERPNext user can't close " + str(u) + "'s to-do on " + str(name)
                         + ". Unassign them in Helpdesk or the desk instead.")
                if u not in done_remove:
                    done_remove.append(u)
        if done_add or done_remove:
            bits = []
            if done_add:
                bits.append("assigned " + ", ".join(done_add))
            if done_remove:
                bits.append("unassigned " + ", ".join(done_remove))
            audit(dt, name, "; ".join(bits) + " by " + user)
        frappe.response["message"] = {"name": name, "added": done_add, "removed": done_remove}

    elif action == "note":
        # leave a "Command Center:" comment on a record after a change made from the page
        doctype(dt)
        need_edit()
        name = frappe.form_dict.get("name")
        doc = frappe.get_doc(dt, name)
        doc.check_permission("write")
        text = str(frappe.form_dict.get("text") or "").strip()
        if not text:
            deny("Nothing to note.")
        audit(dt, name, text.replace("<", "&lt;")[:900] + " (" + user + ")")
        frappe.response["message"] = {"name": name}

    elif action.startswith("agenda_"):
        # ---- weekly meeting agenda (doctypes ilL-Meeting-Agenda / ilL-Meeting-Agenda-Item) ----
        # Same rules as the rest: Viewer reads, Editor writes, ERPNext permissions decide the rest.
        # Removing an agenda item is the one delete the gateway does; it only ever touches
        # agenda items, never the records they link to.
        AG = "ilL-Meeting-Agenda"
        AI = "ilL-Meeting-Agenda-Item"
        ITEM_FIELDS = ["name", "item_title", "details", "status", "presenter", "sort_order", "outcome",
                       "reference_doctype", "reference_name", "carried_from", "todo_names", "owner", "creation"]
        ITEM_EDITABLE = ["item_title", "details", "presenter", "status", "outcome"]
        MEETING_EDITABLE = ["title", "meeting_date", "status", "notes"]

        if not frappe.db.exists("DocType", AG):
            deny("The meeting agenda isn't installed on this site yet. It arrives with the next app deploy.")

        def agenda_doc(name, ptype):
            if not name:
                deny("Pick a meeting first.")
            d = frappe.get_doc(AG, name)
            d.check_permission(ptype)
            return d

        def item_doc(name, ptype):
            d = frappe.get_doc(AI, name)
            d.check_permission(ptype)
            return d

        def only(values, keys):
            out = {}
            for k in values:
                if k not in keys:
                    deny("Not editable here: " + k)
                out[k] = values[k]
            return out

        def items_of(agenda):
            return frappe.get_list(AI, filters={"agenda": agenda}, fields=ITEM_FIELDS,
                                   order_by="sort_order asc, creation asc", limit_page_length=500)

        def ref_rows(items):
            # live columns of each linked record the user may read (one query per doctype)
            want = {}
            for it in items:
                d = it.get("reference_doctype")
                if d and it.get("reference_name") and d in SECTION_OF and available(d):
                    if d not in want:
                        want[d] = []
                    if it["reference_name"] not in want[d]:
                        want[d].append(it["reference_name"])
            refs = {}
            columns = {}
            for d in want:
                try:
                    for r in fixrows(d, frappe.get_list(d, fields=qfields(d, cols(d)),
                                                        filters={"name": ["in", want[d]]},
                                                        limit_page_length=len(want[d]))):
                        refs[d + "|" + r["name"]] = r
                    columns[d] = colinfo(d)
                except Exception:
                    pass
            return {"refs": refs, "columns": columns}

        def made_todos(it):
            # "list"/"dict" aren't sandbox builtins: keep only entries that behave like {name: ...}
            out = []
            try:
                v = json.loads(it.get("todo_names") or "[]")
                for t in v:
                    try:
                        if t.get("name"):
                            out.append(t)
                    except Exception:
                        pass
            except Exception:
                pass
            return out

        def todo_live(items):
            # current status of the to-dos made from these items, where the user may read them
            names = []
            for it in items:
                for t in made_todos(it):
                    if t.get("name") and t["name"] not in names:
                        names.append(t["name"])
            out = {}
            if names and available("ToDo"):
                try:
                    for r in frappe.get_list("ToDo", filters={"name": ["in", names]},
                                             fields=["name", "status", "date", "allocated_to"],
                                             limit_page_length=len(names)):
                        out[r["name"]] = r
                except Exception:
                    pass
            return out

        def html(t):
            return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        def date_label(agenda):
            return str(frappe.db.get_value(AG, agenda, "meeting_date") or agenda)

        if action == "agenda_list":
            meetings = frappe.get_list(AG, fields=["name", "title", "meeting_date", "status"],
                                       order_by="meeting_date desc, creation desc", limit_page_length=60)
            names = []
            for m in meetings:
                names.append(m["name"])
                m["items"] = 0
                m["open"] = 0
            if names:
                tally = {}
                for it in frappe.get_list(AI, filters={"agenda": ["in", names]}, fields=["agenda", "status"],
                                          limit_page_length=5000):
                    if it["agenda"] not in tally:
                        tally[it["agenda"]] = [0, 0]
                    tally[it["agenda"]][0] = tally[it["agenda"]][0] + 1
                    if it["status"] == "Open":
                        tally[it["agenda"]][1] = tally[it["agenda"]][1] + 1
                for m in meetings:
                    if m["name"] in tally:
                        m["items"] = tally[m["name"]][0]
                        m["open"] = tally[m["name"]][1]
            frappe.response["message"] = {"meetings": meetings, "today": frappe.utils.nowdate(),
                                          "can_edit": can_edit() and can(AG, "create") and can(AI, "create")}

        elif action == "agenda_get":
            ag = agenda_doc(frappe.form_dict.get("name"), "read")
            items = items_of(ag.name)
            live = ref_rows(items)
            frappe.response["message"] = {
                "agenda": {"name": ag.name, "title": ag.title, "meeting_date": str(ag.meeting_date or ""),
                           "status": ag.status, "notes": ag.notes or "", "modified": str(ag.modified)},
                "items": items, "refs": live["refs"], "columns": live["columns"], "todos": todo_live(items),
                "can_edit": can_edit() and bool(ag.has_permission("write")),
            }

        elif action == "agenda_create":
            need_edit()
            values = jsonarg("values")
            date = values.get("meeting_date") or frappe.utils.nowdate()
            ag = frappe.get_doc({"doctype": AG, "title": values.get("title") or "Weekly meeting",
                                 "meeting_date": date, "status": "Open"})
            ag.insert()
            carried = 0
            if values.get("carry"):
                # bring forward everything still Open on the most recent earlier meeting
                prev = frappe.get_list(AG, filters={"meeting_date": ["<=", date], "name": ["!=", ag.name]},
                                       fields=["name"], order_by="meeting_date desc, creation desc",
                                       limit_page_length=1)
                if prev:
                    for it in items_of(prev[0]["name"]):
                        if it["status"] != "Open":
                            continue
                        carried = carried + 1
                        frappe.get_doc({"doctype": AI, "agenda": ag.name, "item_title": it["item_title"],
                                        "details": it["details"], "presenter": it["presenter"],
                                        "reference_doctype": it["reference_doctype"],
                                        "reference_name": it["reference_name"], "sort_order": carried,
                                        "carried_from": it["name"], "status": "Open"}).insert()
                        old = item_doc(it["name"], "write")
                        old.status = "Carried over"
                        old.save()
            frappe.response["message"] = {"name": ag.name, "carried": carried}

        elif action == "agenda_save_meeting":
            need_edit()
            ag = agenda_doc(frappe.form_dict.get("name"), "write")
            values = only(jsonarg("values"), MEETING_EDITABLE)
            for k in values:
                ag.set(k, values[k])
            ag.save()
            frappe.response["message"] = {"name": ag.name}

        elif action == "agenda_add":
            need_edit()
            ag = agenda_doc(frappe.form_dict.get("agenda"), "read")
            values = only(jsonarg("values"), ITEM_EDITABLE + ["reference_doctype", "reference_name"])
            rdt = values.get("reference_doctype") or ""
            rname = values.get("reference_name") or ""
            if rdt or rname:
                if not (rdt and rname):
                    deny("A linked record needs both its type and its ID.")
                doctype(rdt)   # allowed in the Command Center, section unlocked, readable
                if not frappe.get_list(rdt, filters={"name": rname}, fields=["name"], limit_page_length=1):
                    deny(rdt + " " + rname + " doesn't exist or you can't see it.")
                dup = frappe.get_list(AI, filters={"agenda": ag.name, "reference_doctype": rdt,
                                                   "reference_name": rname}, fields=["name"], limit_page_length=1)
                if dup:
                    frappe.response["message"] = {"name": dup[0]["name"], "duplicate": True}
                    return
            title = str(values.get("item_title") or "").strip() or (rdt + " " + rname).strip()
            if not title:
                deny("Give the item a title.")
            last = 0
            for it in items_of(ag.name):
                if (it["sort_order"] or 0) > last:
                    last = it["sort_order"] or 0
            it = frappe.get_doc({"doctype": AI, "agenda": ag.name, "item_title": title[:140],
                                 "details": values.get("details") or "", "presenter": values.get("presenter") or None,
                                 "reference_doctype": rdt or None, "reference_name": rname or None,
                                 "status": "Open", "sort_order": last + 1})
            it.insert()
            if rdt and rname:
                audit(rdt, rname, "added to the " + date_label(ag.name) + " meeting agenda by " + user)
            frappe.response["message"] = {"name": it.name}

        elif action == "agenda_update":
            need_edit()
            it = item_doc(frappe.form_dict.get("name"), "write")
            values = only(jsonarg("values"), ITEM_EDITABLE)
            was = it.status
            was_outcome = str(it.outcome or "")
            for k in values:
                it.set(k, values[k])
            it.save()
            # the decision lands on the linked record's timeline: once when the item is marked
            # discussed, and again only if its outcome is changed afterwards
            became = it.status == "Discussed" and was != "Discussed"
            reworded = it.status == "Discussed" and bool(it.outcome) and str(it.outcome or "") != was_outcome
            if it.reference_doctype and it.reference_name and (became or reworded):
                note = "discussed at the " + date_label(it.agenda) + " meeting"
                if it.outcome:
                    note = note + ": " + str(it.outcome)[:700]
                audit(it.reference_doctype, it.reference_name, note)
            frappe.response["message"] = {"name": it.name}

        elif action == "agenda_order":
            need_edit()
            ag = agenda_doc(frappe.form_dict.get("agenda"), "read")
            names = jsonarg("names")
            i = 0
            for n in names:
                i = i + 1
                it = item_doc(n, "write")
                if it.agenda != ag.name:
                    continue
                if (it.sort_order or 0) != i:
                    it.sort_order = i
                    it.save()
            frappe.response["message"] = {"ordered": i}

        elif action == "agenda_todo":
            need_edit()
            if not (frappe.db.exists("DocType", "ToDo") and can("ToDo", "create")):
                deny("Your ERPNext user can't create to-dos.")
            it = item_doc(frappe.form_dict.get("name"), "write")
            values = jsonarg("values")
            title = str(values.get("title") or "").strip()
            notes = str(values.get("notes") or "").strip()
            owners = values.get("owners") or []
            priority = values.get("priority") or "Medium"
            if not title:
                deny("Give the to-do a title.")
            if not owners:
                deny("Pick at least one owner.")
            if priority not in ["High", "Medium", "Low"]:
                deny("Priority must be High, Medium or Low.")
            for o in owners:
                if not frappe.db.exists("User", {"name": o, "enabled": 1}):
                    deny(str(o) + " isn't an active user.")
            # the to-do points at what the item is about, or back at the agenda item itself
            ref_dt = AI
            ref_name = it.name
            if it.reference_doctype and it.reference_name:
                ref_dt = it.reference_doctype
                ref_name = it.reference_name
            desc = "<p><b>" + html(title) + "</b></p>"
            if notes:
                desc = desc + "<p>" + html(notes) + "</p>"
            desc = desc + "<p>From the " + html(date_label(it.agenda)) + " meeting: " + html(it.item_title) + "</p>"
            desc = desc + "<p>[meeting] Owners: " + ", ".join(owners) + "</p>"
            made = []
            for o in owners:
                td = {"doctype": "ToDo", "status": "Open", "allocated_to": o, "priority": priority,
                      "assigned_by": user, "description": desc,
                      "reference_type": ref_dt, "reference_name": ref_name}
                if values.get("date"):
                    td["date"] = values.get("date")
                doc = frappe.get_doc(td)
                doc.insert()
                made.append({"name": doc.name, "owner": o, "title": title[:140], "date": values.get("date") or ""})
            it.todo_names = json.dumps(made_todos(it) + made)
            it.save()
            frappe.response["message"] = {"todos": made}

        elif action == "agenda_remove":
            need_edit()
            it = item_doc(frappe.form_dict.get("name"), "delete")
            it.delete()
            frappe.response["message"] = {"removed": 1}

        else:
            deny("Unknown action.")

    else:
        deny("Unknown action.")


main()
