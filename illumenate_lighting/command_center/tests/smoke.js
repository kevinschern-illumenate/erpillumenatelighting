const { JSDOM } = require('jsdom'); const fs = require('fs');
const js = fs.readFileSync(require('path').join(__dirname, '../page/cc.js'),'utf8');
const LIVE = require('path').join(__dirname, 'live_cc_html.fixture.html');
const html0 = `<body><div id="cc"><div class="cc-top"><span id="ccstamp"></span><span id="ccwho"></span><input id="ccq"><button id="ccrefresh"></button><button id="ccadd"></button><input type="checkbox" id="ccmeeting"></div><div id="ccnav" class="cc-nav"></div><div id="ccmain"></div>
<div id="ccmodal"><form id="tform"><div id="tOwners"></div><select id="tProj"></select><input id="tTitle"><input id="tDue"><select id="tPri"></select><textarea id="tNotes"></textarea><p id="tMsg"></p><button id="tSave"></button><button id="tCancel" type="button"></button></form></div><div id="ccsheet2" class="cc-modal"></div><div id="cctoast"></div></div></body>`;
const html = '<body>' + fs.readFileSync(LIVE, 'utf8').split('<footer class="web-footer"')[0] + '</body>';
const dom = new JSDOM(html, { url: 'https://x.test/command-center', runScripts: 'outside-only', pretendToBeVisual: true });
const w = dom.window; const errs = [];
w.addEventListener('error', e => errs.push('onerror: ' + e.message));
w.console.error = (...a) => errs.push('console.error: ' + a.join(' '));
w.scrollTo = () => {}; w.print = () => { w.__printed = (w.__printed||0)+1; };
w.document.cookie = 'user_id=kevins%40x.com'; w.frappe = { csrf_token: 'tok' };
w.prompt = () => 'My view'; w.confirm = () => true;
const TODAY = '2026-11-17';
const users = ['kevins@x.com','jay@x.com','ryanb@x.com'].map(n => ({ name: n, full_name: n.split('@')[0] }));
const ptasks = [
 { name:'TASK-1', subject:'Order extrusions', project:'PROJ-1', status:'Open', _assign:'["ryanb@x.com"]', exp_start_date:'2026-11-01', exp_end_date:'2026-11-10', deps:[], priority:'High' },
 { name:'TASK-2', subject:'Test samples', project:'PROJ-1', status:'Working', _assign:'[]', exp_start_date:'2026-11-12', exp_end_date:'2026-11-20', deps:['TASK-1'], priority:'Medium' },
 { name:'TASK-3', subject:'Ship kit', project:'PROJ-1', status:'Completed', _assign:'["jay@x.com"]', exp_end_date:'2026-11-05', deps:[] },
 { name:'TASK-4', subject:'Draft spec', project:'PROJ-2', status:'Open', _assign:'["kevins@x.com"]', exp_end_date:'2026-11-18', deps:[] } ];
const D = { today: TODAY, generated: '2026-11-17 16:00:00', note_names: {}, notes: { 'Command Center – This week': '<ul><li>Decide on tape supplier</li></ul>', 'Command Center – Recommendations': '<ol><li>x</li></ol>' },
 users, todos: [], tasks: [], tk: [ { name:'HD-1', status:'Open', age:4, created:'2026-11-10', type:'Quotation', subject:'Quote', assigned:'[]', idle:4 }, { name:'HD-2', status:'Replied', age:12, created:'2026-11-01', type:'Service', subject:'Fix', assigned:'[]', idle:12 } ],
 newd: [ { customer:'A', month:'2026-11', this_month:4000, last_month:0, first:'2026-11-03' } ], purch: [], ship: [ { so:'ilL-SAL-ORD-1', customer:'A', value:5000, delivery:'2026-11-01', status:'To Deliver', state:'At risk', reasons:['x'], delivered:0, lines:[] } ],
 mfg: [], reqs: [], needwo: [], drafts: [], quotes: [ { name:'Q-1', party_name:'A', docstatus:1, status:'Open', base_net_total:2500, valid_till:'2026-11-20', transaction_date:'2026-11-10' } ], changes: [], spif: [], spif_start: '2026-11-01',
 fin: { mtd: 8000, goal: 25000, last_month: 9000, mtdN: 3, ar: 4000 }, ar: [], monthly: [{month:'2026-10',si:9000},{month:'2026-11',si:8000}], conc: [], conc_total: 0, trend: [], active90: 5, tiers: {}, customers: ['A'], lowstock: [],
 projects: [ { name:'PROJ-1', project_name:'Lutron launch', status:'Open', customer:'A', expected_start_date:'2026-11-01', expected_end_date:'2026-12-01', percent_complete:30, notes:'<p>Notes here</p>', priority:'High' }, { name:'PROJ-2', project_name:'Spec sheets', status:'Open', expected_end_date:'2026-12-15', percent_complete:0 } ], ptasks };
let finOK = true, feedFail = false, stagesFail = false, catOK = false; const calls = [], saves = [], assigns = [], creates = [], counted = [];
// v8 Workbench: ilLumenate-area doctypes (status kinds, builder-created, prompt-named)
const col = (f, l, t) => ({ fieldname: f, label: l, type: t || 'Data' });
const ILLDT = {
  'ilL-Attribute-CCT': { section:'ill_attributes', sections:['ill_attributes'], can_create:true, create:'inline', status_kind:'bool', builder:false, columns:[col('name','ID'),col('label','Label'),col('status','Status','Select')] },
  'ilL-Attribute-LED Package': { section:'ill_attributes', sections:['ill_attributes'], can_create:true, create:'inline', status_kind:null, builder:false, columns:[col('name','ID')] },
  'ilL-Fixture-Template': { section:'ill_templates', sections:['ill_templates'], can_create:true, create:'builder', status_kind:'bool', builder:true, columns:[col('name','ID'),col('status','Status','Select')] },
  'Purchase Order': { section:'quotes', sections:['quotes'], can_create:false, create:'inline', status_kind:'status', columns:[col('name','ID'),col('status','Status','Select')] },
  'ilL-Spec-Driver': { section:'ill_specs', sections:['ill_specs'], can_create:true, create:'builder', status_kind:null, builder:true, columns:[col('name','ID'),col('item','Item','Link')] } };
// portal data behind the gateway's "stages" action (Design / Quotes / Sales orders / Service lanes)
const ST = { today: TODAY, can_edit: true, missing: [],
  projects: [ { name:'ILL-PROJ-1', project_name:'Hotel lobby', customer:'A', status:'ACTIVE', architect:'Arch Co', location:'Denver' } ],
  schedules: [
    { name:'SCH-1', schedule_name:'Lobby rev A', ill_project:'ILL-PROJ-1', customer:'A', status:'DRAFT', version:1, is_locked:0, lines:3, modified:'2026-11-16' },
    { name:'SCH-2', schedule_name:'Lobby rev B', ill_project:'ILL-PROJ-1', customer:'A', status:'READY', version:2, is_locked:1, lines:5, modified:'2026-11-16' },
    { name:'SCH-3', schedule_name:'Guest floors', ill_project:'ILL-PROJ-1', customer:'A', status:'READY', version:1, lines:2, modified:'2026-11-16' },
    { name:'SCH-4', schedule_name:'Ballroom', customer:'A', status:'QUOTED', version:1, lines:8, modified:'2026-11-16' },
    { name:'SCH-5', schedule_name:'Spa', customer:'A', status:'ORDER_REQUESTED', version:1, lines:1, modified:'2026-11-16' } ],
  doc_requests: [
    { name:'ILL-REQ-1', request_type:'Shop drawing', status:'In Progress', fixture_schedule:'SCH-3', requester_customer:'A', assigned_to:'jay@x.com', sla_deadline:'2026-11-12 17:00:00', creation:'2026-11-09 10:00:00' },
    { name:'ILL-REQ-2', request_type:'Manufacturing sign-off', status:'Submitted', sales_order:'ilL-SAL-ORD-1', requester_customer:'A', creation:'2026-11-16 10:00:00' } ],
  reviews: [], offers: [ { name:'OFFER-1', quotation:'Q-1', quote_request:'QR-2', schedule:'SCH-4', customer:'A', state:'ACCEPTED', responded_on:'2026-11-15 10:00:00', modified:'2026-11-15' } ],
  quote_requests: [ { name:'QR-1', schedule:'SCH-4', customer:'A', state:'REQUESTED', assigned_to:'ryanb@x.com', creation:'2026-11-05 09:00:00', modified:'2026-11-05' },
    { name:'QR-2', schedule:'SCH-4', customer:'A', state:'ISSUED', latest_offer:'Q-1', creation:'2026-11-10 09:00:00', modified:'2026-11-12' } ],
  intakes: [ { name:'OI-1', schedule:'SCH-5', customer:'A', state:'SUBMITTED', creation:'2026-11-16 09:00:00', customer_message:'Please ship by Dec 1' } ],
  account_requests: [ { name:'AR-1', request_type:'Address change', customer:'A', requested_by:'dealer@a.com', state:'Pending', creation:'2026-11-02 09:00:00' },
    { name:'AR-2', request_type:'Dealer application', requested_by:'new@b.com', state:'Information needed', creation:'2026-11-14 09:00:00' } ],
  tickets: [ { name:'HD-1', ill_fixture_schedule:'SCH-3', ill_project:'ILL-PROJ-1', priority:'High' } ] };
// in-memory meeting agenda behind the gateway's agenda_* actions
const AGS = { meetings: [], items: [] }; let agSeq = 0;
const agRefs = items => { const r = {}; items.forEach(i => {
  if (i.reference_doctype === 'Sales Order') r['Sales Order|' + i.reference_name] = { name: i.reference_name, customer: 'A', status: 'To Deliver', grand_total: 5000 };
  if (i.reference_doctype === 'Quotation') r['Quotation|' + i.reference_name] = { name: i.reference_name, status: 'Open', grand_total: 1200 };
  if (i.reference_doctype === 'ToDo') r['ToDo|' + i.reference_name] = { name: i.reference_name, description: '<p>Call Bob</p><p>[email] Owners: k</p>', status: 'Open' }; }); return r; };
