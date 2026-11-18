const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

const API = 'illumenate_lighting.illumenate_lighting.api.gallery_publication.';
const modulePath = path.join(__dirname, '../../illumenate_lighting/public/js/gallery_publication.js');
const formPath = path.join(
  __dirname,
  '../../illumenate_lighting/illumenate_lighting/doctype/ill_webflow_gallery/ill_webflow_gallery.js',
);

const flush = async () => {
  for (let i = 0; i < 6; i += 1) await new Promise(resolve => setImmediate(resolve));
};

const receipt = (extra = {}) => ({
  name: 'PUB-1', gallery: 'g1', brand: 'illumenate', state: 'NEEDS_REVIEW',
  current_hash: 'cur', approved_hash: '', staged_hash: '', live_hash: '',
  readiness: { ready: true, issues: [], warnings: [] },
  ...extra,
});

function setup(t, { inspect = receipt(), jobs = [], doc = {}, isNew = false, dirty = false, requestError = null, inspectError = null, noBrands = false, gate = null } = {}) {
  const dom = new JSDOM('<html><body></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const calls = [];
  const buttons = {};
  const events = {};
  const sections = [];
  const alerts = [];
  const messages = [];
  const reloads = [];
  const frappe = {
    ui: { form: { on(doctype, handlers) { events[doctype] = handlers; } } },
    utils: { escape_html: s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])) },
    db: {
      async get_list(doctype, opts) {
        calls.push({ list: doctype, opts });
        if (doctype === 'ilL-Webflow-Brand') {
          return noBrands ? [] : [{ name: 'lighting_206', is_default: 0 }, { name: 'illumenate', is_default: 1 }];
        }
        return jobs;
      },
    },
    async call(args) {
      calls.push(args);
      if (args.method === API + 'inspect') {
        if (inspectError) throw inspectError;
        if (gate) await gate;
        return { message: inspect };
      }
      if (args.method === API + 'request') {
        if (requestError) throw requestError;
        return { message: { job: 'JOB-9', ...inspect } };
      }
      return { message: { job: args.args.job, state: 'QUEUED' } };
    },
    show_alert(a) { alerts.push(a); },
    msgprint(m) { messages.push(m); },
  };
  const frm = {
    doc: { name: 'g1', is_active: 0, target_brands: [{ brand: 'lighting_206', enabled: 1 }], ...doc },
    is_new: () => isNew,
    is_dirty: () => dirty,
    add_custom_button(label, fn) {
      const $button = $('<button>');
      buttons[label] = { fn, $button };
      return $button;
    },
    remove_custom_button(label) { delete buttons[label]; },
    async reload_doc() { reloads.push(1); },
    dashboard: { add_section(html) { const $s = $(html); sections.push($s); return $s; } },
    fields_dict: { gallery_images: { set_description(text) { frm.description = text; } } },
  };
  const context = { frappe, __: s => s, document: dom.window.document, window: dom.window, console };
  const factory = new Function('window', 'frappe', '__', 'document', 'module', 'exports',
    fs.readFileSync(modulePath, 'utf8') + '\nreturn typeof module !== "undefined" ? module.exports : null;');
  const mod = { exports: {} };
  factory(context.window, frappe, context.__, context.document, mod, mod.exports);
  return { api: mod.exports, frm, buttons, calls, sections, alerts, messages, reloads, frappe, events, $ };
}

const text = s => s.sections.map(x => x.text()).join('\n');

test('no buttons or panel for an unsaved gallery', async t => {
  const s = setup(t, { isNew: true });
  await s.api.refresh(s.frm);
  assert.deepEqual(Object.keys(s.buttons), []);
  assert.equal(s.calls.length, 0);
});

test('saved gallery gets the three buttons and Publish Live is disabled until staged', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  for (const label of ['Approve and Stage', 'Publish Live', 'Retire']) assert.ok(s.buttons[label], label);
  assert.equal(s.buttons['Publish Live'].$button.prop('disabled'), true);
  assert.equal(s.buttons['Retry'], undefined);
});

test('Publish Live enables only when staged, approved and staged hashes equal the current hash', async t => {
  const ok = setup(t, { inspect: receipt({ state: 'STAGED', approved_hash: 'cur', staged_hash: 'cur' }) });
  await ok.api.refresh(ok.frm);
  assert.equal(ok.buttons['Publish Live'].$button.prop('disabled'), false);
  for (const extra of [
    { state: 'STAGED', approved_hash: 'old', staged_hash: 'cur' },
    { state: 'STAGED', approved_hash: 'cur', staged_hash: 'old' },
    { state: 'READY', approved_hash: 'cur', staged_hash: 'cur' },
  ]) {
    const s = setup(t, { inspect: receipt(extra) });
    await s.api.refresh(s.frm);
    assert.equal(s.buttons['Publish Live'].$button.prop('disabled'), true, JSON.stringify(extra));
  }
});

