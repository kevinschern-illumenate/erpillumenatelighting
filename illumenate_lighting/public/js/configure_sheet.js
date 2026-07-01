(function () {
  const templates = window.ILL_LED_SHEET_TEMPLATES || [];
  const ctx = window.ILL_LED_SHEET_CONTEXT || {};
  let lastResult = null;
  const $id = (id) => document.getElementById(id);
  const money = (v) => `$${Number(v || 0).toFixed(2)}`;
  const option = (value, label) => { const o = document.createElement('option'); o.value = value || ''; o.textContent = label || value || ''; return o; };
  function fill(select, rows, labelFn) { if (!select) return; select.innerHTML = ''; select.appendChild(option('', 'Select...')); (rows || []).forEach(r => select.appendChild(option(r.attribute_link || r.name, labelFn ? labelFn(r) : (r.option_code || r.name)))); const def = (rows || []).find(r => r.is_default); if (def) select.value = def.attribute_link || def.name; }
  function selectedTemplate() { return templates.find(t => t.name === $id('sheetTemplate').value); }
  function byType(t, type) { return (t && t.allowed_options || []).filter(o => o.option_type === type); }
  function renderTemplate() { const t = selectedTemplate(); fill($id('sheetSpec'), t ? t.allowed_specs : [], r => `${r.name} (${r.total_sheet_watts || 0}W, ${r.sheet_width_ft || 0}x${r.sheet_height_ft || 0} ft)`); fill($id('sheetCct'), byType(t, 'CCT'), r => r.option_code); fill($id('sheetOutput'), byType(t, 'Output Level'), r => r.option_code); fill($id('sheetEnvironment'), byType(t, 'Environment Rating'), r => r.option_code); fill($id('sheetMounting'), byType(t, 'Mounting'), r => r.option_code); fill($id('sheetFinish'), byType(t, 'Finish'), r => r.option_code); }
  function currentSchedule() { return ($id('scheduleSelect') && $id('scheduleSelect').value) || ctx.schedule_name; }
  function currentLine() { const sel = $id('lineSelect'); if (sel && sel.value && sel.value !== '__new__') return sel.value; return ctx.line_idx; }
  function payload() {
    return {
      template: $id('sheetTemplate').value,
      spec: $id('sheetSpec').value,
      options: { CCT: $id('sheetCct').value, 'Output Level': $id('sheetOutput').value, 'Environment Rating': $id('sheetEnvironment').value, Mounting: $id('sheetMounting').value, Finish: $id('sheetFinish').value },
      coverage_width_value: $id('coverageWidthValue').value,
      coverage_width_unit: $id('coverageWidthUnit').value,
      coverage_height_value: $id('coverageHeightValue').value,
      coverage_height_unit: $id('coverageHeightUnit').value,
      include_power_supply: $id('sheetIncludePowerSupply').checked ? 1 : 0,
      schedule_name: currentSchedule(),
      line_idx: currentLine(),
    };
  }
  function render(r) {
    const includePs = !!r.include_power_supply;
    const groups = (r.groups || []).map(g => `<tr><td>${g.group_number}</td><td>${g.sheet_count}</td><td>${g.group_watts}</td><td>${g.compatible_driver || ''}</td></tr>`).join('');
    const p = r.pricing || {};
    const psRows = (r.power_supplies || []).map(ps => `<tr><td>${ps.item_name || ps.driver_item}</td><td>${ps.qty}</td><td>${ps.max_wattage || ''}W</td><td>${money(ps.line_total)}</td></tr>`).join('');
    const psBlock = includePs
      ? `<h6 class="mt-3">Power Supplies</h6><table class="table table-sm"><thead><tr><th>Item</th><th>Qty</th><th>Supports</th><th>MSRP</th></tr></thead><tbody>${psRows || '<tr><td colspan="4" class="text-muted">None</td></tr>'}</tbody></table>`
      : `<p class="text-muted mt-3">Power supplies excluded (calculated for validation only).</p>`;
    $id('sheetSummary').innerHTML =
      `<h6>${r.part_number || ''}</h6>` +
      `<dl class="row mb-0">` +
      `<dt class="col-7">Requested area</dt><dd class="col-5">${Number(r.total_coverage_sqft).toFixed(2)} sq ft</dd>` +
      `<dt class="col-7">Normalized dimensions</dt><dd class="col-5">${Number(r.coverage_width_ft).toFixed(2)} x ${Number(r.coverage_height_ft).toFixed(2)} ft</dd>` +
      `<dt class="col-7">Sheet / panel dimensions</dt><dd class="col-5">${Number(r.sheet_width_ft).toFixed(2)} x ${Number(r.sheet_height_ft).toFixed(2)} ft</dd>` +
      `<dt class="col-7">Total panels needed</dt><dd class="col-5">${r.panels_needed}</dd>` +
      `<dt class="col-7">Panels wide / tall</dt><dd class="col-5">${r.panels_wide} / ${r.panels_tall}</dd>` +
      `<dt class="col-7">Number of groups</dt><dd class="col-5">${r.total_groups}</dd>` +
      `<dt class="col-7">Panels per group</dt><dd class="col-5">${(r.panels_per_group || []).join(', ')}</dd>` +
      `<dt class="col-7">Jumper cables</dt><dd class="col-5">${r.jumper_cable_qty}</dd>` +
      `<dt class="col-7">Leader cables</dt><dd class="col-5">${r.leader_cable_qty}</dd>` +
      `<dt class="col-7">Total watts</dt><dd class="col-5">${Number(r.total_system_watts).toFixed(2)}W</dd>` +
      `</dl>` +
      `<h6 class="mt-3">Groups</h6><table class="table table-sm"><thead><tr><th>Group</th><th>Panels</th><th>Watts</th><th>Driver</th></tr></thead><tbody>${groups}</tbody></table>` +
      psBlock +
      `<h6 class="mt-3">Pricing</h6><table class="table table-sm"><tbody>` +
      `<tr><td>Panels</td><td class="text-right">${money(p.panels_msrp)}</td></tr>` +
      `<tr><td>Jumpers</td><td class="text-right">${money(p.jumpers_msrp)}</td></tr>` +
      `<tr><td>Leaders</td><td class="text-right">${money(p.leaders_msrp)}</td></tr>` +
      (includePs ? `<tr><td>Power supplies</td><td class="text-right">${money(p.power_supplies_msrp)}</td></tr>` : '') +
      `<tr class="font-weight-bold"><td>Total MSRP</td><td class="text-right">${money(p.total_msrp != null ? p.total_msrp : r.total_msrp)}</td></tr>` +
      `</tbody></table>`;
  }
  function call(method, args, cb) { frappe.call({ method, args, freeze: true, callback: (r) => cb(r.message || r) }); }
  function populateSelect(select, rows) { if (!select) return; rows = rows || []; select.innerHTML = '<option value="">Select...</option>'; rows.forEach(r => select.appendChild(option(r.value, r.label))); select.disabled = !rows.length; }
  function loadProjects() { call('illumenate_lighting.illumenate_lighting.api.portal.get_user_projects_for_configurator', {}, function (r) { populateSelect($id('projectSelect'), r.projects); }); }
  function loadSchedules(project) { populateSelect($id('scheduleSelect'), []); populateSelect($id('lineSelect'), [{ value: '__new__', label: '+ New Line' }]); if (!project) return; call('illumenate_lighting.illumenate_lighting.api.portal.get_schedules_for_project', { project_name: project }, function (r) { populateSelect($id('scheduleSelect'), r.schedules); }); }
  function loadLines(schedule) { populateSelect($id('lineSelect'), [{ value: '__new__', label: '+ New Line' }]); if (!schedule) return; call('illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator', { schedule_name: schedule }, function (r) { const lines = (r.lines || []).map(l => ({ value: l.idx, label: `${l.line_id || ('Line ' + (l.idx + 1))} — ${l.summary || ''}` })); populateSelect($id('lineSelect'), [{ value: '__new__', label: '+ New Line' }].concat(lines)); }); }
  document.addEventListener('DOMContentLoaded', function () {
    if (!$id('sheetTemplate')) return;
    fill($id('sheetTemplate'), templates.map(t => ({ name: t.name })), r => r.name); $id('sheetTemplate').addEventListener('change', renderTemplate);
    loadProjects(); if ($id('projectSelect')) $id('projectSelect').addEventListener('change', e => loadSchedules(e.target.value)); if ($id('scheduleSelect')) $id('scheduleSelect').addEventListener('change', e => loadLines(e.target.value));
    const existing = window.ILL_LED_SHEET_EXISTING || null;
    if (existing) {
      $id('sheetTemplate').value = existing.sheet_template || ''; renderTemplate();
      $id('sheetSpec').value = existing.sheet_spec || '';
      $id('sheetCct').value = existing.selected_cct || '';
      $id('sheetOutput').value = existing.selected_output_level || '';
      $id('sheetEnvironment').value = existing.selected_environment_rating || '';
      $id('sheetMounting').value = existing.selected_mounting || '';
      $id('sheetFinish').value = existing.selected_finish || '';
      $id('coverageWidthValue').value = existing.coverage_width_ft || ''; $id('coverageWidthUnit').value = 'ft';
      $id('coverageHeightValue').value = existing.coverage_height_ft || ''; $id('coverageHeightUnit').value = 'ft';
      $id('sheetIncludePowerSupply').checked = existing.include_power_supply == null ? true : !!existing.include_power_supply;
    }
    $id('calculateSheet').addEventListener('click', function () { call('illumenate_lighting.illumenate_lighting.api.led_sheet_configurator.validate_sheet_configuration', payload(), function (r) { lastResult = r; render(r); $id('saveSheet').disabled = !(r.success && ctx.can_save); }); });
    $id('saveSheet').addEventListener('click', function () { call('illumenate_lighting.illumenate_lighting.api.led_sheet_configurator.save_sheet_configuration', payload(), function () { const sched = currentSchedule(); window.location.href = sched ? `/portal/schedules/${sched}` : '/portal/projects'; }); });
  });
})();
