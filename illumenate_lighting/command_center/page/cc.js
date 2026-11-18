/* ilLumenate Command Center v5 — base v2/v3 by Claude, Nov 17 2026.
   v4: Workbench. v5: Executive overview, Project review mode, saved views, activity feed, print.
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
      D = (await r.json()).message; prep(); render();
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
      const m = raw.match(/\[(ad-hoc|email|review|cleanup)\] Owners:\s*([^<\n]*)/);
      const tag = m ? m[1] : ((x._user_tags || '').replace(/^,/, '') || null);
      const owners = m ? m[2].split(',').map(s => s.trim()).filter(Boolean) : [x.allocated_to];
      const tmp = document.createElement('div'); tmp.innerHTML = raw;
      const p = tmp.querySelector('p'); const title = (p ? p.textContent : tmp.textContent).trim();
      const mail = (raw.match(/href="(https:\/\/mail\.google\.com[^"]+)"/) || [])[1];
      let notes = ''; if (p) { p.remove(); notes = tmp.textContent.replace(/\[(ad-hoc|email|review|cleanup)\] Owners:.*$/s, '').replace('Email thread (kevins@ inbox): open in Gmail', '').trim(); }
      const nice = title.replace(/^Assignment for (.+?) (ilL-SAL-ORD-)?(\S.*)$/, (_, dt, p, n) => dt + ' ' + n);
      const key = tag ? title : x.name;
      if (seen[key]) { seen[key].ids.push(x.name); return; }
      const row = { id: x.name, ids: [x.name], title: nice || '(no description)', notes, owners, due: x.date, priority: x.priority,
        source: tag === 'email' ? 'kevins@' : tag === 'ad-hoc' ? 'ad hoc' : 'ERPNext', tag, mail: mail ? mail.replace(/&amp;/g, '&') : null,
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
      { k: 'purch', n: 'Purchasing', v: m.firm.length, l: `Lines short · ${m.late.length} past order-by`, s: m.late.length ? ['Act now', 'bad'] : m.firm.length ? ['Watch', 'warn'] : ['Clear', 'good'], c: m.firm.length },
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
  
  /* quick links to the ERPNext doctype pages behind each section */
  const QL = {
    pipeline: [['Customers', '/app/customer'], ['Sales orders', '/app/sales-order'], ['Sales invoices', '/app/sales-invoice'], ['Sales partners (reps)', '/app/sales-partner'], ['Customer groups (tiers)', '/app/customer-group']],
    quotes: [['+ New quotation', '/app/quotation/new'], ['Quotations', '/app/quotation'], ['Quote requests', '/app/ill-quote-request'], ['Quote offers', '/app/ill-quote-offer'], ['Quote & design tickets', '/helpdesk/tickets'], ['Help desk', '/helpdesk/tickets']],
    orders: [['+ New sales order', '/app/sales-order/new'], ['Sales orders', '/app/sales-order'], ['Order requests', '/app/ill-order-intake'], ['Order changes', '/app/ill-order-change'], ['Order tickets', '/helpdesk/tickets'], ['Delivery notes', '/app/delivery-note']],
    so: [['Sales orders', '/app/sales-order'], ['+ New delivery note', '/app/delivery-note/new'], ['+ New sales invoice', '/app/sales-invoice/new']],
    purch: [['+ New material request', '/app/material-request/new'], ['+ New purchase order', '/app/purchase-order/new'], ['Material requests', '/app/material-request'], ['Purchase orders', '/app/purchase-order'], ['Purchase receipts', '/app/purchase-receipt'], ['Suppliers', '/app/supplier'], ['Stock balance', '/app/query-report/Stock%20Balance'], ['Items', '/app/item']],
    mfg: [['+ New work order', '/app/work-order/new'], ['Work orders', '/app/work-order'], ['BOMs', '/app/bom'], ['Production plans', '/app/production-plan'], ['Stock entries', '/app/stock-entry']],
    ship: [['+ New delivery note', '/app/delivery-note/new'], ['Delivery notes', '/app/delivery-note'], ['Shipments', '/app/shipment'], ['Sales orders to deliver', '/app/sales-order?status=%5B%22in%22%2C%5B%22To%20Deliver%22%2C%22To%20Deliver%20and%20Bill%22%5D%5D']],
    service: [['Help desk', '/helpdesk/tickets'], ['Knowledge base', '/helpdesk/kb']],
    requests: [['Quote requests', '/app/ill-quote-request'], ['Order requests', '/app/ill-order-intake'], ['Drawing requests', '/app/ill-document-request'], ['Account requests', '/app/ill-account-request'], ['Order changes', '/app/ill-order-change']],
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
  V.purch = m => {
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
    return header('Purchasing', 'What we need to order, worked back from each order\'s required date using lead times.') + `
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
  /* ---------------- production board (manufacturing) ----------------
     The warehouse "Schedule Wizard", live: order queue with build points, capacity burn-down,
     waiting for parts, shipped and on-time. Data: illumenate_lighting...production_board.get_board
     (app endpoint, read-only). Weights and capacity: ilL-Production-Settings. */
  const PB_API = 'illumenate_lighting.illumenate_lighting.api.production_board.get_board';
  const PB = { data: null, err: null, busy: false, at: 0, filter: 'all', sort: 'esd' };
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
      ${PB_RUNS.map(([k]) => `<td class="num">${pbCount(r.counts[k])}</td>`).join('')}
      <td class="num"><b>${pbNum(r.points)}</b></td><td class="num">${pbNum(r.hours)}</td><td class="num">${r.worth == null ? '<span class="calc">—</span>' : money(r.worth)}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`);
  };
  PB.body = () => {
    const X = PB.data;
    if (!X) return PB.err ? `<div class="err">Couldn't load the production board: ${esc(PB.err)}</div>` : '<div class="empty">Loading the production board…</div>';
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
    const qHead = ['Sales order', '#$', '#Com %', 'Ship date', 'Status', ...PB_RUNS.map(([, n]) => '#' + n), '#Points', '#Hrs', '#$ / pt', 'Notes'];
    const wfpRows = X.wfp.filter(rowOK).map(r => `<tr class="${r.going_to_miss ? 'pb-row-late' : ''}"><td>${link('sales-order', r.so, short(r.so))}<div class="m">${esc(r.customer || '')}</div></td><td class="num">${pbMoney(r.amount)}</td><td>${pbEsd(r)}</td>
      <td>${r.eta ? fmtd(r.eta) : badge('No PO', 'bad')}</td><td>${r.going_to_miss ? badge('Going to miss', 'bad') : badge('OK', 'good')}</td><td>${r.this_month ? 'Yes' : 'No'}</td>
      <td class="num">${pbNum(r.points)}</td><td>${r.short_items.slice(0, 4).map(s => `${link('item', s.item)} <span class="calc">${pbNum(s.qty, 2)}${r.no_po_items.includes(s.item) ? ', no PO' : ''}</span>`).join('<br>')}${r.short_items.length > 4 ? `<div class="calc">+${r.short_items.length - 4} more</div>` : ''}</td><td class="pb-notes">${esc(r.notes)}</td></tr>`);
    const shipRows = sh.rows.filter(rowOK).map(s => `<tr><td>${link('delivery-note', s.delivery_note)}</td><td>${s.so ? link('sales-order', s.so, short(s.so)) : ''}<div class="m">${esc(s.customer || '')}</div></td><td class="num">${pbMoney(s.amount)}</td><td class="num">${pbPct(s.com_pct, flag)}</td>
      <td>${fmtd(s.esd)}</td><td>${fmtd(s.shipped)}</td><td>${s.on_time ? badge('On time', 'good') : s.not_warehouse_fault ? badge('Late, not warehouse', 'warn') : badge('Late', 'bad')}</td><td class="pb-notes">${esc(s.late_reason || '')}</td></tr>`);
    const weekly = hbars(sh.weekly.map(w => ({ label: 'Week of ' + fmtd(w.week_of), value: w.on_time_pct == null ? 0 : w.on_time_pct * 100, color: w.on_time_pct != null && w.on_time_pct < 0.95 ? '#eb6834' : '#12b76a', title: pbN(w.shipments, 'shipment') })), { max: 100, fmt: v => Math.round(v) + '%', lw: '130px' });
    return `${X.money ? '' : '<p class="small">Dollar figures need the Command Center Finance or Manufacturing Manager role.</p>'}
      <div class="ex-kpis pb-kpis">${pipe.join('')}</div>
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
    const s = $('#pbsort'); if (s) s.onchange = () => { PB.sort = s.value; $('#pbroot').innerHTML = PB.body(); PB.bind(); };
    const X = PB.data; if (!X) return;
    const b = X.capacity.burndown;
    vbars($('#pbburn'), b.map(r => fmtd(r.date)), [{ name: 'Points left', color: '#2a78d6', values: b.map(r => r.remaining) }], { target: X.capacity.capacity_per_day, targetLabel: '1 day of capacity', fmt: v => Math.round(v), h: 220 });
  };
  PB.mount = () => {
    const r = $('#pbrefresh'); if (r) r.onclick = () => pbFetch(true);
    PB.bind();
    if (!PB.busy && (!PB.data || Date.now() - PB.at > 120000)) pbFetch();
  };
  V.mfg = m => {
    const row = w => `<tr><td>${link('work-order', w.wo)}</td><td>${link('item', w.item, w.name)}<div class="m mono">${esc(w.item)}</div></td><td class="num">${w.qty}</td><td>${link('sales-order', w.so, short(w.so))}</td><td>${fmtd(w.created)}</td><td>${w.flag === 'Active' ? badge(w.status, w.draft ? 'warn' : 'info') : badge(w.flag.split(':')[0].split(' (')[0], 'bad')}</td></tr>`;
    return header('Manufacturing', 'Production board: what to build, how long the queue takes with today\'s crew, and what is waiting on parts.',
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
    return header('Shipping', 'Which open sales orders can go out this week, and which are at risk.') + `<div class="grid">
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
  V.req = m => {
    const types = ['Quote Request', 'Sales Order Request', 'Drawing Request', 'Account Request'];
    return header('Requests pipeline', 'Open requests from the dealer portal. A red age means open for more than 2 business days. ISSUED means the quote is out and we\'re waiting on the dealer.') + `<div class="lanes">
      ${types.map(t => { const rs = D.reqs.filter(r => r.type === t && rowOK(r)).sort((a, b) => b.open - a.open || b.age - a.age); const o = rs.filter(r => r.open).length;
        return `<div class="lane"><div class="lane-h"><span>${t}s</span>${badge(o + ' open', o ? 'info' : 'mute')}</div>
        ${rs.map(r => `<div class="kcard ${r.open ? '' : 'closed'}"><div class="r">${link(r.dt, r.name)}${r.open && r.age > 2 ? badge(r.age + 'd', 'bad') : `<span class="calc">${r.age}d</span>`}</div>
          <div style="margin-top:4px">${cust(r.customer)}</div><div class="m">${esc(r.state)}${r.detail ? ' · ' + esc(r.detail) : ''}</div>
          <div class="r" style="margin-top:8px">${r.owner ? avatar(r.owner) : '<span class="calc">Unassigned</span>'}<span class="calc">${fmtd(r.created)}</span></div></div>`).join('') || '<div class="empty">None</div>'}</div>`; }).join('')}</div>`;
  };
  V.inbox = m => {
    const CAT = { Quotation: 'Quotes', Service: 'Tech support', 'Sales Order': 'Order status', Design: 'Design' }, cats = ['Quotes', 'Tech support', 'Order status', 'Design', 'Other'];
    const cnt = arr => cats.map(c => arr.filter(t => (CAT[t.type] || 'Other') === c).length);
    setTimeout(() => vbars($('#ch-inbox'), cats, [{ name: 'This week', color: '#2a78d6', values: cnt(m.tw) }, { name: 'Last week', color: '#eb6834', values: cnt(m.lw) }], { labels: true, h: 230 }));
    const open = D.tk.filter(t => (t.status === 'Open' || t.status === 'Replied') && rowOK(t)).sort((a, b) => (a.status > b.status ? 1 : -1) || b.age - a.age);
    return header('Inbox (sales@)', 'Help desk tickets. Replying closes the ticket\'s ToDo automatically, and a customer reply reopens it with a fresh ToDo.') + `<div class="grid">
      ${stat('Tickets this week', m.tw.length, `Last week ${m.lw.length}`).replace('card stat', 'card stat s4')}
      ${stat('Waiting on us', m.tOpen.length, 'Open tickets').replace('card stat', 'card stat s4')}
      ${stat('Waiting over 2 business days', m.tOld.length, 'Needs a reply', m.tOld.length ? 'bad' : '').replace('card stat', 'card stat s4')}
      ${card('Tickets by type', 'Created in the last 7 days vs the 7 before. Emails that never became a ticket aren\'t counted.', '<div class="chart" id="ch-inbox"></div>', 's12')}
      ${tableCard('Open and waiting tickets', 'Open = our move. Replied = waiting on the customer (close it after 10 days).', ['Ticket', 'Subject', 'Type', 'Status', 'Owner', '#Age'],
        open.map(t => `<tr><td>${link('hd-ticket', t.name)}</td><td>${esc(t.subject)}<div class="m">${fmtd(t.created)}</div></td><td>${esc(t.type)}</td><td>${t.status === 'Open' ? sdot('Open', 'warn') : sdot('Replied', 'mute')}</td><td>${avs(t.assignedL)}</td>
          <td class="num">${(t.status === 'Open' && t.age > 2) || (t.status === 'Replied' && t.age > 10) ? badge(t.age + 'd', 'bad') : t.age + 'd'}</td></tr>`))}
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
      <select data-f="source">${opt('', 'All sources', S.source)}${['ERPNext', 'sales@ (help desk)', 'ad hoc'].concat(S.meeting ? [] : ['kevins@']).map(s => opt(s, s, S.source)).join('')}</select>
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
          <td style="white-space:nowrap">${esc(x.source)}${x.tag && !['email', 'ad-hoc'].includes(x.tag) ? `<div class="m">${esc(x.tag)}</div>` : ''}${x.mail ? `<div class="m"><a target="_blank" rel="noopener" href="${x.mail}">Open email</a></div>` : ''}</td>
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
  const soPurch = so => D.purch.filter(r => r.short_firm > 0 && r.docs.some(x => x.doc === so || (x.src === 'Work Order' && woSO[x.doc] === so)));
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
    const p = pipeData(m);
    const st = [
      ['pipeline', 'Overview', `${m.newThis.length}/8`, 'new dealers', m.newThis.length >= 8 * m.pace ? 'good' : 'bad'],
      ['quotes', 'Quotes & design', p.inqOpen.length + p.qOut.length, `${p.inqOpen.length} our move · ${p.qOut.length} quotes out`, p.inqOpen.some(t => t.age > 2) ? 'warn' : 'good'],
      ['orders', 'Sales orders', D.ship.length, kfmt(p.soVal) + ' open', p.corr.length ? 'warn' : 'good'],
      ['purch', 'Purchasing', m.firm.length, `${m.late.length} late`, m.late.length ? 'bad' : 'good'],
      ['mfg', 'Manufacturing', m.act.length, `${D.needwo.length} lines need WO`, D.needwo.length || m.dup.length ? 'warn' : 'good'],
      ['ship', 'Shipping', `${p.ready.length}/${D.ship.length}`, `ready · ${m.past.length} past due`, m.past.length ? 'bad' : 'good'],
    ];
    return `<div class="chev">${st.map(([k, n, v, l, s]) => `<a href="#${k}" class="cv ${cur === k ? 'on' : ''}"><div class="cvn"><span class="dot ${s}"></span>${n}</div><div class="cvv">${esc(v)}</div><div class="cvl">${esc(l)}</div></a>`).join('')}</div>`;
  }

  V.pipeline = m => {
    const p = pipeData(m), tr = D.trend.filter(x => x.change != null && rowOK(x)).slice(0, 10);
    const fun = [
      ['quotes', 'Inquiries', p.inqOpen.length + p.inqWait.length, 'design & quote tickets open', '#2a78d6'],
      ['quotes', 'Quotes out', p.qOut.length, kfmt(p.qVal) + ' waiting on dealers', '#3b84dc'],
      ['orders', 'Sales orders', D.ship.length, kfmt(p.soVal) + ' open', '#4c90e1'],
      ['purch', 'Need materials', p.soShort.length, m.firm.length + ' lines short', '#eb6834'],
      ['mfg', 'In production', p.soMfg.length, m.act.length + ' work orders', '#eda100'],
      ['ship', 'Ready to ship', p.ready.length, m.past.length + ' orders past due', '#12b76a'],
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
    const tks = p.inq.filter(t => rowOK(t) && (!DONE_TK.includes(t.status) || (t.modified || t.created) >= since));
    const col = (title, sub, list, k) => `<div class="bcol"><div class="lane-h"><span><span class="dot ${k}"></span> ${title}</span><span class="ct">${list.length}</span></div><div class="small" style="margin:-4px 0 10px">${sub}</div>
      ${list.map(t => { const q = t.quotation && D.qByName[t.quotation], td = D.byRef['HD Ticket|' + t.name] || [];
        return `<div class="tcard"><div class="r"><span class="badge ${t.type === 'Design' ? 'info' : 'mute'}">${esc(t.type === 'Quotation' ? 'Quote' : t.type)}</span>${t.status === 'Open' && t.age > 2 ? badge(t.age + 'd', 'bad') : `<span class="small">${t.age}d</span>`}</div>
          <div class="tt" style="margin-top:8px">${link('hd-ticket', t.name, t.subject || t.name)}</div><div class="m">${esc(t.raised_by || '')}</div>
          ${q ? `<div class="qchip">${link('quotation', q.name, short(q.name).replace('ilL-SAL-QTN-', ''))} · ${money(q.base_net_total)} · ${esc(q.docstatus === 0 ? 'Draft' : q.status)}</div>` : (t.type === 'Quotation' ? (LOGGED ? `<button class="cc-btn soft" style="margin-top:8px" data-linkq="${esc(t.name)}">Link quotation</button>` : '<div class="m" style="margin-top:6px">No quotation linked</div>') : '')}
          ${td.length ? `<div class="tdl">${td.slice(0, 3).map(x => `<div>☐ <a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a></div>`).join('')}${td.length > 3 ? `<div class="calc">+${td.length - 3} more</div>` : ''}</div>` : ''}
          <div class="r" style="margin-top:10px">${avs(t.assignedL)}<span class="small">${fmtd(t.created)}</span></div></div>`; }).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`;
    const qrows = p.qOut.concat(S.qdraft ? p.qDraft : []).filter(rowOK).sort((a, b) => String(a.valid_till || '9').localeCompare(String(b.valid_till || '9')));
    return header('Quotes & design', 'Design and quotation tickets from sales@, the quotes we\'ve sent, and who\'s waiting on whom.') + `
      <div class="grid" style="margin-bottom:20px">
        ${stat('Our move', p.inqOpen.length, `${p.inqOpen.filter(t => t.age > 2).length} waiting over 2 business days`, p.inqOpen.some(t => t.age > 2) ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Waiting on customer', p.inqWait.length, 'Tickets we\'ve replied to').replace('card stat', 'card stat s3')}
        ${stat('Quotes out', p.qOut.length, `${money(p.qVal)} waiting on dealers`).replace('card stat', 'card stat s3')}
        ${stat('Expiring in 7 days', p.qExp.length, `${p.qDraft.length} unsent drafts (last 120 days)`, p.qExp.length ? 'bad' : '').replace('card stat', 'card stat s3')}
      </div>
      <div class="board" style="grid-template-columns:repeat(3,minmax(260px,1fr))">
        ${col('Our move', 'Open: needs a reply, design or quote', tks.filter(t => t.status === 'Open').sort((a, b) => b.age - a.age), 'bad')}
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
        <div class="tt" style="margin-top:8px">${link('hd-ticket', t.name, t.subject || t.name)}</div><div class="m">${esc(t.raised_by || '')}</div>
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
    return header('Sales orders', 'Every open order with its progress, to-dos, tasks and anything that needs correcting. Click an order for the full picture.') + `
      <div class="grid" style="margin-bottom:20px">
        ${stat('Open orders', D.ship.length, money(p.soVal) + ' total').replace('card stat', 'card stat s3')}
        ${stat('Past delivery date', m.past.length, '', m.past.length ? 'bad' : '').replace('card stat', 'card stat s3')}
        ${stat('Need materials', p.soShort.length, 'Orders with short items').replace('card stat', 'card stat s3')}
        ${stat('Need correcting', p.corr.length, 'Flags below', p.corr.length ? 'bad' : '').replace('card stat', 'card stat s3')}
      </div>
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
          Tasks open: ${tk.length}</div>${tk.length ? `<div style="margin-top:8px">${tk.slice(0, 5).map(t => `<div class="todo-r"><span>${avs(t.owners)}</span><span>${esc(t.subject)}</span></div>`).join('')}</div>` : ''}`, 's4')}
        ${tableCard('Order lines', `${s.lines.length} lines`, ['Item', '#Qty', '#Delivered', '#Amount', ''], s.lines.map(l => `<tr><td>${link('item', l.item, l.name || l.item)}<div class="m mono">${esc(l.item)}</div></td><td class="num">${l.qty}</td><td class="num">${l.delivered}</td><td class="num">${money(l.amount)}</td><td>${l.old ? badge('Retired code', 'warn') : ''}</td></tr>`), '', 's12')}
        ${tableCard('Purchasing needed for this order', 'Short components for this order and its work orders', ['Item', '#Short', 'Supplier', 'Order by', 'Draft PO / MR', ''],
          pur.map(r => `<tr><td>${link('item', r.item)}<div class="m">${esc(r.group || '')}</div></td><td class="num"><b>${+r.short_firm.toFixed(2)}</b></td><td>${r.supplier ? link('supplier', r.supplier) : badge('No supplier', 'warn')}</td>
            <td>${r.order_by ? (r.late ? badge('Late · ' + fmtd(r.order_by), 'bad') : fmtd(r.order_by)) : '—'}</td><td>${[r.draft_po && link('purchase-order', r.draft_po), r.mr && link('material-request', r.mr)].filter(Boolean).join('<br>') || '<span class="calc">None</span>'}</td>
            <td class="num">${!r.draft_po && !r.mr && !r.manufactured && LOGGED ? `<button class="cc-btn soft" data-mr="${esc(r.item)}">Draft MR</button>` : ''}</td></tr>`), '', 's6')}
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
          <div class="tt" style="margin-top:8px">${link('hd-ticket', t.name, t.subject || t.name)}</div><div class="m">${esc(t.raised_by || '')}</div>
          ${so ? `<div class="qchip">Order ${s ? `<a href="#so-${encodeURIComponent(so)}">${esc(short(so))}</a> · ${esc(s.status)}` : link('sales-order', so, short(so))}</div>` : (LOGGED && !DONE_TK.includes(t.status) ? `<button class="cc-btn soft" style="margin-top:8px" data-linkso="${esc(t.name)}">Link sales order</button>` : '')}
          ${td.length ? `<div class="tdl">${td.slice(0, 3).map(x => `<div>☐ <a target="_blank" rel="noopener" href="${x.url}">${esc(x.title)}</a></div>`).join('')}${td.length > 3 ? `<div class="calc">+${td.length - 3} more</div>` : ''}</div>` : ''}
          <div class="r" style="margin-top:10px">${avs(t.assignedL)}<span class="small">${fmtd(t.created)}</span></div></div>`; }).join('') || '<div class="drop-hint">Nothing here</div>'}</div>`;
    const people = {}; open.concat(wait).forEach(t => (t.assignedL.length ? t.assignedL : ['(unassigned)']).forEach(u => { people[u] = (people[u] || 0) + 1; }));
    return header('Service', 'Tech support and service tickets from sales@: what\'s waiting on us, what\'s waiting on the customer, and how old it is.') + `
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
      await call('frappe.client.set_value', { doctype: 'HD Ticket', name: t.name, fieldname: 'ill_sales_order', value: v }); toast('Sales order linked to ticket ' + esc(t.name));
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
      await call('frappe.client.set_value', { doctype: 'HD Ticket', name: t.name, fieldname: 'ill_quotation', value: v }); toast('Quotation linked to ticket ' + esc(t.name));
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
    root.querySelectorAll('[data-mrlow]').forEach(b => b.onclick = async () => {
      const date = addDays(TODAY, 14); b.disabled = true; b.textContent = '…';
      try { const res = await call('frappe.client.insert', { doc: { doctype: 'Material Request', material_request_type: 'Purchase', company: 'ilLumenate Lighting', transaction_date: TODAY, schedule_date: date, set_warehouse: 'Stores - ilL',
          items: [{ item_code: b.dataset.mrlow, qty: +b.dataset.qty || 1, schedule_date: date, warehouse: 'Stores - ilL' }] } });
        toast(`Draft ${esc(res.name)} created, not submitted · <a target="_blank" href="/app/material-request/${encodeURIComponent(res.name)}">Open</a>`); await load(); }
      catch (e) { toast('Could not create: ' + esc(e.message)); b.disabled = false; b.textContent = 'Draft MR'; }
    });
    const ch = $('#ch-pipe'); if (ch) { const ms = D.monthly; vbars(ch, ms.map(x => fmtM(x.month)), [{ name: 'Invoiced', color: '#2a78d6', values: ms.map(x => x.si) }], { fmt: kfmt, target: D.fin.goal, targetLabel: 'Target ' + kfmt(D.fin.goal), h: 220 }); }
  }

  /* ---------------- render ---------------- */
  let WORK_SEG = false;
  const workSeg = () => `<div class="seg" style="margin:-8px 0 20px"><button data-go="work" class="${S.view === 'work' || S.view.startsWith('p-') ? 'on' : ''}">Projects</button><button data-go="tasks" class="${S.view === 'tasks' ? 'on' : ''}">All tasks &amp; to-dos</button></div>`;
  const PIPE = ['pipeline', 'quotes', 'orders', 'purch', 'mfg', 'ship'];
  function render() {
    const m = M();
    $('#ccstamp').textContent = 'Live from ERPNext · updated ' + new Date(D.generated.replace(' ', 'T')).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    let v = S.view; const so = v.startsWith('so-') ? decodeURIComponent(v.slice(3)) : null, pid = v.startsWith('p-') ? v.slice(2) : null;
    const known = PIPE.concat(['service', 'requests', 'inbox', 'finance', 'work', 'tasks', 'rec', 'exec', 'review']);
    if (!so && !pid && !known.includes(v) && !wbIsView()) { v = S.view = 'pipeline'; }
    const group = wbIsView() ? 'wb' : so || PIPE.includes(v) ? 'pipeline' : (pid || v === 'work' || v === 'tasks') ? 'work' : v;
    const p = pipeData(m);
    const svcOpen = D.tk.filter(t => (SVC_TYPES.includes(t.type) || !t.type) && t.status === 'Open');
    const TOP = [['pipeline', 'Sales pipeline', null, null], ['exec', 'Executive', null, null], ['service', 'Service', svcOpen.length, svcOpen.some(t => t.age > 2) ? 'bad' : 'good'], ['requests', 'Requests', m.openReq.length, m.oldReq.length ? 'warn' : 'good'], ['inbox', 'Inbox', m.tOpen.length, m.tOld.length > 3 ? 'bad' : m.tOld.length ? 'warn' : 'good'],
      ['finance', 'Finance', null, D.fin.mtd >= m.goalPace ? 'good' : 'warn'], ['work', 'Projects & tasks', m.overdue.length, m.overdue.length ? 'warn' : 'good'], ['review', 'Review', null, null], ['wb', 'Workbench', null, null], ['rec', 'Recommendations', null, 'info']];
    $('#ccnav').innerHTML = TOP.map(([k, n, c, s]) => `<a class="cc-tab ${group === k ? 'on' : ''}" href="#${k}">${s ? `<span class="dot ${s}"></span>` : ''}${n}${c ? `<span class="ct">${c}</span>` : ''}</a>`).join('');
    CUR_M = m; CUR_STEP = (PIPE.includes(v) && !so) ? v : null; WORK_SEG = group === 'work' && !pid; CUR_LINKS = so ? 'so' : pid ? 'project' : v;
    let html;
    if (so) html = V.so(m, so);
    else if (pid) html = V.project(m, pid);
    else if (wbIsView()) html = WB.html(v);
    else if (v === 'exec') html = EX.html();
    else if (v === 'review') html = RV.html();
    else if (v === 'purch') html = V.purch(m) + `<div class="grid" style="margin-top:20px">${V.purch_low()}</div>`;
    else html = ({ requests: V.req, inbox: V.inbox, finance: V.fin, tasks: V.tasks })[v] ? ({ requests: V.req, inbox: V.inbox, finance: V.fin, tasks: V.tasks })[v](m) : V[v](m);
    CUR_STEP = null; WORK_SEG = false; CUR_LINKS = null;
    $('#ccmain').innerHTML = html;
    bind(); bindProjects(); bindPipe(); if (wbIsView()) WB.mount();
    if (v === 'exec') EX.mount(); if (v === 'review') RV.mount(); if (v === 'mfg') PB.mount();
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
    root.querySelectorAll('[data-mr]').forEach(b => b.onclick = async () => {
      const r = D.purch.find(x => x.item === b.dataset.mr); if (!r) return;
      const date = r.need_by && r.need_by > TODAY ? r.need_by : addDays(TODAY, r.lead || 14);
      b.disabled = true; b.textContent = '…';
      try {
        const res = await call('frappe.client.insert', { doc: { doctype: 'Material Request', material_request_type: 'Purchase', company: 'ilLumenate Lighting', transaction_date: TODAY, schedule_date: date, set_warehouse: 'Stores - ilL',
          items: [{ item_code: r.item, qty: Math.ceil(r.short_firm), schedule_date: date, warehouse: 'Stores - ilL' }] } });
        toast(`Draft ${esc(res.name)} created, not submitted · <a target="_blank" href="/app/material-request/${encodeURIComponent(res.name)}">Open</a>`); await load();
      } catch (e) { toast('Could not create: ' + esc(e.message)); b.disabled = false; b.textContent = 'Draft MR'; }
    });
  }
  const addDays = (d, n) => { const t = new Date(d + 'T12:00'); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
  async function call(method, args) {
    const tok = CSRF(); if (!tok) throw new Error('please log in to ERPNext first');
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
  const WB = { cfg: null, cfgErr: null, cfgBusy: false, lists: {}, counts: null, cbusy: false, metas: {}, dt: null };
  const gw = (action, args) => call(GW, Object.assign({ action }, args || {}));
  const wbIsView = () => String(S.view || '').split('/')[0] === 'wb';
  const wbRoute = v => { const p = String(v || '').split('/'); return p[1] ? decodeURIComponent(p[1]) : null; };
  const wbLabel = dt => String(dt).replace(/^ilL-/, '').replace(/-/g, ' ');
  const wbPlain = v => String(v == null ? '' : v).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  const wbKind = s => {
    s = String(s || '');
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

  /* ---- landing: one card per stage ---- */
  function wbLanding() {
    const cfg = WB.cfg, byS = {};
    Object.keys(cfg.doctypes).forEach(d => { (byS[cfg.doctypes[d].section] = byS[cfg.doctypes[d].section] || []).push(d); });
    const cards = cfg.sections.map(s => {
      const dts = byS[s.key] || [];
      if (s.locked) return `<div class="card wb-card locked"><div class="wb-card-h"><h3>${esc(s.label)}</h3><span class="badge mute">🔒 Locked</span></div><p class="small">Needs the <b>${esc(s.needs)}</b> role. Ask Kevin.</p></div>`;
      if (!dts.length) return '';
      return `<div class="card wb-card"><div class="wb-card-h"><h3>${esc(s.label)}</h3></div>
        ${dts.map(d => { const n = WB.counts ? WB.counts[d] : null; return `<button class="wb-dt" data-wbdt="${esc(d)}"><span>${esc(wbLabel(d))}</span><span class="ct">${n == null ? '…' : n}</span></button>`; }).join('')}</div>`;
    }).join('');
    return `<div class="wb-head"><div><h1>Workbench</h1><p>Every doctype behind each stage in one place. Pick one to browse, open, edit or add records.</p></div>
      ${cfg.can_edit ? '<span class="badge good">Editor</span>' : '<span class="badge mute">View only</span>'}</div><div class="wb-grid">${cards}</div>`;
  }

  /* ---- list view: header + toolbar (static) and #wbdata (redrawn on every fetch) ---- */
  function wbListShell(dt) {
    const cfg = WB.cfg, info = cfg.doctypes[dt], L = wbL(dt);
    const sib = Object.keys(cfg.doctypes).filter(d => cfg.doctypes[d].section === info.section);
    const sec = cfg.sections.find(s => s.key === info.section) || {};
    return `<div class="wb-crumb"><a href="#wb">Workbench</a><span>›</span>${esc(sec.label || info.section)}</div>
      <div class="wb-head"><div><h1>${esc(wbLabel(dt))}</h1></div>
        <div class="wb-actions"><a class="cc-btn soft" target="_blank" rel="noopener" href="${wbListUrl(dt)}" style="text-decoration:none">Open in ERPNext</a>
        ${info.can_create ? `<button class="cc-btn primary" id="wbnew">+ New ${esc(wbLabel(dt))}</button>` : ''}</div></div>
      ${sib.length > 1 ? `<div class="seg wb-sib">${sib.map(d => `<button data-wbdt="${esc(d)}" class="${d === dt ? 'on' : ''}">${esc(wbLabel(d))}</button>`).join('')}</div>` : ''}
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
    const pref = ['item_code', 'item_name', 'qty', 'uom', 'rate', 'amount'];
    for (const k of Object.keys(doc)) {
      const a = doc[k]; if (!Array.isArray(a) || !a.length || typeof a[0] !== 'object' || !('item_code' in a[0])) continue;
      const cs = pref.filter(c => c in a[0] && !(c === 'item_name' && 'item_code' in a[0] && a[0].item_name === a[0].item_code));
      return `<div class="wb-sec">Line items</div><div class="card flush"><table class="wb-table"><thead><tr>${cs.map(c => `<th>${esc(c.replace('_', ' '))}</th>`).join('')}</tr></thead><tbody>${a.slice(0, 8).map(r => `<tr>${cs.map(c => `<td>${['rate', 'amount'].includes(c) ? money(Number(r[c])) : esc(r[c] == null ? '' : r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>${a.length > 8 ? `<div class="empty">+ ${a.length - 8} more · open in ERPNext to see all</div>` : ''}</div>`;
    }
    return '';
  }
  async function wbOpen(dt, name) {
    const el = wbShowSheet('<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>', '', esc(name));
    try {
      const [g, meta] = await Promise.all([gw('get', { dt, name }), wbMeta(dt)]);
      const doc = g.doc, L = wbL(dt), cols = (L.cols || WB.cfg.doctypes[dt].columns);
      const canEdit = g.editable && meta.fields.length;
      const why = !WB.cfg.can_edit ? 'View only. Ask Kevin for the Command Center Editor role to edit.' : doc.docstatus !== 0 ? 'Submitted or cancelled, so it is read-only here. Open it in ERPNext to amend.' : '';
      const kv = cols.filter(c => c.fieldname !== 'name' && !(c.fieldname === 'status' && doc.status)).map(c => `<div class="wb-kv"><span>${esc(c.label)}</span><b>${wbCell(c, doc[c.fieldname])}</b></div>`).join('');
      const req = meta.fields.filter(f => f.reqd), opt = meta.fields.filter(f => !f.reqd);
      const form = canEdit ? `<div class="wb-sec">Edit</div>${req.map(f => wbField(f, doc[f.fieldname])).join('')}${opt.length ? `<details class="wb-more-f"><summary>${opt.length} more fields</summary>${opt.map(f => wbField(f, doc[f.fieldname])).join('')}</details>` : ''}` : (why ? `<p class="wb-note">${esc(why)}</p>` : '');
      const aud = g.audit.length ? `<div class="wb-sec">Recent changes from the Command Center</div><ul class="wb-audit">${g.audit.map(a => `<li><span>${fmtd(a.creation)}</span> ${esc(wbPlain(a.content).replace(/^Command Center:\s*/, ''))}</li>`).join('')}</ul>` : '';
      const sh = wbShowSheet(`<div class="wb-kvs">${kv}</div>${wbItems(doc)}${form}${aud}<p class="cc-msg" id="wbMsg"></p>
        <div class="cc-sheet-f wb-foot"><a class="cc-btn soft" target="_blank" rel="noopener" href="${docUrl(dt, name)}" style="text-decoration:none">Open in ERPNext</a>${canEdit ? '<button class="cc-btn primary" type="submit" id="wbsave">Save changes</button>' : ''}</div>`,
        `${esc(wbLabel(dt))}${doc.status ? ' · ' + badge(doc.status, wbKind(doc.status)) : ''}`, esc(name));
      const f = sh.querySelector('#wbform'); wbLinks(f);
      f.onsubmit = async e => {
        e.preventDefault(); if (!canEdit) return;
        const vals = wbCollect(f, meta.fields, doc), msg = sh.querySelector('#wbMsg'), b = sh.querySelector('#wbsave');
        if (!Object.keys(vals).length) { msg.textContent = 'No changes to save.'; return; }
        b.disabled = true; b.textContent = 'Saving…'; msg.textContent = '';
        try { const r = await gw('save', { dt, name, values: vals }); closeSheet(); toast(`Saved ${esc(name)} · ${r.changed} field${r.changed === 1 ? '' : 's'} updated`); wbFetch(dt, false); }
        catch (err) { msg.textContent = 'Not saved: ' + err.message; b.disabled = false; b.textContent = 'Save changes'; }
      };
    } catch (e) { wbShowSheet(`<p class="cc-msg">Couldn't open ${esc(name)}: ${esc(e.message)}</p>`, '', esc(name)); }
  }
  async function wbNew(dt) {
    wbShowSheet('<div class="cc-loading"><span class="cc-spin"></span>Loading…</div>', '', 'New ' + esc(wbLabel(dt)));
    try {
      const meta = await wbMeta(dt), blocked = meta.required_tables.length > 0;
      const req = meta.fields.filter(f => f.reqd), opt = meta.fields.filter(f => !f.reqd);
      const sh = wbShowSheet(`${blocked ? `<div class="wb-banner">This needs line items (${esc(meta.required_tables.join(', '))}), which are added in ERPNext. <a target="_blank" rel="noopener" href="/app/${slug(dt)}/new">Create it in ERPNext ›</a></div>` : ''}
        ${blocked ? '' : `${req.map(f => wbField(f, f.default)).join('')}${opt.length ? `<details class="wb-more-f" ${req.length ? '' : 'open'}><summary>${opt.length} more fields</summary>${opt.map(f => wbField(f, f.default)).join('')}</details>` : ''}
        <p class="cc-msg" id="wbMsg"></p><div class="cc-sheet-f"><button class="cc-btn primary" type="submit" id="wbsave">Create draft</button></div>`}`,
        'Saved as a draft in ERPNext. Nothing is submitted.', 'New ' + esc(wbLabel(dt)));
      const f = sh.querySelector('#wbform'); wbLinks(f);
      f.onsubmit = async e => {
        e.preventDefault(); if (blocked) return;
        const msg = sh.querySelector('#wbMsg'), b = sh.querySelector('#wbsave'), vals = wbCollect(f, meta.fields, null);
        const miss = req.filter(r => vals[r.fieldname] === undefined).map(r => r.label || r.fieldname);
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
    r.querySelectorAll('[data-wbdt]').forEach(b => b.onclick = () => { location.hash = 'wb/' + encodeURIComponent(b.dataset.wbdt); });
    const n = r.querySelector('#wbnew'); if (n) n.onclick = () => wbNew(WB.dt);
    const q = r.querySelector('#wbq'); if (q) { let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { const L = wbL(WB.dt); L.search = q.value.trim(); wbFetch(WB.dt, false); }, 300); }; }
    wbData();
  }
  async function wbCounts() {
    if (WB.cbusy || !WB.cfg) return; WB.cbusy = true; let c = {};
    try { c = (await gw('counts')).counts || {}; Object.keys(c).forEach(k => { if (c[k] == null) c[k] = '—'; }); }
    catch (e) { await Promise.all(Object.keys(WB.cfg.doctypes).map(async d => { try { c[d] = (await gw('list', { dt: d, limit: 1 })).total; } catch (e2) { c[d] = '—'; } })); }
    WB.counts = c; WB.cbusy = false; if (wbIsView() && !WB.dt) { const r = $('#wbroot'); if (r) { r.innerHTML = wbBody(); wbBind(); } }
  }
  async function wbEnsure() {
    if (!WB.cfg && !WB.cfgBusy) { WB.cfgBusy = true; try { WB.cfg = await gw('config'); WB.cfgErr = null; } catch (e) { WB.cfgErr = e.message; } WB.cfgBusy = false; }
    if (!wbIsView()) return;
    const r = $('#wbroot'); if (r && !r.dataset.drawn) { r.innerHTML = wbBody(); wbBind(); }
    if (!WB.cfg) return;
    if (WB.dt && WB.cfg.doctypes[WB.dt]) { const L = wbL(WB.dt); if (!L.loaded && !L.loading) wbFetch(WB.dt, false); }
    else if (!WB.dt && !WB.counts) wbCounts();
  }
  WB.html = v => {
    WB.dt = wbRoute(v); const pre = String(v || '').split('/')[2];
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

  /* ---------------- init ---------------- */
  $('#ccwho').innerHTML = LOGGED ? `Signed in as ${esc(USER)}` : `Viewing as guest · <a href="/login?redirect-to=/command-center">Log in</a> to add tasks, close ToDos and draft orders`;
  $('#ccrefresh').onclick = () => load(true);
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
  setInterval(() => { if (!document.hidden && !$('#ccmodal').classList.contains('on') && !$('#ccsheet2').classList.contains('on')) load(); }, 5 * 60 * 1000);
})();