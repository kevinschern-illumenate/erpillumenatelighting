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
  const shows = [];
  // Frappe's form dashboard: add_section appends a ".form-dashboard-section custom <css>" block.
  const $wrapper = $('<div class="form-dashboard"></div>');
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
  // Frappe's sidebar: the layout-side-section holds the title row (and, for galleries, our status pill).
  const $page = $('<div class="page-wrapper"><div class="layout-side-section"><div class="sidebar-title">test</div></div></div>');
  // The Images section: the table's wrapper sits in a parent, where the hero card is inserted before it.
  const $imagesSection = $('<div class="section-body"><div class="frappe-control"></div></div>');
  const $tableHost = $imagesSection.find('.frappe-control');
  const frm = {
    page: { wrapper: $page },
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
    dashboard: {
      wrapper: $wrapper,
      add_section(html, label, css) {
        const $s = $(`<div class="form-dashboard-section custom ${css || ''}"></div>`).append(html);
        $wrapper.append($s);
        sections.push($s);
        return $s;
      },
      show() { shows.push(1); },
    },
    fields_dict: { gallery_images: { set_description(text) { frm.description = text; }, $wrapper: $tableHost } },
  };
  const context = { frappe, __: s => s, document: dom.window.document, window: dom.window, console };
  const factory = new Function('window', 'frappe', '__', 'document', 'module', 'exports',
    fs.readFileSync(modulePath, 'utf8') + '\nreturn typeof module !== "undefined" ? module.exports : null;');
  const mod = { exports: {} };
  factory(context.window, frappe, context.__, context.document, mod, mod.exports);
  return { $imagesSection, api: mod.exports, frm, buttons, calls, sections, shows, $wrapper, $page, alerts, messages, reloads, frappe, events, $ };
}

// What is on screen: the sections still attached to the dashboard.
const text = s => s.$wrapper.text();
const pill = s => s.$page.find('.ill-gallery-status .indicator-pill');

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