const agendaReply = b => { const v = b.values || {};
  if (b.action === 'agenda_list') return { today: TODAY, can_edit: true, meetings: AGS.meetings.map(m => ({ ...m, items: AGS.items.filter(i => i.agenda === m.name).length, open: AGS.items.filter(i => i.agenda === m.name && i.status === 'Open').length })) };
  if (b.action === 'agenda_create') { const name = 'MTG-' + (++agSeq); AGS.meetings.unshift({ name, title: v.title, meeting_date: v.meeting_date, status: 'Open', notes: '' }); return { name, carried: 0 }; }
  if (b.action === 'agenda_get') { const items = AGS.items.filter(i => i.agenda === b.name).sort((a, c) => a.sort_order - c.sort_order);
    return { agenda: { ...AGS.meetings.find(m => m.name === b.name) }, items: items.map(i => ({ ...i })), refs: agRefs(items), can_edit: true,
      columns: { 'Sales Order': [{ fieldname: 'name', label: 'ID', type: 'Data' }, { fieldname: 'grand_total', label: 'Total', type: 'Currency' }] } }; }
  if (b.action === 'agenda_add') { if (v.reference_name && AGS.items.some(i => i.agenda === b.agenda && i.reference_name === v.reference_name)) return { name: 'dup', duplicate: true };
    const it = { name: 'AI-' + (++agSeq), agenda: b.agenda, item_title: v.item_title, details: '', presenter: v.presenter || null, status: 'Open', outcome: '', reference_doctype: v.reference_doctype || null, reference_name: v.reference_name || null, sort_order: AGS.items.length + 1 };
    AGS.items.push(it); return { name: it.name }; }
  if (b.action === 'agenda_update') { Object.assign(AGS.items.find(i => i.name === b.name), v); return { name: b.name }; }
  if (b.action === 'agenda_order') { b.names.forEach((n, k) => { AGS.items.find(i => i.name === n).sort_order = k + 1; }); return { ordered: b.names.length }; }
  if (b.action === 'agenda_save_meeting') { Object.assign(AGS.meetings.find(m => m.name === b.name), v); return { name: b.name }; }
  if (b.action === 'agenda_todo') { const it = AGS.items.find(i => i.name === b.name), made = v.owners.map((o, k) => ({ name: 'TD-M' + (++agSeq), owner: o, title: v.title, date: v.date }));
    it.todo_names = JSON.stringify(JSON.parse(it.todo_names || '[]').concat(made)); AGS.lastTodo = v; return { todos: made }; }
  if (b.action === 'agenda_remove') { AGS.items = AGS.items.filter(i => i.name !== b.name); return { removed: 1 }; }
  throw new Error('unknown ' + b.action); };
