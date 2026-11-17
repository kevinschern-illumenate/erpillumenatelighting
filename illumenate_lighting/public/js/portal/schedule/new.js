// Schedule detail page (new). Extracted verbatim from templates/pages/schedule.html (plan 2.1).
// Handle create schedule form submission
$('#createScheduleForm').on('submit', function(e) {
	e.preventDefault();

	var form = $(this);
	var submitBtn = form.find('button[type="submit"]');

	// Prevent double submission
	if (submitBtn.prop('disabled')) {
		return;
	}

	submitBtn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Creating...');

	var data = {
		schedule_name: form.find('[name="schedule_name"]').val(),
		ill_project: form.find('[name="ill_project"]').val(),
		notes: form.find('[name="notes"]').val()
	};

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.create_schedule',
		args: {
			schedule_data: data
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				frappe.msgprint({
					title: 'Success',
					indicator: 'green',
					message: 'Schedule created successfully'
				});
				// Redirect to the new schedule
				window.location.href = '/portal/schedules/' + r.message.schedule_name;
			} else {
				frappe.msgprint({
					title: 'Error',
					indicator: 'red',
					message: r.message.error || 'Error creating schedule'
				});
				submitBtn.prop('disabled', false).html('<i class="fa fa-plus" aria-hidden="true"></i> Create Schedule');
			}
		},
		error: function() {
			submitBtn.prop('disabled', false).html('<i class="fa fa-plus" aria-hidden="true"></i> Create Schedule');
		}
	});
});
