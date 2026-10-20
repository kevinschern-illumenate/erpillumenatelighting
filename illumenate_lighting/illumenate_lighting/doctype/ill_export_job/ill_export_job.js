// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Export-Job", {
	refresh(frm) {
		// Packet issues are logged here for staff; the customer's PDF never shows them.
		if (frm.doc.issue_log) {
			const errors = frm.doc.issue_count || 0;
			frm.set_intro(
				errors
					? __(
							"{0} issue(s) kept documents out of this packet. The customer received it with those left blank. See Submittal Issues below.",
							[errors]
					  )
					: __("This packet was generated with warnings. See Submittal Issues below."),
				errors ? "orange" : "blue"
			);
		}
	},
});
