/* Publication History (plan 4.14, D12, Phase 6): a read-only section at the bottom of the
   Webflow Product and the templates. One line per brand (on Webflow since, last sync) and one
   timeline (owner, 2026-11-08): the latest pushes with the statuses at the time, and the
   status changes (template Product Status, product Webflow Status). */
(function () {
    const API = 'illumenate_lighting.illumenate_lighting.publication_history.get_history';
    const TEMPLATES = ['ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-Controller-Template',
        'ilL-Driver-Template', 'ilL-Extrusion-Kit-Template', 'ilL-LED-Sheet-Template'];
    const esc = value => frappe.utils.escape_html(value == null ? '' : String(value));
    const when = value => (value ? esc(String(value).slice(0, 16)) : '—');

    function html(history) {
        if (!history || !history.product) return '';
        const brands = (history.brands || []).map(row => `<div>${esc(row.brand)}: `
            + (row.published_on ? __('published since {0}', [when(row.published_on)]) : row.on_webflow ? __('on Webflow, never published') : __('not on Webflow'))
            + (row.staged_on ? ` &middot; ${__('last sync {0}', [when(row.staged_on)])}` : '')
            + (row.review_reason ? ` &middot; ${esc(row.review_reason)}` : '') + '</div>').join('');
        const rows = (history.rows || []).map(row => {
            const change = row.kind === 'status';
            const resultClass = change ? 'text-muted' : row.ok ? 'text-success' : row.error ? 'text-danger' : '';
            return `<tr${change ? ' class="ill-status-change" style="background: var(--subtle-fg, #f8f8f8);"' : ''}>
            <td>${when(row.when)}</td><td>${esc(row.status) || '—'}</td>
            <td class="${resultClass}">${esc(row.result)}</td>
            <td>${esc(row.by)}</td><td>${change ? '' : when(row.completed_on)}</td>
            <td class="text-muted">${esc(row.error || '')}</td></tr>`;
        }).join('');
        // Frappe's own section markup, so the section lines up with the others.
        return `<div class="row form-section card-section visible-section ill-publication-history">
            <div class="section-head">${__('Publication History')}
              <span class="text-muted small" style="font-weight: normal;">(${esc(history.product)})</span></div>
            <div class="section-body"><div class="form-column col-sm-12">
            ${brands || `<div class="text-muted">${__('Never synced to Webflow.')}</div>`}
            ${rows ? `<div style="overflow-x: auto; margin-top: 8px;"><table class="table table-sm small" style="margin: 0;">
              <thead><tr><th>${__('When')}</th><th>${__('Status')}</th><th>${__('Result')}</th>
              <th>${__('By')}</th><th>${__('Finished')}</th><th>${__('Error')}</th></tr></thead>
              <tbody>${rows}</tbody></table></div>
              <div class="text-muted small">${__('Latest {0} pushes and status changes. Statuses on pushes are recorded from 2026-11-08.', [history.limit])}
              <a href="/app/ill-publish-job?product=${encodeURIComponent(history.product)}">${__('All publication jobs')}</a></div>` : ''}
            </div></div>
          </div>`;
    }

    function render(frm, history) {
        if (frm.__ill_history_el) { frm.__ill_history_el.remove(); frm.__ill_history_el = null; }
        const content = html(history);
        if (!content || !frm.layout || !frm.layout.wrapper) return;
        frm.__ill_history_el = $(content);
        $(frm.layout.wrapper).append(frm.__ill_history_el);
    }

    function show(frm, args) {
        if (frm.is_new()) return render(frm, null);
        const name = frm.doc.name;
        frappe.xcall(API, args).then(history => {
            if (frm.doc.name === name) render(frm, history);
        }).catch(() => render(frm, null));
    }

    window.illPublicationHistory = {html, show};
    frappe.ui.form.on('ilL-Webflow-Product', {refresh(frm) { show(frm, {product: frm.doc.name}); }});
    TEMPLATES.forEach(doctype => frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (!frm.doc.webflow_product) return render(frm, null);
            show(frm, {template_doctype: frm.doctype, template_name: frm.doc.name});
        },
    }));
})();
