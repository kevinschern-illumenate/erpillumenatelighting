import json, sys
from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safe_globals
from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem
class D(dict):
    __getattr__=dict.get
# per-doctype fake meta for the v8 ilLumenate cases: {dt: {"fields": [...], "title_field", "autoname"}}
META={}
def F(fn,ft="Data",**k): return D(dict(dict(fieldname=fn,label=fn.replace("_"," ").title(),fieldtype=ft,read_only=0,hidden=0,options=None,reqd=0,default=None),**k))
class Meta:
    def __init__(s,dt):
        x=META.get(dt) or {}
        s.dt=dt; s.title_field=x.get("title_field"); s.autoname=x.get("autoname","")
        s.fields=x["fields"] if "fields" in x else [D(fieldname="status",label="Status",fieldtype="Select",read_only=0,hidden=0,options="Open\nDone",reqd=0,default=None),D(fieldname="subject",label="Subject",fieldtype="Data",read_only=0,hidden=0,options=None,reqd=1,default=None)]
    def get_field(s,c):
        for f in s.fields:
            if f.fieldname==c: return f
        if s.dt in META: return None
        return D(label=c.title(),fieldtype="Data") if c in ("grand_total","modified","customer","exp_end_date","project","priority","valid_till","state","schedule","assigned_to","ill_project","ill_fixture_schedule","schedule_name","request_type") else None
class Doc:
    docstatus=0; name="T-1"
    def __init__(s,v=None): s.v=dict(v or {}); s.v.setdefault("status","Open")
    def has_permission(s,p): return True
    def check_permission(s,p): pass
    def get(s,k): return s.v.get(k)
    def set(s,k,x): s.v[k]=x
    def save(s): saved.append(dict(s.v))
    def insert(s,**k):
        s.name="T-NEW"
        if s.v.get("doctype")=="ToDo": TODOS.append(dict(s.v))
        CREATED.append(dict(s.v))
        return s
    def as_dict(s): return s.v
saved=[]
TODOS=[]
CREATED=[]
DOCS={}  # (dt, name) -> values for "get"
CALLS=[]
# in-memory agenda store (ilL-Meeting-Agenda / ilL-Meeting-Agenda-Item) for the agenda_* actions
AGD="ilL-Meeting-Agenda"; AGI="ilL-Meeting-Agenda-Item"
STORE={AGD:{},AGI:{}}; AUDIT=[]; SEQ=[0]
class SDoc:
    def __init__(s,v):
        object.__setattr__(s,"v",dict(v))
    def __getattr__(s,k):
        if k=="v": raise AttributeError(k)
        return s.v.get(k)
    def __setattr__(s,k,x): s.v[k]=x
    def get(s,k): return s.v.get(k)
    def set(s,k,x): s.v[k]=x
    def has_permission(s,p): return True
    def check_permission(s,p): pass
    def insert(s,**k):
        dt=s.v["doctype"]
        if dt=="Comment": AUDIT.append(s.v["reference_doctype"]+" "+s.v["reference_name"]+": "+s.v["content"]); return s
        SEQ[0]+=1; s.v["name"]=("MTG-%d" if dt==AGD else "AI-%d")%SEQ[0]; s.v.setdefault("creation","2026-11-17 10:00:%02d"%SEQ[0])
        s.v.setdefault("modified","x"); STORE[dt][s.v["name"]]=s; return s
    def save(s): STORE[s.v["doctype"]][s.v["name"]]=s
    def delete(s): del STORE[s.v["doctype"]][s.v["name"]]
def store_match(v,flt):
    for k,c in (flt or {}).items():
        x=v.get(k)
        if isinstance(c,list):
            op,val=c
            if op=="in" and x not in val: return False
            if op=="!=" and x==val: return False
            if op=="<=" and not (str(x)<=str(val)): return False
        elif x!=c: return False
    return True
