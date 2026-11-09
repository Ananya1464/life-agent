/* Lifebot on the phone. Talks only to this app's /api; the server reads and writes your vault in OneDrive. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = window.LifebotMarkdown.escape;
  const P = window.Pomodoro;
  const VIEWS = ['chat', 'tasks', 'focus', 'reminders', 'briefings'];
  const BRIEF_LABELS = {
    meal_plan: 'Meal plan', ai_edge: 'AI Edge: opportunities and research', career_prep: 'Career prep',
    evening_checkin: 'Evening check-in', goal_planner: 'Full day plan', tomorrow_planner: "Tomorrow's plan", weekly_review: 'Weekly review',
  };
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: keep going */ } },
  };

  let S = { tasks: { tasks: [], summary: { total: 0, done: 0 }, etag: null, markdown: '' }, reminders: [], briefings: [], today: '', pushReady: false, chatReady: false, user: null };
  let lastLoad = 0;
  let current = 'chat';

  // ------------------------------------------------------------------ plumbing
  function toast(text, ms = 3200) {
    const t = $('toast');
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, ms);
  }

  function setDot(state) { const d = $('sync-dot'); d.className = `dot ${state}`; d.title = state === 'online' ? 'Synced with your vault' : state === 'offline' ? 'Offline' : 'Syncing'; }

  async function api(path, { method = 'GET', body } = {}) {
    const opts = { method, headers: { 'X-Lifebot': '1' }, credentials: 'same-origin' };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, opts); } catch {
      setDot('offline');
      throw new Error('No connection. Check your internet and try again.');
    }
    const j = await r.json().catch(() => ({}));
    if ((r.status === 401 || r.status === 403) && j.signIn) { showSignIn(j.error); const e = new Error(j.error || 'Please sign in'); e.silent = true; throw e; }
    if (!r.ok) { const e = new Error(j.error || `Something went wrong (${r.status})`); e.status = r.status; e.data = j; throw e; }
    setDot('online');
    return j;
  }

  function fail(err) { if (!err.silent) toast(err.message); }

  function showSignIn(message) {
    $('shell').hidden = true;
    $('signin').hidden = false;
    if (!$('signin-art').firstChild && window.AVOCADO_SVG) $('signin-art').innerHTML = window.AVOCADO_SVG;
    const errBox = $('signin-error');
    if (message && message !== 'Please sign in') { errBox.textContent = message; errBox.hidden = false; }
  }

  // ------------------------------------------------------------------ navigation
  function go(name) {
    if (!VIEWS.includes(name)) name = 'chat';
    current = name;
    document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === name));
    document.querySelectorAll('.tabs a').forEach((a) => {
      if (a.dataset.tab === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (name === 'focus') renderFocus();
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', () => go(location.hash.slice(1)));

  // ------------------------------------------------------------------ load
  async function load({ quiet = false } = {}) {
    setDot('');
    try {
      const j = await api('/api/state');
      S = { ...S, ...j };
      lastLoad = Date.now();
      $('shell').hidden = false;
      $('signin').hidden = true;
      if (j.user && j.user.email === 'dev@local' && !document.querySelector('.dev-banner')) {
        document.body.insertAdjacentHTML('afterbegin', '<div class="dev-banner">LOCAL TEST MODE: reading a folder on this computer</div>');
      }
      renderAll();
      flushOutbox();
    } catch (e) { if (!quiet) fail(e); }
  }

  function renderAll() {
    const d = S.today ? new Date(`${S.today}T12:00:00`) : new Date();
    $('today-label').textContent = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase();
    renderTasks();
    fillFocusSelect();
    renderFocus();
    renderReminders();
    renderBriefings();
    renderChat();
  }

  // ------------------------------------------------------------------ tasks
  let editing = null;

  function renderTasks() {
    const { tasks, summary } = S.tasks;
    const open = tasks.filter((t) => !t.checked).length;
    $('tasks-summary').textContent = `${summary.done}/${summary.total} done`;
    $('tasks-progress').style.width = summary.total ? `${Math.round((summary.done / summary.total) * 100)}%` : '0';
    const badge = $('tasks-badge');
    badge.textContent = open; badge.classList.toggle('on', open > 0);
    const list = $('task-list');
    if (!tasks.length) { list.innerHTML = '<div class="empty">No tasks yet. Type one above.</div>'; return; }
    const running = pomo.state.phase === 'focus' && pomo.state.task ? pomo.state.task.id : null;
    let html = '';
    let phase;
    tasks.forEach((t) => {
      if (t.phase !== phase) { phase = t.phase; if (phase) html += `<div class="phase">${esc(phase)}</div>`; }
      const ts = t.checked && t.doneTimestamp ? `<span class="task-ts">done ${esc(String(t.doneTimestamp).replace('T', ' '))}</span>` : '';
      html += `<div class="task${t.checked ? ' done' : ''}${running === t.id ? ' current' : ''}" data-id="${esc(t.id)}">
        <button class="box" type="button" data-act="toggle" aria-label="${t.checked ? 'Mark not done' : 'Mark done'}">${t.checked ? '&#10003;' : ''}</button>
        <button class="task-text" type="button" data-act="edit">${esc(t.text)}${ts}</button>
        ${t.checked ? '' : '<button class="start" type="button" data-act="focus" aria-label="Focus on this task">&#9654;</button>'}
      </div>`;
    });
    list.innerHTML = html;
  }

  const findTask = (id) => S.tasks.tasks.find((t) => t.id === id);

  async function taskOp(op, { quiet = false } = {}) {
    try {
      const j = await api('/api/tasks', { method: 'POST', body: op });
      S.tasks = j.tasks;
      renderTasks(); fillFocusSelect();
      return j;
    } catch (e) {
      if (e.data && e.data.tasks) { S.tasks = e.data.tasks; renderTasks(); fillFocusSelect(); }
      if (!quiet) fail(e);
      throw e;
    }
  }

  $('task-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const input = $('task-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    try { await taskOp({ op: 'add', text }); } catch { input.value = text; }
  });

  $('task-list').addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-act]');
    if (!btn) return;
    const row = btn.closest('.task');
    const t = row && findTask(row.dataset.id);
    if (!t) return;
    if (btn.dataset.act === 'toggle') {
      const checked = !t.checked;
      t.checked = checked;                                   // optimistic
      row.classList.toggle('done', checked);
      btn.innerHTML = checked ? '&#10003;' : '';
      if (checked) beep(880, 0.08);
      taskOp({ op: 'toggle', id: t.id, text: t.text, checked }).catch(() => {});
    } else if (btn.dataset.act === 'edit') {
      openSheet(t);
    } else if (btn.dataset.act === 'focus') {
      startFocus(t);
      location.hash = 'focus';
    }
  });

  function openSheet(t) {
    editing = t;
    $('sheet-input').value = t.text;
    $('sheet-error').hidden = true;
    $('sheet-focus').hidden = t.checked;
    $('sheet').hidden = false;
    setTimeout(() => $('sheet-input').focus(), 50);
  }
  const closeSheet = () => { $('sheet').hidden = true; editing = null; };
  $('sheet-cancel').addEventListener('click', closeSheet);
  $('sheet').addEventListener('click', (ev) => { if (ev.target.id === 'sheet') closeSheet(); });
  $('sheet-save').addEventListener('click', async () => {
    if (!editing) return;
    try { await taskOp({ op: 'edit', id: editing.id, oldText: editing.text, newText: $('sheet-input').value }, { quiet: true }); closeSheet(); }
    catch (e) { $('sheet-error').textContent = e.message; $('sheet-error').hidden = false; }
  });
  $('sheet-delete').addEventListener('click', async () => {
    if (!editing) return;
    const btn = $('sheet-delete');
    if (!btn.dataset.armed) { btn.dataset.armed = '1'; btn.textContent = 'Tap again to delete'; setTimeout(() => { delete btn.dataset.armed; btn.textContent = 'Delete'; }, 3000); return; }
    delete btn.dataset.armed; btn.textContent = 'Delete';
    try { await taskOp({ op: 'remove', id: editing.id, text: editing.text }, { quiet: true }); closeSheet(); toast('Task deleted.'); }
    catch (e) { $('sheet-error').textContent = e.message; $('sheet-error').hidden = false; }
  });
  $('sheet-focus').addEventListener('click', () => { if (editing) { const t = editing; closeSheet(); startFocus(t); location.hash = 'focus'; } });

  $('md-toggle').addEventListener('click', () => {
    const pane = $('md-pane');
    pane.hidden = !pane.hidden;
    $('md-toggle').textContent = pane.hidden ? 'Edit as text' : 'Close text editor';
    if (!pane.hidden) $('md-editor').value = S.tasks.markdown || '';
  });
  $('md-save').addEventListener('click', async () => {
    try {
      await taskOp({ op: 'save', markdown: $('md-editor').value, etag: S.tasks.etag }, { quiet: true });
      $('md-pane').hidden = true; $('md-toggle').textContent = 'Edit as text';
      toast('Saved to Tasks.md');
    } catch (e) {
      toast(e.message, 5000);
      if (e.data && e.data.tasks) $('md-editor').value = e.data.tasks.markdown;
    }
  });

  // ------------------------------------------------------------------ focus (avocado timer)
  const pomo = ls.get('lb_pomo', null) || { state: P.idle(), cfg: { focusMin: 25, breakMin: 5 }, today: { date: '', sessions: 0, minutes: 0 } };
  if (!pomo.today) pomo.today = { date: '', sessions: 0, minutes: 0 };
  const savePomo = () => ls.set('lb_pomo', pomo);

  function fillFocusSelect() {
    const sel = $('focus-select');
    const keep = sel.value;
    const open = S.tasks.tasks.filter((t) => !t.checked);
    sel.innerHTML = '<option value="">Free focus (no task)</option>' + open.map((t) => `<option value="${esc(t.id)}">${esc(t.text)}</option>`).join('');
    if (pomo.state.task && open.some((t) => t.id === pomo.state.task.id)) sel.value = pomo.state.task.id;
    else if (open.some((t) => t.id === keep)) sel.value = keep;
  }

  function sendFocus(evt) {
    api('/api/focus', { method: 'POST', body: evt }).then((j) => {
      if (evt.type === 'started' && j && j.pushScheduled === false && S.pushReady) toast('Could not schedule the end-of-session push. Keep the app open.');
    }).catch(() => {
      const box = ls.get('lb_outbox', []);
      box.push(evt);
      ls.set('lb_outbox', box.slice(-50));
    });
  }

  async function flushOutbox() {
    const box = ls.get('lb_outbox', []);
    if (!box.length) return;
    ls.set('lb_outbox', []);
    for (const evt of box) {
      if (['started', 'resumed', 'adjusted'].includes(evt.type) && Number(evt.endsAt) < Date.now()) continue;   // stale push
      try { await api('/api/focus', { method: 'POST', body: evt }); } catch { const b = ls.get('lb_outbox', []); b.push(evt); ls.set('lb_outbox', b); }
    }
  }

  function handleEvents(events, now) {
    for (const e of events) {
      const base = { task: e.task, runId: e.runId };
      if (e.type === 'started') sendFocus({ type: 'started', ...base, endsAt: now + pomo.state.durationMs });
      if (e.type === 'abandoned') sendFocus({ type: 'abandoned', ...base, durationSec: e.durationSec });
      if (e.type === 'completed') {
        sendFocus({ type: 'completed', ...base, durationSec: e.durationSec });
        if (pomo.today.date !== S.today) pomo.today = { date: S.today, sessions: 0, minutes: 0 };
        pomo.today.sessions += 1; pomo.today.minutes += Math.round(e.durationSec / 60);
        celebrate();
        beep(660, 0.12); setTimeout(() => beep(990, 0.18), 160);
        toast(e.task ? `Done: ${e.task.text}. Break time.` : 'Focus done. Break time.', 5000);
      }
      if (e.type === 'break_done') { beep(520, 0.15); toast('Break over. Ready for the next one?'); }
    }
  }

  function apply(result, now) { pomo.state = result.state; handleEvents(result.events, now); savePomo(); renderFocus(); renderTasks(); }

  function startFocus(task) {
    const now = Date.now();
    const t = task ? { id: task.id, text: task.text } : null;
    if (t) $('focus-select').value = t.id;
    apply(P.start(pomo.state, t, now, pomo.cfg), now);
  }

  $('focus-start').addEventListener('click', () => {
    const id = $('focus-select').value;
    startFocus(id ? findTask(id) : null);
  });
  $('focus-pause').addEventListener('click', () => {
    const now = Date.now();
    apply(P.pause(pomo.state, now), now);
    if (pomo.state.phase === 'focus') sendFocus({ type: 'paused', task: pomo.state.task, runId: pomo.state.runId });
  });
  $('focus-resume').addEventListener('click', () => {
    const now = Date.now();
    apply(P.resume(pomo.state, now), now);
    if (pomo.state.phase === 'focus') sendFocus({ type: 'resumed', task: pomo.state.task, runId: pomo.state.runId, endsAt: now + P.remainingMs(pomo.state, now) });
  });
  $('focus-stop').addEventListener('click', () => { const now = Date.now(); apply(P.stop(pomo.state, now), now); });
  const adjust = (min) => {
    const now = Date.now();
    apply(P.adjust(pomo.state, min * 60000, now), now);
    if (pomo.state.phase === 'focus' && pomo.state.runningSince !== null) {
      sendFocus({ type: 'adjusted', task: pomo.state.task, runId: pomo.state.runId, endsAt: now + P.remainingMs(pomo.state, now) });
    }
  };
  $('focus-minus').addEventListener('click', () => adjust(-5));
  $('focus-plus').addEventListener('click', () => adjust(5));
  ['cfg-focus', 'cfg-break'].forEach((id) => $(id).addEventListener('change', () => {
    const f = Math.min(120, Math.max(1, Number($('cfg-focus').value) || 25));
    const b = Math.min(60, Math.max(1, Number($('cfg-break').value) || 5));
    pomo.cfg = { focusMin: f, breakMin: b };
    savePomo(); renderFocus();
  }));

  function renderFocus() {
    if (!$('stage').querySelector('svg') && window.AVOCADO_SVG) $('stage').insertAdjacentHTML('afterbegin', window.AVOCADO_SVG);
    const now = Date.now();
    const v = P.view(pomo.state, now);
    const idle = v.phase === 'idle';
    $('focus-time').textContent = P.format(idle ? pomo.cfg.focusMin * 60000 : v.remainingMs);
    $('focus-phase').textContent = idle ? 'READY' : v.phase === 'focus' ? (v.running ? 'FOCUS' : 'PAUSED') : (v.running ? 'BREAK' : 'PAUSED');
    $('focus-task').textContent = v.task ? v.task.text.toUpperCase() : (idle ? 'PICK A TASK' : 'FREE FOCUS');
    const pit = $('pit');
    pit.classList.toggle('running', !idle);
    pit.style.setProperty('--p', idle || !v.durationMs ? '0%' : `${Math.round((1 - v.remainingMs / v.durationMs) * 100)}%`);
    $('focus-start').hidden = !idle;
    $('focus-select').disabled = !idle;
    $('focus-pause').hidden = idle || !v.running;
    $('focus-resume').hidden = idle || v.running;
    $('focus-stop').hidden = idle;
    $('focus-stop').textContent = v.phase === 'break' ? 'Skip break' : 'Stop';
    $('focus-minus').hidden = $('focus-plus').hidden = v.phase !== 'focus';
    $('cfg-focus').value = pomo.cfg.focusMin; $('cfg-break').value = pomo.cfg.breakMin;
    const today = pomo.today && pomo.today.date === S.today ? pomo.today : { sessions: 0, minutes: 0 };
    $('focus-stats').textContent = `${today.sessions} today · ${today.minutes} min`;
    const fb = $('focus-badge');
    fb.textContent = v.phase === 'focus' ? '!' : ''; fb.classList.toggle('on', v.phase === 'focus');
    $('focus-note').textContent = S.pushReady ? 'Your phone gets a push when the time is up, even if it is locked.' : 'Phone push is off, so keep the app open to hear the end.';
  }

  function celebrate() { const st = $('stage'); st.classList.add('celebrate'); setTimeout(() => st.classList.remove('celebrate'), 4000); }

  let audio = null;
  function beep(freq, dur) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const o = audio.createOscillator(); const g = audio.createGain();
      o.type = 'square'; o.frequency.value = freq; g.gain.value = 0.05;
      o.connect(g); g.connect(audio.destination); o.start();
      g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + dur); o.stop(audio.currentTime + dur + 0.02);
    } catch { /* sound is optional */ }
  }

  setInterval(() => {
    const now = Date.now();
    const r = P.tick(pomo.state, now, pomo.cfg);
    if (r.events.length) apply(r, now);
    else if (pomo.state.phase !== 'idle' && current === 'focus') renderFocus();
  }, 500);

  // ------------------------------------------------------------------ reminders
  const pad = (n) => String(n).padStart(2, '0');
  const toInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  function setRemAt(d) { $('rem-at').value = toInput(d); }
  function whenText(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  function renderReminders() {
    const pending = S.reminders.filter((r) => r.status === 'pending');
    const past = S.reminders.filter((r) => r.status !== 'pending').slice(0, 10);
    $('rem-summary').textContent = `${pending.length} upcoming`;
    const b = $('rem-badge'); b.textContent = pending.length; b.classList.toggle('on', pending.length > 0);
    const soon = Date.now() + 3 * 24 * 3600e3 - 15 * 60000;
    const item = (r) => {
      const rep = r.repeat && r.repeat !== 'none' ? ` · repeats ${r.repeat}` : '';
      let note = '';
      if (r.status === 'pending' && S.pushReady && !r.armedCount && Date.parse(r.at) > soon) note = '<br><span>Push is scheduled once you open the app within 3 days of it.</span>';
      if (r.status === 'missed') note = '<br><span class="warn">Missed: no push was sent, because the app was not opened in the 3 days before it.</span>';
      const actions = r.status === 'pending'
        ? `<button class="ghost tiny" data-act="done">${r.repeat !== 'none' ? 'Stop repeating' : 'Done'}</button><button class="ghost tiny" data-act="snooze">Snooze 10m</button><button class="danger tiny" data-act="remove">Delete</button>`
        : '<button class="danger tiny" data-act="remove">Remove</button>';
      return `<div class="rem ${r.status}" data-id="${esc(r.id)}"><div class="rem-text">${esc(r.text)}</div><div class="rem-when">${esc(whenText(r.at))}${esc(rep)}${r.status !== 'pending' ? ` · ${esc(r.status)}` : ''}${note}</div><div class="rem-actions">${actions}</div></div>`;
    };
    $('rem-list').innerHTML = (pending.length ? pending.map(item).join('') : '<div class="empty">No reminders. Add one above, or ask Lifebot in chat.</div>')
      + (past.length ? `<div class="section-label">Recent</div>${past.map(item).join('')}` : '');
    $('push-state').textContent = S.pushReady ? 'Phone push: on' : 'Phone push: off';
    $('push-help').textContent = S.pushReady
      ? 'Reminders reach you through the ntfy app, the same topic as your desktop Lifebot. ntfy can hold a push for up to 3 days, so later reminders are scheduled the next time you open this app.'
      : 'Set NTFY_TOPIC on the server (Vercel settings) to the same topic your desktop Lifebot uses, then redeploy.';
    $('push-test').disabled = !S.pushReady;
  }

  async function remOp(body, okText) {
    try {
      const j = await api('/api/reminders', { method: 'POST', body });
      S.reminders = j.reminders; S.pushReady = j.pushReady;
      renderReminders();
      if (okText) toast(okText);
      return j;
    } catch (e) { fail(e); throw e; }
  }

  $('rem-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const text = $('rem-text').value.trim();
    const at = new Date($('rem-at').value);
    if (!text || Number.isNaN(at.getTime())) return toast('Add what and when.');
    try {
      await remOp({ op: 'add', text, at: at.toISOString(), repeat: $('rem-repeat').value }, `Reminder set for ${whenText(at.toISOString())}.`);
      $('rem-text').value = ''; setRemAt(new Date(Date.now() + 30 * 60000));
    } catch { /* toast shown */ }
  });
  $('rem-quick').addEventListener('click', (ev) => {
    const b = ev.target.closest('button');
    if (!b) return;
    if (b.dataset.min) setRemAt(new Date(Date.now() + Number(b.dataset.min) * 60000));
    if (b.dataset.tomorrow) { const [h, m] = b.dataset.tomorrow.split(':').map(Number); const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(h, m, 0, 0); setRemAt(d); }
  });
  $('rem-list').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-act]');
    const row = b && b.closest('.rem');
    if (!row) return;
    const id = row.dataset.id;
    if (b.dataset.act === 'done') remOp({ op: 'done', id, all: true }, 'Done.').catch(() => {});
    if (b.dataset.act === 'snooze') remOp({ op: 'snooze', id, minutes: 10 }, 'Snoozed for 10 minutes.').catch(() => {});
    if (b.dataset.act === 'remove') remOp({ op: 'remove', id }, 'Removed.').catch(() => {});
  });
  $('push-test').addEventListener('click', () => api('/api/reminders', { method: 'POST', body: { op: 'test' } }).then(() => toast('Test push sent. Check your ntfy app.')).catch(fail));

  // ------------------------------------------------------------------ briefings + vault
  const navStack = [];

  function renderBriefings() {
    const list = S.briefings || [];
    $('brief-summary').textContent = list.length ? `${list.filter((b) => b.date === S.today).length} today` : '';
    if (!list.length) { $('brief-list').innerHTML = '<div class="empty">No briefings found in your vault yet.</div>'; return; }
    const yday = (() => { const d = new Date(`${S.today}T12:00:00`); d.setDate(d.getDate() - 1); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; })();
    let html = '';
    let day;
    list.slice(0, 40).forEach((b) => {
      if (b.date !== day) {
        day = b.date;
        const label = day === S.today ? 'TODAY' : day === yday ? 'YESTERDAY' : new Date(`${day}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase();
        html += `<div class="brief-day">${esc(label)}</div>`;
      }
      html += `<button class="brief-item" type="button" data-open="Briefings/${esc(b.name)}"><span>${esc(BRIEF_LABELS[b.kind] || b.kind.replace(/_/g, ' '))}</span><span class="arrow">&gt;</span></button>`;
    });
    $('brief-list').innerHTML = html;
  }

  function showNote(show) { $('brief-index').hidden = show; $('note-view').hidden = !show; window.scrollTo(0, 0); }

  async function openNote(path, push = true) {
    if (push) navStack.push({ path });
    showNote(true);
    const bm = /^Briefings\/(\d{4}-\d{2}-\d{2}) ([a-z_]+)\.md$/.exec(path);
    $('note-title').textContent = bm
      ? `${BRIEF_LABELS[bm[2]] || bm[2].replace(/_/g, ' ')} · ${new Date(`${bm[1]}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}`
      : path.split('/').pop().replace(/\.md$/, '');
    $('note-meta').textContent = 'Loading...';
    $('note-body').innerHTML = '';
    try {
      const j = await api(`/api/note?path=${encodeURIComponent(path)}`);
      $('note-meta').textContent = j.modified ? `Updated ${new Date(j.modified).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : '';
      $('note-body').innerHTML = window.LifebotMarkdown.render(j.text, { suggestions: j.suggestions });
    } catch (e) { $('note-meta').textContent = ''; $('note-body').innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  }

  async function openFolder(folder, push = true) {
    if (push) navStack.push({ folder });
    showNote(true);
    $('note-title').textContent = folder || 'ANANYA-OS';
    $('note-meta').textContent = 'Loading...';
    $('note-body').innerHTML = '';
    try {
      const j = await api(`/api/note?folder=${encodeURIComponent(folder)}`);
      $('note-meta').textContent = `${j.entries.length} items`;
      $('note-body').innerHTML = j.entries.length ? `<div class="brief-list">${j.entries.map((e) => {
        const p = folder ? `${folder}/${e.name}` : e.name;
        return e.isFolder
          ? `<button class="brief-item folder" type="button" data-folder="${esc(p)}"><span>${esc(e.name)}/</span><span class="arrow">&gt;</span></button>`
          : `<button class="brief-item" type="button" data-open="${esc(p)}"><span>${esc(e.name.replace(/\.md$/, ''))}</span><span class="arrow">&gt;</span></button>`;
      }).join('')}</div>` : '<div class="empty">Nothing here.</div>';
    } catch (e) { $('note-meta').textContent = ''; $('note-body').innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  }

  $('view-briefings').addEventListener('click', async (ev) => {
    const idea = ev.target.closest('.add-idea');
    if (idea) {
      idea.disabled = true;
      try { await taskOp({ op: 'add', text: idea.dataset.idea }, { quiet: true }); idea.textContent = 'Added'; toast('Added to your tasks.'); }
      catch (e) { idea.disabled = false; toast(e.message); }
      return;
    }
    const b = ev.target.closest('[data-open],[data-folder]');
    if (!b) return;
    if (b.dataset.open !== undefined) openNote(b.dataset.open);
    else openFolder(b.dataset.folder);
  });
  $('note-back').addEventListener('click', () => {
    navStack.pop();
    const prev = navStack[navStack.length - 1];
    if (!prev) return showNote(false);
    if (prev.path !== undefined) openNote(prev.path, false); else openFolder(prev.folder, false);
  });

  // ------------------------------------------------------------------ chat
  const chat = ls.get('lb_chat', []);
  const saveChat = () => ls.set('lb_chat', chat.slice(-40));

  function renderChat() {
    const log = $('chat-log');
    const intro = S.chatReady ? '' : '<div class="msg bot">Chat is not set up yet: the server needs GEMINI_API_KEY (or NVIDIA_API_KEY). Your tasks, focus timer, reminders and briefings all work without it.</div>';
    log.innerHTML = intro + (chat.length ? chat.map((m) => `<div class="msg ${m.role === 'user' ? 'user' : 'bot'}">${esc(m.text)}${m.tag ? `<span class="tag">${esc(m.tag)}</span>` : ''}</div>`).join('')
      : '<div class="msg bot">Hi Ananya. I can see your tasks, reminders, briefings and vault notes. What do you need?</div>');
    $('chat-chips').hidden = chat.length > 0;
    if (current === 'chat') log.lastElementChild && log.lastElementChild.scrollIntoView({ block: 'end' });
  }

  async function sendChat(text) {
    text = String(text || '').trim();
    if (!text) return;
    const history = chat.slice(-10).map((m) => ({ role: m.role, text: m.text }));
    chat.push({ role: 'user', text });
    saveChat(); renderChat();
    $('chat-log').insertAdjacentHTML('beforeend', '<div class="msg bot typing" id="typing">THINKING...</div>');
    $('typing').scrollIntoView({ block: 'end' });
    $('chat-send').disabled = true;
    try {
      const j = await api('/api/chat', { method: 'POST', body: { message: text, history } });
      const tags = [];
      for (const a of j.actions || []) {
        if (a.type === 'tasks_changed') tags.push('tasks updated');
        if (a.type === 'reminders_changed') tags.push('reminder saved');
        if (a.type === 'start_focus') { const t = findTask(a.taskId) || { id: a.taskId, text: a.text }; startFocus(t); tags.push('focus started'); }
      }
      chat.push({ role: 'bot', text: j.reply, tag: tags.length ? `✓ ${tags.join(', ')}` : '' });
      if ((j.actions || []).some((a) => a.type !== 'start_focus')) load({ quiet: true });
      if ((j.actions || []).some((a) => a.type === 'start_focus')) setTimeout(() => { location.hash = 'focus'; }, 900);
    } catch (e) {
      if (!e.silent) chat.push({ role: 'bot', text: `I could not answer: ${e.message}` });
    } finally {
      $('chat-send').disabled = false;
      saveChat(); renderChat();
    }
  }

  $('chat-form').addEventListener('submit', (ev) => { ev.preventDefault(); const t = $('chat-input').value; $('chat-input').value = ''; autosize(); sendChat(t); });
  $('chat-input').addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' && !ev.shiftKey && !('ontouchstart' in window)) { ev.preventDefault(); $('chat-form').requestSubmit(); }
  });
  const autosize = () => { const ta = $('chat-input'); ta.style.height = 'auto'; ta.style.height = `${Math.min(160, ta.scrollHeight)}px`; };
  $('chat-input').addEventListener('input', autosize);
  $('chat-chips').addEventListener('click', (ev) => { const b = ev.target.closest('.chip'); if (b) sendChat(b.textContent); });
  $('chat-clear').addEventListener('click', () => { chat.length = 0; saveChat(); renderChat(); });

  // ------------------------------------------------------------------ start
  $('refresh').addEventListener('click', () => load());
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    const now = Date.now();
    const r = P.tick(pomo.state, now, pomo.cfg);
    if (r.events.length) apply(r, now);
    if (now - lastLoad > 20000) load({ quiet: true });
  });

  const params = new URLSearchParams(location.search);
  if (params.get('signin_error')) {
    showSignIn(params.get('signin_error'));
    history.replaceState(null, '', location.pathname + location.hash);
  }
  setRemAt(new Date(Date.now() + 30 * 60000));
  go(location.hash.slice(1) || 'chat');
  renderFocus();
  load().then(() => { fillFocusSelect(); renderFocus(); });

  if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('/sw.js').catch(() => {});
})();
