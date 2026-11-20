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

test('the page renders the NOW bar, today and the week into the Command Center shell', () => {
  const nodes = {};
  ['cc', 'kdclock', 'kdnow', 'kdtoday', 'kdweek', 'kdwho', 'kdcc'].forEach(id => { nodes[id] = { innerHTML: '', textContent: '', href: '' }; });
  const timers = [];
  const RealDate = Date;
  class FixedDate extends RealDate { constructor(...a) { super(...(a.length ? a : ['2026-11-17T18:42:00Z'])); } }
  const page = load({
    Date: FixedDate,
    KD_BOOT: { user: 'kevins@example.com', first_name: 'Kevin', schedule: SCHEDULE, command_center: '/command-center' },
    document: { hidden: false, title: '', getElementById: id => nodes[id] || null, addEventListener() {} },
    setInterval: (fn, ms) => timers.push(ms),
  });
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
  assert.equal(page.document.title, "Ops block · 1h 18m · Kevin's Desk");
  assert.deepEqual(timers, [15000]);
});