def store_list(dt,k):
    rows=[d.v for d in STORE[dt].values() if store_match(d.v,k.get("filters"))]
    key="meeting_date" if dt==AGD else "sort_order"
    rows.sort(key=lambda r:(str(r.get(key) or 0).zfill(12),r.get("creation","")),reverse=dt==AGD)
    return [{f:r.get(f) for f in k.get("fields",["name"])} for r in rows][:k.get("limit_page_length") or 9999]
FALLBACK=False
V16=True
def run(user, roles, form):
    resp={}
    def get_all(dt,**k):
        if dt=="Has Role": return [{"role":r} for r in roles]
        if dt=="Comment": return [{"creation":"x","owner":"a","content":"Command Center: z","reference_doctype":"Task","reference_name":"T-1"}]
        if dt=="ilL-Child-Fixture-Schedule-Line": return [{"parent":"S-1"},{"parent":"S-1"}]
        if dt=="ToDo": return [{"name":"TD-X"}] if k.get("filters",{}).get("allocated_to")=="dup@x" else []
        return []
    def get_list(dt,**k):
        if dt in STORE: return store_list(dt,k)
        f=k.get("fields",[])
        CALLS.append((dt,f,k.get("filters"),k.get("order_by"),k.get("group_by")))
        if dt=="ilL-Project-Fixture-Schedule" and "schedule_name" in f: return [{"name":"S-1","status":"READY","ill_project":"P-9"}]
        if dt=="ToDo" and k.get("filters",{}).get("allocated_to"): return [{"name":"TD-OLD"}]
        if "state" in f and not any(isinstance(x,dict) or "(" in str(x) for x in f): return [{"name":"QR-1","state":"REQUESTED"}]
        # emulate Frappe: v16 accepts aggregates only as dicts, v15 only as strings
        strs = [x for x in f if isinstance(x, str) and "(" in x]; dicts = [x for x in f if isinstance(x, dict)]
        if (strs or dicts) and FALLBACK: raise Exception("aggregates refused")
        if strs and V16: raise Exception("SQL functions are not allowed as strings in SELECT")
        if dicts and not V16: raise Exception("Invalid field")
        if (strs or dicts) and len(f)==1: return [{"total":3}]
        if strs or dicts: return [{"status":"Open","n":2,"v":100.0},{"status":"Done","n":1,"v":5}]
        return [{"name":"T-1","status":"Open"}]
    def throw(m): raise Exception(m)
    def get_doc(*a):
        if isinstance(a[0],dict) and a[0].get("doctype") in STORE or isinstance(a[0],dict) and a[0].get("doctype")=="Comment": return SDoc(a[0])
        if isinstance(a[0],str) and a[0] in STORE:
            if a[1] not in STORE[a[0]]: raise Exception(a[0]+" "+str(a[1])+" not found")
            return STORE[a[0]][a[1]]
        if isinstance(a[0],str) and len(a)>1 and (a[0],a[1]) in DOCS: return Doc(DOCS[(a[0],a[1])])
        return Doc(a[0] if isinstance(a[0],dict) else None)
    fr=D(session=D(user=user),get_all=get_all,get_list=get_list,get_meta=Meta,get_doc=get_doc,
         db=D(exists=lambda *a:True,count=lambda *a:0,get_value=lambda dt,n,f:STORE[dt][n].v.get(f)),throw=throw,form_dict=D(form),response=resp,
         utils=D(nowdate=lambda:"2026-11-17",now=lambda:"2026-11-17 12:00:00",add_days=lambda d,n:"2026-11-24"))
    g=dict(safe_globals); g["__builtins__"]=dict(safe_builtins, min=min,max=max,sorted=sorted,sum=sum)
    g.update(frappe=fr,json=json,_getattr_=getattr,_getitem_=default_guarded_getitem,_getiter_=default_guarded_getiter,_write_=lambda x:x,_iter_unpack_sequence_=guarded_iter_unpack_sequence,_inplacevar_=lambda op,a,b:a)
    exec(compile_restricted(open(__import__('os').path.join(__import__('os').path.dirname(__file__),'../ss/cc_gateway.py')).read(),'<s>','exec'),g,{})
    return resp.get("message")
