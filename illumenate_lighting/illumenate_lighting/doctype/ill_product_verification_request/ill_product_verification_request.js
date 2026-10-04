frappe.ui.form.on('ilL-Product-Verification-Request', {
  refresh(frm) {
    if (frm.doc.schedule) frm.add_custom_button(__('Open schedule'), () => frappe.set_route('Form', 'ilL-Project-Fixture-Schedule', frm.doc.schedule));
    if (frm.doc.state === 'REQUESTED') frm.add_custom_button(__('Start review'), () => frm.set_value('state', 'UNDER_REVIEW').then(() => frm.save()));
    if (['UNDER_REVIEW', 'INFORMATION_NEEDED'].includes(frm.doc.state)) {
      for (const [label, state] of [['Mark verified', 'VERIFIED'], ['Not feasible', 'NOT_FEASIBLE']]) {
        frm.add_custom_button(__(label), () => frappe.prompt({fieldname: 'resolution', fieldtype: 'Small Text', label: __('Resolution'), reqd: 1}, (values) => frm.set_value({...values, state}).then(() => frm.save()), __(label)));
      }
    }
  }
});
