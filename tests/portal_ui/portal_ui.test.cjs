// PortalUI: one way for portal calls to succeed or fail, plus confirm and inline errors (UI-3).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const SOURCE = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_ui.js'), 'utf8');

function setup(respond) {
  const dom = new JSDOM('<body><button id="go">Go</button><form id="f"><input name="email" id="email"></form></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  const alerts = [];
  w.frappe = {
    call(options) { respond(options); },
    show_alert: value => alerts.push(value),
  };
  w.eval(SOURCE);
  return { w, alerts, button: w.document.getElementById('go') };
}

test('success resolves with the message and frees the busy button', async () => {
  const { w, button, alerts } = setup(options => {
    assert.equal(options.type, 'POST');
    assert.equal(button.disabled, true);
    options.callback({ message: { success: true, name: 'P-1' } });
  });
  const result = await w.PortalUI.call('x.y', { a: 1 }, { busy: button, successToast: 'Saved <ok>' });
  assert.equal(result.name, 'P-1');
  assert.equal(button.disabled, false);
  assert.deepEqual(alerts.map(a => [a.message, a.indicator]), [['Saved &lt;ok&gt;', 'green']]);
});

test('a {success:false} reply rejects with its error text', async () => {
  const { w, button } = setup(options => options.callback({ message: { success: false, error: 'Project not <b>found</b>' } }));
  await assert.rejects(w.PortalUI.call('x.y', {}, { busy: button }), { message: 'Project not found' });
  assert.equal(button.disabled, false);
});

test('a missing message is a success with nothing to read, not a crash', async () => {
  const { w } = setup(options => options.callback({}));
  assert.equal(await w.PortalUI.call('x.y'), undefined);
});

test('a frappe.throw (HTTP 417) rejects with the server message', async () => {
  const { w } = setup(options => options.error({
    exc_type: 'ValidationError',
    _server_messages: JSON.stringify([JSON.stringify({ message: 'Choose VIEW or EDIT project access' })]),
  }));
  await assert.rejects(w.PortalUI.call('x.y'), { message: 'Choose VIEW or EDIT project access' });
});

test('a network failure says so', async () => {
  const { w } = setup(options => options.error({ status: 0, responseText: '' }));
  await assert.rejects(w.PortalUI.call('x.y'), /offline/);
});

test('an unexplained failure still rejects with a usable message', async () => {
  const { w } = setup(options => options.error({ status: 500 }));
  await assert.rejects(w.PortalUI.call('x.y'), /could not be completed/);
});

test('confirm focuses the action, resolves true on it and false on Escape, and restores focus', async () => {
  const { w, button } = setup(() => {});
  button.focus();
  const first = w.PortalUI.confirm({ title: 'Delete schedule?', body: 'Delete "<b>L1</b>"?', confirmLabel: 'Delete', tone: 'danger' });
  const dialog = w.document.querySelector('.ill-confirm [role="dialog"]');
  assert.equal(w.document.activeElement.textContent, 'Delete');
  assert.equal(dialog.querySelectorAll('b').length, 0);
  w.document.activeElement.click();
  assert.equal(await first, true);
  assert.equal(w.document.activeElement, button);
  const second = w.PortalUI.confirm({ body: 'Sure?' });
  w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape' }));
  assert.equal(await second, false);
  assert.equal(w.document.querySelector('.ill-confirm'), null);
});

test('field errors show under the field and clear on the next call', () => {
  const { w } = setup(() => {});
  const form = w.document.getElementById('f');
  assert.equal(w.PortalUI.fieldErrors(form, { email: 'Enter a valid email' }), true);
  const input = w.document.getElementById('email');
  assert.equal(input.getAttribute('aria-invalid'), 'true');
  assert.equal(w.document.getElementById(input.getAttribute('aria-describedby')).textContent, 'Enter a valid email');
  assert.equal(w.document.activeElement, input);
  assert.equal(w.PortalUI.fieldErrors(form, {}), false);
  assert.equal(form.querySelectorAll('.ill-field-error').length, 0);
});

test('escape covers quotes as well as markup', () => {
  const { w } = setup(() => {});
  assert.equal(w.PortalUI.escape(`<a href="x">'</a>`), '&lt;a href=&quot;x&quot;&gt;&#39;&lt;/a&gt;');
});

// UI-5: async sections load with a skeleton, show one empty state and fail with a Retry button.
test('skeleton marks the section busy and announces what is loading', () => {
  const { w } = setup(() => {});
  const box = w.document.createElement('div');
  w.PortalUI.skeleton(box, 'Loading exports', 2);
  assert.equal(box.getAttribute('aria-busy'), 'true');
  assert.equal(box.querySelector('.sr-only').textContent, 'Loading exports');
  assert.equal(box.querySelectorAll('.ill-skeleton__line').length, 2);
  assert.equal(box.querySelector('.ill-skeleton').getAttribute('aria-hidden'), 'true');
});

test('empty renders the shared .ill-empty with text, never markup', () => {
  const { w } = setup(() => {});
  const box = w.document.createElement('div');
  w.PortalUI.skeleton(box);
  w.PortalUI.empty(box, { icon: 'download', title: 'No <b>exports</b>', text: 'Generate one.' });
  const empty = box.querySelector('.ill-empty');
  assert.ok(empty.classList.contains('ill-empty--quiet'));
  assert.equal(empty.querySelector('h3').textContent, 'No <b>exports</b>');
  assert.equal(empty.querySelector('b'), null);
  assert.equal(box.getAttribute('aria-busy'), 'false');
});

test('failed shows the message as an alert and Retry runs the loader again', () => {
  const { w } = setup(() => {});
  const box = w.document.createElement('div');
  let retried = 0;
  w.PortalUI.failed(box, 'Server <i>down</i>', () => { retried += 1; });
  const alert = box.querySelector('.ill-empty--error');
  assert.equal(alert.getAttribute('role'), 'alert');
  assert.equal(alert.querySelector('p').textContent, 'Server <i>down</i>');
  alert.querySelector('button').click();
  assert.equal(retried, 1);
  assert.equal(w.document.querySelector('.alert-danger'), null);
});

test('toasts shown through frappe.show_alert are also announced in a polite status region', async () => {
  const { w, alerts } = setup(() => {});
  w.PortalUI.toast('Saved <ok>', 'green');
  assert.equal(alerts.length, 1);
  const region = w.document.querySelector('.ill-announcer');
  assert.equal(region.getAttribute('role'), 'status');
  assert.equal(region.getAttribute('aria-live'), 'polite');
  await new Promise(resolve => w.setTimeout(resolve, 80));
  assert.equal(region.textContent, 'Saved <ok>');
  assert.equal(region.querySelector('ok'), null);
});

// Plan 2.3/2.4: PortalAPI.call on top of PortalUI.call.
const legacy417 = (payload) => options => options.error(payload);

test('PortalAPI maps a portal_error field onto the form and keeps the button busy until it settles', async () => {
  const { w, button, alerts } = setup(options => {
    assert.equal(button.disabled, true);
    options.error({
      exc_type: 'PortalError',
      _server_messages: JSON.stringify([JSON.stringify({ message: 'Use a work email. Personal domains are not accepted.' })]),
      portal_error: { code: 'EMAIL_DOMAIN', message: 'Use a work email.', field: 'email', hint: 'Personal domains are not accepted.' },
    });
  });
  const form = w.document.getElementById('f');
  const error = await w.PortalAPI.call('x.y', {}, { button, form }).catch(e => e);
  assert.equal(error.code, 'EMAIL_DOMAIN');
  assert.equal(error.field, 'email');
  assert.equal(error.message, 'Use a work email.');
  assert.equal(error.shown, true);
  assert.equal(button.disabled, false);
  const input = w.document.getElementById('email');
  assert.equal(input.getAttribute('aria-invalid'), 'true');
  assert.equal(w.document.getElementById('email-error').textContent, 'Use a work email. Personal domains are not accepted.');
  assert.deepEqual(alerts, [], 'an inline field error is not also toasted');
});

test('PortalAPI shows one red toast when no field can take the error, and clears old field errors first', async () => {
  let reply = { message: { success: false, error: 'Schedule is <b>locked</b>', error_code: 'schedule_locked', field: 'nope' } };
  const { w, alerts } = setup(options => options.callback(reply));
  const form = w.document.getElementById('f');
  w.PortalUI.fieldErrors(form, { email: 'old' });
  const error = await w.PortalAPI.call('x.y', {}, { form }).catch(e => e);
  assert.equal(error.code, 'schedule_locked');
  assert.equal(form.querySelectorAll('.ill-field-error').length, 0);
  assert.deepEqual(alerts.map(a => [a.message, a.indicator]), [['Schedule is locked', 'red']]);
  reply = { message: { success: false, error: 'Quiet' } };
  await assert.rejects(w.PortalAPI.call('x.y', {}, { toast: false }), { message: 'Quiet', shown: false });
  assert.equal(alerts.length, 1);
});

test('PortalAPI retries only transport failures, and only as often as asked', async () => {
  let calls = 0;
  const { w } = setup(options => {
    calls += 1;
    if (calls < 3) options.error({ status: 503 });
    else options.callback({ message: { ok: true } });
  });
  w.setTimeout = (fn) => { fn(); return 0; };
  const result = await w.PortalAPI.call('x.y', {}, { retry: 2, toast: false });
  assert.deepEqual(result, { ok: true });
  assert.equal(calls, 3);

  calls = 0;
  const validation = setup(options => { calls += 1; legacy417({ _server_messages: JSON.stringify([JSON.stringify({ message: 'Bad length' })]) })(options); });
  await assert.rejects(validation.w.PortalAPI.call('x.y', {}, { retry: 3, toast: false }), { message: 'Bad length', transient: false });
  assert.equal(calls, 1, 'a server answer is never re-sent');
});

test('PortalUI.call keeps its old messages and now also carries the error code', async () => {
  const { w } = setup(options => options.callback({ message: { success: false, error: 'Nope', error_code: 'permission_denied' } }));
  await assert.rejects(w.PortalUI.call('x.y'), { message: 'Nope', code: 'permission_denied', field: null, transient: false });
  const offline = setup(options => options.error({ status: 0, responseText: '' }));
  await assert.rejects(offline.w.PortalUI.call('x.y'), { message: /offline/, transient: true, status: 0 });
});
