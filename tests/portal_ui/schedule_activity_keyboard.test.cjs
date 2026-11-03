// Plans 3.11, 3.13 and 3.14: the schedule activity timeline, keyboard shortcuts and the remembered
// dealer pricing toggle.
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const ACTIVITY = `<div id="scheduleActivitySection"><button id="scheduleActivityToggle" aria-expanded="false">Show activity</button>
  <div id="scheduleActivity" hidden><ol id="scheduleActivityList"></ol><p id="scheduleActivityStatus"></p>
  <button id="scheduleActivityMore" hidden>Show more</button></div></div>`;

const LINES = `<button id="addLine" data-toggle="modal" data-target="#addLineModal">Add</button>
  <input type="search" id="lineFilter"><span id="lineFilterStatus"></span>
  <button type="button" data-shortcuts-open>Shortcuts</button>
  <table class="fixture-lines-table"><tbody>
    <tr data-line-idx="0" data-line-key="K0"><td><button class="drag-handle-btn">⋮</button></td><td>Linear A1 Lobby</td></tr>
    <tr data-line-idx="1" data-line-key="K1"><td><button class="drag-handle-btn">⋮</button></td><td>Downlight B2 Office</td></tr>
    <tr data-line-idx="2" data-line-key="K2"><td><button class="drag-handle-btn">⋮</button></td><td>Linear C3 Office</td></tr>
  </tbody></table>
  <textarea id="notes"></textarea><select id="pick"><option>a</option></select><div id="rich" contenteditable="true"><span id="inner">x</span></div>
  <div class="modal show" id="openModal"></div>
  <div id="scheduleShortcutsHelp" hidden><button data-shortcuts-close>×</button></div>`;

const windows = [];
afterEach(() => { while (windows.length) windows.pop().close(); });

function page(context, body, scripts, { storage = {}, setup } = {}) {
  const json = JSON.stringify({ schedule_name: 'S-1', i18n: {}, ...context }).replace(/</g, '\\u003c');
  const dom = new JSDOM(`<body>${body}<script type="application/json" id="schedule-context">${json}</script></body>`, {
    runScripts: 'outside-only',
    url: 'https://portal.test/portal/schedules/S-1',
  });
  const w = dom.window;
  windows.push(w);
  const requests = [];
  w.frappe = { call: args => requests.push(args), msgprint() {} };
  w.__ = text => text;
  for (const [key, value] of Object.entries(storage)) w.sessionStorage.setItem(key, value);
  if (setup) setup(w);
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + scripts.map(read).join('\n'));
  return { w, document: w.document, requests };
}

function press(w, target, key, extra = {}) {
  const event = new w.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...extra });
  target.dispatchEvent(event);
  return event.defaultPrevented;
}

