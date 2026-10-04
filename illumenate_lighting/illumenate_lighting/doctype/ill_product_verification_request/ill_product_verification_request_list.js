frappe.listview_settings['ilL-Product-Verification-Request'] = {
  get_indicator(doc) {
    const colors = {REQUESTED: 'orange', UNDER_REVIEW: 'blue', INFORMATION_NEEDED: 'yellow', VERIFIED: 'green', NOT_FEASIBLE: 'red', CANCELLED: 'gray'};
    return [doc.state.replaceAll('_', ' '), colors[doc.state], 'state,=,' + doc.state];
  }
};