V=["Command Center Viewer"]; E=V+["Command Center Editor"]
m=run("a@x",V,{"action":"config"}); print("config", list(m["doctypes"])[:3], len(m["doctypes"]), "fin sec locked:", [s["locked"] for s in m["sections"] if s["key"]=="finance"])
print("counts", run("a@x",V,{"action":"counts"})["counts"]["Task"])
print("list", run("a@x",V,{"action":"list","dt":"Task","search":"x"})["total"])
o=run("a@x",E+["Command Center Finance"],{"action":"overview"}); print("overview", len(o["signals"]), o["stats"]["Quotation"]["statuses"][:1], o["finance_ok"])
print("feed", len(run("a@x",V,{"action":"feed","dts":["Task"]})["rows"]))
print("save", run("a@x",E,{"action":"save","dt":"Task","name":"T-1","values":{"subject":"New"}}))
for who,form in [("viewer save",{"action":"save","dt":"Task","name":"T-1","values":{"subject":"n"}}),("bad field",{"action":"save","dt":"Task","name":"T-1","values":{"docstatus":1}})]:
    try: run("a@x",V if who=="viewer save" else E,form); print(who,"NOT BLOCKED")
    except Exception as e: print(who,"blocked:",e)
try: run("Guest",[],{"action":"config"})
except Exception as e: print("guest blocked:",e)
try: run("b@x",[],{"action":"config"})
except Exception as e: print("no role blocked:",e)
FALLBACK=True
o=run("a@x",V,{"action":"overview"}); print("overview fallback (no aggregates):", o["stats"]["Quotation"]["statuses"])
V16=False; FALLBACK=False
print("v15 path: list total", run("a@x",V,{"action":"list","dt":"Task","search":"x"})["total"], "overview", run("a@x",V,{"action":"overview"})["stats"]["Quotation"]["statuses"][:1])

# ---- meeting agenda ----
print("agenda_list empty", run("a@x",V,{"action":"agenda_list"}))
try: run("a@x",V,{"action":"agenda_create","values":{"meeting_date":"2026-11-17"}}); print("viewer create NOT BLOCKED")
except Exception as e: print("viewer agenda_create blocked:",e)
m1=run("a@x",E,{"action":"agenda_create","values":{"title":"Weekly","meeting_date":"2026-11-17"}})["name"]
a=run("a@x",E,{"action":"agenda_add","agenda":m1,"values":{"item_title":"Hiring plan","presenter":"a@x"}})
b=run("a@x",E,{"action":"agenda_add","agenda":m1,"values":{"item_title":"","reference_doctype":"Sales Order","reference_name":"T-1"}})
dup=run("a@x",E,{"action":"agenda_add","agenda":m1,"values":{"reference_doctype":"Sales Order","reference_name":"T-1"}})
print("add free + linked + duplicate:", bool(a["name"]), bool(b["name"]), dup.get("duplicate"))
for who,form in [("not allowed doctype",{"action":"agenda_add","agenda":m1,"values":{"reference_doctype":"User","reference_name":"x"}}),
                 ("half link",{"action":"agenda_add","agenda":m1,"values":{"reference_doctype":"Task"}}),
                 ("bad field",{"action":"agenda_update","name":a["name"],"values":{"agenda":"other"}})]:
    try: run("a@x",E,form); print(who,"NOT BLOCKED")
    except Exception as e: print(who,"blocked:",e)
