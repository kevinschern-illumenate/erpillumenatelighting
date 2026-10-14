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

function load() {
  // jQuery loads ahead of the page script, as the portal's web bundle does.
  const html = fs.readFileSync(path.join(__dirname, 'rendered/projects-hostile.html'), 'utf8')
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
  assert.equal(w.document.querySelector('h5').textContent.includes("x');alert(2);//<b>"), true);
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
  assert.ok(first.classList.contains('d-none'), 'hidden while archived projects are hidden');
  assert.equal(first.querySelector('.js-project-status').textContent, 'ARCHIVED');
  assert.ok(first.querySelector('.js-unarchive-project'));
  assert.equal(first.querySelector('.js-archived-note').hidden, false);
  dom.window.close();
});
