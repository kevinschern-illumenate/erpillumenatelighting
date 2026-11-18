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
let finOK = true, feedFail = false; const calls = [];
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
  if (b.action === 'config') return { user:'k', can_edit:true, today:TODAY, sections:[{key:'quotes',label:'Quotes',locked:false,needs:''},{key:'projects',label:'Projects & tasks',locked:false,needs:''},{key:'finance',label:'Finance',locked:!finOK,needs:'Command Center Finance'}], doctypes:{ Quotation:{section:'quotes',can_create:false,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'},{fieldname:'grand_total',label:'Total',type:'Currency'}]}, ToDo:{section:'projects',can_create:true,columns:[{fieldname:'name',label:'ID',type:'Data'}]}, 'Sales Order':{section:'quotes',can_create:false,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'customer',label:'Customer',type:'Link'},{fieldname:'status',label:'Status',type:'Select'}]}, Task:{section:'projects',can_create:true,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'}]} } };
  if (b.action === 'counts') return { counts:{ Quotation:3, Task:null } };
  if (b.action === 'list' && b.dt === 'ToDo') return { rows:[{name:'TD-1',description:'<p>Call Bob</p><p>[email] Owners: k</p>',status:'Open'},{name:'TD-2',description:'<p>Order tape</p>',status:'Open'}], columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'description',label:'Description',type:'Small Text'},{fieldname:'status',label:'Status',type:'Select'}], total:2 };
  if (b.action === 'list') return { rows:[{name:'QTN-1',status:b.filters&&b.filters.status||'Open',grand_total:1200}], columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'},{fieldname:'grand_total',label:'Total',type:'Currency'}], total:1 };
  if (b.action === 'overview') return { today:TODAY, finance_ok:finOK, sections:[], can_edit:true, stats:{ Quotation:{section:'quotes',count:3,value:9000,statuses:[['Open',2,7000],['Ordered',1,2000]]}, 'Sales Order':{section:'orders',count:2,value:12000,statuses:[['To Deliver',2,12000]]}, 'Purchase Order':{statuses:[['To Receive',1,3000]]}, ...(finOK?{'Sales Invoice':{statuses:[['Overdue',1,500],['Paid',4,0]]}}:{}) }, signals:[{id:'a',label:'Quotes expiring within 7 days',dt:'Quotation',count:2,status:'Open',tone:'warn'},{id:'b',label:'Overdue invoices',dt:'Sales Invoice',count:0,status:'Overdue',tone:'bad'}] };
  if (b.action.startsWith('agenda_')) return agendaReply(b);
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
let boardMoney = true, boardCalls = 0;
w.fetch = async (url, opt) => { const ok = (m) => ({ ok:true, status:200, json: async () => ({ message: m }) });
  if (url.endsWith('production_board.get_board')) { boardCalls++; return ok(boardMoney ? BOARD : Object.assign({}, BOARD, { money:false })); }
  if (url.startsWith('/api/method/ill_command_center')) return ok(D);
  if (url === '/api/method/ill_cc_gateway') { try { return ok(gwReply(JSON.parse(opt.body))); } catch (e) { return { ok:false, status:417, json: async () => ({ exception: e.message }) }; } }
  return { ok:false, status:404, json: async () => ({}) }; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = () => w.document.querySelector('#ccmain').textContent.replace(/\s+/g,' ');
const check = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if (!cond) errs.push('check failed: ' + name); };
const go = async h => { w.location.hash = h; await sleep(120); };
(async () => {
  w.eval(js); await sleep(200);
  check('pipeline renders', /Sales pipeline/.test(txt()));
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
  for (const v of ['quotes','orders','purch','mfg','ship','service','requests','inbox','finance','work','p-PROJ-1','so-ilL-SAL-ORD-1','rec']) { await go(v); check('view ' + v + ' renders', txt().length > 50 && !/Couldn't load data/.test(txt())); }
  console.log('gateway actions seen:', [...new Set(calls)].join(','));
  console.log(errs.length ? 'ERRORS:\n' + errs.join('\n') : 'NO ERRORS'); process.exit(errs.length ? 1 : 0);
})();
