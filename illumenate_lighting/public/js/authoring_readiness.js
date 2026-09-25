/* Draft authoring remains possible; preflight explains channel blockers. */
['ilL-Fixture-Template','ilL-Tape-Neon-Template','ilL-LED-Sheet-Template','ilL-Driver-Template','ilL-Controller-Template'].forEach(doctype => {
    frappe.ui.form.on(doctype, {refresh(frm) {
        if (frm.is_new() || !frappe.user_roles.some(role => ['System Manager','ilL Engineering','ilL Catalog Publisher','ilL Integration'].includes(role))) return;
        frm.add_custom_button(__('Engineering preflight'), async () => {
            if (frm.is_dirty()) { frappe.msgprint(__('Save this draft before checking its dependencies.')); return; }
            const response = await frappe.call({method:'illumenate_lighting.illumenate_lighting.api.product_readiness.authoring_preview', args:{doctype,name:frm.doc.name},freeze:true});
            const result=response.message, esc=frappe.utils.escape_html;
            const dialog=new frappe.ui.Dialog({title:__('Engineering preflight'),fields:[{fieldname:'results',fieldtype:'HTML'}]});
            const wrapper=dialog.fields_dict.results.$wrapper;
            wrapper.append(result.ready ? $('<p>').text(__('Saved master checks pass. Open the affected product to check its configure, PDF, portal and CMS channels.')) : $('<div>').html(result.issues.map(issue=>`<p>${esc(issue.record)} / ${esc(issue.field)}: ${esc(issue.message)}</p>`).join('')));
            function append(page) {
                (page.products || []).forEach(product => {
                    $('<p>').append($('<a>').attr('href','/app/ill-webflow-product/'+encodeURIComponent(product.product)).text(product.product)).appendTo(wrapper);
                });
                if (page.next_cursor) $('<button type="button" class="btn btn-default btn-sm">').text(__('Scan next product page')).appendTo(wrapper).on('click',async function () {
                    const button=$(this).prop('disabled',true);
                    try { const next=await frappe.call({method:'illumenate_lighting.illumenate_lighting.api.product_readiness.affected_products',args:{doctype,name:frm.doc.name,after:page.next_cursor}}); button.remove(); append(next.message); }
                    catch (_) { button.prop('disabled',false); }
                });
            }
            append(result.affected); dialog.show();
        },__('Actions'));
    }});
});
