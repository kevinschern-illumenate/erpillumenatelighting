// The collaborators page changes one row at a time and keeps removed people as
// inactive rows. Needs tests/portal_ui/rendered/collaborators.html from
// tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const JQUERY = fs.readFileSync(require.resolve('jquery'), 'utf8');

function load(respond) {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/collaborators.html'), 'utf8')
    .replace('<body>', '<body><script>' + JQUERY + '</script>');
  const calls = [];
  const alerts = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/projects/P-1/collaborators',
    beforeParse(w) {
      w.confirm = () => true;
      w.frappe = {
        call(options) {
          calls.push(options);
          const reply = respond(options);
          if (reply instanceof Error) options.error(reply);
          else options.callback({ message: reply });
        },
        msgprint() {},
        show_alert: value => alerts.push(value.message),
      };
    },
  });
  dom.window.jQuery.fn.modal = function () { return this; };
  return { dom, w: dom.window, calls, alerts };
}

let modified = 0;
function ok(options) {
  modified += 1;
  return {
    success: true,
    modified: 'rev-' + modified,
    collaborator: {
      user: options.args.user,
      access_level: options.args.level || 'VIEW',
      is_active: options.method.endsWith('.deactivate') ? 0 : 1,
    },
  };
}

function row(w, user) {
  return [...w.document.querySelectorAll('#collaboratorsList tr')].find(tr => tr.dataset.user === user);
}

test('changing a level calls set_access_level for that one user with the page revision', () => {
  const { w, calls, alerts } = load(ok);
  const select = row(w, 'architect@studio.test').querySelector('.access-level-select');
  select.value = 'EDIT';
  w.jQuery(select).trigger('change');
  const [call] = calls;
  assert.equal(call.method, 'illumenate_lighting.illumenate_lighting.portal.collaborators.set_access_level');
  assert.deepEqual({ ...call.args }, {
    user: 'architect@studio.test', level: 'EDIT', project: 'P-1', expected_modified: '2026-10-14 01:00:00',
  });
  assert.deepEqual(alerts, ['Access updated']);
});

test('removing deactivates in place and the next call carries the new revision', () => {
  const { w, calls } = load(ok);
  row(w, 'architect@studio.test').querySelector('.remove-collaborator').click();
  const removed = row(w, 'architect@studio.test');
  assert.ok(removed, 'row stays on the page');
  assert.equal(removed.querySelector('.collaborator-status').textContent, 'Inactive');
  assert.equal(removed.querySelector('.remove-collaborator').hidden, true);
  assert.equal(calls[0].method.split('.').pop(), 'deactivate');
  const revision = 'rev-' + modified;
  w.document.querySelector('#newCollaboratorUser').value = 'teammate@acme.test';
  w.document.querySelector('#addCollaboratorButton').click();
  assert.equal(calls[1].args.expected_modified, revision);
});

test('adding a teammate appends their row without a reload and drops them from the picker', () => {
  const { w, calls } = load(ok);
  w.document.querySelector('#newCollaboratorUser').value = 'teammate@acme.test';
  w.document.querySelector('#newCollaboratorAccess').value = 'EDIT';
  w.document.querySelector('#addCollaboratorButton').click();
  assert.equal(calls[0].args.user, 'teammate@acme.test');
  const added = row(w, 'teammate@acme.test');
  assert.equal(added.querySelector('strong').textContent, 'Tess Mate');
  assert.equal(added.querySelector('small').textContent, 'teammate@acme.test');
  assert.equal(added.querySelector('.access-level-select').value, 'EDIT');
  assert.equal(w.document.querySelectorAll('#newCollaboratorUser option[value="teammate@acme.test"]').length, 0);
  assert.equal(w.document.querySelector('#addCollaboratorButton').disabled, true);
});

test('a refused change puts the select back', () => {
  const { w } = load(() => new Error('PermissionError'));
  const select = row(w, 'architect@studio.test').querySelector('.access-level-select');
  select.value = 'EDIT';
  w.jQuery(select).trigger('change');
  assert.equal(select.value, 'VIEW');
});

test('hostile names render as text', () => {
  const { w } = load(ok);
  assert.equal(row(w, 'architect@studio.test').querySelector('strong').textContent, 'Ada "<b>"');
  assert.equal(w.document.querySelectorAll('#collaboratorsList b').length, 0);
});