test('the template wires the timeline, shortcuts and pricing preference behind their flags', () => {
  assert.match(TEMPLATE, /"activity_timeline": \(activity_timeline_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"keyboard_shortcuts": \(keyboard_shortcuts_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"dealer_pricing_on": \(dealer_pricing_on \| default\(false\)\) if show_dealer_pricing else false/);
  assert.match(TEMPLATE, /\{% if activity_timeline_enabled \| default\(false\) %\}[\s\S]{0,200}id="scheduleActivitySection"/);
  assert.match(TEMPLATE, /\{% if keyboard_shortcuts_enabled \| default\(false\) %\}[\s\S]{0,200}id="scheduleShortcutsHelp"[^>]*role="dialog"/);
  assert.match(TEMPLATE, /aria-keyshortcuts="Alt\+ArrowUp Alt\+ArrowDown"/);
  assert.match(TEMPLATE, /"New since you opened this page": _\("New since you opened this page"\)/);
});

test('the timeline loads on open, renders text only and marks entries newer than the page', () => {
  const { w, document, requests } = page({ activity_timeline: true, schedule_modified: '2026-11-03 10:00:00' }, ACTIVITY, ['activity']);
  document.getElementById('scheduleActivityToggle').click();
  assert.equal(document.getElementById('scheduleActivity').hidden, false);
  assert.equal(document.getElementById('scheduleActivityToggle').getAttribute('aria-expanded'), 'true');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'illumenate_lighting.illumenate_lighting.portal.schedule_activity.schedule_activity');
  assert.deepEqual(requests[0].args, { schedule_name: 'S-1', start: 0, limit: 20 });
  requests[0].callback({ message: { success: true, has_more: true, next_start: 20, entries: [
    { kind: 'line_added', title: 'Line added <b>x</b>', detail: 'A1', at: '2026-11-03 10:05:00', at_display: 'Nov 3', by_name: 'Pat' },
    { kind: 'status', title: 'Status changed', at: '2026-11-02 09:00:00' },
  ] } });
  requests[0].always();
  const items = document.querySelectorAll('#scheduleActivityList li');
  assert.equal(items.length, 2);
  assert.equal(items[0].querySelector('.ill-activity-title').textContent, 'Line added <b>x</b>');
  assert.equal(items[0].querySelector('b'), null);
  assert.equal(items[0].querySelector('.ill-activity-meta').textContent, 'Nov 3 · Pat');
  assert.ok(items[0].classList.contains('is-new'));
  assert.ok(!items[1].classList.contains('is-new'));
  assert.equal(document.getElementById('scheduleActivityMore').hidden, false);

  document.getElementById('scheduleActivityMore').click();
  assert.deepEqual(requests[1].args, { schedule_name: 'S-1', start: 20, limit: 20 });
  requests[1].callback({ message: { success: true, has_more: false, entries: [{ kind: 'export', title: 'Exported', at: '2026-11-01' }] } });
  requests[1].always();
  assert.equal(document.querySelectorAll('#scheduleActivityList li').length, 3);
  assert.equal(document.getElementById('scheduleActivityMore').hidden, true);

  document.getElementById('scheduleActivityToggle').click();
  assert.equal(document.getElementById('scheduleActivity').hidden, true);
  w.ScheduleActivity.open(true);
  assert.equal(requests.length, 3);
  requests[2].callback({ message: { success: false, error: 'Not permitted' } });
  assert.equal(document.getElementById('scheduleActivityStatus').textContent, 'Not permitted');
});

test('the timeline does nothing when switched off', () => {
  const { document, requests } = page({ activity_timeline: false }, ACTIVITY, ['activity']);
  document.getElementById('scheduleActivityToggle').click();
  assert.equal(requests.length, 0);
  assert.equal(document.getElementById('scheduleActivity').hidden, true);
});

function keyboardPage(context = {}, options = {}) {
  const added = [];
  const moved = [];
  const result = page({ keyboard_shortcuts: true, ...context }, LINES, ['keyboard'], {
    ...options,
    setup: w => { w.moveScheduleLine = (from, to) => moved.push([from, to]); },
  });
  result.document.getElementById('addLine').addEventListener('click', () => added.push(true));
  return { ...result, added, moved };
}

test('/ focuses the filter, which hides non-matching rows; Esc clears it', () => {
  const { w, document } = keyboardPage();
  assert.equal(press(w, document.body, '/'), true);
  const input = document.getElementById('lineFilter');
  assert.equal(document.activeElement, input);
  input.value = 'office';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  const hidden = [...document.querySelectorAll('tbody tr')].map(row => row.hidden);
  assert.deepEqual(hidden, [true, false, false]);
  assert.equal(document.getElementById('lineFilterStatus').textContent, '2 line(s) shown');
  assert.equal(press(w, input, 'Escape'), true);
  assert.equal(input.value, '');
  assert.deepEqual([...document.querySelectorAll('tbody tr')].map(row => row.hidden), [false, false, false]);
});

test('n adds a line only when no dialog is open; ? toggles the help and Esc closes it then dialogs', () => {
  const { w, document, added } = keyboardPage();
  const modal = document.getElementById('openModal');
  assert.equal(press(w, document.body, 'n'), false);
  assert.equal(added.length, 0);
  assert.equal(press(w, document.body, 'Escape'), true);
  assert.ok(!modal.classList.contains('show'));
  assert.equal(press(w, document.body, 'n'), true);
  assert.equal(added.length, 1);

  const help = document.getElementById('scheduleShortcutsHelp');
  assert.equal(press(w, document.body, '?', { shiftKey: true }), true);
  assert.equal(help.hidden, false);
  assert.equal(document.activeElement, help.querySelector('[data-shortcuts-close]'));
  assert.equal(press(w, document.activeElement, 'n'), false);
  assert.equal(added.length, 1);
  assert.equal(press(w, document.activeElement, 'Escape'), true);
  assert.equal(help.hidden, true);
  document.querySelector('[data-shortcuts-open]').click();
  assert.equal(help.hidden, false);
  help.querySelector('[data-shortcuts-close]').click();
  assert.equal(help.hidden, true);
});

test('shortcuts never fire while typing or with Ctrl/⌘ held', () => {
  const { w, document, added } = keyboardPage();
  document.getElementById('openModal').classList.remove('show');
  for (const id of ['lineFilter', 'notes', 'pick', 'rich', 'inner']) {
    const target = document.getElementById(id);
    assert.equal(w.ScheduleKeyboard.typing(target), true, id);
    assert.equal(press(w, target, 'n'), false, id);
    assert.equal(press(w, target, '/'), false, id);
    assert.equal(press(w, target, '?'), false, id);
  }
  assert.equal(press(w, document.body, 'n', { ctrlKey: true }), false);
  assert.equal(press(w, document.body, 'n', { metaKey: true }), false);
  assert.equal(added.length, 0);
  assert.equal(document.getElementById('scheduleShortcutsHelp').hidden, true);
});

test('arrows move between rows and Alt+arrows reorder through moveScheduleLine', () => {
  const { w, document, moved } = keyboardPage();
  const handles = document.querySelectorAll('.drag-handle-btn');
  handles[0].focus();
  assert.equal(press(w, handles[0], 'ArrowDown'), true);
  assert.equal(document.activeElement, handles[1]);
  assert.equal(press(w, handles[1], 'ArrowUp'), true);
  assert.equal(document.activeElement, handles[0]);
  assert.equal(press(w, handles[0], 'ArrowUp'), true);
  assert.equal(document.activeElement, handles[0]);

  assert.equal(press(w, handles[1], 'ArrowDown', { altKey: true }), true);
  assert.deepEqual(moved, [[1, 2]]);
  assert.equal(w.sessionStorage.getItem('ill-kbd-focus:S-1'), 'K1');
  assert.equal(press(w, handles[0], 'ArrowUp', { altKey: true }), true);
  assert.deepEqual(moved, [[1, 2]]);
});

test('focus returns to the moved line after the reload, and the kill switch turns it all off', () => {
  const after = keyboardPage({}, { storage: { 'ill-kbd-focus:S-1': 'K2' } });
  assert.equal(after.document.activeElement, after.document.querySelectorAll('.drag-handle-btn')[2]);
  assert.equal(after.w.sessionStorage.getItem('ill-kbd-focus:S-1'), null);

  const off = keyboardPage({ keyboard_shortcuts: false });
  off.document.getElementById('openModal').classList.remove('show');
  assert.equal(press(off.w, off.document.body, 'n'), false);
  assert.equal(press(off.w, off.document.body, '/'), false);
  assert.equal(off.added.length, 0);
});

const PRICING = '<button id="dealerPricingBtn">Show Dealer Pricing</button>';

test('the pricing toggle is saved per user and turned back on at load', () => {
  const on = page({ dealer_pricing_on: true }, PRICING, ['pricing']);
  assert.equal(on.requests.length, 1);
  assert.equal(on.requests[0].method, 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_dealer_pricing');

  const off = page({ dealer_pricing_on: false }, PRICING, ['pricing']);
  assert.equal(off.requests.length, 0);
  off.w.toggleDealerPricing();
  const saved = off.requests.find(r => r.method.endsWith('user_preferences.set_show_dealer_pricing'));
  assert.equal(saved.type, 'POST');
  assert.deepEqual(saved.args, { show: 1 });

  const missing = page({ dealer_pricing_on: true }, '', ['pricing']);
  assert.equal(missing.requests.length, 0);
});
