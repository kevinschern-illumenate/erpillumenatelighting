/* ilLumenate Command Center v9 — base v2/v3 by Claude, Nov 17 2026.
   v4: Workbench. v5: Executive overview, Project review mode, saved views, activity feed, print.
   v6: Meeting agenda (weekly meeting, items linked to any Command Center record).
   v7: Pipeline restructure: Design stage before Quotes, portal requests inside their stages
       (Requests tab retired), Service after Shipping, Inbox as a help desk portal.
   v8: Purchasing desk (flow strip, lanes for requests / quotes / POs / shipments / bills, landed cost) from
       the app endpoint purchasing_board.get_board; Catalog tab (the Catalog Builder embedded, kept alive across
       tabs); Workbench ilLumenate area (every app doctype, grouped), child tables, builder hand-off.
   v9: Manufacturing "Flow" tab (sales orders → work orders → picks → shipping, with the warehouse's to-do list) and the
       Shipping pick list, from the app endpoint warehouse_flow.get_flow. The workbook views stay as reports.
   v10: Manufacturing "Labels" (the print station: batches per roll, confirm before Printed) and "Reel count" tabs, from
       the app endpoints labels.* and reels.*; hidden unless their flag is on in ilL-Production-Settings.
   Workbench/Executive/Review feed: /api/method/ill_cc_gateway (Server Script "ilL Command Center Gateway").
   Original header: ilLumenate Command Center v2 — live page on ERPNext. Built by Claude, Nov 17 2026.
   Data: /api/method/ill_command_center (Server Script "ilL Command Center API", read-only).
   Writes (signed-in users only): ToDo create/close, draft Material Request. Nothing is submitted. */
(function () {
  const API = '/api/method/ill_command_center';
  const root = document.getElementById('cc'); if (!root) return;
  const $ = s => root.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const slug = s => String(s).toLowerCase().replace(/ /g, '-');
  const docUrl = (dt, name) => slug(dt) === 'hd-ticket' ? `/helpdesk/tickets/${encodeURIComponent(name)}` : `/app/${slug(dt)}/${encodeURIComponent(name)}`;
  const link = (dt, name, label) => name ? `<a target="_blank" rel="noopener" href="${docUrl(dt, name)}">${esc(label || name)}</a>` : '';
  const cust = c => c ? link('customer', c) : '<span class="calc">—</span>';
  const money = v => v == null ? '—' : (v < 0 ? '−' : '') + '$' + Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
  const kfmt = v => Math.abs(v) >= 1000 ? '$' + (v / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1) + 'K' : '$' + Math.round(v);
  const fmtd = d => d ? new Date(String(d).slice(0, 10) + 'T12:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
  const badge = (t, k) => `<span class="badge ${k}">${esc(t)}</span>`;
  const sdot = (t, k) => `<span class="st"><span class="dot ${k}"></span>${esc(t)}</span>`;
  const short = s => String(s || '').replace('ilL-SAL-ORD-', '').replace('ilL-ACC-SINV-', '');
  const cookie = n => (document.cookie.split('; ').find(c => c.startsWith(n + '=')) || '').split('=').slice(1).join('=');
  const USER = decodeURIComponent(cookie('user_id') || 'Guest'), LOGGED = USER && USER !== 'Guest';
  const CSRF = () => (window.frappe && frappe.csrf_token && frappe.csrf_token !== 'None') ? frappe.csrf_token : null;
  const SYS = /api|worker|integration|^sales@|^info@|^hi@|^administrator$|^guest$/i;
  const PCOL = ['#2a78d6', '#eb6834', '#1baf7a', '#6250d6', '#e87ba4', '#008300', '#eda100'];
  const S = { view: (location.hash || '#pipeline').slice(1), q: '', person: '', source: '', status: '', mine: false, meeting: false, showDone: false, limit: 30 };
  let D = null, NAMES = {}, SHORT = {}, COLOR = {}, TEAM = [], TODAY = '';

  /* ---------------- data ---------------- */
  function lockScreen(kind) {
    root.classList.add('locked'); $('#ccnav').innerHTML = ''; $('#ccstamp').textContent = 'Restricted';
    $('#ccmain').innerHTML = `<div class="lock"><div class="lock-i">🔒</div><h1>${kind === 'login' ? 'Log in to view the Command Center' : 'You don\'t have access yet'}</h1>
      <p>${kind === 'login' ? 'This page is only visible to selected ilLumenate team members. Log in with your ERPNext account to continue.' : `You're signed in as <b>${esc(USER)}</b>, but this account isn't on the Command Center list. Ask Kevin to add the <b>Command Center Viewer</b> role to your user.`}</p>
      ${kind === 'login' ? '<a class="cc-btn primary" href="/login?redirect-to=/command-center" style="text-decoration:none;display:inline-flex">Log in</a>' : '<a class="cc-btn soft" href="/app" style="text-decoration:none;display:inline-flex">Go to ERPNext</a>'}</div>`;
  }
  async function load(manual) {
    const b = $('#ccrefresh');
    if (manual) { b.disabled = true; b.classList.add('spinning'); }
    try {
      const r = await fetch(API + '?_=' + Date.now(), { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (r.status === 403 || (!LOGGED && !r.ok)) { lockScreen('login'); return; }
      if (!r.ok) { let msg = ''; try { const jj = await r.json(); msg = JSON.parse(JSON.parse(jj._server_messages)[0]).message; } catch (e) { }
        if (/access/i.test(msg)) { lockScreen('denied'); return; } throw new Error('ERPNext answered ' + r.status); }
      root.classList.remove('locked');
      // a manual Refresh also re-reads access (catalog tab), so a new role shows without reloading the page
      if (manual) WHO = null;
      D = (await r.json()).message; prep(); PL.stale = true; render(); whoami();
      if (manual) toast('Up to date with ERPNext');
    } catch (e) { $('#ccmain').innerHTML = `<div class="err">Couldn't load data from ERPNext: ${esc(e.message)}. Try Refresh.</div>`; }
    finally { b.disabled = false; b.classList.remove('spinning'); }
  }
  function prep() {
    TODAY = D.today; D.noteNames = D.note_names || {};
    TEAM = D.users.filter(u => !SYS.test(u.name));
    D.users.forEach(u => { SHORT[u.name] = (u.full_name || u.name).split(' ')[0]; });
    TEAM.forEach((u, i) => { NAMES[u.name] = SHORT[u.name]; COLOR[u.name] = PCOL[i % PCOL.length]; });
    const seen = {}, todos = [];
    D.todos.forEach(x => {
      if (x.reference_type === 'Task') return;
      const raw = x.description || '';
      const m = raw.match(/\[(ad-hoc|email|review|cleanup|meeting)\] Owners:\s*([^<\n]*)/);
      const tag = m ? m[1] : ((x._user_tags || '').replace(/^,/, '') || null);
      const owners = m ? m[2].split(',').map(s => s.trim()).filter(Boolean) : [x.allocated_to];
      const tmp = document.createElement('div'); tmp.innerHTML = raw;
      const p = tmp.querySelector('p'); const title = (p ? p.textContent : tmp.textContent).trim();
      const mail = (raw.match(/href="(https:\/\/mail\.google\.com[^"]+)"/) || [])[1];
      let notes = ''; if (p) { p.remove(); notes = tmp.textContent.replace(/\[(ad-hoc|email|review|cleanup|meeting)\] Owners:.*$/s, '').replace('Email thread (kevins@ inbox): open in Gmail', '').trim(); }
      const nice = title.replace(/^Assignment for (.+?) (ilL-SAL-ORD-)?(\S.*)$/, (_, dt, p, n) => dt + ' ' + n);
      const key = tag ? title : x.name;
      if (seen[key]) { seen[key].ids.push(x.name); return; }
      const row = { id: x.name, ids: [x.name], title: nice || '(no description)', notes, owners, due: x.date, priority: x.priority,
        source: tag === 'email' ? 'kevins@' : tag === 'ad-hoc' ? 'ad hoc' : tag === 'meeting' ? 'meeting' : 'ERPNext', tag, mail: mail ? mail.replace(/&amp;/g, '&') : null,
        url: '/app/todo/' + x.name, ref: x.reference_type ? { dt: x.reference_type, name: x.reference_name } : null, private: tag === 'email', kind: 'todo' };
      seen[key] = row; todos.push(row);
    });
    D.T = todos;
    D.tasks.forEach(t => { t.owners = JSON.parse(t._assign || '[]'); t.exp_end_date = t.exp_end_date ? String(t.exp_end_date).slice(0, 10) : null; });
    D.tk.forEach(t => { t.assignedL = JSON.parse(t.assigned || '[]'); });
    prepProjects(); prepPipe();
  }
  function allTasks() {
    const t = D.T.map(x => ({ ...x, status: x.due && x.due < TODAY ? 'Overdue' : 'Open' }));
    D.tasks.forEach(x => t.push({ id: x.name, ids: [], title: x.subject, owners: x.owners, due: x.exp_end_date, priority: x.priority, source: 'ERPNext', tag: 'project',
      status: x.exp_end_date && x.exp_end_date < TODAY ? 'Overdue' : 'Open', url: '/app/task/' + x.name, ref: { dt: 'Project', name: x.project }, kind: 'task' }));
    D.tk.filter(x => x.status === 'Open').forEach(x => t.push({ id: 'HD-' + x.name, ids: [], title: 'Help desk ' + x.name + ': ' + (x.subject || ''), owners: x.assignedL, due: null,
      priority: x.age > 2 ? 'High' : 'Medium', source: 'sales@ (help desk)', status: x.age > 2 ? 'Overdue' : 'Open', url: '/helpdesk/tickets/' + x.name, kind: 'ticket', age: x.age }));
    return t.filter(x => !(S.meeting && x.private));
  }
  const passes = x => (!S.person || (x.owners || []).includes(S.person)) && (!S.mine || (x.owners || []).includes(USER)) &&
    (!S.source || x.source === S.source) && (!S.status || x.status === S.status) && (!S.q || JSON.stringify(x).toLowerCase().includes(S.q));
  const rowOK = o => !S.q || JSON.stringify(o).toLowerCase().includes(S.q);
  const avatar = e => `<span class="avatar" title="${esc(SHORT[e] || e)}" style="background:${COLOR[e] || '#98a2b3'}">${esc((SHORT[e] || e || '?').slice(0, 1).toUpperCase())}</span>`;
  const avs = list => (list || []).length ? `<span class="avs">${list.map(avatar).join('')}</span>` : '<span class="calc">Unassigned</span>';

  /* ---------------- charts ---------------- */
  function tipOn(el, html, e) { const t = el.querySelector('.tip'), b = el.getBoundingClientRect(); t.innerHTML = html; t.style.display = 'block';
    t.style.left = Math.max(0, Math.min(e.clientX - b.left + 14, b.width - t.offsetWidth - 4)) + 'px'; t.style.top = (e.clientY - b.top - t.offsetHeight - 10) + 'px'; }
  const tipOff = el => el.querySelector('.tip').style.display = 'none';
  const niceStep = max => { const raw = max / 4, p = Math.pow(10, Math.floor(Math.log10(raw || 1))), n = raw / p; return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * p; };
  function vbars(el, cats, series, o = {}) {
    if (!el) return;
    const W = el.clientWidth || 600, H = o.h || 240, pl = 44, pb = 28, pt = 26;
    const max = Math.max(o.target || 0, ...series.flatMap(s => s.values), 1) * 1.1, y = v => pt + (H - pt - pb) * (1 - v / max);
    const gw = (W - pl - 6) / cats.length, gap = 3, bw = Math.min(30, (gw * 0.62 - gap * (series.length - 1)) / series.length);
    let s = ''; const step = niceStep(max);
    for (let v = 0; v <= max; v += step) s += `<line x1="${pl}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="${v ? '#f2f4f7' : '#eaecf0'}"/><text x="${pl - 8}" y="${y(v) + 4}" font-size="11" text-anchor="end" fill="#98a2b3">${o.fmt ? o.fmt(v) : v}</text>`;
    cats.forEach((c, i) => {
      const x0 = pl + i * gw + (gw - (bw * series.length + gap * (series.length - 1))) / 2;
      series.forEach((sr, j) => { const v = Math.max(sr.values[i] || 0, 0), x = x0 + j * (bw + gap), top = y(v), h = H - pb - top, r = Math.min(4, h, bw / 2);
        if (h > 0) s += `<path d="M${x},${H - pb}V${top + r}q0,-${r} ${r},-${r}h${bw - 2 * r}q${r},0 ${r},${r}V${H - pb}Z" fill="${sr.color}" ${o.dim && i !== cats.length - 1 ? 'opacity=".85"' : ''}/>`;
        if (o.labels && v) s += `<text x="${x + bw / 2}" y="${top - 6}" font-size="11" font-weight="600" text-anchor="middle" fill="#475467">${o.fmt ? o.fmt(v) : v}</text>`; });
      s += `<text x="${pl + i * gw + gw / 2}" y="${H - 8}" font-size="11.5" text-anchor="middle" fill="#98a2b3">${esc(c)}</text><rect x="${pl + i * gw}" y="${pt}" width="${gw}" height="${H - pt - pb}" fill="transparent" data-i="${i}"/>`;
    });
    if (o.target) s += `<line x1="${pl}" x2="${W}" y1="${y(o.target)}" y2="${y(o.target)}" stroke="#f39c12" stroke-width="1.5" stroke-dasharray="4 4"/><text x="${W - 2}" y="${y(o.target) - 8}" font-size="11" text-anchor="end" fill="#b54708" font-weight="500">${esc(o.targetLabel || '')}</text>`;
    el.innerHTML = (series.length > 1 ? `<div class="legend" style="margin-bottom:8px">${series.map(sr => `<span><i style="background:${sr.color}"></i>${esc(sr.name)}</span>`).join('')}</div>` : '') + `<svg width="100%" height="${H}" style="display:block">${s}</svg><div class="tip"></div>`;
    el.querySelectorAll('rect[data-i]').forEach(r => { r.onmousemove = e => { const i = +r.dataset.i; tipOn(el, `<b>${esc(cats[i])}</b><br>` + series.map(sr => `${esc(sr.name)}: ${o.fmt ? o.fmt(sr.values[i] || 0) : sr.values[i] || 0}`).join('<br>') + (o.extra ? o.extra(i) : ''), e); }; r.onmouseleave = () => tipOff(el); });
  }
  function hbars(rows, o = {}) {
    const max = o.max || Math.max(...rows.map(r => Math.abs(r.value)), 1);
    if (!rows.length) return '<div class="empty">Nothing to show</div>';
    return `<div style="--lw:${o.lw || '150px'}">${rows.map(r => `<div class="hbar" title="${esc(r.title || '')}"><div class="lb">${r.html || esc(r.label)}</div>
      <div class="tr"><i style="width:${Math.max(2, Math.min(100, Math.abs(r.value) / max * 100))}%;background:${r.color || o.color || '#2a78d6'}"></i></div><div class="vl">${o.fmt ? o.fmt(r.value) : r.value}</div></div>`).join('')}</div>`;
  }
  function dbars(rows, fmt) {
    if (!rows.length) return '<div class="empty">Nothing to show</div>';
    return `<div class="legend" style="margin-bottom:8px"><span><i style="background:#eb6834"></i>Down</span><span><i style="background:#2a78d6"></i>Up</span><span class="calc">Bars are capped at ±100%; labels show the real change</span></div>` +
      rows.map(r => { const w = Math.min(100, Math.abs(r.value)) / 2; return `<div class="hbar" style="--lw:190px" title="${esc(r.title || '')}"><div class="lb">${r.html}</div>
      <div style="position:relative;height:10px;background:var(--line2);border-radius:6px"><div style="position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:#d0d5dd"></div>
      <i style="position:absolute;top:0;height:100%;border-radius:6px;${r.value < 0 ? `right:50%;width:${w}%` : `left:50%;width:${w}%`};background:${r.value < 0 ? '#eb6834' : '#2a78d6'}"></i></div>
      <div class="vl" style="color:${r.value <= -40 ? 'var(--badt)' : 'var(--ink2)'}">${fmt(r.value)}</div></div>`; }).join('');
  }
  function ring(val, goal, color, sub, size = 132) {
    const n = typeof val === 'number', pct = n ? Math.min(1, goal ? val / goal : 0) : 0, R = size / 2 - 10, C = 2 * Math.PI * R, c = size / 2;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex:none"><circle cx="${c}" cy="${c}" r="${R}" fill="none" stroke="#f2f4f7" stroke-width="10"/>
      ${pct ? `<circle cx="${c}" cy="${c}" r="${R}" fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round" stroke-dasharray="${C * pct} ${C}" transform="rotate(-90 ${c} ${c})"/>` : ''}
      <text x="${c}" y="${c + 2}" text-anchor="middle" font-size="${size / 4.6}" font-weight="700" fill="#101828" letter-spacing="-1">${esc(val)}</text><text x="${c}" y="${c + size / 6.5}" text-anchor="middle" font-size="11.5" fill="#98a2b3">${esc(sub)}</text></svg>`;
  }
  const meter = (pct, mark, color) => `<div class="meter"><i style="width:${Math.min(100, Math.max(0, pct * 100))}%;${color ? 'background:' + color : ''}"></i>${mark != null ? `<b style="left:${Math.min(100, mark * 100)}%" title="pace marker"></b>` : ''}</div>`;
  const stat = (eyebrow, v, d, cls = '', extra = '') => `<div class="card stat"><div class="eyebrow">${eyebrow}</div><div class="v ${cls}">${v}</div>${d ? `<div class="d">${d}</div>` : ''}${extra}</div>`;
  const card = (title, sub, body, cls = '', right = '') => `<div class="card ${cls}"><div class="card-h"><div><h2>${title}</h2>${sub ? `<div class="sub">${sub}</div>` : ''}</div>${right}</div>${body}</div>`;
  const tableCard = (title, sub, head, rows, right = '', span = 's12') => `<div class="card flush ${span}"><div class="card-h"><div><h2>${title}</h2>${sub ? `<div class="sub">${sub}</div>` : ''}</div>${right}</div>
    <div class="tw"><table><thead><tr>${head.map(h => `<th class="${h.startsWith('#') ? 'num' : ''}">${h.replace(/^#/, '')}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${head.length}" class="empty">Nothing here right now</td></tr>`}</tbody></table></div></div>`;

  /* ---------------- metrics ---------------- */
  function M() {
    const day = +TODAY.slice(8, 10), dim = new Date(+TODAY.slice(0, 4), +TODAY.slice(5, 7), 0).getDate(), pace = day / dim;
    const newThis = D.newd.filter(x => x.month === TODAY.slice(0, 7));
    const firm = D.purch.filter(r => r.short_firm > 0), late = firm.filter(r => r.late);
    const past = D.ship.filter(s => s.delivery && s.delivery < TODAY);
    const dup = D.mfg.filter(w => w.flag !== 'Active'), act = D.mfg.filter(w => w.flag === 'Active');
    const openReq = D.reqs.filter(r => r.open), oldReq = openReq.filter(r => r.age > 2);
    const tOpen = D.tk.filter(t => t.status === 'Open'), tOld = tOpen.filter(t => t.age > 2);
    const tasks = allTasks(), overdue = tasks.filter(x => x.status === 'Overdue');
    const ago = n => { const t = new Date(TODAY + 'T12:00'); t.setDate(t.getDate() - n); return t.toISOString().slice(0, 10); };
    const tw = D.tk.filter(t => t.created >= ago(7)), lw = D.tk.filter(t => t.created >= ago(14) && t.created < ago(7));
    const recN = ((D.notes['Command Center – Recommendations'] || '').match(/<li/g) || []).length;
    return { pace, newThis, new3k: newThis.filter(x => x.this_month >= 3000), firm, late, past, dup, act, openReq, oldReq, tOpen, tOld, tasks, overdue, tw, lw, recN,
      spifQ: D.spif.filter(x => x.eligible), goalPace: Math.round(D.fin.goal * pace) };
  }
  function phases(m) {
    const f = D.fin;
    return [
      { k: 'overview', n: 'Overview' },
      { k: 'score', n: 'Break-even', v: `${m.newThis.length}/8`, l: `New dealers this month · ${m.new3k.length} at $3K+`, s: m.newThis.length >= 8 * m.pace ? ['On pace', 'good'] : m.newThis.length >= 4 * m.pace ? ['Behind', 'warn'] : ['Act now', 'bad'], p: m.newThis.length / 8, mark: m.pace },
      (() => { const u = PU.data && PU.data.summary; if (!u) return { k: 'purch', n: 'Purchasing', v: m.firm.length, l: `Lines short · ${m.late.length} past order-by`, s: m.late.length ? ['Act now', 'bad'] : m.firm.length ? ['Watch', 'warn'] : ['Clear', 'good'], c: m.firm.length };
        const n = (u.to_order || {}).count || 0, late = (u.to_order || {}).late || 0, od = (u.pos || {}).overdue || 0;
        return { k: 'purch', n: 'Purchasing', v: n, l: `Lines short · ${late} past order-by · ${od} PO${od === 1 ? '' : 's'} overdue`, s: late || od ? ['Act now', 'bad'] : n ? ['Watch', 'warn'] : ['Clear', 'good'], c: n }; })(),
      { k: 'mfg', n: 'Manufacturing', v: m.act.length, l: `Active work orders · ${m.dup.length} duplicate or stale`, s: m.dup.length ? ['Clean up', 'warn'] : ['OK', 'good'] },
      { k: 'ship', n: 'Shipping', v: `${m.past.length}/${D.ship.length}`, l: 'Open orders past delivery date', s: m.past.length > 2 ? ['Act now', 'bad'] : m.past.length ? ['Watch', 'warn'] : ['On time', 'good'], p: D.ship.length ? 1 - m.past.length / D.ship.length : 1, pc: '#12b76a', c: m.past.length },
      { k: 'req', n: 'Requests', v: m.openReq.length, l: `Open · ${m.oldReq.length} older than 2 business days`, s: m.oldReq.length ? ['Follow up', 'warn'] : ['OK', 'good'], c: m.openReq.length },
      { k: 'inbox', n: 'Inbox', v: m.tw.length, l: `Tickets this week (last week ${m.lw.length}) · ${m.tOld.length} waiting > 2 days`, s: m.tOld.length > 3 ? ['Act now', 'bad'] : m.tOld.length ? ['Watch', 'warn'] : ['OK', 'good'], c: m.tOpen.length },
      { k: 'fin', n: 'Finance', v: kfmt(f.mtd), l: `Invoiced this month · on-pace target ${kfmt(m.goalPace)}`, s: f.mtd >= m.goalPace ? ['On pace', 'good'] : f.mtd >= m.goalPace * 0.6 ? ['Behind', 'warn'] : ['Act now', 'bad'], p: f.mtd / f.goal, mark: m.pace },
      { k: 'tasks', n: 'Tasks', v: m.overdue.length, l: `Overdue of ${m.tasks.length} open tasks`, s: m.overdue.length > 10 ? ['Act now', 'bad'] : m.overdue.length ? ['Watch', 'warn'] : ['Clear', 'good'], c: m.overdue.length },
      { k: 'projects', n: 'Projects', v: D.projects.filter(p => p.tasks && p.tasks.length && p.status === 'Open').length, l: `Active projects · ${D.ptasks.filter(t => t.status !== 'Completed' && t.exp_end_date && String(t.exp_end_date).slice(0, 10) < TODAY).length} overdue tasks`, s: D.ptasks.some(t => t.status !== 'Completed' && t.exp_end_date && String(t.exp_end_date).slice(0, 10) < TODAY) ? ['Behind', 'warn'] : ['On track', 'good'] },
      { k: 'rec', n: 'Recommendations', v: m.recN, l: 'Actions the data suggests', s: ['Review', 'info'] },
    ];
  }
  
  /* ---------------- pipeline config ----------------
     One list drives the stepper, the router, the tab highlight and the quick links: reorder here.
     Mirrors the dealer portal: Design → Quotes → Sales orders → … → Shipping → Service. */
  const STAGES = [
    { k: 'pipeline', n: 'Overview' }, { k: 'design', n: 'Design' }, { k: 'quotes', n: 'Quotes' }, { k: 'orders', n: 'Sales orders' },
    { k: 'purch', n: 'Purchasing' }, { k: 'mfg', n: 'Manufacturing' }, { k: 'ship', n: 'Shipping' }, { k: 'service', n: 'Service' },
  ];
  const PIPE = STAGES.map(x => x.k);
  // retired pages → their new home (old bookmarks and links keep working)
  const REDIRECT = { requests: 'pipeline' };

  /* quick links to the ERPNext doctype pages behind each section */
  const QL = {
    pipeline: [['Customers', '/app/customer'], ['Sales orders', '/app/sales-order'], ['Sales invoices', '/app/sales-invoice'], ['Sales partners (reps)', '/app/sales-partner'], ['Customer groups (tiers)', '/app/customer-group']],
    design: [['Projects', '/app/ill-project'], ['Fixture schedules', '/app/ill-project-fixture-schedule'], ['Drawing requests', '/app/ill-document-request'], ['Drawing reviews', '/app/ill-drawing-review'], ['Help desk', '/helpdesk/tickets']],
    quotes: [['+ New quotation', '/app/quotation/new'], ['Quotations', '/app/quotation'], ['Quote requests', '/app/ill-quote-request'], ['Quote offers', '/app/ill-quote-offer'], ['Help desk', '/helpdesk/tickets']],
    orders: [['+ New sales order', '/app/sales-order/new'], ['Sales orders', '/app/sales-order'], ['Order requests', '/app/ill-order-intake'], ['Order changes', '/app/ill-order-change'], ['Order tickets', '/helpdesk/tickets'], ['Delivery notes', '/app/delivery-note']],
    so: [['Sales orders', '/app/sales-order'], ['+ New delivery note', '/app/delivery-note/new'], ['+ New sales invoice', '/app/sales-invoice/new']],
    purch: [['+ New material request', '/app/material-request/new'], ['+ New purchase order', '/app/purchase-order/new'], ['Material requests', '/app/material-request'], ['RFQs', '/app/request-for-quotation'], ['Supplier quotations', '/app/supplier-quotation'], ['Purchase orders', '/app/purchase-order'], ['Inbound shipments', '/app/ill-inbound-shipment'], ['Purchase receipts', '/app/purchase-receipt'], ['Purchase invoices', '/app/purchase-invoice'], ['Landed cost vouchers', '/app/landed-cost-voucher'], ['Suppliers', '/app/supplier'], ['Customs tariff numbers', '/app/customs-tariff-number'], ['Stock balance', '/app/query-report/Stock%20Balance'], ['Items', '/app/item']],
    mfg: [['+ New work order', '/app/work-order/new'], ['Work orders', '/app/work-order'], ['Material requests (manufacture)', '/app/material-request?material_request_type=Manufacture'], ['BOMs', '/app/bom'], ['Production plans', '/app/production-plan'], ['Stock entries', '/app/stock-entry']],
    ship: [['+ New delivery note', '/app/delivery-note/new'], ['Delivery notes', '/app/delivery-note'], ['Shipments', '/app/shipment'], ['Sales orders to deliver', '/app/sales-order?status=%5B%22in%22%2C%5B%22To%20Deliver%22%2C%22To%20Deliver%20and%20Bill%22%5D%5D']],
    service: [['Help desk', '/helpdesk/tickets'], ['Account requests', '/app/ill-account-request'], ['Knowledge base', '/helpdesk/kb']],
    inbox: [['Help desk', '/helpdesk/tickets'], ['Ticket types (setup)', '/app/hd-ticket-type']],
    finance: [['+ New sales invoice', '/app/sales-invoice/new'], ['Sales invoices', '/app/sales-invoice'], ['Accounts receivable', '/app/query-report/Accounts%20Receivable'], ['Payment entries', '/app/payment-entry'], ['+ New purchase invoice', '/app/purchase-invoice/new'], ['Purchase invoices (bills)', '/app/purchase-invoice'], ['QuickBooks sync log', '/app/ill-qbo-sync-log']],
    work: [['Projects', '/app/project'], ['Tasks', '/app/task'], ['To-dos', '/app/todo?status=Open'], ['Project templates', '/app/project-template']],
    tasks: [['To-dos', '/app/todo?status=Open'], ['Tasks', '/app/task'], ['Projects', '/app/project']],
    project: [['Projects', '/app/project'], ['Tasks', '/app/task']],
    rec: [['Notes', '/app/note'], ['This week note', null], ['Recommendations note', null]],
  };
  let CUR_LINKS = null;
  function qlinks(k) {
    let l = QL[k]; if (!l) return '';
    if (k === 'rec') l = [['All notes', '/app/note'], ['Edit “This week”', '/app/note/' + ((D.noteNames || {})['Command Center – This week'] || '')], ['Edit “Recommendations”', '/app/note/' + ((D.noteNames || {})['Command Center – Recommendations'] || '')]];
    return `<div class="qlinks"><span class="small">In ERPNext:</span>${l.map(([n, u]) => `<a class="ql ${n.startsWith('+') ? 'new' : ''}" target="_blank" rel="noopener" href="${u}">${esc(n)}${n.startsWith('+') ? '' : ' <span>↗</span>'}</a>`).join('')}${LOGGED ? '' : '<span class="calc">ERPNext asks you to log in</span>'}</div>`;
  }

  let CUR_STEP = null, CUR_M = null;
  const header = (title, desc, right = '') => `<div class="ph-h"><div><h1>${title}</h1>${desc ? `<p>${desc}</p>` : ''}</div>${right}</div>` + (CUR_LINKS ? (() => { const x = qlinks(CUR_LINKS); CUR_LINKS = null; return x; })() : '') + (CUR_STEP ? stepper(CUR_M, CUR_STEP) : '') + (WORK_SEG ? workSeg() : '');
  const noteLink = (t, lbl) => link('note', (D.noteNames || {})[t], lbl || 'Edit in ERPNext');

  /* ---------------- views ---------------- */
  const V = {};
  const drv = docs => { const wos = docs.filter(x => x.src === 'Work Order'), sos = docs.filter(x => x.src !== 'Work Order');
    return sos.map(x => link('sales-order', x.doc, short(x.doc)) + (x.draft ? ' <span class="calc">(draft)</span>' : '')).join('<br>') +
      (wos.length ? (sos.length ? '<br>' : '') + (wos.length === 1 ? link('work-order', wos[0].doc) : `<span title="${esc(wos.map(w => w.doc).join(', '))}">${link('work-order', wos[0].doc, wos.length + ' work orders')}</span>`) : ''); };
  // the older feed's shortage list: the Purchasing page before v8, and its fallback when the board can't load
  V.purchOld = (m, bare) => {
    const rows = D.purch.filter(rowOK), firm = rows.filter(r => r.short_firm > 0), maybe = rows.filter(r => r.short_firm <= 0);
    const byGroup = {}; firm.forEach(r => { byGroup[r.group || 'Other'] = (byGroup[r.group || 'Other'] || 0) + 1; });
    const tr = (r, q) => `<tr><td>${link('item', r.item)}<div class="m">${esc(r.group || '')}${r.lead_src !== 'item' && r.lead ? ` · lead time: ${esc(r.lead_src)}` : ''}</div></td>
      <td class="num"><b>${+q.toFixed(2)}</b><div class="m">${+r.on_hand.toFixed(1)} on hand · ${+r.on_order.toFixed(1)} on order</div></td>
      <td>${r.supplier ? link('supplier', r.supplier) : badge('No supplier', 'warn')}<div class="m">${r.lead ? r.lead + '-day lead' : 'No lead time'}</div></td>
      <td>${r.order_by ? (r.late ? badge('Late · ' + fmtd(r.order_by), 'bad') : fmtd(r.order_by)) : '—'}<div class="m">Needed ${fmtd(r.need_by)}</div></td>
      <td style="white-space:nowrap">${[r.draft_po && link('purchase-order', r.draft_po, 'PO ' + r.draft_po.split('-').pop()), r.mr && link('material-request', r.mr, 'MR ' + r.mr.replace(/^MAT-MR-\d{4}-/, ''))].filter(Boolean).join('<br>') || '<span class="calc">None</span>'}</td>
      <td style="white-space:nowrap">${drv(r.docs)}</td>
      <td class="num">${!r.draft_po && !r.mr && !r.manufactured ? (LOGGED ? `<button class="cc-btn soft" data-mr="${esc(r.item)}">Draft MR</button>` : `<a class="calc" href="/login?redirect-to=/command-center">Log in</a>`) : ''}</td></tr>`;
    const head = ['Item', '#Short', 'Supplier', 'Order by', 'Draft PO / MR', 'Driven by', ''];
    return (bare ? '' : header('Purchasing', 'What we need to order, worked back from each order\'s required date using lead times.')) + `
      <div class="callout"><div>ERPNext doesn't reflect the shop floor yet: work orders stay in Draft, and no item has a reorder level or default supplier. <b>Check this list with Ryan before ordering.</b> Where an item has no lead time, the category default is used (extrusions 10 days, tape/neon/sheet 35, power and controls 28). For power supplies, check the shelf for universal units first.</div></div>
      <div class="grid" style="margin-bottom:20px">
        ${stat('Lines short', firm.length, 'Against submitted orders').replace('card stat', 'card stat s3')}
        ${stat('Past order-by date', m.late.length, 'Should already be ordered', m.late.length ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('No draft PO or MR', firm.filter(r => !r.draft_po && !r.mr).length, 'Not started yet').replace('card stat', 'card stat s3')}
        ${stat('No supplier on file', firm.filter(r => !r.supplier).length, 'Needs a supplier set').replace('card stat', 'card stat s3')}
        ${card('Short lines by category', '', hbars(Object.entries(byGroup).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k, value: v })), { lw: '170px' }), 's12')}
      </div>
      <div class="grid">${tableCard('What to order', 'Short = open demand from submitted orders and active work orders, minus stock on hand and on order. Draft MR creates an unsubmitted Material Request for Stores - ilL.', head, firm.map(r => tr(r, r.short_firm)))}
      <div class="card flush s12"><details class="more"><summary>Only short if the draft sales orders go ahead (${maybe.length})</summary><div class="tw" style="border-top:1px solid var(--line)"><table><thead><tr>${head.map(h => `<th>${h.replace('#', '')}</th>`).join('')}</tr></thead><tbody>${maybe.map(r => tr(r, r.short_all)).join('')}</tbody></table></div></details></div></div>`;
  };
  /* ---------------- purchasing desk (v8) ----------------
     One place for the whole buying cycle: what to order → requests → vendor quotes → purchase orders →
     inbound shipments → receipts → bills → landed cost. Data: the app endpoint purchasing_board.get_board
     (read-only, money blanked without a Finance role). Every button creates a DRAFT through a narrow app
     endpoint and returns its name; submitting stays in the desk. Until the first fetch returns, or if it
     fails, the page shows the older feed's shortage list (D.purch). */
  const PU_API = 'illumenate_lighting.illumenate_lighting.api.purchasing_board.';
  const PU = { data: null, err: null, busy: false, at: 0, tab: 'overview', view: 'lanes', showDone: false, sel: {} };
  const PU_TABS = [['overview', 'Overview'], ['order', 'To order'], ['requests', 'Requests'], ['quotes', 'Vendor quotes'], ['pos', 'Purchase orders'], ['shipments', 'Shipments'], ['receipts', 'Receipts'], ['bills', 'Bills'], ['landed', 'Landed cost'], ['suppliers', 'Suppliers']];
  try { const t = localStorage.getItem('cc.purch.tab.' + USER); if (t && PU_TABS.some(x => x[0] === t)) PU.tab = t; } catch (e) { }
  const puPost = (m, args) => call(PU_API + m, args || {});
  const puM = v => v == null ? '<span class="calc">—</span>' : money(v);
  const puK = v => v == null ? '—' : kfmt(v);
  const puPct = v => v == null ? '<span class="calc">—</span>' : (Math.round(v * 10) / 10) + '%';
  const puDays = n => n == null ? '' : `${n}d`;
  const puShort = () => PU.data ? PU.data.shortages : D.purch;
  const puDesk = (dt, n, l) => n ? link(dt, n, l || n) : '';
  const puChips = (dt, list, lbl) => (list || []).map(n => `<span class="qchip">${esc(lbl)} ${link(dt, n, String(n).split('-').slice(-1)[0])}</span>`).join('');
  const puLead = (d, src) => d == null ? badge('No lead time', 'warn') : `<span class="pu-lead" title="Lead time source: ${esc(src || '')}">${d}d${src ? ' · ' + esc(src) : ''}</span>`;
  const puEta = r => !r.eta ? '<span class="calc">No ETA</span>' : r.overdue ? badge('Overdue · ' + fmtd(r.eta), 'bad') : r.will_miss ? `<span class="badge warn" title="${esc(r.will_miss_so ? 'Arrives after ' + r.will_miss_so + ' needs it' : 'Arrives after it is needed')}">ETA ${fmtd(r.eta)} · late for ${r.will_miss_so ? 'order ' + esc(short(r.will_miss_so)) : 'its order'}</span>` : `<span class="small">ETA ${fmtd(r.eta)}${r.eta_src ? ` <span class="calc">(${esc(r.eta_src)})</span>` : ''}</span>`;
  const PU_MODE = { 'Ocean FCL': '⛴', 'Ocean LCL': '⛴', Air: '✈', Courier: '✉', LTL: '⛟', FTL: '⛟', 'Vendor delivers': '⇢', 'Will call': '⌂' };
  const PU_COST_TYPES = ['Freight', 'Duty', 'Tariff (additional)', 'MPF / HMF', 'Brokerage', 'Insurance', 'Drayage / delivery', 'Storage / demurrage', 'Sales / use tax', 'Other'];
  const PU_COST_COL = ['#2a78d6', '#eb6834', '#e87ba4', '#6250d6', '#1baf7a', '#eda100', '#008300', '#98a2b3', '#475467', '#d0d5dd'];
  const PU_VSTAT = ['Not sent', 'Sent', 'Confirmed', 'In production', 'Shipped', 'Delivered', 'Issue'];
  const PU_FREIGHT = ['', 'Ocean FCL', 'Ocean LCL', 'Air', 'Courier', 'LTL', 'FTL', 'Vendor delivers', 'Will call'];
  const PU_SHIP_ST = ['Planned', 'Booked', 'In transit', 'At port / customs', 'Cleared', 'Out for delivery', 'Delivered', 'Costs final', 'Cancelled'];
  // [lane key, label, dot tone] per board
  const PU_LANES = {
    requests: [['draft', 'Draft', 'mute'], ['to_quote', 'To quote', 'warn'], ['quoted', 'Quoted', 'info'], ['ordered', 'Ordered', 'good'], ['receiving', 'Receiving', 'good']],
    quotes: [['rfq_draft', 'RFQ draft', 'mute'], ['awaiting_reply', 'Awaiting reply', 'warn'], ['quoted', 'Quoted', 'info'], ['expiring', 'Expiring soon', 'bad'], ['ordered', 'Ordered', 'good'], ['expired', 'Expired / lost', 'mute']],
    pos: [['draft', 'Draft', 'mute'], ['not_sent', 'Not sent', 'bad'], ['awaiting_confirmation', 'Awaiting confirmation', 'warn'], ['confirmed', 'Confirmed / in production', 'info'], ['in_transit', 'In transit', 'info'], ['partly_received', 'Partly received', 'warn'], ['to_bill', 'To bill', 'warn'], ['on_hold', 'On hold', 'bad'], ['done', 'Done', 'good']],
    shipments: [['planned', 'Planned', 'mute'], ['moving', 'Moving', 'info'], ['customs', 'At customs', 'warn'], ['arriving', 'Arriving', 'info'], ['delivered', 'Delivered · costs open', 'warn'], ['final', 'Costs final', 'good']],
    bills: [['draft', 'Draft', 'mute'], ['unpaid', 'Unpaid', 'warn'], ['overdue', 'Overdue', 'bad'], ['partly_paid', 'Partly paid', 'info'], ['paid', 'Paid (30 days)', 'good']],
  };
  const puLaneOf = (tab, r) => tab === 'quotes' && r.lane === 'lost' ? 'expired' : r.lane;
  function puBoard(tab, rows, cardFn, opts = {}) {
    const lanes = PU_LANES[tab].filter(l => !(l[0] === 'done' && !PU.showDone) && !(opts.hide || []).includes(l[0]));
    const cols = lanes.map(([k, n, tone]) => { const cs = rows.filter(r => puLaneOf(tab, r) === k);
      return `<div class="bcol${PU.lane === k && PU.laneTab === tab ? ' pu-hl' : ''}" data-pulane="${k}"><div class="lane-h"><span><span class="dot ${tone}"></span> ${esc(n)}</span><span class="ct">${cs.length}</span></div>${cs.map(cardFn).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`; });
    return `<div class="board pu-board" style="grid-template-columns:repeat(${lanes.length},minmax(220px,1fr))">${cols.join('')}</div>`;
  }
  const puBtn = (label, attrs, primary) => LOGGED && PU.data && PU.data.can_edit ? `<button type="button" class="cc-btn ${primary ? 'primary' : 'soft'}" ${attrs}>${label}</button>` : '';

  /* ---- flow strip: one tile per step, count + $ + a dot when the step holds a decision ---- */
  PU.flow = X => {
    const s = X.summary || {}, z = o => o || {}, dec = tab => (X.decisions || []).filter(d => d.tab === tab);
    const tiles = [
      ['order', 'To order', z(s.to_order).count + z(s.reorder).count, z(s.to_order).late ? `${z(s.to_order).late} past order-by` : `${z(s.reorder).count || 0} below reorder level`],
      ['requests', 'Requests', z(s.mrs).count, z(s.mrs).draft ? `${z(s.mrs).draft} draft` : 'material requests'],
      ['quotes', 'Vendor quotes', z(s.quotes).out, z(s.quotes).expiring ? `${z(s.quotes).expiring} expiring` : 'RFQs and quotes out'],
      ['pos', 'POs', z(s.pos).count, X.money ? puK(z(s.pos).amount) + ' open' : `${z(s.pos).not_sent || 0} not sent`],
      ['shipments', 'In transit', (z(s.shipments).moving || 0) + (z(s.shipments).customs || 0) + (z(s.shipments).arriving || 0), `${z(s.shipments).customs || 0} at customs`],
      ['receipts', 'Received', z(s.receipts).to_bill, 'to bill'],
      ['bills', 'Bills', z(s.bills).count, X.money ? puK(z(s.bills).unpaid_amount) + ' unpaid' : `${z(s.bills).overdue || 0} overdue`],
      ['landed', 'Landed cost', z(s.landed).needs_lcv, X.money && z(s.landed).est_open_amount ? puK(z(s.landed).est_open_amount) + ' to land' : 'need a voucher'],
    ];
    return `<div class="pu-flow no-print">${tiles.map(([k, n, c, sub], i) => { const d = dec(k), tone = d.some(x => x.tone === 'bad') ? 'bad' : d.length ? 'warn' : '';
      return `${i ? '<span class="pu-arrow" aria-hidden="true">→</span>' : ''}<button type="button" class="pu-step ${PU.tab === k ? 'on' : ''}" data-putab="${k}"><span class="pu-step-n">${esc(n)}${tone ? `<span class="dot ${tone}" title="${esc(d.map(x => x.count + ' ' + x.label).join('\n'))}"></span>` : ''}</span><span class="pu-step-v">${c == null || isNaN(c) ? 0 : c}</span><span class="pu-step-s">${esc(sub || '')}</span></button>`; }).join('')}</div>`;
  };

  PU.body = () => {
    const X = PU.data; PU.after = null;
    if (!X) {
      const fb = PU.err ? `<div class="callout"><div>The purchasing board couldn't load (${esc(PU.err)}). Showing the older shortage list.</div></div>` : '<div class="cc-loading"><span class="cc-spin"></span>Loading the purchasing desk…</div>';
      return fb + V.purchOld(CUR_M || M(), true) + `<div class="grid" style="margin-top:20px">${V.purch_low()}</div>`;
    }
    const tabs = `<div class="seg pu-tabs no-print">${PU_TABS.map(([k, n]) => `<button data-putab="${k}" class="${PU.tab === k ? 'on' : ''}">${n}</button>`).join('')}</div>`;
    const money0 = X.money ? '' : '<p class="small">Dollar figures need the Command Center Finance, Purchase Manager or Accounts Manager role.</p>';
    return PU.flow(X) + tabs + money0 + `<div id="pubody">${(PU[PU.tab] || PU.overview)(X)}</div>`;
  };

  /* ---- Overview: decisions, arriving next 14 days, spend by supplier, open PO $ by month of ETA ---- */
  PU.overview = X => {
    const dec = (X.decisions || []).filter(rowOK);
    const decs = dec.length ? `<div class="dec-grid">${dec.map(d => d.href
      // A decision with an href opens a Desk list (e.g. unlinked purchasing email) instead of a board tab.
      ? `<a class="dec pu-dec ${d.tone}" href="${esc(d.href)}" target="_blank" rel="noopener"><span class="n">${d.count}</span><span class="l">${esc(d.label)}</span></a>`
      : `<button type="button" class="dec pu-dec ${d.tone}" data-putab="${esc(d.tab)}" data-pulane="${esc(d.lane || '')}"><span class="n">${d.count}</span><span class="l">${esc(d.label)}</span></button>`).join('')}</div>` : '<div class="empty">Nothing late, stuck or expiring. 🎉</div>';
    const in14 = addDays(X.today, 14);
    const arr = [].concat(
      (X.pos || []).filter(p => p.docstatus === 1 && p.eta && p.eta <= in14 && !['done', 'to_bill'].includes(p.lane)).map(p => ({ k: 'PO', dt: 'purchase-order', name: p.name, who: p.supplier, eta: p.eta, late: p.overdue, amount: p.amount })),
      (X.shipments || []).filter(s => s.eta && s.eta <= in14 && ['planned', 'moving', 'customs', 'arriving'].includes(s.lane)).map(s => ({ k: 'Shipment', dt: 'ill-inbound-shipment', name: s.name, who: s.supplier || s.forwarder, eta: s.eta, late: s.eta < X.today, amount: s.goods_value, mode: s.mode })))
      .filter(rowOK).sort((a, b) => String(a.eta).localeCompare(String(b.eta)));
    const arrRows = arr.map(a => `<tr class="${a.late ? 'pu-row-late' : ''}"><td>${a.late ? badge(fmtd(a.eta), 'bad') : fmtd(a.eta)}</td><td>${esc(a.k)}${a.mode ? ' ' + (PU_MODE[a.mode] || '') : ''}</td><td>${link(a.dt, a.name)}</td><td>${esc(a.who || '')}</td><td class="num">${puM(a.amount)}</td></tr>`);
    const bySup = {}; (X.pos || []).filter(p => p.docstatus === 1 && p.lane !== 'done').forEach(p => { bySup[p.supplier || '—'] = (bySup[p.supplier || '—'] || 0) + (p.amount || 0); });
    const sup = Object.entries(bySup).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k, v]) => ({ label: k, value: v }));
    const months = {}; (X.pos || []).filter(p => p.docstatus === 1 && p.eta && !['done', 'to_bill'].includes(p.lane)).forEach(p => { const k = String(p.eta).slice(0, 7); months[k] = (months[k] || 0) + (p.amount || 0); });
    const mk = Object.keys(months).sort().slice(0, 8);
    PU.after = () => { if (X.money && mk.length) vbars($('#puetam'), mk.map(k => fmtM(k)), [{ name: 'Open PO value', color: '#2a78d6', values: mk.map(k => months[k]) }], { fmt: kfmt, h: 200 }); };
    return `<div class="grid">
      ${card('Decisions', 'Late, stuck or expiring. Click one to open its list.', decs, 's12')}
      ${tableCard('Arriving in the next 14 days', 'Purchase orders and inbound shipments by ETA. Red = ETA passed and not received.', ['ETA', 'Kind', 'Document', 'Supplier', '#Value'], arrRows, '', 's7')}
      ${card('Open PO value by supplier', X.money ? 'Submitted, not completed' : '', X.money ? hbars(sup, { fmt: kfmt, lw: '150px' }) : '<div class="empty">Needs the Finance role</div>', 's5')}
      ${card('Open PO value by month of ETA', '', X.money ? (mk.length ? '<div id="puetam"></div>' : '<div class="empty">No open purchase orders with an ETA</div>') : '<div class="empty">Needs the Finance role</div>', 's12')}
    </div>`;
  };

  /* ---- To order: shortages, below reorder level, draft-SO shortages, data gaps ---- */
  PU.order = X => {
    const rows = (X.shortages || []).filter(rowOK), firm = rows.filter(r => r.short_firm > 0), maybe = rows.filter(r => !(r.short_firm > 0) && r.short_all > 0);
    const canMR = r => !r.draft_po && !r.mr && !r.manufactured;
    const tr = (r, q, sel) => `<tr class="${r.late ? 'pu-row-late' : ''}">${sel ? `<td>${canMR(r) && LOGGED ? `<input type="checkbox" data-pusel="${esc(r.item)}" ${PU.sel[r.item] ? 'checked' : ''} aria-label="Select ${esc(r.item)}">` : ''}</td>` : ''}<td>${link('item', r.item)}<div class="m">${esc(r.group || '')}</div></td>
      <td class="num"><b>${+(+q).toFixed(2)}</b><div class="m">${+(+r.on_hand || 0).toFixed(1)} on hand · ${+(+r.on_order || 0).toFixed(1)} on order</div></td>
      <td>${r.supplier ? link('supplier', r.supplier) : badge('No supplier', 'warn')}<div class="m">${r.lead ? r.lead + '-day lead · ' + esc(r.lead_src || '') : 'No lead time'}</div></td>
      <td>${r.order_by ? (r.late ? badge('Late · ' + fmtd(r.order_by), 'bad') : fmtd(r.order_by)) : '—'}<div class="m">Needed ${fmtd(r.need_by)}</div></td>
      <td style="white-space:nowrap">${[r.draft_po && link('purchase-order', r.draft_po, 'PO ' + r.draft_po.split('-').pop()), r.mr && link('material-request', r.mr, 'MR ' + r.mr.replace(/^MAT-MR-\d{4}-/, ''))].filter(Boolean).join('<br>') || '<span class="calc">None</span>'}</td>
      <td style="white-space:nowrap">${drv(r.docs || [])}</td>
      <td class="num">${canMR(r) ? puBtn('Draft MR', `data-mr="${esc(r.item)}"`) : ''}</td></tr>`;
    const head = ['', 'Item', '#Short', 'Supplier', 'Order by', 'Draft PO / MR', 'Driven by', ''];
    const nsel = Object.keys(PU.sel).filter(k => PU.sel[k]).length;
    const re = (X.reorder || []).filter(rowOK).map(r => `<tr><td>${link('item', r.item)}<div class="m">${esc(r.item_name || '')}</div></td><td>${esc(r.warehouse || '')}</td>
      <td class="num"><b style="color:var(--badt)">${+(+r.projected).toFixed(1)}</b></td><td class="num">${r.level}</td><td class="num">${r.reorder_qty || '—'}</td><td class="num"><b>${r.suggest_qty}</b></td>
      <td>${r.supplier ? link('supplier', r.supplier) : badge('No supplier', 'warn')}<div class="m">${puLead(r.lead, r.lead_src)}</div></td>
      <td>${[r.open_mr && link('material-request', r.open_mr), r.open_po && link('purchase-order', r.open_po)].filter(Boolean).join('<br>') || '<span class="calc">None</span>'}</td>
      <td class="num">${r.suggested_level != null && r.suggested_level !== r.level ? `<span class="small" title="Daily usage × (lead time + safety days)">suggest ${r.suggested_level}</span> ${puBtn('Apply', `data-pureorder="${esc(r.item)}" data-wh="${esc(r.warehouse || '')}" data-level="${r.suggested_level}" data-qty="${r.reorder_qty || r.suggest_qty}"`)}` : ''}</td>
      <td class="num">${!r.open_mr && !r.open_po ? puBtn('Draft MR', `data-mrlow="${esc(r.item)}" data-qty="${Math.ceil(r.suggest_qty || 1)}"`) : ''}</td></tr>`);
    const G = X.gaps || {}, gl = [['no_supplier', 'No default supplier'], ['no_lead', 'No lead time'], ['no_reorder', 'No reorder level'], ['no_hts', 'No HTS code'], ['no_origin', 'No country of origin']];
    const gap = gl.map(([k, n]) => { const list = (G[k] || []).filter(rowOK);
      return `<details class="more pu-gap"><summary>${esc(n)} <b>${list.length}</b></summary><div class="tw"><table><tbody>${list.slice(0, 200).map(g => `<tr><td>${link('item', g.item)}<div class="m">${esc(g.item_name || '')}</div></td><td class="num">${k === 'no_lead' && LOGGED && X.can_edit ? `<form class="pu-inline" data-puleadf="${esc(g.item)}"><input type="number" min="0" name="days" placeholder="days" aria-label="Lead time days for ${esc(g.item)}"><button class="cc-btn soft">Set</button></form>` : k === 'no_reorder' && g.suggested_level != null ? `<span class="small">suggested level ${g.suggested_level}</span>` : `<a class="small" target="_blank" rel="noopener" href="${docUrl('Item', g.item)}">Open item ↗</a>`}</td></tr>`).join('') || '<tr><td class="empty">None</td></tr>'}</tbody></table></div></details>`; }).join('');
    return `<div class="grid">
      ${stat('Lines short', firm.length, 'Against submitted orders').replace('card stat', 'card stat s3')}
      ${stat('Past order-by date', firm.filter(r => r.late).length, 'Should already be ordered', firm.some(r => r.late) ? 'bad' : '').replace('card stat', 'card stat s3')}
      ${stat('Below reorder level', re.length, 'Projected stock under the level').replace('card stat', 'card stat s3')}
      ${stat('Data gaps', gl.reduce((a, [k]) => a + (G[k] || []).length, 0), 'Items missing purchasing data').replace('card stat', 'card stat s3')}
      ${tableCard('What to order', `Short = open demand from submitted orders and active work orders, minus stock on hand and on order. Order by = needed date − lead time − ${X.settings && X.settings.safety_days != null ? X.settings.safety_days : 3} safety days. Draft MR creates an unsubmitted Material Request.`, head, firm.map(r => tr(r, r.short_firm, true)),
        `<div class="toolbar">${puBtn(`Draft one MR for selected${nsel ? ' (' + nsel + ')' : ''}`, `id="pumrsel" ${nsel ? '' : 'disabled'}`, true)}</div>`)}
      ${tableCard('Below reorder level', 'Projected quantity (on hand + on order − reserved) under the item\'s reorder level. Suggested level = daily usage × (lead time + safety days).', ['Item', 'Warehouse', '#Projected', '#Level', '#Reorder qty', '#Suggest', 'Supplier', 'Open MR / PO', '', ''], re)}
      <div class="card flush s12"><details class="more"><summary>Only short if the draft sales orders go ahead (${maybe.length})</summary><div class="tw" style="border-top:1px solid var(--line)"><table><thead><tr>${head.slice(1).map(h => `<th>${h.replace('#', '')}</th>`).join('')}</tr></thead><tbody>${maybe.map(r => tr(r, r.short_all, false)).join('')}</tbody></table></div></details></div>
      ${card('Data gaps', 'Without a supplier, lead time and reorder level the list above is mostly guesses. Fix the top purchased items first.', gap, 's12')}
    </div>`;
  };

  /* ---- Requests: material request lanes ---- */
  PU.requests = X => {
    const rows = (X.mrs || []).filter(rowOK);
    const cardFn = r => `<div class="tcard"><div class="r">${link('material-request', r.name, r.name.replace(/^MAT-MR-\d{4}-/, 'MR '))}${r.schedule_date ? (r.schedule_date < X.today && !['ordered', 'receiving', 'done'].includes(r.lane) ? badge('Needed ' + fmtd(r.schedule_date), 'bad') : `<span class="small">Needed ${fmtd(r.schedule_date)}</span>`) : ''}</div>
      <div class="m" style="margin-top:6px">${(r.items || []).slice(0, 3).map(i => `${esc(i.item)} × ${+i.qty}`).join('<br>')}${(r.items || []).length > 3 ? `<br>+ ${r.items.length - 3} more` : ''}</div>
      ${r.from_so ? `<div class="qchip">For ${link('sales-order', r.from_so, short(r.from_so))}</div>` : ''}${puChips('request-for-quotation', r.rfqs, 'RFQ')}${puChips('supplier-quotation', r.sqs, 'SQ')}${puChips('purchase-order', r.pos, 'PO')}
      ${r.docstatus === 1 && ['to_quote', 'quoted'].includes(r.lane) ? `<div class="pu-acts">${puBtn('Request quotes', `data-purfq="${esc(r.name)}"`)}${puBtn('Order directly', `data-pupomr="${esc(r.name)}"`)}</div>` : r.docstatus === 0 ? '<div class="small" style="margin-top:6px">Submit in ERPNext to request quotes or order</div>' : ''}</div>`;
    return `<p class="small">A submitted request can go out for quotes (RFQ) or straight to a draft purchase order. Fully received requests are hidden.</p>` + puBoard('requests', rows, cardFn);
  };

  /* ---- Vendor quotes: RFQ / supplier quotation lanes + compare ---- */
  PU.quotes = X => {
    const rows = (X.quotes || []).filter(rowOK), rfq = r => r.doctype === 'Request for Quotation';
    const cardFn = r => `<div class="tcard"><div class="r"><span class="badge ${rfq(r) ? 'mute' : 'info'}">${rfq(r) ? 'RFQ' : 'Quote'}</span>${link(slug(r.doctype), r.name)}</div>
      <div style="margin-top:6px">${rfq(r) ? (r.suppliers || []).map(s => `<span class="qchip" title="${s.email_sent ? 'Email sent' : 'Not emailed yet'}">${esc(s.supplier)} · ${s.quote_status === 'Received' ? '<b style="color:var(--goodt)">received</b>' : 'pending'}</span>`).join('') || '<span class="calc">No suppliers</span>' : (r.supplier ? link('supplier', r.supplier) : '')}</div>
      <div class="r" style="margin-top:6px"><span class="small">${r.items || 0} item${r.items === 1 ? '' : 's'}${r.lead_days != null ? ' · ' + r.lead_days + 'd lead' : ''}</span><b>${rfq(r) ? '' : puM(r.total)}</b></div>
      ${r.valid_till ? `<div class="small">${r.days_left != null && r.days_left < 0 ? badge('Expired ' + fmtd(r.valid_till), 'bad') : r.lane === 'expiring' ? badge(`Valid ${r.days_left}d more`, 'warn') : 'Valid till ' + fmtd(r.valid_till)}</div>` : ''}
      ${r.mr ? `<div class="qchip">MR ${link('material-request', r.mr, r.mr.replace(/^MAT-MR-\d{4}-/, ''))}</div>` : ''}${r.po ? `<div class="qchip">PO ${link('purchase-order', r.po)}</div>` : ''}
      <div class="pu-acts">${rfq(r) && r.docstatus === 1 ? puBtn('Enter quote', `data-pusq="${esc(r.name)}"`) : ''}${!rfq(r) && r.docstatus === 1 && ['quoted', 'expiring'].includes(r.lane) ? puBtn('Accept → draft PO', `data-pupo="${esc(r.name)}"`, true) : ''}</div></div>`;
    const cmp = (X.quote_compare || []).filter(rowOK).map(c => `<tr><td>${link('item', c.item)}</td><td>${c.rows.map(q => `<div class="pu-cmp ${q.cheapest ? 'cheap' : ''} ${q.fastest ? 'fast' : ''}">${link('supplier-quotation', q.sq, q.supplier || q.sq)} · <b>${puM(q.rate)}</b> · ${q.lead_days != null ? q.lead_days + 'd' : '—'} · till ${fmtd(q.valid_till)}${q.cheapest ? ' ' + badge('cheapest', 'good') : ''}${q.fastest ? ' ' + badge('fastest', 'info') : ''}</div>`).join('')}</td></tr>`);
    return puBoard('quotes', rows, cardFn) + `<div class="grid" style="margin-top:20px">${tableCard('Compare quotes', 'Items with two or more live supplier quotations.', ['Item', 'Quotes'], cmp)}</div>`;
  };

  /* ---- Purchase orders: lanes or table, side sheet with tracking ---- */
  const puPoCard = r => `<div class="tcard pu-po" data-puopen="${esc(r.name)}" tabindex="0" role="button" aria-label="Open ${esc(r.name)}"><div class="r"><b>${esc(r.name)}</b><span>${puM(r.amount)}</span></div>
    <div class="m">${esc(r.supplier || '')}${r.paint ? ' ' + badge('Paint', 'warn') : ''}</div>
    <div class="r" style="margin-top:6px">${puLead(r.lead_days, r.lead_src)}${puEta(r)}</div>
    ${r.vendor_order_no ? `<div class="small">Ack # ${esc(r.vendor_order_no)}</div>` : ''}${r.sent_on && r.lane === 'awaiting_confirmation' ? `<div class="small">Sent ${fmtd(r.sent_on)}</div>` : ''}
    ${r.notes ? `<div class="small pu-notes">${esc(r.notes)}</div>` : ''}
    ${(r.sales_orders || []).length ? `<div>${r.sales_orders.slice(0, 3).map(s => `<span class="qchip">${esc(short(s))}</span>`).join('')}</div>` : ''}
    ${r.lane === 'partly_received' ? meter((r.per_received || 0) / 100) : ''}</div>`;
  PU.pos = X => {
    const rows = (X.pos || []).filter(rowOK);
    const bar = `<div class="toolbar no-print" style="margin-bottom:12px"><div class="seg"><button data-puview="lanes" class="${PU.view === 'lanes' ? 'on' : ''}">Lanes</button><button data-puview="table" class="${PU.view === 'table' ? 'on' : ''}">Table</button></div>
      <label class="small"><input type="checkbox" id="pudone" ${PU.showDone ? 'checked' : ''}> Show done</label></div>`;
    if (PU.view === 'table') {
      const list = rows.filter(r => PU.showDone || r.lane !== 'done').slice().sort((a, b) => String(a.eta || '9').localeCompare(String(b.eta || '9')));
      return bar + `<div class="grid">${tableCard('Purchase orders by ETA', 'Click a row to edit tracking.', ['PO', 'Supplier', 'Lane', 'Vendor status', 'Lead', 'ETA', '#Received', '#Value'],
        list.map(r => `<tr class="wb-row ${r.overdue ? 'pu-row-late' : ''}" data-puopen="${esc(r.name)}"><td><b>${esc(r.name)}</b></td><td>${esc(r.supplier || '')}</td><td>${esc((PU_LANES.pos.find(l => l[0] === r.lane) || [0, r.lane])[1])}</td><td>${esc(r.vendor_status || '')}</td><td>${puLead(r.lead_days, r.lead_src)}</td><td>${puEta(r)}</td><td class="num">${Math.round(r.per_received || 0)}%</td><td class="num">${puM(r.amount)}</td></tr>`))}</div>`;
    }
    return bar + puBoard('pos', rows, puPoCard);
  };
  function puPoSheet(name) {
    const X = PU.data, r = (X.pos || []).find(p => p.name === name); if (!r) { window.open(docUrl('Purchase Order', name), '_blank'); return; }
    const ed = LOGGED && X.can_edit, sub = r.docstatus === 1, dis = ed ? '' : 'disabled';
    const sel = (n, opts, v) => `<select name="${n}" ${dis}>${opts.map(o => `<option value="${esc(o)}" ${String(v || '') === o ? 'selected' : ''}>${esc(o || '—')}</option>`).join('')}</select>`;
    const fld = (l, inner) => `<label class="cc-field"><span>${l}</span>${inner}</label>`;
    const inp = (n, t, v) => `<input type="${t}" name="${n}" value="${esc(v == null ? '' : String(v).slice(0, t === 'date' ? 10 : 200))}" ${dis}>`;
    const lines = (r.lines || []).map(l => `<tr data-line="${esc(l.name)}"><td>${link('item', l.item)}<div class="m">${esc(l.item_name || '')}</div></td><td class="num">${+l.qty} <span class="calc">(${+(l.received_qty || 0)} in)</span></td>
      <td><input type="number" min="0" name="lead" value="${esc(l.ill_est_lead_time_days == null ? '' : l.ill_est_lead_time_days)}" placeholder="${esc(l.lead_days == null ? '' : l.lead_days)}" ${dis} aria-label="Line lead time"></td>
      <td><input type="date" name="eta" value="${esc(String(l.ill_eta || '').slice(0, 10))}" ${dis} aria-label="Line ETA"><div class="m">${l.eta ? 'now ' + fmtd(l.eta) : ''}</div></td></tr>`).join('');
    const rel = [['Sales orders', 'sales-order', r.sales_orders], ['Shipments', 'ill-inbound-shipment', r.shipments], ['Receipts', 'purchase-receipt', r.receipts], ['Bills', 'purchase-invoice', r.invoices]]
      .map(([l, dt, list]) => `<div class="wb-kv"><span>${l}</span><b>${(list || []).map(n => link(dt, n, short(n))).join(', ') || '<span class="calc">—</span>'}</b></div>`).join('');
    const sh = wbShowSheet(`<div class="wb-kvs"><div class="wb-kv"><span>Status</span><b>${badge(r.status || '', wbKind(r.status))}</b></div><div class="wb-kv"><span>Ordered</span><b>${fmtd(r.transaction_date)}</b></div><div class="wb-kv"><span>Value</span><b>${puM(r.amount)}</b></div>
        <div class="wb-kv"><span>Received / billed</span><b>${Math.round(r.per_received || 0)}% / ${Math.round(r.per_billed || 0)}%</b></div><div class="wb-kv"><span>ETA</span><b>${puEta(r)}</b></div>${rel}</div>
      <div class="wb-sec">Vendor tracking</div>
      ${fld('Vendor status', sel('ill_vendor_status', PU_VSTAT, r.vendor_status))}${fld('Sent to vendor on', inp('ill_sent_on', 'date', r.sent_on))}${fld('Vendor confirmed on', inp('ill_vendor_confirmed_on', 'date', r.confirmed_on))}
      ${fld('Vendor order / ack #', inp('ill_vendor_order_no', 'text', r.vendor_order_no))}${fld('Estimated lead time (days)', inp('ill_est_lead_time_days', 'number', r.est_lead_time_days))}
      ${fld('Estimated arrival', inp('ill_eta', 'date', r.ill_eta || ''))}${fld('Vendor promised ship date', inp('ill_promised_ship_date', 'date', r.promised_ship_date))}${fld('Freight mode', sel('ill_freight_mode', PU_FREIGHT, r.freight_mode))}
      ${fld('Purchasing notes', `<textarea name="ill_purchasing_notes" rows="2" ${dis}>${esc(r.notes || '')}</textarea>`)}
      ${lines ? `<div class="wb-sec">Lines (blank = use the header)</div><div class="card flush"><table class="wb-table pu-lines"><thead><tr><th>Item</th><th>Qty</th><th>Lead (days)</th><th>ETA</th></tr></thead><tbody>${lines}</tbody></table></div>` : ''}
      <p class="cc-msg" id="puMsg"></p>
      <div class="cc-sheet-f wb-foot"><a class="cc-btn soft" target="_blank" rel="noopener" href="${docUrl('Purchase Order', name)}" style="text-decoration:none" title="Opens the PO in ERPNext: Menu → Email uses the ilL Purchase Order print format. Sending it marks the PO Sent here.">Email PO ↗</a>
        ${sub && ed ? `<button type="button" class="cc-btn soft" data-puact="create_shipment">Create shipment</button><button type="button" class="cc-btn soft" data-puact="make_receipt">Draft receipt</button><button type="button" class="cc-btn soft" data-puact="make_invoice">Draft bill</button>` : ''}
        ${WB.cfg && WB.cfg.can_edit !== false && ed ? '<button type="button" class="cc-btn soft" id="puagenda">+ Add to agenda</button>' : ''}<span style="flex:1"></span>${ed ? '<button class="cc-btn primary" type="submit" id="pusave">Save tracking</button>' : ''}</div>`,
      `Purchase order · ${esc(r.supplier || '')}${r.paint ? ' · Paint' : ''}`, esc(name));
    const f = sh.querySelector('#wbform'), msg = sh.querySelector('#puMsg');
    const keys = { ill_vendor_status: r.vendor_status, ill_sent_on: r.sent_on, ill_vendor_confirmed_on: r.confirmed_on, ill_vendor_order_no: r.vendor_order_no, ill_est_lead_time_days: r.est_lead_time_days, ill_eta: r.ill_eta, ill_promised_ship_date: r.promised_ship_date, ill_freight_mode: r.freight_mode, ill_purchasing_notes: r.notes };
    const ab = sh.querySelector('#puagenda'); if (ab) ab.onclick = () => agQuick('Purchase Order', name, { name, supplier: r.supplier, status: r.status }, ab);
    sh.querySelectorAll('[data-puact]').forEach(b => b.onclick = () => puAct(b, b.dataset.puact, b.dataset.puact === 'create_shipment' ? { pos: [name], values: { supplier: r.supplier, freight_mode: r.freight_mode || '' } } : b.dataset.puact === 'make_receipt' ? { po: name } : { po: name }));
    f.onsubmit = async e => {
      e.preventDefault(); if (!ed) return;
      const vals = {}; Object.keys(keys).forEach(k => { const el = f.elements[k]; if (!el) return; let v = el.value; if (k === 'ill_est_lead_time_days') v = v === '' ? null : +v;
        if (String(v == null ? '' : v) !== String(keys[k] == null ? '' : String(keys[k]).slice(0, el.type === 'date' ? 10 : 9999))) vals[k] = v === '' ? null : v; });
      const rows = []; f.querySelectorAll('tr[data-line]').forEach(tr => { const l = (r.lines || []).find(x => x.name === tr.dataset.line), le = tr.querySelector('[name=lead]').value, et = tr.querySelector('[name=eta]').value;
        if (String(le) !== String(l.ill_est_lead_time_days == null ? '' : l.ill_est_lead_time_days) || et !== String(l.ill_eta || '').slice(0, 10)) rows.push({ name: l.name, ill_est_lead_time_days: le === '' ? null : +le, ill_eta: et || null }); });
      if (!Object.keys(vals).length && !rows.length) { msg.textContent = 'No changes to save.'; return; }
      const b = sh.querySelector('#pusave'); b.disabled = true; b.textContent = 'Saving…'; msg.textContent = '';
      try {
        let n = 0;
        if (Object.keys(vals).length) n += (await puPost('update_po_tracking', { po: name, values: vals })).changed || 0;
        if (rows.length) n += (await puPost('update_po_line_tracking', { po: name, rows })).changed || 0;
        closeSheet(); toast(`Saved ${esc(name)} · ${n} change${n === 1 ? '' : 's'}`); puFetch();
      } catch (err) { msg.textContent = 'Not saved: ' + err.message; b.disabled = false; b.textContent = 'Save tracking'; }
    };
  }

  /* ---- Shipments: lanes, cost bar, side sheet with editable cost lines ---- */
  const puCostBar = s => { const est = s.est_cost || 0, act = s.actual_cost || 0, max = Math.max(est, act, 1), by = k => { const m = {}; (s.costs || []).forEach(c => { m[c.cost_type] = (m[c.cost_type] || 0) + (Number(c[k]) || 0); }); return m; };
    const seg = (m, tot) => Object.entries(m).filter(e => e[1] > 0).map(([t, v]) => `<i title="${esc(t)}: ${money(v)}" style="width:${(v / max * 100).toFixed(1)}%;background:${PU_COST_COL[PU_COST_TYPES.indexOf(t) >= 0 ? PU_COST_TYPES.indexOf(t) : 9]}"></i>`).join('');
    return s.est_cost == null ? '' : `<div class="pu-cost" title="Estimated vs actual inbound costs"><div class="pu-cbar"><span>Est</span><div>${seg(by('est'))}</div><b>${kfmt(est)}</b></div><div class="pu-cbar"><span>Act</span><div>${seg(by('actual'))}</div><b>${act ? kfmt(act) : '—'}</b></div></div>`; };
  const puShipCard = s => `<div class="tcard pu-po" data-pushop="${esc(s.name)}" tabindex="0" role="button" aria-label="Open ${esc(s.name)}"><div class="r"><b><span class="pu-mode" title="${esc(s.mode || 'Mode not set')}">${PU_MODE[s.mode] || '•'}</span> ${esc(s.name)}</b><span class="small">${esc(s.status || '')}</span></div>
    <div class="m">${esc(s.supplier || '')}${s.forwarder ? ' · via ' + esc(s.forwarder) : ''}</div>
    ${s.tracking_no ? `<div class="small">${s.tracking_url ? `<a target="_blank" rel="noopener" href="${esc(s.tracking_url)}">${esc(s.tracking_no)} ↗</a>` : esc(s.tracking_no)}${s.container_no ? ' · ' + esc(s.container_no) : ''}</div>` : ''}
    <div class="small">${s.ata ? 'Arrived ' + fmtd(s.ata) : s.eta ? (s.eta < PU.data.today && ['moving', 'customs', 'arriving', 'planned'].includes(s.lane) ? badge('ETA passed ' + fmtd(s.eta), 'bad') : 'ETA ' + fmtd(s.eta)) : '<span class="calc">No ETA</span>'}</div>
    <div>${(s.pos || []).map(p => `<span class="qchip">${esc(String(p).split('-').slice(-1)[0])}</span>`).join('')}</div>
    <div class="r small"><span>Goods ${puM(s.goods_value)}</span><span>${s.landed_pct != null ? 'Landed +' + puPct(s.landed_pct) : ''}</span></div>${puCostBar(s)}
    ${s.needs_lcv ? `<div style="margin-top:6px">${badge('Needs landed cost', 'warn')}</div>` : ''}</div>`;
  PU.shipments = X => `<p class="small">A shipment joins purchase orders to the container, flight or truck that carries them, with every cost on it. Estimates come from Purchasing Settings and HTS duty rates; actuals from the forwarder's and broker's bills.</p>` + puBoard('shipments', (X.shipments || []).filter(rowOK), puShipCard);
  function puShipSheet(name) {
    const X = PU.data, s = (X.shipments || []).find(x => x.name === name); if (!s) { window.open(docUrl('ilL-Inbound-Shipment', name), '_blank'); return; }
    const ed = LOGGED && X.can_edit, dis = ed ? '' : 'disabled';
    // cost lines are saved as a whole list; without the money role the amounts arrive blank, so they stay read-only
    const costEd = ed && X.money, cdis = costEd ? '' : 'disabled';
    const inp = (n, t, v, l) => `<label class="cc-field"><span>${l}</span><input type="${t}" name="${n}" value="${esc(v == null ? '' : String(v).slice(0, t === 'date' ? 10 : 200))}" ${dis}></label>`;
    const sel = (n, opts, v, l) => `<label class="cc-field"><span>${l}</span><select name="${n}" ${dis}>${opts.map(o => `<option value="${esc(o)}" ${String(v || '') === o ? 'selected' : ''}>${esc(o || '—')}</option>`).join('')}</select></label>`;
    const costRow = c => `<tr data-cost="${esc(c.name || '')}"><td><select name="cost_type" ${cdis}>${PU_COST_TYPES.map(o => `<option ${c.cost_type === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>${c.description ? `<div class="m">${esc(c.description)}</div>` : ''}</td>
      <td><input type="number" step="any" name="est" value="${esc(c.est == null ? '' : c.est)}" ${cdis} aria-label="Estimated"></td><td><input type="number" step="any" name="actual" value="${esc(c.actual == null ? '' : c.actual)}" ${cdis} aria-label="Actual"></td>
      <td><input type="text" name="vendor" value="${esc(c.vendor || '')}" ${cdis} aria-label="Billed by" list="pu_sup"></td><td><input type="text" name="pi" value="${esc(c.pi || '')}" ${cdis} aria-label="Purchase invoice" placeholder="PI"></td>
      <td><input type="checkbox" name="in_lc" ${c.in_lc ? 'checked' : ''} ${cdis} aria-label="Include in landed cost"></td></tr>`;
    const sh = wbShowSheet(`<div class="wb-kvs"><div class="wb-kv"><span>Goods value</span><b>${puM(s.goods_value)}</b></div><div class="wb-kv"><span>Estimated / actual costs</span><b>${puM(s.est_cost)} / ${puM(s.actual_cost)}</b></div>
        <div class="wb-kv"><span>Landed cost</span><b>${s.landed_pct != null ? '+' + puPct(s.landed_pct) : '—'}</b></div><div class="wb-kv"><span>Purchase orders</span><b>${(s.pos || []).map(p => link('purchase-order', p)).join(', ') || '—'}</b></div>
        <div class="wb-kv"><span>Receipts</span><b>${(s.receipts || []).map(p => link('purchase-receipt', p)).join(', ') || '—'}</b></div><div class="wb-kv"><span>Landed cost vouchers</span><b>${(s.lcvs || []).map(v => link('landed-cost-voucher', v.name) + (v.docstatus === 1 ? ' ✓' : ' (draft)')).join(', ') || '—'}</b></div></div>
      <div class="wb-sec">Shipment</div>
      ${sel('status', PU_SHIP_ST, s.status, 'Status')}${sel('freight_mode', PU_FREIGHT, s.mode, 'Freight mode')}${inp('tracking_no', 'text', s.tracking_no, 'Tracking # (BOL / AWB / PRO)')}${inp('tracking_url', 'url', s.tracking_url, 'Tracking link')}
      ${inp('container_no', 'text', s.container_no, 'Container #')}${inp('etd', 'date', s.etd, 'Estimated departure')}${inp('atd', 'date', s.atd, 'Actual departure')}${inp('eta', 'date', s.eta, 'Estimated arrival')}${inp('ata', 'date', s.ata, 'Actual arrival')}
      ${inp('entry_no', 'text', s.entry_no, 'Customs entry # (7501)')}
      <div class="wb-sec">Costs</div><div class="card flush"><table class="wb-table pu-costs"><thead><tr><th>Type</th><th>Estimated</th><th>Actual</th><th>Billed by</th><th>Bill (PI)</th><th>In LC</th></tr></thead><tbody id="pucostrows">${(s.costs || []).map(costRow).join('')}</tbody></table></div>
      ${costEd ? '<button type="button" class="cc-btn soft" id="puaddcost" style="margin-top:8px">+ Cost line</button>' : ed ? '<p class="small">Cost lines need the Finance role to edit here.</p>' : ''}<datalist id="pu_sup"></datalist>
      ${ed ? '<label class="small" style="display:block;margin-top:12px"><input type="checkbox" id="puallowest"> Allow estimates in the landed cost voucher (lines with no bill yet)</label>' : ''}
      <p class="cc-msg" id="puMsg"></p>
      <div class="cc-sheet-f wb-foot"><a class="cc-btn soft" target="_blank" rel="noopener" href="${docUrl('ilL-Inbound-Shipment', name)}" style="text-decoration:none">Open in ERPNext</a>
        ${ed ? `${(s.pos || []).filter(p => !(s.receipts || []).length).slice(0, 1).map(p => `<button type="button" class="cc-btn soft" data-puact="make_receipt" data-po="${esc(p)}">Draft receipt</button>`).join('')}<button type="button" class="cc-btn soft" data-puact="make_landed_cost_voucher">Draft landed cost voucher</button>` : ''}
        <span style="flex:1"></span>${ed ? '<button class="cc-btn primary" type="submit" id="pusave">Save shipment</button>' : ''}</div>`,
      `Inbound shipment · ${esc(s.supplier || '')}`, esc(name));
    const f = sh.querySelector('#wbform'), msg = sh.querySelector('#puMsg');
    const add = sh.querySelector('#puaddcost'); if (add) add.onclick = () => sh.querySelector('#pucostrows').insertAdjacentHTML('beforeend', costRow({ cost_type: 'Freight', in_lc: 1 }));
    sh.querySelectorAll('[data-puact]').forEach(b => b.onclick = () => puAct(b, b.dataset.puact, b.dataset.puact === 'make_receipt' ? { po: b.dataset.po, shipment: name } : { shipment: name, allow_estimate: sh.querySelector('#puallowest') && sh.querySelector('#puallowest').checked ? 1 : 0 }));
    f.onsubmit = async e => {
      e.preventDefault(); if (!ed) return;
      const values = {}; ['status', 'freight_mode', 'tracking_no', 'tracking_url', 'container_no', 'etd', 'atd', 'eta', 'ata', 'entry_no'].forEach(k => { const el = f.elements[k]; if (el) values[k] = el.value || null; });
      // the list replaces the shipment's cost lines, so fields not shown here are carried over from each line
      const costs = [...f.querySelectorAll('tr[data-cost]')].map(tr => { const g = n => tr.querySelector(`[name=${n}]`), o = (s.costs || []).find(c => tr.dataset.cost && c.name === tr.dataset.cost) || {};
        return { name: tr.dataset.cost || null, cost_type: g('cost_type').value, description: o.description || null, expense_account: o.expense_account || null, allocation: o.allocation || null,
          estimated_amount: g('est').value === '' ? null : +g('est').value, actual_amount: g('actual').value === '' ? null : +g('actual').value,
          vendor: g('vendor').value || null, purchase_invoice: g('pi').value || null, include_in_landed_cost: g('in_lc').checked ? 1 : 0 }; });
      const b = sh.querySelector('#pusave'); b.disabled = true; b.textContent = 'Saving…'; msg.textContent = '';
      try { await puPost('update_shipment', costEd ? { name, values, costs } : { name, values }); closeSheet(); toast(`Saved ${esc(name)}`); puFetch(); }
      catch (err) { msg.textContent = 'Not saved: ' + err.message; b.disabled = false; b.textContent = 'Save shipment'; }
    };
  }

  /* ---- Receipts / Bills / Landed cost / Suppliers ---- */
  const PU_LCV = { landed: ['Landed', 'good'], needs_lcv: ['Needs LCV', 'warn'], no_costs: ['No inbound costs', 'mute'] };
  PU.receipts = X => `<div class="grid">${tableCard('Purchase receipts', 'Goods received into stock in the last 120 days, and any still to bill.', ['Receipt', 'Supplier', 'Date', 'POs', '#Value', '#Billed', 'Shipment', 'Landed cost', ''],
    (X.receipts || []).filter(rowOK).map(r => `<tr><td>${link('purchase-receipt', r.name)}${r.docstatus === 0 ? ' ' + badge('Draft', 'mute') : ''}</td><td>${esc(r.supplier || '')}</td><td>${fmtd(r.posting_date)}</td><td>${(r.pos || []).map(p => link('purchase-order', p, String(p).split('-').slice(-1)[0])).join(', ')}</td>
      <td class="num">${puM(r.amount)}</td><td class="num">${Math.round(r.billed_pct || 0)}%</td><td>${r.shipment ? link('ill-inbound-shipment', r.shipment) : '<span class="calc">—</span>'}</td><td>${badge(...(PU_LCV[r.lcv_status] || PU_LCV.no_costs))}${r.lcv_amount ? ' <span class="small">' + puM(r.lcv_amount) + '</span>' : ''}</td>
      <td class="num">${r.docstatus === 1 && (r.billed_pct || 0) < 100 ? puBtn('Draft bill', `data-puact="make_invoice" data-pr="${esc(r.name)}"`) : ''}</td></tr>`))}</div>`;
  const PU_MATCH = { matches: ['Matches', 'good'], qty_off: ['Qty off', 'bad'], price_off: ['Price off', 'warn'] };
  PU.bills = X => { const notQ = (X.bills || []).filter(b => b.docstatus === 1 && !b.qbo_id).length;
    const cardFn = b => `<div class="tcard"><div class="r">${link('purchase-invoice', b.name)}<b>${puM(b.lane === 'paid' ? b.amount : b.outstanding)}</b></div><div class="m">${esc(b.supplier || '')}${b.bill_no ? ' · #' + esc(b.bill_no) : ''}</div>
      <div class="r small" style="margin-top:6px"><span>${b.due_date ? (b.lane === 'overdue' ? badge('Due ' + fmtd(b.due_date), 'bad') : 'Due ' + fmtd(b.due_date)) : ''}</span><span class="badge ${b.kind === 'goods' ? 'mute' : 'info'}">${esc(b.kind || 'goods')}</span></div>
      <div style="margin-top:6px">${b.docstatus === 1 ? (b.qbo_id ? badge('In QBO', 'good') : badge('Not in QBO', 'warn')) : ''} ${b.match ? `<span class="badge ${PU_MATCH[b.match][1]}" title="${esc(b.variance ? `Qty variance ${b.variance.qty == null ? '—' : b.variance.qty} · price variance ${b.variance.price == null ? '—' : money(b.variance.price)}` : '')}">${PU_MATCH[b.match][0]}</span>` : ''}</div>
      <div>${puChips('purchase-order', b.pos, 'PO')}${puChips('purchase-receipt', b.receipts, 'PR')}</div></div>`;
    return `<p class="small">Vendor, forwarder and broker bills. Every submitted bill goes to QuickBooks as a Bill${notQ ? ` · <b>${notQ} not in QuickBooks yet</b> (the hourly sync retries; see Portal Operations)` : ''}. 3-way match compares PO, receipt and bill quantities and prices (over 2% or $50 is flagged).</p>` + puBoard('bills', (X.bills || []).filter(rowOK), cardFn); };
  PU.landed = X => { const L = X.landed || {};
    const pend = (L.pending || []).filter(rowOK).map(p => `<tr><td>${p.shipment ? link('ill-inbound-shipment', p.shipment) : ''}${p.receipt ? (p.shipment ? '<br>' : '') + link('purchase-receipt', p.receipt) : ''}</td><td>${esc(p.supplier || '')}</td><td class="num">${puM(p.est)}</td><td class="num">${puM(p.actual)}</td>
      <td>${(p.missing_bills || []).map(t => badge(t + ' bill not in yet', 'warn')).join(' ') || (p.ready ? badge('Ready', 'good') : '')}</td><td class="num">${p.shipment ? puBtn('Draft LCV', `data-puact="make_landed_cost_voucher" data-ship="${esc(p.shipment)}"`, p.ready) : ''}</td></tr>`);
    const vou = (L.vouchers || []).filter(rowOK).map(v => `<tr><td>${link('landed-cost-voucher', v.name)}</td><td>${v.docstatus === 1 ? badge('Submitted', 'good') : v.docstatus === 2 ? badge('Cancelled', 'bad') : badge('Draft', 'warn')}</td><td>${fmtd(v.posting_date)}</td><td>${(v.receipts || []).map(r => link('purchase-receipt', r)).join(', ')}</td><td class="num">${puM(v.amount)}</td></tr>`);
    const byi = (L.by_item || []).filter(rowOK);
    PU.byItemText = () => ['Item\tLast receipt\tPurchase rate\tLanded rate\tUplift %\t12-month avg uplift %'].concat(byi.map(i => [i.item, i.last_receipt || '', i.purchase_rate == null ? '' : i.purchase_rate, i.landed_rate == null ? '' : i.landed_rate, i.uplift_pct == null ? '' : i.uplift_pct, i.avg_uplift_12m == null ? '' : i.avg_uplift_12m].join('\t'))).join('\n');
    return `<div class="grid">
      ${stat('Need landed cost', (L.pending || []).length, 'Delivered, costs not in a submitted voucher', (L.pending || []).length ? 'bad' : '').replace('card stat', 'card stat s4')}
      ${stat('Estimated costs still to land', puM((X.summary.landed || {}).est_open_amount), 'Freight, duty and tariffs not yet in stock value').replace('card stat', 'card stat s4')}
      ${stat('Landed cost in stock', puM(L.in_stock_amount), 'For the periodic QuickBooks true-up (Decision D1)').replace('card stat', 'card stat s4')}
      ${tableCard('Needs landed cost', 'When every included cost has its bill (or you accept estimates), Draft LCV builds the Landed Cost Voucher. Charlotte checks the distribution and submits it in ERPNext.', ['Shipment / receipt', 'Supplier', '#Estimated', '#Actual', 'Missing', ''], pend)}
      ${tableCard('Landed cost vouchers', 'Last 120 days', ['Voucher', 'Status', 'Date', 'Receipts', '#Amount'], vou, '', 's6')}
      ${tableCard('Landed cost by item', 'Last purchase rate against the valuation after freight, duty and tariffs.', ['Item', 'Last receipt', '#Purchase rate', '#Landed rate', '#Uplift', '#12-mo avg'],
        byi.map(i => `<tr><td>${link('item', i.item)}<div class="m">${esc(i.item_name || '')}</div></td><td>${i.last_receipt ? link('purchase-receipt', i.last_receipt) : ''}</td><td class="num">${puM(i.purchase_rate)}</td><td class="num">${puM(i.landed_rate)}</td><td class="num">${puPct(i.uplift_pct)}</td><td class="num">${puPct(i.avg_uplift_12m)}</td></tr>`),
        `<button type="button" class="cc-btn soft no-print" id="pucopy">Copy as text</button>`, 's6')}
    </div>`; };
  PU.suppliers = X => `<div class="grid">${tableCard('Supplier scorecard', 'Quoted lead time from supplier quotations; actual = receipt date − PO date. On time = received by the ETA.', ['Supplier', '#Open POs', '#Open $', '#Quoted lead', '#Actual lead', '#On time', 'Last PO', 'Default lead time'],
    (X.suppliers || []).filter(rowOK).map(s => `<tr><td>${link('supplier', s.supplier)}</td><td class="num">${s.open_pos || 0}</td><td class="num">${puM(s.open_amount)}</td><td class="num">${puDays(s.avg_quoted_lead) || '—'}</td><td class="num">${puDays(s.avg_actual_lead) || '—'}</td>
      <td class="num">${s.on_time_pct == null ? '—' : Math.round(s.on_time_pct) + '%'}</td><td>${s.last_po ? link('purchase-order', s.last_po) : '—'}</td>
      <td>${LOGGED && X.can_edit ? `<form class="pu-inline" data-pusupf="${esc(s.supplier)}"><input type="number" min="0" name="days" value="${esc(s.default_lead == null ? '' : s.default_lead)}" aria-label="Default lead time for ${esc(s.supplier)}"><button class="cc-btn soft">Set</button></form>` : puDays(s.default_lead) || '—'}</td></tr>`))}</div>`;

  /* ---- actions: every button creates a draft (or saves tracking) and says so ---- */
  const PU_MADE = { make_rfq: ['Request for Quotation', 'request-for-quotation'], make_supplier_quotation: ['Supplier Quotation', 'supplier-quotation'], make_po: ['Purchase Order', 'purchase-order'], make_receipt: ['Purchase Receipt', 'purchase-receipt'],
    make_invoice: ['Purchase Invoice', 'purchase-invoice'], create_shipment: ['Inbound shipment', 'ill-inbound-shipment'], make_landed_cost_voucher: ['Landed Cost Voucher', 'landed-cost-voucher'], draft_material_request: ['Material Request', 'material-request'] };
  async function puAct(btn, method, args) {
    const t = btn ? btn.textContent : ''; if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const r = await puPost(method, args), [lbl, sl] = PU_MADE[method] || ['Record', ''];
      closeSheet(); toast(`Draft ${esc(lbl)} ${esc(r.name)} created, not submitted · <a target="_blank" rel="noopener" href="/app/${sl}/${encodeURIComponent(r.name)}">Open in ERPNext</a>`);
      if (method === 'draft_material_request') PU.sel = {};
      puFetch(); return r;
    } catch (e) { toast('Could not create: ' + esc(e.message)); if (btn) { btn.disabled = false; btn.textContent = t; } }
  }
  function puPick(title, sub, field, label, onOk) {
    const sh = wbShowSheet(`<label class="cc-field"><span>${esc(label)}</span><input type="text" name="${field}" list="pu_pick" autocomplete="off" data-link="Supplier" placeholder="Supplier"></label><datalist id="pu_pick"></datalist>
      <p class="cc-msg" id="puMsg"></p><div class="cc-sheet-f"><button class="cc-btn primary" type="submit" id="pusave">Create draft</button></div>`, sub, title);
    const f = sh.querySelector('#wbform'); wbLinks(f);
    f.onsubmit = async e => { e.preventDefault(); const v = f.elements[field].value.split(',').map(s => s.trim()).filter(Boolean);
      if (!v.length) { sh.querySelector('#puMsg').textContent = 'Pick a supplier.'; return; } await onOk(v, sh.querySelector('#pusave')); };
  }
  PU.bind = () => {
    const r = $('#puroot'); if (!r) return;
    const redraw = () => { r.innerHTML = PU.body(); PU.bind(); };
    r.querySelectorAll('[data-putab]').forEach(b => b.onclick = () => { PU.tab = b.dataset.putab; PU.lane = b.dataset.pulane || null; PU.laneTab = PU.tab; if (PU.tab === 'pos' && PU.lane === 'done') PU.showDone = true;
      try { localStorage.setItem('cc.purch.tab.' + USER, PU.tab); } catch (e) { } redraw(); const hl = r.querySelector('.pu-hl'); if (hl && hl.scrollIntoView) hl.scrollIntoView({ block: 'nearest', inline: 'center' }); });
    r.querySelectorAll('[data-puview]').forEach(b => b.onclick = () => { PU.view = b.dataset.puview; redraw(); });
    const dn = r.querySelector('#pudone'); if (dn) dn.onchange = () => { PU.showDone = dn.checked; redraw(); };
    r.querySelectorAll('[data-puopen]').forEach(c => { c.onclick = e => { if (e.target.closest('a,button,input')) return; puPoSheet(c.dataset.puopen); }; c.onkeydown = e => { if (e.key === 'Enter') puPoSheet(c.dataset.puopen); }; });
    r.querySelectorAll('[data-pushop]').forEach(c => { c.onclick = e => { if (e.target.closest('a,button,input')) return; puShipSheet(c.dataset.pushop); }; c.onkeydown = e => { if (e.key === 'Enter') puShipSheet(c.dataset.pushop); }; });
    r.querySelectorAll('[data-pusel]').forEach(c => c.onchange = () => { PU.sel[c.dataset.pusel] = c.checked; const b = r.querySelector('#pumrsel'), n = Object.keys(PU.sel).filter(k => PU.sel[k]).length; if (b) { b.disabled = !n; b.textContent = `Draft one MR for selected${n ? ' (' + n + ')' : ''}`; } });
    const ms = r.querySelector('#pumrsel'); if (ms) ms.onclick = () => { const X = PU.data, items = puShort().filter(x => PU.sel[x.item]).map(x => ({ item: x.item, qty: Math.ceil(x.short_firm), schedule_date: x.need_by && x.need_by > X.today ? x.need_by : addDays(X.today, x.lead || 14) }));
      if (items.length) puAct(ms, 'draft_material_request', { items }); };
    r.querySelectorAll('[data-pureorder]').forEach(b => b.onclick = async () => { b.disabled = true; try { await puPost('apply_reorder_level', { item: b.dataset.pureorder, warehouse: b.dataset.wh, level: +b.dataset.level, qty: +b.dataset.qty }); toast('Reorder level saved on ' + esc(b.dataset.pureorder)); puFetch(); } catch (e) { toast('Not saved: ' + esc(e.message)); b.disabled = false; } });
    r.querySelectorAll('[data-puleadf]').forEach(f => f.onsubmit = async e => { e.preventDefault(); const d = f.elements.days.value; if (d === '') return; try { await puPost('set_item_lead_time', { item: f.dataset.puleadf, days: +d }); toast(`Lead time ${+d} days saved on ${esc(f.dataset.puleadf)}`); puFetch(); } catch (err) { toast('Not saved: ' + esc(err.message)); } });
    r.querySelectorAll('[data-pusupf]').forEach(f => f.onsubmit = async e => { e.preventDefault(); const d = f.elements.days.value; try { await puPost('set_supplier_lead_time', { supplier: f.dataset.pusupf, days: d === '' ? null : +d }); toast('Default lead time saved on ' + esc(f.dataset.pusupf)); puFetch(); } catch (err) { toast('Not saved: ' + esc(err.message)); } });
    r.querySelectorAll('[data-purfq]').forEach(b => b.onclick = () => puPick('Request quotes', 'Creates a draft Request for Quotation from ' + esc(b.dataset.purfq) + '. Separate several suppliers with commas.', 'suppliers', 'Suppliers', (v, sb) => puAct(sb, 'make_rfq', { material_request: b.dataset.purfq, suppliers: v })));
    r.querySelectorAll('[data-pupomr]').forEach(b => b.onclick = () => puPick('Order directly', 'Creates a draft Purchase Order from ' + esc(b.dataset.pupomr) + ' without quotes.', 'supplier', 'Supplier', (v, sb) => puAct(sb, 'make_po', { material_request: b.dataset.pupomr, supplier: v[0] })));
    r.querySelectorAll('[data-pusq]').forEach(b => b.onclick = () => { const q = (PU.data.quotes || []).find(x => x.name === b.dataset.pusq) || {}, sups = (q.suppliers || []).map(s => s.supplier);
      const sh = wbShowSheet(`<label class="cc-field"><span>Supplier</span><select name="supplier">${sups.map(s => `<option>${esc(s)}</option>`).join('')}</select></label><p class="small">Creates a draft Supplier Quotation to type in the prices and lead times the vendor sent.</p><p class="cc-msg" id="puMsg"></p><div class="cc-sheet-f"><button class="cc-btn primary" type="submit" id="pusave">Create draft</button></div>`, esc(b.dataset.pusq), 'Enter quote');
      sh.querySelector('#wbform').onsubmit = e => { e.preventDefault(); puAct(sh.querySelector('#pusave'), 'make_supplier_quotation', { rfq: b.dataset.pusq, supplier: sh.querySelector('[name=supplier]').value }); }; });
    r.querySelectorAll('[data-pupo]').forEach(b => b.onclick = () => puAct(b, 'make_po', { supplier_quotation: b.dataset.pupo }));
    r.querySelectorAll('[data-puact]').forEach(b => b.onclick = () => puAct(b, b.dataset.puact, b.dataset.pr ? { purchase_receipt: b.dataset.pr } : b.dataset.ship ? { shipment: b.dataset.ship } : {}));
    const cp = r.querySelector('#pucopy'); if (cp) cp.onclick = async () => { try { await navigator.clipboard.writeText(PU.byItemText()); toast('Copied landed cost by item'); } catch (e) { toast('Copy is blocked in this browser'); } };
    mrBind(r);
    if (PU.data && PU.after) PU.after();
  };
  async function puFetch(manual) {
    if (PU.busy) return; PU.busy = true; PU.err = null;
    try { PU.data = await call(PU_API + 'get_board', {}); PU.at = Date.now(); if (manual) toast('Purchasing refreshed'); }
    catch (e) { PU.err = e.message; }
    PU.busy = false;
    const v = String(S.view || '');
    if (v === 'purch') { const r = $('#puroot'); if (r) { r.innerHTML = PU.body(); PU.bind(); } const st = root.querySelector('.chev'); if (st && PU.data) st.outerHTML = stepper(CUR_M || M(), 'purch'); }
    else if (v.startsWith('so-') && PU.data) render();
    if (PU.data && $('#agpk') && AG.pick && AG.pick.tab === 'suggested') agPickDraw();
  }
  PU.mount = () => {
    const r = $('#purefresh'); if (r) r.onclick = () => puFetch(true);
    PU.bind();
    if (!PU.busy && (!PU.data || Date.now() - PU.at > 120000)) puFetch();
  };
  V.purch = () => header('Purchasing', 'What to order, vendor quotes, purchase orders, inbound shipments, receipts, bills and landed cost. Buttons create drafts; submit in ERPNext.',
    `<div class="toolbar no-print"><details class="pu-new"><summary class="cc-btn soft">+ New</summary><div class="pu-menu"><a target="_blank" rel="noopener" href="/app/material-request/new">Material request</a><a target="_blank" rel="noopener" href="/app/request-for-quotation/new">Request for quotation</a><a target="_blank" rel="noopener" href="/app/purchase-order/new">Purchase order</a><a target="_blank" rel="noopener" href="/app/ill-inbound-shipment/new">Inbound shipment</a></div></details>
      <a class="cc-btn soft" style="text-decoration:none" href="/app/ill-purchasing-settings" target="_blank" rel="noopener">Settings</a><button class="cc-btn soft" id="purefresh">Refresh</button></div>`) +
    `<div id="puroot">${PU.body()}</div>`;

  /* ---------------- production board (manufacturing) ----------------
     The warehouse "Schedule Wizard", live: order queue with build points, capacity burn-down,
     waiting for parts, shipped and on-time. Data: illumenate_lighting...production_board.get_board
     (app endpoint, read-only). Weights and capacity: ilL-Production-Settings. */
  const PB_API = 'illumenate_lighting.illumenate_lighting.api.production_board.get_board';
  const PB_SET_API = 'illumenate_lighting.illumenate_lighting.api.production_board.set_build_counts';
  const PB = { data: null, err: null, busy: false, at: 0, filter: 'all', sort: 'esd', tab: 'flow' };
  const PB_ST = { 1: ['Pend-Prod', 'info'], 2: ['In-Prod', 'good'], 3: ['Pend-Ship', 'good'], 5: ['Held', 'bad'], 7: ['Paint', 'warn'], 9: ['Waiting for parts', 'warn'] };
  const PB_RUNS = [['runs_2c', '2C'], ['runs_3c', '3C'], ['runs_4c', '4C'], ['runs_5c', '5C'], ['runs_6c', '6C'], ['loose', 'Loose'], ['wet', 'WR'], ['fmc', 'FMC'], ['assembly', 'Assy']];
  const pbMoney = v => v == null ? '<span class="calc">—</span>' : money(v);
  const pbPct = (v, flag) => v == null ? '<span class="calc">—</span>' : `<span class="${flag != null && v > flag ? 'pb-hi' : ''}">${(v * 100).toFixed(1)}%</span>`;
  const pbNum = (v, d = 1) => v == null ? '—' : (+v).toLocaleString('en-US', { maximumFractionDigits: d });
  const pbN = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const pbCount = v => v ? pbNum(v, 2) : '<span class="calc">·</span>';
  const pbEsd = r => { if (!r.esd) return '<span class="calc">—</span>'; const k = r.esd < PB.data.today ? 'pb-late' : r.esd === PB.data.today ? 'pb-today' : '';
    return `<span class="${k}" title="${r.esd_is_ship_date ? 'Estimated ship date' : 'No ship date set: delivery date'}">${fmtd(r.esd)}${r.esd_is_ship_date ? '' : '*'}</span>`; };
  const pbWarn = r => r.warnings && r.warnings.length ? ` <span class="badge warn" title="${esc(r.warnings.join('\n'))}">!</span>` : '';
  PB.queueRows = () => {
    const X = PB.data, flag = X.settings.commission_flag_pct;
    let rows = X.queue.filter(r => (PB.filter === 'all' || String(r.status) === PB.filter) && rowOK(r));
    const by = { esd: (a, b) => String(a.esd || '9').localeCompare(String(b.esd || '9')), worth: (a, b) => (b.worth || 0) - (a.worth || 0), points: (a, b) => b.points - a.points };
    rows = rows.slice().sort(by[PB.sort] || by.esd);
    return rows.map(r => `<tr class="${r.past_due ? 'pb-row-late' : ''}"><td>${link('sales-order', r.so, short(r.so))}${pbWarn(r)}<div class="m">${esc(r.customer || '')}</div></td>
      <td class="num">${pbMoney(r.amount)}</td><td class="num">${pbPct(r.com_pct, flag)}</td><td>${pbEsd(r)}</td><td>${badge(PB_ST[r.status][0], PB_ST[r.status][1])}</td>
      ${PB_RUNS.map(([k]) => pbCountCell(r, k)).join('')}
      <td class="num"><b>${pbNum(r.points)}</b>${pbAdjusted(r) ? `<div class="pb-adjm" title="${esc(r.adjust_note || 'Adjusted by hand')}">adjusted</div>` : ''}</td><td class="num">${pbNum(r.hours)}</td><td class="num">${r.worth == null ? '<span class="calc">—</span>' : money(r.worth)}</td><td class="pb-notes">${esc(r.notes)}</td>
      ${X.can_adjust ? `<td class="no-print"><button class="cc-btn soft pb-adjb" data-pbadj="${esc(r.so)}" title="Correct the 2C–6C runs and adders for this order">Edit</button></td>` : ''}</tr>`);
  };
  /* Floor corrections: the counted totals come from the pinned builds; the order stores the difference. */
  const pbAdjusted = r => r.adjustments && Object.keys(r.adjustments).length > 0;
  const pbCounted = (r, k) => Math.max((r.counts[k] || 0) - ((r.adjustments || {})[k] || 0), 0);
  const pbCountCell = (r, k) => {
    const d = (r.adjustments || {})[k];
    if (!d) return `<td class="num">${pbCount(r.counts[k])}</td>`;
    return `<td class="num pb-adjc" title="Counted from the build: ${pbNum(pbCounted(r, k), 2)}. Adjusted ${d > 0 ? '+' : ''}${pbNum(d, 2)}${r.adjust_note ? ': ' + esc(r.adjust_note) : ''}">${pbCount(r.counts[k])}</td>`;
  };
  function pbAdjust(so) {
    const r = PB.data && PB.data.queue.find(x => x.so === so); if (!r) return;
    const inputs = PB_RUNS.map(([k, n]) => fld(`${n} <span class="calc">counted ${pbNum(pbCounted(r, k), 2)}</span>`,
      `<input type="number" name="pbc_${k}" min="0" step="any" inputmode="decimal" value="${+(r.counts[k] || 0)}">`)).join('');
    sheet('Edit build counts', `${link('sales-order', r.so, short(r.so))} · ${esc(r.customer || '')}`,
      `<p class="small">Set the order's totals when the configured fixtures don't show all of the work. Runs are by conductor count; WR, FMC, Assy and Loose are the adders. The difference from what the builds count is saved on the sales order, kept through recounts, and noted on its timeline.</p>
      <div class="pb-adjg">${inputs}</div>
      ${fld('Why', `<textarea name="pbnote" rows="2" maxlength="500" placeholder="e.g. Field splice adds a 3C run">${esc(r.adjust_note || '')}</textarea>`)}
      ${pbAdjusted(r) ? '<label class="small" style="display:flex;gap:6px;align-items:center;margin-bottom:10px"><input type="checkbox" name="pbreset"> Clear every adjustment and go back to the counted totals</label>' : ''}`,
      async el => {
        const reset = el.querySelector('[name=pbreset]') && el.querySelector('[name=pbreset]').checked;
        const counts = {}; PB_RUNS.forEach(([k]) => { const v = val(el, 'pbc_' + k); if (v !== '') counts[k] = +v; });
        if (!reset && Object.values(counts).some(v => !(v >= 0))) throw new Error('counts must be zero or more');
        const res = await call(PB_SET_API, { sales_order: r.so, counts: JSON.stringify(counts), note: val(el, 'pbnote'), reset: reset ? 1 : 0 });
        Object.assign(r, { counts: res.counts, adjustments: res.adjustments, adjust_note: res.adjust_note, points: res.points, hours: res.hours });
        PB.at = 0; toast(`${esc(short(r.so))}: build points now ${pbNum(res.points)}`);
      }, 'Save counts');
  }
  // Flow (v9) leads; the rest are the Schedule Wizard workbook's views, kept for reporting.
  const PB_TABS = [['flow', 'Flow'], ['labels', 'Labels'], ['reels', 'Reel count'], ['board', 'Schedule board'], ['mrs', 'Material requests'], ['inbound', 'Run rate & daily $'], ['report', 'Monthly report'], ['releases', 'Releases & holds'], ['prowc', 'Proforma & will call'], ['paint', 'Paint']];
  const PB_MR_LANES = [['draft', 'Draft', 'mute'], ['needs_wo', 'Needs work order', 'warn'], ['building', 'Building', 'info'], ['done', 'Done (30 days)', 'good']];
  const pbMrOpen = X => (X.material_requests || []).filter(r => r.lane !== 'done');
  const pbMonth = m => new Date(m + 'T12:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  const pbSo = r => `${link('sales-order', r.so, short(r.so))}<div class="m">${esc(r.customer || '')}</div>`;
  try { const t = localStorage.getItem('cc.mfg.tab.' + USER); if (t && PB_TABS.some(x => x[0] === t)) PB.tab = t; } catch (e) { }
  // Labels and Reel count only show when their flag is on and the user may use them (pbTabOn, labels section below)
  const pbTabs = () => { const X = PB.data, mrN = X ? pbMrOpen(X).length : 0, mrLate = X ? pbMrOpen(X).some(r => r.late) : false, lbN = LB.total;
    return `<div class="seg pb-tabs no-print">${PB_TABS.filter(([k]) => pbTabOn(k) || PB.tab === k).map(([k, n]) => `${k === 'board' ? '<span class="pb-tabsep" title="The Schedule Wizard workbook\'s views, kept for reporting">Reports</span>' : ''}<button data-pbt="${k}" class="${PB.tab === k ? 'on' : ''}">${n}${k === 'mrs' && mrN ? ` <span class="badge ${mrLate ? 'bad' : 'info'}">${mrN}</span>` : ''}${k === 'labels' && lbN ? ` <span class="badge info">${lbN}</span>` : ''}</button>`).join('')}</div>`; };
  const pbTabBind = () => root.querySelectorAll('[data-pbt]').forEach(b => b.onclick = () => { PB.tab = b.dataset.pbt; try { localStorage.setItem('cc.mfg.tab.' + USER, PB.tab); } catch (e) { } $('#pbroot').innerHTML = PB.body(); PB.bind(); });
  const pbTabsRedraw = () => { const t = $('#pbroot .pb-tabs'); if (t) { t.outerHTML = pbTabs(); pbTabBind(); } };
  PB.body = () => {
    const X = PB.data; PB.after = null;
    const tabs = pbTabs();
    if (PB.tab === 'flow') return tabs + `<div id="flroot">${FL.body()}</div>`;
    if (PB.tab === 'labels') return tabs + `<div id="lbroot">${LB.body()}</div>`;
    if (PB.tab === 'reels') return tabs + `<div id="rlroot">${RL.body()}</div>`;
    if (!X) return tabs + (PB.err ? `<div class="err">Couldn't load the production board: ${esc(PB.err)}</div>` : '<div class="empty">Loading the production board…</div>');
    const money0 = X.money || PB.tab === 'mrs' ? '' : '<p class="small">Dollar figures need the Command Center Finance or Manufacturing Manager role.</p>';
    return tabs + money0 + (({ mrs: PB.mrs, inbound: PB.inbound, report: PB.report, releases: PB.releases, prowc: PB.prowc, paint: PB.paint })[PB.tab] || PB.board)(X);
  };
  /* Manufacture-type Material Requests (the Purchasing desk only shows Purchase ones). Lanes follow their work orders. */
  PB.mrs = X => {
    const rows = (X.material_requests || []).filter(rowOK), open = pbMrOpen(X);
    const cardFn = r => `<div class="tcard"><div class="r">${link('material-request', r.name, r.name.replace(/^MAT-MR-\d{4}-/, 'MR '))}${r.schedule_date ? (r.late ? badge('Needed ' + fmtd(r.schedule_date), 'bad') : `<span class="small">Needed ${fmtd(r.schedule_date)}</span>`) : ''}</div>
      <div class="m" style="margin-top:6px">${r.items.slice(0, 3).map(i => `${esc(i.item_name || i.item)} × ${pbNum(i.qty, 2)}`).join('<br>')}${r.items.length > 3 ? `<br>+ ${r.items.length - 3} more` : ''}</div>
      ${r.sales_orders.map(so => `<div class="qchip">For ${link('sales-order', so, short(so))}</div>`).join('')}
      ${r.work_orders.map(w => `<span class="qchip" title="${esc(w.status)} · ${pbNum(w.produced_qty, 2)} of ${pbNum(w.qty, 2)} made">WO ${link('work-order', w.name, String(w.name).split('-').slice(-1)[0])} · ${esc(w.status)}</span>`).join('')}
      ${r.docstatus === 0 ? '<div class="small" style="margin-top:6px">Draft: submit in ERPNext</div>' : r.lane === 'needs_wo' ? `<div class="small" style="margin-top:6px"><a target="_blank" rel="noopener" href="${docUrl('material-request', r.name)}">Open to create a work order</a></div>` : ''}</div>`;
    const cols = PB_MR_LANES.map(([k, n, tone]) => { const cs = rows.filter(r => r.lane === k);
      return `<div class="bcol"><div class="lane-h"><span><span class="dot ${tone}"></span> ${esc(n)}</span><span class="ct">${cs.length}</span></div>${cs.map(cardFn).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`; });
    return `<div class="ex-kpis pb-kpis">${stat('Open requests', open.length, 'Manufacture-type material requests')}${stat('Need a work order', open.filter(r => r.lane === 'needs_wo').length, 'Submitted, no work order yet', open.some(r => r.lane === 'needs_wo') ? 'warn' : '')}${stat('Past needed date', open.filter(r => r.late).length, 'Not finished by the required date', open.some(r => r.late) ? 'bad' : '')}</div>
      <div class="toolbar no-print" style="margin-bottom:12px"><a class="cc-btn soft" style="text-decoration:none" target="_blank" rel="noopener" href="/app/material-request/new?material_request_type=Manufacture">+ New manufacture request</a><a class="cc-btn soft" style="text-decoration:none" target="_blank" rel="noopener" href="/app/material-request?material_request_type=Manufacture">All in ERPNext</a></div>
      <div class="board pu-board" style="grid-template-columns:repeat(${PB_MR_LANES.length},minmax(220px,1fr))">${cols.join('')}</div>`;
  };
  PB.inbound = X => {
    const I = X.inbound, Dd = X.daily, flag = X.settings.commission_flag_pct;
    const days = I.days.slice().reverse();
    const kpis = [
      stat('Received today', pbMoney(I.today_amount), I.today ? pbN(I.today.count, 'order') + (I.today.rush ? ` · ${I.today.rush} rush` : '') : 'Not a workday'),
      stat('Average per day this month', pbMoney(I.month_avg_amount), 'Workdays before today'),
      stat('Average per day, last 30 workdays', pbMoney(I.avg_30_amount), 'Used for the run-rate estimate'),
      stat('Received this month', pbMoney(I.month_received_amount), ''),
      stat('Shipped per day this month', pbMoney(Dd.average_amount), Dd.needed_amount != null ? `Need ${money(Dd.needed_amount)}/day to reach the goal` : 'Days with shipments'),
    ];
    const rows = I.days.map(r => `<tr><td>${fmtd(r.date)}</td><td class="num">${r.count}</td><td class="num">${pbMoney(r.amount)}</td><td class="num">${pbPct(r.com_pct, flag)}</td><td class="num">${r.zero || ''}</td><td class="num">${r.same_day || ''}</td><td class="num">${r.next_day || ''}</td><td class="num">${r.rush || ''}</td></tr>`);
    const drows = Dd.days.map(r => `<tr><td>${fmtd(r.date)}</td><td class="num">${r.count || ''}</td><td class="num">${r.date > X.today ? '<span class="calc">—</span>' : pbMoney(r.amount)}</td></tr>`);
    PB.after = () => {
      if (!X.money) return;
      vbars($('#pbinb'), days.map(r => fmtd(r.date)), [{ name: 'Received', color: '#2a78d6', values: days.map(r => r.amount) }], { target: X.goal.needed_per_day || 0, targetLabel: X.goal.needed_per_day ? 'Needed per day' : '', fmt: kfmt, h: 220 });
      const past = Dd.days.filter(r => r.date <= X.today);
      vbars($('#pbdaily'), past.map(r => fmtd(r.date)), [{ name: 'Shipped', color: '#12b76a', values: past.map(r => r.amount) }], { target: Dd.needed_amount || 0, targetLabel: Dd.needed_amount ? 'Needed per day' : '', fmt: kfmt, h: 220 });
    };
    return `<div class="ex-kpis pb-kpis">${kpis.join('')}</div><div class="grid">
      ${card('Orders received per workday', 'Run rate: submitted sales orders by order date, last 30 workdays.', X.money ? '<div class="chart" id="pbinb"></div>' : '<div class="empty">Needs the finance role</div>', 's12')}
      ${tableCard('Inbound by day', 'Same day = ship date is the day received. Next day = the next workday. Rush = ship date within 3 workdays.', ['Received', '#Orders', '#$', '#Com %', '#$0 orders', '#Same day', '#Next day', '#Rush'], rows, '', 's7')}
      ${card('Daily dollars', 'Shipped (delivery notes) per workday this month.', (X.money ? '<div class="chart" id="pbdaily"></div>' : '') + `<div class="tw"><table><thead><tr><th>Day</th><th class="num">Shipments</th><th class="num">$</th></tr></thead><tbody>${drows.join('')}</tbody></table></div>`, 's5')}
    </div>`;
  };
  PB.report = X => {
    const R = X.reporting, flag = X.settings.commission_flag_pct;
    const line = (label, key, fmt, note) => `<tr><td>${label}${note ? `<div class="m">${note}</div>` : ''}</td>${R.map(m => `<td class="num">${fmt(m[key], m)}</td>`).join('')}</tr>`;
    const pct = v => v == null ? '<span class="calc">—</span>' : `<b class="${v < 1 ? 'pb-hi' : 'pb-ok'}">${Math.round(v * 100)}%</b>`;
    const body = [
      line('Goal', 'goal_amount', v => v ? pbMoney(v) : '<span class="calc">not set</span>'),
      line('Shipped', 'shipped_amount', pbMoney, 'Delivery notes this month'),
      line('Scheduled / available to ship', 'scheduled_amount', pbMoney, 'Open orders by ship date (WFP by part ETA), incl. hold for ship'),
      line('Estimated run rate', 'run_rate_amount', (v, m) => pbMoney(v) + `<div class="m">${m.workdays} workdays</div>`, '30-day average received per day × workdays left'),
      line('At risk', 'at_risk_amount', pbMoney, 'Waiting for parts and going to miss, plus held orders'),
      line('Expected releases', 'release_amount', pbMoney, 'Hold for release / confirmation by likely ship date'),
      line('<b>Projection</b>', 'projected_amount', v => `<b>${pbMoney(v)}</b>`),
      line('Projection without at-risk', 'projected_safe_amount', pbMoney),
      line('Projection vs goal', 'goal_pct', pct),
      line('Avg commission (known orders)', 'com_pct', v => pbPct(v, flag)),
    ];
    return `<div class="grid"><div class="card flush s12"><div class="card-h"><div><h2>Monthly report</h2><div class="sub">This month and the next two against the shipping goal (goals are set in Weights &amp; capacity).</div></div></div>
      <div class="tw"><table class="pb-rep"><thead><tr><th></th>${R.map(m => `<th class="num">${pbMonth(m.month)}</th>`).join('')}</tr></thead><tbody>${body.join('')}</tbody></table></div></div></div>`;
  };
  PB.releases = X => {
    const Rl = X.releases, H = X.ship_holds, flag = X.settings.commission_flag_pct;
    const mcards = Rl.months.map(m => stat(pbMonth(m.month), pbMoney(m.amount), `${pbN(m.count, 'release')}${X.money ? ' · com ' + pbPct(m.com_pct, flag) : ''}`));
    const rrows = Rl.rows.filter(rowOK).sort((a, b) => String(a.likely_ship || '9').localeCompare(String(b.likely_ship || '9'))).map(r => `<tr><td>${pbSo(r)}</td><td class="num">${pbMoney(r.amount)}</td><td class="num">${pbPct(r.com_pct, flag)}</td><td>${r.likely_ship ? fmtd(r.likely_ship) : badge('No date', 'warn')}</td><td>${esc(r.hold_reason.replace('Hold for ', ''))}</td>
      <td class="num">${pbNum(r.release_points)}</td><td class="num">${pbNum(r.release_days, 2)}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`);
    const hrows = H.rows.filter(rowOK).map(r => `<tr><td>${pbSo(r)}</td><td class="num">${pbMoney(r.amount)}</td><td class="num">${pbPct(r.com_pct, flag)}</td><td>${pbEsd(r)}</td><td class="num">${r.days_until == null ? '—' : r.days_until}</td><td class="num">${pbNum(r.points)}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`);
    return `<div class="ex-kpis pb-kpis">${mcards.join('')}${stat('Release workload', pbNum(Rl.points) + ' <span class="small">pts</span>', `${pbNum(Rl.days, 2)} days at today's capacity (release weights)`)}</div>
      <div class="grid">
      ${tableCard('Expected releases', `Hold for release / confirmation. Set Hold Reason and Likely Ship Date on the sales order.${Rl.no_date ? ` ${Rl.no_date} without a likely ship date.` : ''}`, ['Sales order', '#$', '#Com %', 'Likely ship', 'Hold', '#Release pts', '#Days', 'Notes'], rrows)}
      <div class="ex-kpis pb-kpis s12" style="margin:0">${stat('Hold for ship', pbMoney(H.total_amount), pbN(H.rows.length, 'order'))}${stat('Through next month', pbMoney(H.through_next_month_amount), 'Ship date by end of next month')}${stat('Within a week', pbMoney(H.week_amount), 'Ship date in 7 days or less')}</div>
      ${tableCard('Hold for ship', 'Built or buildable; the customer asked us to hold it until the ship date.', ['Sales order', '#$', '#Com %', 'Ship date', '#Days away', '#Points', 'Notes'], hrows)}
      </div>`;
  };
  PB.prowc = X => {
    const P = X.prowc, flag = X.settings.commission_flag_pct;
    const sc = (n, o) => [stat(n + ' open', pbMoney(o.open_amount), pbN(o.open_count, 'order')), stat(n + ' completed this month', pbMoney(o.completed_amount), `${pbN(o.completed_count, 'order')}${X.money ? ' · com ' + pbPct(o.com_pct, flag) : ''}`)];
    const orows = P.rows.filter(rowOK).map(r => `<tr><td>${pbSo(r)}</td><td>${esc(r.prowc)}</td><td class="num">${pbMoney(r.amount)}</td><td class="num">${pbPct(r.com_pct, flag)}</td><td>${pbEsd(r)}</td><td>${badge(PB_ST[r.status][0], PB_ST[r.status][1])}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`);
    const crows = P.completed.filter(rowOK).map(s => `<tr><td>${s.so ? link('sales-order', s.so, short(s.so)) : ''}<div class="m">${esc(s.customer || '')}</div></td><td>${esc(s.prowc)}</td><td class="num">${pbMoney(s.amount)}</td><td class="num">${pbPct(s.com_pct, flag)}</td><td>${fmtd(s.shipped)}</td><td>${link('delivery-note', s.delivery_note)}</td></tr>`);
    return `<div class="ex-kpis pb-kpis">${[...sc('Proforma', P.proforma), ...sc('Will call', P.will_call)].join('')}</div><div class="grid">
      ${tableCard('Open proforma and will-call orders', 'Set Proforma / Will Call on the sales order.', ['Sales order', 'Type', '#$', '#Com %', 'Ship date', 'Status', 'Notes'], orows)}
      ${tableCard('Completed this month', 'Shipped or picked up (delivery notes).', ['Sales order', 'Type', '#$', '#Com %', 'Completed', 'Delivery note'], crows)}</div>`;
  };
  PB.paint = X => {
    const P = X.paint;
    const rows = P.rows.filter(rowOK).map(r => {
      const jobs = r.paint || [];
      return `<tr><td>${pbSo(r)}</td><td class="num">${pbMoney(r.amount)}</td><td>${pbEsd(r)}</td><td>${[...new Set(jobs.map(j => j.po))].map(po => link('purchase-order', po)).join('<br>') || '<span class="calc">Marked by hand</span>'}</td>
        <td>${jobs[0] && jobs[0].sent ? fmtd(jobs[0].sent) : '—'}</td><td>${jobs.length ? fmtd(jobs.map(j => j.due_back).filter(Boolean).sort().pop()) : '—'}</td>
        <td>${jobs.slice(0, 4).map(j => `${esc(j.item_name || j.item)} <span class="calc">${pbNum(j.qty, 2)}</span>`).join('<br>')}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`;
    });
    return `<div class="ex-kpis pb-kpis">${stat('At paint', pbMoney(P.total_amount), pbN(P.rows.length, 'order'))}${stat('Due back this month', pbMoney(P.month_amount), pbN(P.month_count, 'order'))}</div>
      ${P.supplier_group ? '' : '<p class="small">Set the Paint / Finishing Supplier Group in Weights &amp; capacity to pick up paint purchase orders automatically. Until then only orders marked Paint by hand show here.</p>'}
      <div class="grid">${tableCard('Out for paint', 'Open purchase orders to the paint supplier group, linked to the sales order.', ['Sales order', '#$', 'Ship date', 'PO', 'Sent', 'Due back', 'Items', 'Notes'], rows)}</div>`;
  };
  PB.board = X => {
    const flag = X.settings.commission_flag_pct, p = X.pipeline, c = X.capacity, g = X.goal, sh = X.shipped, d = X.due;
    const pipe = [['pend_prod', 'Pend-Prod'], ['in_prod', 'In-Prod'], ['pend_ship', 'Pend-Ship'], ['wfp', 'Waiting for parts'], ['paint', 'Paint'], ['held', 'Held']]
      .map(([k, n]) => stat(n, X.money ? money(p[k].amount) : p[k].count, `${pbN(p[k].count, 'order')} · ${pbNum(p[k].points)} pts${X.money ? ' · avg com ' + pbPct(p[k].com_pct, flag) : ''}`));
    const nextLbl = new Date(d.next_day.date + 'T12:00').getDay() === 1 ? 'Due Monday' : 'Due tomorrow';
    const dueCards = [['Past due', d.past_due, 'bad'], ['Due today', d.today, 'warn'], [nextLbl, d.next_day, ''], ['Due this week', d.this_week, '']]
      .map(([n, v, k]) => stat(n, v.count, X.money ? money(v.amount) : '', v.count ? k : ''));
    const ship = [
      stat('Shipped today', X.money ? money(sh.today.amount) : sh.today.count, `${pbN(sh.today.count, 'shipment')}${X.money ? ' · com ' + pbPct(sh.today.com_pct, flag) : ''}`),
      stat('Shipped this month', X.money ? money(sh.mtd.amount) : sh.mtd.count, `${pbN(sh.mtd.count, 'shipment')}${X.money ? ' · com ' + pbPct(sh.mtd.com_pct, flag) : ''}`),
      stat('Available to ship', X.money ? money(g.available_to_ship) : '—', 'Open orders slated this month (not held)'),
      g.month_goal ? stat('Gap to goal', money(g.gap), `Goal ${money(g.month_goal)} · need ${money(g.needed_per_day)}/day over ${g.shipping_days_left} days`, g.gap > 0 ? 'bad' : 'good')
        : stat('Shipping days left', g.shipping_days_left, X.money ? 'Set a monthly goal in Production Settings' : ''),
      stat('On-time this month', sh.on_time_pct == null ? '—' : Math.round(sh.on_time_pct * 100) + '%', 'Shipped by the estimated ship date, or not warehouse fault', sh.on_time_pct != null && sh.on_time_pct < 0.95 ? 'bad' : ''),
    ];
    const capBody = `<div class="pb-cap">
      <div><div class="small">Workload</div><div class="pb-big">${pbNum(c.workload)} <span class="small">pts</span></div><div class="small">${pbNum(c.whse_points)} in-house (${pbNum(c.in_prod_points)} in production) + ${pbNum(c.wfp_month_points)} waiting for parts due this month</div></div>
      <div><div class="small">Capacity per day</div><div class="pb-big">${pbNum(c.capacity_per_day)}</div><div class="small">${pbNum(X.settings.points_per_person_day)} pts × ${pbNum(X.settings.headcount, 2)} people · ${pbNum(c.left_today)} left today</div></div>
      <div><div class="small">Days to complete</div><div class="pb-big">${pbNum(c.days_to_complete, 2)}</div></div>
      <div><div class="small">Date clear</div><div class="pb-big">${c.date_clear ? fmtd(c.date_clear) : 'Over ' + c.burndown.length + ' workdays'}</div></div></div>`;
    const tabs = [['all', 'All'], ['1', 'Pend-Prod'], ['2', 'In-Prod'], ['3', 'Pend-Ship'], ['7', 'Paint'], ['5', 'Held']]
      .map(([k, n]) => `<button data-pbf="${k}" class="${PB.filter === k ? 'on' : ''}">${n}</button>`).join('');
    const sorts = `<select id="pbsort">${[['esd', 'Ship date'], ['worth', '$ per point'], ['points', 'Points']].map(([k, n]) => `<option value="${k}" ${PB.sort === k ? 'selected' : ''}>Sort: ${n}</option>`).join('')}</select>`;
    const qHead = ['Sales order', '#$', '#Com %', 'Ship date', 'Status', ...PB_RUNS.map(([, n]) => '#' + n), '#Points', '#Hrs', '#$ / pt', 'Notes', ...(X.can_adjust ? [''] : [])];
    const wfpRows = X.wfp.filter(rowOK).map(r => `<tr class="${r.going_to_miss ? 'pb-row-late' : ''}"><td>${link('sales-order', r.so, short(r.so))}<div class="m">${esc(r.customer || '')}</div></td><td class="num">${pbMoney(r.amount)}</td><td>${pbEsd(r)}</td>
      <td>${r.eta ? fmtd(r.eta) : badge('No PO', 'bad')}</td><td>${r.going_to_miss ? badge('Going to miss', 'bad') : badge('OK', 'good')}</td><td>${r.this_month ? 'Yes' : 'No'}</td>
      <td class="num">${pbNum(r.points)}</td><td>${r.short_items.slice(0, 4).map(s => `${link('item', s.item)} <span class="calc">${pbNum(s.qty, 2)}${r.no_po_items.includes(s.item) ? ', no PO' : ''}</span>`).join('<br>')}${r.short_items.length > 4 ? `<div class="calc">+${r.short_items.length - 4} more</div>` : ''}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`);
    const shipRows = sh.rows.filter(rowOK).map(s => `<tr><td>${link('delivery-note', s.delivery_note)}</td><td>${s.so ? link('sales-order', s.so, short(s.so)) : ''}<div class="m">${esc(s.customer || '')}</div></td><td class="num">${pbMoney(s.amount)}</td><td class="num">${pbPct(s.com_pct, flag)}</td>
      <td>${fmtd(s.esd)}</td><td>${fmtd(s.shipped)}</td><td>${s.on_time ? badge('On time', 'good') : s.not_warehouse_fault ? badge('Late, not warehouse', 'warn') : badge('Late', 'bad')}</td><td class="pb-notes">${esc(s.late_reason || '')}</td></tr>`);
    const weekly = hbars(sh.weekly.map(w => ({ label: 'Week of ' + fmtd(w.week_of), value: w.on_time_pct == null ? 0 : w.on_time_pct * 100, color: w.on_time_pct != null && w.on_time_pct < 0.95 ? '#eb6834' : '#12b76a', title: pbN(w.shipments, 'shipment') })), { max: 100, fmt: v => Math.round(v) + '%', lw: '130px' });
    PB.after = () => {
      const b = X.capacity.burndown;
      vbars($('#pbburn'), b.map(r => fmtd(r.date)), [{ name: 'Points left', color: '#2a78d6', values: b.map(r => r.remaining) }], { target: X.capacity.capacity_per_day, targetLabel: '1 day of capacity', fmt: v => Math.round(v), h: 220 });
    };
    return `<div class="ex-kpis pb-kpis">${pipe.join('')}</div>
      <div class="ex-kpis pb-kpis">${ship.join('')}</div>
      <div class="ex-kpis pb-kpis">${dueCards.join('')}</div>
      <div class="grid">
        ${card('Capacity', 'Pend-Prod + In-Prod points, plus waiting-for-parts orders whose parts arrive this month', capBody, 's12')}
        ${card('Burn-down', 'Points left at the end of each workday (holidays skipped). The dashed line is one day of capacity.', '<div class="chart" id="pbburn"></div>', 's12')}
        <div class="card flush s12"><div class="card-h"><div><h2>Order queue</h2><div class="sub">Open sales orders by status. Points = runs by conductor count + wet, FMC, assembly and loose adders. * = no ship date set, delivery date shown.</div></div>
          <div class="toolbar"><div class="seg">${tabs}</div>${sorts}</div></div>
          <div class="tw"><table class="pb-q"><thead><tr>${qHead.map(h => `<th class="${h.startsWith('#') ? 'num' : ''}">${h.replace(/^#/, '')}</th>`).join('')}</tr></thead><tbody>${PB.queueRows().join('') || `<tr><td colspan="${qHead.length}" class="empty">Nothing here right now</td></tr>`}</tbody></table></div></div>
        ${tableCard('Waiting for parts', 'Material is handed to orders in ship-date order; ETA is when open purchase orders cover what is still short.', ['Sales order', '#$', 'Ship date', 'ETA', 'Going to miss?', 'This month?', '#Points', 'Short items', 'Notes'], wfpRows)}
        ${tableCard('Shipped this month', 'Delivery notes. On time = shipped on or before the estimated ship date.', ['Delivery note', 'Sales order', '#$', '#Com %', 'Ship date', 'Shipped', 'On time?', 'Why late'], shipRows, '', 's8')}
        ${card('On-time by week', '', weekly, 's4')}
      </div>`;
  };
  async function pbFetch(manual) {
    if (PB.busy) return; PB.busy = true; PB.err = null;
    try { PB.data = await call(PB_API, {}); PB.at = Date.now(); if (manual) toast('Production board refreshed'); }
    catch (e) { PB.err = e.message; }
    PB.busy = false;
    if (S.view === 'mfg') { const r = $('#pbroot'); if (r) { r.innerHTML = PB.body(); PB.bind(); } }
  }
  PB.bind = () => {
    root.querySelectorAll('[data-pbf]').forEach(b => b.onclick = () => { PB.filter = b.dataset.pbf; $('#pbroot').innerHTML = PB.body(); PB.bind(); });
    pbTabBind();
    root.querySelectorAll('[data-pbadj]').forEach(b => b.onclick = () => pbAdjust(b.dataset.pbadj));
    const s = $('#pbsort'); if (s) s.onchange = () => { PB.sort = s.value; $('#pbroot').innerHTML = PB.body(); PB.bind(); };
    if (PB.data && PB.after) { PB.after(); }
    if (PB.tab === 'flow') FL.mount(); else flCfg();
    if (PB.tab === 'labels') LB.bind(); if (PB.tab === 'reels') RL.mount();
    lbPeek();   // cheap: learns the Labels / Reel count flags and the queued count for the badge
  };
  PB.mount = () => {
    const r = $('#pbrefresh'); if (r) r.onclick = () => { if (PB.tab === 'flow') { FL.at = 0; flFetch(true); pbFetch(); } else if (PB.tab === 'labels') lbFetch(true); else if (PB.tab === 'reels') rlFetch(true); else pbFetch(true); };
    PB.bind();
    if (!PB.busy && (!PB.data || Date.now() - PB.at > 120000)) pbFetch();
  };
  /* ---------------- warehouse flow (v9) ----------------
     The same open orders as the production board, told in ERPNext documents instead of workbook codes:
     Sales Order → Work Order → pick materials → build → pick & ship → Delivery Note. Each order sits at the one
     step it is waiting on; "Your list" is those steps with a count and what to do in ERPNext. Data: the app
     endpoint warehouse_flow.get_flow (read-only, no money). The Shipping page shows its ship-side pick list. */
  const FL_API = 'illumenate_lighting.illumenate_lighting.api.warehouse_flow.get_flow';
  const FL = { data: null, err: null, busy: false, at: 0, step: '', showDone: false, hl: '' };
  // [step, label, tone, bar colour]: in floor order (hold last)
  const FL_STEPS = [['needs_wo', 'Needs work orders', 'bad', '#f04438'], ['draft_wo', 'Work orders in draft', 'warn', '#f79009'], ['waiting_parts', 'Waiting for parts', 'warn', '#eda100'],
    ['to_pick', 'Pick materials', 'info', '#2a78d6'], ['building', 'Building', 'info', '#6250d6'], ['to_ship', 'Pick & ship', 'good', '#12b76a'], ['held', 'On hold', 'mute', '#98a2b3']];
  const FL_LANES = [['draft', 'Draft', 'warn', 'Submit in ERPNext so the floor can start'], ['to_pick', 'Ready to pick', 'info', 'Materials are on the shelf'], ['waiting_parts', 'Waiting for parts', 'warn', 'Short once earlier ship dates take stock'],
    ['in_process', 'In production', 'info', 'Materials moved; Finish books the build'], ['completed', 'Completed', 'good', 'Last 14 days, or still to ship'], ['stopped', 'Stopped', 'bad', 'A stopped work order holds its order']];
  const FL_UOM = { inch: 'in', inches: 'in', foot: 'ft', feet: 'ft', meter: 'm', metre: 'm', meters: 'm', millimeter: 'mm' };
  const flN = v => (+v || 0).toLocaleString('en-US', { maximumFractionDigits: 1 });
  const flU = u => esc(FL_UOM[String(u || '').toLowerCase()] || u || '');
  const FL_PCS = ['nos', 'no', 'ea', 'each', 'unit', 'units', 'pc', 'pcs', 'piece', 'pieces', 'set', 'sets', 'pair', 'kit', 'box'];
  const flSum = rows => { const o = { lines: 0, pieces: 0, other: [] }, by = {};
    rows.forEach(r => { if (!(r.qty > 0)) return; o.lines++; if (FL_PCS.includes(String(r.uom || '').trim().toLowerCase())) o.pieces += r.qty; else by[r.uom || 'units'] = (by[r.uom || 'units'] || 0) + r.qty; });
    o.other = Object.entries(by).map(([uom, qty]) => ({ uom, qty })); return o; };
  const flQty = s => { if (!s) return '—'; const p = [];
    if (s.pieces) p.push(`${flN(s.pieces)} pcs`);
    (s.other || []).forEach(o => p.push(`${flN(o.qty)} ${flU(o.uom)}`));
    return p.join(' + ') || 'nothing'; };
  const flStep = k => { const s = FL_STEPS.find(x => x[0] === k) || [k, k, 'mute']; return badge(s[1], s[2]); };
  const flWO = n => link('work-order', n, 'WO ' + String(n).split('-').slice(-1)[0]);
  const flLaneOf = n => ((FL.data && FL.data.work_orders.find(w => w.name === n)) || {}).lane;
  const flLaneTone = k => (FL_LANES.find(x => x[0] === k) || [0, 0, 'mute'])[2];
  const flEsd = r => !r.esd ? '<span class="calc">No date</span>' : `<span class="${r.past_due ? 'pb-late' : r.esd === FL.data.today ? 'pb-today' : ''}" title="${r.esd_is_ship_date === false ? 'No ship date set: delivery date' : 'Estimated ship date'}">${fmtd(r.esd)}${r.esd_is_ship_date === false ? '*' : ''}</span>`;
  const flCard = (id, title, sub, body, cls, right = '') => `<div class="card ${cls}" id="${id}"><div class="card-h"><div><h2>${title}</h2>${sub ? `<div class="sub">${sub}</div>` : ''}</div>${right}</div>${body}</div>`;
  const flTable = (head, rows, empty) => `<div class="tw"><table><thead><tr>${head.map(h => `<th class="${h.startsWith('#') ? 'num' : ''}">${h.replace(/^#/, '')}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${head.length}" class="empty">${empty || 'Nothing here right now'}</td></tr>`}</tbody></table></div>`;

  // The document chain, left to right. Each tile jumps to its section.
  FL.strip = X => { const s = X.summary, L = s.wo_lanes;
    const tiles = [
      ['fl-orders', 'Sales orders', 'Sales Order', s.orders, `submitted & open${s.past_due ? ` · ${s.past_due} past ship date` : ''}`, s.past_due ? 'bad' : ''],
      ['fl-orders', 'Work orders', 'Work Order', `${s.covered}/${s.build_orders}`, `orders with every build covered${s.lines_need_wo ? ` · ${pbN(s.lines_need_wo, 'line')} need one` : ''}`, s.lines_need_wo ? 'bad' : L.draft ? 'warn' : ''],
      ['fl-pick', 'Pick materials', 'Material transfer', L.to_pick, `work orders ready · ${flQty(s.pick_production)}`, ''],
      ['fl-wos', 'Building', 'Work Order · In process', L.in_process, `${L.waiting_parts} waiting for parts`, L.waiting_parts ? 'warn' : ''],
      ['fl-ship', 'Pick & ship', 'Pick List → Delivery Note', s.steps.to_ship, flQty(s.pick_shipping), s.pick_shipping.short_orders ? 'warn' : ''],
      ['fl-ship', 'Shipped', 'Delivery Note · 7 days', s.shipped_week, 'submitted delivery notes', ''],
    ];
    return `<div class="pu-flow fl-flow">${tiles.map(([id, n, dt, v, sub, tone], i) => `${i ? '<span class="pu-arrow" aria-hidden="true">→</span>' : ''}<button type="button" class="pu-step" data-flgo="sec:${id}">
      <span class="pu-step-n">${esc(n)}${tone ? `<span class="dot ${tone}"></span>` : ''}</span><span class="pu-step-v">${esc(v)}</span><span class="pu-step-s" title="${esc(sub.replace(/<[^>]+>/g, ''))}">${sub}</span><span class="fl-dt">${esc(dt)}</span></button>`).join('')}</div>`;
  };
  // The warehouse manager's list: one row per step that has something in it, with the ERPNext move that clears it.
  FL.todo = X => { const s = X.summary, L = s.wo_lanes, st = s.steps;
    const draftOpen = X.work_orders.filter(w => w.lane === 'draft' && w.so_open).length;
    const orphan = X.work_orders.filter(w => w.lane !== 'completed' && w.so && !w.so_open).length;
    const clean = orphan + s.draft_dns_stale + s.pick_lists_stale;
    const items = [
      [st.needs_wo, 'bad', `${pbN(st.needs_wo, 'sales order')} need${st.needs_wo === 1 ? 's' : ''} work orders`, `${pbN(s.lines_need_wo, 'build line')} with no work order. In ERPNext: open the order → Create → Work Order.`, 'step:needs_wo'],
      [draftOpen, 'warn', `${pbN(draftOpen, 'draft work order')} to submit`, 'A draft work order doesn\'t reserve material or reach the floor until it is submitted.', 'lane:draft'],
      [L.to_pick, 'info', `${pbN(L.to_pick, 'work order')} ready to pick materials`, `${flQty(s.pick_production)} to pull. In ERPNext: work order → Start (material transfer), or Create → Pick List.`, 'sec:fl-pick'],
      [L.waiting_parts, 'warn', `${pbN(L.waiting_parts, 'work order')} waiting for parts`, 'Short once earlier ship dates take their stock. Purchasing has the ETAs.', 'lane:waiting_parts'],
      [L.in_process, 'info', `${pbN(L.in_process, 'work order')} in production`, 'When built: work order → Finish, so the finished goods land in stock.', 'lane:in_process'],
      [st.to_ship, 'good', `${pbN(st.to_ship, 'order')} to pick & ship`, `${flQty(s.pick_shipping)}${s.pick_shipping.short_orders ? ` · ${s.pick_shipping.short_orders} short in ERPNext stock` : ''}. In ERPNext: sales order → Create → Pick List, then Delivery Note.`, 'go:ship'],
      [s.draft_dns, 'warn', `${pbN(s.draft_dns, 'draft delivery note')} to submit`, 'Submit it once the order has left the building.', 'go:ship'],
      [st.held, 'mute', `${pbN(st.held, 'order')} on hold`, 'Hold reason, On Hold status or a stopped work order. Nothing to do until it is released.', 'step:held'],
      [clean, 'mute', 'Clean-up: drafts for closed orders', `${[orphan && pbN(orphan, 'work order'), s.draft_dns_stale && pbN(s.draft_dns_stale, 'draft delivery note'), s.pick_lists_stale && pbN(s.pick_lists_stale, 'pick list')].filter(Boolean).join(', ')} tied to orders that are closed or delivered.`, 'sec:fl-clean'],
    ].filter(x => x[0]);
    const body = items.length ? `<div class="fl-todo-list">${items.map(([n, tone, t, sub, go]) => `<button type="button" class="fl-todo" data-flgo="${go}"><span class="fl-n ${tone}">${n}</span><span><span class="fl-t">${t}</span><span class="fl-s">${sub}</span></span><span class="fl-go" aria-hidden="true">→</span></button>`).join('')}</div>`
      : '<div class="empty">Nothing waiting on the warehouse right now</div>';
    return flCard('fl-todo', 'Your list', 'What the open orders are waiting on, most urgent first. Click a row to see the documents.', body, 's6');
  };
  // Sales orders → work orders: coverage ring, where every order sits, and the order table.
  FL.cover = X => { const s = X.summary, tot = s.orders || 1;
    const seg = FL_STEPS.filter(([k]) => s.steps[k]).map(([k, n, , c]) => `<i style="width:${s.steps[k] / tot * 100}%;background:${c}" title="${esc(n)}: ${s.steps[k]}"></i>`).join('');
    const leg = FL_STEPS.filter(([k]) => s.steps[k]).map(([k, n, , c]) => `<button type="button" class="${FL.step === k ? 'on' : ''}" data-flstep="${k}"><i style="background:${c}"></i>${esc(n)} <b>${s.steps[k]}</b></button>`).join('');
    const cov = [['Every build line has a work order', s.covered, 'good'], ['Some lines still need one', s.partly, 'warn'], ['No work orders yet', s.uncovered, 'bad']];
    const body = `<div class="fl-cov">${ring(s.covered, s.build_orders, '#12b76a', `of ${s.build_orders} covered`, 120)}
        <div>${cov.map(([n, v, k]) => `<div class="fl-kv"><span>${sdot(n, k)}</span><b>${v}</b></div>`).join('')}
        <div class="fl-kv"><span>${sdot('Stock only (nothing to build)', 'mute')}</span><b>${s.stock_only}</b></div></div></div>
      <div class="eyebrow" style="margin:18px 0 8px">Where each order is</div><div class="fl-bar">${seg || '<i style="width:100%;background:var(--line)"></i>'}</div>
      <div class="fl-leg">${leg}</div>`;
    return flCard('fl-cover', 'Sales orders → work orders', `${pbN(s.orders, 'submitted sales order')} still to ship; ${s.build_orders} ${s.build_orders === 1 ? 'has' : 'have'} build lines (items with a BOM).`, body, 's6');
  };
  FL.orders = X => {
    const rows = X.orders.filter(r => (!FL.step || r.step === FL.step) && rowOK(r));
    const segs = [['', 'All', X.orders.length], ...FL_STEPS.filter(([k]) => X.summary.steps[k]).map(([k, n]) => [k, n, X.summary.steps[k]])]
      .map(([k, n, c]) => `<button data-flstep="${k}" class="${FL.step === k ? 'on' : ''}">${esc(n)} <span class="calc">${c}</span></button>`).join('');
    const tr = r => { const chips = r.work_orders.map(n => `<span class="fl-chip"><span class="dot ${flLaneTone(flLaneOf(n))}"></span>${flWO(n)}</span>`).join('');
      const flags = [r.parts_short && badge('Parts short', 'warn'), r.pick_short && badge('Short in stock', 'warn'), ...r.pick_lists.map(p => `<span class="fl-chip">Pick list ${link('pick-list', p, String(p).split('-').slice(-1)[0])}</span>`),
        ...r.draft_dns.map(d => `<span class="fl-chip">Draft ${link('delivery-note', d, 'delivery note')}</span>`), r.hold_reason && badge(r.hold_reason, 'mute')].filter(Boolean).join(' ');
      return `<tr class="fl-row ${r.past_due ? 'pb-row-late' : ''}" data-flopen="Sales Order|${esc(r.so)}"><td>${link('sales-order', r.so, short(r.so))}<div class="m">${esc(r.customer)}</div></td><td>${flEsd(r)}</td><td>${flStep(r.step)}</td>
        <td>${r.build_lines ? `<b>${r.build_covered}/${r.build_lines}</b> <span class="calc">build lines</span>` : '<span class="calc">Stock only</span>'}${chips ? `<div>${chips}</div>` : ''}
          ${r.needs_wo.length ? `<div class="m">Needs a work order: ${r.needs_wo.slice(0, 3).map(n => `${esc(n.item_name)} × ${flN(n.missing)}`).join('; ')}${r.needs_wo.length > 3 ? `; + ${r.needs_wo.length - 3} more` : ''}</div>` : ''}</td>
        <td><div>${esc(r.next)}</div>${r.step === 'to_ship' && r.pick.length ? `<div class="m">Pick ${flQty(r.pick_summary)}</div>` : ''}${flags ? `<div style="margin-top:4px">${flags}</div>` : ''}</td></tr>`; };
    return `<div class="card flush s12" id="fl-orders"><div class="card-h"><div><h2>Submitted sales orders</h2><div class="sub">Every open order at the one step it is waiting on, earliest ship date first. Chips are its work orders, coloured by lane. * = no ship date set, delivery date shown. Click any order, work order, item or pick list for its details; floor notes, ship dates and holds can be edited there. Ctrl/⌘-click opens ERPNext.</div></div></div>
      <div style="padding:0 24px"><div class="seg pb-tabs">${segs}</div></div>${flTable(['Sales order', 'Ship date', 'Step', 'Work orders', 'Next'], rows.map(tr), FL.step ? 'No orders at this step' : '')}</div>`;
  };
  // Every work order in a lane.
  FL.wos = X => {
    const lanes = FL_LANES.filter(([k]) => k !== 'stopped' || X.summary.wo_lanes.stopped);
    const card = w => { const pct = w.qty ? Math.min(100, w.produced / w.qty * 100) : 0, pk = flSum(w.pick);
      return `<div class="tcard fl-wo" data-flopen="Work Order|${esc(w.name)}" title="Details and edit"><div class="r"><b>${flWO(w.name)}</b>${w.past_due ? badge('Past ship date', 'bad') : w.esd ? `<span class="small">Ship ${fmtd(w.esd)}</span>` : ''}</div>
        <div class="tt" style="margin-top:4px">${esc(w.item_name)}</div><div class="fl-prog"><i style="width:${pct}%"></i></div><div class="m">${flN(w.produced)} of ${flN(w.qty)} made</div>
        ${w.so ? `<div class="m">For ${link('sales-order', w.so, short(w.so))}${w.customer ? ' · ' + esc(w.customer) : ''}</div>` : '<div class="m">No sales order (built for stock)</div>'}
        ${w.so && !w.so_open && w.lane !== 'completed' ? `<div style="margin-top:6px">${badge('Its order is closed or delivered', 'warn')}</div>` : ''}
        ${w.short.length ? `<div class="m pb-late" style="margin-top:6px">Short: ${w.short.slice(0, 3).map(x => `${esc(x.item)} ${flN(x.qty)}`).join(', ')}${w.short.length > 3 ? ` + ${w.short.length - 3} more` : ''}</div><div class="m">${w.eta ? 'Parts ETA ' + fmtd(w.eta) : 'No open PO covers it'}</div>` : ''}
        ${pk.lines && w.lane !== 'waiting_parts' ? `<div class="m" style="margin-top:6px">To pick: ${flQty(pk)}</div>` : ''}</div>`; };
    const cols = lanes.map(([k, n, tone, hint]) => { const all = X.work_orders.filter(w => w.lane === k && rowOK(w)), cut = k === 'completed' && !FL.showDone && all.length > 6, cs = cut ? all.slice(0, 6) : all;
      return `<div class="bcol ${FL.hl === k ? 'fl-hl' : ''}" data-fllane="${k}"><div class="lane-h"><span><span class="dot ${tone}"></span> ${esc(n)}</span><span class="ct">${all.length}</span></div><div class="small fl-hint">${esc(hint)}</div>
        ${cs.map(card).join('') || '<div class="drop-hint">Nothing here</div>'}${cut ? `<button type="button" class="cc-btn soft" data-fldone>Show ${all.length - 6} more</button>` : ''}</div>`; });
    return flCard('fl-wos', 'Work orders', `${pbN(X.summary.wo_open, 'open work order')}, left to right in the order the floor works them. Completed ones show for 14 days, or until their order ships.`,
      `<div class="board fl-board" style="--n:${lanes.length}">${cols.join('')}</div>`, 'flush s12 fl-pad');
  };
  // Pieces to pull from stock for work orders, one block per work order.
  FL.pickProd = X => {
    const ws = X.work_orders.filter(w => (w.lane === 'to_pick' || w.lane === 'in_process') && w.pick.length && rowOK(w));
    const rows = ws.flatMap(w => [`<tr class="fl-grp"><td colspan="5">${flWO(w.name)} <span class="calc">${esc(w.item_name)}</span>${w.so ? ` · for ${link('sales-order', w.so, short(w.so))}` : ''}${w.esd ? ` · ship ${fmtd(w.esd)}` : ''}</td></tr>`,
      ...w.pick.map(p => `<tr><td>${link('item', p.item)}<div class="m">${esc(p.item_name !== p.item ? p.item_name : '')}</div></td><td class="num"><b>${flN(p.qty)}</b> ${flU(p.uom)}</td><td>${esc(p.warehouse || '—')}</td><td class="num">${flN(p.on_hand)}</td><td>${p.short ? badge('Short ' + flN(p.short), 'bad') : badge('On the shelf', 'good')}</td></tr>`)]);
    return flCard('fl-pick', 'Pick for production', `${flQty(X.summary.pick_production)} for ${pbN(ws.length, 'work order')}: required minus already transferred. On shelf excludes work-in-progress warehouses.`,
      flTable(['Item', '#To pick', 'From', '#On shelf', ''], rows, 'No work order is waiting on materials'), 'flush s7');
  };
  // The ship side, short: which orders, how much. The full list is on the Shipping page.
  FL.pickShip = X => { const s = X.summary.pick_shipping;
    const os = X.orders.filter(r => r.step === 'to_ship' && rowOK(r));
    const rows = os.map(r => `<tr class="fl-row" data-flopen="Sales Order|${esc(r.so)}"><td>${link('sales-order', r.so, short(r.so))}<div class="m">${esc(r.customer)}</div></td><td>${flEsd(r)}</td><td class="num">${r.pick.length ? flQty(r.pick_summary) : '<span class="calc">Picked</span>'}</td><td>${r.pick_short ? badge('Short', 'warn') : r.draft_dns.length ? badge('Delivery note drafted', 'info') : r.pick_lists.length ? badge('Picking', 'info') : badge('Ready', 'good')}</td></tr>`);
    return flCard('fl-ship', 'Pick & ship', `${flQty(s)} across ${pbN(os.length, 'order')}. ${X.summary.shipped_week} delivery note${X.summary.shipped_week === 1 ? '' : 's'} submitted in the last 7 days.`,
      flTable(['Sales order', 'Ship date', '#To pick', ''], rows, 'No order is ready to ship'), 'flush s5', '<a class="cc-btn soft" style="text-decoration:none" href="#ship">Full pick list →</a>');
  };
  FL.clean = X => {
    const wos = X.work_orders.filter(w => w.lane !== 'completed' && w.so && !w.so_open), dns = X.draft_dns.filter(d => !d.open_order), pls = X.pick_lists.filter(p => !p.open_order);
    if (!wos.length && !dns.length && !pls.length) return '';
    const rows = [...wos.map(w => `<tr><td>${flWO(w.name)}</td><td>Work order · ${esc(w.status)}</td><td>${link('sales-order', w.so, short(w.so))}</td><td>${fmtd(w.created)}</td></tr>`),
      ...dns.map(d => `<tr><td>${link('delivery-note', d.name, short(d.name).replace('ilL-MAT-DN-', 'DN '))}</td><td>Draft delivery note</td><td>${d.sales_orders.map(so => link('sales-order', so, short(so))).join('<br>') || '—'}</td><td>${fmtd(d.posting_date)}</td></tr>`),
      ...pls.map(p => `<tr><td>${link('pick-list', p.name)}</td><td>Pick list · ${esc(p.status)}</td><td>${p.sales_orders.map(so => link('sales-order', so, short(so))).join('<br>') || '—'}</td><td>${fmtd(p.created)}</td></tr>`)];
    return `<div class="card flush s12" id="fl-clean"><details class="more"><summary>Clean-up: ${pbN(rows.length, 'document')} tied to closed or delivered orders</summary><div style="padding:0 24px 8px" class="small">They don't block anything, but they make the lists above harder to trust. Cancel or delete them in ERPNext.</div>
      ${flTable(['Document', 'Kind', 'Sales order', 'Date'], rows)}</details></div>`;
  };
  FL.body = () => {
    const X = FL.data;
    if (!X) return FL.err ? `<div class="err">Couldn't load the warehouse flow: ${esc(FL.err)}</div>` : '<div class="cc-loading"><span class="cc-spin"></span>Loading the warehouse flow…</div>';
    return flStale() + FL.strip(X) + `<div class="grid">${FL.todo(X)}${FL.cover(X)}${FL.orders(X)}${FL.wos(X)}${FL.pickProd(X)}${FL.pickShip(X)}${FL.clean(X)}</div>`;
  };
  // Shipping page: the full pick list for orders ready to go, plus pick lists and draft delivery notes on open orders.
  FL.shipBody = () => {
    const X = FL.data;
    if (!X) return FL.err ? `<div class="err">Couldn't load the pick list: ${esc(FL.err)}</div>` : '<div class="empty">Loading the pick list…</div>';
    const s = X.summary.pick_shipping, os = X.orders.filter(r => r.step === 'to_ship' && rowOK(r));
    const rows = os.flatMap(r => [`<tr class="fl-grp"><td colspan="5">${link('sales-order', r.so, short(r.so))} <span class="calc">${esc(r.customer)}</span> · ship ${flEsd(r)}${r.pick_lists.map(p => ` · pick list ${link('pick-list', p)}`).join('')}${r.draft_dns.map(d => ` · draft ${link('delivery-note', d, 'delivery note')}`).join('')}</td></tr>`,
      ...(r.pick.length ? r.pick.map(p => `<tr><td>${link('item', p.item)}<div class="m">${esc(p.item_name !== p.item ? p.item_name : '')}${p.kit ? ` · part of ${esc(p.kit)}` : ''}</div></td><td class="num"><b>${flN(p.qty)}</b> ${flU(p.uom)}</td><td>${esc(p.warehouse || '—')}</td><td>${p.short ? badge('Short ' + flN(p.short), 'bad') : badge('On the shelf', 'good')}</td><td></td></tr>`)
        : ['<tr><td colspan="5" class="calc">Everything is picked; submit the delivery note.</td></tr>'])]);
    const open = X.pick_lists.filter(p => p.open_order), dns = X.draft_dns.filter(d => d.open_order);
    const kpis = `<div class="ex-kpis pb-kpis">${stat('Orders to pick & ship', os.length, 'Built, or nothing to build')}${stat('Lines to pick', s.lines, flQty(s))}${stat('Short in stock', s.short_orders, 'Orders with a line ERPNext shows short', s.short_orders ? 'warn' : '')}${stat('Draft delivery notes', X.summary.draft_dns, 'On open orders: submit once shipped')}${stat('Shipped, last 7 days', X.summary.shipped_week, 'Submitted delivery notes')}</div>`;
    return flStale() + kpis + `<div class="grid" style="margin-bottom:20px">
      <div class="card flush s12" id="fl-shiplist"><div class="card-h"><div><h2>Pick list: ready to ship</h2><div class="sub">Ordered minus delivered or already picked, kits expanded to their parts. Stock is handed to earlier ship dates first, after work orders take theirs. In ERPNext: sales order → Create → Pick List, then Delivery Note.</div></div></div>
        ${flTable(['Item', '#To pick', 'From', 'Stock', ''], rows, 'No order is ready to ship')}</div>
      ${open.length ? tableCard('Open pick lists', '', ['Pick list', 'Status', 'Sales order', '#Lines', 'Qty'], open.map(p => `<tr><td>${link('pick-list', p.name)}</td><td>${esc(p.status)}</td><td>${p.sales_orders.map(so => link('sales-order', so, short(so))).join('<br>')}</td><td class="num">${p.lines}</td><td>${flQty(p)}</td></tr>`), '', 's6') : ''}
      ${dns.length ? tableCard('Draft delivery notes', 'Submit once the order has shipped', ['Delivery note', 'Customer', 'Sales order', 'Date'], dns.map(d => `<tr><td>${link('delivery-note', d.name)}</td><td>${esc(d.customer)}</td><td>${d.sales_orders.map(so => link('sales-order', so, short(so))).join('<br>')}</td><td>${fmtd(d.posting_date)}</td></tr>`), '', 's6') : ''}
      ${X.shipped.length ? tableCard('Shipped in the last 7 days', '', ['Delivery note', 'Customer', 'Date'], X.shipped.filter(rowOK).map(d => `<tr><td>${link('delivery-note', d.name)}</td><td>${esc(d.customer)}</td><td>${fmtd(d.posting_date)}</td></tr>`), '', 's6') : ''}
    </div>`;
  };
  const flStale = () => FL.err ? `<div class="callout"><div>Couldn't refresh the warehouse flow (${esc(FL.err)}). Showing what loaded ${FL.at ? 'at ' + new Date(FL.at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : 'earlier'}.</div></div>` : '';
  function flRedraw() {
    // the stage stepper's Manufacturing count comes from this data once it is in
    const ch = $('.chev'); if (ch && PIPE.includes(S.view)) ch.outerHTML = stepper(CUR_M || M(), S.view);
    const r = $('#flroot'); if (r && S.view === 'mfg') r.innerHTML = FL.body();
    const sh = $('#flship'); if (sh && S.view === 'ship') sh.innerHTML = FL.shipBody();
    FL.bind();
  }
  async function flFetch(manual) {
    if (FL.busy) return; FL.busy = true; FL.err = null;
    try { FL.data = await call(FL_API, {}); FL.at = Date.now(); if (manual) toast('Warehouse flow refreshed'); }
    catch (e) { FL.err = e.message; }
    FL.busy = false; flRedraw();
  }
  FL.bind = () => {
    root.querySelectorAll('[data-flstep]').forEach(b => b.onclick = () => { FL.step = FL.step === b.dataset.flstep && b.closest('.fl-leg') ? '' : b.dataset.flstep; flRedraw(); });
    root.querySelectorAll('[data-fldone]').forEach(b => b.onclick = () => { FL.showDone = true; flRedraw(); });
    // whole work order cards and order rows open their record's sheet (links and buttons inside keep their own click)
    root.querySelectorAll('[data-flopen]').forEach(el => el.onclick = e => { if (e.target.closest('a, button')) return; const [dt, n] = el.dataset.flopen.split('|'); plDetail(dt, n); });
    root.querySelectorAll('[data-flgo]').forEach(b => b.onclick = () => {
      const [k, v] = b.dataset.flgo.split(':'); let target = v;
      if (k === 'go') { location.hash = v; return; }
      if (k === 'step') { FL.step = v; FL.hl = ''; target = 'fl-orders'; flRedraw(); }
      else if (k === 'lane') { FL.hl = v; target = 'fl-wos'; flRedraw(); }
      if (target === 'fl-clean') { const d = $('#fl-clean details'); if (d) d.open = true; }
      const el = $('#' + target); if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };
  // Manufacturing and Shipping: a click on a document link opens its side sheet (details, child tables, the fields
  // that can change, + To-do, + Add to agenda, Open in ERPNext) instead of a new tab. Ctrl/⌘/Shift-click still opens
  // ERPNext, and doctypes the Workbench doesn't cover (or before its config has loaded) open ERPNext as before.
  const FL_SHEET_VIEWS = ['mfg', 'ship'];
  const flDt = slugged => slugged.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  root.addEventListener('click', e => {
    if (!FL_SHEET_VIEWS.includes(S.view) || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest('a[href^="/app/"]'); if (!a || a.closest('#ccsheet2, .qlinks, .pu-menu')) return;
    const mm = a.getAttribute('href').match(/^\/app\/([a-z0-9-]+)\/([^/?#]+)$/); if (!mm || mm[2] === 'new') return;
    const dt = flDt(mm[1]); if (!WB.cfg || !WB.cfg.doctypes[dt]) return;
    e.preventDefault(); wbOpen(dt, decodeURIComponent(mm[2]));
  });
  const flCfg = () => { if (!WB.cfg && !FL.cfgBusy) { FL.cfgBusy = true; gw('config').then(c => { WB.cfg = c; }).catch(() => { }).finally(() => { FL.cfgBusy = false; }); } };
  FL.mount = () => { flCfg(); FL.bind(); if (!FL.busy && (!FL.data || Date.now() - FL.at > 120000)) flFetch(); };
  /* ---------------- labels & reel count (v10) ----------------
     Labels: the warehouse PC's print station. Two printers and no roll swaps: the Dymo keeps 1.5 x 2.5 loaded, the Rollo
     4 x 6. One card per roll, in print order. Print makes a batch (its labels go to Sent), prints the batch PDF through a
     hidden iframe, and only the person's "All printed" / "Some need reprinting" click marks labels Printed.
     Reel count: the inventory count screen for a scanner that types like a keyboard; every scan goes through reels.lookup.
     Data: the app endpoints labels.* and reels.*. Both tabs stay hidden unless their flag is on in ilL-Production-Settings
     and the user may use them. The Sales Order form opens #mfg?labels_so=<name> (Labels tab, filtered to that order). */
  const LB_API = 'illumenate_lighting.illumenate_lighting.api.labels.';
  const RL_API = 'illumenate_lighting.illumenate_lighting.api.reels.';
  const LB = { data: null, err: null, busy: false, at: 0, total: null, so: '', wo: '', printed: false, sel: new Set(), open: {}, mine: [], printing: false };
  const LB_ST = { Queued: 'info', Sent: 'warn', Printed: 'good', Void: 'mute', Cancelled: 'mute' };
  const lbStore = (k, v) => { try { if (v === undefined) return localStorage.getItem(k) || ''; localStorage.setItem(k, v); } catch (e) { } return ''; };
  const lbOn = () => !!(LB.data && (LB.data.labels_enabled || LB.data.reels_enabled) && LB.data.can_print);
  const rlOn = () => RL.setup ? !!(RL.setup.enabled && RL.setup.can_count) : !!(LB.data && LB.data.reels_enabled);
  const pbTabOn = k => k === 'labels' ? lbOn() : k === 'reels' ? rlOn() : true;
  const lbHash = () => { const m = /^#mfg\?labels_so=([^&]*)/.exec(location.hash || ''); if (!m) return; let so = m[1]; try { so = decodeURIComponent(so.replace(/\+/g, ' ')); } catch (e) { }
    LB.so = so.trim(); LB.wo = ''; LB.sel.clear(); LB.at = 0; PB.tab = 'labels'; S.view = 'mfg'; history.replaceState(null, '', '#mfg'); };
  lbHash(); window.addEventListener('hashchange', lbHash);   // runs before the page's own hashchange handler, which then reads #mfg
  async function lbFetch(manual) {
    if (LB.busy) return; LB.busy = true; LB.err = null;
    const args = { include_printed: LB.printed ? 1 : 0 }; if (LB.so) args.sales_order = LB.so; if (LB.wo) args.work_orders = LB.wo;
    try { LB.data = await call(LB_API + 'get_queue', args); LB.at = Date.now(); if (!LB.so && !LB.wo) LB.total = lbCount(LB.data); if (manual) toast('Label queue refreshed'); }
    catch (e) { LB.err = e.message; }
    LB.busy = false; lbRedraw();
  }
  const lbPeek = () => { if (!LB.busy && (!LB.data || Date.now() - LB.at > 120000)) lbFetch(); };
  const lbRefresh = () => { LB.at = 0; lbFetch(); };
  function lbRedraw() {
    const pr = $('#pbroot'); if (!pr || S.view !== 'mfg') return;
    // a remembered Labels / Reel count tab whose flag is off falls back to Flow
    if (['labels', 'reels'].includes(PB.tab) && LB.data && !pbTabOn(PB.tab) && !(PB.tab === 'reels' && RL.setup)) { PB.tab = 'flow'; pr.innerHTML = PB.body(); PB.bind(); return; }
    pbTabsRedraw();
    const r = $('#lbroot'); if (r) { r.innerHTML = LB.body(); LB.bind(); }
  }
  const lbCount = X => ((X && X.groups) || []).reduce((n, g) => n + (g.count || 0), 0);
  // age_minutes comes from the server, so a PC in another time zone still counts 2 hours right
  const lbOld = b => b.age_minutes != null ? b.age_minutes > 120 : (() => { const t = new Date(String(b.sent_at || '').replace(' ', 'T')); return !isNaN(t) && Date.now() - t > 2 * 3600000; })();
  const lbMeta = j => [j.label_template, j.unit_count > 1 ? `Unit ${j.unit_no} of ${j.unit_count}` : '', j.piece_count > 1 ? `Piece ${j.piece_no} of ${j.piece_count}` : '', j.print_count ? `Printed ${j.print_count}×` : '', j.void_reason].filter(Boolean).map(esc).join(' · ');
  const lbPrev = j => j.work_order && j.label_template ? `<a target="_blank" rel="noopener" href="/api/method/${LB_API}preview?template=${encodeURIComponent(j.label_template)}&amp;name=${encodeURIComponent(j.work_order)}">Preview</a>` : '';
  const lbPick = g => g.jobs.filter(j => j.status === 'Queued' && LB.sel.has(j.name)).map(j => j.name);
  const lbBtn = g => { const n = lbPick(g).length; return n ? `Print ${n} selected` : `Print ${g.count || ''}`.trim(); };
  const lbBtns = () => ((LB.data && LB.data.groups) || []).forEach((g, i) => { const b = $(`[data-lbprint="${i}"]`); if (b) b.textContent = lbBtn(g); });
  const lbRow = j => `<tr><td class="no-print lb-ck">${j.status === 'Queued' ? `<input type="checkbox" data-lbsel="${esc(j.name)}" ${LB.sel.has(j.name) ? 'checked' : ''} aria-label="Select this label">` : ''}</td>
    <td>${esc(j.summary || j.name)}<div class="m">${lbMeta(j)}</div></td>
    <td>${badge(j.status, LB_ST[j.status] || 'mute')}${j.is_stale ? ' <span class="badge warn" title="Its work order changed after this label was made">Stale</span>' : ''}</td>
    <td class="no-print lb-act">${['Printed', 'Sent'].includes(j.status) ? `<button type="button" class="cc-btn soft" data-lbre="${esc(j.name)}">Reprint</button> ` : ''}${lbPrev(j)}</td></tr>`;
  // rows by work order (reel and shelf labels have none: "Reels & shelves"), each a collapsible section
  function lbSecs(g, gi) {
    const by = new Map(); g.jobs.forEach(j => { const k = j.work_order || ''; if (!by.has(k)) by.set(k, []); by.get(k).push(j); });
    const many = by.size > 6;
    return [...by].map(([k, jobs]) => { const id = g.stock + '|' + k, open = LB.open[id] != null ? LB.open[id] : !many, j0 = jobs[0], q = jobs.filter(j => j.status === 'Queued').length;
      const title = k ? `${flWO(k)}${j0.sales_order ? ' · ' + link('sales-order', j0.sales_order, short(j0.sales_order)) : ''}${j0.fixture_type ? ` · <span class="small">${esc(j0.fixture_type)}</span>` : ''}` : 'Reels &amp; shelves';
      return `<details class="lb-sec" data-lbsec="${esc(id)}" ${open ? 'open' : ''}><summary><span>${title}</span><span class="small">${pbN(jobs.length, 'label')}${q !== jobs.length ? ` · ${q} queued` : ''}${k && j0.ship_by ? ' · ship by ' + fmtd(j0.ship_by) : ''}</span></summary>
        <div class="tw"><table class="lb-tbl"><thead><tr><th class="no-print lb-ck">${q ? `<input type="checkbox" data-lbselall="${gi}|${esc(k)}" aria-label="Select every queued label here">` : ''}</th><th>Label</th><th>Status</th><th class="no-print"></th></tr></thead><tbody>${jobs.map(lbRow).join('')}</tbody></table></div></details>`; }).join('');
  }
  const lbGroup = (g, gi) => `<div class="card flush s12 lb-grp"><div class="card-h"><div><h2>${esc(g.printer_name || 'No printer set')} · ${esc(g.stock)}</h2>
      <div class="sub">${g.count ? `<b>${g.count} queued</b>` : 'Nothing queued'} · ${pbN(g.work_orders || 0, 'work order')}${g.earliest_ship_by ? ' · earliest ship-by ' + fmtd(g.earliest_ship_by) : ''}${g.label_part_no ? ' · roll ' + esc(g.label_part_no) : ''}</div></div>
      <div class="toolbar no-print"><a class="small" target="_blank" rel="noopener" href="/api/method/${LB_API}test_print?label_stock=${encodeURIComponent(g.stock)}">Test print</a><button type="button" class="cc-btn primary" data-lbprint="${gi}" ${g.count && !LB.printing ? '' : 'disabled'}>${esc(lbBtn(g))}</button></div></div>
    ${lbSecs(g, gi)}</div>`;
  // batches nobody confirmed: older than 2 hours, or closed without an answer in this browser
  const lbUnc = X => (X.unconfirmed || []).filter(b => lbOld(b) || LB.mine.includes(b.name)).map(b => `<div class="callout"><div><b>Batch ${esc(b.name)} was never confirmed.</b> ${pbN(b.label_count || 0, 'label')} on ${esc(b.printer_name || b.label_stock)}, sent ${esc(String(b.sent_at || '').slice(0, 16))}${b.sent_by ? ' by ' + esc(b.sent_by) : ''}. Did they print?
      <div class="toolbar no-print" style="margin-top:8px"><button type="button" class="cc-btn soft" data-lbok="${esc(b.name)}">All printed</button><button type="button" class="cc-btn soft" data-lbsome="${esc(b.name)}">Some need reprinting</button></div></div></div>`).join('');
  LB.body = () => {
    const X = LB.data;
    if (!X) return LB.err ? `<div class="err">Couldn't load the label queue: ${esc(LB.err)}</div>` : '<div class="empty">Loading the label queue…</div>';
    if (!lbOn()) return `<div class="card"><div class="empty">${X.labels_enabled || X.reels_enabled ? 'Printing labels needs a label printing role.' : 'Labels are off. Turn on Labels in ilL-Production-Settings.'}</div></div>`;
    const n = lbCount(X), groups = X.groups || [];
    const bar = `<div class="toolbar no-print lb-bar"><button type="button" class="cc-btn primary" id="lbAll" ${n && !LB.printing ? '' : 'disabled'}>Print all${n ? ' ' + n : ''}</button>
      <input type="text" id="lbSo" placeholder="Sales order" value="${esc(LB.so)}" aria-label="Filter by sales order"><input type="text" id="lbWo" placeholder="Work order(s)" value="${esc(LB.wo)}" aria-label="Filter by work order">
      <label class="small"><input type="checkbox" id="lbPrinted" ${LB.printed ? 'checked' : ''}> Show printed</label><button type="button" class="cc-btn soft" id="lbRefresh">Refresh</button></div>`;
    const stale = LB.err ? `<div class="callout"><div>Couldn't refresh the label queue (${esc(LB.err)}). Showing what loaded at ${new Date(LB.at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}.</div></div>` : '';
    return bar + stale + lbUnc(X) + (groups.some(g => g.jobs.length) ? `<div class="grid">${groups.map((g, i) => g.jobs.length ? lbGroup(g, i) : '').join('')}</div>`
      : `<div class="card"><div class="empty">${LB.so || LB.wo ? 'No labels match these filters.' : 'Nothing queued. Labels are queued when work orders are created.'}</div></div>`);
  };
  LB.bind = () => {
    const X = LB.data; if (!X || !$('#lbroot')) return;
    const go = () => { LB.sel.clear(); lbFetch(); };
    const so = $('#lbSo'), wo = $('#lbWo'), pr = $('#lbPrinted'), rf = $('#lbRefresh'), all = $('#lbAll');
    if (so) so.onchange = () => { LB.so = so.value.trim(); go(); };
    if (wo) wo.onchange = () => { LB.wo = wo.value.split(/[\s,]+/).filter(Boolean).join(', '); go(); };
    if (pr) pr.onchange = () => { LB.printed = pr.checked; go(); };
    if (rf) rf.onclick = () => lbFetch(true);
    if (all) all.onclick = () => lbPrintAll();
    root.querySelectorAll('[data-lbprint]').forEach(b => b.onclick = () => lbPrintOne(X.groups[+b.dataset.lbprint]));
    root.querySelectorAll('[data-lbsel]').forEach(c => c.onchange = () => { c.checked ? LB.sel.add(c.dataset.lbsel) : LB.sel.delete(c.dataset.lbsel); lbBtns(); });
    root.querySelectorAll('[data-lbselall]').forEach(c => c.onchange = () => { const [gi, k] = c.dataset.lbselall.split('|');
      X.groups[+gi].jobs.filter(j => (j.work_order || '') === k && j.status === 'Queued').forEach(j => c.checked ? LB.sel.add(j.name) : LB.sel.delete(j.name));
      c.closest('table').querySelectorAll('[data-lbsel]').forEach(x => { x.checked = c.checked; }); lbBtns(); });
    root.querySelectorAll('[data-lbsec]').forEach(d => d.ontoggle = () => { LB.open[d.dataset.lbsec] = d.open; });
    root.querySelectorAll('[data-lbre]').forEach(b => b.onclick = async () => { b.disabled = true;
      try { const r = await call(LB_API + 'reprint', { job_names: JSON.stringify([b.dataset.lbre]) }); toast(r.requeued ? 'Back in the queue for reprinting' : 'That label can no longer be reprinted'); } catch (e) { toast('Not requeued: ' + esc(e.message)); }
      lbFetch(); });
    root.querySelectorAll('[data-lbok]').forEach(b => b.onclick = async () => { b.disabled = true; try { await lbConfirm(b.dataset.lbok, []); } catch (e) { toast('Not saved: ' + esc(e.message)); } lbFetch(); });
    root.querySelectorAll('[data-lbsome]').forEach(b => b.onclick = () => lbSomeLater(b.dataset.lbsome));
  };
  async function lbConfirm(batch, again) {
    const r = await call(LB_API + 'confirm_batch', again.length ? { batch, reprint_jobs: JSON.stringify(again) } : { batch });
    LB.mine = LB.mine.filter(x => x !== batch);
    toast(`${pbN(r.printed, 'label')} marked printed${r.requeued ? ` · ${r.requeued} back in the queue` : ''}`);
    return r;
  }
  const lbPickList = jobs => `<div class="lb-relist">${jobs.map(j => `<label><input type="checkbox" name="lbre" value="${esc(j.name)}"><span>${esc(j.summary || j.name)}<span class="m">${lbMeta(j)}</span></span></label>`).join('')}</div>`;
  const lbPicked = el => [...el.querySelectorAll('input[name=lbre]:checked')].map(i => i.value);
  // a batch confirmed later (from the banner): its jobs still in Sent come from the queue with printed ones included
  async function lbSomeLater(batch) {
    let jobs;
    try { const X = await call(LB_API + 'get_queue', { include_printed: 1 }); jobs = (X.groups || []).flatMap(g => g.jobs).filter(j => j.batch === batch && j.status === 'Sent'); }
    catch (e) { toast('Couldn\'t load the batch: ' + esc(e.message)); return; }
    const el = sheet(`Batch ${esc(batch)}`, 'Tick the labels that did not print correctly. They go back in the queue; the rest are marked printed.',
      (jobs.length ? lbPickList(jobs) : '<p class="small">None of this batch\'s labels are still waiting. Confirm to close it.</p>') + '<div class="toolbar"><button type="button" class="cc-btn primary" id="lbSomeGo">Confirm</button></div>', null);
    const b = el.querySelector('#lbSomeGo'), msg = el.querySelector('#sMsg');
    b.onclick = async () => { const again = lbPicked(el); if (jobs.length && !again.length) { msg.textContent = 'Tick at least one label, or use All printed.'; return; }
      b.disabled = true; try { await lbConfirm(batch, again); closeSheet(); lbFetch(); } catch (e) { msg.textContent = 'Not saved: ' + e.message; b.disabled = false; } };
  }
  const lbPrintOne = g => { if (!LB.printing && g) { const names = lbPick(g); lbRun([[g, names.length ? names : null]]); } };
  const lbPrintAll = () => { if (!LB.printing && LB.data) lbRun(LB.data.groups.filter(g => g.count).map(g => [g, null])); };
  // one roll after another; the next starts only once the person has answered for the last one
  async function lbRun(list) {
    LB.printing = true; root.querySelectorAll('[data-lbprint], #lbAll').forEach(b => { b.disabled = true; });
    for (let i = 0; i < list.length; i++) {
      const [g, names] = list[i], jobs = g.jobs.filter(j => j.status === 'Queued' && (!names || names.includes(j.name)));
      if (!jobs.length) continue;
      let res; try { res = await call(LB_API + 'create_batch', { label_stock: g.stock, job_names: JSON.stringify(jobs.map(j => j.name)) }); }
      catch (e) { toast(`Couldn't start the ${esc(g.stock)} batch: ${esc(e.message)}`); break; }
      jobs.forEach(j => LB.sel.delete(j.name));
      const out = await lbPanel(res, jobs, list.length > 1 ? `Roll ${i + 1} of ${list.length}` : '');
      if (out !== 'done') { toast(`Batch ${esc(res.batch)} is waiting for confirmation at the top of the Labels tab.${i < list.length - 1 ? ' Print all stopped.' : ''}`); break; }
    }
    LB.printing = false; lbFetch();
  }
  // the print panel: settings in large type, the PDF printed from a hidden iframe, then "Did every label print correctly?"
  function lbPanel(res, jobs, step) {
    const last = lbStore('cc.labels.lastPrinter'), sw = !!res.printer_name && last !== res.printer_name, pdf = esc(res.pdf_url);
    if (res.printer_name) lbStore('cc.labels.lastPrinter', res.printer_name);
    const el = sheet(`Print ${pbN(res.count, 'label')}`, `Batch ${esc(res.batch)}${step ? ' · ' + esc(step) : ''}`, `<div class="lb-panel">
      ${sw ? `<p class="lb-switch">Switch the printer to ${esc(res.printer_name)} in the print dialog</p>` : ''}
      <p class="lb-big">Printer: <b>${esc(res.printer_name || 'the label printer')}</b>. Paper: <b>${esc(res.driver_paper_name || 'the roll size')}</b>. Margins: <b>none</b>. Scale: <b>100%</b>.</p>
      <p id="lbState">Opening the print dialog…</p>
      <p class="small">Nothing came up? <a href="${pdf}" target="_blank" rel="noopener">Open the PDF</a> and press Ctrl+P.</p>
      <div id="lbAsk" hidden><p class="lb-big"><b>Did every label print correctly?</b></p><div class="toolbar"><button type="button" class="cc-btn primary" id="lbOk">All printed</button><button type="button" class="cc-btn soft" id="lbSome">Some need reprinting</button><button type="button" class="cc-btn soft" id="lbAgain">Print again</button></div></div>
      <div id="lbRe" hidden><p>Tick the labels that need reprinting. They go back in the queue; the rest are marked printed.</p>${lbPickList(jobs)}<div class="toolbar"><button type="button" class="cc-btn primary" id="lbReGo">Confirm</button></div></div></div>`, null);
    el.querySelector('.cc-sheet').classList.add('lb-wide');
    const q = s => el.querySelector(s), msg = q('#sMsg'), st = h => { q('#lbState').innerHTML = h; }, ask = () => { if (q('#lbRe').hidden) q('#lbAsk').hidden = false; };
    const fr = document.createElement('iframe'); fr.className = 'lb-frame'; fr.title = 'Label PDF'; fr.setAttribute('aria-hidden', 'true');
    const printIt = () => {
      try { fr.contentWindow.focus(); fr.contentWindow.print(); st('The print dialog opened. Check the settings above, then print.'); }
      catch (e) { const w = window.open(res.pdf_url, '_blank'); st(w ? 'The PDF opened in a new tab. <b>Press Ctrl+P</b> there.' : `The browser blocked the print dialog. <a href="${pdf}" target="_blank" rel="noopener">Open the PDF</a> and <b>press Ctrl+P</b>.`); }
      ask(); };
    let loaded = false, done = false;
    return new Promise(resolve => {
      const obs = new MutationObserver(() => { if (!el.classList.contains('on') && !done) { LB.mine.push(res.batch); end('closed'); } });
      const end = v => { done = true; obs.disconnect(); fr.remove(); resolve(v); };
      obs.observe(el, { attributes: true, attributeFilter: ['class'] });
      fr.onload = () => { loaded = true; if (!done) printIt(); };
      setTimeout(() => { if (!loaded && !done) { st(`The PDF is slow to load. <a href="${pdf}" target="_blank" rel="noopener">Open the PDF</a> and <b>press Ctrl+P</b>.`); ask(); } }, 10000);
      fr.src = res.pdf_url; document.body.appendChild(fr);
      const confirm = async (again, b) => { b.disabled = true; msg.textContent = '';
        try { await lbConfirm(res.batch, again); end('done'); closeSheet(); } catch (e) { msg.textContent = 'Not saved: ' + e.message; b.disabled = false; } };
      q('#lbOk').onclick = e => confirm([], e.currentTarget);
      q('#lbSome').onclick = () => { q('#lbAsk').hidden = true; q('#lbRe').hidden = false; };
      q('#lbAgain').onclick = () => printIt();
      q('#lbReGo').onclick = e => { const again = lbPicked(el); if (!again.length) { msg.textContent = 'Tick at least one label, or use All printed.'; return; } confirm(again, e.currentTarget); };
    });
  }

  /* Reel count: scan box → lookup → routed by kind, whatever step the screen is on.
     Steps for one reel: tag → item (defaults to the last one used) → length (Full / feet + inches / weigh) → scrap? → shelf. */
  const RL = { setup: null, err: null, busy: false, at: 0, cur: null, msg: null, done: [], ft: '', inch: '', grams: '', lot: '', q: '', saving: false, chain: Promise.resolve() };
  try { RL.done = JSON.parse(sessionStorage.getItem('cc.reels.done') || '[]').slice(0, 20); } catch (e) { }
  const rlKeep = () => { try { sessionStorage.setItem('cc.reels.done', JSON.stringify(RL.done)); } catch (e) { } };
  const rlItem = code => ((RL.setup && RL.setup.items) || []).find(i => i.item_code === code);
  const rlFt = mm => { mm = +mm || 0; let f = Math.floor(mm / 304.8), i = Math.round((mm - f * 304.8) / 25.4); if (i === 12) { f++; i = 0; } return i ? `${f}' ${i}"` : `${f}'`; };
  const rlLast = v => lbStore('cc.reels.lastItem.' + USER, v);
  const rlStep = c => !c ? 'tag' : c.confirm ? 'confirm' : (!c.item_code || c.pickItem) ? 'item' : !c.method ? 'length' : c.scrapAsk ? 'scrap' : 'shelf';
  const RL_STEPS = [['tag', 'Scan tag'], ['item', 'Item'], ['length', 'Length'], ['shelf', 'Shelf']];
  const rlLen = c => c.method === 'Full' ? `Full (${(rlItem(c.item_code) || {}).standard || rlFt(c.length_mm)})` : c.method === 'Weighed' ? `${c.weight_g} g, weighed` : c.method ? rlFt(c.length_mm) : '';
  const rlReady = c => !!(c && !c.confirm && c.item_code && !c.pickItem && c.method && !c.scrapAsk);
  const rlCheck = c => { const it = rlItem(c.item_code);
    if (c.method === 'Full') { if (it && it.standard_mm > 0) c.length_mm = it.standard_mm; else c.method = ''; }
    if (c.method === 'Weighed' && !(it && it.can_weigh)) c.method = '';
    c.scrapAsk = !c.scrapOk && c.method === 'Measured' && !!it && it.scrap_mm > 0 && c.length_mm < it.scrap_mm; };
  async function rlFetch(manual) {
    if (RL.busy) return; RL.busy = true; RL.err = null;
    try { RL.setup = await call(RL_API + 'get_count_setup', {}); RL.at = Date.now(); if (manual) toast('Reel count refreshed'); } catch (e) { RL.err = e.message; }
    RL.busy = false; pbTabsRedraw(); rlRedraw();
  }
  function rlRedraw() { const r = $('#rlroot'); if (!r || S.view !== 'mfg') return; r.innerHTML = RL.body(); RL.bind(); }
  RL.mount = () => { RL.bind(); if (!RL.busy && (!RL.setup || Date.now() - RL.at > 600000)) rlFetch(); };
  const rlItems = () => { const q = RL.q.toLowerCase(), last = rlLast(), list = ((RL.setup && RL.setup.items) || []).filter(i => !q || (i.item_code + ' ' + (i.item_name || '')).toLowerCase().includes(q)).sort((a, b) => (b.item_code === last) - (a.item_code === last));
    return list.slice(0, 40).map(i => `<button type="button" class="rl-item ${RL.cur && RL.cur.item_code === i.item_code ? 'on' : ''}" data-rlitem="${esc(i.item_code)}"><b>${esc(i.item_name || i.item_code)}</b><span class="mono">${esc(i.item_code)}${i.standard ? ' · ' + esc(i.standard) : ''}</span></button>`).join('')
      + (list.length > 40 ? `<p class="small">${list.length - 40} more: type to narrow the list</p>` : '') || '<p class="small">No reel-tracked item matches. Tick Reel Tracked on the Item.</p>'; };
  RL.body = () => {
    const X = RL.setup;
    if (!X) return RL.err ? `<div class="err">Couldn't load the reel count: ${esc(RL.err)}</div>` : '<div class="empty">Loading the reel count…</div>';
    if (!X.enabled) return '<div class="card"><div class="empty">Reels are off. Turn on Reels in ilL-Production-Settings.</div></div>';
    if (!X.can_count) return '<div class="card"><div class="empty">Counting reels needs the Stock User, Stock Manager, Manufacturing User or Manufacturing Manager role.</div></div>';
    const c = RL.cur, step = rlStep(c), it = c && rlItem(c.item_code), m = RL.msg;
    const si = RL_STEPS.findIndex(s => s[0] === (step === 'confirm' ? 'tag' : step === 'scrap' ? 'length' : step));
    const steps = `<div class="rl-steps">${RL_STEPS.map(([k, n], i) => `<span class="${i < si ? 'done' : i === si ? 'on' : ''}">${i + 1}. ${n}</span>`).join('')}</div>`;
    const head = c ? `<div class="rl-cur"><b class="mono">${esc(c.reel)}</b>${c.prior && c.prior.status ? ' ' + badge(c.prior.status, 'mute') : ''}${c.item_code ? ' · ' + esc(it ? it.item_name || it.item_code : c.item_code) : ''}${c.method ? ' · ' + esc(rlLen(c)) : ''}${c.location ? ' · shelf ' + esc(c.location) : ''}</div>` : '';
    let body;
    if (step === 'tag') body = '<p class="rl-big">Scan a reel tag</p><p class="small">Then the item, the length and the shelf. Any scan works at any step.</p>';
    else if (step === 'confirm') body = `<p class="rl-big">Counted on ${fmtd(c.prior.counted_on)}: ${esc(c.prior.length || rlFt(c.prior.length_mm))}${c.prior.location ? ' on ' + esc(c.prior.location) : ''}. Recount?</p>
      <div class="toolbar"><button type="button" class="cc-btn primary rl-tap" data-rl="recount">Recount</button><button type="button" class="cc-btn soft rl-tap" data-rl="cancel">Cancel</button></div><p class="small">Or scan a shelf to move it there without recounting.</p>`;
    else if (step === 'item') body = `<p class="rl-big">Scan the item barcode or pick the item</p><input type="text" class="rl-q" id="rlq" placeholder="Search items" value="${esc(RL.q)}" autocomplete="off" aria-label="Search items">
      <div id="rlitems" class="rl-items">${rlItems()}</div>${c.pickItem && c.item_code ? `<div class="toolbar"><button type="button" class="cc-btn soft" data-rl="keepitem">Keep ${esc(c.item_code)}</button></div>` : ''}`;
    else if (step === 'length') body = `<p class="rl-big">How much is on it?</p><div class="rl-len">
      ${it && it.standard_mm > 0 ? `<button type="button" class="cc-btn primary rl-tap" data-rl="full">Full (${esc(it.standard)})</button>` : ''}
      <div class="rl-ftin"><label><input type="text" inputmode="decimal" id="rlft" value="${esc(RL.ft)}" autocomplete="off" aria-label="Feet"><span>ft</span></label><label><input type="text" inputmode="decimal" id="rlin" value="${esc(RL.inch)}" autocomplete="off" aria-label="Inches"><span>in</span></label><button type="button" class="cc-btn soft rl-tap" data-rl="measured">Use length</button></div>
      ${it && it.can_weigh ? `<div class="rl-ftin"><label><input type="text" inputmode="decimal" id="rlg" value="${esc(RL.grams)}" autocomplete="off" aria-label="Grams"><span>g</span></label><button type="button" class="cc-btn soft rl-tap" data-rl="weigh">Weigh</button></div>` : ''}</div>
      <div class="toolbar" style="margin-top:12px"><button type="button" class="cc-btn soft" data-rl="item">Change item</button></div>`;
    else if (step === 'scrap') body = `<p class="rl-big rl-warn">Under ${esc(rlFt(it.scrap_mm))}: scrap it?</p><div class="toolbar"><button type="button" class="cc-btn primary rl-tap" data-rl="scrap">Yes, scrap it</button><button type="button" class="cc-btn soft rl-tap" data-rl="keep">No, keep it</button></div>`;
    else body = `<p class="rl-big">Scan the shelf</p><div class="toolbar"><button type="button" class="cc-btn soft rl-tap" data-rl="noshelf">No shelf${X.warehouse ? ' (' + esc(X.warehouse) + ')' : ''}</button>
      ${(X.locations || []).length ? `<select id="rlloc" aria-label="Pick a shelf"><option value="">Or pick a shelf…</option>${X.locations.map(l => `<option value="${esc(l.name)}">${esc(l.name)}${l.description ? ' · ' + esc(l.description) : ''}</option>`).join('')}</select>` : ''}
      <button type="button" class="cc-btn soft" data-rl="length">Change length</button></div>`;
    const extra = c && step !== 'confirm' ? `<div class="rl-extra"><label class="small">Supplier lot <input type="text" id="rllot" value="${esc(RL.lot)}" autocomplete="off" placeholder="optional"></label><button type="button" class="cc-btn soft" data-rl="cancel">Cancel this reel</button></div>` : '';
    const msg = m ? `<div class="rl-msg ${m[0]}">${m[1]}${m[2] != null ? ` <button type="button" class="cc-btn soft" data-rlscrapit="${m[2]}">Scrap it</button>` : ''}</div>` : '';
    const side = `<div class="card s4 no-print"><div class="card-h"><div><h2>Tools</h2><div class="sub">${pbN(X.tags_left || 0, 'blank tag')} printed and not yet counted</div></div></div><div class="rl-tools">
      <button type="button" class="cc-btn soft" data-rlt="tags">Print reel tags</button><button type="button" class="cc-btn soft" data-rlt="shelves">Add shelves</button><button type="button" class="cc-btn soft" data-rlt="summary">Count summary</button>
      <button type="button" class="cc-btn soft" data-rlt="labels" ${RL.done.some(d => !d.scrap) ? '' : 'disabled'}>Print reel labels for this session's reels</button></div></div>`;
    const list = tableCard('Counted this session', RL.done.length ? `The last ${RL.done.length} in this browser tab` : '', ['Reel', 'Item', 'Length', 'Shelf', 'Time'],
      RL.done.map(d => `<tr><td class="mono">${esc(d.reel)}</td><td>${esc(d.item_name || d.item_code)}</td><td>${d.scrap ? badge('Scrapped', 'bad') : esc(d.length)}</td><td>${esc(d.location || (d.warehouse ? d.warehouse + ' (no shelf)' : ''))}</td><td>${esc(d.at)}</td></tr>`));
    return `<div class="grid"><div class="card s8 rl-main"><div class="rl-scanrow no-print"><input type="text" id="rlscan" class="rl-scan" placeholder="Scan here" autocomplete="off" spellcheck="false" aria-label="Scan box"><button type="button" class="cc-btn primary" id="rlgo">Enter</button></div>
      ${msg}${steps}${head}${body}${extra}</div>${side}${list}</div>`;
  };
  const rlScan = v => { RL.chain = RL.chain.then(() => rlRoute(v)).catch(() => { }); };   // scans in order, one lookup at a time
  RL.bind = () => {
    const sc = $('#rlscan'); if (!sc) return;
    sc.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); const v = sc.value; sc.value = ''; rlScan(v); } };
    $('#rlgo').onclick = () => { const v = sc.value; sc.value = ''; rlScan(v); };
    // numeric fields: Enter uses the value; a scan that lands in one (it has letters) is routed like any other scan
    const num = (id, key, act) => { const el = $(id); if (!el) return; el.oninput = () => { RL[key] = el.value; };
      el.onkeydown = e => { if (e.key !== 'Enter') return; e.preventDefault(); if (/[a-z]/i.test(el.value)) { const v = el.value; el.value = RL[key] = ''; rlScan(v); } else rlAct(act); }; };
    num('#rlft', 'ft', 'measured'); num('#rlin', 'inch', 'measured'); num('#rlg', 'grams', 'weigh');
    const lot = $('#rllot'); if (lot) { lot.oninput = () => { RL.lot = lot.value; }; lot.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); sc.focus(); } }; }
    const q = $('#rlq'); if (q) q.oninput = () => { RL.q = q.value; $('#rlitems').innerHTML = rlItems(); rlItemBind(); };
    rlItemBind();
    const loc = $('#rlloc'); if (loc) loc.onchange = () => { const l = (RL.setup.locations || []).find(x => x.name === loc.value); if (l && RL.cur) { RL.cur.location = l.name; RL.cur.warehouse = l.warehouse || ''; rlSave(false); } };
    root.querySelectorAll('[data-rl]').forEach(b => b.onclick = () => rlAct(b.dataset.rl));
    root.querySelectorAll('[data-rlt]').forEach(b => b.onclick = () => rlTool(b.dataset.rlt));
    root.querySelectorAll('[data-rlscrapit]').forEach(b => b.onclick = () => rlScrapIt(+b.dataset.rlscrapit));
    const a = document.activeElement; if (!$('#ccsheet2').classList.contains('on') && (!a || a === document.body || !root.contains(a))) sc.focus({ preventScroll: true });
  };
  const rlItemBind = () => root.querySelectorAll('[data-rlitem]').forEach(b => b.onclick = () => rlSetItem(b.dataset.rlitem));
  // the scan box keeps focus: a character typed with nothing focused (or a button) goes to it
  document.addEventListener('keydown', e => {
    if (S.view !== 'mfg' || PB.tab !== 'reels' || e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1 || e.key === ' ' || $('#ccsheet2').classList.contains('on')) return;
    const a = document.activeElement; if (a && a !== document.body && a.tagName !== 'BUTTON') return;
    const s = $('#rlscan'); if (s) s.focus({ preventScroll: true });
  });
  function rlSetItem(code) {
    const c = RL.cur; rlLast(code); RL.q = '';
    if (c) { if (c.item_code !== code) c.scrapOk = false; c.item_code = code; c.pickItem = false; rlCheck(c); RL.msg = ['info', `Item ${esc(code)}`]; if (rlReady(c) && c.location) return rlSave(false); }
    else RL.msg = ['info', `${esc(code)} will be the item for the next reel`];
    rlRedraw();
  }
  async function rlRoute(code) {
    code = String(code || '').trim(); if (!code) return;
    let r; try { r = await call(RL_API + 'lookup', { code }); } catch (e) { RL.msg = ['bad', `Couldn't look up ${esc(code)}: ${esc(e.message)}`]; return rlRedraw(); }
    const c = RL.cur, v = esc(r.value || code);
    if (r.kind === 'empty') return;
    if (r.kind === 'reel') {
      if (c && c.reel === r.value) RL.msg = ['info', `Still on ${v}`];
      else { const p = r.reel || {}, lost = c && c.method ? ` ${esc(c.reel)} was not saved.` : '';
        RL.cur = { reel: r.value, prior: p, item_code: p.item_code || rlLast() || '', method: '', location: '', warehouse: '', confirm: p.status !== 'Tag only' && !!p.counted_on };
        RL.ft = RL.inch = RL.grams = RL.lot = '';
        RL.msg = p.status === 'In use' ? ['warn', `${v} is out for a work order. Return it before recounting.${lost}`] : ['info', `${v}${p.status === 'Tag only' ? ': new tag' : ''}.${lost}`]; }
    } else if (r.kind === 'item') return rlSetItem(r.value);
    else if (r.kind === 'location') {
      if (!c) RL.msg = ['bad', `Shelf ${v}: scan a reel tag first`];
      else if (c.confirm) {   // a counted reel, not recounted: the shelf scan is a put-away
        try { const s = await call(RL_API + 'set_location', { reel: c.reel, location: r.value }); RL.msg = ['good', `✓ ${esc(s.reel)} moved to ${esc(s.location)}`]; RL.cur = null; } catch (e) { RL.msg = ['bad', `Not moved: ${esc(e.message)}`]; }
      } else { c.location = r.value; c.warehouse = r.warehouse || ''; if (rlReady(c)) return rlSave(false); RL.msg = ['info', `Shelf ${v} set: the reel saves once its length is in`]; }
    } else if (r.kind === 'work_order') RL.msg = ['warn', `${v} is a work order. Scan a reel tag, an item or a shelf.`];
    else RL.msg = ['bad', esc(r.message || `${code} is not a reel, item or shelf`)];
    rlRedraw();
  }
  function rlAct(a) {
    const c = RL.cur, it = c && rlItem(c.item_code);
    if (a === 'cancel') { RL.cur = null; RL.msg = c ? ['info', `${esc(c.reel)} not saved`] : null; RL.ft = RL.inch = RL.grams = RL.lot = ''; }
    else if (!c) { }
    else if (a === 'recount') c.confirm = false;
    else if (a === 'item') c.pickItem = true;
    else if (a === 'keepitem') c.pickItem = false;
    else if (a === 'length') { c.method = ''; c.scrapAsk = c.scrapOk = false; }
    else if (a === 'full' || a === 'measured' || a === 'weigh') {
      if (a === 'full') { if (!it || !(it.standard_mm > 0)) return; c.method = 'Full'; c.length_mm = it.standard_mm; }
      else if (a === 'measured') { const ft = parseFloat(RL.ft) || 0, inch = parseFloat(RL.inch) || 0, mm = Math.round((ft * 304.8 + inch * 25.4) * 10) / 10;
        if (ft < 0 || inch < 0 || mm <= 0) { RL.msg = ['bad', 'Enter the feet and inches on the reel']; return rlRedraw(); } c.method = 'Measured'; c.length_mm = mm; }
      else { const g = parseFloat(RL.grams) || 0; if (g <= 0) { RL.msg = ['bad', 'Enter the weight in grams']; return rlRedraw(); } c.method = 'Weighed'; c.weight_g = g; c.length_mm = null; }
      c.scrapOk = false; rlCheck(c); RL.msg = null;
      if (rlReady(c) && c.location) return rlSave(false);
    }
    else if (a === 'scrap') return rlSave(true);
    else if (a === 'keep') { c.scrapOk = true; c.scrapAsk = false; if (c.location) return rlSave(false); }
    else if (a === 'noshelf') { c.location = c.warehouse = ''; return rlSave(false); }
    rlRedraw();
  }
  async function rlSave(scrap) {
    const c = RL.cur; if (!c || RL.saving) return; RL.saving = true;
    const args = { reel: c.reel, item_code: c.item_code, method: c.method, scrap: scrap ? 1 : 0 };
    if (c.method === 'Measured') args.length_mm = c.length_mm; if (c.method === 'Weighed') args.weight_g = c.weight_g;
    if (c.location) { args.location = c.location; if (c.warehouse) args.warehouse = c.warehouse; } else if (RL.setup.warehouse) args.warehouse = RL.setup.warehouse;
    if (RL.lot.trim()) args.supplier_lot = RL.lot.trim();
    RL.msg = ['info', `Saving ${esc(c.reel)}…`]; rlRedraw();
    try { rlDone(await call(RL_API + 'count_reel', args), args, scrap); } catch (e) { RL.msg = ['bad', `${esc(c.reel)} not saved: ${esc(e.message)}`]; }
    RL.saving = false; rlRedraw();
  }
  function rlDone(r, args, scrap) {
    const it = rlItem(r.item_code) || {}, d = { reel: r.reel, item_code: r.item_code, item_name: r.item_name || it.item_name || '', length: r.length || rlFt(r.length_mm), location: r.location || '', warehouse: r.warehouse || '', scrap: !!scrap,
      at: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }), args };
    RL.done = [d].concat(RL.done.filter(x => x.reel !== d.reel)).slice(0, 20); rlKeep(); rlLast(r.item_code);
    if (RL.cur && RL.cur.prior && RL.cur.prior.status === 'Tag only' && RL.setup.tags_left) RL.setup.tags_left--;
    const line = `✓ ${esc(d.reel)} · ${esc(d.item_name || d.item_code)} · ${scrap ? 'scrapped' : esc(d.length)} · ${esc(d.location || (d.warehouse ? d.warehouse + ' (no shelf)' : 'no shelf'))}`;
    RL.msg = r.under_scrap_line && !scrap ? ['warn', line + ' · under the scrap line', 0] : ['good', line];
    if (RL.cur && RL.cur.reel === r.reel) RL.cur = null; RL.ft = RL.inch = RL.grams = RL.lot = '';
  }
  // a weighed reel can only be checked against the scrap line once saved: "Scrap it" recounts it with scrap=1
  async function rlScrapIt(i) {
    const d = RL.done[i]; if (!d || !d.args) return;
    try { rlDone(await call(RL_API + 'count_reel', Object.assign({}, d.args, { scrap: 1 })), d.args, true); } catch (e) { RL.msg = ['bad', `${esc(d.reel)} not scrapped: ${esc(e.message)}`]; }
    rlRedraw();
  }
  function rlSheet(title, sub, inner, label, fn) {
    const el = sheet(title, sub, inner + `<div class="toolbar"><button type="submit" class="cc-btn primary" id="rlGo">${label}</button></div>`, null), b = el.querySelector('#rlGo'), msg = el.querySelector('#sMsg');
    el.querySelector('#sform').onsubmit = async e => { e.preventDefault(); b.disabled = true; msg.textContent = '';
      try { await fn(el); closeSheet(); const s = $('#rlscan'); if (s) s.focus({ preventScroll: true }); } catch (err) { msg.textContent = 'Not done: ' + err.message; } finally { b.disabled = false; } };
    return el;
  }
  async function rlTool(k) {
    const X = RL.setup;
    if (k === 'tags') rlSheet('Print reel tags', `Blank ID tags (R-00001…) on the 1.5 x 2.5 roll. ${pbN(X.tags_left || 0, 'tag')} printed and not yet counted.`, fld('How many', '<input type="number" name="n" min="1" max="500" value="50" required>'), 'Queue tags', async el => {
      const r = await call(RL_API + 'print_tags', { count: +val(el, 'n') }); X.tags_left = (X.tags_left || 0) + (+val(el, 'n'));
      toast(`Queued ${esc(r.first)} to ${esc(r.last)}; print them from the Labels tab`); lbRefresh(); rlRedraw(); });
    else if (k === 'shelves') rlSheet('Add shelves', 'Shelf codes separated by spaces, commas or new lines. Each gets a LOC- barcode label in the queue.',
      fld('Shelf codes', '<textarea name="codes" rows="4" placeholder="A1 A2 A3 B1" required></textarea>') + fld('Warehouse', `<input type="text" name="wh" value="${esc(X.warehouse || '')}">`), 'Add shelves', async el => {
      const r = await call(RL_API + 'create_locations', { codes: val(el, 'codes'), warehouse: val(el, 'wh') || undefined }), n = r.created.length;
      toast(n ? `Added ${n} shel${n === 1 ? 'f' : 'ves'} (${esc(r.created.join(', '))}); print the labels from the Labels tab` : 'Those shelves already exist');
      RL.at = 0; rlFetch(); lbRefresh(); });
    else if (k === 'labels') { const reels = [...new Set(RL.done.filter(d => !d.scrap).map(d => d.reel))]; if (!reels.length) return;
      try { const r = await call(RL_API + 'print_reel_labels', { reels: JSON.stringify(reels) }); toast(`Queued ${pbN(r.queued || 0, 'reel label')}; print them from the Labels tab`); lbRefresh(); } catch (e) { toast('Not queued: ' + esc(e.message)); } }
    else if (k === 'summary') {
      let r; try { r = await call(RL_API + 'count_summary', {}); } catch (e) { toast('Couldn\'t load the count summary: ' + esc(e.message)); return; }
      const n = v => v == null ? '<span class="calc">—</span>' : pbNum(v, 3), whs = [...new Set(r.rows.filter(x => x.counted_qty != null).map(x => x.warehouse).filter(Boolean))];
      const rows = r.rows.map(x => `<tr><td>${esc(x.item_name || x.item_code)}<div class="m mono">${esc(x.item_code)}</div></td><td>${esc(x.warehouse || '')}</td><td class="num">${x.reels}</td><td>${esc(x.length)}</td><td class="num">${n(x.counted_qty)} ${esc(x.stock_uom || '')}</td><td class="num">${n(x.erpnext_qty)}</td>
        <td class="num">${x.difference == null ? '<span class="calc">—</span>' : x.difference ? `<b class="pb-hi">${x.difference > 0 ? '+' : ''}${pbNum(x.difference, 3)}</b>` : '0'}</td></tr>`);
      const el = sheet('Count summary', `${pbN(r.tags_left || 0, 'blank tag')} not yet counted${r.missing ? ` · ${pbN(r.missing, 'reel')} marked missing` : ''}. Quantities are in each item's stock unit.`,
        flTable(['Item', 'Warehouse', '#Reels', 'Counted length', '#Counted qty', '#ERPNext qty', '#Difference'], rows, 'No reels counted yet')
        + (r.not_counted.length ? `<p class="small"><b>Not counted yet (${r.not_counted.length}):</b> ${r.not_counted.map(esc).join(', ')}</p>` : '')
        + (r.can_reconcile && whs.length ? `<div class="toolbar" style="margin-top:12px">${whs.map(w => `<button type="button" class="cc-btn soft" data-rlrec="${esc(w)}">Draft stock reconciliation · ${esc(w)}</button>`).join('')}</div><p class="small">A draft only: review and submit it in ERPNext to close the count. Items with no counted reels are left out.</p>` : ''), null);
      el.querySelector('.cc-sheet').classList.add('lb-wide');
      el.querySelectorAll('[data-rlrec]').forEach(b => b.onclick = async () => { b.disabled = true;
        try { const d = await call(RL_API + 'make_stock_reconciliation', { warehouse: b.dataset.rlrec }); b.outerHTML = `<a class="cc-btn soft" style="text-decoration:none" target="_blank" rel="noopener" href="${docUrl('stock-reconciliation', d.name)}">Open draft ${esc(d.name)} (${pbN(d.items, 'item')})</a>`; }
        catch (e) { b.disabled = false; el.querySelector('#sMsg').textContent = 'Not drafted: ' + e.message; } });
    }
  }
  V.mfg = m => {
    const row = w => `<tr><td>${link('work-order', w.wo)}</td><td>${link('item', w.item, w.name)}<div class="m mono">${esc(w.item)}</div></td><td class="num">${w.qty}</td><td>${link('sales-order', w.so, short(w.so))}</td><td>${fmtd(w.created)}</td><td>${w.flag === 'Active' ? badge(w.status, w.draft ? 'warn' : 'info') : badge(w.flag.split(':')[0].split(' (')[0], 'bad')}</td></tr>`;
    return header('Manufacturing', 'Flow: every open order and work order at the step it is waiting on, with what to do next in ERPNext. Reports: the schedule workbook\'s views (points, capacity, dollars).',
      `<div class="toolbar no-print"><a class="cc-btn soft" style="text-decoration:none" href="/app/ill-production-settings" target="_blank" rel="noopener">Weights &amp; capacity</a><button class="cc-btn soft" id="pbrefresh">Refresh</button></div>`) +
      `<div id="pbroot">${PB.body()}</div>
      <div class="grid" style="margin-top:20px"><div class="card flush s12"><details class="more"><summary>Work order clean-up (${m.act.length} active · ${m.dup.length} duplicate or stale · ${D.needwo.length} lines with no work order)</summary><div class="grid" style="padding:0 16px 16px">
      ${tableCard('Active work orders', '', ['Work order', 'Item', '#Qty', 'Sales order', 'Created', 'Status'], D.mfg.filter(w => w.flag === 'Active' && rowOK(w)).map(row))}
      ${tableCard('Order lines that need a work order', 'Items with a BOM on submitted sales orders but no work order', ['Item', 'Sales order', '#Qty'], D.needwo.filter(rowOK).map(n => `<tr><td>${link('item', n.item)}</td><td>${link('sales-order', n.so, short(n.so))}</td><td class="num">${n.qty}</td></tr>`), '', 's6')}
      ${tableCard('Duplicate and stale drafts', 'Review and delete in ERPNext', ['Work order', 'Item', '#Qty', 'Sales order', 'Created', 'Flag'], D.mfg.filter(w => w.flag !== 'Active' && rowOK(w)).map(row), '', 's6')}
      </div></details></div></div>`;
  };
  V.ship = m => {
    const rows = D.ship.filter(rowOK);
    const ts = d => +new Date((d || TODAY) + 'T12:00'), lo = Math.min(...rows.map(s => ts(s.delivery)), ts(TODAY)), hi = Math.max(...rows.map(s => ts(s.delivery)), ts(TODAY));
    const pos = d => 3 + (ts(d) - lo) / ((hi - lo) || 1) * 94;
    const col = s => s.state === 'Ready' ? '#12b76a' : s.delivery < TODAY ? '#f04438' : '#f79009';
    const ready = rows.filter(s => s.state === 'Ready').length;
    return header('Shipping', 'What to pick and ship now, then which open sales orders can go out this week and which are at risk.', '<div class="toolbar no-print"><button class="cc-btn soft" id="flrefresh">Refresh</button></div>') + `<div id="flship">${FL.shipBody()}</div><div class="grid">
      ${stat('Open sales orders', D.ship.length, money(D.ship.reduce((a, s) => a + s.value, 0)) + ' total').replace('card stat', 'card stat s4')}
      ${stat('Past delivery date', m.past.length, 'Oldest ' + fmtd(m.past.reduce((a, s) => s.delivery < a ? s.delivery : a, '9999')), m.past.length ? 'bad' : '').replace('card stat', 'card stat s4')}
      ${stat('Ready per ERPNext', ready, 'No draft work orders or shortages', 'good').replace('card stat', 'card stat s4')}
      ${card('Delivery timeline', 'Each open order at its delivery date', `<div class="legend" style="margin-bottom:10px"><span><i style="background:#f04438"></i>Past due</span><span><i style="background:#f79009"></i>Upcoming, at risk</span><span><i style="background:#12b76a"></i>Ready</span></div>
        <div style="position:relative;height:${36 + rows.length * 24}px;background:linear-gradient(#f2f4f7,#f2f4f7) left 0 bottom 0/100% 1px no-repeat">
        <div style="position:absolute;left:${pos(TODAY)}%;top:0;bottom:0;border-left:1.5px dashed #f39c12"></div><div class="calc" style="position:absolute;left:calc(${pos(TODAY)}% + 6px);top:0;color:#b54708">Today</div>
        ${rows.map((s, i) => { const p = pos(s.delivery), right = p > 68; return `<div title="${esc(s.customer)} · ${fmtd(s.delivery)} · ${money(s.value)}" style="position:absolute;top:${22 + i * 24}px;${right ? `right:${100 - p}%;flex-direction:row-reverse` : `left:${p}%`};transform:translateX(${right ? '5px' : '-5px'});display:flex;align-items:center;gap:8px;white-space:nowrap;font-size:12px">
          <span style="width:10px;height:10px;border-radius:50%;flex:none;background:${col(s)};box-shadow:0 0 0 3px #fff"></span><span>${esc(s.customer)} <span class="calc">${fmtd(s.delivery)}</span></span></div>`; }).join('')}</div>`, 's12')}
      ${tableCard('Can it go out?', '', ['Sales order', 'Dealer', 'Delivery', '#Value', '#Delivered', 'Ship?', 'Why'],
        rows.map(s => `<tr><td>${link('sales-order', s.so, short(s.so))}<div class="m">${esc(s.status)}</div></td><td>${cust(s.customer)}</td><td>${s.delivery < TODAY ? badge(fmtd(s.delivery), 'bad') : fmtd(s.delivery)}</td><td class="num">${money(s.value)}</td>
          <td class="num">${s.delivered}%</td><td>${s.state === 'Ready' ? sdot('Ready', 'good') : sdot('At risk', 'warn')}</td><td class="m" style="max-width:320px">${s.reasons.map(esc).join(' · ')}${s.state === 'Ready' && s.delivery < TODAY ? ' · may have shipped without a Delivery Note' : ''}</td></tr>`))}
      ${D.drafts.length ? tableCard('Draft sales orders', 'Not submitted, so they create no demand', ['Draft', 'Customer', '#Value', 'Created'], D.drafts.map(x => `<tr><td>${link('sales-order', x.so, short(x.so))}</td><td>${cust(x.customer)}</td><td class="num">${money(x.value)}</td><td>${fmtd(x.created)}</td></tr>`)) : ''}
    </div>`;
  };
  V.fin = m => {
    const f = D.fin, ms = D.monthly;
    setTimeout(() => vbars($('#ch-fin'), ms.map(x => fmtM(x.month)), [{ name: 'Invoiced', color: '#2a78d6', values: ms.map(x => x.si) }], { fmt: kfmt, target: f.goal, targetLabel: 'Break-even target (calculated)' }));
    return header('Finance', 'Owner: Charlotte. Built from ERPNext Sales Invoices. Cash, payables and true margin need QuickBooks exports.') + `<div class="grid">
      ${stat('Invoiced this month', money(f.mtd), `${f.mtdN} invoices · last month ${money(f.last_month)}`, '', meter(f.mtd / f.goal, m.pace) + `<div class="calc" style="margin-top:6px">${Math.round(f.mtd / f.goal * 100)}% of ${money(f.goal)} target · the tick marks today's pace</div>`).replace('card stat', 'card stat s3')}
      ${stat('On-pace target to date', money(m.goalPace), '<span class="calc">Calculated: target × share of month gone</span>').replace('card stat', 'card stat s3')}
      ${stat('Receivables outstanding', money(f.ar), `${D.ar.length} invoices · QuickBooks payments sync in`).replace('card stat', 'card stat s3')}
      ${stat('Cash · payables · margin', '—', 'Needs a QuickBooks export').replace('card stat', 'card stat s3')}
      ${card('Invoiced by month', 'Break-even target ≈ $17K current business + 8 new dealers × $3K', '<div class="chart" id="ch-fin"></div>', 's8')}
      ${card(`Customer concentration`, `Share of ${TODAY.slice(0, 4)} invoicing, total ${money(D.conc_total)}`, hbars(D.conc.slice(0, 8).map((c, i) => ({ html: cust(c.customer), value: c.pct, color: i === 0 ? '#eb6834' : '#2a78d6' })), { fmt: v => v + '%', lw: '140px', max: Math.max(...D.conc.map(c => c.pct)) }), 's4')}
      ${tableCard('Receivables aging', '', ['Invoice', 'Dealer', 'Due', '#Outstanding', '#Days past due'], D.ar.map(a => `<tr><td>${link('sales-invoice', a.si, short(a.si))}</td><td>${cust(a.customer)}</td><td>${fmtd(a.due)}</td><td class="num">${money(a.amt)}</td><td class="num">${a.days > 0 ? badge(a.days + 'd', 'bad') : a.days}</td></tr>`))}
    </div>`;
  };
  V.tasks = m => {
    let t = m.tasks.filter(passes);
    t.sort((a, b) => (a.status === 'Overdue' ? 0 : 1) - (b.status === 'Overdue' ? 0 : 1) || (a.due || '9999').localeCompare(b.due || '9999'));
    const projs = D.projects.map(p => ({ ...p, open: D.tasks.filter(x => x.project === p.name).length })).filter(p => p.open || p.percent_complete);
    const opt = (v, l, cur) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(l)}</option>`;
    const tools = `<div class="toolbar">
      <select data-f="person">${opt('', 'All people', S.person)}${TEAM.map(u => opt(u.name, u.full_name || u.name, S.person)).join('')}</select>
      <select data-f="source">${opt('', 'All sources', S.source)}${['ERPNext', 'sales@ (help desk)', 'ad hoc', 'meeting'].concat(S.meeting ? [] : ['kevins@']).map(s => opt(s, s, S.source)).join('')}</select>
      <div class="seg">${['', 'Overdue', 'Open'].map(s => `<button data-st="${s}" class="${S.status === s ? 'on' : ''}">${s || 'All'}</button>`).join('')}</div>
      ${LOGGED ? `<label class="cc-switch" style="color:var(--ink2)"><input type="checkbox" data-f="mine" ${S.mine ? 'checked' : ''}><span style="background:${S.mine ? '#f39c12' : '#d0d5dd'}"></span>My items</label>` : ''}${viewsBar('tasks')}</div>`;
    const pr = p => ({ High: 'bad', Medium: 'mute', Low: 'mute' }[p] || 'mute');
    return header('Projects & tasks', 'Live from ERPNext: ToDos (including tasks from Kevin\'s email, hidden in meeting mode), project tasks and open help desk tickets. A task with several owners shows once.', tools) + `<div class="grid">
      ${stat('Open tasks', t.length, 'Matching the filters').replace('card stat', 'card stat s4')}
      ${stat('Overdue', t.filter(x => x.status === 'Overdue').length, 'Past their due date', 'bad').replace('card stat', 'card stat s4')}
      ${stat('Due in the next 7 days', t.filter(x => x.due && x.due >= TODAY && x.due <= addDays(TODAY, 7)).length, '').replace('card stat', 'card stat s4')}
      ${tableCard(`Master task list`, 'Overdue first, then by due date', ['Task', 'Owners', 'Due', 'Source', ''],
        t.slice(0, S.limit).map(x => `<tr class="${x.private ? 'priv' : ''}"><td style="max-width:560px">${x.kind === 'task' ? `<a href="#p-${esc(x.ref.name)}" style="color:var(--ink);font-weight:500">${esc(x.title)}</a>` : `<a target="_blank" rel="noopener" href="${x.url}" style="color:var(--ink);font-weight:500">${esc(x.title)}</a>`}
          ${x.notes ? `<div class="m">${esc(x.notes.slice(0, 180))}</div>` : ''}${x.ref ? `<div class="m">${link(x.ref.dt, x.ref.name, x.ref.dt + ' · ' + short(x.ref.name))}</div>` : ''}</td>
          <td>${avs(x.owners)}</td><td style="white-space:nowrap">${x.due ? (x.status === 'Overdue' ? badge(fmtd(x.due), 'bad') : fmtd(x.due)) : '<span class="calc">—</span>'}${x.priority === 'High' ? `<div class="m" style="color:var(--badt)">High priority</div>` : ''}</td>
          <td style="white-space:nowrap">${esc(x.source)}${x.tag && !['email', 'ad-hoc', 'meeting'].includes(x.tag) ? `<div class="m">${esc(x.tag)}</div>` : ''}${x.mail ? `<div class="m"><a target="_blank" rel="noopener" href="${x.mail}">Open email</a></div>` : ''}</td>
          <td class="num" style="white-space:nowrap">${x.kind === 'todo' && LOGGED ? `<button class="cc-btn soft" data-done="${x.ids.join(',')}">✓ Done</button> ` : ''}<a class="cc-btn soft" target="_blank" rel="noopener" href="${x.url}" style="text-decoration:none">Edit</a></td></tr>`).concat(t.length > S.limit ? [`<tr><td colspan="5" style="text-align:center;padding:14px"><button class="cc-btn soft" data-more="1">Show ${Math.min(30, t.length - S.limit)} more of ${t.length - S.limit} remaining</button></td></tr>`] : []), '', 's12')}
      ${card('Projects', `${D.projects.length - projs.length} other open projects have no tasks yet`, hbars(projs.map(p => ({ html: link('project', p.name, p.project_name), value: Math.round(p.percent_complete || 0), title: p.open + ' open tasks' })), { fmt: v => v + '%', lw: '300px', max: 100 }), 's12')}
    </div>`;
  };
  V.rec = m => header('Recommendations', 'New projects or actions the data points to, each with an owner and a reason.', `<span class="calc">${noteLink('Command Center – Recommendations')}</span>`) + `<div class="card note">${D.notes['Command Center – Recommendations'] || '<div class="empty">No note yet</div>'}</div>`;

  /* ---------------- projects ---------------- */
  const TSTAT = { 'Open': '#98a2b3', 'Working': '#2a78d6', 'Pending Review': '#6250d6', 'Overdue': '#f04438', 'Completed': '#12b76a' };
  const COLS = ['Open', 'Working', 'Pending Review', 'Completed'];
  const tOver = t => t.status !== 'Completed' && t.end && t.end < TODAY;
  function prepProjects() {
    D.ptasks.forEach(t => { t.owners = JSON.parse(t._assign || '[]'); t.start = t.exp_start_date ? String(t.exp_start_date).slice(0, 10) : null; t.end = t.exp_end_date ? String(t.exp_end_date).slice(0, 10) : null; });
    D.projects.forEach(p => {
      p.tasks = D.ptasks.filter(t => t.project === p.name);
      p.done = p.tasks.filter(t => t.status === 'Completed').length;
      p.over = p.tasks.filter(tOver).length;
      p.team = [...new Set(p.tasks.flatMap(t => t.owners))];
      p.start = p.expected_start_date ? String(p.expected_start_date).slice(0, 10) : null; p.end = p.expected_end_date ? String(p.expected_end_date).slice(0, 10) : null;
      p.pct = p.tasks.length ? Math.round(p.done / p.tasks.length * 100) : Math.round(p.percent_complete || 0);
      p.next = p.tasks.filter(t => t.status !== 'Completed' && t.end).sort((a, b) => a.end.localeCompare(b.end))[0];
    });
  }
  const statusBar = tasks => { const n = tasks.length || 1, c = {}; tasks.forEach(t => { const k = tOver(t) ? 'Overdue' : t.status in TSTAT ? t.status : 'Open'; c[k] = (c[k] || 0) + 1; });
    return `<div class="stk" style="height:8px" title="${Object.entries(c).map(([k, v]) => v + ' ' + k).join(' · ')}">${['Completed', 'Working', 'Pending Review', 'Open', 'Overdue'].filter(k => c[k]).map(k => `<i style="flex:${c[k]};background:${TSTAT[k]}"></i>`).join('')}</div>`; };
  const statusLegend = () => `<div class="legend">${Object.entries(TSTAT).map(([k, v]) => `<span><i style="background:${v}"></i>${k}</span>`).join('')}</div>`;
  const pBtn = (label, attr, primary) => LOGGED ? `<button class="cc-btn ${primary ? 'primary' : 'soft'}" ${attr}>${label}</button>` : `<a class="cc-btn soft" href="/login?redirect-to=/command-center%23${S.view}" style="text-decoration:none">Log in to ${label.replace(/^\+ /, '').toLowerCase()}</a>`;

  V.projects = m => {
    const active = D.projects.filter(p => p.tasks.length && p.status === 'Open' && rowOK({ n: p.project_name, c: p.customer, t: p.tasks.map(t => t.subject) }));
    const empty = D.projects.filter(p => !p.tasks.length && p.status === 'Open' && rowOK({ n: p.project_name, c: p.customer }));
    const done = D.projects.filter(p => p.status === 'Completed');
    const open = D.ptasks.filter(t => t.status !== 'Completed'), over = open.filter(tOver), week = open.filter(t => t.end && t.end >= TODAY && t.end <= addDays(TODAY, 7));
    const ppl = TEAM.map(u => u.name), mat = active.map(p => ({ p, c: ppl.map(u => p.tasks.filter(t => t.status !== 'Completed' && t.owners.includes(u)).length) }));
    const mx = Math.max(1, ...mat.flatMap(r => r.c));
    return header('Projects & tasks', 'Every company project, its tasks and who owns them. Click a project for its board and timeline.', `<div class="toolbar">${pBtn('+ New task', 'data-newtask=""')}${pBtn('+ New project', 'data-newproj', true)}</div>`) + `
      <div class="grid" style="margin-bottom:20px">
        ${stat('Active projects', active.length, `${empty.length} more have no tasks yet`).replace('card stat', 'card stat s3')}
        ${stat('Open project tasks', open.length, `${D.ptasks.length - open.length} completed`).replace('card stat', 'card stat s3')}
        ${stat('Overdue', over.length, 'Past their end date', over.length ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Due in the next 7 days', week.length, '').replace('card stat', 'card stat s3')}
      </div>
      <div class="pgrid">${active.map(p => `<a class="pcard" href="#p-${esc(p.name)}">
        <div class="r"><div style="min-width:0"><div class="eyebrow">${esc(p.name)}${p.customer ? ' · ' + esc(p.customer) : ''}</div><div class="pt">${esc(p.project_name)}</div></div>${ringPct(p.pct, 60)}</div>
        ${statusBar(p.tasks)}
        <div class="r" style="margin-top:12px"><span class="small">${p.done}/${p.tasks.length} tasks done${p.over ? ` · <b style="color:var(--badt)">${p.over} overdue</b>` : ''}</span>${avs(p.team)}</div>
        <div class="pn">${p.next ? `Next: <b>${esc(p.next.subject)}</b> · ${tOver(p.next) ? badge(fmtd(p.next.end), 'bad') : fmtd(p.next.end)}` : '<span class="calc">No open tasks with dates</span>'}</div>
        <div class="r small" style="margin-top:6px"><span>${p.start ? fmtd(p.start) : '—'} → ${p.end ? fmtd(p.end) : 'no end date'}</span>${p.priority ? `<span>${esc(p.priority)} priority</span>` : ''}</div></a>`).join('') || '<div class="card empty">No active projects with tasks yet. Create one with “New project”.</div>'}</div>
      ${active.length ? card('Who\'s on what', 'Open tasks per person per project. Darker = more tasks.', `<div class="tw"><table class="heat"><thead><tr><th>Project</th>${ppl.map(u => `<th class="num">${avatar(u)}</th>`).join('')}</tr></thead><tbody>
        ${mat.map(r => `<tr><td><a href="#p-${esc(r.p.name)}">${esc(r.p.project_name)}</a></td>${r.c.map(v => `<td class="num"><span class="hc" style="background:${v ? `rgba(42,120,214,${0.15 + 0.85 * v / mx})` : 'var(--line2)'};color:${v / mx > .5 ? '#fff' : 'var(--ink2)'}">${v || ''}</span></td>`).join('')}</tr>`).join('')}</tbody></table></div>`, 's12').replace('class="card s12"', 'class="card s12" style="margin-top:20px"') : ''}
      ${empty.length ? `<div class="card flush" style="margin-top:20px"><details class="more"><summary>Open projects with no tasks yet (${empty.length})</summary><div class="chipwrap">${empty.map(p => `<a class="pchip" href="#p-${esc(p.name)}">${esc(p.project_name)}</a>`).join('')}</div></details></div>` : ''}
      ${done.length ? `<div class="card flush" style="margin-top:20px"><details class="more"><summary>Recently completed (${done.length})</summary><div class="chipwrap">${done.map(p => `<a class="pchip" href="#p-${esc(p.name)}">✓ ${esc(p.project_name)}</a>`).join('')}</div></details></div>` : ''}`;
  };

  V.project = (m, id) => {
    const p = D.projects.find(x => x.name === id);
    if (!p) return header('Project not found', `${esc(id)} isn't an open or recently completed project.`) + '<a href="#projects">← All projects</a>';
    let tasks = p.tasks.filter(t => (!S.pperson || t.owners.includes(S.pperson)) && rowOK(t));
    const mode = S.pmode || 'board';
    const tools = `<div class="toolbar"><div class="seg">${['board', 'timeline', 'list'].map(k => `<button data-pmode="${k}" class="${mode === k ? 'on' : ''}">${k[0].toUpperCase() + k.slice(1)}</button>`).join('')}</div>
      ${pBtn('+ Add task', `data-newtask="${esc(p.name)}"`, true)}<a class="cc-btn soft" target="_blank" rel="noopener" href="/app/project/${encodeURIComponent(p.name)}" style="text-decoration:none">Open in ERPNext</a></div>`;
    const people = `<div class="pfilter"><span class="small">Filter:</span><button data-pp="" class="${!S.pperson ? 'on' : ''}">Everyone</button>${p.team.map(u => `<button data-pp="${esc(u)}" class="${S.pperson === u ? 'on' : ''}">${avatar(u)}${esc(SHORT[u] || u)}</button>`).join('')}</div>`;
    let body = '';
    if (mode === 'board') {
      const cols = COLS.concat(tasks.some(t => t.status === 'Overdue') ? [] : []);
      body = `<div class="board">${cols.map(c => { const ts = tasks.filter(t => (t.status === c) || (c === 'Open' && t.status === 'Overdue'));
        return `<div class="bcol" data-col="${c}"><div class="lane-h"><span><span class="dot" style="background:${TSTAT[c]}"></span> ${c}</span><span class="ct">${ts.length}</span></div>
          ${ts.map(t => `<div class="tcard" draggable="${LOGGED}" data-task="${esc(t.name)}"><div class="tt">${esc(t.subject)}</div>
            <div class="r" style="margin-top:10px">${avs(t.owners)}<span>${t.end ? (tOver(t) ? badge(fmtd(t.end), 'bad') : `<span class="small">${fmtd(t.end)}</span>`) : ''}</span></div>
            ${t.priority === 'High' || t.deps.length ? `<div class="m" style="margin-top:6px">${t.priority === 'High' ? '<span style="color:var(--badt)">High</span>' : ''}${t.priority === 'High' && t.deps.length ? ' · ' : ''}${t.deps.length ? `Waits on ${t.deps.length} task${t.deps.length > 1 ? 's' : ''}` : ''}</div>` : ''}</div>`).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`; }).join('')}</div>
        ${LOGGED ? '<p class="calc" style="margin-top:10px">Drag a card to another column to change its status. Click a card to edit it.</p>' : ''}`;
    } else if (mode === 'timeline') {
      const dated = tasks.filter(t => t.start || t.end).sort((a, b) => (a.start || a.end).localeCompare(b.start || b.end));
      const lo = Math.min(...dated.map(t => ts(t.start || t.end)), ts(TODAY)), hi = Math.max(...dated.map(t => ts(t.end || t.start)), ts(TODAY)) + 864e5;
      const X = d => (ts(d) - lo) / (hi - lo) * 100;
      const months = []; for (let d = new Date(lo); d <= hi; d.setDate(d.getDate() + 7)) months.push(new Date(d));
      body = `<div class="card">${statusLegend()}<div class="gantt">
        <div class="gscale">${months.map(d => `<span style="left:${X(d.toISOString().slice(0, 10))}%">${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>`).join('')}</div>
        <div class="gtoday" style="left:calc(260px + (100% - 260px) * ${X(TODAY) / 100})"><span>Today</span></div>
        ${dated.map(t => { const s = t.start || t.end, e = t.end || t.start, col = tOver(t) ? TSTAT.Overdue : TSTAT[t.status] || TSTAT.Open;
          return `<div class="grow" data-task="${esc(t.name)}"><div class="gl">${avs(t.owners)}<span title="${esc(t.subject)}">${esc(t.subject)}</span></div>
          <div class="gt"><i style="left:${X(s)}%;width:max(10px, ${X(addDays(e, 1)) - X(s)}%);background:${col}" title="${esc(t.subject)} · ${fmtd(s)} → ${fmtd(e)} · ${esc(t.status)}"></i></div></div>`; }).join('') || '<div class="empty">No tasks with dates</div>'}</div>
        ${tasks.length > dated.length ? `<p class="calc">${tasks.length - dated.length} task(s) without dates aren't shown.</p>` : ''}</div>`;
    } else {
      body = tableCard('Tasks', '', ['Task', 'Owners', 'Status', 'Start', 'Due', 'Priority'], tasks.map(t => `<tr data-task="${esc(t.name)}" style="cursor:pointer"><td><b style="font-weight:500">${esc(t.subject)}</b>${t.deps.length ? `<div class="m">Waits on ${t.deps.join(', ')}</div>` : ''}</td><td>${avs(t.owners)}</td>
        <td>${sdot(tOver(t) ? 'Overdue' : t.status, tOver(t) ? 'bad' : t.status === 'Completed' ? 'good' : t.status === 'Working' ? 'info' : 'mute')}</td><td>${fmtd(t.start)}</td><td>${tOver(t) ? badge(fmtd(t.end), 'bad') : fmtd(t.end)}</td><td>${esc(t.priority || '')}</td></tr>`), '', 's12');
    }
    return `<a href="#work" class="small" style="display:inline-block;margin-bottom:10px">← All projects</a>` + header(esc(p.project_name), `${esc(p.name)}${p.customer ? ' · ' + cust(p.customer) : ''} · ${p.start ? fmtd(p.start) : '—'} → ${p.end ? fmtd(p.end) : 'no end date'} · ${badge(p.status, p.status === 'Completed' ? 'good' : 'info')}`, tools) + `
      <div class="grid" style="margin-bottom:20px">
        <div class="card s3"><div class="eyebrow">Progress</div><div class="ring-wrap" style="margin-top:10px">${ringPct(p.pct, 92)}<div><div style="font-size:22px;font-weight:700">${p.done}<span class="small"> / ${p.tasks.length}</span></div><div class="small">tasks done</div>${p.over ? `<div class="small" style="color:var(--badt);margin-top:4px">${p.over} overdue</div>` : ''}</div></div></div>
        <div class="card s5"><div class="eyebrow">Task status</div><div style="margin:14px 0 10px">${statusBar(p.tasks)}</div>${statusLegend()}</div>
        <div class="card s4"><div class="eyebrow">Team</div><div style="margin-top:12px;display:flex;flex-direction:column;gap:8px">${p.team.map(u => { const n = p.tasks.filter(t => t.owners.includes(u) && t.status !== 'Completed').length, o = p.tasks.filter(t => t.owners.includes(u) && tOver(t)).length;
          return `<div style="display:flex;align-items:center;gap:10px">${avatar(u)}<span style="flex:1">${esc(SHORT[u] || u)}</span><span class="small">${n} open${o ? ` · <b style="color:var(--badt)">${o} overdue</b>` : ''}</span></div>`; }).join('') || '<span class="calc">Nobody assigned yet</span>'}</div></div>
      </div>${p.notes ? `<div class="card" style="margin-bottom:20px"><div class="eyebrow" style="margin-bottom:8px">About this project</div><div class="small" style="color:var(--ink2)">${p.notes}</div></div>` : ''}
      ${people}${body}`;
  };
  function ringPct(pct, size) { const R = size / 2 - 6, C = 2 * Math.PI * R, c = size / 2;
    return `<svg width="${size}" height="${size}" style="flex:none"><circle cx="${c}" cy="${c}" r="${R}" fill="none" stroke="#f2f4f7" stroke-width="7"/>${pct ? `<circle cx="${c}" cy="${c}" r="${R}" fill="none" stroke="#12b76a" stroke-width="7" stroke-linecap="round" stroke-dasharray="${C * pct / 100} ${C}" transform="rotate(-90 ${c} ${c})"/>` : ''}<text x="${c}" y="${c + size / 14}" text-anchor="middle" font-size="${size / 4.4}" font-weight="700" fill="#101828">${pct}%</text></svg>`; }
  const ts = d => +new Date(String(d).slice(0, 10) + 'T12:00');

  /* ---- forms ---- */
  function sheet(title, sub, inner, onSave, saveLabel = 'Save') {
    const el = $('#ccsheet2');
    el.innerHTML = `<div class="cc-sheet"><div class="cc-sheet-h"><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div><button class="cc-x" data-close aria-label="Close">×</button></div>
      <form id="sform">${inner}<p class="cc-msg" id="sMsg"></p><div class="cc-sheet-f">${onSave ? `<button class="cc-btn primary" type="submit" id="sSave">${saveLabel}</button>` : ''}</div></form></div>`;
    el.classList.add('on');
    el.querySelector('[data-close]').onclick = closeSheet; el.onclick = e => { if (e.target === el) closeSheet(); };
    el.querySelector('#sform').onsubmit = async e => { e.preventDefault(); if (!onSave) return; const b = el.querySelector('#sSave'), msg = el.querySelector('#sMsg');
      b.disabled = true; const t = b.textContent; b.textContent = 'Saving…';
      try { await onSave(el); closeSheet(); await load(); } catch (err) { msg.textContent = 'Not saved: ' + err.message; } finally { b.disabled = false; b.textContent = t; } };
    setTimeout(() => { const f = el.querySelector('input[type=text]'); if (f) f.focus(); }, 50);
    return el;
  }
  function closeSheet() { $('#ccsheet2').classList.remove('on'); }
  const ownerChips = (sel = []) => `<div class="cc-owners">${TEAM.map(u => `<label><input type="checkbox" name="own" value="${esc(u.name)}" ${sel.includes(u.name) ? 'checked' : ''}>${avatar(u.name)}${esc(u.full_name || u.name)}</label>`).join('')}</div>`;
  const fld = (label, html) => `<label class="cc-field"><span>${label}</span>${html}</label>`;
  const sel = (name, opts, cur) => `<select name="${name}">${opts.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(l)}</option>`; }).join('')}</select>`;
  const val = (el, n) => (el.querySelector(`[name="${n}"]`) || {}).value || '';
  const checked = el => [...el.querySelectorAll('input[name=own]:checked')].map(i => i.value);

  function newProject() {
    sheet('New project', 'Creates an ERPNext Project. Add tasks to it right after.', `
      ${fld('Project name', '<input type="text" name="pname" placeholder="e.g. Lutron 206 extrusion launch">')}
      <div class="cc-row2">${fld('Start', `<input type="date" name="pstart" value="${TODAY}">`)}${fld('Target end', '<input type="date" name="pend">')}</div>
      <div class="cc-row2">${fld('Priority', sel('ppri', ['Medium', 'High', 'Low'], 'Medium'))}${fld('Customer (optional)', `<input type="text" name="pcust" list="cccusts" placeholder="Start typing…"><datalist id="cccusts">${D.customers.map(c => `<option value="${esc(c)}">`).join('')}</datalist>`)}</div>
      ${fld('What is this project about?', '<textarea name="pnotes" rows="3"></textarea>')}`, async el => {
      const name = val(el, 'pname').trim(); if (!name) throw new Error('add a project name');
      const c = val(el, 'pcust').trim(); if (c && !D.customers.includes(c)) throw new Error('pick a customer from the list, or leave it blank');
      const doc = { doctype: 'Project', project_name: name, status: 'Open', priority: val(el, 'ppri'), expected_start_date: val(el, 'pstart') || null, expected_end_date: val(el, 'pend') || null, percent_complete_method: 'Task Completion' };
      if (c) doc.customer = c; if (val(el, 'pnotes').trim()) doc.notes = '<p>' + esc(val(el, 'pnotes').trim()) + '</p>';
      const r = await call('frappe.client.insert', { doc }); toast(`Project ${esc(r.name)} created`); location.hash = 'p-' + r.name;
    }, 'Create project');
  }
  function newTask(pid) {
    const projs = D.projects.filter(p => p.status === 'Open');
    sheet('New task', 'Creates an ERPNext Task. Each owner is assigned and notified.', `
      ${fld('Task', '<input type="text" name="tsub" placeholder="What needs to happen?">')}
      ${fld('Project', sel('tproj', projs.map(p => [p.name, p.project_name]), pid || (projs[0] || {}).name))}
      <div class="cc-field"><span>Owners</span>${ownerChips()}</div>
      <div class="cc-row2">${fld('Start', `<input type="date" name="tstart" value="${TODAY}">`)}${fld('Due', '<input type="date" name="tend">')}</div>
      <div class="cc-row2">${fld('Priority', sel('tpri', ['Medium', 'High', 'Low', 'Urgent'], 'Medium'))}${fld('Status', sel('tstat', ['Open', 'Working', 'Pending Review'], 'Open'))}</div>
      ${fld('Details', '<textarea name="tdesc" rows="3"></textarea>')}`, async el => {
      const sub = val(el, 'tsub').trim(), own = checked(el); if (!sub) throw new Error('add a task title');
      const start = val(el, 'tstart') || null, end = val(el, 'tend') || null; if (start && end && end < start) throw new Error('due date is before the start date');
      const doc = { doctype: 'Task', subject: sub, project: val(el, 'tproj'), status: val(el, 'tstat'), priority: val(el, 'tpri'), exp_start_date: start, exp_end_date: end };
      if (val(el, 'tdesc').trim()) doc.description = '<p>' + esc(val(el, 'tdesc').trim()) + '</p>';
      const r = await call('frappe.client.insert', { doc });
      if (own.length) await call('frappe.desk.form.assign_to.add', { doctype: 'Task', name: r.name, assign_to: own, date: end, priority: doc.priority === 'Urgent' ? 'High' : doc.priority, description: sub });
      toast(`Task ${esc(r.name)} created${own.length ? ' · ' + own.length + ' notified' : ''}`); if (!S.view.startsWith('p-')) location.hash = 'p-' + doc.project;
    }, 'Create task');
  }
  function editTask(id) {
    const t = D.ptasks.find(x => x.name === id); if (!t) return;
    const ro = !LOGGED;
    const el = sheet(esc(t.subject), `${esc(t.name)} · ${link('project', t.project, (D.projects.find(p => p.name === t.project) || {}).project_name || t.project)} · ${link('task', t.name, 'Open in ERPNext')}`, `
      ${ro ? `<p class="callout" style="margin:0 0 14px">You're viewing as a guest. <a href="/login?redirect-to=/command-center%23${S.view}">Log in</a> to edit.</p>` : ''}
      ${fld('Task', `<input type="text" name="tsub" value="${esc(t.subject)}" ${ro ? 'disabled' : ''}>`)}
      <div class="cc-row2">${fld('Status', sel('tstat', ['Open', 'Working', 'Pending Review', 'Completed', 'Cancelled'], t.status === 'Overdue' ? 'Open' : t.status))}${fld('Priority', sel('tpri', ['Low', 'Medium', 'High', 'Urgent'], t.priority))}</div>
      <div class="cc-row2">${fld('Start', `<input type="date" name="tstart" value="${t.start || ''}">`)}${fld('Due', `<input type="date" name="tend" value="${t.end || ''}">`)}</div>
      <div class="cc-field"><span>Owners</span>${ownerChips(t.owners)}</div>
      ${t.deps.length ? `<div class="cc-field"><span>Waits on</span><div class="small">${t.deps.map(d => { const x = D.ptasks.find(y => y.name === d); return `${x ? sdot(x.status, x.status === 'Completed' ? 'good' : 'mute') : ''} ${esc(x ? x.subject : d)}`; }).join('<br>')}</div></div>` : ''}
      ${t.description ? `<div class="cc-field"><span>Details</span><div class="small" style="color:var(--ink2);white-space:pre-wrap">${esc(t.description)}</div></div>` : ''}`, ro ? null : async el => {
      const f = { subject: val(el, 'tsub').trim(), status: val(el, 'tstat'), priority: val(el, 'tpri'), exp_start_date: val(el, 'tstart') || null, exp_end_date: val(el, 'tend') || null };
      if (f.exp_start_date && f.exp_end_date && f.exp_end_date < f.exp_start_date) throw new Error('due date is before the start date');
      if (f.status === 'Completed' && t.status !== 'Completed') f.completed_on = TODAY;
      const ch = {}; Object.entries(f).forEach(([k, v]) => { const old = k === 'exp_start_date' ? t.start : k === 'exp_end_date' ? t.end : t[k]; if ((v || null) !== (old || null)) ch[k] = v; });
      if (Object.keys(ch).length) await call('frappe.client.set_value', { doctype: 'Task', name: t.name, fieldname: ch });
      const own = checked(el), add = own.filter(u => !t.owners.includes(u)), rem = t.owners.filter(u => !own.includes(u));
      if (add.length) await call('frappe.desk.form.assign_to.add', { doctype: 'Task', name: t.name, assign_to: add, date: f.exp_end_date, priority: f.priority === 'Urgent' ? 'High' : f.priority, description: f.subject });
      for (const u of rem) await call('frappe.desk.form.assign_to.remove', { doctype: 'Task', name: t.name, assign_to: u });
      toast('Task updated in ERPNext');
    }, 'Save changes');
    if (ro) el.querySelectorAll('input,select,textarea').forEach(i => i.disabled = true);
  }
  async function moveTask(id, status) {
    const t = D.ptasks.find(x => x.name === id); if (!t || t.status === status) return;
    const f = { status }; if (status === 'Completed') f.completed_on = TODAY;
    t.status = status; render();
    try { await call('frappe.client.set_value', { doctype: 'Task', name: id, fieldname: f }); toast(`Moved to ${esc(status)}`); }
    catch (e) { toast('Could not move: ' + esc(e.message)); }
    await load();
  }
  function bindProjects() {
    root.querySelectorAll('[data-newproj]').forEach(b => b.onclick = newProject);
    root.querySelectorAll('[data-newtask]').forEach(b => b.onclick = () => newTask(b.dataset.newtask));
    root.querySelectorAll('[data-pmode]').forEach(b => b.onclick = () => { S.pmode = b.dataset.pmode; render(); });
    root.querySelectorAll('[data-pp]').forEach(b => b.onclick = () => { S.pperson = b.dataset.pp; render(); });
    root.querySelectorAll('[data-task]').forEach(c => { c.onclick = () => editTask(c.dataset.task); c.ondragstart = e => { e.dataTransfer.setData('text/plain', c.dataset.task); c.classList.add('drag'); }; c.ondragend = () => c.classList.remove('drag'); });
    root.querySelectorAll('.bcol').forEach(col => { col.ondragover = e => { if (LOGGED) { e.preventDefault(); col.classList.add('over'); } }; col.ondragleave = () => col.classList.remove('over');
      col.ondrop = e => { e.preventDefault(); col.classList.remove('over'); moveTask(e.dataTransfer.getData('text/plain'), col.dataset.col); }; });
  }

  /* ---------------- sales pipeline ---------------- */
  const fmtM = m => new Date(m + '-15T12:00').toLocaleDateString('en-US', { month: 'short' }) + (m.endsWith('-01') ? " '" + m.slice(2, 4) : '');
  const INQ_TYPES = ['Quotation', 'Design'];
  const DONE_TK = ['Resolved', 'Closed'];
  function pipeData(m) {
    const inq = D.tk.filter(t => INQ_TYPES.includes(t.type));
    const inqOpen = inq.filter(t => t.status === 'Open'), inqWait = inq.filter(t => t.status === 'Replied');
    const realQ = D.quotes.filter(q => !/^ZZ /i.test(q.party_name || '') && q.party_name !== 'ilLumenate Lighting');
    const qOut = realQ.filter(q => q.docstatus === 1 && q.status === 'Open'), qDraft = realQ.filter(q => q.docstatus === 0);
    const qExp = qOut.filter(q => q.valid_till && String(q.valid_till).slice(0, 10) <= addDays(TODAY, 7));
    const soVal = D.ship.reduce((a, s) => a + s.value, 0);
    const soShort = D.ship.filter(s => soPurch(s.so).length), soMfg = D.ship.filter(s => soWOs(s.so).length || D.needwo.some(n => n.so === s.so));
    const ready = D.ship.filter(s => s.state === 'Ready');
    return { inq, inqOpen, inqWait, qOut, qDraft, qExp, qVal: qOut.reduce((a, q) => a + (q.base_net_total || 0), 0), soVal, soShort, soMfg, ready,
      corr: D.ship.filter(s => soFlags(s).length) };
  }
  const woSO = {}; // filled in prepPipe
  function prepPipe() {
    D.mfg.forEach(w => { woSO[w.wo] = w.so; });
    D.byRef = {};
    D.T.forEach(t => { if (t.ref) { const k = t.ref.dt + '|' + t.ref.name; (D.byRef[k] = D.byRef[k] || []).push(t); } });
    D.projBySO = {}; D.projects.forEach(p => { if (p.sales_order) (D.projBySO[p.sales_order] = D.projBySO[p.sales_order] || []).push(p); });
    D.tkBySO = {}; D.tkByQ = {};
    D.tk.forEach(t => { if (t.sales_order) (D.tkBySO[t.sales_order] = D.tkBySO[t.sales_order] || []).push(t); if (t.quotation) (D.tkByQ[t.quotation] = D.tkByQ[t.quotation] || []).push(t); });
    D.qByName = {}; D.quotes.forEach(q => { D.qByName[q.name] = q; });
  }
  const soPurch = so => puShort().filter(r => r.short_firm > 0 && (r.docs || []).some(x => x.doc === so || (x.src === 'Work Order' && woSO[x.doc] === so)));
  const soPOs = so => PU.data ? (PU.data.pos || []).filter(p => (p.sales_orders || []).includes(so) && p.lane !== 'done') : [];
  const soWOs = so => D.mfg.filter(w => w.so === so);
  const soTodos = so => (D.byRef['Sales Order|' + so] || []);
  const soTasks = so => (D.projBySO[so] || []).flatMap(p => p.tasks.filter(t => t.status !== 'Completed'));
  function soFlags(s) {
    const f = [];
    if (s.value <= 0) f.push(['Order value ' + money(s.value), 'bad']);
    if (s.status === 'On Hold') f.push(['On hold', 'warn']);
    if (s.delivery && s.delivery < TODAY) f.push(['Past delivery date', 'bad']);
    const old = (s.lines || []).filter(l => l.old); if (old.length) f.push([old.length + ' line(s) on retired part numbers', 'warn']);
    const dup = soWOs(s.so).filter(w => w.flag !== 'Active'); if (dup.length) f.push([dup.length + ' duplicate/stale work order(s)', 'warn']);
    if (s.state === 'Ready' && s.delivery < TODAY) f.push(['May have shipped without a Delivery Note', 'warn']);
    D.changes.filter(c => c.sales_order === s.so && !['COMPLETED', 'REJECTED'].includes(c.state)).forEach(c => f.push([c.request_type + ' request ' + c.state.toLowerCase().replace('_', ' '), 'info']));
    return f;
  }
  function soSteps(s) {
    const pur = soPurch(s.so).length, wos = soWOs(s.so).filter(w => w.flag === 'Active'), nw = D.needwo.filter(n => n.so === s.so).length;
    return [
      ['Ordered', 'good', 'Submitted'],
      ['Materials', pur ? 'bad' : 'good', pur ? pur + ' short' : 'In stock'],
      ['Production', nw ? 'bad' : wos.length ? 'warn' : 'good', nw ? nw + ' need WO' : wos.length ? wos.length + ' WO open' : 'Done / none'],
      ['Shipped', s.delivered >= 100 ? 'good' : s.delivered > 0 ? 'warn' : s.state === 'Ready' ? 'info' : 'mute', s.delivered >= 100 ? 'Delivered' : s.delivered > 0 ? s.delivered + '%' : s.state === 'Ready' ? 'Ready' : 'Not yet'],
      ['Billed', s.status === 'To Deliver' ? 'good' : 'mute', s.status === 'To Deliver' ? 'Invoiced' : 'Not yet'],
    ];
  }
  const miniSteps = s => `<div class="msteps">${soSteps(s).map(([n, k]) => `<span class="ms ${k}" title="${n}"></span>`).join('')}</div>`;
  const bigSteps = s => `<div class="steps">${soSteps(s).map(([n, k, d], i) => `<div class="step ${k}"><div class="sc">${k === 'good' ? '✓' : k === 'bad' ? '!' : i + 1}</div><div><div class="sn">${n}</div><div class="sd">${esc(d || (i ? '' : 'Submitted'))}</div></div></div>`).join('<div class="sl"></div>')}</div>`;

  function stepper(m, cur) {
    const p = pipeData(m), x = PL.data;
    const svcOpen = D.tk.filter(t => (SVC_TYPES.includes(t.type) || !t.type) && t.status === 'Open');
    const dsn = x ? x.schedules.filter(z => schedStage(z) === 'design') : null, dr = x ? x.doc_requests.filter(r => DR_OPEN.includes(r.status) && !r.sales_order) : null;
    const qr = x ? x.quote_requests.filter(q => q.state === 'REQUESTED' || q.state === 'UNDER_REVIEW') : null, oi = x ? x.intakes.filter(o => o.state === 'SUBMITTED' || o.state === 'UNDER_REVIEW') : null;
    const ar = x ? x.account_requests.filter(a => a.state === 'Pending') : null;
    const SUM = {
      pipeline: () => [`${m.newThis.length}/8`, 'new dealers', m.newThis.length >= 8 * m.pace ? 'good' : 'bad'],
      design: () => x ? [dsn.length, `${dr.length} drawing${dr.length === 1 ? '' : 's'} open`, dr.some(r => ageBd(r.creation) > 2 && r.status !== 'Waiting on Customer') ? 'warn' : 'good'] : ['…', 'loading', 'mute'],
      quotes: () => [(qr ? qr.length : p.inqOpen.length) + p.qOut.length, `${p.qOut.length} quotes out`, (qr || []).some(q => ageBd(q.creation) > 2) || p.inqOpen.some(t => t.age > 2) ? 'warn' : 'good'],
      orders: () => [D.ship.length, oi && oi.length ? `${oi.length} new request${oi.length === 1 ? '' : 's'}` : kfmt(p.soVal) + ' open', p.corr.length || (oi || []).some(o => ageBd(o.creation) > 2) ? 'warn' : 'good'],
      purch: () => { const u = PU.data && PU.data.summary; if (!u) return [m.firm.length, `${m.late.length} late`, m.late.length ? 'bad' : 'good'];
        const late = (u.to_order || {}).late || 0, od = (u.pos || {}).overdue || 0; return [(u.to_order || {}).count || 0, `${late} late · ${od} PO${od === 1 ? '' : 's'} overdue`, late || od ? 'bad' : (u.to_order || {}).count ? 'warn' : 'good']; },
      mfg: () => { const f = FL.data && FL.data.summary; if (!f) return [m.act.length, `${D.needwo.length} lines need WO`, D.needwo.length || m.dup.length ? 'warn' : 'good'];
        return [f.wo_open, `open WOs · ${f.lines_need_wo} line${f.lines_need_wo === 1 ? '' : 's'} need one`, f.lines_need_wo ? 'bad' : f.wo_lanes.draft || f.wo_lanes.waiting_parts ? 'warn' : 'good']; },
      ship: () => [`${p.ready.length}/${D.ship.length}`, `ready · ${m.past.length} past due`, m.past.length ? 'bad' : 'good'],
      service: () => [svcOpen.length + (ar ? ar.length : 0), ar && ar.length ? `${ar.length} account request${ar.length === 1 ? '' : 's'}` : 'tickets our move', svcOpen.some(t => t.age > 2) || (ar || []).some(a => ageBd(a.creation) > 2) ? 'bad' : 'good'],
    };
    return `<div class="chev">${STAGES.map(st => { const [v, l, k] = SUM[st.k](); return `<a href="#${st.k}" class="cv ${cur === st.k ? 'on' : ''}"><div class="cvn"><span class="dot ${k}"></span>${esc(st.n)}</div><div class="cvv">${esc(v)}</div><div class="cvl">${esc(l)}</div></a>`; }).join('')}</div>`;
  }

  V.pipeline = m => {
    const p = pipeData(m), tr = D.trend.filter(x => x.change != null && rowOK(x)).slice(0, 10);
    const fun = [
      ['design', 'In design', PL.data ? PL.data.schedules.filter(z => schedStage(z) === 'design').length : p.inqOpen.length + p.inqWait.length, PL.data ? 'fixture schedules · ' + PL.data.doc_requests.filter(r => DR_OPEN.includes(r.status)).length + ' drawings open' : 'design & quote tickets open', '#1d6bc8'],
      ['quotes', 'Quote requests', PL.data ? PL.data.quote_requests.filter(q => QR_ACTIVE.includes(q.state) && q.state !== 'ISSUED').length : p.inqOpen.length, 'from the portal, not yet issued', '#2a78d6'],
      ['quotes', 'Quotes out', p.qOut.length, kfmt(p.qVal) + ' waiting on dealers', '#3b84dc'],
      ['orders', 'Sales orders', D.ship.length, kfmt(p.soVal) + ' open', '#4c90e1'],
      ['purch', 'Need materials', p.soShort.length, m.firm.length + ' lines short', '#eb6834'],
      ['mfg', 'In production', p.soMfg.length, m.act.length + ' work orders', '#eda100'],
      ['ship', 'Ready to ship', p.ready.length, m.past.length + ' orders past due', '#12b76a'],
      ['service', 'Service', D.tk.filter(t => (SVC_TYPES.includes(t.type) || !t.type) && t.status === 'Open').length + (PL.data ? PL.data.account_requests.filter(a => AR_OPEN.includes(a.state)).length : 0), 'tickets & customer requests open', '#6250d6'],
      ['finance', 'Invoiced this month', D.fin.mtdN, kfmt(D.fin.mtd), '#067647'],
    ];
    const fmax = Math.max(...fun.map(f => f[2]), 1);
    return header('Sales pipeline', 'From first inquiry to invoice, and how far we are from break-even. Click a stage to dig in.') + `
      <div class="grid">
        <div class="card s8"><div class="card-h"><div><h2>Pipeline right now</h2><div class="sub">Live counts at each stage</div></div></div>
          <div class="funnel">${fun.map(([k, n, v, l, c], i) => `<a class="fr" href="#${k}"><div class="fl"><div class="fn">${n}</div><div class="small">${esc(l)}</div></div>
            <div class="ft"><i style="width:${Math.max(4, v / fmax * 100)}%;background:${c}"></i></div><div class="fv">${v}</div></a>`).join('')}</div></div>
        <div class="card s4"><div class="eyebrow">Break-even this month</div><div class="ring-wrap" style="margin-top:12px">${ring(m.newThis.length, 8, '#2a78d6', 'new dealers', 112)}
          <div><div class="small">On pace by today</div><div style="font-size:20px;font-weight:700">${(8 * m.pace).toFixed(1)}</div><div class="small" style="margin-top:8px">At $3K+ this month</div><div style="font-size:20px;font-weight:700">${m.new3k.length}</div></div></div>
          <div style="margin-top:16px" class="small">Invoiced ${money(D.fin.mtd)} of ${money(D.fin.goal)} target</div>${meter(D.fin.mtd / D.fin.goal, m.pace)}
          <div style="margin-top:14px;display:flex;justify-content:space-between" class="small"><span>SPIF qualifying orders</span><b style="color:var(--ink)">${m.spifQ.length}</b></div>
          <div style="display:flex;justify-content:space-between" class="small"><span>Rep payouts owed</span><b style="color:var(--ink)">$0</b></div>
          <div style="display:flex;justify-content:space-between" class="small"><span>Active dealers (90 days)</span><b style="color:var(--ink)">${D.active90}</b></div>
          <div style="display:flex;justify-content:space-between" class="small"><span>Dealers with no pricing tier</span><b style="color:var(--ink)">${D.tiers['(none)'] || 0}</b></div></div>
        ${card('Existing dealers, last 90 days vs the 90 before', 'Keep current business: change in invoiced amount, largest accounts first', dbars(tr.map(x => ({ html: cust(x.customer), value: x.change, title: `${money(x.prior)} → ${money(x.recent)}` })), v => (v > 0 ? '+' : '') + v + '%'), 's7')}
        ${card('Invoiced by month', 'Against the break-even target', '<div class="chart" id="ch-pipe"></div>', 's5')}
        ${tableCard('New dealers', '“New” = first submitted order or invoice in that month. Goal: 8 a month, each ordering $3K+ a month.', ['Dealer', 'First order', 'Tier', 'Rep', '#Last month', '#This month', '$3K+'],
          D.newd.filter(rowOK).map(x => `<tr><td>${cust(x.customer)}</td><td>${fmtd(x.first)}</td><td>${esc(x.tier || '—')}</td><td>${esc(x.rep || '—')}</td><td class="num">${money(x.last_month)}</td><td class="num">${money(x.this_month)}</td><td>${x.this_month >= 3000 ? badge('Yes', 'good') : badge('Not yet', 'mute')}</td></tr>`), '', 's7')}
        ${tableCard('SPIF candidates', `$3K+ orders since Oct 1. SPIF counts from ${fmtd(D.spif_start)}.`, ['Order', 'Dealer', '#Amount', 'SPIF'],
          D.spif.map(x => `<tr><td>${link('sales-order', x.so, short(x.so))}<div class="m">${fmtd(x.date)} · rep: ${esc(x.rep || 'none')}</div></td><td>${cust(x.customer)}</td><td class="num">${money(x.amount)}</td><td>${x.eligible ? badge('Qualifies', 'good') : badge('Before SPIF', 'mute')}</td></tr>`), '', 's5')}
      </div>`;
  };

  V.quotes = m => {
    const p = pipeData(m);
    const since = addDays(TODAY, -30);
    const tks = p.inq.filter(t => t.type === 'Quotation' && rowOK(t) && (!DONE_TK.includes(t.status) || (t.modified || t.created) >= since));
    const col = (title, sub, list, k) => `<div class="bcol"><div class="lane-h"><span><span class="dot ${k}"></span> ${title}</span><span class="ct">${list.length}</span></div><div class="small" style="margin:-4px 0 10px">${sub}</div>
      ${list.map(t => { const q = t.quotation && D.qByName[t.quotation], td = D.byRef['HD Ticket|' + t.name] || [];
        return `<div class="tcard"><div class="r"><span class="badge mute">Quote</span>${t.status === 'Open' && t.age > 2 ? badge(t.age + 'd', 'bad') : `<span class="small">${t.age}d</span>`}</div>
          <div class="tt" style="margin-top:8px"><a href="#" data-tksheet="${esc(t.name)}">${esc(t.subject || t.name)}</a></div><div class="m">${esc(t.raised_by || '')}</div>
          ${q ? `<div class="qchip">${link('quotation', q.name, short(q.name).replace('ilL-SAL-QTN-', ''))} · ${money(q.base_net_total)} · ${esc(q.docstatus === 0 ? 'Draft' : q.status)}</div>` : (t.type === 'Quotation' ? (LOGGED ? `<button class="cc-btn soft" style="margin-top:8px" data-linkq="${esc(t.name)}">Link quotation</button>` : '<div class="m" style="margin-top:6px">No quotation linked</div>') : '')}
          ${td.length ? `<div class="tdl">${td.slice(0, 3).map(x => `<div>☐ <a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a></div>`).join('')}${td.length > 3 ? `<div class="calc">+${td.length - 3} more</div>` : ''}</div>` : ''}
          <div class="r" style="margin-top:10px">${avs(t.assignedL)}<span class="small">${fmtd(t.created)}</span></div></div>`; }).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`;
    const qrows = p.qOut.concat(S.qdraft ? p.qDraft : []).filter(rowOK).sort((a, b) => String(a.valid_till || '9').localeCompare(String(b.valid_till || '9')));
    const qrq = PL.data ? PL.data.quote_requests.filter(q => q.state === 'REQUESTED' || q.state === 'UNDER_REVIEW') : null, qrw = PL.data ? PL.data.quote_requests.filter(q => q.state === 'INFORMATION_NEEDED') : null;
    const qOpen = tks.filter(t => t.status === 'Open'), qWait = tks.filter(t => t.status === 'Replied');
    return header('Quotes', 'Quote requests from the portal, the offers and quotations we\'ve sent, and quotation tickets from sales@. Schedules arrive here from Design.') + `
      <div class="grid" style="margin-bottom:20px">
        ${qrq ? stat('Quote requests, our move', qrq.length, `${qrq.filter(q => ageBd(q.creation) > 2).length} older than 2 business days · ${qOpen.length} tickets open`, qrq.some(q => ageBd(q.creation) > 2) ? 'bad' : '').replace('card stat', 'card stat s3')
          : stat('Our move', qOpen.length, `${qOpen.filter(t => t.age > 2).length} waiting over 2 business days`, qOpen.some(t => t.age > 2) ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Waiting on dealer', (qrw ? qrw.length : 0) + qWait.length, `${qrw ? qrw.length + ' requests need info · ' : ''}${qWait.length} tickets replied`).replace('card stat', 'card stat s3')}
        ${stat('Quotes out', p.qOut.length, `${money(p.qVal)} waiting on dealers`).replace('card stat', 'card stat s3')}
        ${stat('Expiring in 7 days', p.qExp.length, `${p.qDraft.length} unsent drafts (last 120 days)`, p.qExp.length ? 'bad' : '').replace('card stat', 'card stat s3')}
      </div>
      ${sec('Quote requests', 'From the portal: requested → under review → issued → the dealer\'s answer. Red age = waiting on us more than 2 business days.')}${quoteLanes()}
      ${sec('Quotation tickets', 'Quote conversations from sales@ (design tickets are on <a href="#design">Design</a>)')}
      <div class="board" style="grid-template-columns:repeat(3,minmax(260px,1fr))">
        ${col('Our move', 'Open: needs a reply or a quote', tks.filter(t => t.status === 'Open').sort((a, b) => b.age - a.age), 'bad')}
        ${col('Waiting on customer', 'Replied: follow up if quiet for 10+ days', tks.filter(t => t.status === 'Replied').sort((a, b) => b.age - a.age), 'warn')}
        ${col('Done (last 30 days)', 'Resolved or closed', tks.filter(t => DONE_TK.includes(t.status)), 'good')}
      </div>
      <div class="grid" style="margin-top:20px">${tableCard('Quotes waiting on dealers', 'Submitted quotations still open, soonest expiry first', ['Quotation', 'Dealer', 'Sent', 'Valid till', '#Value', 'Ticket', 'Status'],
        qrows.map(q => { const vt = q.valid_till && String(q.valid_till).slice(0, 10), tkl = D.tkByQ[q.name] || [];
          return `<tr><td>${link('quotation', q.name, q.name.replace('ilL-SAL-QTN-', ''))}${q.ill_quote_request ? `<div class="m">${link('ill-quote-request', q.ill_quote_request)}</div>` : ''}</td><td>${cust(q.party_name)}</td><td>${fmtd(q.transaction_date)}<div class="m">${bdaysJS(q.transaction_date)} business days ago</div></td>
            <td>${vt ? (vt < TODAY ? badge('Expired ' + fmtd(vt), 'bad') : vt <= addDays(TODAY, 7) ? badge(fmtd(vt), 'warn') : fmtd(vt)) : '—'}</td><td class="num">${money(q.base_net_total)}</td>
            <td>${tkl.map(t => link('hd-ticket', t.name)).join(', ') || '<span class="calc">—</span>'}</td><td>${q.docstatus === 0 ? badge('Draft', 'mute') : badge('Waiting', 'info')}</td></tr>`; }),
        `<label class="cc-switch" style="color:var(--ink2)"><input type="checkbox" data-qdraft ${S.qdraft ? 'checked' : ''}><span style="background:${S.qdraft ? '#f39c12' : '#d0d5dd'}"></span>Include drafts</label>`)}</div>`;
  };
  const bdaysJS = d => { let a = new Date(String(d).slice(0, 10) + 'T12:00'), b = new Date(TODAY + 'T12:00'), n = 0; while (a < b) { a.setDate(a.getDate() + 1); if (a.getDay() % 6) n++; } return n; };


  // ticket board used by Sales orders (order-status tickets + any ticket linked to an order)
  function orderTicketBoard() {
    const since = addDays(TODAY, -30);
    const all = D.tk.filter(t => t.type === 'Sales Order' || t.sales_order);
    const tks = all.filter(t => rowOK(t) && (!DONE_TK.includes(t.status) || (t.modified || t.created) >= since));
    const card = t => { const so = t.sales_order, s = so && D.ship.find(x => x.so === so), td = D.byRef['HD Ticket|' + t.name] || [];
      return `<div class="tcard"><div class="r"><span class="badge ${t.type === 'Sales Order' ? 'info' : 'mute'}">${esc(t.type === 'Sales Order' ? 'Order status' : (t.type || 'Untyped'))}</span>${t.status === 'Open' && t.age > 2 ? badge(t.age + 'd', 'bad') : t.status === 'Replied' && t.idle > 10 ? badge(t.idle + 'd quiet', 'warn') : `<span class="small">${t.age}d</span>`}</div>
        <div class="tt" style="margin-top:8px"><a href="#" data-tksheet="${esc(t.name)}">${esc(t.subject || t.name)}</a></div><div class="m">${esc(t.raised_by || '')}</div>
        ${so ? `<div class="qchip">Order ${s ? `<a href="#so-${encodeURIComponent(so)}">${esc(short(so))}</a> · ${esc(s.status)} · ${money(s.value)}` : link('sales-order', so, short(so)) + ' · not open'}</div>` : (LOGGED && !DONE_TK.includes(t.status) ? `<button class="cc-btn soft" style="margin-top:8px" data-linkso="${esc(t.name)}">Link sales order</button>` : '<div class="m" style="margin-top:6px">No order linked</div>')}
        ${td.length ? `<div class="tdl">${td.slice(0, 3).map(x => `<div>☐ <a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a></div>`).join('')}${td.length > 3 ? `<div class="calc">+${td.length - 3} more</div>` : ''}</div>` : ''}
        <div class="r" style="margin-top:10px">${avs(t.assignedL)}<span class="small">${fmtd(t.created)}</span></div></div>`; };
    const col = (title, sub, list, k) => `<div class="bcol"><div class="lane-h"><span><span class="dot ${k}"></span> ${title}</span><span class="ct">${list.length}</span></div><div class="small" style="margin:-4px 0 10px">${sub}</div>${list.map(card).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`;
    return `<div class="card-h" style="margin:28px 0 12px"><div><h2 style="font-size:17px">Order tickets</h2><div class="sub">Order-status tickets from sales@ and any ticket linked to a sales order (${all.filter(t => t.sales_order).length} linked so far)</div></div></div>
      <div class="board" style="grid-template-columns:repeat(3,minmax(260px,1fr))">
        ${col('Our move', 'Open: needs a reply or an update', tks.filter(t => t.status === 'Open').sort((a, b) => b.age - a.age), 'bad')}
        ${col('Waiting on customer', 'Replied: follow up if quiet for 10+ days', tks.filter(t => t.status === 'Replied').sort((a, b) => b.idle - a.idle), 'warn')}
        ${col('Done (last 30 days)', 'Resolved or closed', tks.filter(t => DONE_TK.includes(t.status)), 'good')}
      </div>`;
  }
  const tkPills = so => { const ts = (D.tkBySO[so] || []); if (!ts.length) return '';
    const open = ts.filter(t => t.status === 'Open').length, wait = ts.filter(t => t.status === 'Replied').length;
    return `<span class="pill" title="${esc(ts.map(t => t.name + ' ' + t.status).join(', '))}"><span class="dot ${open ? 'bad' : wait ? 'warn' : 'good'}"></span>${ts.length} ticket${ts.length > 1 ? 's' : ''}${open ? ' · ' + open + ' open' : wait ? ' · waiting' : ''}</span>`; };

  V.orders = m => {
    const p = pipeData(m), rows = D.ship.filter(rowOK);
    return header('Sales orders', 'Order requests from the portal, then every open order with its progress, to-dos, tasks and anything that needs correcting.') + `
      <div class="grid" style="margin-bottom:20px">
        ${stat('Open orders', D.ship.length, money(p.soVal) + ' total').replace('card stat', 'card stat s3')}
        ${stat('Past delivery date', m.past.length, '', m.past.length ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Need materials', p.soShort.length, 'Orders with short items').replace('card stat', 'card stat s3')}
        ${stat('Need correcting', p.corr.length, 'Flags below', p.corr.length ? 'bad' : '').replace('card stat', 'card stat s3')}
      </div>
      ${orderLanes()}
      ${sec('Open sales orders', 'Click an order for the full picture')}
      <div class="sol">${rows.map(s => { const fl = soFlags(s), td = soTodos(s.so), tk = soTasks(s.so);
        return `<a class="sorow" href="#so-${encodeURIComponent(s.so)}"><div class="so-a"><div class="so-n">${esc(short(s.so))}</div><div class="small">${esc(s.customer)} · ${esc(s.status)}</div></div>
          <div class="so-b">${miniSteps(s)}<div class="small">${soSteps(s).map(x => x[0] + ': ' + x[2]).slice(1, 4).join(' · ')}</div></div>
          <div class="so-c"><div class="num" style="font-weight:600">${money(s.value)}</div><div class="small">${s.delivery < TODAY ? `<span style="color:var(--badt)">Due ${fmtd(s.delivery)}</span>` : 'Due ' + fmtd(s.delivery)}</div></div>
          <div class="so-d">${tkPills(s.so)}${td.length ? `<span class="pill">☐ ${td.length} to-do${td.length > 1 ? 's' : ''}</span>` : ''}${tk.length ? `<span class="pill">▦ ${tk.length} task${tk.length > 1 ? 's' : ''}</span>` : ''}${fl.slice(0, 2).map(f => badge(f[0], f[1])).join('')}${fl.length > 2 ? `<span class="calc">+${fl.length - 2}</span>` : ''}</div>
          <div class="so-e">›</div></a>`; }).join('') || '<div class="card empty">No open sales orders</div>'}</div>
      ${orderTicketBoard()}
      ${D.drafts.length ? `<div class="grid" style="margin-top:20px">${tableCard('Draft sales orders', 'Not submitted, so they create no demand yet', ['Draft', 'Customer', '#Lines', '#Value', 'Created'], D.drafts.map(x => `<tr><td>${link('sales-order', x.so, short(x.so))}</td><td>${cust(x.customer)}</td><td class="num">${x.lines_n || ''}</td><td class="num">${money(x.value)}</td><td>${fmtd(x.created)}</td></tr>`))}</div>` : ''}
      <div class="grid" style="margin-top:20px">${tableCard('Order change requests', 'Changes, cancellations, reorders and replacements dealers asked for in the portal', ['Request', 'Order', 'Type', 'State', 'Owner', 'Due'],
        D.changes.map(c => `<tr><td>${link('ill-order-change', c.name)}</td><td>${link('sales-order', c.sales_order, short(c.sales_order))}</td><td>${esc(c.request_type)}</td><td>${esc(c.state)}</td><td>${c.assigned_to ? avatar(c.assigned_to) : '—'}</td><td>${fmtd(c.due_date)}</td></tr>`))}</div>`;
  };

  V.so = (m, id) => {
    const s = D.ship.find(x => x.so === id);
    if (!s) return `<a href="#orders" class="small">← All sales orders</a>` + header('Order not open', `${esc(id)} isn't an open sales order (it may be completed or closed).`, `<a class="cc-btn soft" target="_blank" href="/app/sales-order/${encodeURIComponent(id)}">Open in ERPNext</a>`);
    const pur = soPurch(s.so), wos = soWOs(s.so), nw = D.needwo.filter(n => n.so === s.so), td = soTodos(s.so), tk = soTasks(s.so), fl = soFlags(s), tks = D.tkBySO[s.so] || [];
    const q = s.quotation && D.qByName[s.quotation];
    return `<a href="#orders" class="small" style="display:inline-block;margin-bottom:10px">← All sales orders</a>` + header(esc(short(s.so)), `${cust(s.customer)} · ${esc(s.status)} · due ${fmtd(s.delivery)} · ${money(s.value)}`,
      `<div class="toolbar">${pBtn('+ Add to-do', `data-sotodo="${esc(s.so)}"`, true)}<a class="cc-btn soft" target="_blank" rel="noopener" href="/app/sales-order/${encodeURIComponent(s.so)}" style="text-decoration:none">Open in ERPNext</a></div>`) + `
      <div class="card" style="margin-bottom:20px">${bigSteps(s)}</div>
      <div class="grid">
        ${card('Needs correcting', '', fl.length ? fl.map(f => `<div style="padding:6px 0">${badge(f[0], f[1])}</div>`).join('') : '<div class="empty" style="padding:8px">Nothing flagged</div>', 's4')}
        ${card('To-dos', 'ERPNext ToDos on this order', (td.length ? td.map(x => `<div class="todo-r"><span>${avs(x.owners)}</span><a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a>${x.due ? (x.due < TODAY ? badge(fmtd(x.due), 'bad') : `<span class="small">${fmtd(x.due)}</span>`) : ''}${LOGGED ? `<button class="cc-btn soft" data-done="${x.ids.join(',')}">✓</button>` : ''}</div>`).join('') : '<div class="empty" style="padding:8px">No to-dos</div>'), 's4')}
        ${card('Related', '', `<div class="small" style="line-height:2">Quotation: ${q ? link('quotation', q.name, q.name.replace('ilL-SAL-QTN-', '')) + ' · ' + money(q.base_net_total) : (s.quotation ? link('quotation', s.quotation) : '—')}<br>
          Tickets: ${tks.length ? '' : '—'}${tks.map(t => `<div class="todo-r" style="line-height:1.4"><span>${sdot(t.status === 'Open' ? 'Our move' : t.status === 'Replied' ? 'Waiting' : t.status, t.status === 'Open' ? 'bad' : t.status === 'Replied' ? 'warn' : 'good')}</span>${link('hd-ticket', t.name, t.name + ' · ' + (t.subject || ''))}<span class="small">${t.age}d</span></div>`).join('')}Projects: ${(D.projBySO[s.so] || []).map(p => `<a href="#p-${esc(p.name)}">${esc(p.project_name)}</a>`).join(', ') || '—'}<br>
          Order requests: ${PL.data ? (PL.data.oiBySO[s.so] || []).map(o => `${link('ill-order-intake', o.name)} ${stBadge(o.state)}`).join(' ') || '—' : '…'}<br>
          Drawing requests: ${PL.data ? (PL.data.reqBySO[s.so] || []).map(r => `${link('ill-document-request', r.name)} ${stBadge(r.status)}`).join(' ') || '—' : '…'}<br>
          Tasks open: ${tk.length}</div>${tk.length ? `<div style="margin-top:8px">${tk.slice(0, 5).map(t => `<div class="todo-r"><span>${avs(t.owners)}</span><span>${esc(t.subject)}</span></div>`).join('')}</div>` : ''}`, 's4')}
        ${tableCard('Order lines', `${s.lines.length} lines`, ['Item', '#Qty', '#Delivered', '#Amount', ''], s.lines.map(l => `<tr><td>${link('item', l.item, l.name || l.item)}<div class="m mono">${esc(l.item)}</div></td><td class="num">${l.qty}</td><td class="num">${l.delivered}</td><td class="num">${money(l.amount)}</td><td>${l.old ? badge('Retired code', 'warn') : ''}</td></tr>`), '', 's12')}
        ${tableCard('Purchasing needed for this order', PU.data ? 'Short components, and the purchase orders feeding this order with their ETA' : 'Short components for this order and its work orders', ['Item', '#Short', 'Supplier', 'Order by', 'Draft PO / MR', ''],
          pur.map(r => `<tr><td>${link('item', r.item)}<div class="m">${esc(r.group || '')}</div></td><td class="num"><b>${+r.short_firm.toFixed(2)}</b></td><td>${r.supplier ? link('supplier', r.supplier) : badge('No supplier', 'warn')}</td>
            <td>${r.order_by ? (r.late ? badge('Late · ' + fmtd(r.order_by), 'bad') : fmtd(r.order_by)) : '—'}</td><td>${[r.draft_po && link('purchase-order', r.draft_po), r.mr && link('material-request', r.mr)].filter(Boolean).join('<br>') || '<span class="calc">None</span>'}</td>
            <td class="num">${!r.draft_po && !r.mr && !r.manufactured && LOGGED ? `<button class="cc-btn soft" data-mr="${esc(r.item)}">Draft MR</button>` : ''}</td></tr>`).concat(soPOs(s.so).map(p => `<tr><td colspan="3">${link('purchase-order', p.name)} <span class="small">${esc(p.supplier || '')} · ${esc(p.vendor_status || p.status || '')}</span></td><td colspan="3">${p.eta ? (p.overdue ? badge('ETA ' + fmtd(p.eta) + ' · overdue', 'bad') : p.will_miss ? badge('ETA ' + fmtd(p.eta) + ' · late for this order', 'warn') : 'ETA ' + fmtd(p.eta)) : '<span class="calc">No ETA</span>'}</td></tr>`)), '', 's6')}
        ${tableCard('Manufacturing', `${wos.filter(w => w.flag === 'Active').length} active work orders${nw.length ? ` · ${nw.length} line(s) need one` : ''}`, ['Work order', 'Item', '#Qty', 'Status'],
          wos.map(w => `<tr><td>${link('work-order', w.wo)}</td><td>${esc(w.name || w.item)}</td><td class="num">${w.qty}</td><td>${w.flag === 'Active' ? badge(w.status, w.draft ? 'warn' : 'info') : badge('Duplicate/stale', 'bad')}</td></tr>`).concat(nw.map(n => `<tr><td>${badge('Needs WO', 'bad')}</td><td>${link('item', n.item)}</td><td class="num">${n.qty}</td><td></td></tr>`)), '', 's6')}
      </div>`;
  };

  V.purch_low = () => {
    const inPur = new Set(D.purch.map(r => r.item)), low = D.lowstock.filter(b => !inPur.has(b.item) && rowOK(b));
    return tableCard('General low stock', 'Items whose projected stock is below zero across all demand (not already listed above). No reorder levels are set yet, so this is the only low-stock signal.', ['Item', 'Warehouse', '#On hand', '#Reserved', '#On order', '#Projected', ''],
      low.map(b => `<tr><td>${link('item', b.item)}</td><td>${esc(b.warehouse)}</td><td class="num">${+b.actual.toFixed(1)}</td><td class="num">${+b.reserved.toFixed(1)}</td><td class="num">${+b.ordered.toFixed(1)}</td><td class="num"><b style="color:var(--badt)">${+b.projected.toFixed(1)}</b></td>
        <td class="num">${LOGGED ? `<button class="cc-btn soft" data-mrlow="${esc(b.item)}" data-qty="${Math.ceil(-b.projected)}">Draft MR</button>` : ''}</td></tr>`));
  };


  const SVC_TYPES = ['Service', 'Issue', 'Unspecified'];
  V.service = m => {
    const since = addDays(TODAY, -30);
    const all = D.tk.filter(t => SVC_TYPES.includes(t.type) || !t.type);
    const tks = all.filter(t => rowOK(t) && (!DONE_TK.includes(t.status) || (t.modified || t.created) >= since));
    const open = all.filter(t => t.status === 'Open'), wait = all.filter(t => t.status === 'Replied'), done30 = all.filter(t => DONE_TK.includes(t.status) && (t.modified || t.created) >= since);
    const buckets = [['0–2 days', 0, 2], ['3–5 days', 3, 5], ['6–10 days', 6, 10], ['Over 10 days', 11, 1e9]];
    const ageRows = buckets.map(([l, a, b]) => ({ label: l, value: open.concat(wait).filter(t => t.age >= a && t.age <= b).length, color: b > 10 ? '#eb6834' : '#2a78d6' }));
    const col = (title, sub, list, k) => `<div class="bcol"><div class="lane-h"><span><span class="dot ${k}"></span> ${title}</span><span class="ct">${list.length}</span></div><div class="small" style="margin:-4px 0 10px">${sub}</div>
      ${list.map(t => { const so = t.sales_order, s = so && D.ship.find(x => x.so === so), td = D.byRef['HD Ticket|' + t.name] || [];
        return `<div class="tcard"><div class="r"><span class="badge ${t.type === 'Service' ? 'warn' : 'mute'}">${esc(t.type || 'Untyped')}</span>${t.status === 'Open' && t.age > 2 ? badge(t.age + 'd', 'bad') : t.status === 'Replied' && t.idle > 10 ? badge(t.idle + 'd quiet', 'warn') : `<span class="small">${t.age}d</span>`}</div>
          <div class="tt" style="margin-top:8px"><a href="#" data-tksheet="${esc(t.name)}">${esc(t.subject || t.name)}</a></div><div class="m">${esc(t.raised_by || '')}</div>
          ${so ? `<div class="qchip">Order ${s ? `<a href="#so-${encodeURIComponent(so)}">${esc(short(so))}</a> · ${esc(s.status)}` : link('sales-order', so, short(so))}</div>` : (LOGGED && !DONE_TK.includes(t.status) ? `<button class="cc-btn soft" style="margin-top:8px" data-linkso="${esc(t.name)}">Link sales order</button>` : '')}
          ${td.length ? `<div class="tdl">${td.slice(0, 3).map(x => `<div>☐ <a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a></div>`).join('')}${td.length > 3 ? `<div class="calc">+${td.length - 3} more</div>` : ''}</div>` : ''}
          <div class="r" style="margin-top:10px">${avs(t.assignedL)}<span class="small">${fmtd(t.created)}</span></div></div>`; }).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`;
    const people = {}; open.concat(wait).forEach(t => (t.assignedL.length ? t.assignedL : ['(unassigned)']).forEach(u => { people[u] = (people[u] || 0) + 1; }));
    return header('Service', 'After shipping: customer requests from the portal (dealer applications, address and contact changes) and tech support tickets from sales@.') + `
      ${accountLanes()}
      ${sec('Service tickets', 'What\'s waiting on us, what\'s waiting on the customer, and how old it is')}
      <div class="grid" style="margin-bottom:20px">
        ${stat('Our move', open.length, `${open.filter(t => t.age > 2).length} waiting over 2 business days`, open.some(t => t.age > 2) ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Waiting on customer', wait.length, `${wait.filter(t => t.idle > 10).length} quiet for 10+ days`).replace('card stat', 'card stat s3')}
        ${stat('Resolved, last 30 days', done30.length, '').replace('card stat', 'card stat s3')}
        ${stat('Linked to an order', all.filter(t => t.sales_order).length, `of ${all.length} service tickets`).replace('card stat', 'card stat s3')}
        ${card('Age of open tickets', 'Open and waiting tickets, by business days since created', hbars(ageRows, { lw: '120px' }), 's6')}
        ${card('Who has them', 'Open and waiting tickets per person', hbars(Object.entries(people).sort((a, b) => b[1] - a[1]).map(([u, v]) => ({ html: u === '(unassigned)' ? '<span class="calc">Unassigned</span>' : `${avatar(u)} ${esc(SHORT[u] || u)}`, value: v })), { lw: '140px' }), 's6')}
      </div>
      <div class="board" style="grid-template-columns:repeat(3,minmax(260px,1fr))">
        ${col('Our move', 'Open: needs a reply or a fix', tks.filter(t => t.status === 'Open').sort((a, b) => b.age - a.age), 'bad')}
        ${col('Waiting on customer', 'Replied: close it if quiet for 10+ days', tks.filter(t => t.status === 'Replied').sort((a, b) => b.idle - a.idle), 'warn')}
        ${col('Done (last 30 days)', 'Resolved or closed', tks.filter(t => DONE_TK.includes(t.status)), 'good')}
      </div>`;
  };
  function linkSO(tid) {
    const t = D.tk.find(x => x.name === tid); if (!t) return;
    const sos = D.ship.map(s => s.so);
    sheet('Link a sales order', `Ticket ${esc(t.name)}: ${esc(t.subject || '')}`, fld('Sales order', `<input type="text" name="lso" list="ccsolist" placeholder="Start typing a dealer or order number"><datalist id="ccsolist">${D.ship.map(s => `<option value="${esc(s.so)}">${esc(s.customer)} · ${money(s.value)} · ${esc(s.status)}</option>`).join('')}</datalist>`) + '<p class="small">Open orders are listed. You can also paste any sales order number.</p>', async el => {
      const v = val(el, 'lso').trim(); if (!v) throw new Error('enter a sales order');
      await gw('save', { dt: 'HD Ticket', name: t.name, values: { ill_sales_order: v } }); toast('Sales order linked to ticket ' + esc(t.name)); PL.stale = true;
    }, 'Link');
  }

  V.work = m => V.projects(m);
  V.rec = m => header('This week & recommendations', 'What the team has to decide or do, and the actions the data points to.') + `<div class="grid">
    ${card('This week', '', `<div class="note">${D.notes['Command Center – This week'] || '<div class="empty">No note yet</div>'}</div>`, 's6', `<span class="calc">${noteLink('Command Center – This week')}</span>`)}
    ${card('Recommendations', '', `<div class="note">${D.notes['Command Center – Recommendations'] || '<div class="empty">No note yet</div>'}</div>`, 's6', `<span class="calc">${noteLink('Command Center – Recommendations')}</span>`)}</div>`;

  function linkQuote(tid) {
    const t = D.tk.find(x => x.name === tid); if (!t) return;
    const qs = D.quotes.filter(q => q.docstatus < 2);
    sheet('Link a quotation', `Ticket ${esc(t.name)}: ${esc(t.subject || '')}`, fld('Quotation', `<input type="text" name="lq" list="ccqlist" placeholder="Start typing a dealer or quote number"><datalist id="ccqlist">${qs.map(q => `<option value="${esc(q.name)}">${esc(q.party_name)} · ${money(q.base_net_total)} · ${esc(q.docstatus === 0 ? 'Draft' : q.status)}</option>`).join('')}</datalist>`), async el => {
      const v = val(el, 'lq').trim(); if (!D.qByName[v]) throw new Error('pick a quotation from the list');
      await gw('save', { dt: 'HD Ticket', name: t.name, values: { ill_quotation: v } }); toast('Quotation linked to ticket ' + esc(t.name)); PL.stale = true;
    }, 'Link');
  }
  function soTodo(so) {
    sheet('Add a to-do for this order', esc(short(so)), `${fld('To-do', '<input type="text" name="tt" placeholder="What needs to happen?">')}<div class="cc-field"><span>Owners</span>${ownerChips()}</div>
      <div class="cc-row2">${fld('Due', '<input type="date" name="td">')}${fld('Priority', sel('tp', ['Medium', 'High', 'Low'], 'Medium'))}</div>${fld('Notes', '<textarea name="tn" rows="2"></textarea>')}`, async el => {
      const title = val(el, 'tt').trim(), own = checked(el); if (!title || !own.length) throw new Error('add a title and at least one owner');
      const doc = { doctype: 'ToDo', status: 'Open', allocated_to: own[0], priority: val(el, 'tp'), assigned_by: USER, reference_type: 'Sales Order', reference_name: so,
        description: `<p><b>${esc(title)}</b></p>${val(el, 'tn').trim() ? `<p>${esc(val(el, 'tn').trim())}</p>` : ''}<p>[ad-hoc] Owners: ${own.join(', ')}</p>` };
      if (val(el, 'td')) doc.date = val(el, 'td');
      await call('frappe.client.insert', { doc }); toast('To-do added · ' + own.length + ' notified');
    }, 'Add to-do');
  }
  function bindPipe() {
    root.querySelectorAll('[data-linkq]').forEach(b => b.onclick = () => linkQuote(b.dataset.linkq));
    root.querySelectorAll('[data-linkso]').forEach(b => b.onclick = () => linkSO(b.dataset.linkso));
    root.querySelectorAll('[data-sotodo]').forEach(b => b.onclick = () => soTodo(b.dataset.sotodo));
    root.querySelectorAll('[data-qdraft]').forEach(b => b.onchange = () => { S.qdraft = b.checked; render(); });
    const ch = $('#ch-pipe'); if (ch) { const ms = D.monthly; vbars(ch, ms.map(x => fmtM(x.month)), [{ name: 'Invoiced', color: '#2a78d6', values: ms.map(x => x.si) }], { fmt: kfmt, target: D.fin.goal, targetLabel: 'Target ' + kfmt(D.fin.goal), h: 220 }); }
  }

  /* ---------------- pipeline stages from the dealer portal (gateway action "stages") ----------------
     Design (projects, fixture schedules, drawing requests) → Quotes (quote requests, offers) →
     Sales orders (order requests) → … → Service (customer account requests). The fixture schedule's
     status is the spine, so each schedule shows on exactly one stage (furthest along wins). */
  const PL = { data: null, err: null, busy: false, at: 0 };
  const PL_VIEWS = ['pipeline', 'design', 'quotes', 'orders', 'service', 'inbox'];
  const plIsView = () => PL_VIEWS.includes(String(S.view).split('/')[0]) || String(S.view).startsWith('so-');
  const QR_ACTIVE = ['REQUESTED', 'UNDER_REVIEW', 'INFORMATION_NEEDED', 'ISSUED'];
  const DR_OPEN = ['Draft', 'Submitted', 'In Progress', 'Waiting on Customer'];
  const OI_OPEN = ['SUBMITTED', 'UNDER_REVIEW', 'INFORMATION_NEEDED', 'CHANGES_PROPOSED'];
  const AR_OPEN = ['Pending', 'Information needed'];
  // portal states are UPPER_CASE: show them as words, colour them by meaning (not by free text)
  const stLabel = s => { s = String(s || ''); return /^[A-Z_]+$/.test(s) ? s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, ' ') : s; };
  const ST_KIND = { DRAFT: 'mute', READY: 'info', QUOTED: 'info', ORDER_REQUESTED: 'info', ORDERED: 'good', ISSUE: 'bad', CLOSED: 'mute',
    REQUESTED: 'warn', UNDER_REVIEW: 'warn', INFORMATION_NEEDED: 'info', ISSUED: 'info', ACCEPTED: 'good', DECLINED: 'bad', REVISION_REQUESTED: 'warn', SUPERSEDED: 'mute', CANCELLED: 'mute',
    SUBMITTED: 'warn', CHANGES_PROPOSED: 'info', APPROVED: 'good', REJECTED: 'bad', WITHDRAWN: 'mute', COMPLETED: 'good',
    Draft: 'mute', Submitted: 'warn', 'In Progress': 'warn', 'Waiting on Customer': 'info', Completed: 'good', Closed: 'mute', Cancelled: 'mute',
    Pending: 'warn', 'Information needed': 'info', Approved: 'good', Rejected: 'bad', Resolved: 'good', CHANGES_REQUESTED: 'warn' };
  const stBadge = s => badge(stLabel(s), ST_KIND[s] || 'mute');
  const ageBd = d => d ? bdaysJS(String(d).slice(0, 10)) : 0;
  const ageB = (d, open = true) => { const n = ageBd(d); return open && n > 2 ? badge(n + 'd', 'bad') : `<span class="small">${n}d</span>`; };
  const plCanEdit = () => !!((PL.data && PL.data.can_edit) || (WB.cfg && WB.cfg.can_edit));
  const by = (rows, k) => { const o = {}; (rows || []).forEach(r => { const v = r[k]; if (v) (o[v] = o[v] || []).push(r); }); return o; };

  async function plLoad(force) {
    if (PL.busy || (!force && (PL.data || PL.err))) return;
    PL.busy = true;
    try { PL.data = plPrep(await gw('stages')); PL.err = null; } catch (e) { PL.err = e.message; }
    PL.busy = false; PL.at = Date.now();
    if (D && plIsView() && !$('#ccsheet2').classList.contains('on')) render();
  }
  function plPrep(x) {
    x.projBy = {}; x.projects.forEach(p => { x.projBy[p.name] = p; });
    x.schedBy = {}; x.schedules.forEach(s => { x.schedBy[s.name] = s; });
    x.reqBySched = by(x.doc_requests, 'fixture_schedule'); x.reqBySO = by(x.doc_requests, 'sales_order');
    x.revByReq = by(x.reviews, 'request');
    x.qrBySched = by(x.quote_requests, 'schedule'); x.qrBy = {}; x.quote_requests.forEach(q => { x.qrBy[q.name] = q; });
    x.offBySched = by(x.offers, 'schedule'); x.offByQR = by(x.offers, 'quote_request');
    x.oiBySched = by(x.intakes, 'schedule'); x.oiBySO = by(x.intakes, 'sales_order');
    x.tkBy = {}; x.tickets.forEach(t => { x.tkBy[t.name] = t; });
    x.tkBySched = by(x.tickets, 'ill_fixture_schedule');
    return x;
  }
  const tkL = t => (PL.data && PL.data.tkBy[t.name]) || {};
  const projName = n => { const p = PL.data && PL.data.projBy[n]; return p ? p.project_name || n : n; };
  const schedName = s => s ? (s.schedule_name || s.name) : '';
  const schedLink = n => { if (!n) return ''; const s = PL.data && PL.data.schedBy[n]; return `<a href="#design/${encodeURIComponent(n)}">${esc(s ? schedName(s) : n)}</a>`; };
  const userSel = (name, cur, blank = 'Unassigned') => `<select name="${name}"><option value="">${esc(blank)}</option>${TEAM.map(u => `<option value="${esc(u.name)}" ${u.name === cur ? 'selected' : ''}>${esc(u.full_name || u.name)}</option>`).join('')}</select>`;

  // which stage a schedule sits on right now (furthest along wins; earlier items show as chips)
  function schedStage(s) {
    const x = PL.data;
    if (s.status === 'CLOSED') return 'closed';
    if (['ORDER_REQUESTED', 'ORDERED'].includes(s.status) || s.sales_order || (x.oiBySched[s.name] || []).some(o => o.state !== 'WITHDRAWN' && o.state !== 'REJECTED')) return 'orders';
    if (s.status === 'QUOTED' || (x.qrBySched[s.name] || []).some(q => QR_ACTIVE.includes(q.state)) || (x.offBySched[s.name] || []).some(o => o.state === 'ISSUED' || o.state === 'ACCEPTED')) return 'quotes';
    return 'design';
  }
  const openReqs = n => ((PL.data.reqBySched[n] || []).filter(r => DR_OPEN.includes(r.status)));
  const lastReview = reqs => reqs.flatMap(r => PL.data.revByReq[r.name] || []).sort((a, b) => String(b.reviewed_on || b.creation).localeCompare(String(a.reviewed_on || a.creation)))[0];
  function designCol(s) {
    const all = PL.data.reqBySched[s.name] || [], open = openReqs(s.name);
    if (open.some(r => r.status !== 'Waiting on Customer')) return 'drawing';
    if (open.length) return 'waiting';
    const rv = lastReview(all), done = all.filter(r => r.status === 'Completed');
    if (s.status === 'ISSUE' || (rv && rv.decision === 'CHANGES_REQUESTED') || (done.length && !rv)) return 'review';
    return s.status === 'READY' ? 'ready' : 'drafting';
  }
  const slaBadge = r => { if (!r.sla_deadline || !DR_OPEN.includes(r.status)) return ''; const d = String(r.sla_deadline).slice(0, 10);
    return d < TODAY ? badge('SLA ' + fmtd(d), 'bad') : `<span class="small">SLA ${fmtd(d)}</span>`; };
  const tkCountPill = list => { const o = (list || []).filter(t => !DONE_TK.includes(t.status)); return (list || []).length ? `<span class="pill">✉ ${list.length} ticket${list.length > 1 ? 's' : ''}${o.length ? ' · ' + o.length + ' open' : ''}</span>` : ''; };
  const plCol = (title, sub, cards, k) => `<div class="bcol"><div class="lane-h"><span><span class="dot ${k}"></span> ${title}</span><span class="ct">${cards.length}</span></div>${sub ? `<div class="small" style="margin:-4px 0 10px">${sub}</div>` : ''}${cards.join('') || '<div class="drop-hint">Nothing here</div>'}</div>`;
  const plBoard = (cols, n) => `<div class="board" style="grid-template-columns:repeat(${n || cols.length},minmax(230px,1fr))">${cols.join('')}</div>`;
  const plNote = () => PL.busy && !PL.data ? '<div class="card empty"><span class="cc-spin"></span> Loading portal requests from ERPNext…</div>'
    : PL.err ? `<div class="callout"><div>Portal requests couldn't load from the Command Center gateway (${esc(PL.err)}). Showing what the older data feed has.</div></div>` : '';
  const sec = (title, sub, right = '') => `<div class="card-h" style="margin:28px 0 12px"><div><h2 style="font-size:17px">${title}</h2>${sub ? `<div class="sub">${sub}</div>` : ''}</div>${right}</div>`;
  // the older feed's request lane (used only when the gateway can't answer)
  const reqFallback = type => { const rs = (D.reqs || []).filter(r => r.type === type && rowOK(r)).sort((a, b) => b.open - a.open || b.age - a.age);
    return `<div class="lanes"><div class="lane"><div class="lane-h"><span>${esc(type)}s</span>${badge(rs.filter(r => r.open).length + ' open', 'info')}</div>
      ${rs.map(r => `<div class="kcard ${r.open ? '' : 'closed'}"><div class="r">${link(r.dt, r.name)}${r.open && r.age > 2 ? badge(r.age + 'd', 'bad') : `<span class="calc">${r.age}d</span>`}</div>
        <div style="margin-top:4px">${cust(r.customer)}</div><div class="m">${esc(r.state)}${r.detail ? ' · ' + esc(r.detail) : ''}</div>
        <div class="r" style="margin-top:8px">${r.owner ? avatar(r.owner) : '<span class="calc">Unassigned</span>'}<span class="calc">${fmtd(r.created)}</span></div></div>`).join('') || '<div class="empty">None</div>'}</div></div>`; };

  // generic help desk ticket card + 3-column board (Design, Quotes)
  const tkCard = t => { const td = D.byRef['HD Ticket|' + t.name] || [], l = tkL(t), q = (t.quotation || l.ill_quotation) && D.qByName[t.quotation || l.ill_quotation];
    return `<div class="tcard"><div class="r"><span class="badge ${t.type === 'Design' ? 'info' : 'mute'}">${esc(t.type === 'Quotation' ? 'Quote' : (t.type || 'Untyped'))}</span>${t.status === 'Open' && t.age > 2 ? badge(t.age + 'd', 'bad') : t.status === 'Replied' && t.idle > 10 ? badge(t.idle + 'd quiet', 'warn') : `<span class="small">${t.age}d</span>`}</div>
      <div class="tt" style="margin-top:8px"><a href="#" data-tksheet="${esc(t.name)}">${esc(t.subject || t.name)}</a></div><div class="m">${esc(t.raised_by || '')}</div>
      ${l.ill_fixture_schedule ? `<div class="qchip">Schedule ${schedLink(l.ill_fixture_schedule)}</div>` : ''}
      ${q ? `<div class="qchip">${link('quotation', q.name, short(q.name).replace('ilL-SAL-QTN-', ''))} · ${money(q.base_net_total)} · ${esc(q.docstatus === 0 ? 'Draft' : q.status)}</div>` : (t.type === 'Quotation' && LOGGED && !DONE_TK.includes(t.status) ? `<button class="cc-btn soft" style="margin-top:8px" data-linkq="${esc(t.name)}">Link quotation</button>` : '')}
      ${td.length ? `<div class="tdl">${td.slice(0, 3).map(x => `<div>☐ <a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a></div>`).join('')}${td.length > 3 ? `<div class="calc">+${td.length - 3} more</div>` : ''}</div>` : ''}
      <div class="r" style="margin-top:10px">${avs(t.assignedL)}<span class="small">${fmtd(t.created)}</span></div></div>`; };
  function tkBoard(list) {
    const since = addDays(TODAY, -30), tks = list.filter(t => rowOK(t) && (!DONE_TK.includes(t.status) || (t.modified || t.created) >= since));
    return plBoard([
      plCol('Our move', 'Open: needs a reply', tks.filter(t => t.status === 'Open').sort((a, b) => b.age - a.age).map(tkCard), 'bad'),
      plCol('Waiting on customer', 'Replied: follow up if quiet for 10+ days', tks.filter(t => t.status === 'Replied').sort((a, b) => b.idle - a.idle).map(tkCard), 'warn'),
      plCol('Done (last 30 days)', 'Resolved or closed', tks.filter(t => DONE_TK.includes(t.status)).map(tkCard), 'good')]);
  }

  // record actions shared by the lanes: reassign, details (Workbench sheet), to-do, open in ERPNext
  const recActs = (dt, name, opts = {}) => `<div class="pl-acts">${opts.assign && plCanEdit() ? `<button class="cc-btn soft" data-plassign="${esc(dt)}|${esc(name)}">Reassign</button>` : ''}<button class="cc-btn soft" data-pldetail="${esc(dt)}|${esc(name)}">Details</button>${LOGGED ? `<button class="cc-btn soft" data-pltodo="${esc(dt)}|${esc(name)}">+ To-do</button>` : ''}<a class="cc-btn soft" target="_blank" rel="noopener" href="${docUrl(dt, name)}" style="text-decoration:none">↗</a></div>`;
  function plReassign(dt, name) {
    const rows = PL.data ? [].concat(PL.data.doc_requests, PL.data.quote_requests) : [], r = rows.find(x => x.name === name) || {};
    sheet('Reassign ' + esc(wbLabel(dt).toLowerCase()), esc(name), fld('Assigned to', userSel('who', r.assigned_to)) + '<p class="small">Saved on the request in ERPNext, with a “Command Center:” note on its timeline.</p>', async el => {
      const v = val(el, 'who') || null; if ((v || null) === (r.assigned_to || null)) throw new Error('pick someone else');
      await gw('save', { dt, name, values: { assigned_to: v } }); toast(`${esc(name)} ${v ? 'assigned to ' + esc(SHORT[v] || v) : 'unassigned'}`); PL.data = null;
    }, 'Save');
  }
  function refTodo(dt, name) {
    sheet('Add a to-do', `${esc(wbLabel(dt))} ${esc(name)}`, `${fld('To-do', '<input type="text" name="tt" placeholder="What needs to happen?">')}<div class="cc-field"><span>Owners</span>${ownerChips()}</div>
      <div class="cc-row2">${fld('Due', '<input type="date" name="td">')}${fld('Priority', sel('tp', ['Medium', 'High', 'Low'], 'Medium'))}</div>${fld('Notes', '<textarea name="tn" rows="2"></textarea>')}`, async el => {
      const title = val(el, 'tt').trim(), own = checked(el); if (!title || !own.length) throw new Error('add a title and at least one owner');
      const doc = { doctype: 'ToDo', status: 'Open', allocated_to: own[0], priority: val(el, 'tp'), assigned_by: USER, reference_type: dt, reference_name: name,
        description: `<p><b>${esc(title)}</b></p>${val(el, 'tn').trim() ? `<p>${esc(val(el, 'tn').trim())}</p>` : ''}<p>[ad-hoc] Owners: ${own.join(', ')}</p>` };
      if (val(el, 'td')) doc.date = val(el, 'td');
      await call('frappe.client.insert', { doc }); toast('To-do added · ' + own.length + ' notified');
    }, 'Add to-do');
  }
  async function plDetail(dt, name) { if (!WB.cfg) { try { WB.cfg = await gw('config'); } catch (e) { toast('Could not open: ' + esc(e.message)); return; } } if (!WB.cfg.doctypes[dt]) { window.open(docUrl(dt, name), '_blank'); return; } wbOpen(dt, name); }
  function bindStages() {
    root.querySelectorAll('[data-plassign]').forEach(b => b.onclick = e => { e.preventDefault(); const [dt, n] = b.dataset.plassign.split('|'); plReassign(dt, n); });
    root.querySelectorAll('[data-pldetail]').forEach(b => b.onclick = e => { e.preventDefault(); const [dt, n] = b.dataset.pldetail.split('|'); plDetail(dt, n); });
    root.querySelectorAll('[data-pltodo]').forEach(b => b.onclick = e => { e.preventDefault(); const [dt, n] = b.dataset.pltodo.split('|'); refTodo(dt, n); });
    root.querySelectorAll('[data-tksheet]').forEach(b => b.onclick = e => { e.preventDefault(); tkSheet(b.dataset.tksheet); });
    root.querySelectorAll('[data-ibf]').forEach(el => el.onchange = () => { IB[el.dataset.ibf] = el.value; render(); });
    root.querySelectorAll('[data-ibmode]').forEach(b => b.onclick = () => { IB.mode = b.dataset.ibmode; render(); });
    root.querySelectorAll('[data-ibroute]').forEach(f => f.onsubmit = e => { e.preventDefault(); ibRoute(f); });
  }

  /* ---- Design ---- */
  const drRow = r => { const open = DR_OPEN.includes(r.status), s = r.fixture_schedule && PL.data.schedBy[r.fixture_schedule];
    return `<tr><td>${link('ill-document-request', r.name)}<div class="m">${esc(r.request_type || 'Request')}${r.fixture_or_product_text ? ' · ' + esc(r.fixture_or_product_text) : ''}</div></td>
      <td>${cust(r.requester_customer || r.owner_customer)}</td>
      <td>${r.fixture_schedule ? schedLink(r.fixture_schedule) : ''}${r.sales_order ? `<div class="m">Order <a href="#so-${encodeURIComponent(r.sales_order)}">${esc(short(r.sales_order))}</a></div>` : ''}${r.project ? `<div class="m">${esc(projName(r.project))}</div>` : (s && s.ill_project ? `<div class="m">${esc(projName(s.ill_project))}</div>` : '')}</td>
      <td>${stBadge(r.status)}${r.priority && r.priority !== 'Normal' ? ' ' + badge(r.priority, 'bad') : ''}${r.required_for_manufacturing ? '<div class="m">Needed for manufacturing</div>' : ''}</td>
      <td>${r.assigned_to ? avatar(r.assigned_to) + ' <span class="small">' + esc(SHORT[r.assigned_to] || r.assigned_to) + '</span>' : '<span class="calc">Unassigned</span>'}</td>
      <td style="white-space:nowrap">${slaBadge(r) || (r.requested_due_date ? '<span class="small">Due ' + fmtd(r.requested_due_date) + '</span>' : '')}</td><td class="num">${ageB(r.creation, open)}</td>
      <td class="num">${recActs('ilL-Document-Request', r.name, { assign: open })}</td></tr>`; };
  const DR_HEAD = ['Request', 'Dealer', 'Schedule / project', 'Status', 'Assigned', 'SLA / due', '#Age', ''];
  function schedCard(s) {
    const x = PL.data, p = x.projBy[s.ill_project] || {}, open = openReqs(s.name), r = open[0] || (x.reqBySched[s.name] || [])[0], tks = x.tkBySched[s.name] || [];
    const parties = [['Architect', p.architect], ['Lighting designer', p.lighting_designer], ['GC', p.general_contractor]].filter(a => a[1]).map(a => a[0] + ': ' + esc(a[1])).join(' · ');
    const rv = lastReview(x.reqBySched[s.name] || []);
    return `<a class="tcard" style="display:block;color:inherit;text-decoration:none" href="#design/${encodeURIComponent(s.name)}">
      <div class="r">${stBadge(s.status)}${r && DR_OPEN.includes(r.status) ? ageB(r.creation) : `<span class="small">${fmtd(s.modified)}</span>`}</div>
      <div class="tt" style="margin-top:8px">${esc(schedName(s))}</div>
      <div class="m">${s.ill_project ? '<b style="font-weight:500;color:var(--ink2)">' + esc(p.project_name || s.ill_project) + '</b> · ' : ''}${esc(s.customer || p.customer || '')}</div>
      ${parties ? `<div class="m">${parties}</div>` : ''}${p.location ? `<div class="m">${esc(String(p.location).slice(0, 80))}</div>` : ''}
      <div class="m">v${esc(s.version || 1)}${s.is_locked ? ' · 🔒 locked' : ''} · ${s.lines || 0} line${s.lines === 1 ? '' : 's'}</div>
      ${r ? `<div class="qchip">Drawing ${esc(r.name)} · ${esc(stLabel(r.status))}${r.sla_deadline && DR_OPEN.includes(r.status) && String(r.sla_deadline).slice(0, 10) < TODAY ? ' · <b style="color:var(--badt)">past SLA</b>' : ''}</div>` : ''}
      ${rv ? `<div class="m" style="margin-top:6px">Review ${esc(rv.revision || '')}: ${stBadge(rv.decision)}</div>` : ''}
      <div class="r" style="margin-top:10px">${r && r.assigned_to ? avatar(r.assigned_to) : '<span class="calc">No drawing owner</span>'}${tkCountPill(tks)}</div></a>`;
  }
  V.design = m => {
    const head = header('Design', 'Fixture schedules, projects and drawing requests from the dealer portal. A schedule moves on to Quotes once the dealer asks for a quote.');
    if (!PL.data) return head + (plNote() || '<div class="card empty">Loading…</div>') + (PL.err ? reqFallback('Drawing Request') + sec('Design tickets', 'Design-type help desk tickets from sales@') + tkBoard(D.tk.filter(t => t.type === 'Design')) : '');
    const x = PL.data, sch = x.schedules.filter(s => schedStage(s) === 'design' && rowOK({ s, p: x.projBy[s.ill_project] }));
    const cols = { drafting: [], ready: [], drawing: [], waiting: [], review: [] }; sch.forEach(s => cols[designCol(s)].push(s));
    const openDR = x.doc_requests.filter(r => DR_OPEN.includes(r.status)), general = x.doc_requests.filter(r => !r.sales_order && rowOK(r));
    const pastSLA = openDR.filter(r => r.sla_deadline && String(r.sla_deadline).slice(0, 10) < TODAY && r.status !== 'Waiting on Customer');
    const designTk = D.tk.filter(t => t.type === 'Design');
    return head + plNote() + `<div class="grid" style="margin-bottom:20px">
        ${stat('Active projects', x.projects.filter(p => p.status === 'ACTIVE').length, `${x.projects.filter(p => p.status === 'ON_HOLD').length} on hold`).replace('card stat', 'card stat s3')}
        ${stat('Schedules in design', sch.length, `${cols.drafting.length} drafting · ${cols.ready.length} ready for quote`).replace('card stat', 'card stat s3')}
        ${stat('Open drawing requests', openDR.length, `${openDR.filter(r => r.status === 'Waiting on Customer').length} waiting on customer`).replace('card stat', 'card stat s3')}
        ${stat('Drawings past SLA', pastSLA.length, 'Submitted or in progress', pastSLA.length ? 'bad' : '').replace('card stat', 'card stat s3')}
      </div>
      ${plBoard([
        plCol('Drafting', 'Dealer is building the schedule', cols.drafting.map(schedCard), 'mute'),
        plCol('Ready for quote', 'Ready, no quote request yet', cols.ready.map(schedCard), 'info'),
        plCol('Drawing in progress', 'Open drawing request on our side', cols.drawing.map(schedCard), 'bad'),
        plCol('Waiting on customer', 'We asked the dealer for something', cols.waiting.map(schedCard), 'warn'),
        plCol('Review', 'Changes requested, issue, or just delivered', cols.review.map(schedCard), 'good')], 5)}
      ${sec('Drawing & document requests', `General requests from the portal. ${x.doc_requests.length - general.length ? `${x.doc_requests.filter(r => r.sales_order).length} tied to sales orders are on <a href="#orders">Sales orders</a>. ` : ''}Red age = open more than 2 business days.`)}
      <div class="grid">${tableCard('Open and recent requests', 'Open first, oldest first', DR_HEAD, general.sort((a, b) => (DR_OPEN.includes(b.status) - DR_OPEN.includes(a.status)) || String(a.creation).localeCompare(String(b.creation))).map(drRow))}</div>
      ${sec('Design tickets', 'Design-type help desk tickets from sales@')}${tkBoard(designTk)}`;
  };

  /* ---- Design drill-down: #design/<schedule> ---- */
  const DS = { name: null, doc: null, err: null, busy: false };
  async function dsLoad(name) {
    if (DS.busy) return; DS.busy = true; DS.err = null;
    try { DS.doc = (await gw('get', { dt: 'ilL-Project-Fixture-Schedule', name })).doc; DS.name = name; } catch (e) { DS.err = e.message; DS.name = name; DS.doc = null; }
    DS.busy = false; if (String(S.view).startsWith('design/')) render();
  }
  V.designSched = (m, id) => {
    const back = `<a href="#design" class="small" style="display:inline-block;margin-bottom:10px">← Design</a>`;
    if (DS.name !== id && !DS.busy) { DS.doc = null; setTimeout(() => dsLoad(id)); }
    const x = PL.data, s = (x && x.schedBy[id]) || DS.doc;
    if (!s) return back + header(esc(id), DS.err ? 'Couldn\'t load this schedule: ' + esc(DS.err) : 'Loading…');
    const p = (x && x.projBy[s.ill_project]) || {}, reqs = (x && x.reqBySched[id]) || [], qrs = (x && x.qrBySched[id]) || [], offs = (x && x.offBySched[id]) || [], ois = (x && x.oiBySched[id]) || [], tks = (x && x.tkBySched[id]) || [];
    const stage = x ? schedStage(s) : 'design', lines = (DS.name === id && DS.doc && DS.doc.lines) || [];
    const reviews = reqs.flatMap(r => (x.revByReq[r.name] || []).map(v => ({ ...v, req: r.name })));
    const kv = (k, v) => v ? `<div class="wb-kv"><span>${k}</span><b>${v}</b></div>` : '';
    return back + header(esc(schedName(s)), `${esc(s.name)} · ${cust(s.customer || p.customer)} · ${stBadge(s.status)} · v${esc(s.version || 1)}${s.is_locked ? ' · 🔒 locked' : ''}`,
      `<div class="toolbar">${stage !== 'design' && stage !== 'closed' ? `<a class="cc-btn soft" href="#${stage}" style="text-decoration:none">Now on ${esc(STAGES.find(z => z.k === stage).n)} →</a>` : ''}${LOGGED ? `<button class="cc-btn soft" data-pltodo="ilL-Project-Fixture-Schedule|${esc(id)}">+ To-do</button>` : ''}<button class="cc-btn soft" data-pldetail="ilL-Project-Fixture-Schedule|${esc(id)}">Details</button><a class="cc-btn soft" target="_blank" rel="noopener" href="${docUrl('ilL-Project-Fixture-Schedule', id)}" style="text-decoration:none">Open in ERPNext</a></div>`) + `
      <div class="grid">
        ${card('Project', s.ill_project ? link('ill-project', s.ill_project, p.project_name || s.ill_project) : 'No project', `<div class="wb-kvs">${kv('Dealer', cust(p.customer || s.customer))}${kv('Status', p.status ? stBadge(p.status) : '')}${kv('Architect', esc(p.architect || ''))}${kv('Lighting designer', esc(p.lighting_designer || ''))}${kv('General contractor', esc(p.general_contractor || ''))}${kv('Location', esc(p.location || ''))}${kv('Start', p.estimated_start_date ? fmtd(p.estimated_start_date) : '')}${kv('ERPNext project', p.erp_project ? link('project', p.erp_project) : '')}</div>`, 's4')}
        ${card('Where it is', 'Earlier and later steps for this schedule', `<div class="small" style="line-height:1.9">
          Drawing requests: ${reqs.map(r => `${link('ill-document-request', r.name)} ${stBadge(r.status)}`).join(' ') || '—'}<br>
          Quote requests: ${qrs.map(q => `${link('ill-quote-request', q.name)} ${stBadge(q.state)}`).join(' ') || '—'}<br>
          Offers: ${offs.map(o => `${link('ill-quote-offer', o.name)} ${stBadge(o.state)}${o.quotation ? ' ' + link('quotation', o.quotation, short(o.quotation).replace('ilL-SAL-QTN-', '')) : ''}`).join(' ') || '—'}<br>
          Order requests: ${ois.map(o => `${link('ill-order-intake', o.name)} ${stBadge(o.state)}`).join(' ') || '—'}<br>
          Sales order: ${s.sales_order ? `<a href="#so-${encodeURIComponent(s.sales_order)}">${esc(short(s.sales_order))}</a>` : '—'}<br>
          Tickets: ${tks.map(t => `<a href="#" data-tksheet="${esc(t.name)}">${esc(t.name)}</a> ${esc(t.status || '')}`).join(', ') || '—'}</div>`, 's4')}
        ${card('Drawing reviews', 'Dealer decisions on delivered drawings', reviews.length ? reviews.map(v => `<div class="todo-r"><span>${stBadge(v.decision)}</span><span>${esc(v.req)} rev ${esc(v.revision || '')}${v.note ? ' · ' + esc(v.note) : ''}</span><span class="small">${fmtd(v.reviewed_on || v.creation)}</span></div>`).join('') : '<div class="empty" style="padding:8px">No reviews yet</div>', 's4')}
        ${tableCard('Fixture schedule lines', DS.busy ? 'Loading…' : `${lines.length} line${lines.length === 1 ? '' : 's'} · read-only here`, ['Line', '#Qty', 'Location', 'Product', 'Configured', 'Status'],
          lines.map(l => `<tr><td>${esc(l.line_id || l.idx)}</td><td class="num">${esc(l.qty)}</td><td>${esc(l.location || '')}</td><td>${esc(l.manufacturer_type || '')}${l.manufacturer_name ? '<div class="m">' + esc(l.manufacturer_name) + (l.fixture_model_number ? ' ' + esc(l.fixture_model_number) : '') + '</div>' : ''}</td>
            <td>${esc(l.ill_item_code || l.configured_fixture || l.configured_tape_neon || l.configured_led_sheet || l.accessory_item || '')}</td><td>${l.configuration_status ? badge(l.configuration_status, wbKind(l.configuration_status)) : ''}</td></tr>`), '', 's12')}
        ${x ? tableCard('Drawing & document requests', '', DR_HEAD, reqs.map(drRow), '', 's12') : ''}
      </div>`;
  };

  /* ---- Quotes: quote requests → offers → quotations ---- */
  function qrCard(q) {
    const x = PL.data, off = (x.offByQR[q.name] || []).sort((a, b) => String(b.creation).localeCompare(String(a.creation)))[0], qn = (off && off.quotation) || q.latest_offer, qt = qn && D.qByName[qn];
    const wait = q.state === 'ISSUED' || q.state === 'INFORMATION_NEEDED';
    return `<div class="tcard"><div class="r">${stBadge(q.state)}${ageB(q.modified || q.creation, !wait)}</div>
      <div class="tt" style="margin-top:8px">${link('ill-quote-request', q.name)} · ${esc(q.customer || '')}</div>
      ${q.schedule ? `<div class="m">Schedule ${schedLink(q.schedule)}${q.project ? ' · ' + esc(projName(q.project)) : ''}</div>` : ''}
      ${qn ? `<div class="qchip">${link('quotation', qn, short(qn).replace('ilL-SAL-QTN-', ''))}${qt ? ' · ' + money(qt.base_net_total) : ''}${off && off.valid_until ? ' · valid to ' + fmtd(off.valid_until) : ''}</div>` : ''}
      ${q.due_date ? `<div class="m" style="margin-top:6px">Due ${String(q.due_date).slice(0, 10) < TODAY && !wait ? badge(fmtd(q.due_date), 'bad') : fmtd(q.due_date)}</div>` : ''}
      <div class="r" style="margin-top:10px">${q.assigned_to ? avatar(q.assigned_to) : '<span class="calc">Unassigned</span>'}</div>${recActs('ilL-Quote-Request', q.name, { assign: QR_ACTIVE.includes(q.state) })}</div>`;
  }
  function offerCard(o) {
    const x = PL.data, oi = (o.schedule && (x.oiBySched[o.schedule] || [])[0]) || (o.sales_order && (x.oiBySO[o.sales_order] || [])[0]), qt = o.quotation && D.qByName[o.quotation];
    return `<div class="tcard"><div class="r">${stBadge(o.state)}<span class="small">${fmtd(o.responded_on || o.modified)}</span></div>
      <div class="tt" style="margin-top:8px">${link('ill-quote-offer', o.name)} · ${esc(o.customer || '')}</div>
      ${o.schedule ? `<div class="m">Schedule ${schedLink(o.schedule)}</div>` : ''}${o.response_note ? `<div class="m">“${esc(String(o.response_note).slice(0, 140))}”</div>` : ''}
      ${o.quotation ? `<div class="qchip">${link('quotation', o.quotation, short(o.quotation).replace('ilL-SAL-QTN-', ''))}${qt ? ' · ' + money(qt.base_net_total) : ''}</div>` : ''}
      ${o.state === 'ACCEPTED' ? `<div class="qchip" style="background:var(--goodb,#ecfdf3);color:var(--goodt,#067647)">Continues in <a href="#orders">Sales orders</a>${oi ? ' · ' + esc(oi.name) + ' ' + esc(stLabel(oi.state)) : o.sales_order ? ' · ' + esc(short(o.sales_order)) : ''}</div>` : ''}</div>`;
  }
  function quoteLanes() {
    if (!PL.data) return plNote() + (PL.err ? reqFallback('Quote Request') : '');
    const x = PL.data, qr = x.quote_requests.filter(q => QR_ACTIVE.includes(q.state) && rowOK(q)), st = s => qr.filter(q => q.state === s).sort((a, b) => String(a.creation).localeCompare(String(b.creation)));
    const since = addDays(TODAY, -30), outc = x.offers.filter(o => ['ACCEPTED', 'DECLINED', 'REVISION_REQUESTED'].includes(o.state) && String(o.responded_on || o.modified) >= since && rowOK(o));
    return plBoard([
      plCol('Requested', 'New from the portal', st('REQUESTED').map(qrCard), 'bad'),
      plCol('Under review', 'We\'re pricing it', st('UNDER_REVIEW').map(qrCard), 'warn'),
      plCol('Information needed', 'Waiting on the dealer', st('INFORMATION_NEEDED').map(qrCard), 'info'),
      plCol('Issued', 'Quote out, waiting on the dealer', st('ISSUED').map(qrCard), 'info'),
      plCol('Dealer responded', 'Accepted, declined or revision asked (30 days)', outc.sort((a, b) => String(b.responded_on || b.modified).localeCompare(String(a.responded_on || a.modified))).map(offerCard), 'good')], 5);
  }

  /* ---- Sales orders: order requests (intake) + drawing requests tied to orders ---- */
  function oiCard(o) {
    const s = o.sales_order && D.ship.find(z => z.so === o.sales_order), wait = o.state === 'INFORMATION_NEEDED' || o.state === 'CHANGES_PROPOSED';
    return `<div class="tcard"><div class="r">${stBadge(o.state)}${ageB(o.creation, OI_OPEN.includes(o.state) && !wait)}</div>
      <div class="tt" style="margin-top:8px">${link('ill-order-intake', o.name)} · ${esc(o.customer || '')}</div>
      ${o.schedule ? `<div class="m">Schedule ${schedLink(o.schedule)}</div>` : ''}${o.customer_message ? `<div class="m">“${esc(String(o.customer_message).slice(0, 140))}”</div>` : ''}
      ${o.sales_order ? `<div class="qchip">Order ${s ? `<a href="#so-${encodeURIComponent(o.sales_order)}">${esc(short(o.sales_order))}</a> · ${money(s.value)}` : link('sales-order', o.sales_order, short(o.sales_order))}</div>` : ''}
      ${o.due_date ? `<div class="m" style="margin-top:6px">Due ${fmtd(o.due_date)}</div>` : ''}
      <div class="r" style="margin-top:10px">${o.assigned_to ? avatar(o.assigned_to) : '<span class="calc">Unassigned</span>'}</div>${recActs('ilL-Order-Intake', o.name)}</div>`;
  }
  function orderLanes() {
    if (!PL.data) return plNote() + (PL.err ? reqFallback('Sales Order Request') : '');
    const x = PL.data, oi = x.intakes.filter(rowOK), st = s => oi.filter(o => o.state === s).sort((a, b) => String(a.creation).localeCompare(String(b.creation)));
    const soDR = x.doc_requests.filter(r => r.sales_order && rowOK(r));
    return sec('Order requests', 'Dealers asking to turn a quoted schedule into an order (portal intake). Approved ones show for 30 days.') + plBoard([
      plCol('Submitted', 'New from the portal', st('SUBMITTED').map(oiCard), 'bad'),
      plCol('Under review', '', st('UNDER_REVIEW').map(oiCard), 'warn'),
      plCol('Information needed', 'Waiting on the dealer', st('INFORMATION_NEEDED').map(oiCard), 'info'),
      plCol('Changes proposed', 'Waiting on the dealer to accept', st('CHANGES_PROPOSED').map(oiCard), 'info'),
      plCol('Approved', 'Last 30 days', st('APPROVED').map(oiCard), 'good')], 5)
      + (soDR.length ? `<div class="grid" style="margin-top:20px">${tableCard('Drawing requests tied to sales orders', 'Manufacturing sign-off and other drawings for orders', DR_HEAD, soDR.sort((a, b) => (DR_OPEN.includes(b.status) - DR_OPEN.includes(a.status)) || String(a.creation).localeCompare(String(b.creation))).map(drRow))}</div>` : '');
  }

  /* ---- Service: customer account requests ---- */
  function arCard(a) {
    return `<div class="tcard"><div class="r"><span class="badge info">${esc(a.request_type || 'Request')}</span>${ageB(a.creation, a.state === 'Pending')}</div>
      <div class="tt" style="margin-top:8px">${a.customer ? cust(a.customer) : esc(a.requested_by || '—')}</div><div class="m">${esc(a.requested_by || '')} · ${stBadge(a.state)}</div>
      ${a.staff_note ? `<div class="m">${esc(String(a.staff_note).slice(0, 140))}</div>` : ''}
      <div class="r" style="margin-top:10px">${a.assigned_to ? avatar(a.assigned_to) : '<span class="calc">Unassigned</span>'}</div>${recActs('ilL-Account-Request', a.name)}</div>`;
  }
  function accountLanes() {
    if (!PL.data) return plNote() + (PL.err ? reqFallback('Account Request') : '');
    const ar = PL.data.account_requests.filter(rowOK), st = s => ar.filter(a => s.includes(a.state)).sort((a, b) => String(a.creation).localeCompare(String(b.creation)));
    return sec('Customer requests', 'Dealer applications, address, contact and profile changes from the portal. Red age = pending more than 2 business days.') + plBoard([
      plCol('Pending', 'Our move', st(['Pending']).map(arCard), 'bad'),
      plCol('Information needed', 'Waiting on the dealer', st(['Information needed']).map(arCard), 'warn'),
      plCol('Done (last 30 days)', 'Approved, rejected or resolved', st(['Approved', 'Rejected', 'Resolved']).map(arCard), 'good')]);
  }

  /* ---------------- Inbox: help desk portal ----------------
     Triage, reassign, link records and change status/priority/type here; replies are written in Helpdesk. */
  const IB = { mode: 'triage', status: 'open', type: '', who: '', linked: '', sort: 'age' };
  const TK_TYPES = () => [...new Set(['Quotation', 'Design', 'Sales Order', 'Service', 'Issue'].concat(D.tk.map(t => t.type).filter(Boolean)))];
  function tkStage(t) {
    const l = tkL(t), s = l.ill_fixture_schedule && PL.data && PL.data.schedBy[l.ill_fixture_schedule];
    if (s) { const st = schedStage(s); if (st !== 'closed') return st; }
    if (t.sales_order || l.ill_sales_order || t.type === 'Sales Order') return 'orders';
    if (t.quotation || l.ill_quotation || t.type === 'Quotation') return 'quotes';
    if (t.type === 'Design' || l.ill_project) return 'design';
    return 'service';
  }
  const tkLinks = t => { const l = tkL(t), out = [];
    if (l.ill_project) out.push(`<span class="pill">Project ${esc(projName(l.ill_project))}</span>`);
    if (l.ill_fixture_schedule) out.push(`<span class="pill">${schedLink(l.ill_fixture_schedule)}</span>`);
    const q = t.quotation || l.ill_quotation; if (q) out.push(`<span class="pill">${link('quotation', q, short(q).replace('ilL-SAL-QTN-', 'Quote '))}</span>`);
    const so = t.sales_order || l.ill_sales_order; if (so) out.push(`<span class="pill"><a href="#so-${encodeURIComponent(so)}">Order ${esc(short(so))}</a></span>`);
    return out.join(' '); };
  const tkLinked = t => { const l = tkL(t); return !!(t.quotation || t.sales_order || l.ill_quotation || l.ill_sales_order || l.ill_project || l.ill_fixture_schedule); };
  const replyBtn = t => `<a class="cc-btn ${t.status === 'Open' ? 'primary' : 'soft'}" target="_blank" rel="noopener" href="/helpdesk/tickets/${encodeURIComponent(t.name)}" style="text-decoration:none">Reply in Helpdesk</a>`;
  function ibRows(list) {
    return list.map(t => { const stg = tkStage(t), sn = (STAGES.find(z => z.k === stg) || {}).n;
      return `<tr><td style="max-width:380px"><a href="#" data-tksheet="${esc(t.name)}" style="color:var(--ink);font-weight:500">${esc(t.subject || t.name)}</a><div class="m">${esc(t.name)}${t.raised_by ? ' · ' + esc(t.raised_by) : ''}</div></td>
        <td>${esc(t.type || '—')}${tkL(t).priority ? `<div class="m">${esc(tkL(t).priority)}</div>` : ''}</td><td>${t.status === 'Open' ? sdot('Open', 'warn') : t.status === 'Replied' ? sdot('Replied', 'mute') : sdot(t.status, 'good')}</td>
        <td>${avs(t.assignedL)}</td><td><a class="pill" href="#${stg}">${esc(sn)}</a> ${tkLinks(t)}</td>
        <td class="num">${(t.status === 'Open' && t.age > 2) || (t.status === 'Replied' && t.idle > 10) ? badge(t.age + 'd', 'bad') : t.age + 'd'}</td>
        <td class="num" style="white-space:nowrap"><button class="cc-btn soft" data-tksheet="${esc(t.name)}">Manage</button> ${replyBtn(t)}</td></tr>`; });
  }
  const IB_HEAD = ['Ticket', 'Type', 'Status', 'Owners', 'Stage / links', '#Age', ''];
  V.inbox = m => {
    const CAT = { Quotation: 'Quotes', Service: 'Tech support', 'Sales Order': 'Order status', Design: 'Design' }, cats = ['Quotes', 'Tech support', 'Order status', 'Design', 'Other'];
    const cnt = arr => cats.map(c => arr.filter(t => (CAT[t.type] || 'Other') === c).length);
    const live = D.tk.filter(t => t.status === 'Open' || t.status === 'Replied');
    const unrouted = live.filter(t => !t.assignedL.length || !t.type), needs = live.filter(t => t.status === 'Open');
    const opt = (v, l, cur) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(l)}</option>`;
    const seg = `<div class="seg">${[['triage', 'All tickets', live.length], ['reply', 'Needs a reply', needs.length], ['routing', 'Routing', unrouted.length]].map(([k, l, n]) => `<button data-ibmode="${k}" class="${IB.mode === k ? 'on' : ''}">${l} <span class="calc">${n}</span></button>`).join('')}</div>`;
    let body;
    if (IB.mode === 'reply') {
      body = tableCard('Needs a reply', 'Open tickets: the customer wrote last (Helpdesk marks a ticket Open when they do). Oldest first. Write the reply in Helpdesk.', IB_HEAD, ibRows(needs.filter(rowOK).sort((a, b) => b.age - a.age)));
    } else if (IB.mode === 'routing') {
      const ed = plCanEdit();
      body = tableCard('Unassigned or untyped', ed ? 'Give each one a type and an owner so nothing sits unowned.' : 'View only: the Command Center Editor role is needed to route tickets.', ['Ticket', 'Status', '#Age', 'Type', 'Owner', ''],
        unrouted.filter(rowOK).sort((a, b) => b.age - a.age).map(t => `<tr><td style="max-width:380px"><a href="#" data-tksheet="${esc(t.name)}" style="color:var(--ink);font-weight:500">${esc(t.subject || t.name)}</a><div class="m">${esc(t.name)}${t.raised_by ? ' · ' + esc(t.raised_by) : ''}</div></td>
          <td>${esc(t.status)}</td><td class="num">${t.age}d</td>
          <td colspan="3">${ed ? `<form class="ib-route" data-ibroute="${esc(t.name)}"><select name="type">${opt('', '— type —', t.type || '')}${TK_TYPES().map(k => opt(k, k, t.type || '')).join('')}</select>${userSel('who', t.assignedL[0], '— owner —')}<button class="cc-btn primary" type="submit">Save</button></form>` : `${esc(t.type || '—')} · ${avs(t.assignedL)}`}</td></tr>`));
    } else {
      let list = D.tk.filter(t => IB.status === 'open' ? (t.status === 'Open' || t.status === 'Replied') : IB.status === 'all' ? true : t.status === IB.status);
      if (IB.type) list = list.filter(t => (t.type || '') === (IB.type === '(none)' ? '' : IB.type));
      if (IB.who) list = list.filter(t => IB.who === '(none)' ? !t.assignedL.length : t.assignedL.includes(IB.who));
      if (IB.linked) list = list.filter(t => IB.linked === 'yes' ? tkLinked(t) : !tkLinked(t));
      list = list.filter(rowOK).sort((a, b) => IB.sort === 'new' ? String(b.created).localeCompare(String(a.created)) : b.age - a.age);
      const tools = `<div class="toolbar ib-f s12">
        <select data-ibf="status">${[['open', 'Open + replied'], ['Open', 'Open'], ['Replied', 'Replied'], ['Resolved', 'Resolved'], ['Closed', 'Closed'], ['all', 'Any status']].map(([v, l]) => opt(v, l, IB.status)).join('')}</select>
        <select data-ibf="type">${opt('', 'All types', IB.type)}${TK_TYPES().map(k => opt(k, k, IB.type)).join('')}${opt('(none)', 'No type', IB.type)}</select>
        <select data-ibf="who">${opt('', 'Anyone', IB.who)}${opt('(none)', 'Unassigned', IB.who)}${TEAM.map(u => opt(u.name, u.full_name || u.name, IB.who)).join('')}</select>
        <select data-ibf="linked">${opt('', 'Linked or not', IB.linked)}${opt('yes', 'Linked to a record', IB.linked)}${opt('no', 'Not linked', IB.linked)}</select>
        <select data-ibf="sort">${opt('age', 'Oldest first', IB.sort)}${opt('new', 'Newest first', IB.sort)}</select></div>`;
      body = tools + tableCard('Tickets', `${list.length} matching. Manage reassigns, links and changes status here; replies are written in Helpdesk.`, IB_HEAD, ibRows(list.slice(0, 200)));
    }
    setTimeout(() => vbars($('#ch-inbox'), cats, [{ name: 'This week', color: '#2a78d6', values: cnt(m.tw) }, { name: 'Last week', color: '#eb6834', values: cnt(m.lw) }], { labels: true, h: 200 }));
    return header('Inbox (sales@)', 'The help desk, managed from here: triage, reassign, link quotes, orders, projects and schedules, change status. Anything that needs a written reply opens in Helpdesk.', seg) + `<div class="grid" style="margin-bottom:20px">
      ${stat('Needs a reply', needs.length, `${m.tOld.length} waiting over 2 business days`, m.tOld.length ? 'bad' : '').replace('card stat', 'card stat s3')}
      ${stat('Waiting on customer', live.length - needs.length, 'Replied').replace('card stat', 'card stat s3')}
      ${stat('Unassigned or untyped', unrouted.length, 'See Routing', unrouted.length ? 'warn' : '').replace('card stat', 'card stat s3')}
      ${stat('Tickets this week', m.tw.length, `Last week ${m.lw.length}`).replace('card stat', 'card stat s3')}
      </div>${PL.err ? plNote() : ''}<div class="grid">${body}${card('Tickets by type', 'Created in the last 7 days vs the 7 before', '<div class="chart" id="ch-inbox"></div>', 's12')}</div>`;
  };
  async function ibRoute(f) {
    const name = f.dataset.ibroute, t = D.tk.find(x => x.name === name); if (!t) return;
    const type = f.elements.type.value, who = f.elements.who.value, b = f.querySelector('button'); b.disabled = true; b.textContent = '…';
    try {
      if (type && type !== (t.type || '')) await gw('save', { dt: 'HD Ticket', name, values: { ticket_type: type } });
      if (who && !t.assignedL.includes(who)) await gw('assign', { dt: 'HD Ticket', name, add: [who], remove: [] });
      toast('Ticket ' + esc(name) + ' routed'); await load();
    } catch (e) { toast('Not saved: ' + esc(e.message)); b.disabled = false; b.textContent = 'Save'; }
  }
  // ticket side sheet: details, owners, links, status/priority/type, recent Command Center changes
  async function tkSheet(name) {
    const t = D.tk.find(x => x.name === name) || { name, assignedL: [] };
    const el = sheet(esc(t.subject || name), esc(name), '<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>', null);
    let g, meta;
    try { [g, meta] = await Promise.all([gw('get', { dt: 'HD Ticket', name }), wbMeta('HD Ticket')]); }
    catch (e) { el.querySelector('#sform').innerHTML = `<p class="cc-msg">Couldn't open ${esc(name)}: ${esc(e.message)}</p><div class="cc-sheet-f">${replyBtn(t)}</div>`; return; }
    const doc = g.doc, wf = {}; (meta.fields || []).forEach(f => { wf[f.fieldname] = f; });
    const ed = g.editable && plCanEdit(), can = k => ed && !!wf[k];
    const owners = t.assignedL.length ? t.assignedL : (() => { try { return JSON.parse(doc._assign || '[]'); } catch (e) { return []; } })();
    const x = PL.data, dl = (id, rows) => `<datalist id="${id}">${rows.join('')}</datalist>`;
    const lists = {
      ill_quotation: dl('tkq', D.quotes.filter(q => q.docstatus < 2).map(q => `<option value="${esc(q.name)}">${esc(q.party_name)} · ${money(q.base_net_total)}</option>`)),
      ill_sales_order: dl('tkso', D.ship.map(s => `<option value="${esc(s.so)}">${esc(s.customer)} · ${money(s.value)}</option>`)),
      ill_project: dl('tkp', (x ? x.projects : []).map(p => `<option value="${esc(p.name)}">${esc(p.project_name || '')} · ${esc(p.customer || '')}</option>`)),
      ill_fixture_schedule: dl('tks', (x ? x.schedules : []).map(s => `<option value="${esc(s.name)}">${esc(schedName(s))} · ${esc(s.customer || '')}</option>`)) };
    const LINKS = [['ill_quotation', 'Quotation', 'tkq', 'quotation'], ['ill_sales_order', 'Sales order', 'tkso', 'sales-order'], ['ill_project', 'Project', 'tkp', 'ill-project'], ['ill_fixture_schedule', 'Fixture schedule', 'tks', 'ill-project-fixture-schedule']];
    const fieldOrRO = (k, label, html) => can(k) ? fld(label, html) : `<div class="wb-kv"><span>${label}</span><b>${esc(doc[k] || '—')}</b></div>`;
    const stg = tkStage({ ...t, type: doc.ticket_type, sales_order: doc.ill_sales_order, quotation: doc.ill_quotation });
    const inner = `<div class="wb-kvs">
        <div class="wb-kv"><span>Requester</span><b>${esc(doc.raised_by || t.raised_by || '—')}</b></div>
        <div class="wb-kv"><span>Opened</span><b>${fmtd(doc.opening_date || doc.creation)} · ${esc(t.age != null ? t.age + ' business days' : '')}</b></div>
        <div class="wb-kv"><span>Stage</span><b><a href="#${stg}">${esc((STAGES.find(z => z.k === stg) || {}).n || stg)}</a></b></div>
        <div class="wb-kv"><span>Last activity</span><b>${fmtd(doc.modified)}</b></div></div>
      ${ed ? '' : `<p class="wb-note">${plCanEdit() ? 'This ticket is read-only here.' : 'View only. Reassigning, linking and status changes need the Command Center Editor role.'}</p>`}
      <div class="cc-row2">${fieldOrRO('status', 'Status', sel('status', ['Open', 'Replied', 'Paused', 'Resolved', 'Closed'].concat(doc.status && !['Open', 'Replied', 'Paused', 'Resolved', 'Closed'].includes(doc.status) ? [doc.status] : []), doc.status))}
        ${fieldOrRO('priority', 'Priority', `<input type="text" name="priority" list="tkpri" value="${esc(doc.priority || '')}">${dl('tkpri', ['Low', 'Medium', 'High', 'Urgent'].map(p => `<option value="${p}">`))}`)}</div>
      <div class="cc-row2">${fieldOrRO('ticket_type', 'Type', `<input type="text" name="ticket_type" list="tktype" value="${esc(doc.ticket_type || '')}">${dl('tktype', TK_TYPES().map(k => `<option value="${esc(k)}">`))}`)}
        ${fieldOrRO('agent_group', 'Team', `<input type="text" name="agent_group" value="${esc(doc.agent_group || '')}">`)}</div>
      <div class="cc-field"><span>Owners</span>${ed ? ownerChips(owners) : avs(owners)}</div>
      <div class="wb-sec">Linked records</div>
      ${LINKS.map(([k, label, id, sl]) => can(k) ? `<div class="cc-field"><span>${label}${doc[k] ? ` · <a target="_blank" rel="noopener" href="/app/${sl}/${encodeURIComponent(doc[k])}">open ↗</a>` : ''}</span><div style="display:flex;gap:8px"><input type="text" name="${k}" list="${id}" value="${esc(doc[k] || '')}" placeholder="Not linked" style="flex:1">${doc[k] ? `<button type="button" class="cc-btn soft" data-unlink="${k}">Unlink</button>` : ''}</div>${lists[k]}</div>` : `<div class="wb-kv"><span>${label}</span><b>${doc[k] ? link(sl, doc[k]) : '—'}</b></div>`).join('')}
      ${g.audit.length ? `<div class="wb-sec">Recent changes from the Command Center</div><ul class="wb-audit">${g.audit.map(a => `<li><span>${fmtd(a.creation)}</span> ${esc(wbPlain(a.content).replace(/^Command Center:\s*/, ''))}</li>`).join('')}</ul>` : ''}`;
    const sh = sheet(esc(doc.subject || t.subject || name), `${esc(name)} · ${esc(doc.status || '')}`, inner, ed ? async elx => {
      const vals = {};
      ['status', 'priority', 'ticket_type', 'agent_group', 'ill_quotation', 'ill_sales_order', 'ill_project', 'ill_fixture_schedule'].forEach(k => { if (!can(k)) return; const v = val(elx, k).trim(); if (v !== String(doc[k] || '')) vals[k] = v || null; });
      if (vals.ill_quotation && !D.qByName[vals.ill_quotation]) throw new Error('pick a quotation from the list');
      const own = checked(elx), add = own.filter(u => !owners.includes(u)), rem = owners.filter(u => !own.includes(u));
      if (!Object.keys(vals).length && !add.length && !rem.length) throw new Error('nothing changed');
      if (Object.keys(vals).length) await gw('save', { dt: 'HD Ticket', name, values: vals });
      if (add.length || rem.length) await gw('assign', { dt: 'HD Ticket', name, add, remove: rem });
      toast('Ticket ' + esc(name) + ' updated'); PL.data = null;
    } : null, 'Save changes');
    const f = sh.querySelector('.cc-sheet-f'); if (f) f.insertAdjacentHTML('afterbegin', replyBtn({ name, status: doc.status }) + `<a class="cc-btn soft" target="_blank" rel="noopener" href="/app/hd-ticket/${encodeURIComponent(name)}" style="text-decoration:none">Desk view</a><span style="flex:1"></span>`);
    sh.querySelectorAll('[data-unlink]').forEach(b => b.onclick = () => { const i = sh.querySelector(`[name="${b.dataset.unlink}"]`); i.value = ''; b.remove(); });
  }


  /* ---------------- Catalog tab (v8) ----------------
     The ERPNext Catalog Builder (/catalog-builder?embed=1) in a same-origin iframe, so the session, CSRF
     token, permission gate and localStorage drafts are the builder's own. The iframe lives OUTSIDE #ccmain
     (which render() replaces) and is only hidden on other tabs, so the grid, undo stack and a passing Check
     survive switching to Inbox and back. Tab shown to ilL Catalog Publisher / System Manager (gateway
     config.catalog.allowed); the builder page re-checks server-side. No new sync path: Check → Import. */
  let WHO = null, WHO_BUSY = false;
  async function whoami() {
    if (WHO || WHO_BUSY) return; WHO_BUSY = true;
    try { WHO = await gw('config', { lite: 1 }); } catch (e) { WHO = { catalog: { allowed: false }, err: e.message }; }
    WHO_BUSY = false; if (D) render();
  }
  const catOK = () => !!(WHO && WHO.catalog && WHO.catalog.allowed);
  const CAT = { host: null, frame: null, ready: false, dirty: false, queue: [] };
  const CAT_SRC = '/catalog-builder?embed=1';
  function catHost() {
    if (CAT.host) return CAT.host;
    const h = document.createElement('div'); h.id = 'cccatalog'; h.className = 'cc-catalog no-print';
    const f = document.createElement('iframe'); f.src = CAT_SRC; f.title = 'Catalog Builder'; f.setAttribute('loading', 'eager');
    h.appendChild(f); $('#ccmain').insertAdjacentElement('afterend', h);
    CAT.host = h; CAT.frame = f; return h;
  }
  function catShow(on) {
    if (!on) { if (CAT.host) CAT.host.style.display = 'none'; return; }
    const h = catHost(); h.style.display = '';
    try { const top = h.getBoundingClientRect().top + (window.scrollY || 0); if (top > 0) h.style.setProperty('--cat-top', Math.round(top) + 'px'); } catch (e) { }
  }
  function catPost(m) { try { CAT.frame.contentWindow.postMessage(m, location.origin); } catch (e) { } }
  // messages to the builder wait until it has said "ready"
  function catSend(msg) { const m = Object.assign({ source: 'ill-command-center' }, msg); if (CAT.ready && CAT.frame) catPost(m); else CAT.queue.push(m); }
  function catOpen(msg) {
    closeSheet();
    if (!catOK()) { window.open('/catalog-builder', '_blank', 'noopener'); return; }
    catSend(msg); location.hash = 'catalog';
  }
  function catNav() {
    const a = $('#ccnav a[href="#catalog"]'); if (!a) return; const d = a.querySelector('.dot');
    if (CAT.dirty && !d) a.insertAdjacentHTML('afterbegin', '<span class="dot warn" title="Catalog draft not imported yet"></span>');
    if (!CAT.dirty && d) d.remove();
  }
  window.addEventListener('message', e => {
    const m = e.data;
    if (e.origin !== location.origin || !m || typeof m !== 'object' || m.source !== 'ill-catalog-builder') return;
    if (!CAT.frame || (e.source && e.source !== CAT.frame.contentWindow)) return;
    if (m.type === 'ready') { CAT.ready = true; CAT.queue.splice(0).forEach(catPost); }
    else if (m.type === 'dirty') { CAT.dirty = !!m.dirty; catNav(); }
    else if (m.type === 'imported') {
      CAT.dirty = false; catNav();
      toast(`Imported ${+m.created || 0} record${+m.created === 1 ? '' : 's'} to ERPNext${m.name ? ` (receipt <a target="_blank" rel="noopener" href="/app/ill-catalog-import/${encodeURIComponent(m.name)}">${esc(m.name)}</a>)` : ''}`);
      // Workbench counts and catalog lists are stale now; the open sheet (if a catalog record) is re-read
      WB.counts = null; WB.icounts = {}; WB.igot = {};
      Object.keys(WB.lists).forEach(d => { const c = WB.cfg && WB.cfg.doctypes[d]; if (c && (c.builder || (c.sections || []).some(k => /^ill_/.test(k)))) WB.lists[d].loaded = false; });
      if (WB.sheet && $('#ccsheet2').classList.contains('on')) wbOpen(WB.sheet.dt, WB.sheet.name);
    }
  });
  window.addEventListener('beforeunload', e => { if (CAT.dirty) { e.preventDefault(); e.returnValue = ''; } });
  V.catalog = () => WHO ? `<div class="ph-h cat-h"><div><h1>Catalog Builder</h1><p>Builds sync to ERPNext through Check → Import, with the same permissions and audit receipts as the standalone builder. Drafts are kept in this browser and carry over to full screen.</p></div>
      <div class="toolbar no-print"><a class="cc-btn soft" style="text-decoration:none" href="/catalog-builder" target="_blank" rel="noopener">Open full screen ↗</a><a class="cc-btn soft" style="text-decoration:none" href="/app/ill-catalog-import" target="_blank" rel="noopener">Import history</a><button class="cc-btn soft" id="catreload">Reload builder</button></div></div>`
    : '<div class="cc-loading"><span class="cc-spin"></span>Checking catalog access…</div>';
  function catBind() {
    const b = $('#catreload'); if (!b) return;
    b.onclick = () => { if (CAT.dirty && !confirm('Reload the builder? Your draft is kept in this browser, but undo history and the last Check are lost.')) return;
      CAT.ready = false; CAT.dirty = false; catNav(); try { CAT.frame.contentWindow.location.reload(); } catch (e) { CAT.frame.src = CAT_SRC; } };
  }

  /* ---------------- render ---------------- */
  const agNavCount = () => { const m = (AG.list || []).find(x => x.name === agDefault()); return m && m.status === 'Open' && m.open ? m.open : null; };
  let WORK_SEG = false;
  const workSeg = () => `<div class="seg" style="margin:-8px 0 20px"><button data-go="work" class="${S.view === 'work' || S.view.startsWith('p-') ? 'on' : ''}">Projects</button><button data-go="tasks" class="${S.view === 'tasks' ? 'on' : ''}">All tasks &amp; to-dos</button></div>`;
  function render() {
    const m = M();
    $('#ccstamp').textContent = 'Live from ERPNext · updated ' + new Date(D.generated.replace(' ', 'T')).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    if (REDIRECT[S.view]) { S.view = REDIRECT[S.view]; history.replaceState(null, '', '#' + S.view); }
    let v = S.view; const so = v.startsWith('so-') ? decodeURIComponent(v.slice(3)) : null, pid = v.startsWith('p-') ? v.slice(2) : null;
    const dsid = v.startsWith('design/') ? decodeURIComponent(v.slice(7)) : null;
    const known = PIPE.concat(['inbox', 'finance', 'work', 'tasks', 'rec', 'exec', 'review', 'catalog']);
    if (v === 'catalog' && WHO && !catOK()) { v = S.view = 'pipeline'; history.replaceState(null, '', '#pipeline'); }
    if (!so && !pid && !dsid && !known.includes(v) && !wbIsView() && !agIsView()) { v = S.view = 'pipeline'; }
    if (plIsView() && ((!PL.data && !PL.err) || PL.stale)) { PL.stale = false; plLoad(true); }
    const group = wbIsView() ? 'wb' : agIsView() ? 'agenda' : so || dsid || PIPE.includes(v) ? 'pipeline' : (pid || v === 'work' || v === 'tasks') ? 'work' : v;
    const TOP = [['pipeline', 'Sales pipeline', null, null], ['exec', 'Executive', null, null], ['inbox', 'Inbox', m.tOpen.length, m.tOld.length > 3 ? 'bad' : m.tOld.length ? 'warn' : 'good'],
      ['finance', 'Finance', null, D.fin.mtd >= m.goalPace ? 'good' : 'warn'], ['work', 'Projects & tasks', m.overdue.length, m.overdue.length ? 'warn' : 'good'], ['review', 'Review', null, null], ['agenda', 'Agenda', agNavCount(), null], ['wb', 'Workbench', null, null]].concat(catOK() ? [['catalog', 'Catalog', null, CAT.dirty ? 'warn' : null]] : []).concat([['rec', 'Recommendations', null, 'info']]);
    $('#ccnav').innerHTML = TOP.map(([k, n, c, s]) => `<a class="cc-tab ${group === k ? 'on' : ''}" href="#${k}">${s ? `<span class="dot ${s}"></span>` : ''}${n}${c ? `<span class="ct">${c}</span>` : ''}</a>`).join('');
    CUR_M = m; CUR_STEP = dsid ? 'design' : (PIPE.includes(v) && !so) ? v : null; WORK_SEG = group === 'work' && !pid; CUR_LINKS = so ? 'so' : pid ? 'project' : dsid ? 'design' : v;
    let html;
    if (so) html = V.so(m, so);
    else if (pid) html = V.project(m, pid);
    else if (dsid) html = V.designSched(m, dsid);
    else if (wbIsView()) html = WB.html(v);
    else if (agIsView()) html = AG.html();
    else if (v === 'exec') html = EX.html();
    else if (v === 'review') html = RV.html();
    else if (v === 'catalog') html = V.catalog();
    else if (v === 'purch') html = V.purch(m);
    else html = ({ inbox: V.inbox, finance: V.fin, tasks: V.tasks })[v] ? ({ inbox: V.inbox, finance: V.fin, tasks: V.tasks })[v](m) : V[v](m);
    CUR_STEP = null; WORK_SEG = false; CUR_LINKS = null;
    $('#ccmain').innerHTML = html;
    catShow(v === 'catalog' && catOK()); if (v === 'catalog') { catBind(); if (!WHO) whoami(); }
    bind(); bindProjects(); bindPipe(); bindStages(); if (wbIsView()) WB.mount();
    if (v === 'exec') EX.mount(); if (v === 'review') RV.mount(); if (v === 'mfg') PB.mount(); if (v === 'ship') { FL.mount(); const fr = $('#flrefresh'); if (fr) fr.onclick = () => { FL.at = 0; flFetch(true); }; } if (v === 'purch') PU.mount(); if (agIsView()) AG.mount();
    if (so && !PU.data && !PU.busy && !PU.err) puFetch();
    root.querySelectorAll('[data-go]').forEach(b => b.onclick = () => { location.hash = b.dataset.go; });
  }
  function bind() {
    bindSV();
    root.querySelectorAll('.tile[data-v]').forEach(el => el.onclick = () => { location.hash = el.dataset.v; });
    root.querySelectorAll('select[data-f]').forEach(el => el.onchange = () => { S[el.dataset.f] = el.value; S.limit = 30; render(); });
    root.querySelectorAll('input[data-f="mine"]').forEach(el => el.onchange = () => { S.mine = el.checked; render(); });
    root.querySelectorAll('.seg button[data-st]').forEach(el => el.onclick = () => { S.status = el.dataset.st; S.limit = 30; render(); });
    root.querySelectorAll('[data-more]').forEach(el => el.onclick = () => { S.limit += 30; render(); });
    root.querySelectorAll('[data-done]').forEach(b => b.onclick = async () => {
      b.disabled = true; b.textContent = '…';
      try { for (const id of b.dataset.done.split(',')) await call('frappe.client.set_value', { doctype: 'ToDo', name: id, fieldname: 'status', value: 'Closed' }); toast('Marked done in ERPNext'); await load(); }
      catch (e) { toast('Could not close: ' + esc(e.message)); b.disabled = false; b.textContent = '✓ Done'; }
    });
    mrBind(root);
  }
  // "Draft MR" buttons (shortage rows and low-stock rows): one draft Material Request through the purchasing
  // board endpoint (company and warehouse come from ilL-Purchasing-Settings). Nothing is submitted.
  function mrBind(scope) {
    const go = async (b, item, qty, date) => {
      b.disabled = true; b.textContent = '…';
      try { const res = await puPost('draft_material_request', { items: [{ item, qty, schedule_date: date }] });
        toast(`Draft ${esc(res.name)} created, not submitted · <a target="_blank" href="/app/material-request/${encodeURIComponent(res.name)}">Open</a>`); if (S.view === 'purch') puFetch(); else await load(); }
      catch (e) { toast('Could not create: ' + esc(e.message)); b.disabled = false; b.textContent = 'Draft MR'; }
    };
    scope.querySelectorAll('[data-mr]').forEach(b => b.onclick = () => { const r = puShort().find(x => x.item === b.dataset.mr); if (!r) return;
      go(b, r.item, Math.ceil(r.short_firm > 0 ? r.short_firm : r.short_all || 1), r.need_by && r.need_by > TODAY ? r.need_by : addDays(TODAY, r.lead || 14)); });
    scope.querySelectorAll('[data-mrlow]').forEach(b => b.onclick = () => go(b, b.dataset.mrlow, +b.dataset.qty || 1, addDays(TODAY, 14)));
  }
  const addDays = (d, n) => { const t = new Date(d + 'T12:00'); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
  // A session that opened /command-center before the desk has no CSRF token on this page (the Web Page
  // renders "None"). The desk page always carries one, so read it from there once and reuse it.
  let csrfFetch = null;
  function ensureCsrf() {
    if (CSRF()) return Promise.resolve(CSRF());
    if (!csrfFetch) {
      csrfFetch = fetch('/app', { credentials: 'same-origin' })
        .then(r => (r.ok ? r.text() : ''))
        .then(html => { const m = html.match(/csrf_token\s*=\s*["']([0-9a-f]{16,})["']/); if (m) { window.frappe = window.frappe || {}; frappe.csrf_token = m[1]; } return m ? m[1] : null; })
        .catch(() => null)
        .finally(() => { csrfFetch = null; });
    }
    return csrfFetch;
  }
  async function call(method, args) {
    const tok = CSRF() || await ensureCsrf(); if (!tok) throw new Error('please log in to ERPNext first');
    const r = await fetch('/api/method/' + method, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Frappe-CSRF-Token': tok }, body: JSON.stringify(args) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { let msg = r.status + ''; try { msg = JSON.parse(JSON.parse(j._server_messages)[0]).message; } catch (e) { msg = j.exception || msg; } throw new Error(String(msg).replace(/<[^>]+>/g, '')); }
    return j.message;
  }
  function toast(html) { const t = $('#cctoast'); t.innerHTML = html; t.style.display = 'block'; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', 6000); }

  /* ---------------- add task ---------------- */
  async function addTask(e) {
    e.preventDefault();
    const title = $('#tTitle').value.trim(), owners = [...root.querySelectorAll('#tOwners input:checked')].map(i => i.value), msg = $('#tMsg');
    if (!title || !owners.length) { msg.textContent = 'Add a title and at least one owner.'; return; }
    const due = $('#tDue').value || null, pri = $('#tPri').value, proj = $('#tProj').value, notes = $('#tNotes').value.trim();
    const doc = { doctype: 'ToDo', status: 'Open', allocated_to: owners[0], priority: pri, assigned_by: USER,
      description: `<p><b>${esc(title)}</b></p>${notes ? `<p>${esc(notes)}</p>` : ''}<p>[ad-hoc] Owners: ${owners.join(', ')}</p>` };
    if (due) doc.date = due; if (proj) { doc.reference_type = 'Project'; doc.reference_name = proj; }
    const b = $('#tSave'); b.disabled = true; b.textContent = 'Saving…';
    try { await call('frappe.client.insert', { doc }); closeModal(); toast(`Saved to ERPNext · ${owners.length} owner${owners.length > 1 ? 's' : ''} notified`); location.hash = 'tasks'; await load(); }
    catch (err) { msg.textContent = 'Not saved: ' + err.message; }
    finally { b.disabled = false; b.textContent = 'Save to ERPNext'; }
  }
  function openModal() {
    if (!LOGGED) { toast('Log in to ERPNext to add tasks · <a href="/login?redirect-to=/command-center">Log in</a>'); return; }
    if (!D) return;
    $('#tOwners').innerHTML = TEAM.map(u => `<label><input type="checkbox" value="${esc(u.name)}">${avatar(u.name)}${esc(u.full_name || u.name)}</label>`).join('');
    $('#tProj').innerHTML = '<option value="">None</option>' + D.projects.map(p => `<option value="${esc(p.name)}">${esc(p.project_name)}</option>`).join('');
    $('#ccmodal').classList.add('on'); setTimeout(() => $('#tTitle').focus(), 50);
  }
  function closeModal() { $('#ccmodal').classList.remove('on'); $('#tform').reset(); $('#tMsg').textContent = ''; }

  /* ---------------- workbench: every stage's doctypes, drill in, edit, add ----------------
     Talks only to the role-gated Server Script "ilL Command Center Gateway" (ill_cc_gateway).
     Nothing is submitted, cancelled or deleted from here. */
  const GW = 'ill_cc_gateway';
  const WB = { cfg: null, cfgErr: null, cfgBusy: false, lists: {}, counts: null, cbusy: false, metas: {}, dt: null,
    area: 'pipeline', icounts: {}, igot: {}, iq: '', from: null, sheet: null };
  try { if (localStorage.getItem('cc.wb.area.' + USER) === 'ill') WB.area = 'ill'; } catch (e) { }
  const gw = (action, args) => call(GW, Object.assign({ action }, args || {}));
  const wbIsView = () => String(S.view || '').split('/')[0] === 'wb';
  // #wb (last area used), #wb/~pipeline, #wb/~ill, #wb/<doctype>[/<status>]
  const wbRoute = v => { const p = String(v || '').split('/'); return p[1] && p[1][0] !== '~' ? decodeURIComponent(p[1]) : null; };
  const wbAreaOf = v => { const p = String(v || '').split('/')[1]; return p === '~ill' ? 'ill' : p === '~pipeline' ? 'pipeline' : null; };
  const wbSecs = info => (info && (info.sections || [info.section])) || [];
  const wbLabel = dt => String(dt).replace(/^ilL-/, '').replace(/-/g, ' ');
  const wbPlain = v => String(v == null ? '' : v).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  const wbKind = s => {
    s = String(s || '');
    if (/^inactive$/i.test(s)) return 'mute';
    if (/^active$/i.test(s)) return 'good';
    if (/cancel|reject|lost|expire|stop|overdue|block|fail|spam/i.test(s)) return 'bad';
    if (/complet|paid|closed|resolv|deliver|approv|won|done|ordered|received|submitted/i.test(s)) return 'good';
    if (/draft|open|pend|hold|partly|^to |unpaid|repl|wait|working|new|review/i.test(s)) return 'warn';
    return 'mute';
  };
  const wbCol = { good: 'var(--good,#1baf7a)', warn: 'var(--warn,#eda100)', bad: 'var(--bad,#d93025)', mute: '#98a2b3' };
  const wbL = dt => WB.lists[dt] || (WB.lists[dt] = { rows: [], total: 0, status: '', search: '', order: 'modified desc', loading: false, loaded: false, err: null, mix: null, cols: null });
  // meeting mode hides ToDos made from Kevin's email (same rule as the Tasks page)
  const wbPrivate = (dt, r) => S.meeting && dt === 'ToDo' && /\[email\]/.test(String((r || {}).description || ''));
  const wbListUrl = dt => slug(dt) === 'hd-ticket' ? '/helpdesk/tickets' : '/app/' + slug(dt);

  function wbCell(c, v) {
    if (v == null || v === '') return '<span class="calc">—</span>';
    if (c.fieldname === 'status') return badge(v, wbKind(v));
    if (c.type === 'Currency') return money(Number(v));
    if (c.type === 'Percent') return Math.round(Number(v)) + '%';
    if (c.type === 'Date' || c.type === 'Datetime') return fmtd(v);
    if (c.type === 'Check') return v ? '✓' : '';
    const t = wbPlain(v); return esc(t.length > 70 ? t.slice(0, 70) + '…' : t);
  }

  /* ---- landing: Pipeline (one card per stage) or ilLumenate (one card per app doctype group) ---- */
  const wbAreaSeg = () => `<div class="seg wb-area no-print"><button data-wbarea="pipeline" class="${WB.area !== 'ill' ? 'on' : ''}">Pipeline</button><button data-wbarea="ill" class="${WB.area === 'ill' ? 'on' : ''}">ilLumenate</button></div>`;
  const wbDtBtn = (d, sec, n) => `<button class="wb-dt" data-wbdt="${esc(d)}" data-wbfrom="${esc(sec)}"><span>${esc(wbLabel(d))}</span><span class="ct" data-wbct="${esc(d)}">${n == null ? '…' : n}</span></button>`;
  function wbLanding() {
    const cfg = WB.cfg;
    if (WB.area === 'ill') return wbIllLanding();
    const cards = cfg.sections.filter(s => (s.area || 'pipeline') === 'pipeline').map(s => {
      const dts = Object.keys(cfg.doctypes).filter(d => wbSecs(cfg.doctypes[d]).includes(s.key));
      if (s.locked) return `<div class="card wb-card locked"><div class="wb-card-h"><h3>${esc(s.label)}</h3><span class="badge mute">🔒 Locked</span></div><p class="small">Needs the <b>${esc(s.needs)}</b> role. Ask Kevin.</p></div>`;
      if (!dts.length) return '';
      return `<div class="card wb-card"><div class="wb-card-h"><h3>${esc(s.label)}</h3></div>
        ${dts.map(d => wbDtBtn(d, s.key, WB.counts ? WB.counts[d] : null)).join('')}</div>`;
    }).join('');
    return `<div class="wb-head"><div><h1>Workbench</h1><p>Every doctype behind each stage in one place. Pick one to browse, open, edit or add records.</p></div>
      ${cfg.can_edit ? '<span class="badge good">Editor</span>' : '<span class="badge mute">View only</span>'}</div>${wbAreaSeg()}<div class="wb-grid">${cards}</div>`;
  }
  function wbIllCards() {
    const cfg = WB.cfg, q = WB.iq.toLowerCase();
    const cards = cfg.sections.filter(s => s.area === 'ill').map(s => {
      const all = Object.keys(cfg.doctypes).filter(d => wbSecs(cfg.doctypes[d]).includes(s.key)), dts = all.filter(d => !q || wbLabel(d).toLowerCase().includes(q) || d.toLowerCase().includes(q));
      if (s.locked) return q ? '' : `<div class="card wb-card locked"><div class="wb-card-h"><h3>${esc(s.label)}</h3><span class="badge mute">🔒 Locked</span></div><p class="small">Needs the <b>${esc(s.needs)}</b> role.</p></div>`;
      if (!dts.length) return '';
      return `<div class="card wb-card" data-wbgroup="${esc(s.key)}"><div class="wb-card-h"><h3>${esc(s.label)}</h3><span class="small">${all.length}</span></div>
        ${dts.map(d => wbDtBtn(d, s.key, WB.icounts[d])).join('')}</div>`;
    }).join('');
    const st = (cfg.settings || []).filter(x => !q || x.doctype.toLowerCase().includes(q));
    const set = st.length ? `<div class="card wb-card"><div class="wb-card-h"><h3>Settings</h3><span class="small">opens in ERPNext</span></div>${st.map(x => `<a class="wb-dt" target="_blank" rel="noopener" href="${esc(x.url)}"><span>${esc(wbLabel(x.doctype))}</span><span class="ct">↗</span></a>`).join('')}</div>` : '';
    return (cards + set) || '<div class="empty">No doctype matches.</div>';
  }
  function wbIllLanding() {
    return `<div class="wb-head"><div><h1>Workbench · ilLumenate</h1><p>Every app doctype, grouped like the desk workspace: templates, specs, attributes, maps, configured products, portal, publishing and logs. Templates, specs and maps are created in the Catalog Builder.</p></div>
      ${WB.cfg.can_edit ? '<span class="badge good">Editor</span>' : '<span class="badge mute">View only</span>'}</div>${wbAreaSeg()}
      <div class="wb-bar"><input type="search" id="wbillq" placeholder="Filter doctypes…" value="${esc(WB.iq)}" aria-label="Filter doctypes"></div><div class="wb-grid" id="wbillgrid">${wbIllCards()}</div>`;
  }
  // counts for the ilLumenate landing: one call per group, when its card first comes into view
  function wbICounts(scope) {
    const fetchGroup = async key => {
      if (WB.igot[key]) return; WB.igot[key] = 'busy';
      try { const c = (await gw('counts', { area: 'ill', section: key })).counts || {}; Object.keys(c).forEach(d => { WB.icounts[d] = c[d] == null ? '—' : c[d]; }); WB.igot[key] = 'done'; }
      catch (e) { WB.igot[key] = null; }
      const r = $('#wbroot'); if (r) r.querySelectorAll(`[data-wbgroup="${key}"] [data-wbct]`).forEach(el => { const n = WB.icounts[el.dataset.wbct]; el.textContent = n == null ? '—' : n; });
    };
    const cards = [...(scope || root).querySelectorAll('[data-wbgroup]')].filter(c => !WB.igot[c.dataset.wbgroup]);
    if (!cards.length) return;
    if (typeof IntersectionObserver === 'function') {
      const io = new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) { io.unobserve(en.target); fetchGroup(en.target.dataset.wbgroup); } }), { rootMargin: '200px' });
      cards.forEach(c => io.observe(c));
    } else cards.forEach(c => fetchGroup(c.dataset.wbgroup));
  }

  /* ---- list view: header + toolbar (static) and #wbdata (redrawn on every fetch) ---- */
  function wbListShell(dt) {
    const cfg = WB.cfg, info = cfg.doctypes[dt], L = wbL(dt), secs = wbSecs(info);
    const from = WB.from && WB.from.dt === dt && secs.includes(WB.from.sec) ? WB.from.sec : WB.area === 'ill' ? (secs.find(k => /^ill_/.test(k)) || info.section) : info.section;
    const sec = cfg.sections.find(s => s.key === from) || {}, ill = sec.area === 'ill';
    const sib = Object.keys(cfg.doctypes).filter(d => wbSecs(cfg.doctypes[d]).includes(from));
    return `<div class="wb-crumb"><a href="#wb/${ill ? '~ill' : '~pipeline'}">${ill ? 'Workbench · ilLumenate' : 'Workbench'}</a><span>›</span>${esc(sec.label || from)}${info.read_only ? ' ' + badge('Read-only here', 'mute') : ''}</div>
      <div class="wb-head"><div><h1>${esc(wbLabel(dt))}</h1></div>
        <div class="wb-actions"><a class="cc-btn soft" target="_blank" rel="noopener" href="${wbListUrl(dt)}" style="text-decoration:none">Open in ERPNext</a>
        ${info.can_create ? `<button class="cc-btn primary" id="wbnew">+ New ${esc(wbLabel(dt))}${info.create === 'builder' ? ' in Catalog Builder' : ''}</button>` : ''}</div></div>
      ${sib.length > 1 ? `<div class="seg wb-sib">${sib.map(d => `<button data-wbdt="${esc(d)}" data-wbfrom="${esc(from)}" class="${d === dt ? 'on' : ''}">${esc(wbLabel(d))}</button>`).join('')}</div>` : ''}
      <div class="wb-bar"><input type="search" id="wbq" placeholder="Search ${esc(wbLabel(dt))}…" value="${esc(L.search)}">${viewsBar('wb:' + dt)}</div>
      <div id="wbdata"></div>`;
  }
  function wbData() {
    const dt = WB.dt, el = $('#wbdata'); if (!el || !dt || !WB.cfg || !WB.cfg.doctypes[dt]) return;
    const L = wbL(dt), cols = L.cols || WB.cfg.doctypes[dt].columns;
    if (L.err) { el.innerHTML = `<div class="err">Couldn't load ${esc(wbLabel(dt))}: ${esc(L.err)}</div>`; return; }
    if (!L.loaded) { el.innerHTML = '<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>'; return; }
    const rows = L.rows.filter(r => !wbPrivate(dt, r)), has = f => cols.some(c => c.fieldname === f), now = Date.now();
    const sumF = has('outstanding_amount') && dt === 'Sales Invoice' ? 'outstanding_amount' : has('grand_total') ? 'grand_total' : null;
    const tiles = [['Records', L.total]];
    if (sumF) tiles.push([sumF === 'outstanding_amount' ? 'Outstanding' : 'Value', money(rows.reduce((a, r) => a + (Number(r[sumF]) || 0), 0)), rows.length < L.total ? `first ${rows.length} loaded` : '']);
    if (has('status')) tiles.push(['In progress', rows.filter(r => wbKind(r.status) === 'warn').length, rows.length < L.total ? `of ${rows.length} loaded` : '']);
    tiles.push(['Touched this week', rows.filter(r => r.modified && now - new Date(String(r.modified).replace(' ', 'T')).getTime() < 7 * 864e5).length, rows.length < L.total ? `of ${rows.length} loaded` : '']);
    let mix = '';
    if (L.status && !(L.mix && L.mix.length > 1)) mix = `<div class="wb-mix"><div class="wb-chips"><button class="wb-chip" data-wbstatus="">All</button><button class="wb-chip on" data-wbstatus="${esc(L.status)}"><span class="dot ${wbKind(L.status)}"></span>${esc(L.status)}</button></div></div>`;
    if (L.mix && L.mix.length > 1) {
      const tot = L.mix.reduce((a, m) => a + m[1], 0);
      mix = `<div class="wb-mix"><div class="wb-mixbar">${L.mix.map(([s, n]) => `<span title="${esc(s)}: ${n}" style="width:${(n / tot * 100).toFixed(2)}%;background:${wbCol[wbKind(s)]}"></span>`).join('')}</div>
        <div class="wb-chips"><button class="wb-chip ${L.status ? '' : 'on'}" data-wbstatus="">All</button>${L.mix.map(([s, n]) => `<button class="wb-chip ${L.status === s ? 'on' : ''}" data-wbstatus="${esc(s)}"><span class="dot ${wbKind(s)}"></span>${esc(s)} <b>${n}</b></button>`).join('')}</div></div>`;
    }
    const [sf, sd] = L.order.split(' ');
    const head = cols.map(c => `<th data-wbsort="${esc(c.fieldname)}" class="wb-th">${esc(c.label)}${sf === c.fieldname ? (sd === 'asc' ? ' ▲' : ' ▼') : ''}</th>`).join('');
    const body = rows.map(r => `<tr class="wb-row" data-wbopen="${esc(r.name)}">${cols.map((c, i) => `<td${i === 0 ? ' class="wb-first"' : ''}>${wbCell(c, r[c.fieldname])}</td>`).join('')}</tr>`).join('');
    el.innerHTML = `<div class="wb-tiles">${tiles.map(([l, v, s]) => `<div class="wb-tile"><div class="l">${esc(l)}</div><div class="v">${typeof v === 'number' ? v.toLocaleString('en-US') : v}</div>${s ? `<div class="s">${esc(s)}</div>` : ''}</div>`).join('')}</div>
      ${mix}
      <div class="card flush wb-tablewrap">${rows.length ? `<table class="wb-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>` : '<div class="empty">Nothing matches.</div>'}</div>
      <div class="wb-more">${L.rows.length < L.total ? `<button class="cc-btn soft" id="wbmore" ${L.loading ? 'disabled' : ''}>${L.loading ? 'Loading…' : 'Load more'}</button>` : ''}<span class="small">Showing ${rows.length} of ${L.total}${rows.length < L.rows.length ? ` · ${L.rows.length - rows.length} hidden in meeting mode` : ''}</span></div>`;
    el.querySelectorAll('[data-wbstatus]').forEach(b => b.onclick = () => { L.status = b.dataset.wbstatus; wbFetch(dt, false); });
    el.querySelectorAll('[data-wbsort]').forEach(h => h.onclick = () => { const f = h.dataset.wbsort; L.order = f + ' ' + (sf === f && sd === 'desc' ? 'asc' : 'desc'); wbFetch(dt, false); });
    el.querySelectorAll('[data-wbopen]').forEach(r => r.onclick = () => wbOpen(dt, r.dataset.wbopen));
    const m = el.querySelector('#wbmore'); if (m) m.onclick = () => wbFetch(dt, true);
  }
  async function wbFetch(dt, append) {
    const L = wbL(dt); if (L.loading) return;
    L.loading = true; L.err = null; wbData();
    try {
      const res = await gw('list', { dt, filters: L.status ? { status: L.status } : {}, search: L.search, order_by: L.order, limit: 50, start: append ? L.rows.length : 0 });
      L.rows = append ? L.rows.concat(res.rows) : res.rows; L.total = res.total; L.cols = res.columns; L.loaded = true;
      if (!L.status && !L.search && !append && res.columns.some(c => c.fieldname === 'status')) {
        const m = {}; L.rows.forEach(r => { if (r.status) m[r.status] = (m[r.status] || 0) + 1; }); L.mix = Object.keys(m).map(k => [k, m[k]]).sort((a, b) => b[1] - a[1]);
      }
    } catch (e) { L.err = e.message; L.loaded = true; }
    L.loading = false; if (WB.dt === dt && wbIsView()) wbData();
  }

  /* ---- record sheet: summary, line items, edit form, audit ---- */
  const wbInput = (f, cur) => {
    const n = esc(f.fieldname), v = cur == null ? '' : cur, T = f.type;
    if (T === 'Select') { const o = String(f.options || '').split('\n'); return `<select name="${n}">${o.map(x => `<option value="${esc(x)}" ${String(v) === x ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`; }
    if (T === 'Check') return `<input type="checkbox" name="${n}" ${Number(v) ? 'checked' : ''}>`;
    if (T === 'Date') return `<input type="date" name="${n}" value="${esc(String(v).slice(0, 10))}">`;
    if (T === 'Datetime') return `<input type="datetime-local" name="${n}" value="${esc(String(v).slice(0, 16).replace(' ', 'T'))}">`;
    if (['Int', 'Float', 'Currency', 'Percent'].includes(T)) return `<input type="number" step="any" name="${n}" value="${esc(v)}">`;
    if (['Small Text', 'Text', 'Long Text'].includes(T)) return `<textarea name="${n}" rows="3">${esc(v)}</textarea>`;
    if (T === 'Link') return `<input type="text" name="${n}" value="${esc(v)}" list="dl_${n}" data-link="${esc(f.options || '')}" autocomplete="off" placeholder="${esc(f.options || '')}"><datalist id="dl_${n}"></datalist>`;
    return `<input type="text" name="${n}" value="${esc(v)}">`;
  };
  const wbField = (f, cur) => `<label class="cc-field${f.type === 'Check' ? ' wb-check' : ''}"><span>${esc(f.label || f.fieldname)}${f.reqd ? ' <i class="wb-req">*</i>' : ''}</span>${wbInput(f, cur)}</label>`;
  const wbNorm = (f, o) => f.type === 'Check' ? (Number(o) ? 1 : 0) : f.type === 'Date' ? String(o || '').slice(0, 10) : f.type === 'Datetime' ? String(o || '').slice(0, 16).replace('T', ' ') : ['Int', 'Float', 'Currency', 'Percent'].includes(f.type) ? (o == null || o === '' ? '' : Number(o)) : (o == null ? '' : String(o));
  function wbCollect(form, fields, orig) {
    const out = {};
    fields.forEach(f => {
      const el = form.elements[f.fieldname]; if (!el) return;
      let v = f.type === 'Check' ? (el.checked ? 1 : 0) : el.value;
      if (['Int', 'Float', 'Currency', 'Percent'].includes(f.type)) v = v === '' ? null : Number(v);
      if (f.type === 'Datetime') v = v ? String(v).replace('T', ' ') : '';
      if (!orig) { if (!(v === '' || v === null || v === 0 && f.type === 'Check')) out[f.fieldname] = f.type === 'Datetime' && v.length === 16 ? v + ':00' : v; return; }
      if (String(wbNorm(f, v)) !== String(wbNorm(f, orig[f.fieldname]))) out[f.fieldname] = f.type === 'Datetime' && v.length === 16 ? v + ':00' : v;
    });
    return out;
  }
  function wbLinks(form) {
    form.querySelectorAll('input[data-link]').forEach(inp => {
      let t; inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(async () => {
        const q = inp.value; if (q.length < 1) return;
        try {
          const r = await fetch('/api/method/frappe.desk.search.search_link?doctype=' + encodeURIComponent(inp.dataset.link) + '&txt=' + encodeURIComponent(q) + '&page_length=10', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
          const j = await r.json(), list = j.results || j.message || [];
          form.querySelector('#' + inp.getAttribute('list')).innerHTML = list.map(x => `<option value="${esc(x.value)}">${esc(x.description || '')}</option>`).join('');
        } catch (e) { }
      }, 250); });
    });
  }
  function wbShowSheet(inner, sub, title) {
    const el = $('#ccsheet2');
    el.innerHTML = `<div class="cc-sheet wb-sheet"><div class="cc-sheet-h"><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div><button class="cc-x" data-close aria-label="Close">×</button></div><form id="wbform">${inner}</form></div>`;
    el.classList.add('on'); el.querySelector('[data-close]').onclick = closeSheet; el.onclick = e => { if (e.target === el) closeSheet(); };
    return el;
  }
  async function wbMeta(dt) { return WB.metas[dt] || (WB.metas[dt] = await gw('meta', { dt })); }
  function wbItems(doc) {
    const pref = ['item_code', 'item_name', 'qty', 'uom', 'rate', 'amount']; WB.itemsKey = null;
    for (const k of Object.keys(doc)) {
      const a = doc[k]; if (!Array.isArray(a) || !a.length || typeof a[0] !== 'object' || !('item_code' in a[0])) continue;
      WB.itemsKey = k;
      const cs = pref.filter(c => c in a[0] && !(c === 'item_name' && 'item_code' in a[0] && a[0].item_name === a[0].item_code));
      return `<div class="wb-sec">Line items</div><div class="card flush"><table class="wb-table"><thead><tr>${cs.map(c => `<th>${esc(c.replace('_', ' '))}</th>`).join('')}</tr></thead><tbody>${a.slice(0, 8).map(r => `<tr>${cs.map(c => `<td>${['rate', 'amount'].includes(c) ? money(Number(r[c])) : esc(r[c] == null ? '' : r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>${a.length > 8 ? `<div class="empty">+ ${a.length - 8} more · open in ERPNext to see all</div>` : ''}</div>`;
    }
    return '';
  }
  // C5: child tables, read-only (the gateway sends the first 25 rows and the child's list columns)
  function wbTables(g, dt, name) {
    const ts = (g.tables || []).filter(t => t.fieldname !== WB.itemsKey); if (!ts.length) return '';
    return `<div class="wb-sec">Child tables (read-only)</div>` + ts.map(t => `<details class="wb-ctab" ${t.count && ts.length < 3 ? 'open' : ''}><summary>${esc(t.label)} <b>${t.count}</b></summary>${t.count ? `<div class="card flush"><table class="wb-table"><thead><tr>${t.columns.map(c => `<th>${esc(c.label)}</th>`).join('') || '<th>Row</th>'}</tr></thead><tbody>${t.rows.map((r, i) => `<tr>${t.columns.map(c => `<td>${wbCell(c, r[c.fieldname])}</td>`).join('') || `<td>${i + 1}</td>`}</tr>`).join('')}</tbody></table>
      ${t.count > t.rows.length ? `<div class="empty">+ ${t.count - t.rows.length} more, <a target="_blank" rel="noopener" href="${docUrl(dt, name)}">open in ERPNext</a></div>` : ''}</div>` : '<div class="small" style="padding:4px 0 8px">No rows</div>'}</details>`).join('')
      + `<p class="small">${g.builder && catOK() ? 'Change these rows in the Catalog Builder (Edit in Catalog Builder below) or in ERPNext.' : 'Change these rows in ERPNext.'}</p>`;
  }
  async function wbOpen(dt, name) {
    WB.sheet = { dt, name };
    const el = wbShowSheet('<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>', '', esc(name));
    try {
      const [g, meta] = await Promise.all([gw('get', { dt, name }), wbMeta(dt)]);
      const doc = g.doc, L = wbL(dt), cols = (L.cols || WB.cfg.doctypes[dt].columns);
      // v9: a submitted document offers only the fields ERPNext lets change after submit (g.after_submit)
      const sub = doc.docstatus === 1, fields = sub ? meta.fields.filter(f => (g.after_submit || []).includes(f.fieldname)) : meta.fields;
      const canEdit = g.editable && fields.length;
      const why = g.read_only ? 'A generated or audit record, so it is read-only here.' : !WB.cfg.can_edit ? 'View only. Ask Kevin for the Command Center Editor role to edit.' : doc.docstatus !== 0 && !canEdit ? 'Submitted or cancelled, so it is read-only here. Open it in ERPNext to amend.' : '';
      const tog = g.status_kind === 'bool' && g.editable ? `<button class="cc-btn soft" type="button" id="wbtoggle" data-on="${doc.is_active ? 1 : 0}">${doc.is_active ? 'Deactivate' : 'Activate'}</button>` : '';
      const bld = g.builder && catOK() ? '<button class="cc-btn soft" type="button" id="wbbuilder">Edit in Catalog Builder</button>' : '';
      const kv = cols.filter(c => c.fieldname !== 'name' && !(c.fieldname === 'status' && doc.status)).map(c => `<div class="wb-kv"><span>${esc(c.label)}</span><b>${wbCell(c, doc[c.fieldname])}</b></div>`).join('');
      const req = sub ? fields : fields.filter(f => f.reqd), opt = sub ? [] : fields.filter(f => !f.reqd);
      const form = canEdit ? `<div class="wb-sec">Edit</div>${sub ? '<p class="wb-note">Submitted: only these fields can change after submit. Open it in ERPNext for anything else.</p>' : ''}${req.map(f => wbField(f, doc[f.fieldname])).join('')}${opt.length ? `<details class="wb-more-f"><summary>${opt.length} more fields</summary>${opt.map(f => wbField(f, doc[f.fieldname])).join('')}</details>` : ''}` : (why ? `<p class="wb-note">${esc(why)}</p>` : '');
      const aud = g.audit.length ? `<div class="wb-sec">Recent changes from the Command Center</div><ul class="wb-audit">${g.audit.map(a => `<li><span>${fmtd(a.creation)}</span> ${esc(wbPlain(a.content).replace(/^Command Center:\s*/, ''))}</li>`).join('')}</ul>` : '';
      const items = wbItems(doc);
      const sh = wbShowSheet(`<div class="wb-kvs">${kv}</div>${items}${wbTables(g, dt, name)}${form}${aud}<p class="cc-msg" id="wbMsg"></p>
        <div class="cc-sheet-f wb-foot"><a class="cc-btn soft" target="_blank" rel="noopener" href="${docUrl(dt, name)}" style="text-decoration:none">Open in ERPNext</a>${bld}${tog}${WB.cfg.can_edit && !agIsView() ? '<button class="cc-btn soft" type="button" id="wbagenda">+ Add to agenda</button>' : ''}<span style="flex:1"></span>${canEdit ? '<button class="cc-btn primary" type="submit" id="wbsave">Save changes</button>' : ''}</div>`,
        `${esc(wbLabel(dt))}${doc.status ? ' · ' + badge(doc.status, wbKind(doc.status)) : ''}${g.read_only ? ' · ' + badge('Read-only here', 'mute') : ''}`, esc(name));
      const f = sh.querySelector('#wbform'); wbLinks(f);
      const ab = sh.querySelector('#wbagenda'); if (ab) ab.onclick = () => agQuick(dt, name, doc, ab);
      const bb = sh.querySelector('#wbbuilder'); if (bb) bb.onclick = () => catOpen({ type: 'open', records: [{ doctype: dt, name }] });
      const tb = sh.querySelector('#wbtoggle'); if (tb) tb.onclick = async () => {
        const on = tb.dataset.on === '1' ? 0 : 1; tb.disabled = true;
        try { await gw('save', { dt, name, values: { is_active: on } }); toast(`${esc(name)} ${on ? 'activated' : 'deactivated'}`); wbFetch(dt, false); wbOpen(dt, name); }
        catch (err) { sh.querySelector('#wbMsg').textContent = 'Not saved: ' + err.message; tb.disabled = false; }
      };
      f.onsubmit = async e => {
        e.preventDefault(); if (!canEdit) return;
        const vals = wbCollect(f, fields, doc), msg = sh.querySelector('#wbMsg'), b = sh.querySelector('#wbsave');
        if (!Object.keys(vals).length) { msg.textContent = 'No changes to save.'; return; }
        b.disabled = true; b.textContent = 'Saving…'; msg.textContent = '';
        try { const r = await gw('save', { dt, name, values: vals }); closeSheet(); toast(`Saved ${esc(name)} · ${r.changed} field${r.changed === 1 ? '' : 's'} updated`); if (agIsView() && AG.cur) agLoad(AG.cur); else if (S.view === 'mfg' || S.view === 'ship') { FL.at = 0; flFetch(); if (S.view === 'mfg') { PB.at = 0; pbFetch(); } } else wbFetch(dt, false); }
        catch (err) { msg.textContent = 'Not saved: ' + err.message; b.disabled = false; b.textContent = 'Save changes'; }
      };
    } catch (e) { wbShowSheet(`<p class="cc-msg">Couldn't open ${esc(name)}: ${esc(e.message)}</p>`, '', esc(name)); }
  }
  async function wbNew(dt) {
    const info = (WB.cfg && WB.cfg.doctypes[dt]) || {};
    if (info.create === 'builder') {
      if (catOK()) { catOpen({ type: 'new', doctype: dt }); toast(`New ${esc(wbLabel(dt))}: opened in the Catalog Builder, so it gets a Check and an import receipt`); return; }
      wbShowSheet(`<div class="wb-banner">${esc(wbLabel(dt))} records are created in the Catalog Builder so every change is checked and logged. It needs the ilL Catalog Publisher role.</div>`, '', 'New ' + esc(wbLabel(dt))); return;
    }
    wbShowSheet('<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>', '', 'New ' + esc(wbLabel(dt)));
    try {
      const meta = await wbMeta(dt), blocked = meta.required_tables.length > 0, prompt = String(meta.autoname || '').toLowerCase() === 'prompt';
      const req = meta.fields.filter(f => f.reqd), opt = meta.fields.filter(f => !f.reqd);
      const sh = wbShowSheet(`${blocked ? `<div class="wb-banner">This needs line items (${esc(meta.required_tables.join(', '))}), which are added in ERPNext. <a target="_blank" rel="noopener" href="/app/${slug(dt)}/new">Create it in ERPNext ›</a></div>` : ''}
        ${blocked ? '' : `${prompt ? '<label class="cc-field"><span>Name <i class="wb-req">*</i></span><input type="text" name="__newname" autocomplete="off"></label>' : ''}${req.map(f => wbField(f, f.default)).join('')}${opt.length ? `<details class="wb-more-f" ${req.length ? '' : 'open'}><summary>${opt.length} more fields</summary>${opt.map(f => wbField(f, f.default)).join('')}</details>` : ''}
        <p class="cc-msg" id="wbMsg"></p><div class="cc-sheet-f"><button class="cc-btn primary" type="submit" id="wbsave">Create draft</button></div>`}`,
        'Saved as a draft in ERPNext. Nothing is submitted.', 'New ' + esc(wbLabel(dt)));
      const f = sh.querySelector('#wbform'); wbLinks(f);
      f.onsubmit = async e => {
        e.preventDefault(); if (blocked) return;
        const msg = sh.querySelector('#wbMsg'), b = sh.querySelector('#wbsave'), vals = wbCollect(f, meta.fields, null);
        const miss = req.filter(r => vals[r.fieldname] === undefined).map(r => r.label || r.fieldname);
        if (prompt) { const nn = String(f.elements.__newname.value || '').trim(); if (!nn) miss.unshift('Name'); else vals.__newname = nn; }
        if (miss.length) { msg.textContent = 'Fill in: ' + miss.join(', '); return; }
        b.disabled = true; b.textContent = 'Creating…'; msg.textContent = '';
        try { const r = await gw('create', { dt, values: vals }); closeSheet(); toast(`Created draft ${esc(r.name)} · <a target="_blank" rel="noopener" href="${docUrl(dt, r.name)}">Open</a>`); WB.counts = null; wbFetch(dt, false); }
        catch (err) { msg.textContent = 'Not created: ' + err.message; b.disabled = false; b.textContent = 'Create draft'; }
      };
    } catch (e) { wbShowSheet(`<p class="cc-msg">Couldn't load the form: ${esc(e.message)}</p>`, '', 'New ' + esc(wbLabel(dt))); }
  }

  /* ---- page glue ---- */
  function wbBody() {
    if (WB.cfgErr) return `<div class="err">Couldn't load the workbench: ${esc(WB.cfgErr)}. If this says the endpoint is missing, the "ilL Command Center Gateway" Server Script hasn't been added yet.</div>`;
    if (!WB.cfg) return '<div class="cc-loading"><span class="cc-spin"></span>Loading workbench…</div>';
    if (WB.dt && !WB.cfg.doctypes[WB.dt]) return `<div class="err">${esc(WB.dt)} isn't available to you here. <a href="#wb">Back to the workbench</a></div>`;
    return WB.dt ? wbListShell(WB.dt) : wbLanding();
  }
  function wbBind() {
    const r = $('#wbroot'); if (!r) return;
    bindSV();
    r.querySelectorAll('[data-wbdt]').forEach(b => b.onclick = () => { WB.from = { dt: b.dataset.wbdt, sec: b.dataset.wbfrom || null }; location.hash = 'wb/' + encodeURIComponent(b.dataset.wbdt); });
    r.querySelectorAll('[data-wbarea]').forEach(b => b.onclick = () => { location.hash = 'wb/~' + b.dataset.wbarea; });
    const iq = r.querySelector('#wbillq'); if (iq) iq.oninput = () => { WB.iq = iq.value.trim(); const g = r.querySelector('#wbillgrid'); if (g) { g.innerHTML = wbIllCards(); g.querySelectorAll('[data-wbdt]').forEach(b => b.onclick = () => { WB.from = { dt: b.dataset.wbdt, sec: b.dataset.wbfrom || null }; location.hash = 'wb/' + encodeURIComponent(b.dataset.wbdt); }); wbICounts(g); } };
    if (!WB.dt && WB.area === 'ill' && WB.cfg) wbICounts(r);
    const n = r.querySelector('#wbnew'); if (n) n.onclick = () => wbNew(WB.dt);
    const q = r.querySelector('#wbq'); if (q) { let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { const L = wbL(WB.dt); L.search = q.value.trim(); wbFetch(WB.dt, false); }, 300); }; }
    wbData();
  }
  async function wbCounts() {
    if (WB.cbusy || !WB.cfg) return; WB.cbusy = true; let c = {};
    try { c = (await gw('counts')).counts || {}; Object.keys(c).forEach(k => { if (c[k] == null) c[k] = '—'; }); }
    catch (e) { await Promise.all(Object.keys(WB.cfg.doctypes).filter(d => wbSecs(WB.cfg.doctypes[d]).some(k => !/^ill_/.test(k))).map(async d => { try { c[d] = (await gw('list', { dt: d, limit: 1 })).total; } catch (e2) { c[d] = '—'; } })); }
    WB.counts = c; WB.cbusy = false; if (wbIsView() && !WB.dt) { const r = $('#wbroot'); if (r) { r.innerHTML = wbBody(); wbBind(); } }
  }
  async function wbEnsure() {
    if (!WB.cfg && !WB.cfgBusy) { WB.cfgBusy = true; try { WB.cfg = await gw('config'); WB.cfgErr = null; } catch (e) { WB.cfgErr = e.message; } WB.cfgBusy = false; }
    if (!wbIsView()) return;
    const r = $('#wbroot'); if (r && !r.dataset.drawn) { r.innerHTML = wbBody(); wbBind(); }
    if (!WB.cfg) return;
    if (WB.dt && WB.cfg.doctypes[WB.dt]) { const L = wbL(WB.dt); if (!L.loaded && !L.loading) wbFetch(WB.dt, false); }
    else if (!WB.dt && WB.area !== 'ill' && !WB.counts) wbCounts();
  }
  WB.html = v => {
    WB.dt = wbRoute(v); const pre = String(v || '').split('/')[2], area = wbAreaOf(v);
    if (area) { WB.area = area; try { localStorage.setItem('cc.wb.area.' + USER, area); } catch (e) { } }
    if (WB.dt && pre !== undefined && WB.preApplied !== v) { WB.preApplied = v; const L = wbL(WB.dt), st = decodeURIComponent(pre); if (L.status !== st) { L.status = st; L.loaded = false; L.rows = []; } }
    return `<div id="wbroot" ${WB.cfg || WB.cfgErr ? 'data-drawn="1"' : ''}>${wbBody()}</div>`; };
  WB.mount = () => { wbBind(); wbEnsure(); };

  /* ---------------- saved views (per person, per browser) ----------------
     Filters/search/sort can be named and re-applied. Stored in this browser's localStorage under the
     signed-in user's name, so they don't follow someone to another computer. */
  const SV = {
    key: s => 'cc.views.' + USER + '.' + s,
    list(scope) { try { return JSON.parse(localStorage.getItem(SV.key(scope)) || '[]'); } catch (e) { return []; } },
    put(scope, arr) { try { localStorage.setItem(SV.key(scope), JSON.stringify(arr)); return true; } catch (e) { return false; } }
  };
  const svOpts = scope => '<option value="">Saved views…</option>' + SV.list(scope).map((v, i) => `<option value="${i}">${esc(v.name)}</option>`).join('');
  const viewsBar = scope => `<span class="sv no-print" data-sv="${esc(scope)}"><select data-svpick>${svOpts(scope)}</select><button type="button" class="cc-btn soft" data-svsave>Save view</button><button type="button" class="cc-btn soft" data-svdel title="Delete the selected view">✕</button></span>`;
  function svHandlers(scope) {
    if (scope === 'tasks') return {
      get: () => ({ person: S.person, source: S.source, status: S.status, mine: S.mine }),
      apply: s => { Object.assign(S, { person: '', source: '', status: '', mine: false }, s); S.limit = 30; render(); }
    };
    if (scope.startsWith('wb:')) { const dt = scope.slice(3); return {
      get: () => { const L = wbL(dt); return { status: L.status, search: L.search, order: L.order }; },
      apply: s => { const L = wbL(dt); L.status = s.status || ''; L.search = s.search || ''; L.order = s.order || 'modified desc'; const q = $('#wbq'); if (q) q.value = L.search; wbFetch(dt, false); }
    }; }
    return null;
  }
  function bindSV() {
    root.querySelectorAll('.sv[data-sv]').forEach(el => {
      const scope = el.dataset.sv, h = svHandlers(scope), sel = el.querySelector('[data-svpick]'); if (!h) return;
      sel.onchange = () => { const v = SV.list(scope)[+sel.value]; if (sel.value !== '' && v) h.apply(v.state); };
      el.querySelector('[data-svsave]').onclick = () => {
        const name = (window.prompt('Name this view (for example "Overdue, mine")') || '').trim(); if (!name) return;
        const arr = SV.list(scope).filter(x => x.name !== name); arr.push({ name, state: h.get() });
        if (!SV.put(scope, arr)) { toast('This browser would not save the view'); return; }
        sel.innerHTML = svOpts(scope); sel.value = String(arr.length - 1); toast('Saved view “' + esc(name) + '”');
      };
      el.querySelector('[data-svdel]').onclick = () => {
        if (sel.value === '') return; const arr = SV.list(scope); arr.splice(+sel.value, 1); SV.put(scope, arr); sel.innerHTML = svOpts(scope); toast('View deleted');
      };
    });
  }

  /* ---------------- shared bits for the executive and review pages ---------------- */
  const feedList = (rows, empty) => (rows = (rows || []).filter(a => !(S.meeting && a.reference_doctype === 'ToDo'))).length
    ? `<ul class="wb-audit">${rows.map(a => `<li><span>${fmtd(a.creation)}</span> <b>${esc(SHORT[a.owner] || String(a.owner || '').split('@')[0])}</b> · ${link(a.reference_doctype, a.reference_name)} — ${esc(wbPlain(a.content).replace(/^Command Center:\s*/, '').slice(0, 160))}</li>`).join('')}</ul>`
    : `<div class="empty" style="padding:8px">${empty}</div>`;
  const printBtn = id => `<button class="cc-btn soft" id="${id}">Print / PDF</button>`;

  /* ---------------- executive overview (phase 3) ----------------
     Pipeline value and "decisions" come from the gateway's overview action (so they respect each
     person's ERPNext permissions and the Finance role). Break-even, SPIF and ticket age come from
     the data the page already loads. Finance numbers fail closed: hidden until the gateway says yes. */
  const EX = { data: null, err: null, busy: false, at: 0, feed: null };
  const EX_OPEN = { 'Quotation': /^Open$/i, 'Sales Order': /^To Deliver/i, 'Purchase Order': /^To Receive/i, 'Sales Invoice': /^(Unpaid|Overdue|Partly Paid)/i };
  const exStage = dt => {
    const s = EX.data && EX.data.stats && EX.data.stats[dt]; if (!s || !EX_OPEN[dt]) return null;
    const open = s.statuses.filter(x => EX_OPEN[dt].test(x[0]));
    return { n: open.reduce((a, x) => a + x[1], 0), v: open.reduce((a, x) => a + x[2], 0) };
  };
  const lockedStat = (title, why) => stat(title, '🔒', why).replace('card stat', 'card stat locked');
  EX.body = () => {
    const m = CUR_M || M(), p = pipeData(m), X = EX.data, fin = X ? X.finance_ok : null;
    const qs = exStage('Quotation'), os = exStage('Sales Order');
    const finWhy = EX.err ? 'Unavailable right now' : fin === false ? 'Needs the Command Center Finance role' : 'Loading…';
    const kpis = [
      stat('New dealers this month', `${m.newThis.length}<span class="small"> / 8</span>`, `${m.new3k.length} at $3K+ · on pace by today: ${(8 * m.pace).toFixed(1)}`, '', meter(m.newThis.length / 8, m.pace)),
      stat('Quotes out', qs ? qs.n : p.qOut.length, money(qs ? qs.v : p.qVal) + ' waiting on dealers'),
      stat('Open sales orders', os ? os.n : D.ship.length, money(os ? os.v : p.soVal) + ' still to deliver'),
      fin === true ? stat('Invoiced this month', money(D.fin.mtd), `${Math.round(D.fin.mtd / D.fin.goal * 100)}% of ${money(D.fin.goal)} target`, '', meter(D.fin.mtd / D.fin.goal, m.pace)) : lockedStat('Invoiced this month', finWhy),
      fin === true ? stat('Receivables', money(D.fin.ar), `${D.ar.length} open invoices`) : lockedStat('Receivables', finWhy),
      stat('Tickets waiting over 2 days', m.tOld.length, `${m.tOpen.length} open in total`, m.tOld.length ? 'bad' : ''),
    ];
    const bars = [], add = (dt, label, color, status) => { const s = exStage(dt); if (s) bars.push({ html: `<a href="#wb/${encodeURIComponent(dt)}${status ? '/' + encodeURIComponent(status) : ''}">${label}</a>`, value: s.v, color, title: s.n + ' records' }); };
    add('Quotation', 'Quotes out', '#2a78d6', 'Open'); add('Sales Order', 'Open sales orders', '#4c90e1'); add('Purchase Order', 'Open purchase orders (spend)', '#eda100'); add('Sales Invoice', 'Invoices outstanding', '#067647');
    const dec = [];
    if (X) X.signals.forEach(s => dec.push({ n: s.count, l: s.label, href: '#wb/' + encodeURIComponent(s.dt) + (s.status ? '/' + encodeURIComponent(s.status) : ''), tone: s.count ? s.tone : 'clear' }));
    dec.push({ n: m.late.length, l: 'Material lines past their order-by date', href: '#purch', tone: m.late.length ? 'bad' : 'clear' });
    dec.push({ n: p.qDraft.length, l: 'Quote drafts not sent yet', href: '#quotes', tone: p.qDraft.length ? 'warn' : 'clear' });
    dec.push({ n: m.dup.length, l: 'Duplicate or stale work orders', href: '#mfg', tone: m.dup.length ? 'warn' : 'clear' });
    dec.push({ n: m.spifQ.length, l: 'Orders qualifying for SPIF', href: '#pipeline', tone: m.spifQ.length ? 'info' : 'clear' });
    const rank = { bad: 0, warn: 1, info: 2, clear: 3 };
    dec.sort((a, b) => rank[a.tone] - rank[b.tone] || b.n - a.n);
    const waiting = D.tk.filter(t => t.status === 'Open' || t.status === 'Replied');
    const ageRows = [['0–2 days', 0, 2], ['3–5 days', 3, 5], ['6–10 days', 6, 10], ['Over 10 days', 11, 1e9]].map(([l, a, b]) => ({ label: l, value: waiting.filter(t => t.age >= a && t.age <= b).length, color: b > 10 ? '#eb6834' : '#2a78d6' }));
    const note = (D.notes || {})['Command Center – This week'];
    return `<div class="ex-kpis">${kpis.join('')}</div><div class="grid">
      ${card('Pipeline value by stage', 'Open records only. Click a bar to see them in the Workbench.', hbars(bars, { lw: '220px', fmt: kfmt }) + (EX.err ? `<p class="small">Live stage values are unavailable: ${esc(EX.err)}</p>` : !X ? '<p class="small">Loading…</p>' : ''), 's8')}
      ${card('Break-even this month', '8 new dealers, each ordering $3K+', `<div class="ring-wrap" style="margin-top:4px">${ring(m.newThis.length, 8, '#2a78d6', 'new dealers', 112)}<div><div class="small">At $3K+ this month</div><div style="font-size:20px;font-weight:700">${m.new3k.length}</div><div class="small" style="margin-top:8px">Active dealers (90 days)</div><div style="font-size:20px;font-weight:700">${D.active90}</div><div class="small" style="margin-top:8px">SPIF qualifying orders</div><div style="font-size:20px;font-weight:700">${m.spifQ.length}</div></div></div>`, 's4')}
      ${card('Decisions this week', 'Late, expiring or stuck. Click one to see the records.', `<div class="dec-grid">${dec.map(d => `<a class="dec ${d.tone}" href="${d.href}"><span class="n">${d.n}</span><span class="l">${esc(d.l)}</span></a>`).join('')}</div>${EX.err ? `<p class="small" style="margin-top:10px">Some counts are missing: ${esc(EX.err)}</p>` : !X ? '<p class="small" style="margin-top:10px">Loading the rest…</p>' : ''}`, 's12')}
      ${card('How long tickets have waited', 'Open and replied tickets, business days since created', hbars(ageRows, { lw: '120px' }), 's4')}
      ${card('This week', '', `<div class="note">${note || '<div class="empty">No note yet</div>'}</div>`, 's4', `<span class="calc">${noteLink('Command Center – This week')}</span>`)}
      ${card('Recent changes', 'Made from the Command Center, newest first', EX.feed ? feedList(EX.feed.slice(0, 12), 'No changes made from the Command Center yet.') : (EX.err ? '<div class="empty">Unavailable</div>' : '<div class="empty">Loading…</div>'), 's4')}
    </div>`;
  };
  EX.html = () => header('Executive overview', 'Where the pipeline stands, how far we are from break-even, and what needs a decision this week.',
    `<div class="toolbar no-print"><button class="cc-btn soft" id="exrefresh">Refresh</button>${printBtn('exprint')}</div>`) + `<div id="exroot">${EX.body()}</div>`;
  async function exFetch(manual) {
    if (EX.busy) return; EX.busy = true; EX.err = null;
    try { const [o, f] = await Promise.all([gw('overview'), gw('feed', { limit: 30 })]); EX.data = o; EX.feed = f.rows; EX.at = Date.now(); if (manual) toast('Executive view refreshed'); }
    catch (e) { EX.err = e.message; }
    EX.busy = false;
    if (S.view === 'exec') { const r = $('#exroot'); if (r) r.innerHTML = EX.body(); }
  }
  EX.mount = () => {
    const r = $('#exrefresh'); if (r) r.onclick = () => exFetch(true);
    const p = $('#exprint'); if (p) p.onclick = () => window.print();
    if (!EX.busy && (!EX.data || Date.now() - EX.at > 120000)) exFetch();
  };

  /* ---------------- project review mode (phase 4) ----------------
     Step 0 is the overview of every active project; then one page per project. Arrow keys move
     between them. "Print / PDF" lays every project out one per page for the meeting pack. */
  const RV = { i: 0, all: false, feed: null, fbusy: false };
  const rvProjects = () => D.projects.filter(p => p.status === 'Open' && p.tasks.length).sort((a, b) => b.over - a.over || String(a.end || '9').localeCompare(String(b.end || '9')));
  const rvLive = p => p.tasks.filter(t => t.status !== 'Completed' && t.status !== 'Cancelled');
  const rvWeek = t => t.end && t.end >= TODAY && t.end <= addDays(TODAY, 7);
  function rvOverview(ps) {
    const live = ps.flatMap(rvLive);
    const rows = ps.map((p, k) => { const lv = rvLive(p);
      return `<tr data-rvgo="${k + 1}" style="cursor:pointer"><td><b style="font-weight:600">${esc(p.project_name)}</b><div class="m">${esc(p.name)}${p.customer ? ' · ' + esc(p.customer) : ''}</div></td>
        <td style="min-width:140px">${statusBar(p.tasks)}<div class="m">${p.done}/${p.tasks.length} done · ${p.pct}%</div></td>
        <td class="num">${p.over ? badge(p.over, 'bad') : 0}</td><td class="num">${lv.filter(rvWeek).length}</td><td class="num">${lv.filter(t => !t.owners.length).length || 0}</td>
        <td>${p.next ? esc(p.next.subject) + `<div class="m">${fmtd(p.next.end)}</div>` : '<span class="calc">—</span>'}</td><td>${avs(p.team)}</td></tr>`; });
    return `<section class="rv-step"><div class="grid" style="margin-bottom:20px">
      ${stat('Active projects', ps.length, '').replace('card stat', 'card stat s3')}
      ${stat('Open tasks', live.length, '').replace('card stat', 'card stat s3')}
      ${stat('Overdue', live.filter(tOver).length, 'Past their end date', live.some(tOver) ? 'bad' : '').replace('card stat', 'card stat s3')}
      ${stat('Due in the next 7 days', live.filter(t => rvWeek(t) && !tOver(t)).length, '').replace('card stat', 'card stat s3')}
      ${tableCard('Every active project', 'Most overdue first. Click one to review it.', ['Project', 'Progress', '#Overdue', '#Due in 7 days', '#No owner', 'Next milestone', 'Team'], rows, '', 's12')}</div></section>`;
  }
  function rvProject(p, k, n) {
    const live = rvLive(p), over = live.filter(tOver), week = live.filter(t => rvWeek(t) && !tOver(t)), un = live.filter(t => !t.owners.length);
    const blocked = live.filter(t => (t.deps || []).some(d => { const x = D.ptasks.find(y => y.name === d); return x && x.status !== 'Completed'; }));
    const done = p.tasks.filter(t => t.status === 'Completed');
    const row = t => `<div class="todo-r rv-task" data-task="${esc(t.name)}" style="cursor:pointer"><span>${avs(t.owners)}</span><span>${esc(t.subject)}</span>${t.end ? (tOver(t) ? badge(fmtd(t.end), 'bad') : `<span class="small">${fmtd(t.end)}</span>`) : ''}</div>`;
    const lst = (title, sub, arr, empty) => card(title, sub, (arr.slice(0, 10).map(row).join('') || `<div class="empty" style="padding:8px">${empty}</div>`) + (arr.length > 10 ? `<div class="small" style="margin-top:6px">+ ${arr.length - 10} more · see the board</div>` : ''), 's6');
    const chg = (RV.feed || []).filter(r => (r.reference_doctype === 'Project' && r.reference_name === p.name) || (r.reference_doctype === 'Task' && p.tasks.some(t => t.name === r.reference_name))).slice(0, 8);
    const team = p.team.map(u => { const o = live.filter(t => t.owners.includes(u)), ov = o.filter(tOver);
      return `<div style="display:flex;align-items:center;gap:10px;padding:4px 0">${avatar(u)}<span style="flex:1">${esc(SHORT[u] || u)}</span><span class="small">${o.length} open${ov.length ? ` · <b style="color:var(--badt)">${ov.length} overdue</b>` : ''}</span></div>`; }).join('') || '<span class="calc">Nobody assigned yet</span>';
    return `<section class="rv-step">
      <div class="rv-head"><div><div class="eyebrow">Project ${k} of ${n} · ${esc(p.name)}${p.customer ? ' · ' + esc(p.customer) : ''}</div><h2 class="rv-title">${esc(p.project_name)}</h2>
        <div class="small">${p.start ? fmtd(p.start) : '—'} → ${p.end ? fmtd(p.end) : 'no end date'}${p.priority ? ' · ' + esc(p.priority) + ' priority' : ''}</div></div>${ringPct(p.pct, 84)}</div>
      <div class="toolbar no-print" style="margin:12px 0 16px">${pBtn('+ Add task', `data-newtask="${esc(p.name)}"`, true)}<a class="cc-btn soft" href="#p-${esc(p.name)}" style="text-decoration:none">Board &amp; timeline</a><a class="cc-btn soft" target="_blank" rel="noopener" href="/app/project/${encodeURIComponent(p.name)}" style="text-decoration:none">Open in ERPNext</a></div>
      <div class="grid" style="margin-bottom:20px">
        ${stat('Done', `${p.done}<span class="small"> / ${p.tasks.length}</span>`, 'tasks').replace('card stat', 'card stat s3')}
        ${stat('Overdue', over.length, 'Past their end date', over.length ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Due in 7 days', week.length, '').replace('card stat', 'card stat s3')}
        ${stat('No owner', un.length, `${blocked.length} waiting on other tasks`, un.length ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${lst('Overdue', 'Decide: re-date, reassign or drop', over, 'Nothing overdue')}
        ${lst('Due in the next 7 days', '', week, 'Nothing due this week')}
        ${lst('Needs an owner', 'Open tasks nobody is assigned to', un, 'Everything has an owner')}
        ${lst('Waiting on other tasks', 'Blocked until a dependency is completed', blocked, 'Nothing blocked')}
        ${card('Team load', 'Open tasks per person', team, 's6')}
        ${card('Recent changes', 'Made from the Command Center', RV.feed === null ? '<div class="empty">Loading…</div>' : feedList(chg, RV.feedErr ? 'Change log unavailable.' : 'No changes made from the Command Center yet.'), 's6')}
        ${p.notes ? card('About this project', '', `<div class="small" style="color:var(--ink2)">${p.notes}</div>`, 's12') : ''}
        ${done.length ? card('Completed', `${done.length} task${done.length > 1 ? 's' : ''}`, `<div class="small" style="color:var(--ink2);line-height:1.8">${done.slice(0, 12).map(t => '✓ ' + esc(t.subject)).join('<br>')}${done.length > 12 ? `<br>+ ${done.length - 12} more` : ''}</div>`, 's12') : ''}
      </div></section>`;
  }
  RV.html = () => {
    const ps = rvProjects(); if (RV.i > ps.length) RV.i = 0;
    const names = ['Overview'].concat(ps.map(p => p.project_name));
    const nav = `<div class="rv-nav no-print"><button class="cc-btn soft" data-rv="-1" ${RV.i === 0 || RV.all ? 'disabled' : ''}>◀ Previous</button>
      <select data-rvpick ${RV.all ? 'disabled' : ''}>${names.map((n, k) => `<option value="${k}" ${k === RV.i ? 'selected' : ''}>${k ? k + '. ' : ''}${esc(n)}</option>`).join('')}</select>
      <button class="cc-btn soft" data-rv="1" ${RV.i === ps.length || RV.all ? 'disabled' : ''}>Next ▶</button>
      <label class="cc-switch" style="color:var(--ink2)"><input type="checkbox" id="rvall" ${RV.all ? 'checked' : ''}><span style="background:${RV.all ? '#f39c12' : '#d0d5dd'}"></span>All projects on one page</label>
      <span class="small">Tip: use the ← → keys</span></div>`;
    const body = RV.all ? rvOverview(ps) + ps.map((p, k) => rvProject(p, k + 1, ps.length)).join('') : (RV.i === 0 ? rvOverview(ps) : rvProject(ps[RV.i - 1], RV.i, ps.length));
    return header('Project review', 'Walk through every active project for the Tuesday review: what is overdue, what is due, who has too much, who has nothing.',
      `<div class="toolbar no-print">${printBtn('rvprint')}</div>`) + nav + `<div id="rvroot">${body}</div>`;
  };
  function rvGo(i) { RV.i = Math.max(0, Math.min(rvProjects().length, i)); render(); window.scrollTo({ top: 0 }); }
  function rvPrint() { const was = RV.all; RV.all = true; render(); setTimeout(() => { window.print(); RV.all = was; render(); }, 60); }
  async function rvFeed() {
    RV.fbusy = true;
    try { RV.feed = (await gw('feed', { dts: ['Task', 'Project'], limit: 100 })).rows; RV.feedErr = null; } catch (e) { RV.feed = []; RV.feedErr = e.message; }
    RV.at = Date.now();
    RV.fbusy = false; if (S.view === 'review') render();
  }
  RV.mount = () => {
    root.querySelectorAll('[data-rv]').forEach(b => b.onclick = () => rvGo(RV.i + +b.dataset.rv));
    root.querySelectorAll('[data-rvgo]').forEach(el => el.onclick = () => rvGo(+el.dataset.rvgo));
    const sel = $('[data-rvpick]'); if (sel) sel.onchange = () => rvGo(+sel.value);
    const al = $('#rvall'); if (al) al.onchange = () => { RV.all = al.checked; render(); };
    const pr = $('#rvprint'); if (pr) pr.onclick = rvPrint;
    if (!RV.fbusy && (RV.feed === null || Date.now() - (RV.at || 0) > 120000)) rvFeed();
  };

  /* ---------------- weekly meeting agenda ----------------
     Replaces the shared Google Doc. Meetings and their items live in ERPNext (ilL-Meeting-Agenda and
     ilL-Meeting-Agenda-Item) behind the gateway's agenda_* actions, so everyone sees the same list.
     An item is free text or linked to any record the Command Center can show (to-dos, tasks, sales
     orders, quotes, tickets, ...); linked items show that record's live status, and once an item is
     marked discussed its outcome is written to the linked record's timeline. */
  const AG = { list: null, listErr: null, lbusy: false, canEdit: false, cur: null, data: null, err: null, errFor: null, dbusy: false, at: 0,
    pick: { tab: 'suggested', dt: '', q: '', rows: null, cols: null, busy: false, err: null, cands: [] } };
  const agIsView = () => String(S.view || '').split('/')[0] === 'agenda';
  const agRoute = () => { const p = String(S.view || '').split('/'); return p[1] ? decodeURIComponent(p[1]) : null; };
  const agDate = d => d ? new Date(String(d).slice(0, 10) + 'T12:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) : '—';
  const agLoading = '<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>';
  // with no meeting picked: the next open one from today on, otherwise the most recent
  function agDefault() {
    const ms = AG.list || [];
    const up = ms.filter(m => m.status === 'Open' && String(m.meeting_date) >= TODAY).sort((a, b) => String(a.meeting_date).localeCompare(String(b.meeting_date)));
    return (up[0] || ms[0] || {}).name || null;
  }
  // what a linked record is called: its subject/description, or its type + ID + party
  const AG_OWN = ['subject', 'project_name', 'description'], AG_PARTY = ['customer_name', 'customer', 'party_name', 'supplier', 'production_item', 'material_request_type'];
  function agTitle(dt, name, row) {
    row = row || {};
    for (const f of AG_OWN) { const t = wbPlain(row[f]); if (t) return t.length > 120 ? t.slice(0, 120) + '…' : t; }
    const id = wbLabel(dt) + ' ' + short(name);
    for (const f of AG_PARTY) { const t = wbPlain(row[f]); if (t) return id + ' · ' + (t.length > 80 ? t.slice(0, 80) + '…' : t); }
    return id;
  }
  const agRow = it => it.reference_doctype && it.reference_name && AG.data ? (AG.data.refs || {})[it.reference_doctype + '|' + it.reference_name] : null;
  const agHidden = it => it.reference_doctype === 'ToDo' && wbPrivate('ToDo', agRow(it) || {});
  const agOn = (dt, name) => !!(AG.data && AG.data.items.some(it => it.reference_doctype === dt && it.reference_name === name));
  const agVisible = () => AG.data ? AG.data.items.filter(it => !agHidden(it)) : [];

  function agRef(it) {
    if (!it.reference_doctype || !it.reference_name) return '';
    const dt = it.reference_doctype, row = agRow(it), cols = (AG.data.columns || {})[dt] || [], bits = [];
    if (row) {
      const val = cols.find(c => c.type === 'Currency' && row[c.fieldname] != null); if (val) bits.push(money(Number(row[val.fieldname])));
      const dc = cols.find(c => c.type === 'Date' && row[c.fieldname]); if (dc) bits.push(esc(dc.label) + ' ' + fmtd(row[dc.fieldname]));
      if (row.allocated_to) bits.push(esc(SHORT[row.allocated_to] || row.allocated_to));
    }
    const canOpen = WB.cfg && WB.cfg.doctypes[dt] && row;
    return `<div class="ag-ref"><span class="ag-dt">${esc(wbLabel(dt))}</span>${link(dt, it.reference_name, short(it.reference_name))}${row && row.status ? badge(row.status, wbKind(row.status)) : ''}${bits.map(b => `<span class="small">${b}</span>`).join('')}${row ? '' : '<span class="calc">details not available to you</span>'}${canOpen ? '<button type="button" class="ag-open no-print" data-agopen>Details</button>' : ''}</div>`;
  }
  const agMade = it => { try { const v = JSON.parse(it.todo_names || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; } };
  function agTodos(it) {
    const made = agMade(it); if (!made.length) return '';
    return `<ul class="ag-todos">${made.map(t => {
      const live = (AG.data.todos || {})[t.name], st = live ? live.status : null, done = st === 'Closed' || st === 'Cancelled', due = (live && live.date) || t.date;
      return `<li class="${done ? 'done' : ''}"><span class="ag-tdk">${done ? '✓' : '○'}</span>${link('ToDo', t.name, t.title)}<span class="small">${esc(SHORT[t.owner] || t.owner)}${due ? ' · due ' + fmtd(due) : ''}${st ? ' · ' + esc(st) : ''}</span></li>`;
    }).join('')}</ul>`;
  }
  function agItem(it, i, n, ed) {
    const done = it.status === 'Discussed';
    return `<div class="ag-item ${done ? 'done' : ''}" data-agid="${esc(it.name)}">
      <div class="ag-num">${done ? '✓' : i + 1}</div>
      <div class="ag-body">
        <div class="ag-line"><span class="ag-title" ${ed ? 'data-agedit title="Edit this item"' : ''}>${esc(it.item_title)}</span>${it.carried_from ? '<span class="badge info">Carried over</span>' : ''}${it.presenter ? avatar(it.presenter) : ''}</div>
        ${it.details ? `<div class="ag-det">${esc(it.details)}</div>` : ''}
        ${agRef(it)}
        ${ed ? `<div class="ag-outrow no-print"><textarea class="ag-out" data-agout rows="1" placeholder="Outcome or decision…">${esc(it.outcome || '')}</textarea><button type="button" class="cc-btn soft" data-agtodo title="Turn this outcome into to-dos for the owners">+ To-do</button></div>` : ''}
        ${it.outcome ? `<div class="ag-outp${ed ? ' print-only' : ''}"><b>Outcome:</b> ${esc(it.outcome)}</div>` : ''}
        ${agTodos(it)}
      </div>
      ${ed ? `<div class="ag-ctl no-print"><label class="ag-chk"><input type="checkbox" data-agdone ${done ? 'checked' : ''}>Discussed</label>
        <span class="ag-mv"><button type="button" class="cc-btn soft" data-agmv="-1" ${i === 0 ? 'disabled' : ''} title="Move up" aria-label="Move up">↑</button><button type="button" class="cc-btn soft" data-agmv="1" ${i === n - 1 ? 'disabled' : ''} title="Move down" aria-label="Move down">↓</button></span>
        <button type="button" class="cc-btn soft" data-agedit>Edit</button></div>` : ''}
    </div>`;
  }
  AG.body = () => {
    if (AG.listErr) return `<div class="err">Couldn't load the agenda: ${esc(AG.listErr)}</div>`;
    if (!AG.list) return agLoading;
    const ed = AG.canEdit;
    if (!AG.list.length) return `<div class="card ag-empty"><h2>No meeting agendas yet</h2><p class="small">Start one for this week's meeting. Everyone with Command Center access sees the same agenda.</p>
      ${ed ? '<button class="cc-btn primary" data-agnew>Start this week\'s agenda</button>' : '<p class="small">Ask Kevin for the Command Center Editor role to start one.</p>'}</div>`;
    const bar = `<div class="ag-bar no-print"><select data-agpick aria-label="Meeting">${AG.list.map(m => `<option value="${esc(m.name)}" ${m.name === AG.cur ? 'selected' : ''}>${esc(agDate(m.meeting_date))} · ${esc(m.title)}${m.status === 'Closed' ? ' (closed)' : ''} · ${m.items} item${m.items === 1 ? '' : 's'}</option>`).join('')}</select>
      ${ed ? '<button class="cc-btn soft" data-agnew>+ New meeting</button>' : ''}<span style="flex:1"></span><button class="cc-btn soft" data-agcopy>Copy as text</button>${printBtn('agprint')}</div>`;
    const X = AG.data;
    if (AG.err && AG.errFor === AG.cur) return bar + `<div class="err">Couldn't load this meeting: ${esc(AG.err)}</div>`;
    if (!X || X.agenda.name !== AG.cur) return bar + agLoading;
    const ag = X.agenda, items = agVisible(), hidden = X.items.length - items.length, edit = X.can_edit, open = ag.status === 'Open';
    const done = items.filter(i => i.status === 'Discussed').length;
    const head = `<div class="card ag-head"><div class="ag-hrow"><div><div class="eyebrow">${esc(agDate(ag.meeting_date))}</div><h2 class="rv-title">${esc(ag.title)}</h2>
        <div class="small">${items.length} item${items.length === 1 ? '' : 's'} · ${done} discussed${hidden ? ` · ${hidden} hidden in meeting mode` : ''}</div></div>
        <div class="ag-hact">${badge(open ? 'Open' : 'Closed', open ? 'warn' : 'good')}${edit ? `<button class="cc-btn soft no-print" data-agclose>${open ? 'Close meeting' : 'Reopen'}</button>` : ''}</div></div>
      ${items.length ? meter(done / items.length, null, 'var(--good)') : ''}
      ${edit ? `<label class="cc-field ag-notes no-print"><span>Meeting notes</span><textarea data-agnotes rows="2" placeholder="Anything that isn't tied to one item">${esc(ag.notes)}</textarea></label>` : ''}
      ${ag.notes ? `<div class="ag-det${edit ? ' print-only' : ''}" style="margin-top:10px"><b>Notes:</b> ${esc(ag.notes)}</div>` : ''}</div>`;
    const me = TEAM.some(u => u.name === USER) ? USER : '';
    const add = edit ? `<form class="ag-add no-print" id="agaddf"><input type="text" id="agaddt" placeholder="Add an item and press Enter" maxlength="140" autocomplete="off">
      <select id="agaddp" aria-label="Who brings it"><option value="">Who brings it?</option>${TEAM.map(u => `<option value="${esc(u.name)}" ${u.name === me ? 'selected' : ''}>${esc(u.full_name || u.name)}</option>`).join('')}</select>
      <button class="cc-btn primary" type="submit">Add</button><button class="cc-btn soft" type="button" data-agpicker>+ Add from ERPNext</button></form>` : '';
    const list = items.length ? `<div class="ag-list">${items.map((it, i) => agItem(it, i, items.length, edit)).join('')}</div>`
      : `<div class="card"><div class="empty">Nothing on this agenda yet.${edit ? ' Type an item above, or use “+ Add from ERPNext” to pull in to-dos, orders, quotes or tickets.' : ''}</div></div>`;
    return bar + head + add + list + (!edit ? '<p class="small" style="margin-top:12px">View only. Ask Kevin for the Command Center Editor role to add items.</p>' : '');
  };
  AG.html = () => {
    if (AG.list && AG.cur && !agRoute() && !AG.list.some(m => m.name === AG.cur)) AG.cur = null;
    AG.cur = agRoute() || AG.cur || agDefault();
    return header('Meeting agenda', 'The weekly meeting agenda, kept in ERPNext. Add topics, pull in to-dos, orders, quotes or tickets, then record what was decided.') + `<div id="agroot">${AG.body()}</div>`;
  };
  function agRedraw() {
    if (!agIsView()) return; const r = $('#agroot'); if (!r) return;
    AG.cur = agRoute() || AG.cur || agDefault(); r.innerHTML = AG.body(); agBind();
  }
  async function agList() {
    AG.lbusy = true;
    try { const r = await gw('agenda_list'); AG.list = r.meetings; AG.canEdit = !!r.can_edit; AG.listErr = null; } catch (e) { AG.listErr = e.message; }
    AG.lbusy = false;
    if (agIsView()) { agRedraw(); if (AG.cur && !AG.dbusy && !(AG.data && AG.data.agenda.name === AG.cur)) agLoad(AG.cur); }
  }
  async function agLoad(name) {
    AG.dbusy = true;
    try {
      AG.data = await gw('agenda_get', { name }); AG.err = null;
      const m = (AG.list || []).find(x => x.name === name);   // keep the meeting picker's counts current
      if (m) { m.items = AG.data.items.length; m.open = AG.data.items.filter(i => i.status === 'Open').length; m.status = AG.data.agenda.status; m.title = AG.data.agenda.title; }
    } catch (e) { AG.err = e.message; AG.errFor = name; }
    AG.dbusy = false; AG.at = Date.now(); agRedraw();
    if ($('#ccsheet2').classList.contains('on') && $('#agpk')) agPickDraw();
  }
  function agEnsure() {
    if (!WB.cfg && !WB.cfgBusy) wbEnsure();   // doctypes for the record picker
    if (!AG.list) { if (!AG.lbusy) agList(); return; }
    if (AG.cur && !AG.dbusy && (!AG.data || AG.data.agenda.name !== AG.cur || Date.now() - AG.at > 30000)) agLoad(AG.cur);
  }
  AG.mount = () => { agBind(); agEnsure(); };

  /* ---- changes ---- */
  async function agDo(action, args, okMsg) {
    try { const r = await gw(action, args); if (okMsg) toast(okMsg); return r; }
    catch (e) { toast('Not saved: ' + esc(e.message)); return null; }
    finally { if (AG.cur) agLoad(AG.cur); }
  }
  function agAdd(values) { return agDo('agenda_add', { agenda: AG.data.agenda.name, values }); }
  function agUpdate(id, values) {
    const it = AG.data && AG.data.items.find(x => x.name === id); if (it) Object.assign(it, values);
    return agDo('agenda_update', { name: id, values });
  }
  function agMove(id, dir) {
    const vis = agVisible(), i = vis.findIndex(x => x.name === id), j = i + dir; if (i < 0 || j < 0 || j >= vis.length) return;
    const all = AG.data.items, a = all.indexOf(vis[i]), b = all.indexOf(vis[j]); [all[a], all[b]] = [all[b], all[a]];
    agRedraw(); agDo('agenda_order', { agenda: AG.data.agenda.name, names: all.map(x => x.name) });
  }
  function agText() {
    const ag = AG.data.agenda, out = [`${ag.title} · ${agDate(ag.meeting_date)}`, ''];
    agVisible().forEach((it, i) => {
      out.push(`${i + 1}. ${it.item_title}${it.status === 'Discussed' ? ' (discussed)' : ''}${it.presenter ? ' [' + (SHORT[it.presenter] || it.presenter) + ']' : ''}`);
      if (it.details) out.push('   ' + it.details);
      if (it.reference_name) out.push(`   ${wbLabel(it.reference_doctype)} ${it.reference_name}: ${location.origin}${docUrl(it.reference_doctype, it.reference_name)}`);
      if (it.outcome) out.push('   Outcome: ' + it.outcome);
      agMade(it).forEach(t => out.push(`   To-do: ${t.title} (${SHORT[t.owner] || t.owner}${t.date ? ', due ' + fmtd(t.date) : ''})`));
    });
    if (ag.notes) out.push('', 'Notes: ' + ag.notes);
    return out.join('\n');
  }
  async function agCopy() {
    if (!AG.data) return;
    try { await navigator.clipboard.writeText(agText()); toast('Agenda copied. Paste it into an email or chat.'); }
    catch (e) { toast('This browser would not copy. Use Print / PDF instead.'); }
  }
  function agNewSheet() {
    const last = (AG.list || [])[0];
    let date = TODAY; if (last && last.meeting_date) { date = addDays(String(last.meeting_date).slice(0, 10), 7); while (date < TODAY) date = addDays(date, 7); }
    const prevFor = d => (AG.list || []).find(m => String(m.meeting_date) <= d);
    const carryText = d => { const p = prevFor(d); return p ? `Carry over the ${p.open} open item${p.open === 1 ? '' : 's'} from ${esc(agDate(p.meeting_date))}` : 'Carry over open items from the last meeting'; };
    const sh = wbShowSheet(`<label class="cc-field"><span>Title</span><input type="text" name="title" value="${esc(last ? last.title : 'Weekly meeting')}"></label>
      <label class="cc-field"><span>Meeting date</span><input type="date" name="meeting_date" value="${esc(date)}"></label>
      <label class="cc-field wb-check"><input type="checkbox" name="carry" ${last ? 'checked' : ''}><span id="agcarry">${carryText(date)}</span></label>
      <p class="cc-msg" id="wbMsg"></p><div class="cc-sheet-f"><button class="cc-btn primary" type="submit" id="wbsave">Create agenda</button></div>`,
      'Saved in ERPNext. Open items left from the last meeting can come along.', 'New meeting agenda');
    const f = sh.querySelector('#wbform');
    f.elements.meeting_date.onchange = () => { sh.querySelector('#agcarry').innerHTML = carryText(f.elements.meeting_date.value); };
    f.onsubmit = async e => {
      e.preventDefault(); const b = sh.querySelector('#wbsave'), msg = sh.querySelector('#wbMsg');
      const values = { title: f.elements.title.value.trim() || 'Weekly meeting', meeting_date: f.elements.meeting_date.value, carry: f.elements.carry.checked ? 1 : 0 };
      if (!values.meeting_date) { msg.textContent = 'Pick a date.'; return; }
      b.disabled = true; b.textContent = 'Creating…';
      try {
        const r = await gw('agenda_create', { values }); closeSheet();
        toast(`Agenda created${r.carried ? ` · ${r.carried} open item${r.carried === 1 ? '' : 's'} carried over` : ''}`);
        AG.list = null; AG.data = null; AG.cur = r.name; location.hash = 'agenda/' + encodeURIComponent(r.name);
      } catch (err) { msg.textContent = 'Not created: ' + err.message; b.disabled = false; b.textContent = 'Create agenda'; }
    };
  }
  function agEditSheet(id) {
    const it = AG.data.items.find(x => x.name === id); if (!it) return;
    const people = TEAM.map(u => u.name); if (it.presenter && !people.includes(it.presenter)) people.push(it.presenter);
    const sh = wbShowSheet(`<label class="cc-field"><span>Item</span><input type="text" name="item_title" maxlength="140" value="${esc(it.item_title)}"></label>
      <label class="cc-field"><span>Details</span><textarea name="details" rows="3">${esc(it.details || '')}</textarea></label>
      <div class="cc-row2"><label class="cc-field"><span>Who brings it</span><select name="presenter"><option value="">Nobody yet</option>${people.map(p => `<option value="${esc(p)}" ${p === it.presenter ? 'selected' : ''}>${esc(NAMES[p] || SHORT[p] || p)}</option>`).join('')}</select></label>
      <label class="cc-field"><span>Status</span><select name="status">${['Open', 'Discussed', 'Carried over'].map(s => `<option ${s === it.status ? 'selected' : ''}>${s}</option>`).join('')}</select></label></div>
      <label class="cc-field"><span>Outcome / decision</span><textarea name="outcome" rows="3">${esc(it.outcome || '')}</textarea></label>
      ${it.reference_name ? `<p class="small">Linked to ${esc(wbLabel(it.reference_doctype))} ${link(it.reference_doctype, it.reference_name)}. When the item is marked Discussed, the outcome is added to that record's timeline.</p>` : ''}
      <p class="cc-msg" id="wbMsg"></p><div class="cc-sheet-f wb-foot"><button class="cc-btn soft ag-danger" type="button" id="agrm">Remove from agenda</button><button class="cc-btn primary" type="submit" id="wbsave">Save</button></div>`,
      esc(agDate(AG.data.agenda.meeting_date)), 'Agenda item');
    const f = sh.querySelector('#wbform');
    f.onsubmit = async e => {
      e.preventDefault(); const vals = {};
      ['item_title', 'details', 'presenter', 'status', 'outcome'].forEach(k => { const v = f.elements[k].value; if (String(v) !== String(it[k] || '')) vals[k] = k === 'presenter' ? (v || null) : v; });
      if (vals.item_title !== undefined && !vals.item_title.trim()) { sh.querySelector('#wbMsg').textContent = 'The item needs a title.'; return; }
      closeSheet(); if (Object.keys(vals).length) agUpdate(id, vals);
    };
    sh.querySelector('#agrm').onclick = async () => {
      if (!window.confirm('Remove “' + it.item_title + '” from this agenda? The linked record is not touched.')) return;
      closeSheet(); AG.data.items = AG.data.items.filter(x => x.name !== id); agRedraw(); agDo('agenda_remove', { name: id }, 'Removed from the agenda');
    };
  }

  // "+ To-do": one ERPNext ToDo per owner from the item's outcome, linked to what the item is about
  function agTodoSheet(id, outcome) {
    const it = AG.data.items.find(x => x.name === id); if (!it) return;
    const ag = AG.data.agenda, due = addDays(String(ag.meeting_date).slice(0, 10), 7);
    const people = TEAM.slice(); if (it.presenter && !people.some(u => u.name === it.presenter)) people.push({ name: it.presenter, full_name: SHORT[it.presenter] || it.presenter });
    const linked = it.reference_name ? `${esc(wbLabel(it.reference_doctype))} ${link(it.reference_doctype, it.reference_name)}` : 'this agenda item';
    const sh = wbShowSheet(`<label class="cc-field"><span>To-do</span><input type="text" name="title" maxlength="140" value="${esc((outcome || it.outcome || it.item_title || '').trim().slice(0, 140))}"></label>
      <div class="cc-field"><span>Owners</span><div class="cc-owners">${people.map(u => `<label><input type="checkbox" name="owner" value="${esc(u.name)}" ${u.name === it.presenter ? 'checked' : ''}>${avatar(u.name)}${esc(u.full_name || u.name)}</label>`).join('')}</div></div>
      <div class="cc-row2"><label class="cc-field"><span>Due date</span><input type="date" name="date" value="${esc(due)}"></label>
      <label class="cc-field"><span>Priority</span><select name="priority"><option>Medium</option><option>High</option><option>Low</option></select></label></div>
      <label class="cc-field"><span>Notes</span><textarea name="notes" rows="2" placeholder="Optional context"></textarea></label>
      <p class="small">Each owner gets their own to-do in ERPNext, linked to ${linked}, noting it came from this meeting. It also shows on the Tasks page.</p>
      <p class="cc-msg" id="wbMsg"></p><div class="cc-sheet-f"><button class="cc-btn primary" type="submit" id="wbsave">Create to-do</button></div>`,
      esc(agDate(ag.meeting_date)) + ' · ' + esc(it.item_title), 'Make a to-do');
    const f = sh.querySelector('#wbform');
    f.onsubmit = async e => {
      e.preventDefault(); const msg = sh.querySelector('#wbMsg'), b = sh.querySelector('#wbsave');
      const owners = [...f.querySelectorAll('input[name="owner"]:checked')].map(x => x.value), title = f.elements.title.value.trim();
      if (!title || !owners.length) { msg.textContent = 'Add a title and at least one owner.'; return; }
      b.disabled = true; b.textContent = 'Creating…'; msg.textContent = '';
      try {
        const r = await gw('agenda_todo', { name: id, values: { title, owners, date: f.elements.date.value || null, priority: f.elements.priority.value, notes: f.elements.notes.value.trim() } });
        closeSheet(); toast(`Created ${r.todos.length} to-do${r.todos.length === 1 ? '' : 's'} · ${owners.map(o => esc(SHORT[o] || o)).join(', ')} notified`);
        agLoad(AG.cur); load();
      } catch (err) { msg.textContent = 'Not created: ' + err.message; b.disabled = false; b.textContent = 'Create to-do'; }
    };
  }

  /* ---- record picker: suggestions from the live data, or search any Command Center doctype ---- */
  function agSuggest() {
    const ok = dt => WB.cfg && WB.cfg.doctypes[dt], m = CUR_M || M(), in7 = addDays(TODAY, 7), groups = [];
    groups.push(['Overdue to-dos and tasks', m.overdue.filter(x => x.kind === 'todo' || x.kind === 'task').map(x => ({ dt: x.kind === 'todo' ? 'ToDo' : 'Task', name: x.kind === 'todo' ? x.ids[0] : x.id, title: x.title,
      sub: `Due ${fmtd(x.due)}${(x.owners || []).length ? ' · ' + x.owners.map(o => SHORT[o] || o).join(', ') : ''}` }))]);
    groups.push(['Sales orders at risk', D.ship.filter(s => s.state !== 'Ready').sort((a, b) => String(a.delivery || '9').localeCompare(String(b.delivery || '9'))).map(s => ({ dt: 'Sales Order', name: s.so, title: 'Sales Order ' + short(s.so) + (s.customer ? ' · ' + s.customer : ''),
      sub: `${s.delivery && s.delivery < TODAY ? 'Past delivery date ' : 'Delivery '}${fmtd(s.delivery)} · ${money(s.value)}${(s.reasons || []).length ? ' · ' + s.reasons.join(', ') : ''}` }))]);
    groups.push(['Quotes expiring this week', D.quotes.filter(q => q.docstatus === 1 && q.status === 'Open' && q.valid_till && String(q.valid_till) >= TODAY && String(q.valid_till) <= in7).map(q => ({ dt: 'Quotation', name: q.name, title: 'Quotation ' + q.name + (q.party_name ? ' · ' + q.party_name : ''),
      sub: `Expires ${fmtd(q.valid_till)} · ${money(q.base_net_total)}` }))]);
    groups.push(['Tickets waiting over 2 days', m.tOld.map(t => ({ dt: 'HD Ticket', name: t.name, title: t.subject || 'Ticket ' + t.name, sub: `Waiting ${t.age} days${t.type ? ' · ' + t.type : ''}` }))]);
    // purchasing (v8): from the purchasing board once it has loaded (fetched in the background otherwise)
    if (!PU.data && !PU.busy && !PU.err) puFetch();
    if (PU.data) {
      const X = PU.data, warn = (X.settings || {}).vendor_confirm_warn_days || 3, sentBy = addDays(X.today, -warn);
      groups.push(['Purchase orders overdue', (X.pos || []).filter(p => p.overdue).map(p => ({ dt: 'Purchase Order', name: p.name, title: 'Purchase Order ' + p.name + (p.supplier ? ' · ' + p.supplier : ''), sub: `ETA ${fmtd(p.eta)} passed · ${money(p.amount)}` }))]);
      groups.push(['POs the vendor hasn\'t confirmed', (X.pos || []).filter(p => p.lane === 'awaiting_confirmation' && p.sent_on && p.sent_on <= sentBy).map(p => ({ dt: 'Purchase Order', name: p.name, title: 'Purchase Order ' + p.name + (p.supplier ? ' · ' + p.supplier : ''), sub: `Sent ${fmtd(p.sent_on)}, not confirmed` }))]);
      groups.push(['Shipments waiting for landed cost', (X.shipments || []).filter(x => x.needs_lcv).map(x => ({ dt: 'ilL-Inbound-Shipment', name: x.name, title: 'Shipment ' + x.name + (x.supplier ? ' · ' + x.supplier : ''), sub: `Delivered ${fmtd(x.ata || x.eta)} · costs not landed` }))]);
    }
    return groups.map(([l, rows]) => [l, rows.filter(r => r.name && ok(r.dt)).slice(0, 15)]).filter(g => g[1].length);
  }
  const agPkRow = (c, k) => `<div class="ag-pk-row"><div><b>${esc(c.title)}</b><div class="small">${esc(wbLabel(c.dt))} ${esc(short(c.name))}${c.sub ? ' · ' + esc(c.sub) : ''}</div></div>
    ${agOn(c.dt, c.name) ? '<span class="badge good">On the agenda</span>' : `<button type="button" class="cc-btn soft" data-agpk="${k}">+ Add</button>`}</div>`;
  function agPickDraw() {
    const el = $('#agpk'), P = AG.pick; if (!el) return;
    $('#ccsheet2').querySelectorAll('[data-agtab]').forEach(b => b.classList.toggle('on', b.dataset.agtab === P.tab));
    if (WB.cfgErr) { el.innerHTML = `<div class="err">Couldn't load the record types: ${esc(WB.cfgErr)}</div>`; return; }
    if (!WB.cfg) { el.innerHTML = agLoading; wbEnsure().then(() => { if ($('#agpk')) agPickDraw(); }); return; }
    P.cands = [];
    if (P.tab === 'suggested') {
      const g = agSuggest();
      el.innerHTML = g.length ? g.map(([l, rows]) => `<div class="wb-sec">${esc(l)}</div>${rows.map(c => agPkRow(c, P.cands.push(c) - 1)).join('')}`).join('')
        : '<div class="empty">Nothing overdue, at risk or expiring right now. Use “Search all records”.</div>';
    } else {
      const dts = Object.keys(WB.cfg.doctypes); if (!P.dt || !WB.cfg.doctypes[P.dt]) P.dt = dts.includes('Sales Order') ? 'Sales Order' : dts[0];
      const opts = WB.cfg.sections.filter(s => !s.locked).map(s => { const ds = dts.filter(d => WB.cfg.doctypes[d].section === s.key); return ds.length ? `<optgroup label="${esc(s.label)}">${ds.map(d => `<option value="${esc(d)}" ${d === P.dt ? 'selected' : ''}>${esc(wbLabel(d))}</option>`).join('')}</optgroup>` : ''; }).join('');
      const res = P.err ? `<div class="err">${esc(P.err)}</div>` : P.rows === null || P.busy ? agLoading : P.rows.length ? P.rows.map(r => {
        const st = r.status ? r.status + ' · ' : '', val = (P.cols || []).find(c => c.type === 'Currency' && r[c.fieldname] != null);
        return agPkRow({ dt: P.dt, name: r.name, title: agTitle(P.dt, r.name, r), row: r, sub: st + (val ? money(Number(r[val.fieldname])) + ' · ' : '') + 'modified ' + fmtd(r.modified) }, P.cands.push({ dt: P.dt, name: r.name, title: agTitle(P.dt, r.name, r) }) - 1);
      }).join('') : '<div class="empty">Nothing matches.</div>';
      el.innerHTML = `<div class="ag-pk-bar"><select id="agpkdt" aria-label="Record type">${opts}</select><input type="search" id="agpkq" placeholder="Search ${esc(wbLabel(P.dt))} by ID, name or customer…" value="${esc(P.q)}"></div><div id="agpkres">${res}</div>`;
      el.querySelector('#agpkdt').onchange = e => { P.dt = e.target.value; P.q = ''; agPickFetch(); };
      const q = el.querySelector('#agpkq'); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { P.q = q.value.trim(); agPickFetch(true); }, 300); };
      if (P.rows === null && !P.busy && !P.err) agPickFetch();
    }
    el.querySelectorAll('[data-agpk]').forEach(b => b.onclick = async () => {
      const c = P.cands[+b.dataset.agpk]; if (!c) return; b.disabled = true; b.textContent = 'Adding…';
      const r = await agAdd({ item_title: c.title, reference_doctype: c.dt, reference_name: c.name });
      if (!r) { b.disabled = false; b.textContent = '+ Add'; } else if (r.duplicate) toast('Already on this agenda');
    });
  }
  async function agPickFetch(keepFocus) {
    const P = AG.pick, dt = P.dt; P.busy = true; P.err = null;
    if (!keepFocus) agPickDraw(); else { const r = $('#agpkres'); if (r) r.innerHTML = agLoading; }
    try { const res = await gw('list', { dt, search: P.q, limit: 25 }); if (P.dt !== dt) return; P.rows = res.rows; P.cols = res.columns; }
    catch (e) { P.err = e.message; P.rows = []; }
    P.busy = false;
    const q = $('#agpkq'), pos = q && document.activeElement === q ? q.selectionStart : null;
    agPickDraw(); if (pos !== null) { const q2 = $('#agpkq'); if (q2) { q2.focus(); q2.setSelectionRange(pos, pos); } }
  }
  function agPicker() {
    const el = $('#ccsheet2'), P = AG.pick, ag = AG.data.agenda;
    P.rows = null; P.err = null;
    el.innerHTML = `<div class="cc-sheet wb-sheet"><div class="cc-sheet-h"><div><h2>Add from ERPNext</h2><p>${esc(agDate(ag.meeting_date))} · ${esc(ag.title)}</p></div><button class="cc-x" data-close aria-label="Close">×</button></div>
      <div class="ag-pk"><div class="seg" style="margin-bottom:12px"><button type="button" data-agtab="suggested">Suggested</button><button type="button" data-agtab="search">Search all records</button></div><div id="agpk"></div></div></div>`;
    el.classList.add('on'); el.querySelector('[data-close]').onclick = closeSheet; el.onclick = e => { if (e.target === el) closeSheet(); };
    el.querySelectorAll('[data-agtab]').forEach(b => b.onclick = () => { P.tab = b.dataset.agtab; agPickDraw(); });
    agPickDraw();
  }
  // "+ Add to agenda" on a Workbench record: goes on the next open meeting
  async function agQuick(dt, name, row, btn) {
    const reset = () => { btn.disabled = false; btn.textContent = '+ Add to agenda'; };
    btn.disabled = true; btn.textContent = 'Adding…';
    try {
      if (!AG.list) { const r = await gw('agenda_list'); AG.list = r.meetings; AG.canEdit = !!r.can_edit; }
      const m = (AG.list || []).find(x => x.name === agDefault());
      if (!m || m.status !== 'Open') { toast('No open meeting agenda yet · <a href="#agenda">Start one</a>'); reset(); return; }
      const r = await gw('agenda_add', { agenda: m.name, values: { item_title: agTitle(dt, name, row), reference_doctype: dt, reference_name: name } });
      btn.textContent = r.duplicate ? 'Already on the agenda' : '✓ On the agenda';
      toast(`${r.duplicate ? 'Already on' : 'Added to'} the ${esc(agDate(m.meeting_date))} agenda · <a href="#agenda/${encodeURIComponent(m.name)}">Open agenda</a>`);
      if (!r.duplicate) m.items = (m.items || 0) + 1; AG.at = 0;
    } catch (e) { toast('Not added: ' + esc(e.message)); reset(); }
  }
  function agBind() {
    const r = $('#agroot'); if (!r) return;
    r.querySelectorAll('[data-agnew]').forEach(b => b.onclick = agNewSheet);
    const pk = r.querySelector('[data-agpick]'); if (pk) pk.onchange = () => { location.hash = 'agenda/' + encodeURIComponent(pk.value); };
    const pr = r.querySelector('#agprint'); if (pr) pr.onclick = () => window.print();
    const cp = r.querySelector('[data-agcopy]'); if (cp) cp.onclick = agCopy;
    const X = AG.data; if (!X || X.agenda.name !== AG.cur) return;
    const name = X.agenda.name;
    const cl = r.querySelector('[data-agclose]'); if (cl) cl.onclick = () => { const st = X.agenda.status === 'Open' ? 'Closed' : 'Open'; X.agenda.status = st; agRedraw(); agDo('agenda_save_meeting', { name, values: { status: st } }, st === 'Closed' ? 'Meeting closed' : 'Meeting reopened'); };
    const nt = r.querySelector('[data-agnotes]'); if (nt) nt.onchange = () => { X.agenda.notes = nt.value; agDo('agenda_save_meeting', { name, values: { notes: nt.value } }, 'Notes saved'); };
    const af = r.querySelector('#agaddf'); if (af) af.onsubmit = async e => {
      e.preventDefault(); const t = r.querySelector('#agaddt'), title = t.value.trim(); if (!title) { t.focus(); return; }
      const b = af.querySelector('[type="submit"]'); b.disabled = true; t.value = '';
      const res = await agAdd({ item_title: title, presenter: r.querySelector('#agaddp').value || null });
      b.disabled = false; if (!res) t.value = title; const t2 = $('#agaddt'); if (t2) t2.focus();
    };
    const pkb = r.querySelector('[data-agpicker]'); if (pkb) pkb.onclick = agPicker;
    r.querySelectorAll('[data-agid]').forEach(el => {
      const id = el.dataset.agid, it = X.items.find(x => x.name === id); if (!it) return;
      el.querySelectorAll('[data-agedit]').forEach(b => b.onclick = () => agEditSheet(id));
      const d = el.querySelector('[data-agdone]'); if (d) d.onchange = () => { agUpdate(id, { status: d.checked ? 'Discussed' : 'Open' }); agRedraw(); };
      const o = el.querySelector('[data-agout]'); if (o) { o.onchange = () => agUpdate(id, { outcome: o.value }); o.oninput = () => { o.style.height = 'auto'; o.style.height = o.scrollHeight + 'px'; }; if (o.value) o.oninput(); }
      el.querySelectorAll('[data-agmv]').forEach(b => b.onclick = () => agMove(id, +b.dataset.agmv));
      const td = el.querySelector('[data-agtodo]'); if (td) td.onclick = () => agTodoSheet(id, o ? o.value : '');
      const op = el.querySelector('[data-agopen]'); if (op) op.onclick = () => wbOpen(it.reference_doctype, it.reference_name);
    });
  }

  /* ---------------- init ---------------- */
  $('#ccwho').innerHTML = LOGGED ? `Signed in as ${esc(USER)}` : `Viewing as guest · <a href="/login?redirect-to=/command-center">Log in</a> to add tasks, close ToDos and draft orders`;
  $('#ccrefresh').onclick = () => { AG.at = 0; load(true); };   // AG.at = 0: the agenda re-reads too
  $('#ccadd').onclick = openModal; $('#tCancel').onclick = closeModal; $('#tform').onsubmit = addTask;
  $('#ccmodal').onclick = e => { if (e.target.id === 'ccmodal') closeModal(); };
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeModal(); closeSheet(); }
    if (S.view === 'review' && D && !$('#ccsheet2').classList.contains('on') && !$('#ccmodal').classList.contains('on') && !/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '')) {
      if (e.key === 'ArrowRight') rvGo(RV.i + 1); else if (e.key === 'ArrowLeft') rvGo(RV.i - 1);
    }
  });
  $('#ccmeeting').onchange = e => { S.meeting = e.target.checked; root.classList.toggle('meeting', S.meeting); if (S.meeting && S.source === 'kevins@') S.source = ''; if (D) render(); };
  let qt; $('#ccq').oninput = e => { clearTimeout(qt); qt = setTimeout(() => { S.q = e.target.value.toLowerCase(); if (D) render(); }, 150); };
  window.addEventListener('hashchange', () => { WB.preApplied = null; S.view = (location.hash || '#pipeline').slice(1); if (D) { render(); window.scrollTo({ top: 0, behavior: 'smooth' }); } });
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (D && ['pipeline', 'finance', 'inbox'].includes(S.view)) render(); }, 200); });
  load();
  // the agenda is shared during the meeting: pick up others' changes every 30 s (not while typing)
  setInterval(() => {
    const a = document.activeElement, typing = a && $('#agroot') && $('#agroot').contains(a) && /INPUT|TEXTAREA|SELECT/.test(a.tagName);
    if (D && agIsView() && AG.cur && !AG.dbusy && !document.hidden && !typing && !$('#ccsheet2').classList.contains('on') && !$('#ccmodal').classList.contains('on')) agLoad(AG.cur);
  }, 30000);
  setInterval(() => { if (!document.hidden && !$('#ccmodal').classList.contains('on') && !$('#ccsheet2').classList.contains('on')) load(); }, 5 * 60 * 1000);
})();