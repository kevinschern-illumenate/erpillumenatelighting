// ilLumenate Lighting - shared Quotation/Sales Order configurator shell

(function() {
	const root = window.illumenate_lighting = window.illumenate_lighting || {};
	const api = 'illumenate_lighting.illumenate_lighting.api.quote_order_configurator.';
	const productTypes = ['Linear Fixture', 'LED Tape', 'LED Neon'];

	function canConfigure(frm) {
		return !frm.is_new() && !frm.is_read_only() && frm.doc.docstatus === 0;
	}

	function addButtons(frm) {
		if (!canConfigure(frm)) {
			return;
		}

		frm.add_custom_button(__('Configure Product'), function() {
			showDialog(frm);
		}, __('Tools'));
	}

	function showDialog(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __('Configure Product'),
			fields: [
				{
					fieldname: 'product_type',
					fieldtype: 'Select',
					label: __('Product Type'),
					options: [''].concat(productTypes).join('\n'),
					reqd: 1,
					onchange: function() {
						dialog.set_value('configured_fixture', null);
						dialog.set_value('configured_tape_neon', null);
						renderPreview(dialog, null);
						refreshDialogFields(dialog);
					}
				},
				{
					fieldname: 'qty',
					fieldtype: 'Float',
					label: __('Qty'),
					default: 1,
					reqd: 1
				},
				{ fieldtype: 'Section Break' },
				{
					fieldname: 'configured_fixture',
					fieldtype: 'Link',
					label: __('Configured Fixture'),
					options: 'ilL-Configured-Fixture',
					depends_on: "eval:doc.product_type=='Linear Fixture'",
					onchange: function() {
						loadPreview(dialog);
					}
				},
				{
					fieldname: 'configured_tape_neon',
					fieldtype: 'Link',
					label: __('Configured Tape/Neon'),
					options: 'ilL-Configured-Tape-Neon',
					depends_on: "eval:doc.product_type=='LED Tape'||doc.product_type=='LED Neon'",
					onchange: function() {
						loadPreview(dialog);
					}
				},
				{ fieldtype: 'Section Break' },
				{
					fieldname: 'bom_preview',
					fieldtype: 'HTML',
					options: '<div class="ill-configurator-preview"></div>'
				}
			]
		});

		dialog.set_primary_action(__('Apply to Row'), function() {
			applyConfiguredProduct(frm, dialog);
		});

		dialog.show();
	}

	function selectedItemRowName(frm) {
		const selected = frm.get_selected ? frm.get_selected() : null;
		if (!selected || !selected.items || selected.items.length !== 1) {
			return null;
		}
		return selected.items[0];
	}

	function refreshDialogFields(dialog) {
		['configured_fixture', 'configured_tape_neon'].forEach(function(fieldname) {
			if (dialog.fields_dict[fieldname] && dialog.fields_dict[fieldname].refresh) {
				dialog.fields_dict[fieldname].refresh();
			}
		});
	}

	function getDialogArgs(dialog) {
		const productType = dialog.get_value('product_type');
		return {
			product_type: productType,
			configured_fixture: productType === 'Linear Fixture' ? dialog.get_value('configured_fixture') : null,
			configured_tape_neon: productType === 'LED Tape' || productType === 'LED Neon'
				? dialog.get_value('configured_tape_neon')
				: null
		};
	}

	function loadPreview(dialog) {
		const args = getDialogArgs(dialog);
		if (!args.product_type || (!args.configured_fixture && !args.configured_tape_neon)) {
			renderPreview(dialog, null);
			return;
		}

		renderPreview(dialog, { loading: true });
		frappe.call({
			method: api + 'get_bom_preview',
			args: args,
			callback: function(response) {
				renderPreview(dialog, response.message);
			}
		});
	}

	function renderPreview(dialog, preview) {
		const wrapper = dialog.fields_dict.bom_preview.$wrapper.find('.ill-configurator-preview');
		if (!preview) {
			wrapper.empty();
			return;
		}

		if (preview.loading) {
			wrapper.html('<div class="text-muted small">' + __('Loading BOM...') + '</div>');
			return;
		}

		const messages = (preview.messages || []).map(function(message) {
			return '<div class="text-muted small">' + escapeHtml(message.text || '') + '</div>';
		}).join('');

		if (!preview.items || !preview.items.length) {
			wrapper.html(messages);
			return;
		}

		const rows = preview.items.map(function(item) {
			return '<tr>' +
				'<td>' + escapeHtml(item.item_code || '') + '</td>' +
				'<td>' + escapeHtml(item.item_name || '') + '</td>' +
				'<td class="text-right">' + escapeHtml(String(item.qty || '')) + '</td>' +
				'<td>' + escapeHtml(item.uom || '') + '</td>' +
			'</tr>';
		}).join('');

		wrapper.html(
			messages +
			'<div class="table-responsive" style="max-height: 260px; overflow:auto;">' +
				'<table class="table table-bordered table-condensed">' +
					'<thead><tr>' +
						'<th>' + __('Item') + '</th>' +
						'<th>' + __('Name') + '</th>' +
						'<th class="text-right">' + __('Qty') + '</th>' +
						'<th>' + __('UOM') + '</th>' +
					'</tr></thead>' +
					'<tbody>' + rows + '</tbody>' +
				'</table>' +
			'</div>'
		);
	}

	function applyConfiguredProduct(frm, dialog) {
		const values = dialog.get_values();
		if (!values) {
			return;
		}

		const args = getDialogArgs(dialog);
		if (args.product_type === 'Linear Fixture' && !args.configured_fixture) {
			frappe.msgprint(__('Select a configured fixture.'));
			return;
		}
		if ((args.product_type === 'LED Tape' || args.product_type === 'LED Neon') && !args.configured_tape_neon) {
			frappe.msgprint(__('Select a configured tape/neon product.'));
			return;
		}

		frappe.call({
			method: api + 'apply_configured_product',
			args: Object.assign({}, args, {
				parent_doctype: frm.doctype,
				parent_name: frm.doc.name,
				row_name: selectedItemRowName(frm),
				qty: values.qty || 1
			}),
			freeze: true,
			freeze_message: __('Applying configured product...'),
			callback: function(response) {
				if (!response.message || !response.message.success) {
					return;
				}

				frappe.show_alert({
					message: __('Configured product applied: {0}', [response.message.item_code]),
					indicator: 'green'
				});
				dialog.hide();
				frm.reload_doc();
			}
		});
	}

	function escapeHtml(value) {
		return $('<div>').text(value || '').html();
	}

	root.quote_order_configurator = {
		add_buttons: addButtons,
		show_dialog: showDialog
	};
})();