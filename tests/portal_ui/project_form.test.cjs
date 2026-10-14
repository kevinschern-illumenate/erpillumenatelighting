// The project create form and edit modal share one set of fields and one pair of
// party/contact modals (FLOW-8); sales staff name the owner company (REL-5); a user
// without a company gets the dealer application instead (FLOW-5). The end client and
// team are the owner company's project parties, not Customers (DESK-9). Needs
// tests/portal_ui/rendered/project-{new-dealer,new-staff,new-no-company,edit,edit-party}.html
// from tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');
const JQUERY = fs.readFileSync(require.resolve('jquery'), 'utf8');
const PORTAL_UI = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_ui.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

const CONTACTS = { success: true, contacts: [{ name: 'CONT-1', first_name: 'Pat', last_name: 'Lee' }, { name: 'CONT-2', first_name: 'Sam', company_name: 'Acme' }] };

function load(name, respond = () => ({ success: true })) {
  const html = fs.readFileSync(path.join(__dirname, `rendered/${name}.html`), 'utf8')
    .replace('<body>', '<body><script>' + JQUERY + '</script><script>' + PORTAL_UI + '</script>');
  const calls = [];
  const alerts = [];
  const modals = [];
  // jsdom cannot follow the redirect to the new project; keep that noise out of the output.
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => { if (!/navigation/.test(error.message)) throw error; });
  const dom = new JSDOM(html, {
    virtualConsole,
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/projects/new',
    beforeParse(w) {
      w.__ = (text, args) => String(text).replace(/\{(\d)\}/g, (_, i) => args[i]);
      w.frappe = {
        call(options) {
          calls.push(options);
          const method = options.method.split('.').pop();
          options.callback({ message: method === 'get_contacts_for_project' ? CONTACTS : respond(method, options.args) });
        },
        msgprint() { throw new Error('the project page reports through PortalUI, not msgprint'); },
        show_alert: value => alerts.push(value.message),
      };
    },
  });
  const w = dom.window;
  w.jQuery.fn.modal = function (action) { modals.push([this.attr('id'), action]); return this; };
  const methods = () => calls.map(call => call.method.split('.').pop());
  return { w, doc: w.document, calls, alerts, modals, methods };
}

function submit(w, form) {
  form.dispatchEvent(new w.Event('submit', { cancelable: true, bubbles: true }));
}

test('a dealer picks the end client from their own parties and sees who the project is visible to', async () => {
  const { doc } = load('project-new-dealer');
  await tick();
  const label = doc.querySelector('label[for="projectField-end_client_party"]');
  assert.match(label.textContent, /End client/);
  assert.doesNotMatch(doc.getElementById('createProjectForm').textContent, /\bCustomer\b/);
  assert.equal(doc.getElementById('createProjectForm').elements.customer, undefined, 'the billing Customer is not a form field');
  const endClient = doc.getElementById('projectField-end_client_party');
  assert.equal(endClient.value, '');
  assert.equal(endClient.required, false);
  assert.deepEqual([...endClient.options].map(option => option.textContent), ['Select...', 'Hotel <One>']);
  assert.deepEqual([...doc.getElementById('projectField-architect').options].map(option => option.value), ['', 'PTY-2'], 'each role lists only its parties');
  assert.match(doc.getElementById('projectField-end_client_party-help').textContent, /Who is this project for\? Leave it empty for internal stock or a showroom\./);
  assert.equal(doc.getElementById('projectField-owner_customer'), null, 'dealers own their projects automatically');
  const team = doc.querySelector('.js-project-team');
  assert.equal(team.open, false);
  assert.match(team.querySelector('summary').textContent, /Project team \(optional\)/);
  assert.deepEqual([...team.querySelectorAll('select')].map(select => select.name), ['architect', 'lighting_designer', 'general_contractor']);
  // Contacts load into the project manager select.
  assert.deepEqual([...doc.getElementById('projectField-project_manager').options].map(option => option.textContent), ['Select...', 'Pat Lee', 'Sam (Acme)']);
});

