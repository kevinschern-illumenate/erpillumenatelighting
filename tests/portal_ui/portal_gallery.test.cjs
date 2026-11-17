const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');

const JS = path.join(__dirname, '../../illumenate_lighting/public/js');
const gallery = fs.readFileSync(path.join(JS, 'portal_gallery.js'), 'utf8');
const dealerLogo = fs.readFileSync(path.join(JS, 'portal_dealer_logo.js'), 'utf8');
const tick = async (times = 4) => { for (let i = 0; i < times; i++) await new Promise(resolve => setImmediate(resolve)); };
const plain = value => JSON.parse(JSON.stringify(value));

function setup({flags, body = ''} = {}) {
  const dom = new JSDOM(`<!doctype html><body>${body}</body>`, {runScripts: 'outside-only', url: 'https://portal.test/'});
  const w = dom.window;
  if (flags) {
    const node = w.document.createElement('script');
    node.type = 'application/json'; node.id = 'ill-portal-flags'; node.textContent = JSON.stringify(flags);
    w.document.body.append(node);
  }
  w.__ = (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, index) => String((args || [])[index]));
  const calls = [];
  const responses = {};
  w.PortalUploads = {
    call: async (method, args) => {
      calls.push({method: method.split('.').slice(-2).join('.'), args: plain(args)});
      const response = responses[method.split('.').pop()];
      if (response instanceof Error) throw response;
      return typeof response === 'function' ? response(args) : response;
    },
    upload: async file => { calls.push({method: 'upload', args: {name: file.name}}); return {file_id: 'F-' + file.name}; },
  };
  return {dom, w, doc: w.document, calls, responses};
}

const HOSTILE = '<img src=x onerror="window.pwned=1">';
const DATA = {
  success: true, enabled: true, purposes: ['Site photo', 'Reference image', 'PO'],
  requests: [{name: 'ILL-REQ-1', request_type: 'Drawing', status: 'Submitted'}],
  items: [
    {name: 'D1', schedule: 'S1', schedule_name: 'Lobby', schedule_modified: 'm1', line_key: 'L1', line_id: 'A1', file_name: 'a.jpg', title: 'a.jpg', purpose: 'Site photo', caption: HOSTILE, thumbnail_url: '/private/files/a.thumb.webp', image_url: '/private/files/a.jpg', download_url: '/api/method/x.download?name=D1', can_edit: true},
    {name: 'D2', schedule: 'S1', schedule_name: 'Lobby', schedule_modified: 'm1', line_key: 'L2', line_id: 'B2', file_name: 'b.png', title: 'b.png', purpose: 'Unknown', caption: '', thumbnail_url: '/private/files/b.thumb.webp', image_url: '/private/files/b.png', download_url: '/api/method/x.download?name=D2', can_edit: false},
  ],
};

test('rows group by purpose in the listed order and unknown purposes fall into Other files', () => {
  const {w} = setup();
  w.eval(gallery);
  const groups = plain(w.PortalGallery.groupByPurpose([{purpose: 'PO'}, {purpose: ''}, {purpose: 'Site photo'}, {purpose: 'Nope'}], ['Site photo', 'PO']));
  assert.deepEqual(groups.map(group => [group.label, group.rows.length]), [['Site photo', 1], ['PO', 1], ['Other files', 2]]);
});

test('the gallery renders captions as text, thumbnails lazily, and edit controls only where allowed', async () => {
  const {w, doc, calls, responses} = setup({body: '<div id="g"></div>'});
  responses.gallery = DATA;
  w.eval(gallery);
  await w.PortalGallery.mount(doc.getElementById('g'), {project: 'P'});
  assert.deepEqual(calls[0], {method: 'media.gallery', args: {project: 'P'}});
  const root = doc.getElementById('g');
  assert.equal(root.querySelectorAll('img[onerror]').length, 0);
  assert.equal(w.pwned, undefined);
  assert.ok(root.textContent.includes(HOSTILE));
  assert.deepEqual([...root.querySelectorAll('h5')].map(node => node.textContent), ['Site photo', 'Other files']);
  const images = [...root.querySelectorAll('.ill-gallery__thumb img')];
  assert.deepEqual(images.map(image => image.getAttribute('src')), ['/private/files/a.thumb.webp', '/private/files/b.thumb.webp']);
  assert.ok(images.every(image => image.getAttribute('loading') === 'lazy'));
  const items = root.querySelectorAll('.ill-gallery__item');
  assert.equal(items[0].querySelectorAll('.ill-gallery__edit').length, 1);
  assert.equal(items[0].querySelectorAll('.ill-gallery__request').length, 1);
  assert.equal(items[1].querySelectorAll('.ill-gallery__edit, .ill-gallery__request').length, 0);
});

test('the lightbox shows the original with its caption, navigates and closes on Escape', async () => {
  const {w, doc, responses} = setup({body: '<div id="g"></div>'});
  responses.gallery = DATA;
  w.eval(gallery);
  await w.PortalGallery.mount(doc.getElementById('g'), {project: 'P'});
  doc.querySelector('.ill-gallery__thumb').click();
  const box = doc.querySelector('.ill-lightbox');
  assert.equal(box.getAttribute('role'), 'dialog');
  assert.equal(box.querySelector('img').getAttribute('src'), '/private/files/a.jpg');
  assert.ok(box.querySelector('.ill-lightbox__caption').textContent.includes(HOSTILE));
  assert.equal(box.querySelectorAll('.ill-lightbox__caption *').length, 0);
  assert.equal(box.querySelector('a').getAttribute('href'), '/api/method/x.download?name=D1');
  doc.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'ArrowRight'}));
  assert.equal(box.querySelector('img').getAttribute('src'), '/private/files/b.png');
  doc.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Escape'}));
  assert.equal(doc.querySelector('.ill-lightbox'), null);
});

