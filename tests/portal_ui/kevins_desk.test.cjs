// Kevin's Desk (Phase 1): the Pacific clock, where "now" falls in the schedule, and the NOW bar render.
// The schedule fixture is the real one, printed by kevins_desk/schedule.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');

const REPO = path.join(__dirname, '../..');
const SOURCE = fs.readFileSync(path.join(REPO, 'illumenate_lighting/kevins_desk/page/kd.js'), 'utf8');
const SCHEDULE = JSON.parse(execFileSync('python3', ['-B', '-c',
  'import json; from illumenate_lighting.kevins_desk import schedule; print(json.dumps(schedule.payload()))'], { cwd: REPO }));

function load(extra = {}) {
  const context = { Intl, Date, ...extra };
  context.window = context;
  vm.runInNewContext(SOURCE, context);
  return context;
}

const core = load().KDCore;
const at = (iso) => core.pacific(new Date(iso), SCHEDULE.tz);
const where = (iso) => core.locate(SCHEDULE.days, at(iso));

test('the clock is Pacific whatever the machine says', () => {
  const now = at('2026-11-20T18:42:30Z'); // Fri 10:42:30 PST
  assert.equal(now.dow, 5);
  assert.equal(Math.floor(now.min), 10 * 60 + 42);
  assert.equal(now.clock, '10:42 am');
  assert.equal(now.date, 'Fri, Nov 20');
  assert.equal(at('2026-07-06T15:00:00Z').clock, '8:00 am'); // PDT in summer
});

test('inside a block: current, time left, progress and next', () => {
  const w = where('2026-11-17T18:42:00Z'); // Tue 10:42
  assert.equal(w.state, 'block');
  assert.equal(w.current.title, 'Ops block');
  assert.equal(w.current.hat, 'ops');
  assert.equal(core.fmtLeft(w.left), '1h 18m');
  assert.ok(w.progress > 0.25 && w.progress < 0.27);
  assert.equal(w.next.block.title, 'Lunch');
  assert.equal(w.next.offset, 0);
});

test('Monday kickoff, day themes and Friday review', () => {
  assert.equal(where('2026-11-16T18:30:00Z').current.title, 'Team kickoff'); // Mon 10:30
  assert.equal(where('2026-11-16T18:50:00Z').current.title, 'Ops block'); // Mon 10:50
  assert.equal(where('2026-11-19T22:00:00Z').current.hat, 'systems'); // Thu 2:00 pm
  const fri = where('2026-11-20T23:10:00Z'); // Fri 3:10 pm
  assert.equal(fri.current.title, 'Weekly review');
  assert.equal(fri.next.block.title, 'Customer block 2');
});

test('before, after and weekend point at the next block', () => {
  const early = where('2026-11-17T15:05:00Z'); // Tue 7:05
  assert.equal(early.state, 'before');
  assert.equal(core.fmtLeft(early.startsIn), '25m');
  const late = where('2026-11-18T01:30:00Z'); // Tue 5:30 pm
  assert.equal(late.state, 'after');
  assert.deepEqual([late.next.dow, late.next.offset, late.next.block.title], [3, 1, 'Triage & plan']);
  const friNight = where('2026-11-21T02:00:00Z'); // Fri 6:00 pm -> Monday
  assert.deepEqual([friNight.next.dow, friNight.next.offset], [1, 3]);
  const sat = where('2026-11-21T19:00:00Z');
  assert.equal(sat.state, 'weekend');
  assert.equal(sat.next.dow, 1);
  assert.equal(where('2026-11-17T23:29:59Z').current.title.startsWith('Deep work'), true); // Tue 3:29:59 pm
  assert.equal(where('2026-11-17T23:30:00Z').current.title, 'Customer block 2'); // boundary belongs to the next block
});

test('time left rounds up and never goes negative', () => {
  assert.equal(core.fmtLeft(0.2), '1m');
  assert.equal(core.fmtLeft(60), '1h');
  assert.equal(core.fmtLeft(-3), '0m');
});

