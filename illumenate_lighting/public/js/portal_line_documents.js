/* Documents belong to a stable line; file replacement is finalized only after upload succeeds. */
window.PortalLineDocuments = {
    open(schedule, lineKey) {
        const api = 'illumenate_lighting.illumenate_lighting.portal.line_documents.';
        let modified, changed = false, busy = false;
        const dialog = new frappe.ui.Dialog({title: __('Line specifications'), fields: [{fieldname: 'body', fieldtype: 'HTML'}]});
        const body = dialog.fields_dict.body.$wrapper;
        const list = $('<div aria-live="polite"></div>').appendTo(body);
        const input = $('<input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" class="form-control-file mt-3">').attr('aria-label', __('Specification files')).appendTo(body);
        const label = $('<label class="mt-2 d-block"></label>').appendTo(body);
        const primary = $('<input type="checkbox" class="mr-2">').appendTo(label);
        label.append(document.createTextNode(__('Use the first selected file as the primary specification')));
        $('<p class="small text-muted"></p>').text(__('PDF, JPEG or PNG. Up to 10 files per line, 20 MiB per file. Replacements keep earlier issued packets intact.')).appendTo(body);
        const feedback = $('<div role="status" aria-live="polite"></div>').appendTo(body);
        async function refresh() {
            const result = await PortalUploads.call(api + 'list_documents', {schedule_name: schedule, line_key: lineKey});
            modified = result.modified;
            label.toggle(result.manufacturer_type !== 'ILLUMENATE');
            if (result.manufacturer_type === 'ILLUMENATE') primary.prop('checked', false);
            list.empty();
            if (!result.documents.length) list.text(__('No additional documents have been selected. Existing legacy primary specifications remain on the schedule.'));
            result.documents.forEach(row => {
                const item = $('<div class="d-flex align-items-center justify-content-between mb-2"></div>').appendTo(list);
                $('<a target="_blank" rel="noopener"></a>').attr('href', '/api/method/' + api + 'download?name=' + encodeURIComponent(row.name)).text(row.file_name + (row.is_primary ? ' (' + __('Primary') + ')' : '')).appendTo(item);
                $('<button type="button" class="btn btn-sm btn-outline-danger"></button>').text(__('Remove from line')).appendTo(item).on('click', async function () {
                    if (busy) return;
                    busy = true;
                    try { await PortalUploads.call(api + 'remove', {name: row.name, expected_modified: modified}); changed = true; await refresh(); }
                    catch (error) { feedback.text(error.message); }
                    finally { busy = false; }
                });
            });
        }
        dialog.set_primary_action(__('Upload and attach'), async function () {
            if (busy || !input[0].files.length) return;
            busy = true;
            dialog.get_primary_btn().prop('disabled', true);
            feedback.text(__('Uploading files. The current specifications remain selected until every upload succeeds.'));
            try {
                const files = await PortalUploads.uploadAll(input[0], 'ilL-Project-Fixture-Schedule', schedule);
                await PortalUploads.call(api + 'attach', {schedule_name: schedule, line_key: lineKey, file_ids: JSON.stringify(files),
                    primary_file: primary.prop('checked') ? files[0] : null, expected_modified: modified});
                changed = true; input.val(''); feedback.text(__('Documents attached.'));
                await refresh();
            } catch (error) { feedback.text(error.message); }
            finally { busy = false; dialog.get_primary_btn().prop('disabled', false); }
        });
        dialog.onhide = function () { if (changed) window.location.reload(); };
        dialog.show();
        refresh().catch(error => { feedback.text(error.message); dialog.get_primary_btn().prop('disabled', true); });
    }
};
