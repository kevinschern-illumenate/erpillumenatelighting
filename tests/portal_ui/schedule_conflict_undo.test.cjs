// Plans 3.10 and 3.12: the Undo toast after a destructive line action, and the collaborator
// conflict notice ("Updated by <user> at <time>") instead of a generic error.
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const opened = [];
afterEach(() => { while (opened.length) opened.pop().window.close(); });

function page(context = {}, { storage = null, scripts = ['conflict', 'undo'] } = {}) {
  const json = JSON.stringify({ schedule_name: 'S-1', schedule_modified: '2026-11-03 10:00:00', undo: true, i18n: {}, ...context })
    .replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><div class="ill-page ill-page--schedule"><div id="scheduleConflictNotice" hidden></div></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  opened.push(dom);
  const w = dom.window;
  const requests = [];
  const hidden = [];
  w.frappe = { call: args => requests.push(args), msg_dialog: { hide: () => hidden.push(true) } };
  if (storage) w.sessionStorage.setItem('ill-undo:S-1', JSON.stringify(storage));
  w.eval(read('context') + '\n' + scripts.map(read).join('\n'));
  const reloads = [];
  if (w.ScheduleUndo) w.ScheduleUndo.reload = () => reloads.push('undo');
  if (w.ScheduleConflict) w.ScheduleConflict.reload = () => reloads.push('conflict');
  return { dom, w, requests, reloads, hidden };
}

test('the template wires the kill switches, containers, strings and scripts', () => {
  assert.match(TEMPLATE, /"undo": \(undo_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /\{% if undo_enabled \| default\(false\) %\}[\s\S]{0,200}<div id="scheduleUndoToast"[^>]*role="status"[^>]*hidden>/);
  assert.match(TEMPLATE, /<div class="alert alert-warning ill-conflict-notice" id="scheduleConflictNotice" role="alert" tabindex="-1" hidden><\/div>/);
  assert.match(TEMPLATE, /"stale", "conflict", "undo", "activity", "keyboard"\]/);
  assert.match(TEMPLATE, /"Updated by \{0\} at \{1\}\.": _\("Updated by \{0\} at \{1\}\."\)/);
  assert.match(read('lines'), /ScheduleUndo\.offer\(r\.message\.undo\)/);
  assert.match(read('bulk'), /ScheduleUndo\.offer\(message\.undo\)/);
  assert.match(read('bulk'), /You can undo this for a few seconds\./);
  for (const name of ['lines', 'reorder']) assert.match(read(name), /ScheduleConflict\.handle\(r\)\) return;/);
});

test('an offer survives the reload and shows a text-only toast with a countdown', () => {
  const first = page();
  assert.equal(first.w.ScheduleUndo.offer({ token: 'tok', expires_in: 10, action: 'delete', count: 2 }), true);
  const stored = JSON.parse(first.w.sessionStorage.getItem('ill-undo:S-1'));
  assert.equal(stored.token, 'tok');
  assert.ok(stored.until > Date.now() + 9000 && stored.until <= Date.now() + 10000);

  const { dom, w } = page({ i18n: { 'Deleted {0} line(s).': '{0} ligne(s) supprimée(s).' } }, { storage: stored });
  const toast = w.document.getElementById('scheduleUndoToast');
  assert.equal(toast.hidden, false);
  assert.equal(toast.getAttribute('role'), 'status');
  assert.equal(toast.querySelector('.ill-undo-text').textContent, '2 ligne(s) supprimée(s).');
  assert.match(toast.querySelector('.ill-undo-countdown').textContent, /^(9|10)s$/);
  assert.equal(toast.querySelector('.ill-undo-button').textContent, 'Undo');
});

