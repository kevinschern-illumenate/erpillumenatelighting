/**
 * Build preview (plan 6.6): a read-only SVG drawing of the calculated build.
 *
 * `model(result, family)` is pure: it turns the server's computed build into
 * scaled drawing primitives (pieces, runs, feed points, jumpers, cut lengths or
 * the sheet grid) and never changes the build. `render(container, result,
 * family)` draws that model with createElementNS and textContent only.
 * Families: 'linear', 'tape', 'neon', 'sheet'.
 */
(function (root, factory) {
	'use strict';
	var api = factory();
	if (typeof module === 'object' && module.exports) module.exports = api;
	if (root) root.IllBuildPreview = api;
}(typeof window !== 'undefined' ? window : null, function () {
	'use strict';

	var SVG_NS = 'http://www.w3.org/2000/svg';
	var MM_PER_INCH = 25.4;
	var WIDTH = 720;
	var MARGIN = 16;
	var GAP = 18;
	var MIN_PIECE = 3;
	var MAX_PIECES = 60;
	var MAX_PANELS = 400;

	function t(text) {
		return typeof __ === 'function' ? __(text) : text;
	}

	function number(value) {
		var n = Number(value);
		return isFinite(n) ? n : 0;
	}

	function inches(mm) {
		return (number(mm) / MM_PER_INCH).toFixed(1) + '"';
	}

	function round(value) {
		return Math.round(value * 100) / 100;
	}

	function linearPieces(computed) {
		var source = (computed.user_segments && computed.user_segments.length) ? computed.user_segments : (computed.segments || []);
		return source.map(function (s, i) {
			var length = number(s.profile_cut_len_mm) || number(s.tape_cut_len_mm) || number(s.manufacturable_length_mm);
			return {
				key: s.segment_index != null ? s.segment_index : i + 1,
				label: s.user_segment_index != null ? String(s.user_segment_index) : String(i + 1),
				length_mm: length,
				lens_mm: number(s.lens_cut_len_mm),
				leader_in: number(s.start_leader_len_mm) / MM_PER_INCH,
				jumper_in: number(s.end_jumper_len_mm) / MM_PER_INCH,
				runs: [],
			};
		});
	}

	function tapePieces(computed) {
		return (computed.segments || []).map(function (s, i) {
			return {
				key: s.segment_index != null ? s.segment_index : i + 1,
				label: String(s.segment_index != null ? s.segment_index : i + 1),
				length_mm: number(s.manufacturable_length_mm) || number(s.requested_length_mm),
				lens_mm: 0,
				leader_in: number(s.start_lead_length_inches),
				jumper_in: s.end_type === 'Jumper' ? number(s.end_feed_length_inches) : 0,
				runs: (s.runs || []).map(function (r) {
					return { length_mm: number(r.run_len_mm), watts: number(r.run_watts) };
				}),
			};
		});
	}

	// Linear runs carry the physical segment they start in; place them on that piece.
	function attachLinearRuns(pieces, runs) {
		var byKey = {};
		pieces.forEach(function (p) { byKey[p.key] = p; });
		var unplaced = [];
		(runs || []).forEach(function (r) {
			var run = { length_mm: number(r.run_len_mm), watts: number(r.run_watts) };
			if (byKey[r.segment_index]) byKey[r.segment_index].runs.push(run);
			else unplaced.push(run);
		});
		if (unplaced.length && pieces.length) pieces[0].runs = pieces[0].runs.concat(unplaced);
	}

	function stripModel(pieces, family) {
		var truncated = pieces.length > MAX_PIECES;
		if (truncated) pieces = pieces.slice(0, MAX_PIECES);
		var total = pieces.reduce(function (sum, p) { return sum + p.length_mm; }, 0);
		var gaps = Math.max(pieces.length - 1, 0);
		var usable = WIDTH - 2 * MARGIN - gaps * GAP;
		var scale = total > 0 ? usable / total : 0;
		var shapes = [];
		var feeds = 0;
		var jumpers = 0;
		var runCount = 0;
		var x = MARGIN;
		var pieceY = 52;
		var runY = 74;
		pieces.forEach(function (p, index) {
			var w = Math.max(p.length_mm * scale, MIN_PIECE);
			shapes.push({ type: 'rect', cls: 'ill-bp-piece', x: round(x), y: pieceY, width: round(w), height: 14,
				title: t('Segment') + ' ' + p.label + ': ' + inches(p.length_mm) });
			shapes.push({ type: 'text', cls: 'ill-bp-label', x: round(x + w / 2), y: pieceY - 6, text: inches(p.length_mm) });
			if (p.lens_mm) {
				shapes.push({ type: 'text', cls: 'ill-bp-note', x: round(x + w / 2), y: pieceY + 26, text: t('Lens') + ' ' + inches(p.lens_mm) });
			}
			var runX = x;
			var runScale = p.runs.reduce(function (s, r) { return s + r.length_mm; }, 0);
			// Runs never draw past their piece even when tape continues across a joiner.
			var fit = runScale > p.length_mm && runScale > 0 ? p.length_mm / runScale : 1;
			p.runs.forEach(function (r, ri) {
				var rw = Math.max(r.length_mm * scale * fit, 1);
				runCount += 1;
				feeds += 1;
				shapes.push({ type: 'rect', cls: 'ill-bp-run ill-bp-run--' + (runCount % 2 ? 'a' : 'b'), x: round(runX), y: runY, width: round(rw), height: 8,
					title: t('Run') + ' ' + runCount + ': ' + inches(r.length_mm) + (r.watts ? ', ' + r.watts.toFixed(1) + ' W' : '') });
				shapes.push({ type: 'circle', cls: 'ill-bp-feed', cx: round(runX), cy: runY + 4, r: 4,
					title: t('Feed point') + ' ' + runCount + (ri === 0 && p.leader_in ? ', ' + t('leader') + ' ' + p.leader_in.toFixed(0) + '"' : '') });
				runX += rw;
			});
			if (!p.runs.length && p.leader_in) {
				feeds += 1;
				shapes.push({ type: 'circle', cls: 'ill-bp-feed', cx: round(x), cy: runY + 4, r: 4,
					title: t('Feed point') + ', ' + t('leader') + ' ' + p.leader_in.toFixed(0) + '"' });
			}
			if (index < pieces.length - 1) {
				var x1 = x + w;
				var x2 = x1 + GAP;
				if (p.jumper_in) {
					jumpers += 1;
					shapes.push({ type: 'path', cls: 'ill-bp-jumper', d: 'M' + round(x1) + ' ' + (pieceY + 7) + ' Q' + round((x1 + x2) / 2) + ' ' + (pieceY + 34) + ' ' + round(x2) + ' ' + (pieceY + 7),
						title: t('Jumper') + ' ' + p.jumper_in.toFixed(0) + '"' });
				} else {
					shapes.push({ type: 'line', cls: 'ill-bp-joint', x1: round(x1), y1: pieceY + 7, x2: round(x2), y2: pieceY + 7,
						title: t('Joined') });
				}
			}
			x += w + GAP;
		});
		var summary = [
			pieces.length + ' ' + t(pieces.length === 1 ? 'segment' : 'segments'),
			runCount + ' ' + t(runCount === 1 ? 'run' : 'runs'),
			feeds + ' ' + t(feeds === 1 ? 'feed point' : 'feed points'),
			jumpers + ' ' + t(jumpers === 1 ? 'jumper' : 'jumpers'),
		].join(', ');
		return { kind: 'strip', family: family, width: WIDTH, height: 100, shapes: shapes, truncated: truncated,
			counts: { pieces: pieces.length, runs: runCount, feeds: feeds, jumpers: jumpers }, total_mm: total, summary: summary };
	}

	function sheetModel(r) {
		var cols = Math.max(parseInt(r.panels_wide, 10) || 0, 0);
		var rows = Math.max(parseInt(r.panels_tall, 10) || 0, 0);
		var needed = Math.min(parseInt(r.panels_needed, 10) || cols * rows, cols * rows);
		if (!cols || !rows || !needed) return null;
		var truncated = needed > MAX_PANELS;
		var drawn = Math.min(needed, MAX_PANELS);
		var groupOf = [];
		// Groups fill in panel order; positions are illustrative, not a wiring plan.
		(r.groups || []).forEach(function (g, gi) {
			for (var k = 0; k < (parseInt(g.sheet_count, 10) || 0); k++) groupOf.push(gi);
		});
		var aspect = number(r.sheet_height_ft) && number(r.sheet_width_ft) ? number(r.sheet_height_ft) / number(r.sheet_width_ft) : 1;
		var cell = Math.min((WIDTH - 2 * MARGIN) / cols, 60 / aspect);
		var cellH = cell * aspect;
		var shapes = [];
		for (var i = 0; i < drawn; i++) {
			var col = i % cols;
			var row = Math.floor(i / cols);
			var group = groupOf[i] != null ? groupOf[i] : -1;
			shapes.push({ type: 'rect', cls: 'ill-bp-panel ill-bp-group--' + (group < 0 ? 'none' : group % 6),
				x: round(MARGIN + col * cell), y: round(MARGIN + row * cellH), width: round(cell - 2), height: round(cellH - 2),
				title: t('Panel') + ' ' + (i + 1) + (group >= 0 ? ', ' + t('driver group') + ' ' + (group + 1) : '') });
		}
		var groups = (r.groups || []).length;
		var summary = [
			needed + ' ' + t(needed === 1 ? 'panel' : 'panels') + ' (' + cols + ' × ' + rows + ')',
			groups + ' ' + t(groups === 1 ? 'driver group' : 'driver groups'),
			number(r.leader_cable_qty) + ' ' + t('leader cables'),
			number(r.jumper_cable_qty) + ' ' + t('jumper cables'),
		].join(', ');
		return { kind: 'grid', family: 'sheet', width: WIDTH, height: round(2 * MARGIN + Math.ceil(drawn / cols) * cellH), shapes: shapes,
			truncated: truncated, counts: { panels: needed, cols: cols, rows: rows, groups: groups }, summary: summary };
	}

	function model(result, family) {
		if (!result) return null;
		if (family === 'sheet') return sheetModel(result);
		var computed = result.computed || {};
		var pieces;
		if (family === 'linear') {
			pieces = linearPieces(computed);
			attachLinearRuns(pieces, computed.runs);
		} else {
			pieces = tapePieces(computed);
		}
		pieces = pieces.filter(function (p) { return p.length_mm > 0; });
		return pieces.length ? stripModel(pieces, family) : null;
	}

	var ATTRS = { rect: ['x', 'y', 'width', 'height'], circle: ['cx', 'cy', 'r'], line: ['x1', 'y1', 'x2', 'y2'], path: ['d'], text: ['x', 'y'] };

	function clear(container) {
		while (container.firstChild) container.removeChild(container.firstChild);
	}

	function render(container, result, family) {
		if (!container) return null;
		clear(container);
		if (container.getAttribute('data-enabled') !== '1') {
			container.hidden = true;
			return null;
		}
		var drawing = model(result, family);
		if (!drawing) {
			container.hidden = true;
			return null;
		}
		var doc = container.ownerDocument;
		var heading = doc.createElement('h6');
		heading.textContent = t('Build preview');
		container.appendChild(heading);
		var svg = doc.createElementNS(SVG_NS, 'svg');
		svg.setAttribute('viewBox', '0 0 ' + drawing.width + ' ' + drawing.height);
		svg.setAttribute('role', 'img');
		svg.setAttribute('class', 'ill-bp-svg');
		svg.setAttribute('aria-label', t('Build preview') + ': ' + drawing.summary);
		var title = doc.createElementNS(SVG_NS, 'title');
		title.textContent = drawing.summary;
		svg.appendChild(title);
		drawing.shapes.forEach(function (shape) {
			var el = doc.createElementNS(SVG_NS, shape.type);
			el.setAttribute('class', shape.cls);
			ATTRS[shape.type].forEach(function (name) { el.setAttribute(name, String(shape[name])); });
			if (shape.type === 'text') {
				el.setAttribute('text-anchor', 'middle');
				el.textContent = shape.text;
			}
			if (shape.title) {
				var tip = doc.createElementNS(SVG_NS, 'title');
				tip.textContent = shape.title;
				el.appendChild(tip);
			}
			svg.appendChild(el);
		});
		container.appendChild(svg);
		var caption = doc.createElement('p');
		caption.className = 'small text-muted mb-0';
		caption.textContent = drawing.summary + (drawing.truncated ? ' — ' + t('preview shows the first part only') : '')
			+ (drawing.kind === 'grid' ? ' — ' + t('group colours show panel order, not wiring') : '')
			+ ' — ' + t('preview only; the build above is authoritative');
		container.appendChild(caption);
		container.hidden = false;
		return drawing;
	}

	return { model: model, render: render };
}));
