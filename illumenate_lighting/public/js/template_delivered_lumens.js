/* Delivered Lumens on the fixture template (owner, 2026-11-13): only the lens columns the
   template has are shown. A lens the template does not have is empty in every row; its column
   is hidden here. A dash in a shown column means that lens does not reach the output. */
(function () {
    const LENSES = ['white', 'frosted', 'clear', 'black'];

    function showLensColumns(frm) {
        const field = frm.fields_dict && frm.fields_dict.delivered_lumens;
        if (!field || !field.grid) return;
        const rows = frm.doc.delivered_lumens || [];
        LENSES.forEach(lens => {
            const used = rows.some(row => row[lens]);
            field.grid.update_docfield_property(lens, 'in_list_view', used ? 1 : 0);
            field.grid.update_docfield_property(lens, 'hidden', used ? 0 : 1);
        });
        field.grid.visible_columns = null;
        field.grid.refresh();
    }

    window.illDeliveredLumens = {showLensColumns};
    frappe.ui.form.on('ilL-Fixture-Template', {refresh: showLensColumns});
})();