g=run("a@x",V,{"action":"agenda_get","name":m1})
print("get:", g["agenda"]["title"], [i["item_title"] for i in g["items"]], "refs:", list(g["refs"]), "sort:", [i["sort_order"] for i in g["items"]])
run("a@x",E,{"action":"agenda_update","name":b["name"],"values":{"status":"Discussed","outcome":"Ship Friday"}})
run("a@x",E,{"action":"agenda_update","name":b["name"],"values":{"details":"no new audit"}})
print("audit:", AUDIT)
run("a@x",E,{"action":"agenda_order","agenda":m1,"names":[b["name"],a["name"]]})
print("reordered:", [i["item_title"] for i in run("a@x",V,{"action":"agenda_get","name":m1})["items"]])
run("a@x",E,{"action":"agenda_save_meeting","name":m1,"values":{"notes":"n","status":"Closed"}})
m2=run("a@x",E,{"action":"agenda_create","values":{"title":"Weekly","meeting_date":"2026-11-24","carry":1}})
print("carry over:", m2["carried"], "old item now:", STORE[AGI][a["name"]].v["status"])
l=run("a@x",V,{"action":"agenda_list"}); print("list:", [(x["meeting_date"],x["status"],x["items"],x["open"]) for x in l["meetings"]], "can_edit", l["can_edit"])
run("a@x",E,{"action":"agenda_remove","name":a["name"]}); print("removed:", a["name"] not in STORE[AGI])
t=run("a@x",E,{"action":"agenda_todo","name":b["name"],"values":{"title":"Confirm balance <date>","owners":["r@x","j@x"],"date":"2026-11-24","priority":"High"}})
t2=run("a@x",E,{"action":"agenda_todo","name":b["name"],"values":{"title":"Second","owners":["r@x"]}})
print("todo: made", len(t["todos"]), "stored", len(json.loads(STORE[AGI][b["name"]].v["todo_names"])), "get has todos map:", "todos" in run("a@x",V,{"action":"agenda_get","name":m1}))
for who,form,roles in [("viewer todo",{"action":"agenda_todo","name":b["name"],"values":{"title":"x","owners":["r@x"]}},V),
                       ("todo no owners",{"action":"agenda_todo","name":b["name"],"values":{"title":"x","owners":[]}},E),
                       ("todo bad priority",{"action":"agenda_todo","name":b["name"],"values":{"title":"x","owners":["r@x"],"priority":"Urgent"}},E)]:
    try: run("a@x",roles,form); print(who,"NOT BLOCKED")
    except Exception as e: print(who,"blocked:",e)
print("todo doc:", TODOS[0]["reference_type"], TODOS[0]["reference_name"], TODOS[0]["allocated_to"], TODOS[0]["priority"], "escaped:", "&lt;date&gt;" in TODOS[0]["description"], "[meeting] Owners: r@x, j@x" in TODOS[0]["description"])

# ---- pipeline restructure: state fields, stages, assign, note ----
m=run("a@x",V,{"action":"config"})
print("sections in pipeline order:", [x["key"] for x in m["sections"]])
print("no requests section:", "requests" not in [x["key"] for x in m["sections"]])
qr=m["doctypes"]["ilL-Quote-Request"]; print("quote request section/status col:", qr["section"], [c["fieldname"] for c in qr["columns"]][:4], [c["label"] for c in qr["columns"] if c["fieldname"]=="status"])
del CALLS[:]
r=run("a@x",V,{"action":"list","dt":"ilL-Quote-Request","filters":{"status":"REQUESTED"},"order_by":"status asc"})
c=[x for x in CALLS if x[0]=="ilL-Quote-Request" and "name" in x[1]][-1]
print("list maps status->state:", "state" in c[1] and "status" not in c[1], c[2], c[3], "row status:", r["rows"][0].get("status"))
del CALLS[:]
o=run("a@x",V,{"action":"overview"})
g=[x for x in CALLS if x[0]=="ilL-Order-Intake" and x[4]][:1]
print("overview groups intake by state:", g[0][4] if g else None, "signals:", [x["id"] for x in o["signals"]][:4])
st=run("a@x",V,{"action":"stages"})
print("stages keys:", sorted(k for k in st if k not in ("today","can_edit")))
print("stages schedule lines:", st["schedules"][0]["lines"], "project fetched for schedule:", any(x[0]=="ilL-Project" and x[2]=={"name":["in",["P-9"]]} for x in CALLS))
del TODOS[:]
a=run("a@x",E,{"action":"assign","dt":"HD Ticket","name":"T-1","add":["j@x","dup@x"],"remove":["r@x"]})
print("assign:", a["added"], a["removed"], "todo made for:", [t["allocated_to"] for t in TODOS], "audit:", AUDIT[-1] if AUDIT else None)
for who,form,roles in [("viewer assign",{"action":"assign","dt":"HD Ticket","name":"T-1","add":["j@x"]},V),
                       ("assign nobody",{"action":"assign","dt":"HD Ticket","name":"T-1"},E),
                       ("assign not allowed dt",{"action":"assign","dt":"User","name":"x","add":["j@x"]},E),
                       ("viewer note",{"action":"note","dt":"HD Ticket","name":"T-1","text":"x"},V)]:
    try: run("a@x",roles,form); print(who,"NOT BLOCKED")
    except Exception as e: print(who,"blocked:",e)
