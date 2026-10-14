// The projects list renders hostile project names without executing them. Needs
// tests/portal_ui/rendered/projects-hostile.html from tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const JQUERY = fs.readFileSync(require.resolve('jquery'), 'utf8');
const PORTAL_UI = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_ui.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function load(name = 'projects-hostile') {
  // jQuery loads ahead of the page script, as the portal's web bundle does.
  const html = fs.readFileSync(path.join(__dirname, `rendered/${name}.html`), 'utf8')
    .replace('<body>', '<body><script>' + JQUERY + '</script><script>' + PORTAL_UI + '</script>');
  const alerts = [];
  const calls = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/projects',
    beforeParse(w) {
      w.alert = value => alerts.push(value);
      w.__ = (text, args) => String(text).replace(/\{(\d)\}/g, (_, i) => args[i]);
      w.frappe = {
        call: args => { calls.push(args); args.callback({ message: { success: true } }); },
        msgprint() {},
        utils: { escape_html: value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') },
      };
    },
  });
  return { dom, w: dom.window, alerts, calls };
}

test('archive and unarchive receive the exact hostile names and run no injected script', async () => {
  const { dom, w, alerts, calls } = load();
  const confirms = [];
  const answer = async () => {
    await tick();
    const dialog = w.document.querySelector('.ill-confirm');
    confirms.push({ text: dialog.textContent, markup: dialog.querySelectorAll('b').length });
    dialog.querySelector('.btn-primary').click();
    await tick(); await tick();
  };
  assert.equal(w.document.querySelectorAll('[onclick]').length, 0);
  w.document.querySelector('.js-archive-project').click();
  await answer();
  w.document.querySelector('.js-unarchive-project[data-project=\'P-2";alert(3);//\']').click();
  await answer();
  assert.deepEqual(alerts, []);
  assert.deepEqual(calls.map(c => [c.method.split('.').pop(), c.args.project_name]), [
    ['archive_project', "P-1');alert(1);//"],
    ['unarchive_project', 'P-2";alert(3);//'],
  ]);
  assert.match(confirms[0].text, /x'\);alert\(2\);\/\/<b>/, 'the name is shown as text');
  assert.equal(confirms[0].markup, 0);
  assert.equal(w.document.querySelector('.js-project-name').textContent, "x');alert(2);//<b>");
  dom.window.close();
});

test('archiving and restoring update the row in place', async () => {
  const { dom, w } = load();
  const row = name => [...w.document.querySelectorAll('.project-row')].find(r => r.dataset.project === name);
  const first = row("P-1');alert(1);//");
  first.querySelector('.js-archive-project').click();
  await tick();
  w.document.querySelector('.ill-confirm .btn-primary').click();
  await tick(); await tick();
  assert.equal(first.dataset.status, 'ARCHIVED');
  assert.ok(first.isConnected, 'the All filter keeps archived projects listed');
  assert.equal(first.querySelector('.js-project-status').hidden, false);
  assert.equal(first.querySelector('.js-unarchive-project').textContent, 'Restore');
  dom.window.close();
});

test('archiving under the Active filter takes the row off the list', async () => {
  const { dom, w } = load();
  w.eval("projectFilter = 'active'");
  const first = w.document.querySelector('.project-row');
  first.querySelector('.js-archive-project').click();
  await tick();
  w.document.querySelector('.ill-confirm .btn-primary').click();
  await tick(); await tick();
  assert.equal(first.isConnected, false);
  assert.equal(w.document.querySelectorAll('.project-row').length, 1);
  dom.window.close();
});

test('read-only viewers get no archive buttons; facts, badges and pages carry over', () => {
  const { dom, w } = load('projects-readonly');
  const doc = w.document;
  assert.equal(doc.querySelectorAll('.js-archive-project, .js-unarchive-project').length, 0);
  const first = doc.querySelector('.project-row');
  assert.equal(first.querySelector('.js-schedule-count').textContent, '2');
  assert.equal(first.querySelector('.js-next-step').textContent, 'Quote ready');
  assert.match(first.textContent, /Acme <Lighting>/);
  assert.ok(doc.querySelectorAll('.project-row')[1].textContent.includes('Private'));
  const pages = [...doc.querySelectorAll('.ill-pager a')].map(a => a.getAttribute('href'));
  assert.deepEqual(pages, ['?page=1&search=x%26y&status=active&sort=name', '?page=3&search=x%26y&status=active&sort=name']);
  assert.equal(doc.querySelector('#project-sort').value, 'name');
  assert.equal(doc.querySelector('#project-search').value, 'x&y');
  dom.window.close();
});