test('Retire is disabled while the gallery is active', async t => {
  const active = setup(t, { doc: { is_active: 1 } });
  await active.api.refresh(active.frm);
  assert.equal(active.buttons.Retire.$button.prop('disabled'), true);
  const off = setup(t, { doc: { is_active: 0 } });
  await off.api.refresh(off.frm);
  assert.equal(off.buttons.Retire.$button.prop('disabled'), false);
});

test('Approve and Stage inspects first, then requests with the hash inspect returned', async t => {
  const s = setup(t, { inspect: receipt({ current_hash: 'abc123' }) });
  await s.api.refresh(s.frm);
  s.calls.length = 0;
  await s.buttons['Approve and Stage'].fn();
  await flush();
  const methods = s.calls.filter(c => c.method).map(c => c.method);
  assert.deepEqual(methods, [API + 'inspect', API + 'request']);
  const request = s.calls.find(c => c.method === API + 'request');
  assert.deepEqual(request.args, { gallery: 'g1', brand: 'lighting_206', operation: 'STAGE', expected_hash: 'abc123' });
  assert.equal(request.type, 'POST');
});

test('Publish Live and Retire request their operations', async t => {
  const s = setup(t, { inspect: receipt({ state: 'STAGED', approved_hash: 'cur', staged_hash: 'cur' }) });
  await s.api.refresh(s.frm);
  assert.equal(s.buttons['Publish Live'].$button.prop('disabled'), false);
  assert.equal(s.buttons.Retire.$button.prop('disabled'), false);
  s.calls.length = 0;
  await s.buttons['Publish Live'].fn();
  await s.buttons.Retire.fn();
  await flush();
  const ops = s.calls.filter(c => c.method === API + 'request').map(c => c.args.operation);
  assert.deepEqual(ops, ['PUBLISH', 'RETIRE']);
});

test('brand defaults to the first enabled target brand, else the default brand', async t => {
  const s = setup(t, { doc: { target_brands: [{ brand: 'x', enabled: 0 }, { brand: 'lighting_206', enabled: 1 }] } });
  await s.api.refresh(s.frm);
  assert.equal(s.calls.find(c => c.method === API + 'inspect').args.brand, 'lighting_206');
  const d = setup(t, { doc: { target_brands: [] } });
  await d.api.refresh(d.frm);
  assert.equal(d.calls.find(c => c.method === API + 'inspect').args.brand, 'illumenate');
});

test('Retry appears only when the latest job failed and retries that job', async t => {
  const s = setup(t, { jobs: [{ name: 'JOB-3', state: 'FAILED', operation: 'STAGE', last_error: 'boom' }] });
  await s.api.refresh(s.frm);
  const list = s.calls.find(c => c.list === 'ilL-Gallery-Publish-Job');
  assert.deepEqual(list.opts.filters, { gallery: 'g1', brand: 'lighting_206' });
  assert.equal(list.opts.order_by, 'creation desc');
  assert.equal(list.opts.limit, 1);
  assert.ok(s.buttons.Retry);
  await s.buttons.Retry.fn();
  const retry = s.calls.find(c => c.method === API + 'retry');
  assert.deepEqual(retry.args, { job: 'JOB-3' });
  const ok = setup(t, { jobs: [{ name: 'JOB-4', state: 'DONE' }] });
  await ok.api.refresh(ok.frm);
  assert.equal(ok.buttons.Retry, undefined);
});

test('issues show record and message in red, warnings grey, and server text is escaped', async t => {
  const s = setup(t, {
    inspect: receipt({
      readiness: {
        ready: false,
        issues: [{ record: 'Image <b>1</b>', field: 'image', message: '<script>alert(1)</script>' }],
        warnings: [{ record: 'g1', field: 'quote', message: 'Quote is short' }],
      },
    }),
  });
  await s.api.refresh(s.frm);
  const html = s.sections.map(x => x.html()).join('');
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<b>1</b>'));
  assert.match(text(s), /<script>alert\(1\)<\/script>/);
  assert.match(text(s), /Image <b>1<\/b>/);
  assert.equal(s.sections[0].find('.text-danger').length, 1);
  assert.equal(s.sections[0].find('.text-muted').length >= 1, true);
  assert.match(s.sections[0].find('.text-muted').text(), /Quote is short/);
});

