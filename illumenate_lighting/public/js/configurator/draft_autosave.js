/**
 * Durable configurator drafts (plan 3.1).
 *
 * On /portal/configure (the page renders #ill-draft-autosave only when the dealer can save to
 * the schedule and the ill_portal_durable_drafts kill switch is on) the first configurator with
 * an exportRequest() saves its request to the server, debounced, and shows
 * "Saving draft… / Draft saved / Unsaved changes". When a draft exists for the same user,
 * schedule, line and product type, a prompt offers to restore it. Restoring reuses the
 * existing ?resume= view-switch path, so nothing is saved to the schedule until the dealer
 * confirms. sessionStorage remains the fallback when the server cannot be reached.
 */
(function (root) {
	'use strict';
	var IllConfigurator = root.IllConfigurator = root.IllConfigurator || {};
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.line_drafts.';
	var IGNORED = ['projectSelect', 'scheduleSelect', 'lineSelect'];
	var active = null;

	function $(value) { return root.jQuery(value); }
	function call(args) { return root.frappe.call(args); }

	function text(value) { return root.__ ? root.__(value) : value; }

	function marker() {
		var node = root.document && root.document.getElementById('ill-draft-autosave');
		if (!node) return null;
		try {
			var parsed = JSON.parse(node.textContent || '{}');
			return parsed && parsed.enabled ? parsed : null;
		} catch (_) { return null; }
	}

	function storage() {
		try { return root.sessionStorage; } catch (_) { return null; }
	}

	function formatTime(value) {
		var date = value instanceof Date ? value : new Date(String(value).replace(' ', 'T'));
		if (isNaN(date.getTime())) return String(value || '');
		return date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
	}

	function DraftAutosave(instance, options) {
		this.instance = instance;
		this.context = instance.context || {};
		this.productType = options.product_type || ((instance.exportRequest() || {}).family) || '';
		this.lineKey = this.context.line_key || '';
		this.localKey = 'ill-config-draft:' + [this.context.schedule_name, this.lineKey, this.productType].join('|');
		this.timer = null;
		this.saving = false;
		this.pending = false;
		this.state = '';
		this.namespace = '.illDraft' + (instance.instanceId || '');
		this.render();
		this.bind();
		this.offer();
	}

	DraftAutosave.prototype.args = function () {
		return { schedule_name: this.context.schedule_name, product_type: this.productType, line_key: this.lineKey || null };
	};

	DraftAutosave.prototype.render = function () {
		var $root = this.instance.$root;
		this.$status = $('<div class="ill-draft-status small text-muted mb-2" role="status" aria-live="polite"></div>');
		this.$prompt = $('<div class="ill-draft-prompt alert alert-info d-none" role="region"></div>');
		this.$prompt.attr('aria-label', text('Saved draft'));
		var host = $root[0] === root.document ? $('body') : $root;
		host.prepend(this.$status).prepend(this.$prompt);
	};

	DraftAutosave.prototype.setState = function (state, when) {
		this.state = state;
		var labels = {
			saving: text('Saving draft…'),
			saved: text('Draft saved'),
			unsaved: text('Unsaved changes'),
			local: text('Draft kept in this browser only'),
		};
		var label = labels[state] || '';
		if (state === 'saved' && when) label += ' · ' + formatTime(when);
		this.$status.text(label).attr('data-state', state);
	};

	DraftAutosave.prototype.bind = function () {
		var self = this;
		this.instance.$root.on('input' + this.namespace + ' change' + this.namespace, 'input, select, textarea', function (event) {
			if (!(event.originalEvent || event.illUserSelection)) return;
			if (self.instance.isPopulating || self.instance._applyingRestore || self.instance.destroyed) return;
			if (IGNORED.indexOf(this.getAttribute('data-ill-original-id') || this.id) >= 0) return;
			self.schedule();
		});
		if (this.instance._disposers) this.instance._disposers.push(function () { self.dispose(); });
	};

	DraftAutosave.prototype.schedule = function () {
		var self = this;
		if (this.finished || this.disposed) return;
		this.setState('unsaved');
		root.clearTimeout(this.timer);
		this.timer = root.setTimeout(function () { self.save(); }, DraftAutosave.debounceMs);
	};

	DraftAutosave.prototype.payload = function () {
		return { request: this.instance.exportRequest(), metadata: this.context.draft || {} };
	};

	DraftAutosave.prototype.keepLocal = function (draft) {
		var store = storage();
		if (!store) return false;
		try {
			store.setItem(this.localKey, JSON.stringify({ draft: draft, savedAt: Date.now() }));
			return true;
		} catch (_) { return false; }
	};

	DraftAutosave.prototype.save = function () {
		var self = this;
		if (this.instance.destroyed || this.disposed || this.finished) return;
		if (this.saving) { this.pending = true; return; }
		var draft;
		try { draft = this.payload(); } catch (_) { return; }
		this.saving = true;
		this.setState('saving');
		var args = this.args();
		args.draft = JSON.stringify(draft);
		call({
			method: METHOD + 'save_draft',
			type: 'POST',
			args: args,
			callback: function (r) {
				var message = r && r.message;
				if (message && message.success) {
					var store = storage();
					try { if (store) store.removeItem(self.localKey); } catch (_) {}
					self.setState('saved', message.saved_on ? message.saved_on : new Date());
				} else if (message && message.disabled) {
					self.dispose();
				} else self.setState(self.keepLocal(draft) ? 'local' : 'unsaved');
			},
			error: function () { self.setState(self.keepLocal(draft) ? 'local' : 'unsaved'); },
			always: function () {
				self.saving = false;
				// A save that was in flight when the line was saved must not leave a stale draft behind.
				if (self.finished) { self.sendDiscard(); return; }
				if (self.pending) { self.pending = false; self.schedule(); }
			},
		});
	};

	DraftAutosave.prototype.offer = function () {
		var self = this;
		if (new URLSearchParams(root.location.search).get('resume')) return;
		call({
			method: METHOD + 'get_draft',
			type: 'GET',
			args: this.args(),
			callback: function (r) {
				var message = (r && r.message) || {};
				if (message.draft && message.draft.request) self.prompt(message.draft, message.saved_on);
				else self.offerLocal();
			},
			error: function () { self.offerLocal(); },
		});
	};

	DraftAutosave.prototype.offerLocal = function () {
		var store = storage();
		if (!store) return;
		try {
			var local = JSON.parse(store.getItem(this.localKey) || 'null');
			if (local && local.draft && local.draft.request && Date.now() - local.savedAt < 86400000) {
				this.prompt(local.draft, new Date(local.savedAt));
			}
		} catch (_) {}
	};

	DraftAutosave.prototype.prompt = function (draft, savedOn) {
		var self = this;
		var $message = $('<span class="mr-2"></span>').text(text('You have a saved draft from') + ' ' + formatTime(savedOn) + '.');
		var $restore = $('<button type="button" class="btn btn-sm btn-primary mr-2 ill-draft-restore"></button>').text(text('Restore draft'));
		var $discard = $('<button type="button" class="btn btn-sm btn-outline-secondary ill-draft-discard"></button>').text(text('Discard'));
		$restore.on('click', function () { self.restore(draft); });
		$discard.on('click', function () { self.discard(false); self.$prompt.addClass('d-none').empty(); });
		this.$prompt.empty().append($message, $restore, $discard).removeClass('d-none');
	};

	DraftAutosave.prototype.restore = function (draft) {
		var store = storage();
		if (!store || !root.crypto || !root.crypto.randomUUID) {
			root.frappe.msgprint(text('Allow session storage to restore this draft.'));
			return;
		}
		var url = new URL(root.location.href);
		var id = root.crypto.randomUUID();
		try {
			// expected_modified stays null so the save uses the schedule revision this page loaded.
			store.setItem('ill-config-view:' + id, JSON.stringify({ request: draft.request, schedule: this.context.schedule_name, expected_modified: null, savedAt: Date.now() }));
			var metadata = draft.metadata || {};
			if (!url.searchParams.get('draft') && Object.keys(metadata).length) {
				var draftId = root.crypto.randomUUID();
				store.setItem('ill-line-draft:' + draftId, JSON.stringify({ schedule: this.context.schedule_name, metadata: metadata, savedAt: Date.now() }));
				url.searchParams.set('draft', draftId);
			}
		} catch (_) {
			root.frappe.msgprint(text('Allow session storage to restore this draft.'));
			return;
		}
		url.searchParams.set('resume', id);
		if (draft.request.template) url.searchParams.set('template', draft.request.template);
		DraftAutosave.navigate(url.toString());
	};

	// finished=true after a successful save to the schedule (autosave stops); the prompt's
	// Discard keeps autosaving later edits. keepalive lets the request finish during a redirect.
	DraftAutosave.prototype.discard = function (finished) {
		if (finished) {
			this.finished = true;
			this.pending = false;
			root.clearTimeout(this.timer);
		}
		var store = storage();
		try { if (store) store.removeItem(this.localKey); } catch (_) {}
		this.sendDiscard();
	};

	DraftAutosave.prototype.sendDiscard = function () {
		var args = this.args();
		if (root.fetch) {
			root.fetch('/api/method/' + METHOD + 'discard_draft', {
				method: 'POST',
				keepalive: true,
				credentials: 'same-origin',
				headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Frappe-CSRF-Token': (root.frappe && root.frappe.csrf_token) || '' },
				body: JSON.stringify(args),
			}).catch(function () {});
		} else call({ method: METHOD + 'discard_draft', type: 'POST', args: args });
	};

	DraftAutosave.prototype.dispose = function () {
		if (this.disposed) return;
		this.disposed = true;
		root.clearTimeout(this.timer);
		this.instance.$root.off(this.namespace);
		this.$status.remove();
		this.$prompt.remove();
		if (this.instance._draftAutosave === this) this.instance._draftAutosave = null;
		if (active === this) active = null;
	};

	IllConfigurator.attachDraftAutosave = function (instance) {
		var options = marker();
		if (!options || !instance || instance.destroyed || typeof instance.exportRequest !== 'function') return null;
		if (!instance.context || !instance.context.schedule_name) return null;
		if (active && !active.disposed && !active.instance.destroyed) return null;
		active = new DraftAutosave(instance, options);
		instance._draftAutosave = active;
		return active;
	};
	DraftAutosave.debounceMs = 2000;
	DraftAutosave.navigate = function (href) { root.location.href = href; };
	IllConfigurator.DraftAutosave = DraftAutosave;
})(window);
