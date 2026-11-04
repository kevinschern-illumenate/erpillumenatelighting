/**
 * Saved configuration presets (plan 3.6).
 *
 * On /portal/configure (the page renders #ill-config-presets only when the ill_portal_presets
 * kill switch is on) the first configurator with an exportRequest() gets a "Save as preset"
 * control. The current request is saved under a label, privately or shared with the dealer's
 * company. The server strips prices, re-checks the template and replaces a preset of the same
 * label. All text is set with .text()/.val(); nothing here builds HTML from user data.
 */
(function (root) {
	'use strict';
	var IllConfigurator = root.IllConfigurator = root.IllConfigurator || {};
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.presets.save_preset';
	var active = null;

	function $(value) { return root.jQuery(value); }
	function text(value) { return root.__ ? root.__(value) : value; }

	function marker() {
		var node = root.document && root.document.getElementById('ill-config-presets');
		if (!node) return null;
		try {
			var parsed = JSON.parse(node.textContent || '{}');
			return parsed && parsed.enabled ? parsed : null;
		} catch (_) { return null; }
	}

	function PresetSaver(instance, options) {
		this.instance = instance;
		this.context = instance.context || {};
		this.canShare = !!options.can_share;
		this.render();
		this.bind();
	}

	PresetSaver.prototype.render = function () {
		var id = 'illPresetLabel' + (this.instance.instanceId || '');
		this.$panel = $('<div class="ill-preset-save mb-2"></div>');
		this.$toggle = $('<button type="button" class="btn btn-sm btn-outline-secondary ill-preset-toggle"></button>')
			.text(text('Save as preset')).attr('aria-expanded', 'false');
		this.$form = $('<form class="ill-preset-form form-inline d-none mt-2" novalidate></form>');
		this.$label = $('<input type="text" class="form-control form-control-sm mr-2 ill-preset-label" maxlength="140" autocomplete="off">')
			.attr('id', id).attr('placeholder', text('Preset name'));
		this.$form.append($('<label class="sr-only"></label>').attr('for', id).text(text('Preset name')), this.$label);
		if (this.canShare) {
			this.$share = $('<input type="checkbox" class="form-check-input ill-preset-share">').attr('id', id + 'Share');
			this.$form.append($('<div class="form-check mr-2"></div>').append(
				this.$share, $('<label class="form-check-label"></label>').attr('for', id + 'Share').text(text('Share with my company'))));
		}
		this.$submit = $('<button type="submit" class="btn btn-sm btn-primary mr-1"></button>').text(text('Save preset'));
		this.$cancel = $('<button type="button" class="btn btn-sm btn-link ill-preset-cancel"></button>').text(text('Cancel'));
		this.$form.append(this.$submit, this.$cancel);
		this.$status = $('<span class="ill-preset-status small ml-2" role="status" aria-live="polite"></span>');
		this.$panel.append(this.$toggle, this.$status, this.$form);
		var $root = this.instance.$root;
		var host = $root[0] === root.document ? $('body') : $root;
		host.prepend(this.$panel);
	};

	PresetSaver.prototype.status = function (message, failed) {
		this.$status.text(message || '').toggleClass('text-danger', !!failed).toggleClass('text-muted', !failed);
	};

	PresetSaver.prototype.toggle = function (open) {
		this.$form.toggleClass('d-none', !open);
		this.$toggle.attr('aria-expanded', open ? 'true' : 'false');
		if (open) this.$label.trigger('focus');
	};

	PresetSaver.prototype.bind = function () {
		var self = this;
		this.$toggle.on('click', function () { self.toggle(self.$form.hasClass('d-none')); });
		this.$cancel.on('click', function () { self.toggle(false); });
		this.$form.on('submit', function (event) {
			event.preventDefault();
			self.save();
		});
	};

	PresetSaver.prototype.save = function () {
		var self = this;
		var label = String(this.$label.val() || '').trim();
		if (!label) {
			this.status(text('Name the preset.'), true);
			return;
		}
		var request = null;
		try { request = this.instance.exportRequest(); } catch (_) { request = null; }
		if (!request || !request.family) {
			this.status(text('Choose a product before saving a preset.'), true);
			return;
		}
		this.$submit.prop('disabled', true);
		this.status(text('Saving preset…'), false);
		root.frappe.call({
			method: METHOD,
			type: 'POST',
			args: {
				label: label,
				request: JSON.stringify(request),
				shared_with_company: this.$share && this.$share.is(':checked') ? 1 : 0,
				schedule_name: this.context.schedule_name || null,
			},
			callback: function (r) {
				var message = r.message || {};
				if (message.disabled) {
					self.$panel.addClass('d-none');
					return;
				}
				if (message.success) {
					self.toggle(false);
					self.status(text('Saved preset {0}.').replace('{0}', (message.preset || {}).label || label), false);
				}
			},
			error: function () { self.status(text('Could not save the preset.'), true); },
			always: function () { self.$submit.prop('disabled', false); },
		});
	};

	IllConfigurator.attachPresets = function (instance) {
		var options = marker();
		if (!options || !instance || instance.destroyed || typeof instance.exportRequest !== 'function') return null;
		if (active && !active.instance.destroyed) return null;
		active = new PresetSaver(instance, options);
		instance._presetSaver = active;
		return active;
	};
	IllConfigurator.PresetSaver = PresetSaver;
})(window);
