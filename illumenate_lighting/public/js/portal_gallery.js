/* Project and line photo gallery (hardening plan 4.3–4.5). DOM is built with text nodes only. */
(function () {
	const API = 'illumenate_lighting.illumenate_lighting.portal.';
	const t = (text, args) => (typeof __ === 'function' ? __(text, args) : String(text));

	function flags() {
		const node = typeof document !== 'undefined' && document.getElementById('ill-portal-flags');
		if (!node) return {};
		try { return JSON.parse(node.textContent || '{}') || {}; } catch (error) { return {}; }
	}

	function enabled(flag) { return flags()[flag] !== false; }

	function el(tag, attrs, children) {
		const node = document.createElement(tag);
		Object.entries(attrs || {}).forEach(([key, value]) => {
			if (value === undefined || value === null || value === false) return;
			if (key === 'text') node.textContent = String(value);
			else if (key === 'className') node.className = value;
			else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
			else node.setAttribute(key, value === true ? '' : String(value));
		});
		[].concat(children || []).forEach(child => child != null && node.append(child));
		return node;
	}

	/* Rows grouped by purpose in the listed order; rows without one come last. */
	function groupByPurpose(rows, purposes) {
		const order = [...(purposes || []), ''];
		const groups = new Map(order.map(purpose => [purpose, []]));
		(rows || []).forEach(row => {
			const key = order.includes(row.purpose || '') ? (row.purpose || '') : '';
			groups.get(key).push(row);
		});
		return order.filter(purpose => groups.get(purpose).length).map(purpose => ({purpose, label: purpose ? t(purpose) : t('Other files'), rows: groups.get(purpose)}));
	}

	function purposeSelect(purposes, value, label) {
		const select = el('select', {className: 'form-control form-control-sm', 'aria-label': label || t('Purpose')});
		select.append(el('option', {value: '', text: t('No purpose')}));
		(purposes || []).forEach(purpose => select.append(el('option', {value: purpose, text: t(purpose)})));
		select.value = value || '';
		return select;
	}

	function lightbox(items, start) {
		let index = start;
		const previous = document.activeElement;
		const image = el('img', {className: 'ill-lightbox__image'});
		const caption = el('p', {className: 'ill-lightbox__caption'});
		const download = el('a', {className: 'btn btn-sm btn-light', text: t('Download original'), rel: 'noopener'});
		const close = el('button', {type: 'button', className: 'btn btn-sm btn-light', text: t('Close')});
		const prev = el('button', {type: 'button', className: 'btn btn-sm btn-light', text: t('Previous'), 'aria-label': t('Previous photo')});
		const next = el('button', {type: 'button', className: 'btn btn-sm btn-light', text: t('Next'), 'aria-label': t('Next photo')});
		const overlay = el('div', {className: 'ill-lightbox', role: 'dialog', 'aria-modal': 'true', 'aria-label': t('Photo viewer'), tabindex: '-1'}, [
			el('figure', {className: 'ill-lightbox__figure'}, [image, el('figcaption', {}, caption)]),
			el('div', {className: 'ill-lightbox__actions'}, [prev, next, download, close]),
		]);
		function show() {
			const item = items[index];
			image.src = item.image_url || item.thumbnail_url;
			image.alt = item.caption || item.title || item.file_name || '';
			caption.textContent = [item.line_id ? t('Line {0}', [item.line_id]) : '', item.purpose ? t(item.purpose) : '', item.caption].filter(Boolean).join(' · ');
			download.href = item.download_url;
			prev.disabled = index === 0;
			next.disabled = index === items.length - 1;
		}
		function hide() {
			overlay.remove();
			document.removeEventListener('keydown', onKey, true);
			previous?.focus?.();
		}
		function move(step) { index = Math.min(items.length - 1, Math.max(0, index + step)); show(); }
		function onKey(event) {
			if (event.key === 'Escape') { event.stopPropagation(); hide(); }
			else if (event.key === 'ArrowLeft') move(-1);
			else if (event.key === 'ArrowRight') move(1);
		}
		prev.addEventListener('click', () => move(-1));
		next.addEventListener('click', () => move(1));
		close.addEventListener('click', hide);
		overlay.addEventListener('click', event => { if (event.target === overlay) hide(); });
		document.addEventListener('keydown', onKey, true);
		document.body.append(overlay);
		show();
		overlay.focus();
		return {overlay, hide};
	}

	function editor(item, purposes, onSaved, feedback) {
		const select = purposeSelect(purposes, item.purpose, t('Purpose for {0}', [item.title]));
		const input = el('input', {type: 'text', className: 'form-control form-control-sm mt-1', maxlength: '280', 'aria-label': t('Caption for {0}', [item.title])});
		input.value = item.caption || '';
		const save = el('button', {type: 'button', className: 'btn btn-sm btn-primary mt-1', text: t('Save')});
		save.addEventListener('click', async () => {
			save.disabled = true;
			try {
				await window.PortalUploads.call(API + 'line_documents.annotate', {name: item.name, expected_modified: item.schedule_modified, purpose: select.value, caption: input.value});
				feedback.textContent = t('Saved.');
				await onSaved();
			} catch (error) { feedback.textContent = error.message; }
			finally { save.disabled = false; }
		});
		return el('div', {className: 'ill-gallery__edit'}, [select, input, save]);
	}

	function requestPicker(item, requests, feedback) {
		const select = el('select', {className: 'form-control form-control-sm', 'aria-label': t('Drawing request for {0}', [item.title])});
		requests.forEach(request => select.append(el('option', {value: request.name, text: [request.name, request.request_type, t(request.status)].filter(Boolean).join(' · ')})));
		const send = el('button', {type: 'button', className: 'btn btn-sm btn-outline-primary mt-1', text: t('Attach to drawing request')});
		send.addEventListener('click', async () => {
			send.disabled = true;
			try {
				const result = await window.PortalUploads.call(API + 'media.attach_to_request', {document: item.name, request_name: select.value});
				feedback.textContent = result.already_attached ? t('That request already has this photo.') : t('Photo attached to {0}.', [select.value]);
			} catch (error) { feedback.textContent = error.message; }
			finally { send.disabled = false; }
		});
		return el('div', {className: 'ill-gallery__request'}, [select, send]);
	}

	function render(container, data, reload) {
		container.replaceChildren();
		const feedback = el('div', {role: 'status', 'aria-live': 'polite', className: 'small text-muted mb-2'});
		container.append(feedback);
		if (!data.items.length) {
			container.append(el('p', {className: 'text-muted', text: t('No photos yet. Attach site photos to a fixture line from its documents.')}));
			return;
		}
		const all = [];
		groupByPurpose(data.items, data.purposes).forEach(group => {
			container.append(el('h5', {className: 'ill-gallery__group mt-3', text: group.label}));
			const grid = el('div', {className: 'ill-gallery__grid', role: 'list'});
			group.rows.forEach(item => {
				const index = all.push(item) - 1;
				const thumb = el('button', {type: 'button', className: 'ill-gallery__thumb', 'aria-label': t('View {0}', [item.caption || item.title])},
					el('img', {src: item.thumbnail_url, alt: item.caption || item.title, loading: 'lazy'}));
				thumb.addEventListener('click', () => lightbox(all, index));
				const meta = el('figcaption', {className: 'small'}, [
					el('div', {className: 'text-truncate', text: item.caption || item.title}),
					el('div', {className: 'text-muted', text: [item.line_id ? t('Line {0}', [item.line_id]) : '', item.schedule_name].filter(Boolean).join(' · ')}),
					el('a', {href: item.download_url, rel: 'noopener', text: t('Download original')}),
				]);
				const card = el('figure', {className: 'ill-gallery__item', role: 'listitem'}, [thumb, meta]);
				if (item.can_edit) {
					card.append(editor(item, data.purposes, reload, feedback));
					if (data.requests.length) card.append(requestPicker(item, data.requests, feedback));
				}
				grid.append(card);
			});
			container.append(grid);
		});
	}

	async function mount(container, scope) {
		if (!container) return null;
		if (!enabled('gallery')) { container.hidden = true; return null; }
		const args = scope.schedule ? {schedule_name: scope.schedule, line_key: scope.lineKey || null} : {project: scope.project};
		const reload = async () => {
			const data = await window.PortalUploads.call(API + 'media.gallery', args);
			if (!data.enabled) { container.hidden = true; return data; }
			render(container, data, reload);
			return data;
		};
		try { return await reload(); }
		catch (error) {
			container.replaceChildren(el('p', {className: 'text-danger', role: 'alert', text: error.message}));
			return null;
		}
	}

	window.PortalGallery = {mount, render, lightbox, groupByPurpose, purposeSelect, enabled, el};
})();