test('the Visible to line follows the privacy toggle', () => {
  const { w, doc } = load('project-new-dealer');
  const line = doc.querySelector('#projectVisibleTo .js-visible-to');
  assert.equal(line.textContent, 'Visible to: Acme <Lighting> team');
  const toggle = doc.getElementById('projectField-is_private');
  toggle.checked = true;
  toggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.equal(line.textContent, 'Visible to: you and invited collaborators');
  assert.match(doc.getElementById('projectField-is_private-help').textContent, /collaborators you invite/);
});

test('create checks required fields inline, then sends the form without an owner company', async () => {
  const { w, doc, calls, methods } = load('project-new-dealer', () => ({ success: true, project_name: 'PRJ-1' }));
  await tick();
  const form = doc.getElementById('createProjectForm');
  submit(w, form);
  assert.ok(doc.getElementById('projectField-project_name').classList.contains('is-invalid'));
  assert.deepEqual(methods(), ['get_contacts_for_project']);
  form.elements.project_name.value = 'Lobby';
  form.elements.architect.value = 'PTY-2';
  submit(w, form);
  await tick();
  const create = calls.find(call => call.method.endsWith('.create_project'));
  assert.equal(create.args.project_data.project_name, 'Lobby');
  assert.equal('customer' in create.args.project_data, false, 'the server bills the owner company');
  assert.equal(create.args.project_data.end_client_party, null);
  assert.equal(create.args.project_data.architect, 'PTY-2');
  assert.equal(create.args.project_data.lighting_designer, null);
  assert.equal(create.args.project_data.is_private, 0);
  assert.equal('owner_customer' in create.args.project_data, false);
});

test('a server refusal shows inline on the form', async () => {
  const { w, doc } = load('project-new-dealer', () => ({ success: false, error: 'You don\'t have permission to create projects for this customer' }));
  const form = doc.getElementById('createProjectForm');
  form.elements.project_name.value = 'Lobby';
  submit(w, form);
  await tick();
  const box = doc.getElementById('projectFormError');
  assert.equal(box.hidden, false);
  assert.match(box.textContent, /permission to create projects/);
});

test('sales staff must name the dealer company that owns the project, which loads its parties', async () => {
  const PARTIES = { end_client_party: [{ value: 'PTY-1', label: 'Hotel <One>' }], architect: [], lighting_designer: [], general_contractor: [] };
  const { w, doc, calls } = load('project-new-staff', method => (method === 'get_project_parties' ? { success: true, parties: PARTIES } : { success: true, project_name: 'PRJ-2' }));
  const owner = doc.getElementById('projectField-owner_customer');
  assert.ok(owner.required);
  assert.deepEqual([...owner.options].map(option => option.textContent), ['Select the dealer company...', 'Acme <Lighting>']);
  assert.equal(doc.getElementById('projectVisibleTo'), null, 'staff choose the owner instead of seeing it');
  const form = doc.getElementById('createProjectForm');
  assert.deepEqual([...form.elements.end_client_party.options].map(option => option.value), [''], 'no parties before an owner company');
  form.elements.project_name.value = 'Showroom';
  submit(w, form);
  assert.ok(owner.classList.contains('is-invalid'));
  assert.equal(calls.some(call => call.method.endsWith('.create_project')), false);
  owner.value = 'ACME';
  owner.dispatchEvent(new w.Event('change', { bubbles: true }));
  await tick();
  const load_parties = calls.find(call => call.method.endsWith('.get_project_parties'));
  assert.equal(load_parties.args.owner_customer, 'ACME');
  assert.deepEqual([...form.elements.end_client_party.options].map(option => option.textContent), ['Select...', 'Hotel <One>']);
  form.elements.end_client_party.value = 'PTY-1';
  submit(w, form);
  await tick();
  const create = calls.find(call => call.method.endsWith('.create_project'));
  assert.equal(create.args.project_data.owner_customer, 'ACME');
  assert.equal(create.args.project_data.end_client_party, 'PTY-1');
  assert.equal('customer' in create.args.project_data, false);
});

