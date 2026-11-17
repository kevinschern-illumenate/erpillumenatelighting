// Schedule detail page (plan 3.9): "Catalog updated — review" badges. The server lists the lines
// whose template, options or chosen power supplies changed since they were configured. Each badge
// names the changes and, for editors, links to the row's own configure link, where the line is
// validated again against the current catalog. Nothing is changed until the dealer saves there.
var ScheduleStale = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.catalog_drift.check';
	var lines = {};

	function rowFor(key) {
		return $('tr[data-line-key]').filter(function () { return this.getAttribute('data-line-key') === key; }).first();
	}

	function badge(key, problems) {
		var row = rowFor(key);
		var cell = row.children('td.col-fixture-details');
		if (!cell.length) return;
		cell.children('.ill-stale-line').remove();
		var box = $('<div class="ill-stale-line small mt-1" role="status"></div>').attr('data-line-key', key);
		box.append($('<span class="badge badge-warning"></span>').text(scheduleText("Catalog updated — review")));
		var configure = row.find('td.col-actions a[href*="line_key="]').first();
		if (configure.length) {
			box.append(' ', $('<a class="ill-stale-review"></a>')
				.attr('href', configure.attr('href'))
				.text(scheduleText("Review and re-validate")));
		}
		var list = $('<ul class="mb-0 pl-3 text-muted"></ul>');
		problems.forEach(function (problem) { list.append($('<li></li>').text(problem)); });
		box.append(list);
		cell.append(box);
	}

	function apply(found) {
		$('.ill-stale-line').remove();
		lines = {};
		Object.keys(found || {}).forEach(function (key) {
			var problems = (found[key] || []).filter(function (problem) { return typeof problem === 'string' && problem; });
			if (!problems.length) return;
			lines[key] = problems;
			badge(key, problems);
		});
	}

	function load() {
		frappe.call({
			method: METHOD,
			type: 'GET',
			args: { schedule_name: scheduleContext.schedule_name },
			callback: function (r) {
				var message = (r && r.message) || {};
				if (message.enabled) apply(message.lines);
			},
			// The badge is advisory: a failed check leaves the schedule as it is.
			error: function () {},
		});
	}

	if (scheduleContext.stale_badge && scheduleContext.schedule_name) $(load);

	return {
		load: load,
		apply: apply,
		lines: function () { return $.extend({}, lines); },
	};
})();
