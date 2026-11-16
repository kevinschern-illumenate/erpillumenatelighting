// Schedule detail page (plan 3.5): "Add by part number" in the Add Line dialog. The server decodes
// the part number against the products offered now; a match opens the configurator pre-filled
// (?pn=) with this dialog's line details as the add-line draft. Nothing is saved until the dealer
// adds the line, and codes the server could not match are shown, never guessed.
var SchedulePartNumber = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.part_number.decode_part_number';

	function show(text, failed) {
		var $result = $('#addLinePartNumberResult');
		$result.text(text).toggleClass('text-danger', !!failed).toggleClass('text-muted', !failed);
	}

	function metadata() {
		var form = $('#addLineForm');
		var values = {};
		['line_id', 'location', 'qty', 'notes'].forEach(function (field) { values[field] = form.find('[name="' + field + '"]').val() || ''; });
		return values;
	}

	function open(partNumber) {
		var values = metadata();
		var qty = Number(values.qty || 1);
		if (!Number.isInteger(qty) || qty < 1) {
			show(scheduleText("Enter a positive whole quantity."), true);
			return;
		}
		values.qty = qty;
		var id = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : null;
		try {
			if (!id) throw new Error('no uuid');
			window.sessionStorage.setItem('ill-line-draft:' + id, JSON.stringify({ schedule: schedule_name, metadata: values, savedAt: Date.now() }));
			window.sessionStorage.setItem('ill-line-draft-last:' + schedule_name, id);
		} catch (_) {
			show(scheduleText("Browser storage is unavailable. Allow session storage to preserve this draft."), true);
			return;
		}
		var params = new URLSearchParams({ category: 'Linear Fixture', schedule: schedule_name, pn: partNumber, draft: id });
		SchedulePartNumber.navigate('/portal/configure?' + params.toString());
	}

	function explain(message) {
		if (message.status === 'ambiguous') {
			var names = (message.candidates || []).map(function (row) { return row.label; }).join(', ');
			return scheduleText("This part number fits several products: {0}. Choose the product below.").replace('{0}', names);
		}
		var reasons = (message.unmatched || []).map(function (row) { return row.answer + ' (' + row.reason + ')'; }).join(', ');
		return message.error || scheduleText("No product matches this part number.") + (reasons ? ' ' + reasons : '');
	}

	function decode() {
		var value = String($('#addLinePartNumber').val() || '').trim();
		if (!value) {
			show(scheduleText("Enter a fixture part number."), true);
			return;
		}
		var $button = $('#addLinePartNumberGo').prop('disabled', true);
		show(scheduleText("Looking up…"), false);
		frappe.call({
			method: METHOD,
			type: 'GET',
			args: { part_number: value, schedule: schedule_name },
			callback: function (r) {
				var message = r.message || {};
				if (message.success && message.template) {
					show(scheduleText("Opening the configurator…"), false);
					open(message.part_number || value);
					return;
				}
				show(explain(message), true);
			},
			error: function () { show(scheduleText("Could not look up this part number."), true); },
			always: function () { $button.prop('disabled', false); },
		});
	}

	if (scheduleContext.part_number_decode) {
		$(document).on('click', '#addLinePartNumberGo', decode);
		$(document).on('keydown', '#addLinePartNumber', function (event) {
			if (event.key === 'Enter') {
				event.preventDefault();
				decode();
			}
		});
	}

	return {
		decode: decode,
		navigate: function (href) { window.location.href = href; },
	};
})();
