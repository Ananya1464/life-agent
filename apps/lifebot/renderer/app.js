/* Lifebot renderer: a view over the state owned by the main process. No user text goes through innerHTML. */
(function () {
  const api = window.lifebot;
  const R = window.Reminders;
  const P = window.Pomodoro;
  const $ = (id) => document.getElementById(id);

  const state = { tasks: [], markdown: '', reminders: [], settings: {}, pomodoro: null, history: [], busy: false, currentTaskId: null };

  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    children.flat().forEach((c) => { if (c != null) el.append(c); });
    return el;
  }

  function toast(text) {
    const t = h('div', { class: 'toast', text });
    $('toasts').append(t);
    setTimeout(() => t.remove(), 3500);
  }

  // ---------------------------------------------------------------- navigation
  function showTab(name) {
    if (name === 'dashboard') { openDashboard(); return; }
    document.querySelectorAll('.nav').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
    if (name === 'chat') $('chat-input').focus();
    if (name === 'tasks') $('task-input').focus();
  }
  document.querySelectorAll('.nav').forEach((b) => b.addEventListener('click', () => { Sfx.play('click'); showTab(b.dataset.tab); }));

  async function openDashboard() {
    toast('Building your dashboard...');
    const r = await api.dashboard.open();
    toast(r.ok ? 'Opened in Obsidian' : `Dashboard: ${r.error}`);
  }
  $('open-dashboard').addEventListener('click', openDashboard);

  function setBridge(status) {
    $('bridge-dot').className = `dot ${status}`;
    $('bridge-text').textContent = status === 'online' ? 'Agent online' : 'Agent offline';
  }

  function setBadge(id, n) {
    const el = $(id);
    el.textContent = n > 0 ? String(n) : '';
    el.classList.toggle('on', n > 0);
  }

  // ---------------------------------------------------------------- chat
  function addMessage(role, text, tag) {
    const m = h('div', { class: `msg ${role}` }, text);
    if (tag) m.append(h('span', { class: 'tag', text: tag }));
    $('chat-log').append(m);
    $('chat-log').scrollTop = $('chat-log').scrollHeight;
    return m;
  }

  const ACTION_LABEL = { add_reminder: 'Reminder added', add_task: 'Task added', start_focus: 'Focus started' };

  async function sendChat(message) {
    message = message.trim();
    if (!message || state.busy) return;
    state.busy = true;
    $('chat-send').disabled = true;
    $('chat-chips').hidden = true;
    addMessage('user', message);
    const typing = addMessage('bot typing', 'Lifebot is thinking...');
    try {
      const out = await api.chat.send({ message, history: state.history });
      typing.remove();
      const tag = (out.applied || []).map((a) => ACTION_LABEL[a]).filter(Boolean).join(' - ');
      addMessage('bot', out.reply, tag);
      state.history.push({ role: 'user', text: message }, { role: 'bot', text: out.reply });
      state.history = state.history.slice(-20);
    } catch (err) {
      typing.remove();
      addMessage('bot', `Something went wrong: ${err.message}`);
    } finally {
      state.busy = false;
      $('chat-send').disabled = false;
      $('chat-input').focus();
    }
  }

  $('chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = $('chat-input').value;
    $('chat-input').value = '';
    autosize();
    sendChat(text);
  });
  $('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('chat-form').requestSubmit(); }
  });
  function autosize() { const t = $('chat-input'); t.style.height = 'auto'; t.style.height = `${Math.min(t.scrollHeight, 140)}px`; }
  $('chat-input').addEventListener('input', autosize);
  document.querySelectorAll('#chat-chips .chip').forEach((c) => c.addEventListener('click', () => sendChat(c.textContent)));
  $('chat-clear').addEventListener('click', async () => {
    await api.chat.clear();
    state.history = [];
    $('chat-log').replaceChildren();
    $('chat-chips').hidden = false;
    greet();
  });

  function greet() {
    addMessage('bot', 'Hi Ananya, I am Lifebot. I can add tasks, set reminders, start a focus session on a task, and tell you how your focus has been going. What would you like to do?');
  }

  // ---------------------------------------------------------------- typewriter
  function renderTasks() {
    const list = $('task-list');
    list.replaceChildren();
    // today's tasks, then open tasks still hanging from earlier days (older finished ones are hidden)
    const tasks = state.tasks.filter((t) => t.isToday !== false);
    const carried = state.tasks.filter((t) => t.carried);
    $('tasks-summary').textContent = tasks.length ? `${tasks.filter((t) => t.checked).length}/${tasks.length} done today${carried.length ? ` · ${carried.length} carried over` : ''}` : (carried.length ? `${carried.length} carried over` : '');
    $('tasks-progress').style.width = tasks.length ? `${(100 * tasks.filter((t) => t.checked).length) / tasks.length}%` : '0';
    setBadge('tasks-badge', tasks.filter((t) => !t.checked).length + carried.length);
    if (!tasks.length && !carried.length) { list.append(h('div', { class: 'empty', text: 'No tasks yet. Type one above and press Enter.' })); }
    let phase = null;
    const addRow = (t) => {
      if (t.phase && t.phase !== phase && !t.carried) { phase = t.phase; list.append(h('div', { class: 'phase', text: phase })); }
      const box = h('button', {
        class: 'box', type: 'button', 'aria-label': t.checked ? 'Mark not done' : 'Mark done',
        onclick: () => { Sfx.play(t.checked ? 'click' : 'done'); api.tasks.toggle({ lineIndex: t.lineIndex, checked: !t.checked }); },
      }, t.checked ? '✓' : '');
      const isCurrent = state.currentTaskId === t.id;
      const pick = h('button', {
        class: `pick${isCurrent ? ' on' : ''}`, type: 'button', title: isCurrent ? 'Current task (click to clear)' : 'Make this the current task',
        'aria-label': isCurrent ? 'Clear the current task' : 'Make this the current task', 'aria-pressed': String(isCurrent),
        onclick: () => api.tasks.setCurrent(isCurrent ? null : t.id),
      }, isCurrent ? '\u25C9' : '\u25CE');
      const row = h('div', { class: `task${t.checked ? ' done' : ''}${isCurrent ? ' current' : ''}` }, box, pick,
        h('span', { class: 'task-text', text: t.text }),
        t.checked && t.doneTimestamp ? h('span', { class: 'task-ts', text: t.doneTimestamp.replace('T', ' ') }) : null,
        t.carried ? h('span', { class: 'task-ts', text: `from ${t.date}` }) : null,
        t.checked ? null : h('button', { class: 'start', type: 'button', text: '▶ Start', onclick: () => startTask(t) }),
        removeButton(t));
      list.append(row);
    };
    tasks.forEach(addRow);
    if (carried.length) {
      list.append(h('div', { class: 'phase carried', text: 'Carried over from earlier days (not completed)' }));
      carried.forEach(addRow);
    }
    renderFocusSelect();
    if (document.activeElement !== $('md-editor')) $('md-editor').value = state.markdown;
  }

  /** Two-step delete: the first click arms it, the second (within 3s) removes the task from the file. */
  function removeButton(t) {
    const b = h('button', { class: 'remove', type: 'button', title: 'Remove this task', 'aria-label': `Remove ${t.text}`, text: '✕' });
    let armed = null;
    b.addEventListener('click', async () => {
      if (!armed) {
        b.textContent = 'SURE?'; b.classList.add('armed');
        armed = setTimeout(() => { armed = null; b.textContent = '✕'; b.classList.remove('armed'); }, 3000);
        return;
      }
      clearTimeout(armed); armed = null;
      const res = await api.tasks.remove(t.id);
      if (res && res.ok === false) { toast(res.error || 'Could not remove'); b.textContent = '✕'; b.classList.remove('armed'); }
    });
    return b;
  }

  function startTask(t) {
    openPicker(t);                                 // choose the length first
  }

  $('task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $('task-input').value.trim();
    if (!text) return;
    $('task-input').value = '';
    await api.tasks.add(text);
  });
  $('md-toggle').addEventListener('click', () => {
    const pane = $('md-pane');
    pane.hidden = !pane.hidden;
    $('md-toggle').textContent = pane.hidden ? 'Edit as text' : 'Hide text';
  });
  $('md-save').addEventListener('click', async () => { await api.tasks.saveMarkdown($('md-editor').value); toast('Saved'); });

  // ---------------------------------------------------------------- focus

  function renderFocusSelect() {
    const sel = $('focus-select');
    const keep = sel.value;
    sel.replaceChildren(h('option', { value: '', text: 'Free focus (no task)' }),
      ...state.tasks.filter((t) => !t.checked).map((t) => h('option', { value: t.id, text: t.text })));
    if ([...sel.options].some((o) => o.value === keep)) sel.value = keep;
  }

  function renderPomodoro(v) {
    state.pomodoro = v;
    const idle = v.phase === 'idle';
    const total = idle ? state.settings.focusMin * 60000 : v.durationMs;
    const remaining = idle ? total : v.remainingMs;
    const stage = $('stage');
    $('focus-time').textContent = P.format(remaining);
    $('focus-phase').textContent = idle ? 'READY' : `${v.phase === 'focus' ? 'FOCUS' : 'BREAK'}${v.running ? '' : ' (PAUSED)'}`;
    $('focus-task').textContent = idle ? 'PICK A TASK' : (v.task ? v.task.text.toUpperCase() : 'FREE FOCUS');
    const pit = $('pit');
    pit.classList.toggle('running', !idle && v.phase === 'focus');
    pit.style.setProperty('--p', `${idle ? 0 : Math.round(100 * (1 - remaining / total))}%`);
    stage.classList.toggle('celebrate', v.phase === 'break');          // focus just finished: happy, hungry avocado
    $('focus-start').hidden = !idle;
    $('focus-select').hidden = !idle;
    $('focus-pause').hidden = idle || !v.running;
    $('focus-resume').hidden = idle || v.running;
    $('focus-stop').hidden = idle;
    $('focus-minus').hidden = idle || v.phase !== 'focus';
    $('focus-plus').hidden = idle || v.phase !== 'focus';
    $('focus-badge').textContent = idle ? '' : P.format(remaining);
    $('focus-badge').classList.toggle('on', !idle);
    const s = v.stats || { completed: 0, seconds: 0 };
    $('focus-stats').textContent = s.completed ? `Today: ${s.completed} session${s.completed === 1 ? '' : 's'}, ${Math.round(s.seconds / 60)} min` : 'No sessions yet today';
  }

  // the Focus tab shows exactly the same avocado as the floating timer
  document.getElementById('stage').insertAdjacentHTML('afterbegin', window.AVOCADO_SVG);

  $('focus-start').addEventListener('click', () => {
    const id = $('focus-select').value;
    openPicker(state.tasks.find((t) => t.id === id) || null);
  });
  $('focus-pause').addEventListener('click', () => api.pomodoro.pause());
  $('focus-resume').addEventListener('click', () => api.pomodoro.resume());
  $('focus-stop').addEventListener('click', () => { Sfx.play('click'); api.pomodoro.stop(); });
  for (const [id, key] of [['cfg-focus', 'focusMin'], ['cfg-break', 'breakMin']]) {
    $(id).addEventListener('change', async () => {
      const n = parseInt($(id).value, 10);
      if (Number.isFinite(n)) state.settings = await api.settings.set({ [key]: n });
      $(id).value = state.settings[key];
      if (state.pomodoro) renderPomodoro(state.pomodoro);
    });
  }

  // ---------------------------------------------------------------- start picker: choose the length
  let pickerTask = null;

  function markPreset() {
    const v = parseInt($('picker-minutes').value, 10);
    document.querySelectorAll('#picker-presets .chip').forEach((c) => c.classList.toggle('on', parseInt(c.dataset.m, 10) === v));
  }

  function openPicker(task) {
    pickerTask = task || { text: 'Free focus' };
    $('picker-task').textContent = pickerTask.text;
    const remembered = pickerTask.lastMinutes;
    $('picker-minutes').value = remembered || state.settings.focusMin;
    $('picker-hint').textContent = remembered ? `Last time: ${remembered} min` : 'Default length';
    $('picker-error').hidden = true;
    $('picker').hidden = false;
    markPreset();
    $('picker-minutes').focus();
    $('picker-minutes').select();
  }

  function closePicker() { $('picker').hidden = true; pickerTask = null; }

  async function confirmPicker() {
    const m = parseInt($('picker-minutes').value, 10);
    if (!Number.isFinite(m) || m < 1 || m > 180) {
      $('picker-error').textContent = 'Enter a length from 1 to 180 minutes';
      $('picker-error').hidden = false;
      return;
    }
    const t = pickerTask;
    closePicker();
    Sfx.play('start');
    await api.pomodoro.start({ id: t.id, text: t.text, minutes: m });
    showTab('focus');
  }

  document.querySelectorAll('#picker-presets .chip').forEach((c) => c.addEventListener('click', () => {
    $('picker-minutes').value = c.dataset.m;
    markPreset();
  }));
  $('picker-minutes').addEventListener('input', markPreset);
  $('picker-go').addEventListener('click', confirmPicker);
  $('picker-cancel').addEventListener('click', closePicker);
  $('picker').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); confirmPicker(); }
    else if (e.key === 'Escape') { e.preventDefault(); closePicker(); }
  });
  $('picker').addEventListener('click', (e) => { if (e.target === $('picker')) closePicker(); });
  $('focus-minus').addEventListener('click', () => api.pomodoro.adjust(-5));
  $('focus-plus').addEventListener('click', () => api.pomodoro.adjust(5));

  // ---------------------------------------------------------------- reminders
  function localInputValue(d) {
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function quickTime(kind) {
    const d = new Date();
    if (kind === '10m') d.setMinutes(d.getMinutes() + 10);
    else if (kind === '1h') d.setHours(d.getHours() + 1);
    else if (kind === 'tonight') { d.setHours(21, 0, 0, 0); if (d < new Date()) d.setDate(d.getDate() + 1); }
    else if (kind === 'tomorrow') { d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); }
    return localInputValue(d);
  }

  function renderReminders() {
    const list = $('rem-list');
    list.replaceChildren();
    const items = state.reminders;
    setBadge('rem-badge', items.filter((r) => r.status === 'fired').length);
    if (!items.length) list.append(h('div', { class: 'empty', text: 'No reminders. Add one above, or ask Lifebot.' }));
    for (const r of items) {
      const fired = r.status === 'fired';
      list.append(h('div', { class: `rem${fired ? ' fired' : ''}` },
        h('div', { class: 'rem-main' }, h('div', { text: r.text }),
          h('div', { class: 'rem-when', text: fired ? `Due ${R.describe(r)}` : R.describe(r) })),
        fired ? h('button', { class: 'ghost small', text: 'Snooze 10m', onclick: () => api.reminders.snooze({ id: r.id, minutes: 10 }) }) : null,
        fired ? h('button', { class: 'primary small', text: 'Done', onclick: () => api.reminders.done(r.id) }) : null,
        h('button', { class: 'ghost small', text: 'Delete', 'aria-label': 'Delete reminder', onclick: () => api.reminders.remove(r.id) })));
    }
  }

  $('rem-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('rem-error').hidden = true;
    try {
      await api.reminders.add({ text: $('rem-text').value, at: $('rem-at').value, repeat: $('rem-repeat').value });
      $('rem-text').value = '';
      $('rem-at').value = quickTime('1h');
    } catch (err) {
      $('rem-error').textContent = err.message.replace(/^Error invoking remote method '[^']+': (Error: )?/, '');
      $('rem-error').hidden = false;
    }
  });
  document.querySelectorAll('.quick .chip').forEach((c) => c.addEventListener('click', () => { $('rem-at').value = quickTime(c.dataset.q); }));

  function showAlert(r) {
    const card = h('div', { class: 'alert', role: 'alert' },
      h('div', { class: 'alert-title', text: 'Reminder' }),
      h('div', { class: 'alert-text', text: r.text }),
      h('div', { class: 'row' },
        h('button', { class: 'ghost small', text: 'Snooze 10m', onclick: () => { api.reminders.snooze({ id: r.id, minutes: 10 }); card.remove(); } }),
        h('button', { class: 'primary small', text: 'Done', onclick: () => { api.reminders.done(r.id); card.remove(); } })));
    $('alerts').append(card);
  }

  // ---------------------------------------------------------------- briefings
  let briefs = [];
  const noteText = new Map();                      // task -> text of the note being shown
  const when = (ms) => (ms ? new Date(ms).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : '');
  const STATUS = { ok: 'Done', failed: 'Failed', running: 'Running...', none: 'Not run yet' };

  function renderBriefs() {
    const list = $('brief-list');
    list.replaceChildren();
    const ok = briefs.filter((b) => b.status === 'ok').length;
    $('brief-summary').textContent = briefs.length ? `${ok}/${briefs.length} done` : '';
    setBadge('brief-badge', briefs.filter((b) => b.status === 'failed').length);
    for (const b of briefs) {
      const shown = noteText.has(b.task);
      const note = h('pre', { class: 'brief-note' });
      note.hidden = !shown;
      if (shown) note.textContent = noteText.get(b.task);
      const run = h('button', { class: 'ghost', type: 'button', text: 'Run now',
        onclick: async () => { Sfx.play('click'); const r = await api.briefs.run(b.task); if (r && r.ok === false) toast(r.error || 'Could not start'); } });
      run.disabled = b.status === 'running';
      const view = h('button', { class: 'ghost', type: 'button', text: shown ? 'Hide' : 'View latest',
        onclick: async () => {
          if (noteText.has(b.task)) { noteText.delete(b.task); renderBriefs(); return; }
          const r = await api.briefs.read(b.task);
          if (!r.ok) { toast(r.error || 'No note'); return; }
          noteText.set(b.task, r.text); renderBriefs();
        } });
      view.disabled = !b.note;
      const head = h('div', { class: 'brief-head' },
        h('div', { class: 'brief-title' }, h('strong', { text: b.label }),
          h('span', { class: 'muted', text: ` ${b.weekly ? 'weekly Mon' : 'daily'} ${b.time}` })),
        h('span', { class: `brief-status ${b.status}`, text: STATUS[b.status] || b.status }), run, view);
      const meta = b.status === 'failed' ? h('div', { class: 'brief-meta err', text: `${b.error || 'It did not finish.'} (${when(b.at)})` })
        : (b.at ? h('div', { class: 'brief-meta muted', text: `Last run ${when(b.at)}${b.note ? ` · ${b.note}` : ''}` }) : null);
      list.append(h('div', { class: 'card brief' }, head, meta, note));
    }
  }

  // ---------------------------------------------------------------- settings
  function renderSettings() {
    const s = state.settings;
    $('set-notifications').checked = !!s.notifications;
    $('set-nudges').checked = s.nudges !== false;
    $('set-briefings').checked = s.briefings !== false;
    $('set-login').checked = !!s.openAtLogin;
    $('set-avocado').checked = s.avocado !== false;
    $('set-typewriter').checked = s.typewriter !== false;
    if (document.activeElement !== $('set-ntfy')) $('set-ntfy').value = s.ntfyTopic || '';
    $('cfg-focus').value = s.focusMin;
    $('cfg-break').value = s.breakMin;
  }
  $('set-briefings').addEventListener('change', async (e) => { state.settings = await api.settings.set({ briefings: e.target.checked }); });
  $('set-nudges').addEventListener('change', async (e) => { state.settings = await api.settings.set({ nudges: e.target.checked }); });
  $('set-notifications').addEventListener('change', async (e) => { state.settings = await api.settings.set({ notifications: e.target.checked }); });
  $('set-typewriter').addEventListener('change', async (e) => { state.settings = await api.settings.set({ typewriter: e.target.checked }); });
  $('set-avocado').addEventListener('change', async (e) => { state.settings = await api.settings.set({ avocado: e.target.checked }); });
  $('set-login').addEventListener('change', async (e) => { state.settings = await api.settings.set({ openAtLogin: e.target.checked }); });
  $('ntfy-save').addEventListener('click', async () => {
    state.settings = await api.settings.set({ ntfyTopic: $('set-ntfy').value });
    $('ntfy-msg').textContent = state.settings.ntfyTopic ? 'Saved. Reminders will also be pushed to your phone.' : 'Phone push turned off.';
  });
  $('ntfy-test').addEventListener('click', async () => {
    state.settings = await api.settings.set({ ntfyTopic: $('set-ntfy').value });
    const r = await api.reminders.testPush();
    $('ntfy-msg').textContent = r.ok ? 'Test sent. Check your phone.' : `Could not send: ${r.error}`;
  });
  $('sync-now').addEventListener('click', async () => {
    $('sync-msg').textContent = 'Syncing...';
    const r = await api.sync.now();
    $('sync-msg').textContent = !r.ok ? `Failed: ${r.error}` : r.result.skipped_empty ? 'Nothing new to sync.' : `Synced ${r.result.pushed} event(s)${r.result.failed ? `, ${r.result.failed} failed` : ''}.`;
  });

  // ---------------------------------------------------------------- game HUD
  const XP_BLOCKS = 14;
  let lastLevel = null;

  function renderHud(g) {
    if (!g) return;
    $('hud-total').textContent = String(g.total);
    $('hud-today').textContent = `DIAMONDS +${g.today} TODAY`;
    $('hud-lv').textContent = `LV ${g.level} ${String(g.title || '').toUpperCase()}`;
    $('hud-streak').textContent = `${g.streak} DAY${g.streak === 1 ? '' : 'S'}`;
    $('hud-xptext').textContent = `${g.xp}/${g.xp_needed} TO LV ${g.level + 1}`;
    const filled = Math.round((XP_BLOCKS * g.xp_pct) / 100);
    const bar = $('hud-xp');
    bar.replaceChildren(...Array.from({ length: XP_BLOCKS }, (_, i) => h('span', { class: i < filled ? 'on' : '' })));
    lastLevel = g.level;
  }

  function floatText(text, cls) {
    const el = h('div', { class: `float ${cls || ''}`, text });
    document.body.append(el);
    setTimeout(() => el.remove(), 1600);
  }

  function onReward(reward) {
    renderHud(reward.stats);
    if (reward.level_up) {
      Sfx.play('levelup');
      floatText(`LEVEL UP! LV ${reward.stats.level}`, 'big');
    } else if (reward.diamonds > 0) {
      Sfx.play('diamond');
      floatText(`+${reward.diamonds} DIAMONDS`);
    }
  }

  function setSound(on) {
    Sfx.setEnabled(on);
    $('sound-toggle').textContent = on ? 'SOUND ON' : 'SOUND OFF';
    $('sound-toggle').classList.toggle('off', !on);
  }

  $('sound-toggle').addEventListener('click', async () => {
    const on = !Sfx.isEnabled();
    state.settings = await api.settings.set({ sound: on });
    setSound(on);
    if (on) Sfx.play('click');
  });
  $('hud-gem').append(window.Pixel.sprite('gem', 4));
  $('hud-flame').append(window.Pixel.sprite('flame', 4));

  // ---------------------------------------------------------------- boot
  async function boot() {
    const init = await api.init();
    Object.assign(state, { tasks: init.tasks, markdown: init.markdown, reminders: init.reminders, settings: init.settings, currentTaskId: init.currentTaskId || null });
    $('today-label').textContent = new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' });
    setBridge(init.bridge);
    for (const m of init.chat) addMessage(m.role === 'user' ? 'user' : 'bot', m.text);
    state.history = init.chat.slice(-20);
    if (!init.chat.length) greet(); else $('chat-chips').hidden = true;
    $('rem-at').value = quickTime('1h');
    renderTasks(); renderReminders(); renderSettings(); renderPomodoro(init.pomodoro);
    setSound(init.settings.sound !== false);
    renderHud(init.game);
    api.game.stats().then(renderHud);

    api.on.tasks((p) => { state.tasks = p.tasks; state.markdown = p.markdown; state.currentTaskId = p.currentTaskId || null; renderTasks(); });
    api.on.reminders((list) => { state.reminders = list; renderReminders(); });
    api.on.reminderFired(showAlert);
    api.on.pomodoro(renderPomodoro);
    api.on.bridge(setBridge);
    api.on.navigate(showTab);
    api.on.toast(toast);
    api.on.game(renderHud);
    api.on.reward(onReward);
    api.on.settings((s) => { state.settings = s; renderSettings(); });
    api.on.briefs((list) => { briefs = list; renderBriefs(); });
    api.briefs.list().then((list) => { briefs = list; renderBriefs(); });
    showTab('chat');
  }
  boot().catch((err) => { document.body.prepend(h('div', { class: 'error', text: `Failed to start: ${err.message}` })); });
})();
