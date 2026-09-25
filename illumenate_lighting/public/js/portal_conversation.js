/* Shared portal/Desk thread. Messages are plain text; attachments stay private. */
(function () {
	'use strict';
	window.PortalConversation = function (root) {
		if (root._conversation) return root._conversation;
		const api = 'illumenate_lighting.illumenate_lighting.portal.conversations.';
		const element = (tag, text, className) => {
			const node = document.createElement(tag);
			if (text !== undefined) node.textContent = text;
			if (className) node.className = className;
			return node;
		};
		const uid = 'thread-' + crypto.randomUUID();
		const status = element('p', '', 'text-muted');
		const result = element('p'); result.setAttribute('role', 'status');
		const list = element('div');
		const paging = element('nav'); paging.setAttribute('aria-label', __('Conversation pages'));
		const newer = element('button', __('Newer'), 'btn btn-sm btn-outline-secondary');
		const older = element('button', __('Older'), 'btn btn-sm btn-outline-secondary');
		const count = element('span', '', 'mx-3'); paging.append(newer, count, older);
		const form = element('form', undefined, 'my-3');
		const label = element('label', __('Your message')); label.htmlFor = uid;
		const body = element('textarea', undefined, 'form-control'); body.id = uid; body.rows = 4; body.required = true; body.maxLength = 20000;
		const fileLabel = element('label', __('Attachments: PDF, JPEG or PNG, up to 20 MiB each'), 'mt-2'); fileLabel.htmlFor = uid + '-files';
		const files = element('input', undefined, 'form-control'); files.id = fileLabel.htmlFor; files.type = 'file'; files.multiple = true; files.accept = '.pdf,.png,.jpg,.jpeg';
		const staffFields = element('div', undefined, 'my-2');
		const visibilityLabel = element('label', __('Visibility')); visibilityLabel.htmlFor = uid + '-visibility';
		const visibility = element('select', undefined, 'form-control'); visibility.id = visibilityLabel.htmlFor;
		[['Customer', __('Customer visible')], ['Internal', __('Staff only')]].forEach(([value, text]) => { const option = element('option', text); option.value = value; visibility.append(option); });
		const actionLabel = element('label', __('Action')); actionLabel.htmlFor = uid + '-action';
		const action = element('select', undefined, 'form-control'); action.id = actionLabel.htmlFor;
		[['REPLY', __('Reply')], ['REQUEST_INFO', __('Request customer information')], ['RESOLVE', __('Resolve with this message')], ['REOPEN', __('Reopen with this message')]].forEach(([value, text]) => { const option = element('option', text); option.value = value; action.append(option); });
		staffFields.append(visibilityLabel, visibility, actionLabel, action); staffFields.hidden = true;
		const submit = element('button', __('Send message'), 'btn btn-primary mt-3'); submit.type = 'submit';
		form.append(label, body, fileLabel, files, staffFields, submit);
		root.append(status, list, paging, form, result);
		let page = 1, serial = 0, sending = false, retryBody, retryKey;
		const context = { parent_type: root.dataset.parentType, parent_name: root.dataset.parentName };
		const commercial = ['ilL-Quote-Request', 'ilL-Order-Intake', 'ilL-Order-Change'].includes(context.parent_type);
		if (commercial) [...action.options].filter(option => ['RESOLVE', 'REOPEN'].includes(option.value)).forEach(option => option.remove());
		async function load() {
			const token = ++serial;
			try {
				const response = await frappe.call({method: api + 'list_messages', args: {...context, page}});
				if (token !== serial || !root.isConnected) return;
				const data = response.message;
				status.textContent = __('Status: {0}. Next action: {1}.', [data.status, data.next_action_by]);
				staffFields.hidden = !data.is_staff; form.hidden = !(data.can_reply || (!commercial && data.is_staff));
				list.replaceChildren();
				if (!data.messages.length) list.append(element('p', __('No replies yet.')));
				data.messages.forEach(message => {
					const card = element('article', undefined, 'border rounded p-3 mb-2');
					card.append(element('p', `${message.actor} · ${message.creation} · ${message.visibility === 'Internal' ? __('Staff only') : __('Customer visible')}`, 'text-muted'));
					const text = element('p', message.body); text.style.whiteSpace = 'pre-wrap'; card.append(text);
					(message.files || []).forEach(file => {
						if (!file.file_url.startsWith('/private/files/')) return;
						const link = element('a', file.file_name, 'd-block'); link.href = file.file_url; card.append(link);
					});
					list.append(card);
				});
				count.textContent = __('Page {0} · {1} messages', [data.page, data.total]);
				newer.disabled = page <= 1; older.disabled = page * data.page_size >= data.total;
			} catch (error) { if (token === serial) result.textContent = __('Could not load this conversation. Reload to check your access.'); }
		}
		newer.addEventListener('click', () => { page--; load(); });
		older.addEventListener('click', () => { page++; load(); });
		visibility.addEventListener('change', () => { if (visibility.value === 'Internal') action.value = 'REPLY'; action.disabled = visibility.value === 'Internal'; });
		form.addEventListener('submit', async event => {
			event.preventDefault(); if (sending) return;
			sending = true; submit.disabled = true; result.textContent = __('Sending…');
			const draft = {body: body.value.trim(), visibility: visibility.value, action: action.value};
			try {
				const file_ids = await PortalUploads.uploadAll(files);
				const payload = {...context, ...draft, file_ids};
				const signature = JSON.stringify(payload);
				if (signature !== retryBody) { retryBody = signature; retryKey = crypto.randomUUID(); }
				await PortalUploads.call(api + 'reply', {...payload, idempotency_key: retryKey});
				if (body.value.trim() === draft.body) body.value = '';
				files.value = ''; files._uploadedFiles = new Map(); retryBody = null; retryKey = null;
				page = 1; result.textContent = __('Message received.'); await load();
			} catch (error) { result.textContent = error.message || __('Message not sent. Your draft is preserved.'); }
			finally { sending = false; submit.disabled = false; }
		});
		root._conversation = {refresh: load}; load(); return root._conversation;
	};
	function mount() { document.querySelectorAll('[data-portal-conversation]').forEach(root => window.PortalConversation(root)); }
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true}); else mount();
})();
