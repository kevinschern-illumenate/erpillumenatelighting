frappe.pages['ill-portal-operations'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({parent: wrapper, title: __('Portal Operations'), single_column: true});
	const container = document.createElement('div'); container.className = 'p-3'; page.main[0].append(container);
	const cards = document.createElement('div'); cards.className = 'd-flex flex-wrap';
	const filters = document.createElement('div'); filters.className = 'my-3';
	const label = document.createElement('label'); label.textContent = __('Queue view'); label.htmlFor = 'portal-queue-view';
	const view = document.createElement('select'); view.id = label.htmlFor; view.className = 'form-control';
	const searchLabel = document.createElement('label'); searchLabel.textContent = __('Find request ID'); searchLabel.htmlFor = 'portal-queue-search';
	const search = document.createElement('input'); search.id = searchLabel.htmlFor; search.className = 'form-control'; search.type = 'search';
	filters.append(label, view, searchLabel, search);
	const status = document.createElement('p'); status.setAttribute('role', 'status');
	const table = document.createElement('div'); table.className = 'table-responsive';
	const nav = document.createElement('nav'); nav.setAttribute('aria-label', __('Queue pages'));
	const prev = document.createElement('button'); prev.textContent = __('Previous'); prev.className = 'btn btn-default';
	const next = document.createElement('button'); next.textContent = __('Next'); next.className = 'btn btn-default'; nav.append(prev, next);
	container.append(cards, filters, status, table, nav);
	let selected, currentPage = 1, version = 0, timer;
	async function load() {
		if (!selected) return;
		const request = ++version; status.textContent = __('Loading…');
		try {
			const r = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.queues.items', args: {queue: selected.key, view: view.value, search: search.value, page: currentPage}});
			if (request !== version) return;
			const data = r.message; table.replaceChildren();
			status.textContent = __('{0}: {1} requests · page {2}', [data.label, data.total, data.page]);
			const grid = document.createElement('table'); grid.className = 'table';
			const columns = Object.keys(data.rows[0] || {});
			const head = document.createElement('tr'); columns.forEach(key => { const cell = document.createElement('th'); cell.textContent = key.replaceAll('_', ' '); head.append(cell); });
			const thead = document.createElement('thead'); thead.append(head); grid.append(thead);
			const tbody = document.createElement('tbody');
			data.rows.forEach(row => { const tr = document.createElement('tr'); columns.forEach(key => { const td = document.createElement('td'); if (key === 'name') { const link = document.createElement('button'); link.className = 'btn btn-link p-0'; link.textContent = row[key]; link.addEventListener('click', () => frappe.set_route('Form', data.doctype, row.name)); td.append(link); } else td.textContent = row[key] == null ? '—' : String(row[key]); tr.append(td); }); tbody.append(tr); });
			grid.append(tbody); table.append(grid); prev.disabled = currentPage <= 1; next.disabled = currentPage * data.page_size >= data.total;
		} catch (error) { if (request === version) { table.replaceChildren(); status.textContent = __('Queue unavailable. Check your role or retry.'); } }
	}
	async function refresh() {
		try {
			const r = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.queues.summary'});
			cards.replaceChildren();
			r.message.queues.forEach(queue => {
				const button = document.createElement('button'); button.className = 'btn btn-default m-1'; button.textContent = `${queue.label}: ${queue.available ? queue.total : __('Unavailable')}`; button.disabled = !queue.available;
				button.addEventListener('click', () => { selected = queue; currentPage = 1; view.replaceChildren(); queue.views.forEach(value => { const option = document.createElement('option'); option.value = value; option.textContent = __(value); view.append(option); }); load(); }); cards.append(button);
			});
			if (!selected) cards.querySelector('button:not(:disabled)')?.click(); else load();
			if (!r.message.queues.length) status.textContent = __('No portal operations role is assigned to this account.');
		} catch (error) { status.textContent = __('Could not load queue counts.'); }
	}
	view.addEventListener('change', () => { currentPage = 1; load(); });
	search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { currentPage = 1; load(); }, 250); });
	prev.addEventListener('click', () => { currentPage--; load(); }); next.addEventListener('click', () => { currentPage++; load(); });
	page.set_primary_action(__('Refresh queues'), refresh); refresh();
};
