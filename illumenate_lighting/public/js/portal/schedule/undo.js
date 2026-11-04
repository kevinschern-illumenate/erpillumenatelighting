// Schedule detail page (plan 3.10): a 10-second "Undo" after deleting, moving or bulk-editing lines.
// The server keeps what the action removed or overwrote in a short-lived receipt and returns
// {token, expires_in, action, count} as `undo`. Every action reloads the page, so the offer is kept in
// sessionStorage and the toast appears after the reload for whatever is left of the window. Undo
// calls line_undo.undo_line_action, which re-checks access and editability. Text-only DOM.
var ScheduleUndo = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.line_undo.undo_line_action';
	var timer = null;

	function storageKey() { return 'ill-undo:' + (scheduleContext.schedule_name || ''); }

	function enabled() { return !!scheduleContext.undo; }

	function format(text) {
		var values = Array.prototype.slice.call(arguments, 1);
		return text.replace(/\{(\d)\}/g, function (match, index) {
			return values[index] === undefined ? match : String(values[index]);
		});
	}

	function pending() {
		try {
			var entry = JSON.parse(sessionStorage.getItem(storageKey()) || 'null');
			return entry && entry.token && entry.until > Date.now() ? entry : null;
		} catch (e) {
			return null;
		}
	}

	function clear() {
		try { sessionStorage.removeItem(storageKey()); } catch (e) {}
	}

	// Remember an offer from a successful action, to show once the page reloads.
	function offer(receipt) {
		if (!enabled() || !receipt || typeof receipt.token !== 'string' || !receipt.token) return false;
		var seconds = Math.max(1, Math.min(Number(receipt.expires_in) || 10, 30));
		try {
			sessionStorage.setItem(storageKey(), JSON.stringify({
				token: receipt.token,
				action: receipt.action,
				count: Number(receipt.count) || 1,
				until: Date.now() + seconds * 1000,
			}));
			return true;
		} catch (e) {
			return false;
		}
	}

	function describe(entry) {
		if (entry.action === 'move') return format(scheduleText("Moved {0} line(s)."), entry.count);
		if (entry.action === 'update') return format(scheduleText("Updated {0} line(s)."), entry.count);
		return format(scheduleText("Deleted {0} line(s)."), entry.count);
	}

	function toast() {
		var box = document.getElementById('scheduleUndoToast');
		if (box) return box;
		box = document.createElement('div');
		box.id = 'scheduleUndoToast';
		box.className = 'ill-undo-toast';
		box.setAttribute('role', 'status');
		box.setAttribute('aria-live', 'polite');
		(document.querySelector('.ill-page--schedule') || document.body).appendChild(box);
		return box;
	}

	function hide() {
		if (timer) clearInterval(timer);
		timer = null;
		var box = document.getElementById('scheduleUndoToast');
		if (box) {
			box.hidden = true;
			box.textContent = '';
		}
	}

	function element(tag, className, text) {
		var node = document.createElement(tag);
		node.className = className;
		if (text) node.textContent = text;
		return node;
	}

	function tick() {
		var entry = pending();
		var countdown = document.querySelector('#scheduleUndoToast .ill-undo-countdown');
		if (!entry) {
			clear();
			hide();
			return false;
		}
		if (countdown) countdown.textContent = format(scheduleText("{0}s"), Math.ceil((entry.until - Date.now()) / 1000));
		return true;
	}

	function show(entry) {
		var box = toast();
		box.textContent = '';
		box.appendChild(element('span', 'ill-undo-text', describe(entry)));
		var button = element('button', 'btn btn-sm btn-light ill-undo-button', scheduleText("Undo"));
		button.type = 'button';
		button.addEventListener('click', function () { undo(button); });
		box.appendChild(button);
		box.appendChild(element('span', 'ill-undo-countdown', ''));
		var dismiss = element('button', 'btn btn-sm btn-link ill-undo-dismiss', scheduleText("Dismiss"));
		dismiss.type = 'button';
		dismiss.addEventListener('click', function () { clear(); hide(); });
		box.appendChild(dismiss);
		box.hidden = false;
		tick();
		if (timer) clearInterval(timer);
		timer = setInterval(tick, 1000);
	}

	function undo(button) {
		var entry = pending();
		if (!entry) {
			clear();
			hide();
			return;
		}
		if (button) button.disabled = true;
		var restored = false;
		frappe.call({
			method: METHOD,
			type: 'POST',
			args: { token: entry.token },
			callback: function (r) {
				if (r && r.message && r.message.success) {
					restored = true;
					ScheduleUndo.reload();
				}
			},
			always: function () {
				clear();
				if (!restored) hide();
			},
		});
	}

	function init() {
		if (!enabled()) return;
		var entry = pending();
		if (entry) show(entry);
		else clear();
	}

	init();

	return {
		offer: offer,
		pending: pending,
		show: show,
		hide: hide,
		tick: tick,
		undo: undo,
		init: init,
		reload: function () { window.location.reload(); },
	};
})();