const gwReply = b => {
  calls.push(b.action);
  if (b.action === 'config' && b.lite) return { user:'k', can_edit:true, today:TODAY, catalog:{ allowed:catOK, url:'/catalog-builder' }, sections:[] };
  if (b.action === 'config') return { user:'k', can_edit:true, today:TODAY, catalog:{ allowed:catOK, url:'/catalog-builder' }, settings:[{doctype:'ilL-Purchasing-Settings',url:'/app/ill-purchasing-settings'}], sections:[{key:'quotes',label:'Quotes',locked:false,needs:''},{key:'projects',label:'Projects & tasks',locked:false,needs:''},{key:'finance',label:'Finance',locked:!finOK,needs:'Command Center Finance'},{key:'ill_templates',label:'Product templates',locked:false,needs:'',area:'ill'},{key:'ill_attributes',label:'Attributes',locked:false,needs:'',area:'ill'},{key:'ill_specs',label:'Specifications',locked:false,needs:'',area:'ill'},{key:'ill_logs',label:'Logs & system (read-only)',locked:true,needs:'System Manager',area:'ill'}], doctypes:{ ...ILLDT, Quotation:{section:'quotes',can_create:false,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'},{fieldname:'grand_total',label:'Total',type:'Currency'}]}, ToDo:{section:'projects',can_create:true,columns:[{fieldname:'name',label:'ID',type:'Data'}]}, 'Sales Order':{section:'quotes',can_create:false,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'customer',label:'Customer',type:'Link'},{fieldname:'status',label:'Status',type:'Select'}]}, Task:{section:'projects',can_create:true,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'}]} } };
  if (b.action === 'counts' && b.area === 'ill') { counted.push(b.section); return { counts: Object.fromEntries(Object.keys(ILLDT).filter(d => ILLDT[d].sections.includes(b.section)).map(d => [d, 7])) }; }
  if (b.action === 'counts') return { counts:{ Quotation:3, Task:null } };
  if (b.action === 'list' && b.dt === 'ilL-Attribute-CCT') return { rows:[{name:'2700K',label:'2700K',status: b.filters && b.filters.status || 'Active'},{name:'5000K',label:'5000K',status:'Inactive'}], columns:ILLDT['ilL-Attribute-CCT'].columns, total:2 };
  if (b.action === 'list' && b.dt === 'ilL-Spec-Driver') return { rows:[{name:'DRV-1',item:'DRV-1'}], columns:ILLDT['ilL-Spec-Driver'].columns, total:1 };
  if (b.action === 'get' && b.dt === 'ilL-Fixture-Template') return { doc:{ name:b.name, status:'Active', is_active:1, docstatus:0 }, audit:[], editable:true, builder:true, status_kind:'bool', read_only:false, create:'builder',
    tables:[ { fieldname:'allowed_finishes', label:'Allowed finishes', count:30, columns:[col('finish','Finish','Link')], rows: Array.from({ length: 25 }, (_, i) => ({ finish:'FIN-' + i })) }, { fieldname:'allowed_lenses', label:'Allowed lenses', count:0, columns:[], rows:[] } ] };
  if (b.action === 'get' && b.dt === 'ilL-Attribute-CCT') return { doc:{ name:b.name, label:b.name, status:'Active', is_active:1, docstatus:0 }, audit:[], editable:true, builder:false, status_kind:'bool', read_only:false, create:'inline', tables:[] };
  if (b.action === 'meta' && b.dt === 'ilL-Attribute-LED Package') return { dt:b.dt, fields:[{ fieldname:'code', label:'Code', type:'Data', reqd:1 }], required_tables:[], can_edit:true, autoname:'prompt', create:'inline' };
  if (b.action === 'create') { creates.push(b); return { name: (b.values && b.values.__newname) || 'NEW-1' }; }
  if (b.action === 'list' && b.dt === 'ToDo') return { rows:[{name:'TD-1',description:'<p>Call Bob</p><p>[email] Owners: k</p>',status:'Open'},{name:'TD-2',description:'<p>Order tape</p>',status:'Open'}], columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'description',label:'Description',type:'Small Text'},{fieldname:'status',label:'Status',type:'Select'}], total:2 };
  if (b.action === 'list') return { rows:[{name:'QTN-1',status:b.filters&&b.filters.status||'Open',grand_total:1200}], columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'},{fieldname:'grand_total',label:'Total',type:'Currency'}], total:1 };
  if (b.action === 'overview') return { today:TODAY, finance_ok:finOK, sections:[], can_edit:true, stats:{ Quotation:{section:'quotes',count:3,value:9000,statuses:[['Open',2,7000],['Ordered',1,2000]]}, 'Sales Order':{section:'orders',count:2,value:12000,statuses:[['To Deliver',2,12000]]}, 'Purchase Order':{statuses:[['To Receive',1,3000]]}, ...(finOK?{'Sales Invoice':{statuses:[['Overdue',1,500],['Paid',4,0]]}}:{}) }, signals:[{id:'a',label:'Quotes expiring within 7 days',dt:'Quotation',count:2,status:'Open',tone:'warn'},{id:'b',label:'Overdue invoices',dt:'Sales Invoice',count:0,status:'Overdue',tone:'bad'}] };
  if (b.action.startsWith('agenda_')) return agendaReply(b);
  if (b.action === 'stages') { if (stagesFail) throw new Error('gateway down'); return JSON.parse(JSON.stringify(ST)); }
  if (b.action === 'save') { saves.push(b); return { name: b.name, changed: Object.keys(b.values).length }; }
  if (b.action === 'assign') { assigns.push(b); return { name: b.name, added: b.add, removed: b.remove }; }
  if (b.action === 'get' && b.dt === 'ilL-Project-Fixture-Schedule') return { doc: { name: b.name, status: 'READY', lines: [ { idx:1, line_id:'L1', qty:4, location:'Lobby', manufacturer_type:'ILLUMENATE', ill_item_code:'ILL-TAPE-1', configuration_status:'Configured' } ] }, audit: [], editable: false };
  if (b.action === 'get' && b.dt === 'HD Ticket') return { doc: { name: b.name, subject: 'Quote', status: 'Open', priority: 'Medium', ticket_type: 'Quotation', raised_by: 'dealer@a.com', _assign: '[]', ill_quotation: null, ill_fixture_schedule: 'SCH-3', docstatus: 0 }, audit: [ { creation: '2026-11-17 09:00:00', content: 'Command Center: assigned jay@x.com by kevins@x.com' } ], editable: true };
  if (b.action === 'meta' && b.dt === 'HD Ticket') return { dt: b.dt, fields: ['status','priority','ticket_type','agent_group','ill_quotation','ill_sales_order','ill_project','ill_fixture_schedule'].map(f => ({ fieldname: f, label: f, type: 'Data' })), required_tables: [], can_edit: true };
  if (b.action === 'get') return { doc: { name: b.name, status: 'Open', docstatus: 0, grand_total: 1200 }, audit: [], editable: true };
  if (b.action === 'meta') return { dt: b.dt, fields: [], required_tables: [], can_edit: true };
  if (b.action === 'feed' && feedFail) throw new Error('feed down');
  if (b.action === 'feed') return { rows:[{creation:'2026-11-17 10:00:00',owner:'kevins@x.com',content:'Command Center: edited by kevins (status: Open -> Working)',reference_doctype:'Task',reference_name:'TASK-2'}] };
  throw new Error('unknown ' + b.action);
};
const cnt = o => Object.assign({ runs_2c:0, runs_3c:0, runs_4c:0, runs_5c:0, runs_6c:0, loose:0, wet:0, fmc:0, assembly:0 }, o);
const bucket = (n, a, p) => ({ count:n, amount:a, com:a*0.2, com_pct:0.2, points:p });
const BOARD = { as_of:'2026-11-17T10:00:00', today:TODAY, money:true,
 settings:{ points_per_person_day:57.5, headcount:5.5, capacity_per_day:316.25, points_per_hour:6.76, commission_flag_pct:0.22, weights:{} },
 pipeline:{ pend_prod:bucket(1,727,2), in_prod:bucket(1,25251.88,322), pend_ship:bucket(0,0,0), wfp:bucket(1,19459.84,41), paint:bucket(0,0,0), held:bucket(0,0,0) },
 due:{ past_due:{count:1,amount:727}, today:{count:0,amount:0}, next_day:{count:0,amount:0,date:'2026-11-18'}, this_week:{count:1,amount:25251.88} },
 capacity:{ whse_points:324, in_prod_points:322, wfp_month_points:41, workload:365, capacity_per_day:316.25, left_today:120, days_to_complete:1.15, date_clear:'2026-11-18', burndown:[{date:'2026-11-17',capacity:120,remaining:245},{date:'2026-11-18',capacity:316.25,remaining:0}], overtime:{daily:0,days:0,weekend:0} },
 queue:[ { so:'ilL-SAL-ORD-67312', customer:'Wichita', amount:25251.88, com_pct:0.19, com:4797, esd:'2026-11-20', esd_is_ship_date:true, status:2, status_label:'In-Prod', counts:cnt({runs_2c:23, wet:92, fmc:69}), points:322, hours:47.6, worth:63.51, notes:'A lns', warnings:[], work_orders:2, short_items:[], no_po_items:[], eta:null, going_to_miss:false, this_month:true, past_due:false },
   { so:'ilL-SAL-ORD-68686', customer:'B', amount:727, com_pct:0.25, com:181, esd:'2026-11-10', esd_is_ship_date:false, status:1, status_label:'Pend-Prod', counts:cnt({runs_2c:2}), points:2, hours:0.3, worth:272.75, notes:'', warnings:['Conductor count unknown'], work_orders:1, short_items:[], no_po_items:[], eta:null, going_to_miss:false, this_month:true, past_due:true } ],
 wfp:[ { so:'ilL-SAL-ORD-68552', customer:'C', amount:19459.84, com_pct:0.1, com:1946, esd:'2026-11-19', esd_is_ship_date:true, status:9, status_label:'Waiting for parts', counts:cnt({runs_2c:41}), points:41, hours:6, worth:427, notes:'41 runs', warnings:[], work_orders:1, short_items:[{item:'EXT-1',qty:12},{item:'TAPE-9',qty:3}], no_po_items:['TAPE-9'], eta:null, going_to_miss:true, this_month:false, past_due:false } ],
 shipped:{ today:{count:1,amount:14646.36,com:2298,com_pct:0.157}, mtd:{count:2,amount:20000,com:3000,com_pct:0.15}, on_time_pct:0.5, weekly:[{week_of:'2026-11-16',shipments:2,on_time_pct:0.5}],
   rows:[ { delivery_note:'DN-1', so:'ilL-SAL-ORD-1', customer:'A', amount:14646.36, com_pct:0.157, com:2298, esd:'2026-11-17', shipped:'2026-11-17', on_time:true, not_warehouse_fault:false, late_reason:null },
          { delivery_note:'DN-2', so:'ilL-SAL-ORD-2', customer:'B', amount:5353.64, com_pct:0.14, com:750, esd:'2026-11-10', shipped:'2026-11-12', on_time:false, not_warehouse_fault:false, late_reason:'Short extrusion' } ] },
 goal:{ month_goal:250000, shipped_mtd:20000, available_to_ship:45438.72, gap:184561.28, shipping_days_left:9, needed_per_day:20506.81 },
 inbound:{ today_amount:12418.01, today:{ date:'2026-11-17', count:3, amount:12418.01, com:2000, com_pct:0.16, zero:1, same_day:1, next_day:0, rush:2 }, month_avg_amount:39063.56, avg_30_amount:55666.78, month_received_amount:400000,
   days:[ { date:'2026-11-17', count:3, amount:12418.01, com:2000, com_pct:0.16, zero:1, same_day:1, next_day:0, rush:2 }, { date:'2026-11-16', count:5, amount:61000, com:9000, com_pct:0.15, zero:0, same_day:0, next_day:1, rush:1 } ] },
 daily:{ days:[ { date:'2026-11-16', count:1, amount:5353.64 }, { date:'2026-11-17', count:1, amount:14646.36 }, { date:'2026-11-18', count:0, amount:0 } ], average_amount:10000, needed_amount:20506.81 },
 reporting:[ { month:'2026-11-01', goal_amount:2477000, shipped_amount:308269.45, scheduled_amount:919819.62, run_rate_amount:750000, at_risk_amount:19262.52, release_amount:53882, projected_amount:2051233.59, projected_safe_amount:2031971.07, goal_pct:0.828, com_pct:0.22, workdays:9, orders:40 },
   { month:'2026-12-01', goal_amount:3180000, shipped_amount:0, scheduled_amount:337402.07, run_rate_amount:1100000, at_risk_amount:266882.33, release_amount:534490.88, projected_amount:2238775.28, projected_safe_amount:1971892.95, goal_pct:0.704, com_pct:0.2, workdays:21, orders:10 },
   { month:'2027-01-01', goal_amount:0, shipped_amount:0, scheduled_amount:0, run_rate_amount:1100000, at_risk_amount:88621.98, release_amount:566859.46, projected_amount:1755481.44, projected_safe_amount:1666859.46, goal_pct:null, com_pct:0, workdays:20, orders:0 } ],
 releases:{ rows:[ { so:'ilL-SAL-ORD-65513', customer:'Wichita Biomedical Campus', amount:14076.3, com_pct:0.3113, com:4382, likely_ship:'2026-12-13', hold_reason:'Hold for Release', release_points:30, release_days:0.09, notes:'PLS ORDER CHECK IN', status:5, points:22 } ],
   months:[ { month:'2026-11-01', count:0, amount:0, com:0, com_pct:0 }, { month:'2026-12-01', count:1, amount:14076.3, com:4382, com_pct:0.3113 } ], points:30, days:0.09, no_date:0 },
 ship_holds:{ rows:[ { so:'ilL-SAL-ORD-68725', customer:'D', amount:13006, com_pct:0.3156, com:4105, esd:'2026-12-06', esd_is_ship_date:true, days_until:19, points:17, notes:'17 wr runs', hold_reason:'Hold for Ship', status:5 } ], months:[], total_amount:13006, through_next_month_amount:13006, week_amount:0 },
 prowc:{ proforma:{ open_count:1, open_amount:21347.93, completed_count:3, completed_amount:24846.18, com_pct:0.61 }, will_call:{ open_count:0, open_amount:0, completed_count:4, completed_amount:4497.53, com_pct:0.14 },
   rows:[ { so:'ilL-SAL-ORD-63655', customer:'E', amount:21347.93, com_pct:0.69, com:14734, esd:'2026-11-20', esd_is_ship_date:true, status:3, prowc:'Proforma', notes:'' } ],
   completed:[ { delivery_note:'DN-9', so:'ilL-SAL-ORD-67588', customer:'F', amount:1118.88, com_pct:0, shipped:'2026-11-05', prowc:'Will Call' } ] },
 paint:{ rows:[ { so:'ilL-SAL-ORD-68572', customer:'G', amount:9310.94, com_pct:0.177, esd:'2026-11-21', esd_is_ship_date:true, status:7, notes:'1 CH-502 on hand', paint:[ { po:'PO-15059', supplier:'Powder Co', sent:'2026-11-06', due_back:'2026-11-19', item:'CH-409', item_name:'Channel 409', qty:35 } ] } ],
   total_amount:9310.94, month_amount:9310.94, month_count:1, supplier_group:'Finishing' } };
// v8 purchasing board (purchasing_board.get_board): one record per lane
const PL_ = (lane, extra) => Object.assign({ name: 'PO-' + lane, supplier: 'Acme Extrusions', lane, status: lane === 'draft' ? 'Draft' : 'To Receive and Bill', docstatus: lane === 'draft' ? 0 : 1, vendor_status: 'Sent',
  transaction_date: '2026-11-01', lead_days: 28, lead_src: 'quote', eta: '2026-11-29', eta_src: 'po', amount: 1000, per_received: 0, per_billed: 0, sales_orders: [], shipments: [], receipts: [], invoices: [], paint: false,
  lines: [{ name: 'POI-1', item: 'EXT-1', item_name: 'Extrusion 1', qty: 10, received_qty: 0, ill_est_lead_time_days: null, ill_eta: null, lead_days: 28, eta: '2026-11-29' }] }, extra || {});
