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

	// One entry per physical profile/lens piece. `group` is the customer's segment the piece
	// belongs to: a long segment ships as several pieces joined in the field.
	function linearPieces(computed) {
		var source = (computed.user_segments && computed.user_segments.length) ? computed.user_segments : (computed.segments || []);
		return source.map(function (s, i) {
			var length = number(s.profile_cut_len_mm) || number(s.tape_cut_len_mm) || number(s.manufacturable_length_mm);
			return {
				key: s.segment_index != null ? s.segment_index : i + 1,
				group: s.user_segment_index != null ? number(s.user_segment_index) : 1,
				length_mm: length,
				lens_mm: number(s.lens_cut_len_mm),
				tape_mm: number(s.tape_cut_len_mm),
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
				group: i + 1,
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

	function label(pieces) {
		var counts = {};
		pieces.forEach(function (p) { counts[p.group] = (counts[p.group] || 0) + 1; });
		var seen = {};
		pieces.forEach(function (p) {
			seen[p.group] = (seen[p.group] || 0) + 1;
			p.label = t('Segment') + ' ' + p.group + (counts[p.group] > 1 ? ', ' + t('piece') + ' ' + seen[p.group] + ' ' + t('of') + ' ' + counts[p.group] : '');
		});
	}

	// Positions along the drawn strip are "fixture millimetres": the pieces end to end, no gaps.
	function offsets(pieces) {
		var at = 0;
		pieces.forEach(function (p) { p.from = at; at += p.length_mm; p.to = at; });
		return at;
	}

	// Linear tape is one continuous strip per customer segment, so a run can cross the field
	// joints between pieces and, through a jumper, into the next segment. Runs are laid end to
	// end along the tape and mapped onto the pieces, rather than squeezed into the piece the
	// run starts in (which drew every run of a single long segment on its first piece).
	function linearRuns(pieces, runs) {
		var groups = [];
		pieces.forEach(function (p) {
			var last = groups[groups.length - 1];
			if (!last || last.group !== p.group) groups.push(last = { group: p.group, from: p.from, to: p.to, tape: 0 });
			last.to = p.to;
			last.tape += p.tape_mm;
		});
		var list = (runs || []).map(function (r) { return { length_mm: number(r.run_len_mm), watts: number(r.run_watts) }; })
			.filter(function (r) { return r.length_mm > 0; });
		var runTotal = list.reduce(function (sum, r) { return sum + r.length_mm; }, 0);
		var tapeTotal = groups.reduce(function (sum, g) { return sum + g.tape; }, 0);
		if (!(tapeTotal > 0)) {
			// Single-segment builds report one tape length; spread it over the pieces.
			groups.forEach(function (g) { g.tape = g.to - g.from; });
			tapeTotal = groups.reduce(function (sum, g) { return sum + g.tape; }, 0);
		}
		var stretch = runTotal > tapeTotal && runTotal > 0 ? tapeTotal / runTotal : 1;
		function place(position) {
			var before = 0;
			for (var i = 0; i < groups.length; i++) {
				var g = groups[i];
				if (position <= before + g.tape + 0.5 || i === groups.length - 1) {
					var share = g.tape > 0 ? Math.min(Math.max((position - before) / g.tape, 0), 1) : 0;
					return g.from + share * (g.to - g.from);
				}
				before += g.tape;
			}
			return 0;
		}
		var tape = 0;
		return list.map(function (r) {
			var start = tape;
			tape += r.length_mm * stretch;
			return { from: place(start), to: place(tape), length_mm: r.length_mm, watts: r.watts };
		});
	}

	// Tape and neon split runs inside each segment; lay them out along their own segment.
	function tapeRuns(pieces) {
		var placed = [];
		pieces.forEach(function (p) {
			var total = p.runs.reduce(function (sum, r) { return sum + r.length_mm; }, 0);
			var fit = total > p.length_mm && total > 0 ? p.length_mm / total : 1;
			var at = p.from;
			p.runs.forEach(function (r) {
				var width = r.length_mm * fit;
				placed.push({ from: at, to: at + width, length_mm: r.length_mm, watts: r.watts });
				at += width;
			});
		});
		return placed;
	}

	function stripModel(pieces, runs, family) {
		var truncated = pieces.length > MAX_PIECES;
		if (truncated) pieces = pieces.slice(0, MAX_PIECES);
		var total = pieces.length ? pieces[pieces.length - 1].to : 0;
		var gaps = Math.max(pieces.length - 1, 0);
		var usable = WIDTH - 2 * MARGIN - gaps * GAP;
		var scale = total > 0 ? usable / total : 0;
		var shapes = [];
		var feeds = 0;
		var jumpers = 0;
		var pieceY = 52;
		var runY = 74;
		var x = MARGIN;
		pieces.forEach(function (p) {
			p.x = x;
			p.w = Math.max(p.length_mm * scale, MIN_PIECE);
			x += p.w + GAP;
		});
		// A start on a boundary belongs to the next piece; an end belongs to the previous one.
		function xAt(position, start) {
			for (var i = 0; i < pieces.length; i++) {
				var p = pieces[i];
				if ((start ? position < p.to - 0.5 : position <= p.to + 1e-6) || i === pieces.length - 1) {
					var share = p.length_mm > 0 ? Math.min(Math.max((position - p.from) / p.length_mm, 0), 1) : 0;
					return p.x + share * p.w;
				}
			}
			return MARGIN;
		}
		pieces.forEach(function (p, index) {
			shapes.push({ type: 'rect', cls: 'ill-bp-piece', x: round(p.x), y: pieceY, width: round(p.w), height: 14,
				title: p.label + ': ' + inches(p.length_mm) });
			shapes.push({ type: 'text', cls: 'ill-bp-label', x: round(p.x + p.w / 2), y: pieceY - 6, text: inches(p.length_mm) });
			if (p.lens_mm) {
				shapes.push({ type: 'text', cls: 'ill-bp-note', x: round(p.x + p.w / 2), y: pieceY + 26, text: t('Lens') + ' ' + inches(p.lens_mm) });
			}
			if (index < pieces.length - 1) {
				var next = pieces[index + 1];
				var x1 = p.x + p.w;
				var x2 = next.x;
				var mid = pieceY + 7;
				if (next.group === p.group) {
					shapes.push({ type: 'line', cls: 'ill-bp-joint', x1: round(x1), y1: mid, x2: round(x2), y2: mid,
						title: t('Field joint: one segment shipped in pieces') });
				} else if (p.jumper_in) {
					jumpers += 1;
					var through = runs.some(function (r) { return r.from < p.to - 1 && r.to > p.to + 1; });
					shapes.push({ type: 'path', cls: 'ill-bp-jumper', d: 'M' + round(x1) + ' ' + mid + ' Q' + round((x1 + x2) / 2) + ' ' + (pieceY + 34) + ' ' + round(x2) + ' ' + mid,
						title: t('Jumper') + ' ' + p.jumper_in.toFixed(0) + '"' + (through ? ' — ' + t('the run continues into the next segment') : ' — ' + t('the next segment starts a new run with its own feed')) });
				} else {
					shapes.push({ type: 'line', cls: 'ill-bp-break', x1: round(x1), y1: mid, x2: round(x2), y2: mid,
						title: t('Separate segment, no jumper') });
				}
			}
		});
		var drawnEnd = total;
		var runCount = 0;
		runs.forEach(function (r) {
			if (r.from >= drawnEnd) return;
			runCount += 1;
			feeds += 1;
			var cls = 'ill-bp-run ill-bp-run--' + (runCount % 2 ? 'a' : 'b');
			var title = t('Run') + ' ' + runCount + ': ' + inches(r.length_mm) + (r.watts ? ', ' + r.watts.toFixed(1) + ' W' : '');
			// A run that crosses a joint or jumper is drawn on each piece it covers.
			pieces.forEach(function (p) {
				var a = Math.max(r.from, p.from);
				var b = Math.min(r.to, p.to);
				if (b - a <= 0.5) return;
				var x1 = xAt(a, true);
				var x2 = Math.min(p.x + (b - p.from) * scale, p.x + p.w);
				shapes.push({ type: 'rect', cls: cls, x: round(x1), y: runY, width: round(Math.max(x2 - x1, 1)), height: 8, title: title });
			});
			var start = pieces.filter(function (p) { return Math.abs(p.from - r.from) < 1; })[0];
			var leader = start && start.leader_in ? ', ' + t('leader') + ' ' + start.leader_in.toFixed(0) + '"' : '';
			shapes.push({ type: 'circle', cls: 'ill-bp-feed', cx: round(xAt(r.from, true)), cy: runY + 4, r: 4,
				title: t('Feed point') + ' ' + runCount + ' (' + t('run') + ' ' + runCount + ')' + leader });
		});
		if (!runCount) {
			pieces.forEach(function (p) {
				if (!p.leader_in) return;
				feeds += 1;
				shapes.push({ type: 'circle', cls: 'ill-bp-feed', cx: round(p.x), cy: runY + 4, r: 4,
					title: t('Feed point') + ', ' + t('leader') + ' ' + p.leader_in.toFixed(0) + '"' });
			});
		}
		var segments = pieces.reduce(function (list, p) { if (list.indexOf(p.group) < 0) list.push(p.group); return list; }, []).length;
		var parts = [segments + ' ' + t(segments === 1 ? 'segment' : 'segments')];
		if (pieces.length !== segments) parts.push(pieces.length + ' ' + t(pieces.length === 1 ? 'piece' : 'pieces'));
		parts.push(
			runCount + ' ' + t(runCount === 1 ? 'run' : 'runs'),
			feeds + ' ' + t(feeds === 1 ? 'feed point' : 'feed points'),
			jumpers + ' ' + t(jumpers === 1 ? 'jumper' : 'jumpers')
		);
		return { kind: 'strip', family: family, width: WIDTH, height: 100, shapes: shapes, truncated: truncated,
			counts: { segments: segments, pieces: pieces.length, runs: runCount, feeds: feeds, jumpers: jumpers }, total_mm: total, summary: parts.join(', ') };
	}

	function feedOf(group) {
		if (!group || group.supply_number == null) return '';
		return ' (' + t('power supply') + ' ' + number(group.supply_number)
			+ (group.output_number != null ? ', ' + t('output') + ' ' + number(group.output_number) : '') + ')';
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
				title: t('Panel') + ' ' + (i + 1) + (group >= 0 ? ', ' + t('driver group') + ' ' + (group + 1) + feedOf(r.groups[group]) : '') });
		}
		var groups = (r.groups || []).length;
		// Each group is one feed: its own leader cable on one power supply output.
		var supplies = {};
		(r.groups || []).forEach(function (g) { if (g.supply_number != null) supplies[number(g.supply_number)] = true; });
		var supplyCount = Object.keys(supplies).length;
		var summary = [
			needed + ' ' + t(needed === 1 ? 'panel' : 'panels') + ' (' + cols + ' × ' + rows + ')',
			groups + ' ' + t(groups === 1 ? 'driver group' : 'driver groups')
				+ (supplyCount ? ' ' + t('on') + ' ' + supplyCount + ' ' + t(supplyCount === 1 ? 'power supply' : 'power supplies') : ''),
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
		var pieces = (family === 'linear' ? linearPieces(computed) : tapePieces(computed))
			.filter(function (p) { return p.length_mm > 0; });
		if (!pieces.length) return null;
		label(pieces);
		offsets(pieces);
		var runs = family === 'linear' ? linearRuns(pieces, computed.runs) : tapeRuns(pieces);
		return stripModel(pieces, runs, family);
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
