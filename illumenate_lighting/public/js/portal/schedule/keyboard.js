// Schedule detail page (plan 3.13): keyboard shortcuts for power users.
//   /            focus the line filter          n        add a line
//   ?            show or hide the shortcut help Esc      close the help or an open dialog
//   ↑ / ↓        move between line rows         Alt+↑/↓  move the focused line up or down
// Shortcuts never fire while typing in a field, a select or contenteditable, or with Ctrl/⌘ held.
// Alt+↑/↓ is the keyboard alternative to drag reorder and uses the same endpoint (moveScheduleLine).
var ScheduleKeyboard = (function () {
	var FOCUS_KEY = 'ill-kbd-focus:' + (scheduleContext.schedule_name || '');
	var ROWS = '.fixture-lines-table > tbody > tr[data-line-idx]';

	function enabled() { return !!scheduleContext.keyboard_shortcuts; }

	function typing(target) {
		if (!target || target.nodeType !== 1) return false;
		var tag = target.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
		if (target.isContentEditable) return true;
		var editable = target.closest && target.closest('[contenteditable]');
		return !!(editable && editable.getAttribute('contenteditable') !== 'false');
	}

	function visible(node) { return !!node && !node.hidden && node.style.display !== 'none'; }

	function rows() {
		return Array.prototype.slice.call(document.querySelectorAll(ROWS)).filter(visible);
	}

	function help() { return document.getElementById('scheduleShortcutsHelp'); }

	function helpOpen() { var box = help(); return !!box && !box.hidden; }

	var lastFocus = null;

	function toggleHelp(show) {
		var box = help();
		if (!box) return false;
		var open = show === undefined ? box.hidden : show;
		if (open) {
			lastFocus = document.activeElement;
			box.hidden = false;
			var close = box.querySelector('[data-shortcuts-close]');
			if (close) close.focus();
		} else {
			box.hidden = true;
			if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
			lastFocus = null;
		}
		return true;
	}

	function openModals() {
		return Array.prototype.slice.call(document.querySelectorAll('.modal.show'));
	}

	function closeDialogs() {
		if (helpOpen()) return toggleHelp(false);
		var modals = openModals();
		if (!modals.length) return false;
		var modal = modals[modals.length - 1];
		if (window.jQuery && window.jQuery.fn && window.jQuery.fn.modal) window.jQuery(modal).modal('hide');
		else modal.classList.remove('show');
		return true;
	}

	function focusFilter() {
		var input = document.getElementById('lineFilter');
		if (!input) return false;
		input.focus();
		if (typeof input.select === 'function') input.select();
		return true;
	}

	function addLine() {
		var buttons = document.querySelectorAll('[data-target="#addLineModal"]');
		for (var i = 0; i < buttons.length; i++) {
			if (!buttons[i].disabled && visible(buttons[i])) {
				buttons[i].click();
				return true;
			}
		}
		return false;
	}

	function currentRow(target) {
		return target && target.closest ? target.closest(ROWS) : null;
	}

	function focusRow(row, likeHandle) {
		var handle = likeHandle ? row.querySelector('.drag-handle-btn') : null;
		if (handle) {
			handle.focus();
			return;
		}
		if (!row.hasAttribute('tabindex')) row.setAttribute('tabindex', '-1');
		row.focus();
	}

	function step(target, delta) {
		var row = currentRow(target);
		if (!row) return false;
		var list = rows();
		var next = list[list.indexOf(row) + delta];
		if (next) focusRow(next, target.classList && target.classList.contains('drag-handle-btn'));
		return true;
	}

	function move(target, delta) {
		var row = currentRow(target);
		if (!row || !row.querySelector('.drag-handle-btn') || typeof moveScheduleLine !== 'function') return false;
		var from = parseInt(row.getAttribute('data-line-idx'), 10);
		var all = Array.prototype.slice.call(document.querySelectorAll(ROWS));
		var neighbour = all[all.indexOf(row) + delta];
		if (!neighbour || isNaN(from)) return true;
		try { sessionStorage.setItem(FOCUS_KEY, row.getAttribute('data-line-key') || ''); } catch (e) {}
		moveScheduleLine(from, parseInt(neighbour.getAttribute('data-line-idx'), 10));
		return true;
	}

	// After a keyboard move the page reloads; put focus back on the moved line's handle.
	function restoreFocus() {
		var key = null;
		try {
			key = sessionStorage.getItem(FOCUS_KEY);
			sessionStorage.removeItem(FOCUS_KEY);
		} catch (e) {}
		if (!key) return;
		var row = rows().filter(function (node) { return node.getAttribute('data-line-key') === key; })[0];
		if (row) focusRow(row, true);
	}

	function filter(text) {
		var query = String(text || '').trim().toLowerCase();
		var shown = 0;
		Array.prototype.slice.call(document.querySelectorAll(ROWS)).forEach(function (row) {
			var match = !query || row.textContent.toLowerCase().indexOf(query) !== -1;
			row.hidden = !match;
			if (match) shown += 1;
		});
		var status = document.getElementById('lineFilterStatus');
		if (status) status.textContent = query ? scheduleText("{0} line(s) shown").replace('{0}', String(shown)) : '';
		return shown;
	}

	function onKeydown(event) {
		if (!enabled() || event.defaultPrevented || event.ctrlKey || event.metaKey) return;
		var target = event.target;
		if (event.key === 'Escape') {
			if (target && target.id === 'lineFilter' && target.value) {
				target.value = '';
				filter('');
				event.preventDefault();
				return;
			}
			if (typing(target) && !helpOpen()) return;
			if (closeDialogs()) event.preventDefault();
			return;
		}
		if (typing(target)) return;
		if (helpOpen() && event.key !== '?') return;
		var handled = false;
		if (event.altKey) {
			if (event.key === 'ArrowUp') handled = move(target, -1);
			else if (event.key === 'ArrowDown') handled = move(target, 1);
		} else if (event.key === '/') handled = focusFilter();
		else if (event.key === '?') handled = toggleHelp();
		else if ((event.key === 'n' || event.key === 'N') && !event.shiftKey && !openModals().length) handled = addLine();
		else if (event.key === 'ArrowUp') handled = step(target, -1);
		else if (event.key === 'ArrowDown') handled = step(target, 1);
		if (handled) event.preventDefault();
	}

	document.addEventListener('keydown', onKeydown);
	document.addEventListener('input', function (event) {
		if (event.target && event.target.id === 'lineFilter') filter(event.target.value);
	});
	document.addEventListener('click', function (event) {
		var target = event.target && event.target.closest ? event.target.closest('[data-shortcuts-close], [data-shortcuts-open]') : null;
		if (target) toggleHelp(target.hasAttribute('data-shortcuts-open'));
	});
	if (enabled()) restoreFocus();

	return { typing: typing, filter: filter, toggleHelp: toggleHelp, restoreFocus: restoreFocus, onKeydown: onKeydown };
})();
