const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');

const JS = path.join(__dirname, '../../illumenate_lighting/public/js');
const uploads = fs.readFileSync(path.join(JS, 'portal_uploads.js'), 'utf8');
const uploader = fs.readFileSync(path.join(JS, 'portal_uploader.js'), 'utf8');
const tick = async (times = 3) => { for (let i = 0; i < times; i++) await new Promise(resolve => setImmediate(resolve)); };

function setup({flags, multiple = true} = {}) {
  const dom = new JSDOM('<!doctype html><body></body>', {runScripts: 'outside-only', url: 'https://portal.test/'});
  const w = dom.window;
  const doc = w.document;
  if (flags) {
    const node = doc.createElement('script');
    node.type = 'application/json'; node.id = 'ill-portal-flags'; node.textContent = JSON.stringify(flags);
    doc.body.append(node);
  }
  w.__ = (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, index) => String((args || [])[index]));
  w.frappe = {csrf_token: 'csrf'};
  w.DataTransfer = class { constructor() { const list = []; this.files = list; this.items = {add: file => list.push(file)}; } };
  const xhrs = [];
  let active = 0, peak = 0;
  w.XMLHttpRequest = class {
    constructor() { this.upload = {}; this.headers = {}; xhrs.push(this); }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(key, value) { this.headers[key] = value; }
    send(body) { this.body = body; active++; peak = Math.max(peak, active); }
    abort() { this.aborted = true; active--; this.onabort?.(); }
    respond(status, json) { this.status = status; this.responseText = JSON.stringify(json); active--; this.onload(); }
    progress(loaded, total) { this.upload.onprogress?.({lengthComputable: true, loaded, total}); }
  };
  const form = doc.createElement('form');
  const input = doc.createElement('input');
  input.type = 'file'; input.multiple = multiple; input.setAttribute('data-portal-uploader', '');
  let files = [];
  Object.defineProperty(input, 'files', {configurable: true, get: () => files, set: value => { files = value; }});
  form.append(input); doc.body.append(form);
  w.eval(uploads);
  w.eval(uploader);
  w.PortalUploader.enhance();
  const file = (name, size = 10) => new w.File(['x'.repeat(size)], name, {lastModified: 1});
  const pick = list => { files = list; input.dispatchEvent(new w.Event('change')); };
  return {dom, w, doc, form, input, xhrs, file, pick, peak: () => peak, setFiles: value => { files = value; }};
}

const ok = id => ({message: {success: true, file_id: id, pages: id.endsWith('pdf') ? 3 : null}});

test('kill switch leaves the native input untouched (4.1)', () => {
  const {dom, doc, input, w} = setup({flags: {upload_widget: false}});
  assert.equal(input._portalUploader, undefined);
  assert.equal(doc.querySelectorAll('.ill-uploader').length, 0);
  assert.equal(w.PortalUploader.attach(input), null);
  dom.window.close();
});

test('pages enhance marked inputs and render file names as text with clear rejections', async () => {
  const {dom, doc, input, file, pick} = setup();
  assert.ok(input._portalUploader, 'auto-enhanced through data-portal-uploader');
  pick([file('<img src=x onerror=bad()>.pdf'), file('clip.mov'), file('empty.png', 0), file('huge.pdf', 20 * 1024 * 1024 + 1)]);
  await tick();
  const rows = doc.querySelectorAll('.ill-uploader__row');
  assert.equal(rows.length, 1);
  assert.equal(doc.querySelectorAll('.ill-uploader img').length, 0);
  assert.equal(rows[0].querySelector('.ill-uploader__name').textContent, '<img src=x onerror=bad()>.pdf');
  assert.equal(rows[0].querySelector('.ill-uploader__badge').textContent, 'PDF');
  const message = doc.querySelector('.ill-uploader__message').textContent;
  assert.match(message, /clip\.mov was not added: use PDF, JPEG, PNG or HEIC/);
  assert.match(message, /empty\.png was not added: the file is empty/);
  assert.match(message, /huge\.pdf was not added: each file must be 20 MiB or smaller/);
  assert.equal(input.files.length, 1, 'the native FileList mirrors accepted files');
  dom.window.close();
});

test('ten-file cap and single-file inputs replace the previous choice', async () => {
  const many = setup();
  many.pick(Array.from({length: 12}, (_v, index) => many.file('f' + index + '.pdf')));
  await tick();
  assert.equal(many.doc.querySelectorAll('.ill-uploader__row').length, 10);
  assert.match(many.doc.querySelector('.ill-uploader__message').textContent, /f10\.pdf was not added: choose at most 10 files/);
  many.dom.window.close();
  const single = setup({multiple: false});
  single.pick([single.file('a.pdf')]); await tick();
  single.pick([single.file('b.pdf')]); await tick();
  const names = Array.from(single.doc.querySelectorAll('.ill-uploader__name')).map(node => node.textContent);
  assert.deepEqual(names, ['b.pdf']);
  single.dom.window.close();
});