const IDS = ['cc', 'kdclock', 'kdnow', 'kdtoday', 'kdweek', 'kdwho', 'kdcc', 'kdstamp', 'kdrefresh', 'kdsignals', 'kdpipe', 'kdtodos'];

function page({ when = '2026-11-17T18:42:00Z', api, fetch } = {}) {
  const nodes = {}, listeners = {};
  IDS.forEach(id => { nodes[id] = { innerHTML: '', textContent: '', href: '', disabled: false, addEventListener: (ev, fn) => { listeners[id + ':' + ev] = fn; } }; });
  const timers = [], requests = [];
  const RealDate = Date;
  class FixedDate extends RealDate { constructor(...a) { super(...(a.length ? a : [when])); } }
  const ctx = load({
    Date: FixedDate,
    KD_BOOT: { user: 'kevins@example.com', first_name: 'Kevin', schedule: SCHEDULE, command_center: '/command-center', api },
    document: { hidden: false, title: '', getElementById: id => nodes[id] || null, addEventListener() {} },
    setInterval: (fn, ms) => timers.push(ms),
    fetch: fetch && ((url, opts) => { requests.push(url); return fetch(url, opts); }),
    Promise,
  });
  return { ctx, nodes, timers, requests, listeners };
}

test('the page renders the NOW bar, today and the week into the Command Center shell', () => {
  const { ctx, nodes, timers } = page();
  assert.match(nodes.kdnow.innerHTML, /Ops block/);
  assert.match(nodes.kdnow.innerHTML, /1h 18m/);
  assert.match(nodes.kdnow.innerHTML, /Next · 12:00/);
  assert.match(nodes.kdnow.innerHTML, /data-hat="ops"/);
  assert.match(nodes.kdtoday.innerHTML, /class="kd-row now" aria-current="true">\s*<span class="kd-time">10:15–12:00/);
  assert.match(nodes.kdtoday.innerHTML, /Deep-work theme: Product &amp; Engineering/);
  assert.match(nodes.kdweek.innerHTML, /10:00 team kickoff \(45 min\)/);
  assert.match(nodes.kdweek.innerHTML, /3:00 weekly review \(30 min\)/);
  assert.equal(nodes.kdclock.textContent, 'Tue, Nov 17 · 10:42 am Pacific');
  assert.equal(nodes.kdwho.textContent, 'Signed in as kevins@example.com');
  assert.equal(ctx.document.title, "Ops block · 1h 18m · Kevin's Desk");
  assert.deepEqual(timers, [15000, 300000]);
});

const API = { pipeline: '/api/method/x.pipeline', signals: '/api/method/x.signals' };
const PIPE = {
  today: '2026-11-17', built_at: '2026-11-17T10:42:05', cached: true, todos_error: null,
  widgets: [
    { key: 'so_late', label: 'Sales orders past delivery date', stack: 1, dt: 'Sales Order', total: 1, error: null,
      items: [{ id: 'Sales Order:SO-1', dt: 'Sales Order', name: 'SO-1', title: 'SO-1', party: 'Acme <b>', date: '2026-11-12', amount: 1200.4, flag: 'late', url: '/desk/sales-order/SO-1', stack: 1 }] },
    { key: 'quotes_open', label: 'Quotations open more than 3 days', stack: 2, dt: 'Quotation', total: 30, error: null,
      items: [{ id: 'Quotation:Q-1', dt: 'Quotation', name: 'Q-1', title: 'Q-1', party: 'Bolt', date: '2026-11-01', amount: 99, flag: null, url: '/desk/quotation/Q-1', stack: 2 }] },
    { key: 'po_late', label: 'Purchase orders past their date', stack: 1, dt: 'Purchase Order', total: 0, error: "Couldn't load", items: [] },
    { key: 'tickets', label: 'Open tickets', stack: 4, dt: 'HD Ticket', total: 0, error: null, items: [] },
  ],
  todos: [
    { name: 'T-late', title: 'Send drawings', url: '/desk/todo/T-late', date: '2026-11-02', flag: 'late', bucket: 'overdue', priority: 'High', tags: [] },
    { name: 'T-today', title: 'Call Bob & Sue', url: '/desk/todo/T-today', date: '2026-11-17', flag: 'today', bucket: 'today', priority: 'Medium', tags: ['email'],
      gmail: 'https://mail.google.com/mail/u/0/#inbox/abc', ref: { dt: 'Quotation', name: 'QTN 7', url: '/desk/quotation/QTN%207' } },
    { name: 'T-up', title: 'Plan Q1', url: '/desk/todo/T-up', date: '2026-11-25', flag: null, bucket: 'upcoming', tags: [] },
  ],
};
const SIGNALS = { signals: [{ id: 'so_late', label: 'Open orders past delivery date', dt: 'Sales Order', count: 2, tone: 'bad' }] };
const ok = body => Promise.resolve({ ok: true, json: () => Promise.resolve({ message: body }) });

