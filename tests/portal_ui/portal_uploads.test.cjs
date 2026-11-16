const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const FILE = path.join(__dirname, '../../illumenate_lighting/public/js/portal_uploads.js');

function load(response) {
  const requests = [];
  const context = {
    window: {},
    FormData: class { constructor() { this.entries = []; } append(key, value) { this.entries.push([key, value]); } },
    frappe: { csrf_token: 'token' },
    __: (text, args) => (args ? text.replace('{0}', args[0]) : text),
    fetch: async (url, options) => { requests.push({ url, options }); return response; },
  };
  vm.runInNewContext(fs.readFileSync(FILE, 'utf8'), context, { filename: FILE });
  return { uploads: context.window.PortalUploads, requests };
}

const file = (name) => ({ name, size: 10, lastModified: 1 });
const ok = { ok: true, json: async () => ({ message: { success: true, file_id: 'F1' } }) };

test('HEIC and HEIF photos reach the server for conversion (4.2)', async () => {
  const { uploads, requests } = load(ok);
  for (const name of ['IMG_0001.HEIC', 'photo.heif', 'scan.pdf', 'a.JPG']) {
    assert.equal((await uploads.upload(file(name))).file_id, 'F1');
  }
  assert.equal(requests.length, 4);
  await assert.rejects(uploads.upload(file('clip.mov')), /PDF, JPEG, PNG or HEIC/);
  assert.equal(requests.length, 4);
});

test('server rejection reasons are shown as plain text (4.2)', async () => {
  const messages = JSON.stringify([JSON.stringify({ message: '<b>HEIC photos are not supported here</b>; export the photo as JPEG' })]);
  const { uploads } = load({ ok: false, json: async () => ({ _server_messages: messages }) });
  await assert.rejects(uploads.upload(file('IMG.heic')), (error) => {
    assert.match(error.message, /Upload failed for IMG\.heic\..* HEIC photos are not supported here; export the photo as JPEG$/);
    assert.doesNotMatch(error.message, /<b>/);
    return true;
  });
});

test('unreadable error bodies still fail with the generic retry message', async () => {
  const { uploads } = load({ ok: false, json: async () => { throw new Error('not json'); } });
  await assert.rejects(uploads.upload(file('a.png')), /^Error: Upload failed for a\.png\. Your draft is preserved; retry this file\.$/);
});
