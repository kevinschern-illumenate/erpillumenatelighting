// Schedule detail page (plan 3.12): when a save is refused because someone else saved the schedule
// since this page loaded, say who and when ("Updated by <user> at <time>") with Reload and Compare
// actions instead of a generic error. The server puts {modified, modified_display, modified_by_name}
// in `conflict`, next to the old `success`/`error` keys. Text-only DOM.
var ScheduleConflict = (function () {
	function format(text) {
		var values = Array.prototype.slice.call(arguments, 1);
		return text.replace(/\{(\d)\}/g, function (match, index) {
			return values[index] === undefined ? match : String(values[index]);
		});
	}

	function details(r) {
		if (!r || typeof r !== 'object') return null;
		var conflict = r.conflict || (r.message && typeof r.message === 'object' ? r.message.conflict : null);
		return conflict && typeof conflict === 'object' ? conflict : null;
	}

	function notice() {
		var box = document.getElementById('scheduleConflictNotice');
		if (box) return box;
		box = document.createElement('div');
		box.id = 'scheduleConflictNotice';
		box.className = 'alert alert-warning ill-conflict-notice';
		box.setAttribute('role', 'alert');
		box.setAttribute('tabindex', '-1');
		document.body.insertBefore(box, document.body.firstChild);
		return box;
	}

	function button(label, action, primary) {
		var element = document.createElement('button');
		element.type = 'button';
		element.className = 'btn btn-sm ml-2 ' + (primary ? 'btn-warning' : 'btn-outline-secondary');
		element.setAttribute('data-conflict-action', action);
		element.textContent = label;
		return element;
	}

	function canCompare() {
		return !!(window.ScheduleActivity && scheduleContext.activity_timeline);
	}

	function show(conflict) {
		var box = notice();
		box.textContent = '';
		var text = document.createElement('span');
		text.className = 'ill-conflict-text';
		text.textContent = format(
			scheduleText("Updated by {0} at {1}."),
			conflict.modified_by_name || scheduleText("another user"),
			conflict.modified_display || conflict.modified || ''
		) + ' ' + scheduleText("Your change was not saved.");
		box.appendChild(text);
		box.appendChild(button(scheduleText("Reload"), 'reload', true));
		if (canCompare()) box.appendChild(button(scheduleText("Compare"), 'compare', false));
		box.hidden = false;
		if (typeof box.focus === 'function') box.focus();
		if (typeof box.scrollIntoView === 'function') box.scrollIntoView({ block: 'nearest' });
	}

	// The generic error dialog for the same response is replaced by the notice.
	function hideGenericError() {
		setTimeout(function () {
			var dialog = window.frappe && window.frappe.msg_dialog;
			if (dialog && typeof dialog.hide === 'function') dialog.hide();
		}, 0);
	}

	function handle(r) {
		var conflict = details(r);
		if (!conflict) return false;
		show(conflict);
		return true;
	}

	document.addEventListener('click', function (event) {
		var target = event.target && event.target.closest ? event.target.closest('[data-conflict-action]') : null;
		if (!target) return;
		if (target.getAttribute('data-conflict-action') === 'reload') ScheduleConflict.reload();
		else if (canCompare()) window.ScheduleActivity.open(true);
	});

	// Errors thrown by an endpoint (e.g. bulk edit, import) never reach the page's callback, so the
	// notice also watches every response.
	if (window.jQuery && typeof window.jQuery.fn === 'object') {
		window.jQuery(document).on('ajaxComplete', function (event, xhr) {
			if (handle(xhr && xhr.responseJSON)) hideGenericError();
		});
	}

	return {
		details: details,
		handle: handle,
		show: show,
		reload: function () { window.location.reload(); },
	};
})();
