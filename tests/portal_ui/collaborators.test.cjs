// The collaborators page changes one row at a time and keeps removed people as
// inactive rows. Needs tests/portal_ui/rendered/collaborators.html from
// tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const JQUERY = fs.readFileSync(require.resolve('jquery'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const PORTAL_UI = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_ui.js'), 'utf8');

// Answer the portal confirm dialog the page opens.
function accept(w) {
  w.document.querySelector('.ill-confirm .btn-danger, .ill-confirm .btn-primary').click();
}

function load(respond) {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/collaborators.html'), 'utf8')
    .replace('<body>', '<body><script>' + JQUERY + '</script><script>' + PORTAL_UI + '</script>');
  const calls = [];
  const alerts = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/projects/P-1/collaborators',
    beforeParse(w) {
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

test('changing a level calls set_access_level for that one user with the page revision', async () => {
  const { w, calls, alerts } = load(ok);
  const select = row(w, 'architect@studio.test').querySelector('.access-level-select');
  select.value = 'EDIT';
  w.jQuery(select).trigger('change');
  await tick();
  const [call] = calls;
  assert.equal(call.method, 'illumenate_lighting.illumenate_lighting.portal.collaborators.set_access_level');
  assert.deepEqual({ ...call.args }, {
    user: 'architect@studio.test', level: 'EDIT', project: 'P-1', expected_modified: '2026-10-14 01:00:00',
  });
  assert.deepEqual(alerts, ['Access updated']);
});

test('removing deactivates in place and the next call carries the new revision', async () => {
  const { w, calls } = load(ok);
  row(w, 'architect@studio.test').querySelector('.remove-collaborator').click();
  await tick();
  accept(w);
  await tick();
  const removed = row(w, 'architect@studio.test');
  assert.ok(removed, 'row stays on the page');
  assert.equal(removed.querySelector('.collaborator-status').textContent, 'Inactive');
  assert.equal(removed.querySelector('.remove-collaborator').hidden, true);
  assert.equal(calls[0].method.split('.').pop(), 'deactivate');
  const revision = 'rev-' + modified;
  w.document.querySelector('#newCollaboratorUser').value = 'teammate@acme.test';
  w.document.querySelector('#addCollaboratorButton').click();
  await tick();
  assert.equal(calls[1].args.expected_modified, revision);
});

test('adding a teammate appends their row without a reload and drops them from the picker', async () => {
  const { w, calls } = load(ok);
  w.document.querySelector('#newCollaboratorUser').value = 'teammate@acme.test';
  w.document.querySelector('#newCollaboratorAccess').value = 'EDIT';
  w.document.querySelector('#addCollaboratorButton').click();
  await tick();
  assert.equal(calls[0].args.user, 'teammate@acme.test');
  const added = row(w, 'teammate@acme.test');
  assert.equal(added.querySelector('strong').textContent, 'Tess Mate');
  assert.equal(added.querySelector('small').textContent, 'teammate@acme.test');
  assert.equal(added.querySelector('.access-level-select').value, 'EDIT');
  assert.equal(w.document.querySelectorAll('#newCollaboratorUser option[value="teammate@acme.test"]').length, 0);
  assert.equal(w.document.querySelector('#addCollaboratorButton').disabled, true);
});

test('a refused change puts the select back', async () => {
  const { w } = load(() => new Error('PermissionError'));
  const select = row(w, 'architect@studio.test').querySelector('.access-level-select');
  select.value = 'EDIT';
  w.jQuery(select).trigger('change');
  await tick();
  assert.equal(select.value, 'VIEW');
});

test('hostile names render as text', async () => {
  const { w } = load(ok);
  assert.equal(row(w, 'architect@studio.test').querySelector('strong').textContent, 'Ada "<b>"');
  assert.equal(w.document.querySelectorAll('#collaboratorsList b').length, 0);
});

function invitations(options) {
  const method = options.method.split('.').pop();
  if (method === 'invite') {
    return { success: true, invitation: 'INV-2', email: options.args.email, expires_on: '2026-10-21 12:00:00' };
  }
  if (method === 'resend_invitation') {
    return { success: true, invitation: options.args.name, email: 'pending@studio.test', expires_on: '2026-10-28 12:00:00' };
  }
  return { success: true };
}

test('inviting by email adds a pending row without a reload', async () => {
  const { w, calls, alerts } = load(invitations);
  w.document.querySelector('#inviteEmail').value = 'architect@studio.test';
  w.document.querySelector('#inviteFirstName').value = 'Ada';
  w.document.querySelector('#inviteAccess').value = 'EDIT';
  w.document.querySelector('#sendInviteButton').click();
  await tick();
  assert.equal(calls[0].method, 'illumenate_lighting.illumenate_lighting.portal.collaborators.invite');
  assert.deepEqual({ ...calls[0].args }, {
    project: 'P-1', email: 'architect@studio.test', first_name: 'Ada', last_name: '', access_level: 'EDIT',
  });
  const row = w.document.querySelector('#invitationList tr[data-invitation="INV-2"]');
  assert.equal(row.querySelector('small').textContent, 'architect@studio.test');
  assert.deepEqual(alerts, ['Invitation emailed to architect@studio.test']);
});

test('resend updates the expiry and revoke removes the row', async () => {
  const { w, calls } = load(invitations);
  const row = () => w.document.querySelector('#invitationList tr[data-invitation="INV-1"]');
  assert.equal(row().querySelector('strong').textContent, 'Pat <Pending>');
  row().querySelector('.resend-invitation').click();
  await tick();
  assert.deepEqual({ ...calls[0].args }, { name: 'INV-1' });
  assert.equal(row().querySelector('.invitation-expires').textContent.trim(), '2026-10-28');
  row().querySelector('.revoke-invitation').click();
  await tick();
  accept(w);
  await tick();
  assert.equal(calls[1].method.split('.').pop(), 'revoke_invitation');
  assert.equal(row(), null);
  assert.equal(w.document.querySelector('#pendingInvitations').hidden, true);
});
