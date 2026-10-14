// The accept page guides each recipient state and keeps the token across the
// login hop. Needs tests/portal_ui/rendered/accept-invitation-*.html from
// tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');

function load(variant, { hash = '', stored = null, preview }) {
  const html = fs.readFileSync(path.join(__dirname, `rendered/accept-invitation-${variant}.html`), 'utf8');
  const calls = [];
  // jsdom cannot follow the sign-out redirect; keep its "not implemented" noise out of the output.
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => { if (!/navigation/.test(error.message)) throw error; });
  const dom = new JSDOM(html, {
    virtualConsole,
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/accept-invitation' + hash,
    beforeParse(w) {
      if (stored) w.sessionStorage.setItem('ill_invite_token', stored);
      w.frappe = {
        call(options) {
          calls.push(options);
          const method = options.method.split('.').pop();
          if (method === 'invitation_preview') options.callback({ message: preview });
          if (method === 'accept_invitation') options.callback({ message: { success: true, project: 'P-1' } });
          if (method === 'logout') options.callback({});
        },
      };
    },
  });
  return { w: dom.window, calls };
}

const VALID = {
  valid: true, email: 'invitee@studio.test', target: 'Lobby <Refit>', kind: 'project', inviter: 'Dana', has_account: true,
};

test('a signed-out recipient is sent to sign in and the token survives without staying in the URL', () => {
  const { w, calls } = load('guest', { hash: '#tok-123', preview: VALID });
  assert.equal(calls[0].args.token, 'tok-123');
  assert.equal(w.location.hash, '');
  assert.equal(w.sessionStorage.getItem('ill_invite_token'), 'tok-123');
  assert.equal(w.document.getElementById('inviteSignedOut').hidden, false);
  assert.equal(w.document.getElementById('inviteSignUp').hidden, true, 'existing account signs in instead');
  assert.equal(w.document.getElementById('inviteSignIn').getAttribute('href'), '/login?redirect-to=/portal/accept-invitation');
  assert.match(w.document.getElementById('inviteSummary').textContent, /Lobby <Refit>/);
  assert.equal(w.document.querySelectorAll('#inviteSummary *').length, 0);
});

test('a new recipient is offered account creation', () => {
  const { w } = load('guest', { hash: '#tok-123', preview: { ...VALID, has_account: false } });
  assert.equal(w.document.getElementById('inviteSignUp').hidden, false);
  assert.match(w.document.getElementById('inviteSignedOutText').textContent, /doesn't have a portal account/);
});

test('back from login as the invited email, one Accept button finishes it', () => {
  const { w, calls } = load('signed-in', { stored: 'tok-123', preview: { ...VALID, email: 'invitee@studio.test' } });
  assert.equal(calls[0].args.token, 'tok-123');
  assert.equal(w.document.getElementById('inviteAccept').hidden, false);
  w.document.getElementById('acceptInvite').click();
  assert.equal(calls[1].method.split('.').pop(), 'accept_invitation');
  assert.equal(calls[1].args.token, 'tok-123');
  assert.equal(w.sessionStorage.getItem('ill_invite_token'), null);
  assert.equal(w.document.querySelector('#inviteResult a').getAttribute('href'), '/portal/projects/P-1');
});

test('signed in as someone else offers to sign out and continue', () => {
  const { w, calls } = load('signed-in', { hash: '#tok-123', preview: { ...VALID, email: 'other@studio.test' } });
  assert.equal(w.document.getElementById('inviteAccept').hidden, true);
  assert.equal(w.document.getElementById('inviteOtherUser').hidden, false);
  assert.match(w.document.getElementById('inviteOtherUserText').textContent, /Invitee@Studio\.test.*other@studio\.test/);
  w.document.getElementById('switchAccount').click();
  assert.equal(calls[1].method, 'logout');
});

test('a used link explains itself and forgets the token', () => {
  const { w } = load('guest', { hash: '#tok-123', preview: { valid: false, reason: 'used' } });
  assert.match(w.document.getElementById('inviteSummary').textContent, /already been accepted/);
  assert.equal(w.sessionStorage.getItem('ill_invite_token'), null);
  assert.equal(w.document.getElementById('inviteSignedOut').hidden, true);
});

test('no token at all says the link is incomplete', () => {
  const { w, calls } = load('guest', { preview: VALID });
  assert.equal(calls.length, 0);
  assert.match(w.document.getElementById('inviteSummary').textContent, /incomplete/);
});