test('a note under gallery_images says the first row is the hero image', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  assert.match(s.frm.description, /first (row|image).*hero/i);
});

test('the form script wires refresh to the shared module', async t => {
  const s = setup(t);
  const seen = [];
  const form = fs.readFileSync(formPath, 'utf8');
  const frappe = { ui: { form: { on: (d, h) => { seen.push([d, h]); } } } };
  new Function('frappe', 'window', form)(frappe, { IllGalleryPublication: { refresh: f => seen.push(['called', f]) } });
  assert.equal(seen[0][0], 'ilL-Webflow-Gallery');
  seen[0][1].refresh(s.frm);
  assert.equal(seen[1][1], s.frm);
});

test('a dirty form blocks every action: no server call, a message, buttons disabled', async t => {
  const s = setup(t, { dirty: true, jobs: [{ name: 'JOB-3', state: 'FAILED', operation: 'STAGE', last_error: 'x' }],
    inspect: receipt({ state: 'STAGED', approved_hash: 'cur', staged_hash: 'cur' }) });
  await s.api.refresh(s.frm);
  for (const label of ['Approve and Stage', 'Publish Live', 'Retire', 'Retry']) {
    assert.equal(s.buttons[label].$button.prop('disabled'), true, label);
  }
  s.calls.length = 0;
  for (const label of ['Approve and Stage', 'Publish Live', 'Retire', 'Retry']) await s.buttons[label].fn();
  assert.equal(s.calls.length, 0);
  assert.equal(s.messages.length, 4);
  assert.match(s.messages[0], /Save the gallery first/);
  assert.equal(s.reloads.length, 0);
});

test('a second click while an action is in flight sends nothing', async t => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const s = setup(t, { gate: null });
  await s.api.refresh(s.frm);
  s.calls.length = 0;
  // Hold the first action inside inspect by making the next inspect wait.
  const original = s.frappe.call;
  s.frappe.call = async args => { if (args.method === API + 'inspect') await gate; return original(args); };
  const first = s.buttons['Approve and Stage'].fn();
  await flush();
  await s.buttons['Approve and Stage'].fn();
  await s.buttons.Retire.fn();
  release();
  await first;
  const methods = s.calls.filter(c => c.method).map(c => c.method);
  assert.deepEqual(methods, [API + 'inspect', API + 'request']);
  assert.equal(s.frm.__ill_gallery_busy, false);
});

test('an inspect failure renders an escaped error line in the panel and no buttons', async t => {
  const s = setup(t, { inspectError: { message: '<i>boom</i>' } });
  await s.api.refresh(s.frm);
  const html = s.sections.map(x => x.html()).join('');
  assert.ok(!html.includes('<i>boom</i>'));
  assert.match(text(s), /Inspection failed: <i>boom<\/i>/);
  assert.equal(s.sections[0].find('.text-danger').length, 1);
  assert.deepEqual(Object.keys(s.buttons), []);
});

test('a failed request clears the busy flag, shows the escaped message and does not reload', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  s.frappe.call = (orig => async args => {
    if (args.method === API + 'request') throw { message: 'Hash <b>changed</b>' };
    return orig(args);
  })(s.frappe.call);
  await s.buttons['Approve and Stage'].fn();
  assert.equal(s.frm.__ill_gallery_busy, false);
  assert.equal(s.messages.length, 1);
  assert.equal(s.messages[0], 'Hash &lt;b&gt;changed&lt;/b&gt;');
  assert.equal(s.reloads.length, 0);
  await s.buttons['Approve and Stage'].fn();
  assert.equal(s.messages.length, 2, 'a later click is not blocked');
});

test('the form reloads after a successful request and after a retry', async t => {
  const s = setup(t, { jobs: [{ name: 'JOB-3', state: 'FAILED', operation: 'STAGE', last_error: 'x' }] });
  await s.api.refresh(s.frm);
  await s.buttons['Approve and Stage'].fn();
  assert.equal(s.reloads.length, 1);
  assert.equal(s.alerts.length, 1);
  await s.buttons.Retry.fn();
  assert.equal(s.reloads.length, 2);
});

test('no enabled brand shows a notice and no buttons', async t => {
  const s = setup(t, { noBrands: true, doc: { target_brands: [] } });
  await s.api.refresh(s.frm);
  assert.match(text(s), /No Webflow brand is enabled for this gallery/);
  assert.deepEqual(Object.keys(s.buttons), []);
  assert.equal(s.calls.filter(c => c.method).length, 0);
});
