// Schedule detail page (compare). Plan 6.7: two saved lines side by side, read-only.
// The server re-checks access to both lines and only sends prices to pricing users;
// every value is written with textContent.

function renderComparison(container, data) {
	container.textContent = '';
	if (!data || data.enabled === false) {
		container.textContent = scheduleText("Line comparison is turned off on this site.");
		return;
	}
	var wrap = document.createElement('div');
	wrap.className = 'table-responsive';
	var table = document.createElement('table');
	table.className = 'table table-sm mb-0 ill-compare-table';
	var head = table.createTHead().insertRow();
	var corner = document.createElement('th');
	corner.scope = 'col';
	head.appendChild(corner);
	(data.lines || []).forEach(function(line) {
		var th = document.createElement('th');
		th.scope = 'col';
		th.textContent = line.designation + (line.location ? ' — ' + line.location : '');
		if (line.schedule !== scheduleContext.schedule_name) {
			var from = document.createElement('div');
			from.className = 'small text-muted';
			from.textContent = line.schedule_name;
			th.appendChild(from);
		}
		head.appendChild(th);
	});
	var body = table.createTBody();
	(data.rows || []).forEach(function(row) {
		var tr = body.insertRow();
		if (!row.same) tr.className = 'ill-compare-differs';
		var label = document.createElement('th');
		label.scope = 'row';
		label.textContent = row.label;
		if (!row.same) {
			var badge = document.createElement('span');
			badge.className = 'badge badge-warning ml-1';
			badge.textContent = scheduleText("Differs");
			label.appendChild(badge);
		}
		tr.appendChild(label);
		[row.a, row.b].forEach(function(value) {
			var cell = tr.insertCell();
			(Array.isArray(value) ? value : [value]).forEach(function(text, index) {
				if (index) cell.appendChild(document.createElement('br'));
				cell.appendChild(document.createTextNode(text));
			});
		});
	});
	wrap.appendChild(table);
	container.appendChild(wrap);
}

function compareLines(lineA, lineB, button) {
	var container = document.getElementById('compareResult');
	if (!lineA || !lineB || lineA === lineB) {
		container.textContent = scheduleText("Choose two different lines to compare.");
		return Promise.resolve(null);
	}
	container.setAttribute('aria-busy', 'true');
	container.textContent = scheduleText("Comparing…");
	return PortalAPI.call('illumenate_lighting.illumenate_lighting.portal.compare.compare_lines', {
		schedule: scheduleContext.schedule_name,
		line_a: lineA,
		line_b: lineB
	}, { type: 'GET', toast: false, retry: 1, button: button || null }).then(function(data) {
		renderComparison(container, data);
		return data;
	}, function(error) {
		PortalUI.failed(container, (error && error.message) || scheduleText("The comparison could not be loaded."), function() {
			compareLines(lineA, lineB, button);
		});
		return null;
	}).then(function(data) {
		container.setAttribute('aria-busy', 'false');
		return data;
	});
}

(function() {
	var form = document.getElementById('compareLinesForm');
	if (!form) return;
	form.addEventListener('submit', function(event) {
		event.preventDefault();
		compareLines(document.getElementById('compareLineA').value, document.getElementById('compareLineB').value, form.querySelector('button[type="submit"]'));
	});
})();