test('Publish Live enables by hashes only: approved and staged equal current, live does not', async t => {
  for (const extra of [
    { state: 'STAGED', approved_hash: 'cur', staged_hash: 'cur' },
    // A save that changed nothing sent: state is NEEDS_REVIEW until re-inspected, hashes still match.
    { state: 'NEEDS_REVIEW', approved_hash: 'cur', staged_hash: 'cur', live_hash: 'old' },
    { state: 'READY', approved_hash: 'cur', staged_hash: 'cur' },
  ]) {
    const ok = setup(t, { inspect: receipt(extra) });
    await ok.api.refresh(ok.frm);
    assert.equal(ok.buttons['Publish Live'].$button.prop('disabled'), false, JSON.stringify(extra));
  }
  for (const extra of [
    { state: 'STAGED', approved_hash: 'old', staged_hash: 'cur' },
    { state: 'STAGED', approved_hash: 'cur', staged_hash: 'old' },
    { state: 'LIVE', approved_hash: 'cur', staged_hash: 'cur', live_hash: 'cur' },
    { state: 'NEEDS_REVIEW', current_hash: '', approved_hash: '', staged_hash: '' },
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

test('the panel is rebuilt on every refresh: one section, never cached on frm, dashboard shown', async t => {
  const s = setup(t, { inspect: receipt({ state: 'STAGED' }) });
  await s.api.refresh(s.frm);
  await s.api.refresh(s.frm);
  assert.equal(s.sections.length, 2);
  assert.equal(s.$wrapper.find('.ill-gallery-publication-section').length, 1);
  assert.equal(s.sections[0].parent().length, 0, 'the previous section is removed');
  assert.equal(s.shows.length, 2);
  assert.equal(s.frm.__ill_gallery_panel, undefined);
  assert.match(text(s), /STAGED/);
});

test('the panel survives Frappe clearing custom dashboard sections between refreshes', async t => {
  const s = setup(t, { inspect: receipt({ state: 'STAGED' }) });
  await s.api.refresh(s.frm);
  s.$wrapper.find('.form-dashboard-section.custom').remove();
  assert.equal(text(s), '');
  await s.api.refresh(s.frm);
  assert.match(text(s), /STAGED/);
});

test('a form reused for another gallery shows that gallery, not the previous one', async t => {
  const s = setup(t, { inspect: receipt({ state: 'STAGED', current_hash: 'first-gallery' }) });
  await s.api.refresh(s.frm);
  s.frm.doc = { ...s.frm.doc, name: 'g2' };
  s.frappe.call = (orig => async args => {
    if (args.method === API + 'inspect') return { message: receipt({ state: 'LIVE', current_hash: 'second-galle' }) };
    return orig(args);
  })(s.frappe.call);
  await s.api.refresh(s.frm);
  assert.match(text(s), /LIVE/);
  assert.doesNotMatch(text(s), /first-galler/);
  assert.equal(s.$wrapper.find('.ill-gallery-publication-section').length, 1);
});

test('choosing another brand in the panel inspects that brand', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  s.calls.length = 0;
  s.$wrapper.find('select.ill-gallery-brand').val('illumenate').trigger('change');
  await flush();
  assert.equal(s.calls.find(c => c.method === API + 'inspect').args.brand, 'illumenate');
  assert.equal(s.$wrapper.find('.ill-gallery-publication-section').length, 1);
});

test('no enabled brand shows a notice and no buttons', async t => {
  const s = setup(t, { noBrands: true, doc: { target_brands: [] } });
  await s.api.refresh(s.frm);
  assert.match(text(s), /No Webflow brand is enabled for this gallery/);
  assert.deepEqual(Object.keys(s.buttons), []);
  assert.equal(s.calls.filter(c => c.method).length, 0);
});

test('the status pill sits on its own row, above the title, at the top of the sidebar', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  const $side = s.$page.find('.layout-side-section');
  assert.equal(pill(s).length, 1);
  assert.ok($side.children().first().hasClass('ill-gallery-status'), 'first child of the sidebar');
  assert.equal($side.children().first().children().length, 1, 'nothing else on its row');
  assert.equal($side.children().eq(1).text(), 'test', 'the title row follows');
  assert.equal(pill(s).text(), 'Needs staging');
  assert.ok(pill(s).hasClass('indicator-pill') && pill(s).hasClass('orange'));
});

test('each publication state shows its own pill', async t => {
  const cases = [
    [{ state: 'NEEDS_REVIEW' }, 'Needs staging', 'orange'],
    [{ state: 'NEEDS_REVIEW', staged_hash: 'old' }, 'Changes not staged', 'orange'],
    [{ state: 'NEEDS_REVIEW', live_hash: 'old' }, 'Changes not staged', 'orange'],
    [{ state: 'QUEUED' }, 'Queued', 'blue'],
    [{ state: 'STAGED', approved_hash: 'cur', staged_hash: 'cur' }, 'Staged', 'yellow'],
    [{ state: 'LIVE', approved_hash: 'cur', staged_hash: 'cur', live_hash: 'cur' }, 'Live', 'green'],
    [{ state: 'FAILED' }, 'Failed', 'red'],
    [{ state: 'RETIRED' }, 'Retired', 'gray'],
  ];
  for (const [extra, label, color] of cases) {
    const s = setup(t, { inspect: receipt(extra) });
    await s.api.refresh(s.frm);
    assert.equal(pill(s).length, 1, JSON.stringify(extra));
    assert.equal(pill(s).text(), label, JSON.stringify(extra));
    assert.ok(pill(s).hasClass(color), `${label} is ${color}`);
  }
});

test('the pill is replaced on every refresh, never duplicated', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  await s.api.refresh(s.frm);
  await s.api.refresh(s.frm);
  assert.equal(s.$page.find('.ill-gallery-status').length, 1);
});

test('the pill names the brand and explains the status in its tooltip', async t => {
  const s = setup(t, { inspect: receipt({ state: 'LIVE', live_hash: 'cur' }) });
  await s.api.refresh(s.frm);
  const title = pill(s).attr('title');
  assert.match(title, /Published on the Webflow site/);
  assert.match(title, /lighting_206/);
});

test('no pill for an unsaved gallery, and a stale one is removed', async t => {
  const s = setup(t, { isNew: true });
  s.$page.find('.layout-side-section').prepend('<div class="ill-gallery-status"><span class="indicator-pill green">Live</span></div>');
  await s.api.refresh(s.frm);
  assert.equal(s.$page.find('.ill-gallery-status').length, 0);
});

test('no pill when inspect fails or no brand is enabled, and a previous one is cleared', async t => {
  const failing = setup(t, { inspectError: new Error('boom') });
  failing.$page.find('.layout-side-section').prepend('<div class="ill-gallery-status"><span class="indicator-pill green">Live</span></div>');
  await failing.api.refresh(failing.frm);
  assert.equal(failing.$page.find('.ill-gallery-status').length, 0);
  const none = setup(t, { noBrands: true, doc: { target_brands: [] } });
  none.$page.find('.layout-side-section').prepend('<div class="ill-gallery-status"><span class="indicator-pill green">Live</span></div>');
  await none.api.refresh(none.frm);
  assert.equal(none.$page.find('.ill-gallery-status').length, 0);
});

test('the pill follows the state when the form refreshes again', async t => {
  const s = setup(t);
  await s.api.refresh(s.frm);
  assert.equal(pill(s).text(), 'Needs staging');
  // The server now reports the gallery as staged, then live; each refresh replaces the pill.
  const original = s.frappe.call;
  for (const [extra, label] of [
    [{ state: 'STAGED', approved_hash: 'cur', staged_hash: 'cur' }, 'Staged'],
    [{ state: 'LIVE', approved_hash: 'cur', staged_hash: 'cur', live_hash: 'cur' }, 'Live'],
  ]) {
    s.frappe.call = async args => (args.method === API + 'inspect' ? { message: receipt(extra) } : original(args));
    await s.api.refresh(s.frm);
    assert.equal(s.$page.find('.ill-gallery-status').length, 1);
    assert.equal(pill(s).text(), label);
  }
});

test('a sidebar the page does not expose is left alone', async t => {
  const s = setup(t);
  s.frm.page = {};
  await s.api.refresh(s.frm);
  assert.equal(s.$page.find('.ill-gallery-status').length, 0);
  assert.ok(s.buttons['Approve and Stage'], 'the panel and buttons still work');
});

const hero = s => s.$imagesSection.find('> .ill-gallery-hero');

test('the hero preview shows the first image row above the table', async t => {
  const s = setup(t, { doc: { gallery_images: [
    { idx: 2, image: '/files/second.jpg' }, { idx: 1, image: '/files/first.jpg', alt_text: 'Lobby' }] } });
  await s.api.refresh(s.frm);
  assert.equal(hero(s).length, 1);
  assert.equal(hero(s).next().hasClass('frappe-control'), true, 'inserted right above the table');
  assert.equal(hero(s).find('img').attr('src'), '/files/first.jpg');
  assert.equal(hero(s).find('img').attr('alt'), 'Lobby');
  assert.equal(hero(s).find('.text-warning').length, 0);
});

test('the hero preview asks for alt text and for an image when there is none', async t => {
  const s = setup(t, { doc: { gallery_images: [{ idx: 1, image: '/files/first.jpg' }] } });
  await s.api.refresh(s.frm);
  assert.match(hero(s).find('.text-warning').text(), /alt text/);
  const empty = setup(t, { doc: { gallery_images: [] } });
  await empty.api.refresh(empty.frm);
  assert.match(hero(empty).text(), /No hero image yet/);
  assert.equal(hero(empty).find('img').length, 0);
});

test('the hero preview is rebuilt, never duplicated, and works on an unsaved gallery', async t => {
  const s = setup(t, { isNew: true, doc: { gallery_images: [{ idx: 1, image: '/files/a.jpg' }] } });
  await s.api.refresh(s.frm);
  s.frm.doc.gallery_images = [{ idx: 1, image: '/files/b.jpg' }];
  s.api.setHeroPreview(s.frm);
  assert.equal(hero(s).length, 1);
  assert.equal(hero(s).find('img').attr('src'), '/files/b.jpg');
});

test('the form refreshes the hero preview when rows or the image change', () => {
  const calls = [];
  const events = {};
  new Function('frappe', 'window', fs.readFileSync(formPath, 'utf8'))(
    { ui: { form: { on(doctype, handlers) { events[doctype] = handlers; } } } },
    { IllGalleryPublication: { setHeroPreview: frm => calls.push(frm), refresh() {} } });
  const gallery = events['ilL-Webflow-Gallery'];
  for (const name of ['gallery_images_add', 'gallery_images_remove', 'gallery_images_move']) gallery[name]('frm');
  events['ilL-Child-Webflow-Gallery-Image'].image('frm');
  events['ilL-Child-Webflow-Gallery-Image'].alt_text('frm');
  assert.equal(calls.length, 5);
});