test('pipeline widgets, ToDos and decisions render from the desk endpoints', async () => {
  const { ctx, nodes, requests, listeners } = page({ api: API, fetch: url => ok(url.includes('signals') ? SIGNALS : PIPE) });
  await ctx.KDPage.ready;
  assert.deepEqual(requests, [API.pipeline, API.signals]);
  const pipe = nodes.kdpipe.innerHTML;
  assert.ok(pipe.indexOf('data-widget="so_late"') < pipe.indexOf('data-widget="quotes_open"'));
  assert.match(pipe, /1 · Customer blocked · order at risk/);
  assert.match(pipe, /<a href="\/desk\/sales-order\/SO-1" target="_blank" rel="noopener">SO-1<\/a>/);
  assert.match(pipe, /Acme &lt;b&gt;/);
  assert.match(pipe, /\$1,200/);
  assert.match(pipe, /<span class="badge bad">Late<\/span>/);
  assert.match(pipe, /Showing 1 of 30 · <a href="\/command-center#wb\/Quotation"/);
  assert.match(pipe, /Couldn't load this list/);
  assert.match(pipe, /Nothing here right now/);
  const todos = nodes.kdtodos.innerHTML;
  assert.match(todos, /1 overdue · 1 due today · 3 open/);
  assert.ok(todos.indexOf('Send drawings') < todos.indexOf('Call Bob &amp; Sue'));
  assert.match(todos, /<details class="more kd-fold"><summary>Upcoming \(1\)<\/summary>/);
  assert.match(todos, /href="https:\/\/mail.google.com\/mail\/u\/0\/#inbox\/abc"[^>]*>Open in Gmail/);
  assert.match(todos, /href="\/desk\/quotation\/QTN%207"[^>]*>Quotation QTN 7/);
  assert.match(nodes.kdsignals.innerHTML, /<a class="dec bad" href="\/command-center#wb\/Sales%20Order"[^>]*><span class="n">2<\/span>/);
  assert.equal(nodes.kdstamp.textContent, 'Updated 10:42 am (cached)');
  assert.equal(nodes.kdrefresh.textContent, 'Refresh');
  listeners['kdrefresh:click']();
  await new Promise(r => setTimeout(r, 0));
  assert.deepEqual(requests.slice(2), [API.pipeline + '?refresh=1', API.signals + '?refresh=1']);
});

test('a failed load says so instead of showing an empty desk', async () => {
  const { ctx, nodes } = page({ api: API, fetch: url => url.includes('signals') ? Promise.reject(new Error('offline')) : Promise.resolve({ ok: false, status: 404 }) });
  await ctx.KDPage.ready;
  assert.match(nodes.kdpipe.innerHTML, /Couldn't load the pipeline \(HTTP 404\)/);
  assert.match(nodes.kdtodos.innerHTML, /Couldn't load your ToDos/);
  assert.match(nodes.kdsignals.innerHTML, /decisions unavailable \(offline\)/);
  assert.equal(nodes.kdstamp.textContent, 'Not updated');
});