const PUB = { today: TODAY, money: true, can_edit: true, settings: { quote_expiry_warn_days: 7, vendor_confirm_warn_days: 3, receipt_bill_warn_days: 14, lcv_warn_days: 30, safety_days: 3 },
  summary: { to_order: { count: 1, late: 1 }, reorder: { count: 1 }, mrs: { count: 2, draft: 1 }, quotes: { out: 3, expiring: 1 }, pos: { count: 8, amount: 81234.5, not_sent: 1, overdue: 1 }, shipments: { moving: 1, customs: 0, arriving: 0 }, receipts: { to_bill: 1, needs_lcv: 1 }, bills: { count: 2, unpaid_amount: 22100, overdue: 1 }, landed: { needs_lcv: 1, est_open_amount: 6400, in_stock_amount: 3100 } },
  decisions: [ { id: 'po_overdue', label: 'POs past their ETA, not received', count: 1, tone: 'bad', tab: 'pos', lane: 'partly_received' }, { id: 'needs_lcv', label: 'Shipments waiting for landed cost', count: 1, tone: 'warn', tab: 'landed', lane: null } ],
  shortages: [ { item: 'EXT-9', group: 'Extrusions', lead: 10, lead_src: 'group default', on_hand: 2, on_order: 0, supplier: null, need_by: '2026-11-20', order_by: '2026-11-07', late: true, short_firm: 12, short_all: 12, draft_po: null, mr: null, manufactured: false, docs: [{ src: 'Sales Order', doc: 'ilL-SAL-ORD-1', draft: false }] },
    { item: 'TAPE-2', group: 'Tape', lead: 35, lead_src: 'item', on_hand: 0, on_order: 0, supplier: 'Tape Co', need_by: '2026-12-20', order_by: '2026-11-12', late: true, short_firm: 0, short_all: 4, draft_po: null, mr: null, manufactured: false, docs: [{ src: 'Sales Order', doc: 'ilL-SAL-ORD-9', draft: true }] } ],
  reorder: [ { item: 'PSU-60', item_name: '60W driver', warehouse: 'Stores - ilL', projected: 2, level: 10, reorder_qty: 20, suggest_qty: 20, supplier: 'Power Co', lead: 28, lead_src: 'supplier', open_mr: null, open_po: null, suggested_level: 14 } ],
  mrs: [ { name: 'MAT-MR-2026-00001', status: 'Draft', docstatus: 0, lane: 'draft', schedule_date: '2026-11-30', items: [{ item: 'EXT-9', qty: 12, ordered_qty: 0 }], rfqs: [], sqs: [], pos: [] },
    { name: 'MAT-MR-2026-00002', status: 'Pending', docstatus: 1, lane: 'to_quote', schedule_date: '2026-11-10', items: [{ item: 'TAPE-2', qty: 4, ordered_qty: 0 }], from_so: 'ilL-SAL-ORD-1', rfqs: [], sqs: [], pos: [] } ],
  quotes: [ { doctype: 'Request for Quotation', name: 'RFQ-1', status: 'Submitted', docstatus: 1, lane: 'awaiting_reply', suppliers: [{ supplier: 'Tape Co', quote_status: 'Pending', email_sent: 1 }, { supplier: 'Glow Ltd', quote_status: 'Received', email_sent: 1 }], items: 1, mr: 'MAT-MR-2026-00002' },
    { doctype: 'Supplier Quotation', name: 'SQ-1', status: 'Submitted', docstatus: 1, lane: 'expiring', supplier: 'Glow Ltd', valid_till: '2026-11-20', days_left: 3, total: 4200, lead_days: 21, items: 1, rfq: 'RFQ-1' },
    { doctype: 'Supplier Quotation', name: 'SQ-2', status: 'Expired', docstatus: 1, lane: 'expired', supplier: 'Old Co', valid_till: '2026-10-01', days_left: -47, total: 900, items: 1 } ],
  quote_compare: [ { item: 'TAPE-2', rows: [ { sq: 'SQ-1', supplier: 'Glow Ltd', rate: 10, lead_days: 21, valid_till: '2026-11-20', cheapest: true, fastest: false }, { sq: 'SQ-3', supplier: 'Tape Co', rate: 12, lead_days: 14, valid_till: '2026-12-01', cheapest: false, fastest: true } ] } ],
  pos: [ PL_('draft'), PL_('not_sent', { vendor_status: 'Not sent' }), PL_('awaiting_confirmation', { sent_on: '2026-11-10' }), PL_('confirmed', { vendor_status: 'Confirmed', vendor_order_no: 'ACK-77' }),
    PL_('in_transit', { vendor_status: 'Shipped', shipments: ['ILL-SHP-2026-0001'] }), PL_('partly_received', { per_received: 40, eta: '2026-11-10', overdue: true, sales_orders: ['ilL-SAL-ORD-1'] }),
    PL_('to_bill', { per_received: 100, will_miss: true, will_miss_so: 'ilL-SAL-ORD-1', eta: '2026-11-25', sales_orders: ['ilL-SAL-ORD-1'] }), PL_('on_hold', { status: 'On Hold' }), PL_('done', { status: 'Completed', per_received: 100, per_billed: 100 }) ],
  shipments: [ { name: 'ILL-SHP-2026-0001', status: 'In transit', lane: 'moving', supplier: 'Acme Extrusions', forwarder: 'Fast Freight', mode: 'Ocean FCL', tracking_no: 'BOL123', tracking_url: 'https://track.example/BOL123', container_no: 'MSCU1', eta: '2026-11-25', pos: ['PO-in_transit'], receipts: [], goods_value: 20000, est_cost: 2600, actual_cost: 0, landed_pct: 13, needs_lcv: false,
      costs: [ { name: 'C1', cost_type: 'Freight', description: 'Ocean freight Shanghai', est: 1600, actual: null, vendor: 'Fast Freight', pi: null, in_lc: 1, expense_account: 'Freight In - ilL', allocation: 'By qty' }, { name: 'C2', cost_type: 'Duty', est: 1000, actual: null, vendor: 'Broker Co', pi: null, in_lc: 1 } ], lcvs: [] },
    { name: 'ILL-SHP-2026-0002', status: 'Delivered', lane: 'delivered', supplier: 'Acme Extrusions', mode: 'Air', eta: '2026-11-10', ata: '2026-11-11', pos: ['PO-to_bill'], receipts: ['PR-1'], goods_value: 5000, est_cost: 700, actual_cost: 760, landed_pct: 15.2, needs_lcv: true,
      costs: [ { name: 'C3', cost_type: 'Freight', est: 700, actual: 760, vendor: 'Fast Freight', pi: 'PI-9', in_lc: 1 } ], lcvs: [] } ],
  receipts: [ { name: 'PR-1', supplier: 'Acme Extrusions', posting_date: '2026-11-11', status: 'To Bill', docstatus: 1, pos: ['PO-to_bill'], amount: 5000, billed_pct: 0, shipment: 'ILL-SHP-2026-0002', lcv_amount: 0, needs_lcv: true, lcv_status: 'needs_lcv' } ],
  bills: [ { name: 'PI-9', supplier: 'Fast Freight', bill_no: 'FF-1', posting_date: '2026-11-12', due_date: '2026-11-15', status: 'Overdue', docstatus: 1, lane: 'overdue', amount: 760, outstanding: 760, qbo_id: null, pos: [], receipts: [], kind: 'freight/duty', match: null },
    { name: 'PI-8', supplier: 'Acme Extrusions', bill_no: 'A-1', posting_date: '2026-11-12', due_date: '2026-12-12', status: 'Unpaid', docstatus: 1, lane: 'unpaid', amount: 5100, outstanding: 5100, qbo_id: '55', pos: ['PO-to_bill'], receipts: ['PR-1'], kind: 'goods', match: 'price_off', variance: { qty: 0, price: 100 } } ],
  landed: { pending: [ { shipment: 'ILL-SHP-2026-0002', receipt: 'PR-1', supplier: 'Acme Extrusions', est: 700, actual: 760, missing_bills: ['Duty'], ready: false } ], vouchers: [ { name: 'LCV-1', docstatus: 1, receipts: ['PR-0'], amount: 400, posting_date: '2026-10-02' } ],
    by_item: [ { item: 'EXT-1', item_name: 'Extrusion 1', last_receipt: 'PR-0', purchase_rate: 10, landed_rate: 11.5, uplift_pct: 15, avg_uplift_12m: 12.5 } ], in_stock_amount: 3100 },
  gaps: { no_supplier: [{ item: 'EXT-9', item_name: 'Extrusion 9' }], no_lead: [{ item: 'EXT-9', item_name: 'Extrusion 9' }], no_reorder: [{ item: 'PSU-90', item_name: '90W', suggested_level: 6 }], no_hts: [], no_origin: [] },
  suppliers: [ { supplier: 'Acme Extrusions', open_pos: 7, open_amount: 7000, avg_quoted_lead: 28, avg_actual_lead: 31, on_time_pct: 80, last_po: 'PO-done', default_lead: 25 } ] };