test('uploads run three at a time with progress and return ids in display order', async () => {
  const {dom, w, doc, input, xhrs, file, pick, peak} = setup();
  pick(['a.pdf', 'b.png', 'c.heic', 'd.pdf', 'e.jpg'].map(name => file(name)));
  await tick();
  const pending = w.PortalUploads.uploadAll(input, 'ilL-Document-Request', 'DR-1');
  await tick();
  assert.equal(xhrs.length, 3);
  assert.equal(xhrs[0].url, '/api/method/illumenate_lighting.illumenate_lighting.portal.files.upload');
  assert.equal(xhrs[0].headers['X-Frappe-CSRF-Token'], 'csrf');
  assert.equal(xhrs[0].body.get('parent_type'), 'ilL-Document-Request');
  assert.equal(xhrs[0].body.get('parent_name'), 'DR-1');
  xhrs[1].progress(5, 10);
  assert.equal(doc.querySelectorAll('.ill-uploader__progress')[1].value, 50);
  xhrs[2].respond(200, ok('C')); await tick();
  xhrs[1].respond(200, ok('B')); await tick();
  xhrs[0].respond(200, ok('A.pdf')); await tick();
  xhrs[3].respond(200, ok('D')); xhrs[4].respond(200, ok('E'));
  assert.deepEqual([...await pending], ['A.pdf', 'B', 'C', 'D', 'E']);
  assert.equal(peak(), 3);
  assert.match(doc.querySelector('.ill-uploader__meta').textContent, /3 pages/);
  dom.window.close();
});

test('a failed file shows the server reason, retries alone, and resubmits reuse finished uploads', async () => {
  const {dom, w, doc, input, xhrs, file, pick} = setup();
  pick([file('a.pdf'), file('b.heic')]);
  await tick();
  const first = w.PortalUploads.uploadAll(input, 'Issue', 'I-1');
  await tick();
  xhrs[0].respond(200, ok('A'));
  const messages = JSON.stringify([JSON.stringify({message: 'HEIC photos are not supported here; export the photo as JPEG'})]);
  xhrs[1].respond(417, {_server_messages: messages});
  await assert.rejects(first, /Upload failed for b\.heic\..*export the photo as JPEG/);
  const row = doc.querySelectorAll('.ill-uploader__row')[1];
  assert.equal(row.dataset.state, 'failed');
  assert.match(row.querySelector('.ill-uploader__status').textContent, /Failed: HEIC photos are not supported here/);
  assert.equal(row.querySelector('.ill-uploader__retry').hidden, false);
  row.querySelector('.ill-uploader__retry').click();
  await tick();
  assert.equal(xhrs.length, 3, 'retry uploads only the failed file');
  xhrs[2].respond(200, ok('B'));
  await tick();
  assert.deepEqual([...await w.PortalUploads.uploadAll(input, 'Issue', 'I-1')], ['A', 'B']);
  assert.equal(xhrs.length, 3, 'finished files are not uploaded twice');
  dom.window.close();
});

test('cancel aborts one upload and the rest still finish', async () => {
  const {dom, w, doc, input, xhrs, file, pick} = setup();
  pick([file('a.pdf'), file('b.pdf')]);
  await tick();
  const pending = w.PortalUploads.uploadAll(input);
  await tick();
  doc.querySelectorAll('.ill-uploader__cancel')[0].click();
  assert.equal(xhrs[0].aborted, true);
  xhrs[1].respond(200, ok('B'));
  assert.deepEqual([...await pending], ['B']);
  assert.equal(doc.querySelectorAll('.ill-uploader__row').length, 1);
  assert.equal(input.files.length, 1);
  dom.window.close();
});

test('clearing the input or resetting the form clears the widget', async () => {
  const {dom, w, doc, form, input, xhrs, file, pick, setFiles} = setup();
  pick([file('a.pdf')]);
  await tick();
  setFiles([]);
  assert.deepEqual([...await w.PortalUploads.uploadAll(input)], []);
  assert.equal(xhrs.length, 0);
  assert.equal(doc.querySelectorAll('.ill-uploader__row').length, 0);
  pick([file('b.pdf')]);
  await tick();
  form.dispatchEvent(new w.Event('reset'));
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(doc.querySelectorAll('.ill-uploader__row').length, 0);
  dom.window.close();
});

test('JPEG EXIF orientation is read from either byte order (4.2)', () => {
  const {dom, w} = setup();
  const jpeg = little => {
    const bytes = [0xFF, 0xD8, 0xFF, 0xE1, 0x00, 0x22, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00];
    const u16 = value => (little ? [value & 0xFF, value >> 8] : [value >> 8, value & 0xFF]);
    const u32 = value => (little ? [value & 0xFF, (value >> 8) & 0xFF, 0, 0] : [0, 0, (value >> 8) & 0xFF, value & 0xFF]);
    bytes.push(...(little ? [0x49, 0x49] : [0x4D, 0x4D]), ...u16(42), ...u32(8), ...u16(1));
    bytes.push(...u16(0x0112), ...u16(3), ...u32(1), ...u16(6), 0, 0, ...u32(0));
    return new Uint8Array(bytes).buffer;
  };
  assert.equal(w.PortalUploader.jpegOrientation(jpeg(false)), 6);
  assert.equal(w.PortalUploader.jpegOrientation(jpeg(true)), 6);
  assert.equal(w.PortalUploader.jpegOrientation(new Uint8Array([0x89, 0x50, 0x4E, 0x47]).buffer), 1);
  assert.equal(w.PortalUploader.jpegOrientation(new Uint8Array([0xFF, 0xD8, 0xFF, 0xDA, 0, 2]).buffer), 1);
  dom.window.close();
});
