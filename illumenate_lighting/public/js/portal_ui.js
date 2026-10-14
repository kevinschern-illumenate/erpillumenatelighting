/* One interaction kit for portal pages (UI-3): calls that fail one way, toasts, a focus-managed
 * confirm, one escape helper and inline field errors. Pages update the DOM in place after a
 * success instead of showing a dialog and reloading. */
(function () {
	'use strict';
	const t = (text, args) => (typeof __ === 'function' ? __(text, args) : String(text).replace(/\{(\d)\}/g, (_, i) => args[i]));
	const GENERIC = 'The request could not be completed. Retry, or reload the page if it keeps failing.';
	const NETWORK = 'You appear to be offline. Check your connection and retry.';

	function escape(value) {
		return String(value === undefined || value === null ? '' : value)
			.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
	}

	function plain(html) {
		const box = document.createElement('div');
		box.innerHTML = String(html || '');
		return box.textContent.trim();
	}

	// Frappe sends frappe.throw text as a JSON list of JSON-encoded {message} objects.
	function serverMessage(payload) {
		if (!payload) return '';
		if (typeof payload === 'string') return plain(payload);
		if (payload._server_messages) {
			try {
				const messages = JSON.parse(payload._server_messages).map(item => {
					try { const parsed = JSON.parse(item); return parsed.message || parsed; } catch (e) { return item; }
				});
				const text = messages.map(plain).filter(Boolean).join(' ');
				if (text) return text;
			} catch (e) { /* fall through */ }
		}
		if (payload.message && typeof payload.message === 'object' && payload.message.error) return plain(payload.message.error);
		if (payload.responseJSON) return serverMessage(payload.responseJSON);
		if (payload.status === 0) return t(NETWORK);
		return '';
	}

	function setBusy(button, busy) {
		if (!button) return;
		if (busy) {
			button.dataset.portalBusy = '1';
			button.disabled = true;
			button.setAttribute('aria-busy', 'true');
		} else if (button.dataset.portalBusy) {
			delete button.dataset.portalBusy;
			button.disabled = false;
			button.removeAttribute('aria-busy');
		}
	}

	function call(method, args, options) {
		options = options || {};
		setBusy(options.busy, true);
		return new Promise((resolve, reject) => {
			const fail = message => {
				const error = new Error(message || t(GENERIC));
				error.portal = true;
				reject(error);
			};
			try {
				frappe.call({
					method,
					args: args || {},
					type: options.type || 'POST',
					callback(r) {
						const message = r ? r.message : undefined;
						if (message && typeof message === 'object' && message.success === false) {
							fail(plain(message.error));
							return;
						}
						if (options.successToast) toast(options.successToast, 'green');
						resolve(message);
					},
					error(payload) { fail(serverMessage(payload)); },
				});
			} catch (error) {
				fail(error && error.message);
			}
		}).finally(() => setBusy(options.busy, false));
	}

	let toastRegion;
	let announcer;
	// Frappe's alert container is not a live region, so screen readers hear the same text from a
	// visually hidden status region (UI-7). The region exists before its text changes so it is announced.
	function announce(message) {
		if (!announcer || !announcer.isConnected) {
			announcer = document.createElement('div');
			announcer.className = 'sr-only ill-announcer';
			announcer.setAttribute('role', 'status');
			announcer.setAttribute('aria-live', 'polite');
			document.body.append(announcer);
		}
		announcer.textContent = '';
		setTimeout(() => { announcer.textContent = String(message); }, 50);
	}

	function toast(message, tone) {
		if (frappe.show_alert) {
			frappe.show_alert({message: escape(message), indicator: tone || 'green'});
			announce(message);
			return;
		}
		if (!toastRegion || !toastRegion.isConnected) {
			toastRegion = document.createElement('div');
			toastRegion.className = 'ill-toasts';
			toastRegion.setAttribute('role', 'status');
			toastRegion.setAttribute('aria-live', 'polite');
			toastRegion.style.cssText = 'position:fixed;right:1rem;bottom:1rem;z-index:1080;display:flex;flex-direction:column;gap:.5rem';
			document.body.append(toastRegion);
		}
		const item = document.createElement('div');
		item.className = 'ill-toast ill-toast--' + (tone || 'green');
		item.style.cssText = 'background:#fff;border-left:4px solid ' + ({red: '#C0392B', orange: '#B7791F', blue: '#00588C'}[tone] || '#2F855A') + ';box-shadow:0 4px 16px rgba(0,0,0,.12);border-radius:8px;padding:.75rem 1rem;max-width:22rem';
		item.textContent = message;
		toastRegion.append(item);
		setTimeout(() => item.remove(), 5000);
	}

	function confirm(options) {
		options = options || {};
		return new Promise(resolve => {
			const previous = document.activeElement;
			const backdrop = document.createElement('div');
			backdrop.className = 'ill-confirm';
			backdrop.style.cssText = 'position:fixed;inset:0;z-index:1070;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;padding:1rem';
			const dialog = document.createElement('div');
			dialog.setAttribute('role', 'dialog');
			dialog.setAttribute('aria-modal', 'true');
			dialog.className = 'ill-confirm__dialog';
			dialog.style.cssText = 'background:#fff;border-radius:12px;max-width:28rem;width:100%;padding:1.5rem;box-shadow:0 12px 40px rgba(0,0,0,.2)';
			const title = document.createElement('h2');
			title.className = 'h5 mb-2';
			title.id = 'ill-confirm-' + Math.random().toString(36).slice(2);
			title.textContent = options.title || t('Are you sure?');
			dialog.setAttribute('aria-labelledby', title.id);
			const body = document.createElement('p');
			body.className = 'mb-4';
			body.textContent = options.body || '';
			const actions = document.createElement('div');
			actions.className = 'd-flex justify-content-end';
			const cancel = document.createElement('button');
			cancel.type = 'button'; cancel.className = 'btn btn-secondary mr-2'; cancel.textContent = options.cancelLabel || t('Cancel');
			const ok = document.createElement('button');
			ok.type = 'button'; ok.className = 'btn ' + (options.tone === 'danger' ? 'btn-danger' : 'btn-primary');
			ok.textContent = options.confirmLabel || t('Continue');
			actions.append(cancel, ok);
			dialog.append(title, body, actions);
			backdrop.append(dialog);
			const close = answer => {
				document.removeEventListener('keydown', onKey, true);
				backdrop.remove();
				if (previous && previous.focus) previous.focus();
				resolve(answer);
			};
			const onKey = event => {
				if (event.key === 'Escape') { event.preventDefault(); close(false); }
				if (event.key === 'Tab') {
					// Keep focus inside the dialog.
					const items = [cancel, ok];
					const index = items.indexOf(document.activeElement);
					event.preventDefault();
					items[(index + (event.shiftKey ? -1 : 1) + items.length) % items.length].focus();
				}
			};
			cancel.addEventListener('click', () => close(false));
			ok.addEventListener('click', () => close(true));
			backdrop.addEventListener('click', event => { if (event.target === backdrop) close(false); });
			document.addEventListener('keydown', onKey, true);
			document.body.append(backdrop);
			ok.focus();
		});
	}

	function fieldErrors(form, errors) {
		form.querySelectorAll('.ill-field-error').forEach(node => node.remove());
		form.querySelectorAll('.is-invalid').forEach(node => { node.classList.remove('is-invalid'); node.removeAttribute('aria-invalid'); });
		let first = null;
		Object.entries(errors || {}).forEach(([name, message]) => {
			const input = form.querySelector('[name="' + name + '"]');
			if (!input) return;
			input.classList.add('is-invalid');
			input.setAttribute('aria-invalid', 'true');
			const note = document.createElement('div');
			note.className = 'invalid-feedback ill-field-error';
			note.id = (input.id || name) + '-error';
			note.textContent = message;
			input.setAttribute('aria-describedby', note.id);
			input.insertAdjacentElement('afterend', note);
			first = first || input;
		});
		if (first) first.focus();
		return !!first;
	}

	// UI-5: async sections share one loading skeleton, one empty state and one error state with Retry.
	function skeleton(container, label, rows) {
		const note = document.createElement('span');
		note.className = 'sr-only';
		note.textContent = label || t('Loading…');
		const box = document.createElement('div');
		box.className = 'ill-skeleton';
		box.setAttribute('aria-hidden', 'true');
		for (let index = 0; index < (rows || 3); index += 1) {
			const line = document.createElement('div');
			line.className = 'ill-skeleton__line';
			box.append(line);
		}
		container.setAttribute('aria-busy', 'true');
		container.replaceChildren(note, box);
	}

	function state(container, className, options) {
		const box = document.createElement('div');
		box.className = 'ill-empty ill-empty--quiet ' + className;
		if (options.icon) {
			const icon = document.createElement('i');
			icon.className = 'fa fa-' + options.icon;
			icon.setAttribute('aria-hidden', 'true');
			box.append(icon);
		}
		if (options.title) {
			const title = document.createElement('h3');
			title.textContent = options.title;
			box.append(title);
		}
		if (options.text) {
			const text = document.createElement('p');
			text.textContent = options.text;
			box.append(text);
		}
		container.setAttribute('aria-busy', 'false');
		container.replaceChildren(box);
		return box;
	}

	function empty(container, options) {
		return state(container, 'ill-empty--none', options || {});
	}

	function failed(container, message, retry) {
		const box = state(container, 'ill-empty--error', {
			icon: 'exclamation-circle',
			title: t('This section could not load'),
			text: message || t(GENERIC),
		});
		box.setAttribute('role', 'alert');
		if (retry) {
			const button = document.createElement('button');
			button.type = 'button';
			button.className = 'btn btn-sm btn-outline-primary';
			button.textContent = t('Retry');
			button.addEventListener('click', () => retry());
			box.append(button);
		}
		return box;
	}

	window.PortalUI = {call, toast, announce, confirm, escape, fieldErrors, serverMessage, skeleton, empty, failed};
})();