test('Undo posts the token once, then reloads; a failure hides the toast', () => {
  const entry = { token: 'tok', action: 'move', count: 3, until: Date.now() + 8000 };
  const { dom, w, requests, reloads } = page({}, { storage: entry });
  assert.equal(w.document.querySelector('.ill-undo-text').textContent, 'Moved 3 line(s).');
  const button = w.document.querySelector('.ill-undo-button');
  button.click();
  assert.equal(button.disabled, true);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'illumenate_lighting.illumenate_lighting.portal.line_undo.undo_line_action');
  assert.equal(requests[0].type, 'POST');
  assert.deepEqual(requests[0].args, { token: 'tok' });
  requests[0].callback({ message: { success: true } });
  requests[0].always();
  assert.deepEqual(reloads, ['undo']);
  assert.equal(w.sessionStorage.getItem('ill-undo:S-1'), null);

  const failed = page({}, { storage: entry });
  failed.w.document.querySelector('.ill-undo-button').click();
  failed.requests[0].always();
  assert.deepEqual(failed.reloads, []);
  assert.equal(failed.w.document.getElementById('scheduleUndoToast').hidden, true);
});

test('expired offers, Dismiss and the kill switch show nothing', () => {
  const old = page({}, { storage: { token: 'tok', action: 'delete', count: 1, until: Date.now() - 1 } });
  assert.equal(old.w.document.getElementById('scheduleUndoToast'), null);
  assert.equal(old.w.sessionStorage.getItem('ill-undo:S-1'), null);

  const live = page({}, { storage: { token: 'tok', action: 'update', count: 1, until: Date.now() + 5000 } });
  assert.equal(live.w.document.querySelector('.ill-undo-text').textContent, 'Updated 1 line(s).');
  live.w.document.querySelector('.ill-undo-dismiss').click();
  assert.equal(live.w.document.getElementById('scheduleUndoToast').hidden, true);
  assert.equal(live.w.sessionStorage.getItem('ill-undo:S-1'), null);

  const off = page({ undo: false }, { storage: { token: 'tok', action: 'delete', count: 1, until: Date.now() + 5000 } });
  assert.equal(off.w.document.getElementById('scheduleUndoToast'), null);
  assert.equal(off.w.ScheduleUndo.offer({ token: 'x', expires_in: 10 }), false);
  assert.equal(off.w.ScheduleUndo.offer(null), false);
});

test('a stale save shows who saved it and when, as text, with Reload and Compare', () => {
  const compared = [];
  const { dom, w, reloads } = page({ activity_timeline: true });
  w.ScheduleActivity = { open: refresh => compared.push(refresh) };
  const conflict = { modified: '2026-11-03 10:05:00', modified_display: 'Nov 3, 10:05', modified_by_name: 'Pat <img src=x onerror=alert(1)>' };
  assert.equal(w.ScheduleConflict.handle({ message: { success: false, error: 'changed', conflict } }), true);
  const box = w.document.getElementById('scheduleConflictNotice');
  assert.equal(box.hidden, false);
  assert.equal(box.querySelector('.ill-conflict-text').textContent,
    'Updated by Pat <img src=x onerror=alert(1)> at Nov 3, 10:05. Your change was not saved.');
  assert.equal(box.querySelector('img'), null);
  box.querySelector('[data-conflict-action="compare"]').click();
  box.querySelector('[data-conflict-action="reload"]').click();
  assert.deepEqual(compared, [true]);
  assert.deepEqual(reloads, ['conflict']);
});

test('other errors are left alone and Compare needs the timeline', () => {
  const { dom, w } = page({ activity_timeline: false });
  assert.equal(w.ScheduleConflict.handle({ message: { success: false, error: 'Nope' } }), false);
  assert.equal(w.ScheduleConflict.handle(null), false);
  assert.equal(w.document.getElementById('scheduleConflictNotice').hidden, true);
  w.ScheduleConflict.handle({ conflict: { modified: 'm' } });
  const box = w.document.getElementById('scheduleConflictNotice');
  assert.equal(box.querySelector('.ill-conflict-text').textContent, 'Updated by another user at m. Your change was not saved.');
  assert.equal(box.querySelector('[data-conflict-action="compare"]'), null);
});