test('staff add a party for the owner company they picked, and only once they picked it', async () => {
  const { doc, calls, alerts } = load('project-new-staff', method => (method === 'create_party' ? { success: true, party: 'PTY-5', label: 'GC <5>', role: 'General Contractor', existing: false } : { success: true, parties: {} }));
  doc.querySelector('.js-new-party[data-target-select="projectField-general_contractor"]').click();
  doc.getElementById('partyName').value = 'GC <5>';
  doc.querySelector('.js-party-save').click();
  await tick();
  assert.equal(calls.some(call => call.method.endsWith('.create_party')), false);
  assert.deepEqual(alerts, ['Choose the owner company first.']);
  doc.getElementById('projectField-owner_customer').value = 'ACME';
  doc.querySelector('.js-party-save').click();
  await tick();
  const create = calls.find(call => call.method.endsWith('.create_party'));
  assert.deepEqual(
    { name: create.args.party_data.party_name, role: create.args.party_data.role, owner: create.args.party_data.owner_customer },
    { name: 'GC <5>', role: 'General Contractor', owner: 'ACME' }
  );
  assert.equal(doc.getElementById('projectField-general_contractor').value, 'PTY-5');
});

test('one party modal adds a party in the role it was opened for and picks it there', async () => {
  const { doc, calls, alerts, modals } = load('project-new-dealer', method => (method === 'create_party' ? { success: true, party: 'PTY-9', label: 'Studio <9>', role: 'Architect', existing: false } : { success: true }));
  assert.equal(doc.querySelectorAll('#partyModal').length, 1);
  assert.equal(doc.querySelectorAll('#contactModal').length, 1);
  doc.querySelector('.js-new-party[data-target-select="projectField-architect"]').click();
  assert.deepEqual(modals.at(-1), ['partyModal', 'show']);
  doc.querySelector('.js-party-save').click();
  assert.ok(doc.getElementById('partyName').classList.contains('is-invalid'));
  doc.getElementById('partyName').value = 'Studio <9>';
  doc.getElementById('partyEmail').value = 'hi@studio.test';
  doc.querySelector('.js-party-save').click();
  await tick();
  assert.equal(calls.some(call => call.method.endsWith('.create_customer')), false, 'no Customer master is created');
  const create = calls.find(call => call.method.endsWith('.create_party'));
  assert.equal(create.args.party_data.party_name, 'Studio <9>');
  assert.equal(create.args.party_data.role, 'Architect');
  assert.equal(create.args.party_data.email, 'hi@studio.test');
  assert.equal(create.args.party_data.owner_customer, null, 'dealers always add to their own company');
  const architect = doc.getElementById('projectField-architect');
  assert.equal(architect.value, 'PTY-9');
  assert.equal(architect.options[architect.options.length - 1].textContent, 'Studio <9>');
  assert.deepEqual([...doc.getElementById('projectField-lighting_designer').options].map(option => option.value), [''], 'other roles are left alone');
  assert.equal(doc.getElementById('projectField-end_client_party').value, '', 'the end client is left alone');
  assert.deepEqual(modals.at(-1), ['partyModal', 'hide']);
  assert.deepEqual(alerts, ['Studio &lt;9&gt; added']);
});

test('a name the company already has picks the existing party instead of duplicating it', async () => {
  const { doc, alerts } = load('project-new-dealer', method => (method === 'create_party' ? { success: true, party: 'PTY-2', label: 'Studio <A>', role: 'Architect', existing: true } : { success: true }));
  doc.querySelector('.js-new-party[data-target-select="projectField-architect"]').click();
  doc.getElementById('partyName').value = 'studio <a>';
  doc.querySelector('.js-party-save').click();
  await tick();
  const architect = doc.getElementById('projectField-architect');
  assert.equal(architect.value, 'PTY-2');
  assert.deepEqual([...architect.options].map(option => option.value), ['', 'PTY-2']);
  assert.deepEqual(alerts, ['Studio &lt;A&gt; is already on your list']);
});

