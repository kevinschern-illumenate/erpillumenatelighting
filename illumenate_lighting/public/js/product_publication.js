/* Staff publication actions always inspect the saved, current revision. */
frappe.ui.form.on("ilL-Webflow-Product", {
    refresh(frm) {
        if (frm.is_new() || !frappe.user_roles.some(role =>
            ["System Manager", "ilL Catalog Publisher", "ilL Integration", "ilL Engineering"].includes(role))) return;
        frm.add_custom_button(__('Channel preflight'), () => {
            frappe.prompt({fieldname:'channel', fieldtype:'Select', label:__('Channel'), options:'portal\nconfigure\npdf\ncms', reqd:1}, async values => {
                if (frm.is_dirty()) { frappe.msgprint(__('Save the product before inspecting it.')); return; }
                const response = await frappe.call({method:'illumenate_lighting.illumenate_lighting.api.product_readiness.preview', args:{product:frm.doc.name, channel:values.channel}, freeze:true});
                const result=response.message, esc=frappe.utils.escape_html;
                frappe.msgprint({title: result.ready ? __('Channel ready') : __('Setup corrections required'),
                    message: result.ready ? __('The current saved dependencies pass this channel preflight.') : (result.issues || []).map(row=>`<p>${esc(row.record)} / ${esc(row.field)}: ${esc(row.message)}</p>`).join(''), wide:true});
            }, __('Product channel readiness'));
        }, __('Actions'));
        frm.add_custom_button(__('Portal product preview'), () => window.open('/portal/products/' + encodeURIComponent(frm.doc.product_slug), '_blank', 'noopener'), __('Actions'));
        if (!frappe.user_roles.some(role => ["System Manager", "ilL Catalog Publisher", "ilL Integration"].includes(role))) return;
        frm.add_custom_button(__("Readiness and Publication"), () => {
            const dialog = new frappe.ui.Dialog({
                title: __("Product Publication"),
                fields: [
                    {fieldname: "brand", fieldtype: "Link", options: "ilL-Webflow-Brand", label: __("Brand"), reqd: 1},
                    {fieldname: "result", fieldtype: "HTML"}
                ],
                primary_action_label: __("Inspect Saved Revision"),
                async primary_action(values) {
                    if (frm.is_dirty()) { frappe.msgprint(__("Save the product before inspecting it.")); return; }
                    dialog.disable_primary_action();
                    const wrapper = dialog.fields_dict.result.$wrapper.empty();
                    try {
                        const response = await frappe.call({
                            method: "illumenate_lighting.illumenate_lighting.api.publication.inspect",
                            type: "POST", args: {product: frm.doc.name, brand: values.brand}
                        });
                        const result = response.message, esc = frappe.utils.escape_html;
                        wrapper.append(`<p>${esc(result.state)} &middot; ${esc(result.current_hash.slice(0, 12))}</p>`);
                        (result.readiness.issues || []).forEach(issue => {
                            wrapper.append(`<p>${esc(issue.record)} / ${esc(issue.field)}: ${esc(issue.message)}</p>`);
                        });
                        wrapper.append(`<p>${__("Staged revision")}: ${esc((result.staged_hash || "").slice(0, 12)) || "—"}<br>${__("Live revision")}: ${esc((result.live_hash || "").slice(0, 12)) || "—"}</p>`);
                        const link = document.createElement("a");
                        link.textContent = __("Open publication jobs");
                        link.href = `/app/ill-publish-job?product=${encodeURIComponent(frm.doc.name)}&brand=${encodeURIComponent(values.brand)}`;
                        wrapper.append(link);
                        if (!frappe.user_roles.some(role => ["System Manager", "ilL Catalog Publisher"].includes(role))) return;
                        const actions = frm.doc.is_active ? ["STAGE", "PUBLISH"] : ["RETIRE"];
                        actions.forEach(operation => {
                            const button = document.createElement("button");
                            button.type = "button"; button.className = "btn btn-default btn-sm ml-2";
                            button.textContent = {STAGE: __("Approve and Stage"), PUBLISH: __("Publish Live"), RETIRE: __("Retire from Webflow")}[operation];
                            button.disabled = operation !== "RETIRE" && (!result.readiness.ready || (operation === "PUBLISH" && result.staged_hash !== result.current_hash));
                            button.addEventListener("click", async () => {
                                button.disabled = true;
                                try {
                                    const receipt = await frappe.call({method: "illumenate_lighting.illumenate_lighting.api.publication.request",
                                        type: "POST", args: {product: frm.doc.name, brand: values.brand, operation, expected_hash: result.current_hash}});
                                    frappe.show_alert({message: __("Publication job: {0}", [receipt.message.job]), indicator: "green"});
                                    dialog.hide();
                                } catch (error) { button.disabled = false; }
                            });
                            wrapper.append(button);
                        });
                    } catch (error) {
                        wrapper.text(__("Inspection failed. Correct the reported error and retry."));
                    } finally { dialog.enable_primary_action(); }
                }
            });
            dialog.show();
        }, __("Actions"));
    }
});

frappe.ui.form.on("ilL-Publish-Job", {
    refresh(frm) {
        if (frm.doc.state !== "FAILED") return;
        frm.add_custom_button(__("Retry Current Revision"), async () => {
            await frappe.call({method: "illumenate_lighting.illumenate_lighting.api.publication.retry",
                type: "POST", args: {job: frm.doc.name}, freeze: true});
            await frm.reload_doc();
        });
    }
});
