/* Shared portal/Desk thread. Messages are plain text; attachments stay private.
   Decisions, buyer replies and staff replies share one conversation, oldest first. */
(function () {
	'use strict';
	const STYLE = `
.ill-thread{--t-line:var(--ill-navy-100,#E8EAED);--t-soft:var(--ill-surface-soft,#F6F8FA);--t-muted:var(--ill-text-secondary,#5D6D7F);--t-brand:var(--ill-blue-600,#00588C)}
.ill-thread__status{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-bottom:1rem;color:var(--t-muted);font-size:.875rem}
.ill-thread__pill{display:inline-block;padding:.15rem .65rem;border-radius:999px;background:var(--ill-blue-100,#E6EEF4);color:var(--ill-blue-800,#003E62);font-weight:600;font-size:.75rem}
.ill-thread__pill--wait{background:var(--ill-gold-100,#FFF9EE);color:var(--ill-gold-ink,#7A5500)}
.ill-thread__list{display:flex;flex-direction:column;gap:.75rem}
.ill-thread__empty{color:var(--t-muted);text-align:center;padding:1.5rem;border:1px dashed var(--t-line);border-radius:12px}
.ill-thread__msg{max-width:88%;padding:.75rem 1rem;border:1px solid var(--t-line);border-radius:14px;background:#fff}
.ill-thread__msg--mine{align-self:flex-end;background:var(--ill-blue-100,#E6EEF4);border-color:var(--ill-blue-200,#99BCD1)}
.ill-thread__msg--theirs{align-self:flex-start;background:var(--t-soft)}
.ill-thread__msg--decision{border-left:4px solid var(--ill-gold-500,#FDC757)}
.ill-thread__msg--internal{border-style:dashed}
.ill-thread__meta{display:flex;flex-wrap:wrap;gap:.4rem;align-items:baseline;font-size:.8rem;color:var(--t-muted);margin-bottom:.35rem}
.ill-thread__author{font-weight:600;color:var(--ill-navy-600,#172E48)}
.ill-thread__tag{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--t-brand)}
.ill-thread__body{white-space:pre-wrap;margin:0;word-break:break-word}
.ill-thread__files a{display:block;font-size:.875rem;margin-top:.35rem}
.ill-thread__paging{display:flex;justify-content:center;gap:.75rem;align-items:center;margin:.75rem 0;font-size:.8rem;color:var(--t-muted)}
.ill-thread__form{margin-top:1rem;padding-top:1rem;border-top:1px solid var(--t-line)}
.ill-thread__result{font-size:.875rem;color:var(--t-muted);margin:.5rem 0 0}`;
	const STATES = {SUBMITTED: 'Submitted', UNDER_REVIEW: 'Under review', INFORMATION_NEEDED: 'Information needed',
		CHANGES_PROPOSED: 'Changes proposed', APPROVED: 'Approved', REJECTED: 'Needs correction', WITHDRAWN: 'Withdrawn',
		REQUESTED: 'Requested', ISSUED: 'Issued', CLOSED: 'Closed', COMPLETED: 'Completed'};
	function addStyle() {
		if (document.getElementById('ill-thread-style')) return;
		const style = document.createElement('style'); style.id = 'ill-thread-style'; style.textContent = STYLE;
		document.head.append(style);
	}
	function when(value) {
		const date = new Date(String(value).replace(' ', 'T'));
		return isNaN(date) ? String(value) : date.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
	}
	window.PortalConversation = function (root) {
		if (root._conversation) return root._conversation;
		addStyle();
		root.classList.add('ill-thread');
		const api = 'illumenate_lighting.illumenate_lighting.portal.conversations.';
		const element = (tag, text, className) => {
			const node = document.createElement(tag);
			if (text !== undefined) node.textContent = text;
			if (className) node.className = className;
			return node;
		};
		const uid = 'thread-' + crypto.randomUUID();
		const status = element('div', '', 'ill-thread__status');
		const result = element('p', '', 'ill-thread__result'); result.setAttribute('role', 'status');
		const list = element('div', undefined, 'ill-thread__list'); list.setAttribute('aria-live', 'polite');
		const paging = element('nav', undefined, 'ill-thread__paging'); paging.setAttribute('aria-label', __('Conversation pages'));
		const older = element('button', __('Earlier messages'), 'btn btn-sm btn-outline-secondary'); older.type = 'button';
		const newer = element('button', __('Later messages'), 'btn btn-sm btn-outline-secondary'); newer.type = 'button';
		const count = element('span'); paging.append(older, count, newer);
		const form = element('form', undefined, 'ill-thread__form');
		const label = element('label', __('Your message')); label.htmlFor = uid;
		const body = element('textarea', undefined, 'form-control'); body.id = uid; body.rows = 3; body.required = true; body.maxLength = 20000;
		const fileLabel = element('label', __('Attachments: PDF, JPEG or PNG, up to 20 MiB each'), 'mt-2 small'); fileLabel.htmlFor = uid + '-files';
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
		form.append(label, body, fileLabel, files, staffFields, submit, result);
		root.append(status, paging, list, form);
		let page = 1, serial = 0, sending = false, retryBody, retryKey;
		const context = { parent_type: root.dataset.parentType, parent_name: root.dataset.parentName };
		const commercial = ['ilL-Quote-Request', 'ilL-Order-Intake', 'ilL-Order-Change', 'ilL-Product-Verification-Request'].includes(context.parent_type);
		if (commercial) [...action.options].filter(option => ['RESOLVE', 'REOPEN'].includes(option.value)).forEach(option => option.remove());
		function waitingOn(data) {
			if (data.next_action_by === 'None') return '';
			const buyer = data.next_action_by === 'Customer';
			if (data.is_staff) return buyer ? __('Waiting on the buyer') : __('Waiting on ilLumenate');
			return buyer ? __('Waiting on you') : __('Waiting on ilLumenate');
		}
		function renderMessage(message, viewerIsStaff) {
			const fromStaff = message.from_staff === undefined ? !!viewerIsStaff : !!message.from_staff;
			const mine = fromStaff === !!viewerIsStaff;
			const card = element('article', undefined, 'ill-thread__msg ' + (mine ? 'ill-thread__msg--mine' : 'ill-thread__msg--theirs'));
			if (message.action === 'DECISION') card.classList.add('ill-thread__msg--decision');
			if (message.visibility === 'Internal') card.classList.add('ill-thread__msg--internal');
			const meta = element('div', undefined, 'ill-thread__meta');
			meta.append(element('span', message.actor_name || message.actor, 'ill-thread__author'));
			if (fromStaff) meta.append(element('span', __('ilLumenate'), 'ill-thread__tag'));
			if (message.action === 'DECISION') meta.append(element('span', __('Update'), 'ill-thread__tag'));
			if (message.action === 'REQUEST_INFO') meta.append(element('span', __('Information requested'), 'ill-thread__tag'));
			if (message.visibility === 'Internal') meta.append(element('span', __('Staff only'), 'ill-thread__tag'));
			meta.append(element('span', when(message.creation)));
			card.append(meta, element('p', message.body, 'ill-thread__body'));
			const attachments = element('div', undefined, 'ill-thread__files');
			(message.files || []).forEach(file => {
				if (!file.file_url.startsWith('/private/files/')) return;
				const link = element('a', file.file_name); link.href = file.file_url; attachments.append(link);
			});
			if (attachments.childElementCount) card.append(attachments);
			return card;
		}
		async function load() {
			const token = ++serial;
			try {
				const response = await frappe.call({method: api + 'list_messages', args: {...context, page}});
				if (token !== serial || !root.isConnected) return;
				const data = response.message;
				status.replaceChildren(element('span', __(STATES[data.status] || data.status || ''), 'ill-thread__pill'));
				const waiting = waitingOn(data);
				if (waiting) status.append(element('span', waiting, 'ill-thread__pill ill-thread__pill--wait'));
				staffFields.hidden = !data.is_staff; form.hidden = !(data.can_reply || (!commercial && data.is_staff));
				list.replaceChildren();
				if (!data.messages.length) list.append(element('p', __('No messages yet. Questions and updates about this request appear here.'), 'ill-thread__empty'));
				// The API pages newest first; read each page top to bottom, oldest first.
				[...data.messages].reverse().forEach(message => list.append(renderMessage(message, data.is_staff)));
				const pages = Math.max(1, Math.ceil(data.total / data.page_size));
				paging.hidden = pages <= 1;
				count.textContent = __('Page {0} of {1}', [pages - data.page + 1, pages]);
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
				page = 1; result.textContent = __('Message sent.'); await load();
			} catch (error) { result.textContent = error.message || __('Message not sent. Your draft is preserved.'); }
			finally { sending = false; submit.disabled = false; }
		});
		root._conversation = {refresh: load}; load(); return root._conversation;
	};
	function mount() { document.querySelectorAll('[data-portal-conversation]').forEach(root => window.PortalConversation(root)); }
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true}); else mount();
})();
