const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

const script = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/product_media.js'), 'utf8');
const HOSTILE = '"><img src=x onerror=alert(1)><script>bad()</script>';

function setup(t, doc, { write = true, isNew = false } = {}) {
  const dom = new JSDOM('<html><body><div id="form"><div id="hero"></div><div id="gallery"></div></div></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {}, uploads = [], values = [], confirms = [];
  let dirty = 0;
  const frm = {
    doctype: doc.doctype,
    doc,
    perm: [{ write: write ? 1 : 0 }],
    is_new: () => isNew,
    fields_dict: {
      hero_image: { $wrapper: $('#hero', dom.window.document) },
      gallery_images: { $wrapper: $('#gallery', dom.window.document) },
    },
    set_value(field, value) { doc[field] = value; values.push([field, value]); },
    refresh_field() {},
    dirty() { dirty += 1; },
    add_child(table, row) {
      const child = { doctype: 'ilL-Child-Webflow-Gallery-Image', name: 'new-' + ((doc[table] || []).length + 1), idx: (doc[table] || []).length + 1, ...row };
      doc[table] = [...(doc[table] || []), child];
      return child;
    },
  };
  vm.runInNewContext(script, {
    document: dom.window.document,
    __: (text, args) => (args ? text.replace('{0}', args[0]) : text),
    frappe: {
      ui: {
        form: { on(doctype, callbacks) { handlers[doctype] = { ...(handlers[doctype] || {}), ...callbacks }; } },
        FileUploader: function FileUploader(options) { uploads.push(options); },
      },
      router: { slug: name => name.toLowerCase() },
      model: { set_value(doctype, name, field, value) { values.push([name, field, value]); } },
      confirm(_message, yes) { confirms.push(yes); },
    },
  });
  const document = dom.window.document;
  return { frm, handlers, uploads, values, confirms, document, dirty: () => dirty };
}

test('every template form and the Webflow Product register the media handlers (5.2)', t => {
  const { handlers } = setup(t, { doctype: 'ilL-Fixture-Template' });
  for (const doctype of ['ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-LED-Sheet-Template',
    'ilL-Extrusion-Kit-Template', 'ilL-Driver-Template', 'ilL-Controller-Template']) {
    assert.equal(typeof handlers[doctype].refresh, 'function', doctype);
    assert.equal(typeof handlers[doctype].hero_image, 'function', doctype);
  }
  assert.equal(typeof handlers['ilL-Webflow-Product'].refresh, 'function');
  assert.equal(typeof handlers['ilL-Child-Webflow-Gallery-Image'].alt_text, 'function');
});

test('the hero card previews the main image and never turns record values into markup', t => {
  const doc = { doctype: 'ilL-Driver-Template', name: 'D-1', hero_image: '/files/h.jpg?' + HOSTILE, hero_image_alt: HOSTILE };
  const state = setup(t, doc);
  state.handlers['ilL-Driver-Template'].refresh(state.frm);
  const card = state.document.querySelector('.ill-hero-card');
  assert.match(card.textContent, /Main product image — shown to dealers and on Webflow/);
  const image = card.querySelector('img');
  assert.equal(image.getAttribute('alt'), HOSTILE);
  assert.equal(card.querySelectorAll('script').length, 0);
  assert.equal(card.querySelectorAll('img').length, 1);
  assert.match(card.querySelector('.indicator-pill').textContent, /Checking size/);

  state.handlers['ilL-Driver-Template'].refresh(state.frm);
  assert.equal(state.document.querySelectorAll('.ill-hero-card').length, 1, 'refresh replaces the card');
});

test('the hero card warns when the main image or its alt text is missing', t => {
  const state = setup(t, { doctype: 'ilL-Fixture-Template', name: 'F-1', hero_image: '/files/scan.TIFF' });
  state.handlers['ilL-Fixture-Template'].refresh(state.frm);
  const card = state.document.querySelector('.ill-hero-card');
  assert.match(card.textContent, /TIFF\/BMP/);
  assert.match(card.textContent, /Add alt text/);

  state.frm.doc.hero_image = null;
  state.handlers['ilL-Fixture-Template'].hero_image(state.frm);
  assert.match(state.document.querySelector('.ill-hero-card').textContent, /No main product image yet/);
});

test('dropping an image on the hero card uploads it publicly and sets hero_image', t => {
  const state = setup(t, { doctype: 'ilL-Fixture-Template', name: 'F-1' });
  state.handlers['ilL-Fixture-Template'].refresh(state.frm);
  const zone = state.document.querySelector('.ill-hero-card .ill-media-drop');
  const event = new state.document.defaultView.Event('drop', { cancelable: true });
  const image = { type: 'image/png', name: 'a.png' };
  event.dataTransfer = { files: [{ type: 'text/plain', name: 'x.txt' }, image, { type: 'image/jpeg', name: 'b.jpg' }] };
  zone.dispatchEvent(event);
  assert.equal(state.uploads.length, 1);
  const options = state.uploads[0];
  assert.deepEqual([options.doctype, options.docname, options.fieldname], ['ilL-Fixture-Template', 'F-1', 'hero_image']);
  assert.equal(options.make_attachments_public, true);
  assert.deepEqual(Array.from(options.restrictions.allowed_file_types), ['image/*']);
  assert.deepEqual(Array.from(options.files), [image]);
  options.on_success({ file_url: '/files/a.png' });
  assert.deepEqual(state.values, [['hero_image', '/files/a.png']]);
});

test('read-only users and unsaved templates get no upload control', t => {
  const readonly = setup(t, { doctype: 'ilL-Fixture-Template', name: 'F-1' }, { write: false });
  readonly.handlers['ilL-Fixture-Template'].refresh(readonly.frm);
  assert.equal(readonly.document.querySelector('.ill-media-drop'), null);
  const unsaved = setup(t, { doctype: 'ilL-Fixture-Template', name: 'new-1' }, { isNew: true });
  unsaved.handlers['ilL-Fixture-Template'].refresh(unsaved.frm);
  assert.equal(unsaved.document.querySelector('.ill-media-drop'), null);
  assert.match(unsaved.document.querySelector('.ill-hero-card').textContent, /Save the template/);
});

function product() {
  return {
    doctype: 'ilL-Webflow-Product',
    name: 'slim',
    hero_image: '/files/hero.jpg',
    fixture_template: 'F 1/2',
    gallery_images: [
      { doctype: 'ilL-Child-Webflow-Gallery-Image', name: 'r1', idx: 1, image: '/files/1.jpg', alt_text: 'One', display_order: 2 },
      { doctype: 'ilL-Child-Webflow-Gallery-Image', name: 'r2', idx: 2, image: '/files/2.jpg', alt_text: HOSTILE, display_order: 1 },
      { doctype: 'ilL-Child-Webflow-Gallery-Image', name: 'r3', idx: 3, image: '/files/3.jpg', alt_text: '', display_order: 3 },
    ],
  };
}

const order = state => Array.from(state.document.querySelectorAll('.ill-gallery-tile')).map(tile => tile.dataset.row);

test('the gallery manager shows the inherited hero read only and tiles in display order', t => {
  const state = setup(t, product());
  state.handlers['ilL-Webflow-Product'].refresh(state.frm);
  const card = state.document.querySelector('.ill-gallery-manager');
  assert.match(card.textContent, /Main product image \(from the template\)/);
  assert.equal(card.querySelector('a').getAttribute('href'), '/app/ill-fixture-template/F%201%2F2');
  assert.deepEqual(order(state), ['r2', 'r1', 'r3']);
  const inputs = card.querySelectorAll('.ill-gallery-tile input');
  assert.equal(inputs[0].value, HOSTILE);
  assert.equal(card.querySelectorAll('script').length, 0);
  assert.match(card.querySelector('[data-row="r3"]').textContent, /Alt text missing/);
});

test('reordering writes display_order and idx and marks the form dirty', t => {
  const state = setup(t, product());
  state.handlers['ilL-Webflow-Product'].refresh(state.frm);
  const later = Array.from(state.document.querySelector('[data-row="r2"]').querySelectorAll('button')).find(b => b.title === 'Move later');
  later.click();
  assert.deepEqual(order(state), ['r1', 'r2', 'r3']);
  assert.deepEqual(state.frm.doc.gallery_images.map(row => [row.name, row.idx, row.display_order]), [['r1', 1, 1], ['r2', 2, 2], ['r3', 3, 3]]);
  assert.equal(state.dirty(), 1);
});

test('alt text edits, removal and multi-file uploads go through the form model', t => {
  const state = setup(t, product());
  state.handlers['ilL-Webflow-Product'].refresh(state.frm);
  const input = state.document.querySelector('[data-row="r3"] input');
  input.value = 'Three';
  input.dispatchEvent(new state.document.defaultView.Event('change'));
  assert.deepEqual(state.values, [['r3', 'alt_text', 'Three']]);

  Array.from(state.document.querySelector('[data-row="r1"]').querySelectorAll('button')).find(b => b.textContent === 'Remove').click();
  state.confirms[0]();
  assert.deepEqual(order(state), ['r2', 'r3']);

  state.document.querySelector('.ill-gallery-manager .ill-media-drop').click();
  const options = state.uploads[0];
  assert.equal(options.allow_multiple, true);
  assert.equal(options.fieldname, undefined);
  options.on_success({ file_url: '/files/new.jpg' });
  const added = state.frm.doc.gallery_images.at(-1);
  assert.deepEqual([added.image, added.display_order], ['/files/new.jpg', 3]);
  assert.deepEqual(order(state), ['r2', 'r3', added.name]);
});