run("a@x",E,{"action":"note","dt":"HD Ticket","name":"T-1","text":"linked quotation <Q-1>"}); print("note:", AUDIT[-1])

# ---- v8: Catalog tab flag, ilLumenate area, status kinds, read-only / builder doctypes, purchasing ----
FAILS=[]
def ok(name, cond):
    print(("PASS " if cond else "FAIL ")+name)
    if not cond: FAILS.append(name)
CAT="ilL Catalog Publisher"; SM="System Manager"
ok("catalog tab: publisher allowed", run("a@x",V+[CAT],{"action":"config","lite":1})["catalog"]["allowed"] is True)
ok("catalog tab: system manager allowed", run("a@x",V+[SM],{"action":"config","lite":1})["catalog"]["allowed"] is True)
ok("catalog tab: plain viewer not allowed", run("a@x",V,{"action":"config","lite":1})["catalog"]["allowed"] is False)
lite=run("a@x",V,{"action":"config","lite":1}); ok("config lite has no doctypes", "doctypes" not in lite and lite["catalog"]["url"]=="/catalog-builder")
META["ilL-Attribute-CCT"]={"title_field":"label","fields":[F("cct_name"),F("label"),F("kelvin","Int",in_list_view=1),F("is_active","Check"),F("notes","Small Text",in_list_view=1),F("secret","Data",permlevel=1)]}
META["ilL-Spec-Driver"]={"fields":[F("item","Link",in_list_view=1),F("max_wattage","Float",in_list_view=1)]}
META["ilL-Attribute-LED Package"]={"autoname":"prompt","fields":[F("code"),F("is_active","Check")]}
META["ilL-Fixture-Template"]={"fields":[F("template_code"),F("is_active","Check"),F("allowed_finishes","Table",options="ilL-Child-Finish")]}
META["ilL-Child-Finish"]={"fields":[F("finish","Link",in_list_view=1),F("is_default","Check",in_list_view=1),F("hidden_note")]}
cfg=run("a@x",E,{"action":"config"}); D_=cfg["doctypes"]
ok("config: sections carry an area", {x["key"]:x["area"] for x in cfg["sections"]}.get("ill_attributes")=="ill" and {x["key"]:x["area"] for x in cfg["sections"]}.get("quotes")=="pipeline")
ok("config: attribute in the ilL attributes group, bool status, inline create", D_["ilL-Attribute-CCT"]["sections"]==["ill_attributes"] and D_["ilL-Attribute-CCT"]["status_kind"]=="bool" and D_["ilL-Attribute-CCT"]["create"]=="inline")
ok("config: derived columns = name, title, in_list_view, status, modified", [c["fieldname"] for c in D_["ilL-Attribute-CCT"]["columns"]]==["name","label","kelvin","notes","status","modified"])
ok("config: no-status doctype has no status column", "status" not in [c["fieldname"] for c in D_["ilL-Spec-Driver"]["columns"]] and D_["ilL-Spec-Driver"]["status_kind"] is None)
ok("config: template is created via the builder", D_["ilL-Fixture-Template"]["create"]=="builder" and D_["ilL-Fixture-Template"]["builder"] is True)
ok("config: configured fixture is read-only, no create", D_["ilL-Configured-Fixture"]["read_only"] is True and D_["ilL-Configured-Fixture"]["can_create"] is False)
ok("config: ilL-Project in Design and the ilL projects group", D_["ilL-Project"]["sections"]==["design","ill_projects"] and D_["ilL-Project"]["section"]=="design")
ok("config: Webflow session and credential singles excluded", "ilL-Webflow-Session" not in D_ and "ilL-QBO-Settings" not in D_ and "ilL-Webflow-Settings" not in [x["doctype"] for x in cfg["settings"]])
ok("config: settings card lists singles as desk links", any(x["doctype"]=="ilL-Purchasing-Settings" and x["url"]=="/app/ill-purchasing-settings" for x in cfg["settings"]))
ok("config: logs group locked without System Manager", [x["locked"] for x in cfg["sections"] if x["key"]=="ill_logs"]==[True] and "ilL-Portal-Event" not in D_)
ok("config: logs visible to System Manager", "ilL-Portal-Event" in run("a@x",E+[SM],{"action":"config"})["doctypes"])
ok("config: purchasing doctypes (RFQ, SQ, PR, shipment, supplier) and finance-gated bills", all(D_.get(d,{}).get("section")=="purchasing" for d in ["Request for Quotation","Supplier Quotation","Purchase Receipt","ilL-Inbound-Shipment","Supplier"]) and "Purchase Invoice" not in D_ and run("a@x",E+["Command Center Finance"],{"action":"config"})["doctypes"]["Purchase Invoice"]["section"]=="finance")
ok("config: shipment also in the ilL purchasing group", D_["ilL-Inbound-Shipment"]["sections"]==["purchasing","ill_purchasing"])
del CALLS[:]
c=run("a@x",V,{"action":"counts","area":"ill","section":"ill_attributes"})["counts"]
ok("counts: one ilL group only", set(c)<=set(run("a@x",E,{"action":"config"})["doctypes"]) and "ilL-Attribute-CCT" in c and "Quotation" not in c and "ilL-Fixture-Template" not in c)
c=run("a@x",V,{"action":"counts"})["counts"]
ok("counts: default pipeline area unchanged (no ilL-only doctypes)", "Quotation" in c and "ilL-Attribute-CCT" not in c and "ilL-Project" in c)
del CALLS[:]
r=run("a@x",V,{"action":"list","dt":"ilL-Attribute-CCT","filters":{"status":"Active"},"order_by":"status asc"})
call=[x for x in CALLS if x[0]=="ilL-Attribute-CCT" and "name" in x[1]][-1]
ok("list: Active filter -> is_active=1, sort by is_active, row status Active", call[2]=={"is_active":1} and call[3]=="is_active asc" and "is_active" in call[1])
del CALLS[:]
run("a@x",V,{"action":"list","dt":"ilL-Attribute-CCT","filters":{"status":"Inactive"}})
ok("list: Inactive filter -> is_active=0", [x for x in CALLS if x[0]=="ilL-Attribute-CCT" and "name" in x[1]][-1][2]=={"is_active":0})
r=run("a@x",V,{"action":"list","dt":"ilL-Spec-Driver"}); ok("list: doctype with no status works, no status column", "status" not in [c["fieldname"] for c in r["columns"]])
for who,form in [("save read-only doctype",{"action":"save","dt":"ilL-Configured-Fixture","name":"T-1","values":{"subject":"x"}}),
                 ("create read-only doctype",{"action":"create","dt":"ilL-Catalog-Import","values":{"subject":"x"}}),
                 ("create via builder",{"action":"create","dt":"ilL-Fixture-Template","values":{"template_code":"X"}}),
                 ("prompt name missing",{"action":"create","dt":"ilL-Attribute-LED Package","values":{"code":"X"}}),
                 ("__newname on a field-named doctype",{"action":"create","dt":"ilL-Attribute-CCT","values":{"__newname":"X","cct_name":"X"}}),
                 ("permlevel-1 field",{"action":"save","dt":"ilL-Attribute-CCT","name":"T-1","values":{"secret":"x"}})]:
    try: run("a@x",E,form); ok(who+" refused", False)
    except Exception as e: ok(who+" refused ("+str(e)[:60]+")", True)
