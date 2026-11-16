/* Product media authoring (plan 5.2, owner decision D1).
   Template forms: a card for hero_image, the main product image dealers and Webflow show.
   Webflow Product: the inherited hero image (read only) and a gallery manager for gallery_images.
   Uploads go through frappe.ui.FileUploader, so File permissions stay native. Everything is
   built with DOM APIs; record values are only ever set as text, attributes or properties. */
(() => {
    const TEMPLATE_LINKS = {
        fixture_template: 'ilL-Fixture-Template',
        tape_neon_template: 'ilL-Tape-Neon-Template',
        led_sheet_template: 'ilL-LED-Sheet-Template',
        kit_template: 'ilL-Extrusion-Kit-Template',
        driver_template: 'ilL-Driver-Template',
        controller_template: 'ilL-Controller-Template',
    };
    const MIN_WIDTH = 1200;
    const NON_WEB = /\.(tiff?|bmp)$/i;

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function button(label, onClick, className = 'btn btn-xs btn-default') {
        const node = el('button', className, label);
        node.type = 'button';
        node.addEventListener('click', onClick);
        return node;
    }

    function canWrite(frm) {
        return !frm.is_new() && Boolean(frm.perm && frm.perm[0] && frm.perm[0].write);
    }

    function upload(frm, { files, multiple, fieldname, onFile }) {
        return new frappe.ui.FileUploader({
            frm,
            doctype: frm.doctype,
            docname: frm.doc.name,
            fieldname,
            files,
            allow_multiple: multiple,
            make_attachments_public: true,
            restrictions: { allowed_file_types: ['image/*'] },
            on_success: onFile,
        });
    }

    function dropZone(frm, label, options) {
        const zone = el('div', 'ill-media-drop', label);
        zone.tabIndex = 0;
        zone.setAttribute('role', 'button');
        zone.style.cssText = 'border:1px dashed var(--border-color);border-radius:6px;padding:10px;text-align:center;cursor:pointer;margin-top:8px';
        const open = files => upload(frm, { ...options, files });
        zone.addEventListener('click', () => open());
        zone.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
        });
        zone.addEventListener('dragover', event => { event.preventDefault(); zone.classList.add('ill-media-drop-active'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('ill-media-drop-active'));
        zone.addEventListener('drop', event => {
            event.preventDefault();
            zone.classList.remove('ill-media-drop-active');
            const files = Array.from((event.dataTransfer && event.dataTransfer.files) || []).filter(file => /^image\//.test(file.type || ''));
            if (files.length) open(options.multiple ? files : files.slice(0, 1));
        });
        return zone;
    }

    function sizeBadge(image, url) {
        const badge = el('span', 'indicator-pill gray', __('Checking size…'));
        if (NON_WEB.test(String(url).split('?')[0])) {
            badge.className = 'indicator-pill orange';
            badge.textContent = __('TIFF/BMP: use JPEG, PNG or WebP');
            return badge;
        }
        image.addEventListener('load', () => {
            const width = image.naturalWidth, height = image.naturalHeight;
            const narrow = width < MIN_WIDTH;
            badge.className = 'indicator-pill ' + (narrow ? 'orange' : 'green');
            badge.textContent = width + ' × ' + height + ' px' + (narrow ? ' · ' + __('under {0} px wide', [MIN_WIDTH]) : '');
        });
        image.addEventListener('error', () => {
            badge.className = 'indicator-pill red';
            badge.textContent = __('Image could not be loaded');
        });
        return badge;
    }

    function preview(url, alt) {
        const image = el('img');
        image.alt = alt || '';
        image.loading = 'lazy';
        image.style.cssText = 'max-width:100%;max-height:240px;object-fit:contain;display:block;margin:8px 0';
        image.src = url;
        return image;
    }

    function replaceCard(field, className) {
        const host = field && field.$wrapper && field.$wrapper.get(0);
        if (!host || !host.parentNode) return null;
        const old = host.parentNode.querySelector(':scope > .' + className);
        if (old) old.remove();
        const card = el('div', className + ' frappe-card');
        card.style.cssText = 'padding:12px;margin-bottom:12px';
        host.parentNode.insertBefore(card, host);
        return card;
    }

    function heroCard(frm) {
        const card = replaceCard(frm.fields_dict.hero_image, 'ill-hero-card');
        if (!card) return;
        card.appendChild(el('div', 'h6 text-uppercase text-muted', __('Main product image — shown to dealers and on Webflow')));
        const hero = frm.doc.hero_image;
        if (hero) {
            const image = preview(hero, frm.doc.hero_image_alt);
            card.appendChild(image);
            card.appendChild(sizeBadge(image, hero));
            if (!String(frm.doc.hero_image_alt || '').trim()) {
                card.appendChild(el('div', 'text-warning small', __('Add alt text for the main image in "Hero Image Alt Text".')));
            }
        } else {
            card.appendChild(el('div', 'text-warning', __('No main product image yet. Dealers and Webflow fall back to another picture until one is added.')));
        }
        if (canWrite(frm)) {
            card.appendChild(dropZone(frm, hero ? __('Drop an image here or click to replace the main image') : __('Drop an image here or click to add the main image'), {
                multiple: false,
                fieldname: 'hero_image',
                onFile: file => frm.set_value('hero_image', file.file_url),
            }));
        } else if (frm.is_new()) {
            card.appendChild(el('div', 'text-muted small', __('Save the template to add its main image.')));
        }
    }

    function linkedTemplate(doc) {
        const field = Object.keys(TEMPLATE_LINKS).find(name => doc[name]);
        return field ? { doctype: TEMPLATE_LINKS[field], name: doc[field] } : null;
    }

    function orderedRows(frm) {
        return (frm.doc.gallery_images || []).slice().sort((a, b) =>
            (Number(a.display_order) || 0) - (Number(b.display_order) || 0) || (a.idx || 0) - (b.idx || 0));
    }

    function saveOrder(frm, rows) {
        rows.forEach((row, index) => { row.idx = index + 1; row.display_order = index + 1; });
        frm.doc.gallery_images = rows;
        frm.refresh_field('gallery_images');
        frm.dirty();
        galleryManager(frm);
    }

    function move(frm, row, offset) {
        const rows = orderedRows(frm), from = rows.indexOf(row), to = from + offset;
        if (from < 0 || to < 0 || to >= rows.length) return;
        rows.splice(to, 0, rows.splice(from, 1)[0]);
        saveOrder(frm, rows);
    }

    function galleryTile(frm, row, editable, position, total) {
        const tile = el('div', 'ill-gallery-tile');
        tile.dataset.row = row.name;
        tile.style.cssText = 'width:180px;border:1px solid var(--border-color);border-radius:6px;padding:6px';
        if (row.image) {
            const image = preview(row.image, row.alt_text);
            image.style.maxHeight = '110px';
            tile.appendChild(image);
        }
        const alt = el('input', 'form-control input-xs');
        alt.type = 'text';
        alt.placeholder = __('Alt text');
        alt.setAttribute('aria-label', __('Alt text'));
        alt.value = row.alt_text || '';
        alt.disabled = !editable;
        alt.addEventListener('change', () => frappe.model.set_value(row.doctype, row.name, 'alt_text', alt.value));
        tile.appendChild(alt);
        if (!String(row.alt_text || '').trim()) tile.appendChild(el('div', 'text-warning small', __('Alt text missing')));
        if (!editable) return tile;
        const actions = el('div', 'btn-group');
        actions.style.marginTop = '4px';
        const earlier = button('←', () => move(frm, row, -1));
        earlier.title = __('Move earlier');
        earlier.disabled = position === 0;
        const later = button('→', () => move(frm, row, 1));
        later.title = __('Move later');
        later.disabled = position === total - 1;
        actions.append(earlier, later, button(__('Remove'), () => frappe.confirm(__('Remove this image from the gallery?'), () =>
            saveOrder(frm, orderedRows(frm).filter(other => other !== row)))));
        tile.appendChild(actions);
        tile.draggable = true;
        tile.addEventListener('dragstart', event => { event.dataTransfer.setData('text/plain', row.name); });
        tile.addEventListener('dragover', event => event.preventDefault());
        tile.addEventListener('drop', event => {
            const source = event.dataTransfer.getData('text/plain');
            if (!source || source === row.name) return;
            event.preventDefault();
            event.stopPropagation();
            const rows = orderedRows(frm), from = rows.findIndex(other => other.name === source);
            if (from < 0) return;
            const moved = rows.splice(from, 1)[0];
            rows.splice(rows.indexOf(row), 0, moved);
            saveOrder(frm, rows);
        });
        return tile;
    }

    function galleryManager(frm) {
        const card = replaceCard(frm.fields_dict.gallery_images, 'ill-gallery-manager');
        if (!card) return;
        const template = linkedTemplate(frm.doc);
        card.appendChild(el('div', 'h6 text-uppercase text-muted', __('Main product image (from the template)')));
        if (frm.doc.hero_image) card.appendChild(preview(frm.doc.hero_image, ''));
        else card.appendChild(el('div', 'text-warning', __('The linked template has no main image yet.')));
        if (template) {
            const link = el('a', '', __('Edit on template'));
            link.href = '/app/' + frappe.router.slug(template.doctype) + '/' + encodeURIComponent(template.name);
            card.appendChild(link);
        }
        card.appendChild(el('div', 'h6 text-uppercase text-muted mt-3', __('Gallery — additional images, in display order')));
        const editable = canWrite(frm);
        const rows = orderedRows(frm);
        const grid = el('div', 'ill-gallery-grid');
        grid.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px';
        rows.forEach((row, index) => grid.appendChild(galleryTile(frm, row, editable, index, rows.length)));
        if (!rows.length) grid.appendChild(el('div', 'text-muted', __('No gallery images yet.')));
        card.appendChild(grid);
        if (editable) {
            card.appendChild(dropZone(frm, __('Drop images here or click to add them to the gallery'), {
                multiple: true,
                onFile: file => {
                    const last = orderedRows(frm).reduce((max, row) => Math.max(max, Number(row.display_order) || 0), 0);
                    frm.add_child('gallery_images', { image: file.file_url, display_order: last + 1 });
                    frm.refresh_field('gallery_images');
                    galleryManager(frm);
                },
            }));
        }
    }

    Object.values(TEMPLATE_LINKS).forEach(doctype => {
        frappe.ui.form.on(doctype, { refresh: heroCard, hero_image: heroCard, hero_image_alt: heroCard });
    });
    frappe.ui.form.on('ilL-Webflow-Product', { refresh: galleryManager, gallery_images_remove: galleryManager });
    frappe.ui.form.on('ilL-Child-Webflow-Gallery-Image', { image: galleryManager, alt_text: galleryManager, display_order: galleryManager });
})();
