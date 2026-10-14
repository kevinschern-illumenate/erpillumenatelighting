// The projects list renders hostile project names without executing them. Needs
// tests/portal_ui/rendered/projects-hostile.html from tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const JQUERY = fs.readFileSync(require.resolve('jquery'), 'utf8');

function load() {
  // jQuery loads ahead of the page script, as the portal's web bundle does.
  const html = fs.readFileSync(path.join(__dirname, 'rendered/projects-hostile.html'), 'utf8')
    .replace('<body>', '<body><script>' + JQUERY + '</script>');
  const alerts = [];
  const calls = [];
  const confirms = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/projects',
    beforeParse(w) {
      w.alert = value => alerts.push(value);
      w.frappe = {
        call: args => calls.push(args),
        confirm: (message, yes) => { confirms.push(message); yes(); },
        msgprint() {},
        utils: { escape_html: value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') },
      };
    },
  });
  return { dom, w: dom.window, alerts, calls, confirms };
}

test('archive and unarchive receive the exact hostile names and run no injected script', () => {
  const { dom, w, alerts, calls, confirms } = load();
  const archive = w.document.querySelector('.js-archive-project');
  const unarchive = w.document.querySelector('.js-unarchive-project');
  assert.equal(w.document.querySelectorAll('[onclick]').length, 0);
  archive.click();
  unarchive.click();
  assert.deepEqual(alerts, []);
  assert.deepEqual(calls.map(c => [c.method.split('.').pop(), c.args.project_name]), [
    ['archive_project', "P-1');alert(1);//"],
    ['unarchive_project', 'P-2";alert(3);//'],
  ]);
  assert.match(confirms[0], /x'\);alert\(2\);\/\/&lt;b&gt;/);
  assert.doesNotMatch(confirms[0], /<b>/);
  assert.equal(w.document.querySelector('h5').textContent.includes("x');alert(2);//<b>"), true);
  dom.window.close();
});
