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
#   * Never submits, cancels or deletes (the only delete is removing an agenda item).
#     Submitted docs (docstatus 1/2) are read-only.
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
                if d and it.get("reference_name") and d in ALLOWED and available(d):
                    if d not in want:
                        want[d] = []
                    if it["reference_name"] not in want[d]:
                        want[d].append(it["reference_name"])
            refs = {}
            columns = {}
            for d in want:
                try:
                    for r in frappe.get_list(d, fields=cols(d), filters={"name": ["in", want[d]]},
                                             limit_page_length=len(want[d])):
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
