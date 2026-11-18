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
        return D(label=c,fieldtype="Data") if c in ("grand_total","modified","customer","exp_end_date","project","priority","valid_till") else None
class Doc:
    docstatus=0; name="T-1"
    def __init__(s,v=None): s.v=dict(v or {}); s.v.setdefault("status","Open")
    def has_permission(s,p): return True
    def check_permission(s,p): pass
    def get(s,k): return s.v.get(k)
    def set(s,k,x): s.v[k]=x
    def save(s): saved.append(dict(s.v))
    def insert(s,**k): s.name="T-NEW"; return s
    def as_dict(s): return s.v
saved=[]
FALLBACK=False
def run(user, roles, form):
    resp={}
    def get_all(dt,**k):
        if dt=="Has Role": return [{"role":r} for r in roles]
        if dt=="Comment": return [{"creation":"x","owner":"a","content":"Command Center: z","reference_doctype":"Task","reference_name":"T-1"}]
        return []
    def get_list(dt,**k):
        f=k.get("fields",[])
        if any("count(" in x for x in f) and len(f)==1: return [{"total":3}]
        if any("count(" in x for x in f) and FALLBACK: raise Exception("aggregates refused")
        if any("count(" in x for x in f): return [{"status":"Open","n":2,"v":100.0},{"status":"Done","n":1,"v":5}]
        return [{"name":"T-1","status":"Open"}]
    def throw(m): raise Exception(m)
    fr=D(session=D(user=user),get_all=get_all,get_list=get_list,get_meta=Meta,get_doc=lambda *a: Doc(a[0] if isinstance(a[0],dict) else None),
         db=D(exists=lambda *a:True,count=lambda *a:0),throw=throw,form_dict=D(form),response=resp,
         utils=D(nowdate=lambda:"2026-11-17",add_days=lambda d,n:"2026-11-24"))
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