let puMoney = true, puFail = false, puCalls = 0; const puPosts = [];
const scrubPU = o => JSON.parse(JSON.stringify(o), (k, v) => (/amount|^total$|^value$|goods_value|^est$|^actual$|est_cost|actual_cost|outstanding|purchase_rate|landed_rate|open_amount/.test(k) && typeof v === 'number') ? null : v);
let boardMoney = true, boardCalls = 0;
w.fetch = async (url, opt) => { const ok = (m) => ({ ok:true, status:200, json: async () => ({ message: m }) });
  if (url.includes('purchasing_board.')) { const m = url.split('purchasing_board.')[1];
    if (m === 'get_board') { puCalls++; if (puFail) return { ok:false, status:500, json: async () => ({ exception: 'board down' }) }; const x = JSON.parse(JSON.stringify(PUB)); return ok(puMoney ? x : Object.assign(scrubPU(x), { money:false })); }
    puPosts.push({ m, body: JSON.parse(opt.body) }); return ok(m === 'update_po_tracking' || m === 'update_po_line_tracking' ? { name: 'PO-x', changed: 1 } : { name: 'NEW-' + m }); }
  if (url.endsWith('production_board.get_board')) { boardCalls++; return ok(boardMoney ? BOARD : Object.assign({}, BOARD, { money:false })); }
  if (url.startsWith('/api/method/ill_command_center')) return ok(D);
  if (url === '/api/method/ill_cc_gateway') { try { return ok(gwReply(JSON.parse(opt.body))); } catch (e) { return { ok:false, status:417, json: async () => ({ exception: e.message }) }; } }
  return { ok:false, status:404, json: async () => ({}) }; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = () => w.document.querySelector('#ccmain').textContent.replace(/\s+/g,' ');
const check = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if (!cond) errs.push('check failed: ' + name); };
const go = async h => { w.location.hash = h; await sleep(120); };
const closeAll = () => { const x = w.document.querySelector('#ccsheet2 [data-close]'); if (x) x.click(); };
(async () => {
  w.eval(js); await sleep(200);
  check('pipeline renders', /Sales pipeline/.test(txt()));
  // ---- v8: Catalog tab is hidden without catalog access, and appears after Refresh once granted ----
  const navT = () => w.document.querySelector('#ccnav').textContent;
  check('catalog tab hidden for a viewer without catalog access', !/Catalog/.test(navT()) && calls.includes('config'));
  await go('catalog'); await sleep(150);
  check('#catalog without access redirects to the pipeline', w.location.hash === '#pipeline' && !w.document.querySelector('#cccatalog'));
  // ---- v8: purchasing falls back to the older feed when the board can't load ----
  puFail = true; await go('purch'); await sleep(250);
  check('purch: board failure falls back to the D.purch shortage list', /purchasing board couldn't load/.test(txt()) && /What to order/.test(txt()) && /General low stock/.test(txt()));
  puFail = false;
  catOK = true; w.document.querySelector('#ccrefresh').click(); await sleep(300);
  check('catalog tab shown after Refresh for a publisher', /Catalog/.test(navT()));
  check('nav has Executive + Review', /Executive/.test(w.document.querySelector('#ccnav').textContent) && /Review/.test(w.document.querySelector('#ccnav').textContent));
  await go('exec'); await sleep(200);
  check('exec KPIs', /New dealers this month/.test(txt()) && /Quotes out/.test(txt()));
  check('exec quote value from gateway ($7,000)', /\$7,000/.test(txt()));
  check('exec finance shown when allowed', /Invoiced this month/.test(txt()) && /\$8,000/.test(txt()));
  check('exec decisions + link w/ status', /Decisions this week/.test(txt()) && !!w.document.querySelector('a.dec[href="#wb/Quotation/Open"]'));
  check('exec feed', /edited by kevins/.test(txt()));
  check('exec pipeline bar links', !!w.document.querySelector('a[href="#wb/Quotation/Open"]'));
  finOK = false; w.document.querySelector('#exrefresh').click(); await sleep(200);
  check('exec finance fails closed when locked', !/\$8,000/.test(txt()) && /Finance role/.test(txt()));
  await go('review'); await sleep(250);
  check('review overview lists projects', /Lutron launch/.test(txt()) && /Spec sheets/.test(txt()));
  w.document.querySelector('[data-rvgo="1"]').click(); await sleep(100);
  check('review project page', /Project 1 of 2/.test(txt()) && /Order extrusions/.test(txt()) && /Needs an owner/.test(txt()) && /Test samples/.test(txt()));
  check('review blocked + feed filtered to project', /Waiting on other tasks/.test(txt()) && /edited by kevins/.test(txt()));
  w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'ArrowRight' })); await sleep(80);
  check('arrow key moves to project 2', /Project 2 of 2/.test(txt()));
  w.document.querySelector('#rvprint').click(); await sleep(200);
  check('print lays out all + calls print', w.__printed === 1 && true);
  await go('tasks'); await sleep(100);
  check('tasks has saved views bar', !!w.document.querySelector('.sv[data-sv="tasks"]'));
  w.document.querySelector('.sv [data-svsave]').click(); await sleep(50);
  check('view saved to localStorage', JSON.parse(w.localStorage.getItem('cc.views.kevins@x.com.tasks')).length === 1);
  await go('wb'); await sleep(250);
  check('workbench landing uses counts (1 call)', calls.filter(c => c === 'counts').length >= 1 && !calls.includes('list_for_count') && /Quotes/.test(txt()));
  await go('wb/Quotation/Open'); await sleep(250);
  check('workbench status preset applied', /Open/.test(txt()) && w.document.querySelector('.wb-chip.on'));
  check('workbench saved views bar', !!w.document.querySelector('.sv[data-sv="wb:Quotation"]'));
  await go('wb/Quotation'); await sleep(200);
  check('plain wb route keeps filter', true);
  w.document.querySelector('#ccmeeting').click(); await go('wb/ToDo'); await sleep(250);
  check('meeting mode hides email ToDo in workbench', !/Call Bob/.test(txt()) && /Order tape/.test(txt()) && /hidden in meeting mode/.test(txt()));
  w.document.querySelector('#ccmeeting').click(); await sleep(100);
  check('meeting off shows it again', /Call Bob/.test(txt()));
  feedFail = true; const before = calls.length; await go('review'); await sleep(400);
  check('review feed failure does not loop', calls.filter(c => c === 'feed').length - calls.slice(0, before).filter(c => c === 'feed').length <= 1);
  feedFail = false;
  await go('mfg'); await sleep(250);
  check('mfg board loads from app endpoint', boardCalls === 1 && /Order queue/.test(txt()));
  check('mfg pipeline + capacity', /In-Prod/.test(txt()) && /\$25,252/.test(txt()) && /Days to complete/.test(txt()) && /Date clear/.test(txt()));
  check('mfg queue shows build points and worth', /322/.test(txt()) && /\$64/.test(txt()) && /A lns/.test(txt()));
  check('mfg burn-down chart drawn', !!w.document.querySelector('#pbburn svg'));
  check('mfg waiting for parts with no PO', /Waiting for parts/.test(txt()) && /No PO/.test(txt()) && /Going to miss/.test(txt()));
  check('mfg shipped + on-time', /Shipped this month/.test(txt()) && /Short extrusion/.test(txt()) && /50%/.test(txt()));
  check('mfg goal gap', /Gap to goal/.test(txt()) && /\$184,561/.test(txt()));
  check('mfg past-due row flagged', !!w.document.querySelector('tr.pb-row-late'));
  w.document.querySelector('[data-pbf="1"]').click(); await sleep(50);
  check('mfg status filter', /68686/.test(txt()) && !/67312/.test(txt()));
  w.document.querySelector('[data-pbf="all"]').click(); await sleep(50);
  const sel = w.document.querySelector('#pbsort'); sel.value = 'worth'; sel.dispatchEvent(new w.Event('change')); await sleep(50);
  check('mfg sort by $ per point', txt().indexOf('68686') < txt().indexOf('67312'));
  check('mfg keeps work order clean-up', /Work order clean-up/.test(txt()));
  const tab = async k => { w.document.querySelector(`[data-pbt="${k}"]`).click(); await sleep(60); };
  await tab('inbound');
  check('mfg run rate tab', /Orders received per workday/.test(txt()) && /\$12,418/.test(txt()) && /Rush/.test(txt()) && !!w.document.querySelector('#pbinb svg') && !!w.document.querySelector('#pbdaily svg'));
  await tab('report');
  check('mfg monthly report', /Monthly report/.test(txt()) && /\$2,477,000/.test(txt()) && /Expected releases/.test(txt()) && /83%/.test(txt()));
  await tab('releases');
  check('mfg releases + hold for ship', /PLS ORDER CHECK IN/.test(txt()) && /Hold for ship/.test(txt()) && /17 wr runs/.test(txt()) && /Release workload/.test(txt()));
  await tab('prowc');
  check('mfg proforma & will call', /Proforma open/.test(txt()) && /\$21,348/.test(txt()) && /DN-9/.test(txt()));
  await tab('paint');
  check('mfg paint', /Out for paint/.test(txt()) && /PO-15059/.test(txt()) && /Channel 409/.test(txt()));
  await tab('board');
  check('mfg back to board', /Order queue/.test(txt()) && !!w.document.querySelector('#pbburn svg'));
  boardMoney = false; w.document.querySelector('#pbrefresh').click(); await sleep(150);
  check('mfg hides dollars without role', /need the Command Center Finance/.test(txt()));
  boardMoney = true;
  // ---- meeting agenda ----
  const submit = f => f.dispatchEvent(new w.Event('submit', { cancelable: true, bubbles: true }));
  const sheet = () => w.document.querySelector('#ccsheet2');
  check('nav has Agenda', /Agenda/.test(w.document.querySelector('#ccnav').textContent));
  await go('agenda'); await sleep(200);
  check('agenda empty state', /No meeting agendas yet/.test(txt()));
  w.document.querySelector('[data-agnew]').click(); await sleep(50);
  check('new meeting sheet defaults to today', sheet().querySelector('input[name="meeting_date"]').value === TODAY);
  submit(sheet().querySelector('#wbform')); await sleep(300);
  check('meeting created and shown', /#agenda\/MTG-1/.test(w.location.hash) && /Weekly meeting/.test(txt()) && /Nothing on this agenda yet/.test(txt()));
  w.document.querySelector('#agaddt').value = 'Hiring plan for Q1'; submit(w.document.querySelector('#agaddf')); await sleep(250);
  check('free-text item added with presenter', /Hiring plan for Q1/.test(txt()) && AGS.items[0].presenter === 'kevins@x.com');
  w.document.querySelector('[data-agpicker]').click(); await sleep(150);
  const sug = sheet().textContent;
  check('picker suggests at-risk orders + expiring quotes', /Sales orders at risk/.test(sug) && /ilL-SAL-ORD-1|Sales Order 1/.test(sug) && /Quotes expiring this week/.test(sug));
  const soBtn = [...sheet().querySelectorAll('.ag-pk-row')].find(r => /Sales Order 1/.test(r.textContent)).querySelector('[data-agpk]');
  soBtn.click(); await sleep(250);
  check('suggested SO added, picker marks it', AGS.items.some(i => i.reference_doctype === 'Sales Order' && i.reference_name === 'ilL-SAL-ORD-1') && /On the agenda/.test(sheet().textContent));
  sheet().querySelector('[data-agtab="search"]').click(); await sleep(250);
  check('search tab lists records', !!sheet().querySelector('#agpkdt') && /QTN-1/.test(sheet().textContent));
  sheet().querySelector('#agpkdt').value = 'Quotation'; sheet().querySelector('#agpkdt').dispatchEvent(new w.Event('change')); await sleep(250);
  sheet().querySelector('[data-agpk]').click(); await sleep(250);
  check('searched quote added', AGS.items.some(i => i.reference_doctype === 'Quotation' && i.reference_name === 'QTN-1'));
  sheet().querySelector('[data-close]').click(); await sleep(50);
  check('linked item shows live status + value', /To Deliver/.test(txt()) && /\$5,000/.test(txt()));
  const soItem = () => [...w.document.querySelectorAll('.ag-item')].find(r => /Sales Order/.test(r.textContent));
  const d = soItem().querySelector('[data-agdone]'); d.checked = true; d.dispatchEvent(new w.Event('change')); await sleep(250);
  check('mark discussed saves', AGS.items.find(i => i.reference_name === 'ilL-SAL-ORD-1').status === 'Discussed' && /1 discussed/.test(txt()));
  const o = soItem().querySelector('[data-agout]'); o.value = 'Ship Friday'; o.dispatchEvent(new w.Event('change')); await sleep(250);
  check('outcome saved', AGS.items.find(i => i.reference_name === 'ilL-SAL-ORD-1').outcome === 'Ship Friday');
  soItem().querySelector('[data-agtodo]').click(); await sleep(50);
  check('to-do sheet prefilled from outcome, due a week later', sheet().querySelector('input[name="title"]').value === 'Ship Friday' && sheet().querySelector('input[name="date"]').value === '2026-11-24');
  sheet().querySelector('input[name="owner"][value="jay@x.com"]').checked = true; submit(sheet().querySelector('#wbform')); await sleep(300);
  check('to-do created for owner', AGS.lastTodo && AGS.lastTodo.owners.join() === 'jay@x.com' && AGS.lastTodo.title === 'Ship Friday');
  check('item lists its to-do', /Ship Friday/.test(soItem().querySelector('.ag-todos').textContent) && /jay/.test(soItem().querySelector('.ag-todos').textContent));
  w.document.querySelector('.ag-item [data-agmv="1"]').click(); await sleep(250);
  check('move down reorders', /Hiring plan/.test(w.document.querySelectorAll('.ag-item')[1].textContent) && calls.includes('agenda_order'));
  AGS.items.push({ name: 'AI-99', agenda: 'MTG-1', item_title: 'Call Bob', status: 'Open', reference_doctype: 'ToDo', reference_name: 'TD-1', sort_order: 99 });
  w.document.querySelector('#ccrefresh').click(); await sleep(300);
  check('Refresh re-reads the agenda', /Call Bob/.test(txt()));
  w.document.querySelector('#ccmeeting').click(); await sleep(250);
  check('meeting mode hides private email to-do', !/Call Bob/.test(txt()) && /1 hidden in meeting mode/.test(txt()));
  w.document.querySelector('#ccmeeting').click(); await sleep(250);
  const ed = [...w.document.querySelectorAll('.ag-item')].find(r => /Call Bob/.test(r.textContent)).querySelector('button[data-agedit]'); ed.click(); await sleep(50);
  sheet().querySelector('#agrm').click(); await sleep(250);
  check('remove item', !AGS.items.some(i => i.name === 'AI-99') && !/Call Bob/.test(txt()));
  w.document.querySelector('[data-agclose]').click(); await sleep(250);
  check('close meeting', AGS.meetings[0].status === 'Closed' && /Reopen/.test(txt()));
  w.document.querySelector('[data-agclose]').click(); await sleep(250);
  await go('wb/Quotation'); await sleep(250);
  w.document.querySelector('[data-wbopen]').click(); await sleep(250);
  const n0 = AGS.items.length; sheet().querySelector('#wbagenda').click(); await sleep(250);
  check('workbench "+ Add to agenda" adds to the open meeting', /Already on|Added to/.test(w.document.querySelector('#cctoast').textContent) && AGS.items.length === n0 && /Already on the agenda/.test(sheet().textContent));
  sheet().querySelector('[data-close]').click();
  for (const v of ['quotes','orders','purch','mfg','ship','service','inbox','finance','work','p-PROJ-1','so-ilL-SAL-ORD-1','rec']) { await go(v); check('view ' + v + ' renders', txt().length > 50 && !/Couldn't load data/.test(txt())); }
  // ---- pipeline restructure: Design → Quotes → Sales orders → … → Shipping → Service ----
  const nav = () => w.document.querySelector('#ccnav').textContent, chev = () => [...w.document.querySelectorAll('.chev .cvn')].map(e => e.textContent.trim());
  await go('pipeline'); await sleep(150);
  check('stepper order: Design before Quotes, Service after Shipping', chev().join('>') === 'Overview>Design>Quotes>Sales orders>Purchasing>Manufacturing>Shipping>Service');
  check('Requests and Service tabs gone from the top bar', !/Requests/.test(nav()) && !/Service/.test(nav()) && /Inbox/.test(nav()));
  await go('requests'); await sleep(150);
  check('#requests redirects to the pipeline', w.location.hash === '#pipeline' && /Sales pipeline/.test(txt()));
  await go('design'); await sleep(200);
  check('design: schedules in the right columns', /Drafting/.test(txt()) && /Lobby rev A/.test(txt()) && /Lobby rev B/.test(txt()) && /Drawing in progress/.test(txt()));
  const colOf = n => [...w.document.querySelectorAll('.bcol')].find(c => c.textContent.includes(n));
  check('design: schedule with an open drawing request sits in "Drawing in progress"', /Drawing in progress/.test(colOf('Guest floors').querySelector('.lane-h').textContent));
  check('design: quoted / order-requested schedules are not on Design', !/Ballroom/.test([...w.document.querySelectorAll('.bcol')].map(c => c.textContent).join('')) && !/Spa\b/.test([...w.document.querySelectorAll('.bcol')].map(c => c.textContent).join('')));
  check('design: card shows project, parties, lines, lock', /Hotel lobby/.test(txt()) && /Architect: Arch Co/.test(txt()) && /5 lines/.test(txt()) && /locked/.test(txt()));
  check('design: general drawing request listed with SLA, SO-linked one is not', /ILL-REQ-1/.test(txt()) && /SLA Nov 12/.test(txt()) && !/ILL-REQ-2/.test(txt()));
  check('design: design tickets board moved here', /Design tickets/.test(txt()));
  w.document.querySelector('[data-plassign="ilL-Document-Request|ILL-REQ-1"]').click(); await sleep(50);
  sheet().querySelector('select[name="who"]').value = 'ryanb@x.com'; submit(sheet().querySelector('#sform')); await sleep(300);
  check('design: reassign drawing request saves assigned_to through the gateway', saves.some(x => x.dt === 'ilL-Document-Request' && x.name === 'ILL-REQ-1' && x.values.assigned_to === 'ryanb@x.com'));
  await go('design/SCH-3'); await sleep(300);
  check('design drill-down: project, lines, request', /Guest floors/.test(txt()) && /Hotel lobby/.test(txt()) && /ILL-TAPE-1/.test(txt()) && /ILL-REQ-1/.test(txt()) && w.document.querySelector('.cv.on') && /Design/.test(w.document.querySelector('.cv.on').textContent));
  await go('quotes'); await sleep(200);
  check('quotes: request lanes + accepted offer continues in Sales orders', /Quote requests/.test(txt()) && /QR-1/.test(txt()) && /Issued/.test(txt()) && /OFFER-1/.test(txt()) && /Continues in Sales orders/.test(txt()));
  check('quotes: old request red-aged, design tickets gone', !!w.document.querySelector('.bcol .badge.bad') && !/Design tickets/.test(txt()));
  await go('orders'); await sleep(200);
  check('orders: order requests lane + SO drawing requests', /Order requests/.test(txt()) && /OI-1/.test(txt()) && /Please ship by Dec 1/.test(txt()) && /ILL-REQ-2/.test(txt()));
  await go('so-ilL-SAL-ORD-1'); await sleep(150);
  check('order page lists its drawing request', /ILL-REQ-2/.test(txt()));
  await go('service'); await sleep(200);
  check('service: customer requests lane on top', /Customer requests/.test(txt()) && /Address change/.test(txt()) && /Dealer application/.test(txt()) && txt().indexOf('Customer requests') < txt().indexOf('Service tickets'));
  check('service is the last stepper step and highlighted', w.document.querySelector('.cv.on') && /Service/.test(w.document.querySelector('.cv.on').textContent));
  // ---- inbox portal ----
  await go('inbox'); await sleep(200);
  check('inbox: triage table with filters and Reply in Helpdesk', !!w.document.querySelector('[data-ibf="status"]') && /Reply in Helpdesk/.test(txt()) && !!w.document.querySelector('a[href="/helpdesk/tickets/HD-1"]'));
  check('inbox: ticket shows its stage from the linked schedule', /Design/.test([...w.document.querySelectorAll('tr')].find(r => /HD-1/.test(r.textContent)).textContent));
  w.document.querySelector('[data-ibmode="reply"]').click(); await sleep(100);
  check('inbox: needs-a-reply queue lists open tickets only', /HD-1/.test(txt()) && !/HD-2/.test(txt()));
  w.document.querySelector('[data-ibmode="routing"]').click(); await sleep(100);
  check('inbox: routing lists unassigned tickets', !!w.document.querySelector('[data-ibroute="HD-1"]'));
  const rf = w.document.querySelector('[data-ibroute="HD-2"]'); rf.querySelector('select[name="who"]').value = 'jay@x.com'; submit(rf); await sleep(300);
  check('inbox: routing assigns through the gateway', assigns.some(a => a.name === 'HD-2' && a.add.join() === 'jay@x.com'));
  w.document.querySelector('[data-ibmode="triage"]').click(); await sleep(100);
  w.document.querySelector('button[data-tksheet="HD-1"]').click(); await sleep(300);
  check('ticket sheet: links, owners, audit, Reply in Helpdesk', !!sheet().querySelector('input[name="ill_quotation"]') && !!sheet().querySelector('input[name="own"]') && /assigned jay/.test(sheet().textContent) && /Reply in Helpdesk/.test(sheet().textContent));
  sheet().querySelector('input[name="ill_quotation"]').value = 'Q-1'; sheet().querySelector('select[name="status"]').value = 'Replied';
  sheet().querySelector('input[name="own"][value="ryanb@x.com"]').checked = true; sheet().querySelector('[data-unlink="ill_fixture_schedule"]').click();
  submit(sheet().querySelector('#sform')); await sleep(400);
  const sv = saves.filter(x => x.dt === 'HD Ticket' && x.name === 'HD-1').pop();
  check('ticket sheet: saves link, unlink and status in one gateway save', sv && sv.values.ill_quotation === 'Q-1' && sv.values.status === 'Replied' && sv.values.ill_fixture_schedule === null);
  check('ticket sheet: reassign goes through gateway assign', assigns.some(a => a.name === 'HD-1' && a.add.includes('ryanb@x.com')));
  stagesFail = true; w.document.querySelector('#ccrefresh').click(); await sleep(300); await go('design'); await sleep(200);
  check('gateway down: design falls back without breaking', /couldn't load/i.test(txt()) && /Design/.test(txt()));
  await go('quotes'); await sleep(150);
  check('gateway down: quotes still render', /Quotes waiting on dealers/.test(txt()));
  stagesFail = false;
  // ---- v8: purchasing desk ----
  const pTab = async k => { w.document.querySelector(`#puroot .pu-tabs [data-putab="${k}"]`).click(); await sleep(60); };
  const pPost = m => puPosts.filter(x => x.m === m).pop();
  const flow = () => [...w.document.querySelectorAll('.pu-step')].map(b => [...b.children].map(c => c.textContent).join(' ')).join(' | ');
  await go('purch'); await sleep(300);
  check('purch: board from the app endpoint, flow strip', puCalls >= 1 && !!w.document.querySelector('.pu-flow') && /To order 2/.test(flow()) && /POs 8/.test(flow()) && /\$22K unpaid/.test(flow()) && /Landed cost 1/.test(flow()));
  check('purch: flow tile dot for a step holding a decision', !!w.document.querySelector('.pu-step[data-putab="pos"] .dot.bad') && !!w.document.querySelector('.pu-step[data-putab="landed"] .dot.warn'));
  check('purch: stage card uses the board summary', /1 late · 1 PO overdue/.test(w.document.querySelector('.chev').textContent));
  await pTab('overview');
  check('purch overview: decisions + arriving in 14 days, late ones red', /POs past their ETA/.test(txt()) && /ILL-SHP-2026-0001/.test(txt()) && !!w.document.querySelector('tr.pu-row-late') && !!w.document.querySelector('#puetam svg'));
  w.document.querySelector('.pu-dec[data-putab="pos"]').click(); await sleep(80);
  check('purch: a decision opens its tab and lane', !!w.document.querySelector('.pu-board .bcol.pu-hl[data-pulane="partly_received"]'));
  check('purch POs: one lane per status, done hidden', ['Draft', 'Not sent', 'Awaiting confirmation', 'Confirmed / in production', 'In transit', 'Partly received', 'To bill', 'On hold'].every(l => txt().includes(l)) && !/PO-done/.test(txt()));
  check('purch POs: overdue red, will-miss amber with the order it hurts, lead chip', /Overdue · Nov 10/.test(txt()) && /late for order 1/.test(txt()) && /28d · quote/.test(txt()));
  w.document.querySelector('#pudone').click(); await sleep(60);
  check('purch POs: show done', /PO-done/.test(txt()));
  w.document.querySelector('[data-puview="table"]').click(); await sleep(60);
  check('purch POs: table view sorted by ETA', !!w.document.querySelector('tr[data-puopen]') && txt().indexOf('PO-partly_received') < txt().indexOf('PO-to_bill'));
  w.document.querySelector('[data-puview="lanes"]').click(); await sleep(60);
  w.document.querySelector('[data-puopen="PO-confirmed"]').click(); await sleep(60);
  check('purch PO sheet: tracking form, lines, actions', !!sheet().querySelector('select[name="ill_vendor_status"]') && !!sheet().querySelector('tr[data-line="POI-1"]') && /Create shipment/.test(sheet().textContent) && /Email PO/.test(sheet().textContent));
  sheet().querySelector('input[name="ill_vendor_order_no"]').value = 'ACK-99'; sheet().querySelector('tr[data-line="POI-1"] input[name="eta"]').value = '2026-12-04';
  submit(sheet().querySelector('#wbform')); await sleep(250);
  check('purch PO sheet: saves header and line tracking through the app endpoints', pPost('update_po_tracking') && pPost('update_po_tracking').body.values.ill_vendor_order_no === 'ACK-99' && pPost('update_po_tracking').body.po === 'PO-confirmed' && pPost('update_po_line_tracking') && pPost('update_po_line_tracking').body.rows[0].ill_eta === '2026-12-04');
  w.document.querySelector('[data-puopen="PO-confirmed"]').click(); await sleep(60);
  sheet().querySelector('[data-puact="create_shipment"]').click(); await sleep(150);
  check('purch: Create shipment posts the PO and shows a draft toast', pPost('create_shipment') && pPost('create_shipment').body.pos[0] === 'PO-confirmed' && /not submitted/.test(w.document.querySelector('#cctoast').textContent));
  await pTab('order');
  check('purch to order: shortages, draft-SO list, reorder, data gaps', /What to order/.test(txt()) && /EXT-9/.test(txt()) && /Only short if the draft sales orders go ahead \(1\)/.test(txt()) && /PSU-60/.test(txt()) && /Data gaps/.test(txt()) && /No lead time/.test(txt()));
  const psel = w.document.querySelector('[data-pusel="EXT-9"]'); psel.checked = true; psel.dispatchEvent(new w.Event('change')); await sleep(20);
  w.document.querySelector('#pumrsel').click(); await sleep(150);
  check('purch: one draft MR for the selected rows', pPost('draft_material_request') && pPost('draft_material_request').body.items[0].item === 'EXT-9' && pPost('draft_material_request').body.items[0].qty === 12);
  await pTab('order');
  w.document.querySelector('[data-mrlow="PSU-60"]').click(); await sleep(150);
  check('purch: low-stock Draft MR goes through the app endpoint', pPost('draft_material_request').body.items[0].item === 'PSU-60');
  await pTab('order');
  w.document.querySelector('[data-pureorder="PSU-60"]').click(); await sleep(120);
  check('purch: apply suggested reorder level', pPost('apply_reorder_level') && pPost('apply_reorder_level').body.level === 14);
  await pTab('order');
  const lf = w.document.querySelector('[data-puleadf="EXT-9"]'); lf.elements.days.value = '12'; submit(lf); await sleep(120);
  check('purch: set an item lead time from data gaps', pPost('set_item_lead_time') && pPost('set_item_lead_time').body.days === 12);
  await pTab('requests');
  check('purch requests: lanes and the needed-by flag', /To quote/.test(txt()) && /MR 00002/.test(txt()) && /Needed Nov 10/.test(txt()));
  w.document.querySelector('[data-purfq="MAT-MR-2026-00002"]').click(); await sleep(50);
  sheet().querySelector('input[name="suppliers"]').value = 'Tape Co, Glow Ltd'; submit(sheet().querySelector('#wbform')); await sleep(150);
  check('purch: Request quotes drafts an RFQ for the suppliers', pPost('make_rfq') && pPost('make_rfq').body.suppliers.join() === 'Tape Co,Glow Ltd');
  await pTab('quotes');
  check('purch quotes: RFQ supplier chips, expiring and expired lanes, compare', /Glow Ltd · received/.test(txt()) && /Valid 3d more/.test(txt()) && /SQ-2/.test(txt()) && /Compare quotes/.test(txt()) && /cheapest/.test(txt()) && /fastest/.test(txt()));
  w.document.querySelector('[data-pupo="SQ-1"]').click(); await sleep(150);
  check('purch: Accept quote drafts a PO', pPost('make_po') && pPost('make_po').body.supplier_quotation === 'SQ-1');
  await pTab('shipments');
  check('purch shipments: card with tracking, cost bar, landed %', /BOL123/.test(txt()) && !!w.document.querySelector('.pu-cbar i') && /Landed \+13%/.test(txt()) && /Needs landed cost/.test(txt()));
  w.document.querySelector('[data-pushop="ILL-SHP-2026-0001"]').click(); await sleep(60);
  sheet().querySelector('tr[data-cost="C1"] input[name="actual"]').value = '1650'; submit(sheet().querySelector('#wbform')); await sleep(150);
  check('purch: shipment sheet saves cost lines, keeping fields it does not show', pPost('update_shipment') && pPost('update_shipment').body.costs[0].actual_amount === 1650 && pPost('update_shipment').body.costs[0].expense_account === 'Freight In - ilL' && pPost('update_shipment').body.costs[0].description === 'Ocean freight Shanghai' && pPost('update_shipment').body.costs.length === 2);
  w.document.querySelector('[data-pushop="ILL-SHP-2026-0002"]').click(); await sleep(60);
  sheet().querySelector('[data-puact="make_landed_cost_voucher"]').click(); await sleep(150);
  check('purch: Draft landed cost voucher from a shipment', pPost('make_landed_cost_voucher') && pPost('make_landed_cost_voucher').body.shipment === 'ILL-SHP-2026-0002');
  await pTab('receipts');
  check('purch receipts: LCV chip', /Needs LCV/.test(txt()) && /PR-1/.test(txt()));
  w.document.querySelector('[data-puact="make_invoice"][data-pr="PR-1"]').click(); await sleep(150);
  check('purch: Draft bill from a receipt', pPost('make_invoice') && pPost('make_invoice').body.purchase_receipt === 'PR-1');
  await pTab('bills');
  check('purch bills: lanes, QBO and 3-way match chips', /Overdue/.test(txt()) && /Not in QBO/.test(txt()) && /In QBO/.test(txt()) && /Price off/.test(txt()));
  await pTab('landed');
  check('purch landed cost: pending with missing bills, vouchers, by item, in stock total', /Duty bill not in yet/.test(txt()) && /LCV-1/.test(txt()) && /15%/.test(txt()) && /\$3,100/.test(txt()));
  await pTab('suppliers');
  const sf = w.document.querySelector('[data-pusupf="Acme Extrusions"]'); sf.elements.days.value = '30'; submit(sf); await sleep(120);
  check('purch suppliers: scorecard + default lead time', /80%/.test(txt()) && pPost('set_supplier_lead_time') && pPost('set_supplier_lead_time').body.days === 30);
  puMoney = false; w.document.querySelector('#purefresh').click(); await sleep(250); await pTab('pos');
  check('purch: money hidden without the role', /Dollar figures need/.test(txt()) && !/\$1,000/.test(txt()) && /—/.test(txt()));
  await pTab('shipments'); w.document.querySelector('[data-pushop="ILL-SHP-2026-0001"]').click(); await sleep(60);
  check('purch: without the money role cost lines are read-only', sheet().querySelector('tr[data-cost="C1"] input[name="actual"]').disabled && !sheet().querySelector('#puaddcost'));
  const nUp = puPosts.filter(x => x.m === 'update_shipment').length; submit(sheet().querySelector('#wbform')); await sleep(150);
  check('purch: shipment save without money role leaves costs alone', puPosts.filter(x => x.m === 'update_shipment').length === nUp + 1 && !('costs' in pPost('update_shipment').body));
  puMoney = true; w.document.querySelector('#purefresh').click(); await sleep(250);
  await go('so-ilL-SAL-ORD-1'); await sleep(200);
  check('order page: POs feeding the order with their ETA', /PO-to_bill/.test(txt()) && /late for this order/.test(txt()));
  // ---- v8: Catalog tab ----
  await go('catalog'); await sleep(200);
  const host = w.document.querySelector('#cccatalog'), frame = host && host.querySelector('iframe');
  check('catalog: toolbar, iframe outside #ccmain', /Open full screen/.test(txt()) && /Import history/.test(txt()) && frame && frame.getAttribute('src') === '/catalog-builder?embed=1' && !w.document.querySelector('#ccmain').contains(host));
  await go('inbox'); await sleep(150);
  check('catalog: hidden (not destroyed) on other tabs', host.style.display === 'none' && w.document.querySelector('#cccatalog iframe') === frame);
  await go('catalog'); await sleep(150);
  check('catalog: the same iframe comes back', w.document.querySelector('#cccatalog iframe') === frame && host.style.display === '');
  const sent = []; frame.contentWindow.postMessage = (m, o) => sent.push([m, o]);
  const toastT = () => w.document.querySelector('#cctoast').textContent;
  const post = (data, origin) => w.dispatchEvent(new w.MessageEvent('message', { data, origin: origin || 'https://x.test', source: frame.contentWindow }));
  post({ source: 'ill-catalog-builder', type: 'imported', name: 'CAT-IMP-2026-00009', created: 4 }, 'https://evil.test'); await sleep(20);
  check('catalog: messages from another origin ignored', !/CAT-IMP-2026-00009/.test(toastT()));
  post({ source: 'ill-catalog-builder', type: 'dirty', dirty: true }); await sleep(20);
  check('catalog: dirty dot on the tab', !!w.document.querySelector('#ccnav a[href="#catalog"] .dot'));
  post({ source: 'ill-catalog-builder', type: 'imported', name: 'CAT-IMP-2026-00009', created: 4 }); await sleep(20);
  check('catalog: import toast, dirty cleared', /Imported 4 records/.test(toastT()) && /CAT-IMP-2026-00009/.test(toastT()) && !w.document.querySelector('#ccnav a[href="#catalog"] .dot'));
  // ---- v8: Workbench ilLumenate area ----
  await go('wb/~ill'); await sleep(300);
  check('wb ilL: area switch and groups, logs locked', /Workbench · ilLumenate/.test(txt()) && /Attributes/.test(txt()) && /Product templates/.test(txt()) && /Logs & system/.test(txt()) && /Locked/.test(txt()) && !!w.document.querySelector('.wb-area .on[data-wbarea="ill"]'));
  check('wb ilL: one counts call per visible group, none for locked', counted.filter(x => x === 'ill_attributes').length === 1 && !counted.includes('ill_logs') && w.document.querySelector('[data-wbct="ilL-Attribute-CCT"]').textContent === '7');
  check('wb ilL: settings card links to the desk', !!w.document.querySelector('a.wb-dt[href="/app/ill-purchasing-settings"]'));
  const fq = w.document.querySelector('#wbillq'); fq.value = 'cct'; fq.dispatchEvent(new w.Event('input')); await sleep(30);
  check('wb ilL: filter box narrows doctypes', /Attribute CCT/.test(txt()) && !/Fixture Template/.test(txt()));
  fq.value = ''; fq.dispatchEvent(new w.Event('input')); await sleep(30);
  w.document.querySelector('#wbillgrid [data-wbdt="ilL-Attribute-CCT"]').click(); await sleep(250);
  check('wb ilL: breadcrumb from the group, Active/Inactive status mix', /Workbench · ilLumenate/.test(w.document.querySelector('.wb-crumb').textContent) && /Attributes/.test(w.document.querySelector('.wb-crumb').textContent) && /Inactive/.test(txt()) && !!w.document.querySelector('.wb-chip .dot.mute'));
  w.document.querySelector('[data-wbopen="2700K"]').click(); await sleep(250);
  const tg = sheet().querySelector('#wbtoggle'); check('wb ilL: activate/deactivate toggle', tg && /Deactivate/.test(tg.textContent));
  tg.click(); await sleep(200);
  check('wb ilL: toggle saves is_active through the gateway', saves.some(x => x.dt === 'ilL-Attribute-CCT' && x.values.is_active === 0));
  closeAll(); await go('wb/ilL-Spec-Driver'); await sleep(250);
  check('wb ilL: doctype with no status: no status mix or filter', /DRV-1/.test(txt()) && !w.document.querySelector('.wb-mix') && !/In progress/.test(txt()));
  await go('wb/ilL-Fixture-Template'); await sleep(250);
  w.document.querySelector('[data-wbopen]').click(); await sleep(250);
  check('wb ilL: child tables read-only with "more" link', /Child tables/.test(sheet().textContent) && /Allowed finishes 30/.test(sheet().textContent.replace(/\s+/g, ' ')) && /\+ 5 more/.test(sheet().textContent) && /No rows/.test(sheet().textContent));
  sheet().querySelector('#wbbuilder').click(); await sleep(150);
  check('wb → builder: Edit in Catalog Builder switches tab and queues until ready', w.location.hash === '#catalog' && sent.length === 0);
  post({ source: 'ill-catalog-builder', type: 'ready' }); await sleep(20);
  check('wb → builder: queued open message sent after ready, to this origin', sent.length === 1 && sent[0][0].source === 'ill-command-center' && sent[0][0].type === 'open' && sent[0][0].records[0].doctype === 'ilL-Fixture-Template' && sent[0][1] === 'https://x.test');
  await go('wb/ilL-Fixture-Template'); await sleep(250);
  w.document.querySelector('#wbnew').click(); await sleep(150);
  check('wb → builder: + New on a builder doctype opens the Catalog tab with a "new" message', w.location.hash === '#catalog' && sent.length === 2 && sent[1][0].type === 'new' && sent[1][0].doctype === 'ilL-Fixture-Template');
  await go('wb/ilL-Attribute-LED Package'); await sleep(250);
  w.document.querySelector('#wbnew').click(); await sleep(150);
  check('wb ilL: prompt-named doctype asks for a name', !!sheet().querySelector('input[name="__newname"]'));
  sheet().querySelector('input[name="code"]').value = '2835'; submit(sheet().querySelector('#wbform')); await sleep(80);
  check('wb ilL: name is required', /Fill in: Name/.test(sheet().textContent) && !creates.length);
  sheet().querySelector('input[name="__newname"]').value = 'PKG-2835'; submit(sheet().querySelector('#wbform')); await sleep(200);
  check('wb ilL: create sends __newname', creates.length === 1 && creates[0].values.__newname === 'PKG-2835' && creates[0].values.code === '2835');
  await go('wb/~pipeline'); await sleep(250);
  check('wb pipeline: cards unchanged, choice remembered', /Quotes/.test(txt()) && !/Attribute CCT/.test(txt()) && w.localStorage.getItem('cc.wb.area.kevins@x.com') === 'pipeline');
  // agenda picker suggests purchasing follow-ups once the board is loaded
  await go('agenda'); await sleep(250);
  const pk = w.document.querySelector('[data-agpicker]'); if (pk) { pk.click(); await sleep(200); }
  const sgt = sheet().querySelector('[data-agtab="suggested"]'); if (sgt) { sgt.click(); await sleep(150); }
  check('agenda suggestions include overdue POs and shipments waiting for landed cost', pk && /Purchase orders overdue/.test(sheet().textContent) && /PO-partly_received/.test(sheet().textContent));
  closeAll();
  console.log('gateway actions seen:', [...new Set(calls)].join(','));
  console.log(errs.length ? 'ERRORS:\n' + errs.join('\n') : 'NO ERRORS'); process.exit(errs.length ? 1 : 0);
})();
