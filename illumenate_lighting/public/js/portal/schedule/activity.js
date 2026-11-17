// Schedule detail page (plan 3.11): a read-only activity timeline, loaded on demand from
// portal/schedule_activity.schedule_activity in pages of 20. Entries are plain text from the server
// (line changes, status changes, notices and exports); this renders them with textContent only.
// Entries newer than the copy of the schedule on this page are marked, which is what "Compare" in
// the collaborator conflict notice (plan 3.12) opens.
var ScheduleActivity = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.schedule_activity.schedule_activity';
	var PAGE = 20;
	var next = 0;
	var loading = false;
	var loaded = false;

	function el(id) { return document.getElementById(id); }

	function enabled() { return !!scheduleContext.activity_timeline && !!el('scheduleActivity'); }

	function status(text) {
		var node = el('scheduleActivityStatus');
		if (node) node.textContent = text || '';
	}

	function isNew(entry) {
		return !!scheduleContext.schedule_modified && String(entry.at || '') > String(scheduleContext.schedule_modified);
	}

	function part(tag, className, text) {
		var node = document.createElement(tag);
		node.className = className;
		node.textContent = text;
		return node;
	}

	function item(entry) {
		var li = document.createElement('li');
		li.className = 'ill-activity-item ill-activity-' + String(entry.kind || 'event').replace(/[^a-z_]/g, '');
		if (isNew(entry)) {
			li.classList.add('is-new');
			li.appendChild(part('span', 'badge badge-warning ill-activity-new', scheduleText("New since you opened this page")));
		}
		li.appendChild(part('span', 'ill-activity-title', entry.title || ''));
		if (entry.detail) li.appendChild(part('span', 'ill-activity-detail', entry.detail));
		var meta = entry.at_display || entry.at || '';
		if (entry.by_name) meta += ' · ' + entry.by_name;
		li.appendChild(part('span', 'ill-activity-meta', meta));
		return li;
	}

	function render(entries, append) {
		var list = el('scheduleActivityList');
		if (!list) return;
		if (!append) list.textContent = '';
		(entries || []).forEach(function (entry) { list.appendChild(item(entry)); });
	}

	function load(more) {
		if (loading || !enabled()) return;
		loading = true;
		var body = el('scheduleActivity');
		body.setAttribute('aria-busy', 'true');
		status(scheduleText("Loading activity…"));
		frappe.call({
			method: METHOD,
			args: { schedule_name: scheduleContext.schedule_name, start: more ? next : 0, limit: PAGE },
			callback: function (r) {
				var message = (r && r.message) || {};
				if (!message.success) {
					status(message.error || scheduleText("Activity could not be loaded."));
					return;
				}
				render(message.entries, more);
				loaded = true;
				next = message.next_start || 0;
				var button = el('scheduleActivityMore');
				if (button) button.hidden = !message.has_more;
				var empty = !more && !(message.entries || []).length;
				status(empty ? scheduleText("No activity yet.") : '');
			},
			error: function () { status(scheduleText("Activity could not be loaded.")); },
			always: function () {
				loading = false;
				body.setAttribute('aria-busy', 'false');
			},
		});
	}

	function setOpen(open) {
		var body = el('scheduleActivity');
		var toggle = el('scheduleActivityToggle');
		if (body) body.hidden = !open;
		if (toggle) {
			toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
			toggle.textContent = open ? scheduleText("Hide activity") : scheduleText("Show activity");
		}
	}

	// ``refresh`` reloads the first page, e.g. after someone else saved the schedule.
	function open(refresh) {
		if (!enabled()) return;
		setOpen(true);
		if (!loaded || refresh) load(false);
		var section = el('scheduleActivitySection');
		if (section && typeof section.scrollIntoView === 'function') section.scrollIntoView({ block: 'start' });
	}

	document.addEventListener('click', function (event) {
		var target = event.target && event.target.closest ? event.target.closest('#scheduleActivityToggle, #scheduleActivityMore') : null;
		if (!target) return;
		if (target.id === 'scheduleActivityMore') load(true);
		else if (el('scheduleActivity') && el('scheduleActivity').hidden) open(false);
		else setOpen(false);
	});

	return { open: open, close: function () { setOpen(false); }, load: load, render: render };
})();
