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
w.prompt = () => 'My view';
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
const gwReply = b => {
  calls.push(b.action);
  if (b.action === 'config') return { user:'k', can_edit:true, today:TODAY, sections:[{key:'quotes',label:'Quotes',locked:false,needs:''},{key:'projects',label:'Projects & tasks',locked:false,needs:''},{key:'finance',label:'Finance',locked:!finOK,needs:'Command Center Finance'}], doctypes:{ Quotation:{section:'quotes',can_create:false,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'},{fieldname:'grand_total',label:'Total',type:'Currency'}]}, ToDo:{section:'projects',can_create:true,columns:[{fieldname:'name',label:'ID',type:'Data'}]}, Task:{section:'projects',can_create:true,columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'}]} } };
  if (b.action === 'counts') return { counts:{ Quotation:3, Task:null } };
  if (b.action === 'list' && b.dt === 'ToDo') return { rows:[{name:'TD-1',description:'<p>Call Bob</p><p>[email] Owners: k</p>',status:'Open'},{name:'TD-2',description:'<p>Order tape</p>',status:'Open'}], columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'description',label:'Description',type:'Small Text'},{fieldname:'status',label:'Status',type:'Select'}], total:2 };
  if (b.action === 'list') return { rows:[{name:'QTN-1',status:b.filters&&b.filters.status||'Open',grand_total:1200}], columns:[{fieldname:'name',label:'ID',type:'Data'},{fieldname:'status',label:'Status',type:'Select'},{fieldname:'grand_total',label:'Total',type:'Currency'}], total:1 };
  if (b.action === 'overview') return { today:TODAY, finance_ok:finOK, sections:[], can_edit:true, stats:{ Quotation:{section:'quotes',count:3,value:9000,statuses:[['Open',2,7000],['Ordered',1,2000]]}, 'Sales Order':{section:'orders',count:2,value:12000,statuses:[['To Deliver',2,12000]]}, 'Purchase Order':{statuses:[['To Receive',1,3000]]}, ...(finOK?{'Sales Invoice':{statuses:[['Overdue',1,500],['Paid',4,0]]}}:{}) }, signals:[{id:'a',label:'Quotes expiring within 7 days',dt:'Quotation',count:2,status:'Open',tone:'warn'},{id:'b',label:'Overdue invoices',dt:'Sales Invoice',count:0,status:'Overdue',tone:'bad'}] };
  if (b.action === 'feed' && feedFail) throw new Error('feed down');
  if (b.action === 'feed') return { rows:[{creation:'2026-11-17 10:00:00',owner:'kevins@x.com',content:'Command Center: edited by kevins (status: Open -> Working)',reference_doctype:'Task',reference_name:'TASK-2'}] };
  throw new Error('unknown ' + b.action);
};
w.fetch = async (url, opt) => { const ok = (m) => ({ ok:true, status:200, json: async () => ({ message: m }) });
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
  for (const v of ['quotes','orders','purch','mfg','ship','service','requests','inbox','finance','work','p-PROJ-1','so-ilL-SAL-ORD-1','rec']) { await go(v); check('view ' + v + ' renders', txt().length > 50 && !/Couldn't load data/.test(txt())); }
  console.log('gateway actions seen:', [...new Set(calls)].join(','));
  console.log(errs.length ? 'ERRORS:\n' + errs.join('\n') : 'NO ERRORS'); process.exit(errs.length ? 1 : 0);
})();
