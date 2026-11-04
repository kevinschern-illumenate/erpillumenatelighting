// Schedule detail page (exports). Extracted verbatim from templates/pages/schedule.html (plan 2.1).

function generateExport(format, priced) {
	var method = format === 'pdf'
		? 'illumenate_lighting.illumenate_lighting.api.exports.generate_schedule_pdf'
		: 'illumenate_lighting.illumenate_lighting.api.exports.generate_schedule_csv';

	frappe.show_alert({
		message: 'Generating ' + format.toUpperCase() + ' export...',
		indicator: 'blue'
	});

	frappe.call({
		method: method,
		args: {
			schedule_id: schedule_name,
			priced: priced
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				frappe.show_alert({
					message: 'Export generated successfully!',
					indicator: 'green'
				});
				// Refresh export history
				loadExportHistory();
				// Download via the secure serve endpoint (portal users cannot
				// access private files directly).
				if (r.message.export_job) {
					window.open(
						'/api/method/illumenate_lighting.illumenate_lighting.api.exports.serve_export_file'
						+ '?export_job_id=' + encodeURIComponent(r.message.export_job),
						'_blank'
					);
				} else if (r.message.download_url) {
					window.open(r.message.download_url, '_blank');
				}
			} else {
				frappe.msgprint({
					title: 'Export Error',
					indicator: 'red',
					message: r.message.error || 'Error generating export'
				});
			}
		},
		error: function() {
			frappe.msgprint({
				title: 'Export Error',
				indicator: 'red',
				message: 'Error generating export'
			});
		}
	});
}

function loadExportHistory() {
	var $container = $('#exportHistoryContainer');
	var completed = false;
	var retry = function() {
		PortalUI.skeleton($container[0], scheduleText("Loading export history…"));
		loadExportHistory();
	};
	var loadingTimer = setTimeout(function() {
		if (!completed) {
			PortalUI.failed($container[0], scheduleText("Export history is taking longer than expected."), retry);
		}
	}, 15000);

	function showExportHistoryError(message) {
		completed = true;
		clearTimeout(loadingTimer);
		PortalUI.failed($container[0], PortalUI.serverMessage(message) || scheduleText("Export history could not be loaded."), retry);
	}

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.exports.get_export_history',
		args: {
			schedule_id: schedule_name
		},
		callback: function(r) {
			completed = true;
			clearTimeout(loadingTimer);
			if (r.message && r.message.success) {
				renderExportHistory(r.message.exports || []);
			} else {
				showExportHistoryError(r.message && r.message.error);
			}
		},
		error: function(r) {
			showExportHistoryError(r);
		}
	});
}

function renderExportHistory(exports) {
	if (!exports || exports.length === 0) {
		PortalUI.empty(document.getElementById('exportHistoryContainer'), {
			icon: 'download',
			title: scheduleText("No exports yet"),
			text: scheduleText("Use the buttons above to generate exports.")
		});
		return;
	}

	var html = '<div class="table-responsive"><table class="table table-hover mb-0">';
	html += '<thead class="thead-light"><tr>';
	html += '<th>Type</th>';
	html += '<th>Status</th>';
	html += '<th>Requested By</th>';
	html += '<th>Created</th>';
	html += '<th>Download</th>';
	html += '</tr></thead><tbody>';

	exports.forEach(function(exp) {
		var exportStatus = exportStatuses[exp.status] || {label: exp.status, css: 'secondary'};

		var typeLabelMap = {
			'PDF_PRICED': 'PDF (With Pricing)',
			'PDF_NO_PRICE': 'PDF (No Pricing)',
			'CSV_PRICED': 'CSV (With Pricing)',
			'CSV_NO_PRICE': 'CSV (No Pricing)',
			'SPEC_SUBMITTAL': 'Spec Submittal',
			'SPEC_SUBMITTAL_FULL': 'Spec Submittal (Full)'
		};
		var typeLabel = typeLabelMap[exp.export_type] || exp.export_type.replace(/_/g, ' ');
		var createdOn = exp.created_on ? frappe.datetime.prettyDate(exp.created_on) : '-';

		html += '<tr>';
		html += '<td>' + typeLabel + '</td>';
		html += '<td><span class="badge badge-' + PortalUI.escape(exportStatus.css) + '">' + frappe.utils.escape_html(exportStatus.label) + '</span></td>';
		html += '<td>' + frappe.utils.escape_html(exp.requested_by_name || '-') + '</td>';
		html += '<td>' + createdOn + '</td>';
		html += '<td>';
		if ((exp.status === 'COMPLETE' || exp.status === 'INCOMPLETE') && exp.output_file) {
			var dlUrl = '/api/method/illumenate_lighting.illumenate_lighting.api.exports.serve_export_file'
				+ '?export_job_id=' + encodeURIComponent(exp.name);
			html += '<a href="' + dlUrl + '" target="_blank" class="btn btn-sm btn-outline-primary">';
			html += '<i class="fa fa-download" aria-hidden="true"></i> Download</a>';
            if (exp.export_type.indexOf('SPEC_SUBMITTAL') === 0) {
                if (exp.issued_on) html += ' <span>Issued ' + frappe.utils.escape_html(exp.issued_on) + '</span>';
                else if (scheduleContext.can_issue_packet) html += ' <button class="btn btn-sm btn-outline-primary packet-issue" data-job="' + frappe.utils.escape_html(exp.name) + '">Issue packet</button>';
            }
		} else if (exp.status === 'FAILED') {
			html += '<span class="text-danger"><i class="fa fa-times" aria-hidden="true"></i> Failed</span>';
            if (exp.export_type.indexOf('SPEC_SUBMITTAL') === 0) html += ' <button class="btn btn-sm btn-outline-primary packet-retry" data-job="' + frappe.utils.escape_html(exp.name) + '">Retry</button>';
		} else {
			html += '<span class="text-muted"><i class="fa fa-clock-o" aria-hidden="true"></i> Pending</span>';
		}
		if (exp.status === 'FAILED' && exp.error_log) html += '<details><summary>Details</summary><pre style="white-space:pre-wrap">' + frappe.utils.escape_html(exp.error_log) + '</pre></details>';
        if (exp.status === 'RUNNING') html += ' ' + frappe.utils.escape_html(exp.progress_message || '') + ' (' + Number(exp.progress || 0) + '%)';
        html += '</td>';
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    $('#exportHistoryContainer').attr('aria-busy', 'false').html(html);
    $('#exportHistoryContainer .packet-issue').on('click', function () {
        frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.packet_jobs.issue', args: {job_name: this.dataset.job}, callback: loadExportHistory});
    });
    $('#exportHistoryContainer .packet-retry').on('click', function () { retryPacket(this.dataset.job); });
}

// Load export history on page load
$(document).ready(function() {
	loadExportHistory();
    $('.line-documents').on('click', function () { PortalLineDocuments.open(this.dataset.schedule, this.dataset.line).catch(function (error) { frappe.msgprint(frappe.utils.escape_html(error.message)); }); });
	loadVersionHistory();
	restoreScrollAfterReorder();
	initLineReorder();
});
