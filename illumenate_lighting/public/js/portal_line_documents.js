/* Documents belong to a stable line; file replacement is finalized only after upload succeeds. */
window.PortalLineDocuments = {
    async open(schedule, lineKey) {
        const api = 'illumenate_lighting.illumenate_lighting.portal.line_documents.';
        let modified, changed = false, busy = false;
        const dialog = await window.PortalDialog.create({title: __('Line specifications'), fields: [{fieldname: 'body', fieldtype: 'HTML'}]});
        const body = dialog.fields_dict.body.$wrapper;
        const list = $('<div aria-live="polite"></div>').appendTo(body);
        const input = $('<input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.heic,.heif" class="form-control-file mt-3">').attr('aria-label', __('Specification files')).appendTo(body);
        window.PortalUploader?.attach(input[0]);
        const label = $('<label class="mt-2 d-block"></label>').appendTo(body);
        const primary = $('<input type="checkbox" class="mr-2">').appendTo(label);
        label.append(document.createTextNode(__('Use the first selected file as the primary specification')));
        $('<p class="small text-muted"></p>').text(__('PDF, JPEG, PNG or HEIC. Up to 10 files per line, 20 MiB per file. Replacements keep earlier issued packets intact.')).appendTo(body);
        const gallery = window.PortalGallery;
        const annotate = !!gallery && gallery.enabled('upload_purpose');
        let purposes = [];
        const notes = $('<div class="form-row mt-2"></div>').toggle(annotate).appendTo(body);
        const purposeInput = $('<select class="form-control form-control-sm"></select>').attr('aria-label', __('Purpose of the selected files')).appendTo($('<div class="col-sm-5"></div>').appendTo(notes));
        const captionInput = $('<input type="text" maxlength="280" class="form-control form-control-sm">').attr({'aria-label': __('Caption for the selected files'), placeholder: __('Caption (optional)')}).appendTo($('<div class="col-sm-7"></div>').appendTo(notes));
        const feedback = $('<div role="status" aria-live="polite"></div>').appendTo(body);
        async function refresh() {
            const result = await PortalUploads.call(api + 'list_documents', {schedule_name: schedule, line_key: lineKey});
            modified = result.modified;
            label.toggle(result.manufacturer_type !== 'ILLUMENATE');
            if (result.manufacturer_type === 'ILLUMENATE') primary.prop('checked', false);
            purposes = result.purposes || [];
            if (annotate && purposeInput.children().length === 0) purposeInput.append(Array.from(gallery.purposeSelect(purposes, '').children));
            list.empty();
            if (!result.documents.length) list.text(__('No additional documents have been selected. Existing legacy primary specifications remain on the schedule.'));
            const groups = annotate ? gallery.groupByPurpose(result.documents, purposes) : [{label: '', rows: result.documents}];
            const images = result.documents.filter(row => row.thumbnail_url).map(row => {
                const url = '/api/method/' + api + 'download?name=' + encodeURIComponent(row.name);
                return {...row, title: row.file_name, image_url: url, download_url: url};
            });
            groups.forEach(group => {
            if (group.label && groups.length > 1) $('<h6 class="mt-2 mb-1"></h6>').text(group.label).appendTo(list);
            group.rows.forEach(row => {
                const item = $('<div class="d-flex align-items-center justify-content-between mb-2"></div>').appendTo(list);
                const name = $('<div class="d-flex align-items-center"></div>').appendTo(item);
                if (row.thumbnail_url && gallery) {
                    $('<button type="button" class="btn btn-link p-0 mr-2"></button>').attr('aria-label', __('View {0}', [row.caption || row.file_name]))
                        .append($('<img width="48" height="48" loading="lazy" style="object-fit:cover">').attr({src: row.thumbnail_url, alt: row.caption || row.file_name}))
                        .on('click', () => gallery.lightbox(images, images.findIndex(image => image.name === row.name))).appendTo(name);
                }
                const text = $('<div></div>').appendTo(name);
                $('<a target="_blank" rel="noopener"></a>').attr('href', '/api/method/' + api + 'download?name=' + encodeURIComponent(row.name)).text(row.file_name + (row.is_primary ? ' (' + __('Primary') + ')' : '')).appendTo(text);
                if (row.caption) $('<div class="small text-muted"></div>').text(row.caption).appendTo(text);
                $('<button type="button" class="btn btn-sm btn-outline-danger"></button>').text(__('Remove from line')).appendTo(item).on('click', async function () {
                    if (busy) return;
                    busy = true;
                    try { await PortalUploads.call(api + 'remove', {name: row.name, expected_modified: modified}); changed = true; await refresh(); }
                    catch (error) { feedback.text(error.message); }
                    finally { busy = false; }
                });
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
                    primary_file: primary.prop('checked') ? files[0] : null, expected_modified: modified,
                    ...(annotate ? {purpose: purposeInput.val() || '', caption: captionInput.val() || ''} : {})});
                changed = true; input.val(''); captionInput.val(''); window.PortalUploader?.reset(input[0]); feedback.text(__('Documents attached.'));
                await refresh();
            } catch (error) { feedback.text(error.message); }
            finally { busy = false; dialog.get_primary_btn().prop('disabled', false); }
        });
        dialog.onhide = function () { if (changed) window.location.reload(); };
        dialog.show();
        refresh().catch(error => { feedback.text(error.message); dialog.get_primary_btn().prop('disabled', true); });
    }
};