test('saving a caption and sending to a drawing request call the server with the concurrency token', async () => {
  const {w, doc, calls, responses} = setup({body: '<div id="g"></div>'});
  responses.gallery = DATA;
  responses.annotate = {success: true};
  responses.attach_to_request = {success: true, already_attached: false};
  w.eval(gallery);
  await w.PortalGallery.mount(doc.getElementById('g'), {project: 'P'});
  const edit = doc.querySelector('.ill-gallery__edit');
  edit.querySelector('select').value = 'PO';
  edit.querySelector('input').value = 'Signed PO';
  edit.querySelector('button').click();
  await tick();
  assert.deepEqual(calls[1], {method: 'line_documents.annotate', args: {name: 'D1', expected_modified: 'm1', purpose: 'PO', caption: 'Signed PO'}});
  assert.equal(calls[2].method, 'media.gallery');
  doc.querySelector('.ill-gallery__request button').click();
  await tick();
  assert.deepEqual(calls[3], {method: 'media.attach_to_request', args: {document: 'D1', request_name: 'ILL-REQ-1'}});
  assert.ok(doc.querySelector('[role="status"]').textContent.includes('ILL-REQ-1'));
});

test('the kill switch hides the gallery without calling the server', async () => {
  const {w, doc, calls} = setup({flags: {gallery: false}, body: '<div id="g"></div>'});
  w.eval(gallery);
  assert.equal(await w.PortalGallery.mount(doc.getElementById('g'), {project: 'P'}), null);
  assert.equal(doc.getElementById('g').hidden, true);
  assert.equal(calls.length, 0);
});

test('server errors render as text', async () => {
  const {w, doc, responses} = setup({body: '<div id="g"></div>'});
  responses.gallery = new Error(HOSTILE);
  w.eval(gallery);
  await w.PortalGallery.mount(doc.getElementById('g'), {schedule: 'S1', lineKey: 'L1'});
  assert.equal(doc.querySelectorAll('#g img').length, 0);
  assert.ok(doc.getElementById('g').textContent.includes(HOSTILE));
});

const LOGO = `<section id="dealerLogo" data-logo-url="" data-company="Acme &lt;b&gt;">
  <div data-logo-preview></div><input type="file" data-logo-input>
  <button data-logo-save></button><button data-logo-remove hidden></button><div data-logo-feedback></div></section>`;

function logoSetup() {
  const env = setup({body: LOGO});
  const {w, doc} = env;
  w.URL.createObjectURL = () => 'blob:preview';
  w.URL.revokeObjectURL = () => {};
  const input = doc.querySelector('[data-logo-input]');
  let files = [];
  Object.defineProperty(input, 'files', {configurable: true, get: () => files});
  w.eval(dealerLogo);
  w.PortalDealerLogo.mount(doc.getElementById('dealerLogo'));
  const pick = name => { files = name ? [new w.File(['x'], name)] : []; input.dispatchEvent(new w.Event('change')); };
  return {...env, input, pick};
}

test('the dealer logo previews on the title block, saves through a private upload and can be removed', async () => {
  const {doc, calls, responses, pick} = logoSetup();
  const preview = () => doc.querySelector('.ill-logo-preview');
  assert.equal(preview().querySelectorAll('img').length, 0);
  assert.ok(preview().textContent.includes('Acme <b>'));
  assert.equal(preview().querySelectorAll('b').length, 0);
  pick('logo.png');
  assert.equal(preview().querySelector('img').getAttribute('src'), 'blob:preview');
  assert.equal(calls.length, 0);
  responses.set_dealer_logo = {success: true, dealer_logo: '/files/dealer-logo-abc.png'};
  doc.querySelector('[data-logo-save]').click();
  await tick();
  assert.deepEqual(calls.slice(0, 2), [{method: 'upload', args: {name: 'logo.png'}}, {method: 'accounts.set_dealer_logo', args: {file_id: 'F-logo.png'}}]);
  assert.equal(preview().querySelector('img').getAttribute('src'), '/files/dealer-logo-abc.png');
  assert.equal(doc.querySelector('[data-logo-remove]').hidden, false);
  responses.set_dealer_logo = {success: true, dealer_logo: null};
  doc.querySelector('[data-logo-remove]').click();
  await tick();
  assert.deepEqual(calls[2], {method: 'accounts.set_dealer_logo', args: {remove: 1}});
  assert.equal(preview().querySelectorAll('img').length, 0);
  assert.equal(doc.querySelector('[data-logo-remove]').hidden, true);
});

test('a non-image logo is refused before any upload', async () => {
  const {doc, calls, pick} = logoSetup();
  pick('logo.pdf');
  assert.match(doc.querySelector('[data-logo-feedback]').textContent, /PNG or JPEG/);
  doc.querySelector('[data-logo-save]').click();
  await tick();
  assert.equal(calls.length, 0);
});
