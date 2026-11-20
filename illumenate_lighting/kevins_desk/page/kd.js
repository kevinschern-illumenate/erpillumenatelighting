/* Kevin's Desk, Phase 1: NOW bar, today's schedule, week themes.
   Inlined into /kd/<slug> by templates/pages/kevins_desk.py (never served from /assets).
   Boot data: window.KD_BOOT = { user, first_name, schedule: kevins_desk.schedule.payload(), command_center }.
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

  $('kdwho').textContent = `Signed in as ${BOOT.user}`;
  if (BOOT.command_center) $('kdcc').href = BOOT.command_center;
  tick();
  root.setInterval(tick, 15000);
  doc.addEventListener('visibilitychange', () => { if (!doc.hidden) tick(); });
})(typeof window !== 'undefined' ? window : globalThis);
