// Schedule detail page (versions). Extracted verbatim from templates/pages/schedule.html (plan 2.1).

// ─── Version History ─────────────────────────────────────────────────────────
function loadVersionHistory() {
	var container = document.getElementById('versionHistory');
	var failed = function(message) {
		PortalUI.failed(container, PortalUI.serverMessage(message) || scheduleText("Version history could not be loaded."), function() {
			PortalUI.skeleton(container, scheduleText("Loading version history…"), 2);
			loadVersionHistory();
		});
	};
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_version_history',
		args: { schedule_name: scheduleContext.schedule_name },
		callback: function(r) {
			if (r.message && r.message.success) {
				container.setAttribute('aria-busy', 'false');
				renderVersionHistory(r.message.versions, r.message.current);
			} else {
				failed(r.message && r.message.error);
			}
		},
		error: failed
	});
}

function renderVersionHistory(versions, current) {
	if (!versions || versions.length <= 1) {
		PortalUI.empty(document.getElementById('versionHistory'), {
			icon: 'history',
			title: scheduleText("No earlier versions"),
			text: scheduleText("This is the first version of this schedule.")
		});
		return;
	}
	var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0">';
	html += '<thead><tr>';
	html += '<th>Version</th><th>Status</th><th>Notes</th><th>Modified</th><th></th>';
	html += '</tr></thead><tbody>';
	versions.forEach(function(v) {
		var isCurrent = (v.name === current);
		var statusClass = scheduleStatusClasses[v.status] || 'secondary';
		var statusLabel = statusLabels[v.status] || v.status;
		html += '<tr' + (isCurrent ? ' class="table-active"' : '') + '>';
		html += '<td><strong>v' + (v.version || 1) + '</strong>';
		if (v.is_locked) html += ' <i class="fa fa-lock text-muted" role="img" title="' + frappe.utils.escape_html(__('Locked')) + '" aria-label="' + frappe.utils.escape_html(__('Locked')) + '"></i>';
		if (isCurrent) html += ' <span class="badge badge-primary ml-1">current</span>';
		html += '</td>';
		html += '<td><span class="badge badge-' + statusClass + '">' + frappe.utils.escape_html(statusLabel) + '</span></td>';
		html += '<td>' + (v.version_notes ? frappe.utils.escape_html(v.version_notes) : '<span class="text-muted">—</span>') + '</td>';
		html += '<td>' + (v.modified ? frappe.datetime.prettyDate(v.modified) : '-') + '</td>';
		html += '<td>';
		if (!isCurrent) {
			html += '<a href="/portal/schedules/' + encodeURIComponent(v.name) + '" class="btn btn-sm btn-outline-primary">View</a>';
		}
		html += '</td>';
		html += '</tr>';
	});
	html += '</tbody></table></div>';
	$('#versionHistory').html(html);
}

function createNewVersion() {
	$('#versionNotes').val('');
	$('#createVersionModal').modal('show');
}

function confirmCreateVersion() {
	var btn = $('#confirmCreateVersionBtn');
	btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Creating...');
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.create_schedule_version',
		args: {
			schedule_name: scheduleContext.schedule_name,
			version_notes: $('#versionNotes').val() || ''
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				$('#createVersionModal').modal('hide');
				frappe.show_alert({message: 'New version created!', indicator: 'green'});
				window.location.href = '/portal/schedules/' + r.message.new_schedule_name;
			} else {
				btn.prop('disabled', false).html('<i class="fa fa-code-fork" aria-hidden="true"></i> Create');
				frappe.msgprint(r.message ? r.message.error : 'Error creating version');
			}
		},
		error: function() {
			btn.prop('disabled', false).html('<i class="fa fa-code-fork" aria-hidden="true"></i> Create');
		}
	});
}
