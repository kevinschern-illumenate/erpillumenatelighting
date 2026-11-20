/* Kevin's Desk. Phase 1: NOW bar, today's schedule, week themes. Phase 2: pipeline widgets (through the
   Command Center gateway), the Command Center's decisions, my ToDos.
   Inlined into /kd/<slug> by templates/pages/kevins_desk.py (never served from /assets).
   Boot data: window.KD_BOOT = { user, first_name, schedule: kevins_desk.schedule.payload(), command_center, api }.
   The clock is always Pacific (schedule.tz), whatever the laptop's time zone.
   KDCore (pacific, locate, fmtLeft) has no DOM access, so tests/portal_ui/kevins_desk.test.cjs runs it in Node. */
(function (root) {
  'use strict';

  /* ---------------- core (pure) ---------------- */
  const DOW = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 };
  const DAYNAME = ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const LONGDAY = ['', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

  const clock = (h, m) => `${(h + 11) % 12 + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
  const hhmm = min => { const h = Math.floor(min / 60), m = min % 60; return `${(h + 11) % 12 + 1}:${String(m).padStart(2, '0')}`; };

  function pacific(date, tz) {
    const p = {};
    new Intl.DateTimeFormat('en-US', {
      timeZone: tz, weekday: 'short', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }).formatToParts(date).forEach(x => { p[x.type] = x.value; });
    const hour = Number(p.hour) % 24, minute = Number(p.minute);
    return {
      dow: DOW[p.weekday], min: hour * 60 + minute + Number(p.second) / 60,
      date: `${p.weekday}, ${p.month} ${p.day}`, clock: clock(hour, minute),
    };
  }

  function fmtLeft(mins) {
    const m = Math.max(0, Math.ceil(mins - 1e-9)), h = Math.floor(m / 60), r = m % 60;
    return h ? (r ? `${h}h ${r}m` : `${h}h`) : `${r}m`;
  }

  function nextWorkday(days, dow) {
    for (let i = 1; i <= 7; i++) {
      const d = ((dow - 1 + i) % 7) + 1;
      if ((days[d] || []).length) return { dow: d, offset: i };
    }
    return null;
  }

  const firstOf = (days, from) => { const w = nextWorkday(days, from); return w ? { block: days[w.dow][0], dow: w.dow, offset: w.offset } : null; };

  /* Where "now" falls in the schedule.
     state: 'block' (inside a block), 'before' (before the first block today), 'after' (done for the day),
            'weekend' (no blocks today). next: { block, dow, offset (days ahead) } or null. */
  function locate(days, now) {
    const blocks = days[now.dow] || [];
    if (!blocks.length) return { state: 'weekend', current: null, index: -1, next: firstOf(days, now.dow) };
    const first = blocks[0], last = blocks[blocks.length - 1];
    if (now.min < first.start) {
      return { state: 'before', current: null, index: -1, startsIn: first.start - now.min, next: { block: first, dow: now.dow, offset: 0 } };
    }
    if (now.min >= last.end) return { state: 'after', current: null, index: blocks.length, next: firstOf(days, now.dow) };
    const i = blocks.findIndex(b => now.min >= b.start && now.min < b.end);
    if (i < 0) { // a gap between blocks: show the next one
      const j = blocks.findIndex(b => b.start > now.min);
      return { state: 'gap', current: null, index: j - 0.5, startsIn: blocks[j].start - now.min, next: { block: blocks[j], dow: now.dow, offset: 0 } };
    }
    const cur = blocks[i];
    return {
      state: 'block', current: cur, index: i, left: cur.end - now.min,
      progress: (now.min - cur.start) / (cur.end - cur.start),
      next: blocks[i + 1] ? { block: blocks[i + 1], dow: now.dow, offset: 0 } : firstOf(days, now.dow),
    };
  }

  root.KDCore = { pacific, locate, fmtLeft, nextWorkday, hhmm };

  /* ---------------- page ---------------- */
  const BOOT = root.KD_BOOT, doc = root.document;
  if (!BOOT || !doc || !doc.getElementById('cc')) return;

  const S = BOOT.schedule, DAYS = S.days;
  const HAT = {}; S.hats.forEach(h => { HAT[h.key] = h.label; });
  const $ = id => doc.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const hat = key => key
    ? `<span class="kd-hat" data-hat="${esc(key)}">${esc(HAT[key] || key)}</span>`
    : '<span class="kd-hat" data-hat="none">No hat</span>';
  const when = n => !n ? '' : n.offset === 0 ? hhmm(n.block.start) : n.offset === 1 ? `Tomorrow ${hhmm(n.block.start)}` : `${DAYNAME[n.dow]} ${hhmm(n.block.start)}`;

  function nowBar(now, at) {
    let main, side;
    if (at.state === 'block') {
      const b = at.current, pct = Math.min(100, Math.max(0, at.progress * 100)).toFixed(1);
      main = `<div class="eyebrow">Now · ${esc(now.date)} · ${esc(now.clock)} PT</div>
        <h1 class="kd-block">${esc(b.title)}</h1>
        <div class="kd-meta">${hat(b.hat)}<span>${esc(b.label)}</span></div>
        <div class="meter" role="progressbar" aria-label="Block elapsed" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct)}"><i style="width:${pct}%"></i></div>`;
      side = `<div class="kd-left"><div class="v">${esc(fmtLeft(at.left))}</div><div class="d">left in this block</div></div>`;
    } else {
      const label = { before: 'Before the day', gap: 'Between blocks', after: 'Off the clock', weekend: 'Weekend' }[at.state];
      const sub = at.state === 'before' || at.state === 'gap'
        ? `${esc(at.next.block.title)} starts in ${esc(fmtLeft(at.startsIn))}`
        : 'Nothing scheduled until the next workday.';
      main = `<div class="eyebrow">Now · ${esc(now.date)} · ${esc(now.clock)} PT</div>
        <h1 class="kd-block">${esc(label)}</h1><div class="kd-meta"><span>${sub}</span></div>`;
      side = '';
    }
    const n = at.next;
    const next = n ? `<div class="kd-next"><div class="eyebrow">Next · ${esc(when(n))}</div>
        <div class="t">${esc(n.block.title)}</div><div class="kd-meta">${hat(n.block.hat)}<span>${esc(n.block.label)}</span></div></div>` : '';
    return `<div class="kd-now-main">${main}</div>${side}${next}`;
  }

  function today(now, at) {
    let dow = now.dow, title = "Today's schedule";
    if (at.state === 'weekend' || at.state === 'after') {
      if (at.next) { dow = at.next.dow; title = `${LONGDAY[dow]}'s schedule`; }
    }
    const shown = dow !== now.dow;
    const theme = S.themes[dow];
    const rows = (DAYS[dow] || []).map((b, i) => {
      const cls = shown ? '' : i === at.index ? 'now' : (i < at.index ? 'past' : '');
      return `<li class="kd-row ${cls}"${cls === 'now' ? ' aria-current="true"' : ''}>
        <span class="kd-time">${esc(b.label)}</span><span class="kd-title">${esc(b.title)}</span>${hat(b.hat)}</li>`;
    }).join('');
    return `<div class="card-h"><div><h2>${esc(title)}</h2>
      <div class="sub">${theme ? `Deep-work theme: ${esc(theme.label)}` : ''}</div></div></div>
      <ol class="kd-list">${rows}</ol>`;
  }

  function week(now) {
    const rows = [1, 2, 3, 4, 5].map(d => {
      const t = S.themes[d], extras = (DAYS[d] || []).filter(b => b.kind === 'kickoff' || b.kind === 'review');
      const note = extras.map(b => `${hhmm(b.start)} ${b.title.toLowerCase()} (${b.end - b.start} min)`).join(' · ');
      return `<li class="kd-wrow${d === now.dow ? ' today' : ''}"${d === now.dow ? ' aria-current="date"' : ''}>
        <span class="kd-day">${DAYNAME[d]}</span><div>${hat(t.hat)}${note ? `<div class="kd-note">${esc(note)}</div>` : ''}</div></li>`;
    }).join('');
    return `<div class="card-h"><div><h2>This week</h2><div class="sub">Deep work 1:00–3:30, by day</div></div></div>
      <ol class="kd-week">${rows}</ol>`;
  }

  let lastKey = '';
  function tick() {
    const now = pacific(new Date(), S.tz), at = locate(DAYS, now);
    $('kdclock').textContent = `${now.date} · ${now.clock} Pacific`;
    $('kdnow').innerHTML = nowBar(now, at);
    // the lists only change when the block or the day does
    const key = `${now.dow}|${at.state}|${at.index}`;
    if (key !== lastKey) { lastKey = key; $('kdtoday').innerHTML = today(now, at); $('kdweek').innerHTML = week(now); }
    doc.title = (at.current ? `${at.current.title} · ${fmtLeft(at.left)} · ` : '') + "Kevin's Desk";
  }

  /* ---------------- pipeline + ToDos (Phase 2) ----------------
     GET kevins_desk.api.pipeline / .signals (owner-only, cached 5 min server-side; Refresh rebuilds). */
  const API = BOOT.api || {};
  const CC = BOOT.command_center || '/command-center';
  const STACK = { 1: 'Customer blocked · order at risk', 2: 'New sales', 3: 'Converting sales', 4: 'Tickets',
    5: 'Unblocking the team', 6: 'Projects', 7: 'Admin' };
  const DATE_HEAD = { so_late: 'Delivery', so_week: 'Delivery', po_late: 'ETA', quotes_open: 'Quote date', tickets: 'Last update' };
  const PARTY_HEAD = { po_late: 'Supplier', tickets: 'Type' };
  const money = v => v == null ? '' : '$' + Math.round(v).toLocaleString('en-US');
  const fmtd = d => d ? new Date(d + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
  const out = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(text)}</a>`;
  const flag = f => f === 'late' ? ' <span class="badge bad">Late</span>' : f === 'today' ? ' <span class="badge warn">Today</span>' : '';
  const wbUrl = dt => `${CC}#wb/${encodeURIComponent(dt)}`;
  const clock12 = iso => { const m = /T(\d\d):(\d\d)/.exec(iso || ''); return m ? clock(Number(m[1]), Number(m[2])) : ''; };

  async function getJSON(url, refresh) {
    const r = await root.fetch(url + (refresh ? '?refresh=1' : ''), { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()).message;
  }

  function widgetCard(w) {
    const hasMoney = w.items.some(i => i.amount != null);
    const tone = !w.total ? 'mute' : w.stack === 1 ? 'bad' : w.stack === 2 ? 'warn' : 'info';
    const head = ['Record', PARTY_HEAD[w.key] || 'Customer', DATE_HEAD[w.key] || 'Date'].concat(hasMoney ? ['#Amount'] : []);
    const rows = w.items.map(i => `<tr><td>${out(i.url, i.title)}</td><td>${esc(i.party || '')}</td>
      <td class="kd-nowrap">${esc(fmtd(i.date))}${flag(i.flag)}</td>${hasMoney ? `<td class="num">${esc(money(i.amount))}</td>` : ''}</tr>`).join('');
    const body = w.error ? `<div class="empty">Couldn't load this list (${esc(w.error)}). Try Refresh.</div>`
      : rows ? `<div class="tw"><table><thead><tr>${head.map(h => `<th class="${h[0] === '#' ? 'num' : ''}">${esc(h.replace(/^#/, ''))}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`
      : '<div class="empty">Nothing here right now</div>';
    const more = w.total > w.items.length
      ? `<div class="kd-more">Showing ${w.items.length} of ${w.total} · <a href="${esc(wbUrl(w.dt))}" target="_blank" rel="noopener">All in the Command Center ↗</a></div>` : '';
    return `<section class="card flush kd-widget" data-widget="${esc(w.key)}"><div class="card-h"><div>
      <div class="eyebrow">${esc(w.stack)} · ${esc(STACK[w.stack] || '')}</div><h2>${esc(w.label)}</h2></div>
      <span class="badge ${tone}">${esc(w.total)}</span></div>${body}${more}</section>`;
  }

  function todoRow(t) {
    const meta = [t.date ? `${esc(fmtd(t.date))}${flag(t.flag)}` : '<span class="calc">No date</span>'];
    if (t.priority === 'High') meta.push('<span class="badge warn">High</span>');
    if (t.ref) meta.push(out(t.ref.url, `${t.ref.dt} ${t.ref.name}`));
    if (t.gmail) meta.push(out(t.gmail, 'Open in Gmail'));
    (t.tags || []).forEach(tag => meta.push(`<span class="badge mute">${esc(tag)}</span>`));
    return `<li class="kd-todo">${out(t.url, t.title)}<div class="kd-todo-m">${meta.join('')}</div></li>`;
  }

  function todosCard(todos, error) {
    const by = b => todos.filter(t => t.bucket === b);
    const now = by('overdue').concat(by('today')), later = by('upcoming'), undated = by('undated');
    const fold = (label, list) => list.length ? `<details class="more kd-fold"><summary>${esc(label)} (${list.length})</summary><ul class="kd-todos">${list.map(todoRow).join('')}</ul></details>` : '';
    const body = error ? `<div class="empty">Couldn't load your ToDos (${esc(error)}).</div>`
      : `${now.length ? `<ul class="kd-todos">${now.map(todoRow).join('')}</ul>` : '<div class="empty">Nothing due today or overdue</div>'}
         ${fold('Upcoming', later)}${fold('No date', undated)}`;
    const sub = error ? '' : `${by('overdue').length} overdue · ${by('today').length} due today · ${todos.length} open`;
    return `<div class="card-h"><div><h2>My ToDos</h2><div class="sub">${esc(sub)}</div></div>
      <a class="cc-btn soft" href="/desk/todo?allocated_to=${encodeURIComponent(BOOT.user)}&status=Open" target="_blank" rel="noopener">All ↗</a></div>${body}`;
  }

  function signalsStrip(data, error) {
    if (error) return `<div class="kd-sig-note">Command Center decisions unavailable (${esc(error)}).</div>`;
    const list = (data && data.signals) || [];
    if (!list.length) return '';
    return `<div class="eyebrow kd-sig-h">Command Center · decisions this week</div><div class="dec-grid">${list.map(s =>
      `<a class="dec ${esc(s.tone || '')}" href="${esc(wbUrl(s.dt))}" target="_blank" rel="noopener"><span class="n">${esc(s.count)}</span><span class="l">${esc(s.label)}</span></a>`).join('')}</div>`;
  }

  let loading = false;
  async function load(refresh) {
    if (loading || !API.pipeline) return;
    loading = true;
    const btn = $('kdrefresh'); btn.disabled = true; btn.textContent = refresh ? 'Refreshing…' : 'Loading…';
    if (!$('kdpipe').innerHTML) $('kdpipe').innerHTML = '<div class="card"><div class="cc-loading kd-loading"><span class="cc-spin"></span>Loading the pipeline…</div></div>';
    const [pipe, sig] = await Promise.allSettled([getJSON(API.pipeline, refresh), getJSON(API.signals, refresh)]);
    if (pipe.status === 'fulfilled') {
      const p = pipe.value;
      $('kdpipe').innerHTML = p.widgets.map(widgetCard).join('');
      $('kdtodos').innerHTML = todosCard(p.todos, p.todos_error);
      $('kdstamp').textContent = `Updated ${clock12(p.built_at)}${p.cached ? ' (cached)' : ''}`;
    } else {
      $('kdpipe').innerHTML = `<div class="card"><div class="empty">Couldn't load the pipeline (${esc(pipe.reason && pipe.reason.message)}). Try Refresh.</div></div>`;
      $('kdtodos').innerHTML = todosCard([], 'not loaded');
      $('kdstamp').textContent = 'Not updated';
    }
    $('kdsignals').innerHTML = signalsStrip(sig.value, sig.status === 'rejected' ? (sig.reason && sig.reason.message) : null);
    btn.disabled = false; btn.textContent = 'Refresh'; loading = false;
  }

  $('kdwho').textContent = `Signed in as ${BOOT.user}`;
  if (BOOT.command_center) $('kdcc').href = BOOT.command_center;
  $('kdrefresh').addEventListener('click', () => load(true));
  tick();
  root.setInterval(tick, 15000);
  root.setInterval(() => { if (!doc.hidden) load(false); }, 300000);
  doc.addEventListener('visibilitychange', () => { if (!doc.hidden) tick(); });
  root.KDPage = { ready: load(false) };
})(typeof window !== 'undefined' ? window : globalThis);
