import json, sys
from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safe_globals
from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem
class D(dict):
    __getattr__=dict.get
class Meta:
    def __init__(s,dt): s.fields=[D(fieldname="status",label="Status",fieldtype="Select",read_only=0,hidden=0,options="Open\nDone",reqd=0,default=None),D(fieldname="subject",label="Subject",fieldtype="Data",read_only=0,hidden=0,options=None,reqd=1,default=None)]
    def get_field(s,c):
        for f in s.fields:
            if f.fieldname==c: return f
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
        return s
    def as_dict(s): return s.v
saved=[]
TODOS=[]
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