ok("meta: permlevel-1 field not offered, autoname returned", "secret" not in [f["fieldname"] for f in run("a@x",E,{"action":"meta","dt":"ilL-Attribute-CCT"})["fields"]] and run("a@x",E,{"action":"meta","dt":"ilL-Attribute-LED Package"})["autoname"]=="prompt")
del CREATED[:]
n=run("a@x",E,{"action":"create","dt":"ilL-Attribute-LED Package","values":{"__newname":"PKG-2835","code":"2835"}})
ok("create: prompt-named doctype takes the typed name", CREATED and CREATED[-1].get("name")=="PKG-2835" and CREATED[-1].get("__newname")=="PKG-2835" and CREATED[-1].get("code")=="2835")
r=run("a@x",E,{"action":"save","dt":"ilL-Attribute-CCT","name":"T-1","values":{"is_active":0}}); ok("save: is_active toggle goes through save", r["changed"]==1)
DOCS[("ilL-Fixture-Template","FT-1")]={"name":"FT-1","is_active":1,"docstatus":0,"allowed_finishes":[{"finish":"WH"+str(i),"is_default":i==0,"hidden_note":"x"} for i in range(30)]}
g=run("a@x",E,{"action":"get","dt":"ilL-Fixture-Template","name":"FT-1"}); t=g["tables"][0]
ok("get: child tables read-only, capped at 25 rows, in_list_view columns", t["count"]==30 and len(t["rows"])==25 and [c["fieldname"] for c in t["columns"]]==["finish","is_default"] and "hidden_note" not in t["rows"][0])
ok("get: bool status exposed, builder flag, editable header", g["doc"]["status"]=="Active" and g["builder"] is True and g["editable"] is True)
DOCS[("ilL-Configured-Fixture","CF-1")]={"name":"CF-1","docstatus":0}
ok("get: read-only doctype not editable", run("a@x",E,{"action":"get","dt":"ilL-Configured-Fixture","name":"CF-1"})["editable"] is False)
META["Purchase Order"]={"fields":[F("status","Select"),F("supplier","Link"),F("ill_eta","Date"),F("ill_vendor_status","Select"),F("grand_total","Currency"),F("schedule_date","Date"),F("ill_sent_on","Date")]}
del CALLS[:]
o=run("a@x",E,{"action":"overview"}); sig=[x["id"] for x in o["signals"]]
po=[x for x in CALLS if x[0]=="Purchase Order" and x[2] and any(isinstance(f,list) and f[0]=="ill_eta" for f in x[2])]
ok("overview: purchasing signals", all(k in sig for k in ["po_not_sent","po_unconfirmed","sq_expiring","receipt_no_bill","needs_lcv"]))
ok("overview: po_late uses ill_eta when the field exists", bool(po))
ok("overview: sections stay pipeline-only", all(not x["key"].startswith("ill_") for x in o["sections"]))
pc=[c["fieldname"] for c in run("a@x",E,{"action":"config"})["doctypes"]["Purchase Order"]["columns"]]
ok("config: PO columns include vendor status and ETA when present", "ill_vendor_status" in pc and "ill_eta" in pc)
del META["Purchase Order"]
print("v8 checks:", "ALL PASS" if not FAILS else "FAILED: "+", ".join(FAILS))
if FAILS: sys.exit(1)
