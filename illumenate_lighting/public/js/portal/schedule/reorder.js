// Schedule detail page (reorder). Extracted verbatim from templates/pages/schedule.html (plan 2.1).

// ─── Line Reordering (drag-and-drop) ─────────────────────────────────────────
var REORDER_SCROLL_KEY = 'scheduleScrollY:' + schedule_name;

function restoreScrollAfterReorder() {
	try {
		var y = sessionStorage.getItem(REORDER_SCROLL_KEY);
		if (y !== null) {
			sessionStorage.removeItem(REORDER_SCROLL_KEY);
			window.scrollTo(0, parseInt(y, 10) || 0);
		}
	} catch (e) { /* sessionStorage unavailable */ }
}

function moveScheduleLine(from_idx, to_idx) {
	if (from_idx === to_idx) {
		return;
	}
	try {
		sessionStorage.setItem(REORDER_SCROLL_KEY, String(window.scrollY));
	} catch (e) { /* ignore */ }

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.move_schedule_line',
		args: {
			schedule_name: schedule_name,
			from_idx: from_idx,
			to_idx: to_idx,
			line_key: lineRef(from_idx).line_key,
			to_line_key: lineRef(to_idx).line_key,
			expected_modified: scheduleModified
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				location.reload();
			} else {
				try { sessionStorage.removeItem(REORDER_SCROLL_KEY); } catch (e) {}
				if (window.ScheduleConflict && ScheduleConflict.handle(r)) return;
				frappe.msgprint(r.message && r.message.error ? r.message.error : 'Error moving line');
			}
		}
	});
}

function initLineReorder() {
	var tbody = document.querySelector('.fixture-lines-table tbody');
	if (!tbody) {
		return;
	}

	var dragState = null;
	var autoScrollTimer = null;

	function getRows() {
		return Array.prototype.slice.call(
			tbody.querySelectorAll('tr[data-line-idx]')
		);
	}

	function columnCount() {
		var first = tbody.querySelector('tr[data-line-idx]');
		return first ? first.children.length : 1;
	}

	function makeIndicator() {
		var tr = document.createElement('tr');
		tr.className = 'drop-indicator-row';
		var td = document.createElement('td');
		td.colSpan = columnCount();
		var line = document.createElement('div');
		line.className = 'drop-indicator-line';
		td.appendChild(line);
		tr.appendChild(td);
		return tr;
	}

	// Compute the target insertion index (0..rowCount) based on pointer Y.
	function computeTargetIndex(clientY) {
		var rows = getRows();
		for (var i = 0; i < rows.length; i++) {
			var rect = rows[i].getBoundingClientRect();
			var mid = rect.top + rect.height / 2;
			if (clientY < mid) {
				return i;
			}
		}
		return rows.length;
	}

	function positionIndicator(targetIndex) {
		var rows = getRows();
		if (targetIndex >= rows.length) {
			tbody.appendChild(dragState.indicator);
		} else {
			tbody.insertBefore(dragState.indicator, rows[targetIndex]);
		}
	}

	function handleAutoScroll(clientY) {
		var margin = 60;
		var speed = 0;
		if (clientY < margin) {
			speed = -Math.ceil((margin - clientY) / 6);
		} else if (clientY > window.innerHeight - margin) {
			speed = Math.ceil((clientY - (window.innerHeight - margin)) / 6);
		}
		if (speed !== 0) {
			if (!autoScrollTimer) {
				autoScrollTimer = setInterval(function() {
					window.scrollBy(0, dragState ? dragState.scrollSpeed : 0);
				}, 16);
			}
			dragState.scrollSpeed = speed;
		} else if (autoScrollTimer) {
			clearInterval(autoScrollTimer);
			autoScrollTimer = null;
		}
	}

	function onMove(clientY) {
		if (!dragState) {
			return;
		}
		// Insertion index within the list that still contains the dragged row.
		var rawTarget = computeTargetIndex(clientY);
		dragState.rawTarget = rawTarget;
		positionIndicator(rawTarget);
		handleAutoScroll(clientY);
	}

	function pointerMove(e) {
		if (!dragState) {
			return;
		}
		var clientY;
		if (e.touches && e.touches.length) {
			clientY = e.touches[0].clientY;
			e.preventDefault();
		} else {
			clientY = e.clientY;
		}
		onMove(clientY);
	}

	function endDrag() {
		if (!dragState) {
			return;
		}
		if (autoScrollTimer) {
			clearInterval(autoScrollTimer);
			autoScrollTimer = null;
		}

		var fromIdx = dragState.fromIdx;
		var rawTarget = dragState.rawTarget;

		// Clean up visual state.
		if (dragState.indicator && dragState.indicator.parentNode) {
			dragState.indicator.parentNode.removeChild(dragState.indicator);
		}
		dragState.row.classList.remove('row-dragging');
		document.body.classList.remove('reorder-no-select');

		document.removeEventListener('mousemove', pointerMove);
		document.removeEventListener('mouseup', endDrag);
		document.removeEventListener('touchmove', pointerMove);
		document.removeEventListener('touchend', endDrag);
		document.removeEventListener('touchcancel', endDrag);

		dragState = null;

		// rawTarget is the insertion index in the full list (including the
		// dragged row). Convert to a pop/insert target index.
		var toIdx = rawTarget;
		if (rawTarget > fromIdx) {
			toIdx = rawTarget - 1;
		}
		if (toIdx === fromIdx || toIdx < 0) {
			return;
		}
		moveScheduleLine(fromIdx, toIdx);
	}

	function startDrag(handle, clientY, isTouch) {
		var row = handle.closest('tr[data-line-idx]');
		if (!row) {
			return;
		}
		dragState = {
			row: row,
			fromIdx: parseInt(row.getAttribute('data-line-idx'), 10),
			indicator: makeIndicator(),
			rawTarget: null,
			scrollSpeed: 0
		};
		row.classList.add('row-dragging');
		document.body.classList.add('reorder-no-select');

		if (isTouch) {
			document.addEventListener('touchmove', pointerMove, { passive: false });
			document.addEventListener('touchend', endDrag);
			document.addEventListener('touchcancel', endDrag);
		} else {
			document.addEventListener('mousemove', pointerMove);
			document.addEventListener('mouseup', endDrag);
		}
		onMove(clientY);
	}

	tbody.addEventListener('mousedown', function(e) {
		var handle = e.target.closest('.drag-handle-btn');
		if (!handle) {
			return;
		}
		e.preventDefault();
		startDrag(handle, e.clientY, false);
	});

	tbody.addEventListener('touchstart', function(e) {
		var handle = e.target.closest('.drag-handle-btn');
		if (!handle) {
			return;
		}
		e.preventDefault();
		startDrag(handle, e.touches[0].clientY, true);
	}, { passive: false });
}