test('a user without a company is offered the dealer application instead of a broken form', () => {
  const { doc, calls } = load('project-new-no-company');
  const card = doc.getElementById('projectNeedsCompany');
  assert.match(card.textContent, /Your account isn't linked to a company yet/);
  assert.equal(card.querySelector('a.btn-primary').getAttribute('href'), '/portal/request-dealer-access');
  assert.equal(doc.getElementById('createProjectForm'), null);
  assert.equal(doc.querySelector('.js-new-party'), null);
  assert.equal(doc.getElementById('partyModal'), null);
  assert.deepEqual(calls, []);
});

test('the edit modal reuses the fields: end client read-only, team prefilled, contacts kept', async () => {
  const { w, doc, calls, modals } = load('project-edit', method => (method === 'create_contact' ? { success: true, contact_name: 'CONT-7' } : { success: true }));
  assert.match(doc.querySelector('.card-body p.text-muted').textContent, /End client:\s*Client <Co>/);
  const form = doc.getElementById('editProjectForm');
  assert.equal(doc.getElementById('projectField-end_client').value, 'Client <Co>');
  assert.equal(doc.getElementById('projectField-end_client').disabled, true);
  assert.equal(form.elements.customer, undefined);
  assert.equal(form.querySelector('.js-project-team').open, true, 'a project with a team opens the section');
  assert.equal(form.elements.end_client_party, undefined, 'a Customer end client stays read-only');
  assert.equal(form.elements.architect.value, 'PTY-2');
  assert.equal(form.elements.project_manager.value, 'CONT-1');
  assert.equal(doc.querySelector('#projectVisibleTo .js-visible-to').textContent, 'Visible to: Acme <Lighting> team');
  doc.querySelector('.js-edit-project').click();
  await tick();
  assert.deepEqual(modals.at(-1), ['editProjectModal', 'show']);
  assert.equal(form.elements.project_manager.value, 'CONT-1', 'loading contacts keeps the current project manager');
  doc.querySelector('.js-new-contact').click();
  doc.getElementById('contactFirstName').value = 'Jo';
  doc.querySelector('.js-contact-save').click();
  await tick();
  const contact = calls.find(call => call.method.endsWith('.create_contact'));
  assert.equal(contact.args.contact_data.first_name, 'Jo');
  assert.equal(contact.args.contact_data.designation, 'Project Manager');
  assert.equal(form.elements.project_manager.value, 'CONT-7');
  submit(w, form);
  await tick();
  const update = calls.find(call => call.method.endsWith('.update_project'));
  assert.equal(update.args.project_name, 'P-1');
  assert.equal('customer' in update.args.project_data, false);
  assert.equal(update.args.project_data.project_manager, 'CONT-7');
  assert.equal(update.args.project_data.architect, 'PTY-2');
  assert.equal(update.args.project_data.lighting_designer, '');
  assert.equal('end_client_party' in update.args.project_data, false);
});

test('a party end client can be changed in the edit modal, and new parties go to the project owner', async () => {
  const { w, doc, calls } = load('project-edit-party', method => (method === 'create_party' ? { success: true, party: 'PTY-7', label: 'Hotel Two', role: 'End Client', existing: false } : { success: true }));
  assert.match(doc.querySelector('.card-body p.text-muted').textContent, /End client:\s*Hotel <One>/);
  const form = doc.getElementById('editProjectForm');
  assert.equal(doc.getElementById('projectField-end_client'), null);
  assert.equal(form.elements.end_client_party.value, 'PTY-1');
  form.querySelector('.js-new-party[data-target-select="projectField-end_client_party"]').click();
  doc.getElementById('partyName').value = 'Hotel Two';
  doc.querySelector('.js-party-save').click();
  await tick();
  const create = calls.find(call => call.method.endsWith('.create_party'));
  assert.equal(create.args.party_data.role, 'End Client');
  assert.equal(create.args.party_data.owner_customer, 'ACME');
  submit(w, form);
  await tick();
  const update = calls.find(call => call.method.endsWith('.update_project'));
  assert.equal(update.args.project_data.end_client_party, 'PTY-7');
  assert.equal('customer' in update.args.project_data, false);
});
