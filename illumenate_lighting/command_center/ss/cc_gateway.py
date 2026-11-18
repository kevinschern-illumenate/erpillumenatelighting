# Server Script: "ilL Command Center Gateway"
#   Script Type: API      API Method: ill_cc_gateway      Allow Guest: NO
#
# One role-gated endpoint the Command Center page uses to list, inspect, create and edit
# records in every pipeline doctype, plus the aggregates for the Executive page.
#
# Call:  /api/method/ill_cc_gateway   (POST, JSON body, CSRF token like any desk call)
#   action=config                      -> what THIS user may see/do
#   action=counts                      -> record count per available doctype (workbench landing)
#   action=list   dt, filters, search, limit, start, order_by
#   action=meta   dt                   -> editable form fields (so the UI builds forms itself)
#   action=get    dt, name             -> full doc + recent audit entries
#   action=save   dt, name, values     -> update an existing DRAFT/non-submitted doc
#   action=create dt, values           -> insert a new doc (draft)
#   action=overview                    -> per-stage counts/values by status + "decision" signals
#   action=feed   [dts], [limit]       -> recent Command Center changes the user may see
#
# Guarantees
#   * Needs role "Command Center Viewer" (reads) / "Command Center Editor" (writes).
#   * Each section additionally needs its own role when listed in SECTIONS below.
#   * Acts as the signed-in user (no ignore_permissions on data), so ERPNext's own
#     role/permission rules remain the final authority.
#   * Never submits, cancels or deletes. Submitted docs (docstatus 1/2) are read-only.
#   * Only doctypes in ALLOWED can be touched; only non-system fields can be written.
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
    SECTIONS = {
        "sales": ("Sales", ""), "quotes": ("Quotes", ""), "orders": ("Orders", ""),
        "requests": ("Requests", ""), "purchasing": ("Purchasing", ""),
        "manufacturing": ("Manufacturing", ""), "shipping": ("Shipping", ""),
        "service": ("Service", ""), "projects": ("Projects & tasks", ""),
        "finance": ("Finance", "Command Center Finance"),
    }

    # doctype -> (section, [preferred list columns]).  Columns missing on the site are dropped.
    ALLOWED = {
        "Customer":          ("sales",         ["name", "customer_name", "customer_group", "territory", "modified"]),
        "Quotation":         ("quotes",        ["name", "party_name", "status", "grand_total", "transaction_date", "modified"]),
        "ilL-Quote-Request": ("requests",      ["name", "status", "owner", "creation", "modified"]),
        "ilL-Quote-Offer":   ("quotes",        ["name", "status", "owner", "creation", "modified"]),
        "Sales Order":       ("orders",        ["name", "customer", "status", "grand_total", "delivery_date", "modified"]),
        "ilL-Order-Intake":  ("requests",      ["name", "status", "owner", "creation", "modified"]),
        "ilL-Order-Change":  ("orders",        ["name", "status", "owner", "creation", "modified"]),
        "ilL-Document-Request": ("requests",   ["name", "status", "owner", "creation", "modified"]),
        "ilL-Account-Request":  ("requests",   ["name", "status", "owner", "creation", "modified"]),
        "Material Request":  ("purchasing",    ["name", "material_request_type", "status", "schedule_date", "modified"]),
        "Purchase Order":    ("purchasing",    ["name", "supplier", "status", "grand_total", "schedule_date", "modified"]),
        "Work Order":        ("manufacturing", ["name", "production_item", "status", "qty", "planned_start_date", "modified"]),
        "Delivery Note":     ("shipping",      ["name", "customer", "status", "posting_date", "modified"]),
        "Sales Invoice":     ("finance",       ["name", "customer", "status", "grand_total", "outstanding_amount", "due_date", "modified"]),
        "HD Ticket":         ("service",       ["name", "subject", "status", "priority", "ticket_type", "modified"]),
        "Project":           ("projects",      ["name", "project_name", "status", "percent_complete", "expected_end_date", "modified"]),
        "Task":              ("projects",      ["name", "subject", "status", "priority", "project", "exp_end_date", "modified"]),
        "ToDo":              ("projects",      ["name", "description", "status", "allocated_to", "date", "modified"]),
    }

    STD_COLS = {"name": ("ID", "Data"), "owner": ("Created by", "Link"),
                "creation": ("Created", "Datetime"), "modified": ("Modified", "Datetime")}

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

    def available(dt):
        # allowed + exists on this site + the user may read it in ERPNext
        key = dt + "|avail"
        if key not in memo:
            memo[key] = (dt in ALLOWED and section_ok(ALLOWED[dt][0])
                         and bool(frappe.db.exists("DocType", dt)) and can(dt, "read"))
        return memo[key]

    def doctype(dt):
        if dt not in ALLOWED:
            deny("That doctype isn't available in the Command Center.")
        if not section_ok(ALLOWED[dt][0]):
            deny("You don't have access to the " + SECTIONS[ALLOWED[dt][0]][0] + " section.")
        if not frappe.db.exists("DocType", dt):
            deny(dt + " doesn't exist on this site.")
        if not can(dt, "read"):
            deny("Your ERPNext user can't read " + dt + ".")
        return ALLOWED[dt][0]

    def can_edit():
        return EDIT_ROLE in roles

    def need_edit():
        if not can_edit():
            deny("You have view-only access. Ask Kevin for the Command Center Editor role.")

    def cols(dt):
        meta = frappe.get_meta(dt)
        out = []
        for c in ALLOWED[dt][1]:
            if c in STD_COLS or meta.get_field(c):
                out.append(c)
        return out

    def colinfo(dt):
        meta = frappe.get_meta(dt)
        info = []
        for c in cols(dt):
            if c in STD_COLS:
                info.append({"fieldname": c, "label": STD_COLS[c][0], "type": STD_COLS[c][1]})
            else:
                f = meta.get_field(c)
                info.append({"fieldname": c, "label": f.label or c, "type": f.fieldtype})
        return info

    def writable_fields(dt):
        out = {}
        for f in frappe.get_meta(dt).fields:
            if f.fieldtype in SKIP_FIELD_TYPES or f.read_only or f.hidden or f.fieldname in BLOCKED_WRITE:
                continue
            out[f.fieldname] = f
        return out

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
                             "needs": SECTIONS[s][1]})
        dts = {}
        for d in ALLOWED:
            if available(d):
                dts[d] = {"section": ALLOWED[d][0], "columns": colinfo(d),
                          "can_create": can_edit() and can(d, "create")}
        frappe.response["message"] = {"user": user, "can_edit": can_edit(), "sections": sections,
                                      "doctypes": dts, "today": frappe.utils.nowdate()}

    elif action == "counts":
        counts = {}
        for d in ALLOWED:
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
        order = (parts[0] if parts[0] in dcols else "modified") + " " + direction
        clean_filters = {}
        for k in filters:
            if k in dcols:
                clean_filters[k] = filters[k]
        or_filters = None
        q = frappe.form_dict.get("search")
        if q:
            meta = frappe.get_meta(dt)
            or_filters = [["name", "like", "%" + q + "%"]]
            for c in dcols:
                f = meta.get_field(c)
                if f and f.fieldtype in TEXT_TYPES:
                    or_filters.append([c, "like", "%" + q + "%"])
        rows = frappe.get_list(dt, fields=dcols, filters=clean_filters, or_filters=or_filters,
                               order_by=order, limit_start=start, limit_page_length=limit)
        # total honours the user's permissions and the search box (v4 ignored both)
        frappe.response["message"] = {"rows": rows, "columns": colinfo(dt),
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
        for f in frappe.get_meta(dt).fields:
            if f.fieldtype == "Table" and f.reqd:
                tables.append(f.label or f.fieldname)
        frappe.response["message"] = {"dt": dt, "fields": fields, "required_tables": tables,
                                      "can_edit": can_edit()}

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
        frappe.response["message"] = {"doc": doc.as_dict(), "audit": log,
                                      "editable": can_edit() and doc.docstatus == 0}

    elif action == "save":
        doctype(dt)
        need_edit()
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
        values = clean(dt, jsonarg("values"))
        values["doctype"] = dt
        doc = frappe.get_doc(values)
        doc.check_permission("create")
        doc.insert()
        audit(dt, doc.name, "created by " + user)
        frappe.response["message"] = {"name": doc.name}

    elif action == "overview":
        today = frappe.utils.nowdate()
        in7 = frappe.utils.add_days(today, 7)
        ago2 = frappe.utils.add_days(today, -2)

        sections = []
        for s in SECTIONS:
            sections.append({"key": s, "label": SECTIONS[s][0], "locked": not section_ok(s),
                             "needs": SECTIONS[s][1]})

        # per doctype: record count and value, grouped by status
        stats = {}
        for d in ALLOWED:
            if not available(d):
                continue
            dcols = cols(d)
            has_status = "status" in dcols
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
                        rows = frappe.get_list(d, fields=["status"] + fields, group_by="status",
                                               order_by="status asc")
                    else:
                        rows = frappe.get_list(d, fields=fields)
                    break
                except Exception:
                    rows = None
            if rows is not None:
                for r in rows:
                    statuses.append([r.get("status") or "", int(r.get("n") or 0), float(r.get("v") or 0)])
            else:
                # fallback for Frappe versions that refuse SQL aggregates in get_list:
                # pull the plain columns (capped) and add them up here
                statuses = []
                try:
                    plain = ["name"]
                    if has_status:
                        plain.append("status")
                    if valf:
                        plain.append(valf)
                    agg = {}
                    order = []
                    for r in frappe.get_list(d, fields=plain, limit_page_length=5000):
                        k = (r.get("status") or "") if has_status else ""
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
            ["quote_expiring", "Quotes expiring within 7 days", "Quotation",
             [["status", "=", "Open"], ["valid_till", "between", [today, in7]]], "Open", "warn"],
            ["so_late", "Open orders past delivery date", "Sales Order",
             [["status", "in", ["To Deliver and Bill", "To Deliver"]], ["delivery_date", "<", today]], "", "bad"],
            ["po_late", "Purchase orders past their date", "Purchase Order",
             [["status", "in", ["To Receive and Bill", "To Receive"]], ["schedule_date", "<", today]], "", "bad"],
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
            if d in ALLOWED and available(d):
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

    else:
        deny("Unknown action.")


main()
