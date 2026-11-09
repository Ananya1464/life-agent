/* Typewriter card: shows the current task, edits it in place, starts the timer for it, and can minimize.
   Lifebot's main process owns all the data and the clock; this window only displays and requests. */
(function () {
  const api = window.typewriterAPI;
  const $ = (id) => document.getElementById(id);
  const view = $('view'), editor = $('editor'), errorEl = $('error'), statusEl = $('status'), hint = $('hint');
  const startBtn = $('start'), miniText = $('mini-text');
  const MAX = 200;
  const listEl = $('tasklist'), miniListEl = $('mini-tasklist'), miniListBtn = $('mini-list-btn'), listCount = $('list-count');
  let miniOpen = false;

  let task = { state: 'none' };
  let editing = false;
  let baseText = '';
  let statusTimer = null;
  let tick = null;

  const mmss = (ms) => {
    const t = Math.max(0, Math.ceil(ms / 1000));
    return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
  };

  function setStatus(text, isError) {
    statusEl.textContent = text;
    statusEl.style.color = isError ? '#b3261e' : '#2f7d32';
    clearTimeout(statusTimer);
    if (text && !isError) statusTimer = setTimeout(() => { statusEl.textContent = ''; }, 1800);
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = !message;
  }

  /** The timer, as it relates to the task shown on this card. */
  function timerFor() {
    const t = task.timer;
    if (!t || t.phase !== 'focus') return { kind: 'idle' };
    return { kind: task.state === 'ok' && t.taskId === task.id ? 'mine' : 'other', t };
  }

  function remainingText() {
    const t = task.timer;
    if (!t) return '';
    return mmss(t.running && t.endsAt ? t.endsAt - Date.now() : t.remainingMs);
  }

  function renderStart() {
    const tm = timerFor();
    startBtn.classList.remove('stop');
    if (task.state !== 'ok') { startBtn.disabled = true; startBtn.textContent = '▶ START'; return; }
    if (task.checked) { startBtn.disabled = true; startBtn.textContent = 'DONE ✓'; return; }
    if (tm.kind === 'mine') { startBtn.disabled = false; startBtn.classList.add('stop'); startBtn.textContent = `■ STOP ${remainingText()}`; return; }
    if (tm.kind === 'other') { startBtn.disabled = true; startBtn.textContent = `BUSY ${remainingText()}`; return; }
    startBtn.disabled = false;
    startBtn.textContent = '▶ START';
  }

  function renderMini() {
    const tm = timerFor();
    // collapsed: show what is RUNNING (even if another task is selected), else the current task
    const runningRow = tm.kind !== 'idle' && Array.isArray(task.tasks) ? task.tasks.find((r) => r.id === tm.t.taskId) : null;
    const name = runningRow ? runningRow.text : (task.state === 'ok' ? task.text : 'No task');
    miniText.textContent = tm.kind !== 'idle' ? `${remainingText()}  ${name}` : name;
  }

  /** One row per task in the file: click the text to make it current, the play button to start it. */
  function renderRows(ul, rows) {
    ul.textContent = '';
    if (!rows.length) {
      const li = document.createElement('li');
      li.className = 'list-empty';
      li.textContent = 'No tasks yet. Add one in Lifebot.';
      ul.appendChild(li);
      return;
    }
    const running = task.timer && task.timer.phase === 'focus' ? task.timer.taskId : null;
    rows.forEach((r) => {
      const li = document.createElement('li');
      li.className = 'task-row' + (r.id === task.id ? ' current' : '') + (r.checked ? ' checked' : '');
      const text = document.createElement('button');
      text.type = 'button';
      text.className = 'row-text';
      text.textContent = (r.checked ? '✓ ' : '') + r.text;
      text.title = r.text;
      text.addEventListener('click', () => { api.select(r.id); });
      li.appendChild(text);
      if (running === r.id) {
        const run = document.createElement('span');
        run.className = 'row-run';
        run.textContent = '● ' + remainingText();
        li.appendChild(run);
      } else if (!r.checked) {
        const go = document.createElement('button');
        go.type = 'button';
        go.className = 'start-btn row-go';
        go.textContent = '▶';
        go.title = 'Start ' + r.text;
        go.setAttribute('aria-label', 'Start ' + r.text);
        go.disabled = !!running;                                  // one timer at a time
        go.addEventListener('click', async () => {
          const res = await api.start(undefined, r.id);
          if (res && res.ok === false) { showError(res.error || 'Could not start'); setStatus('NOT STARTED', true); }
        });
        li.appendChild(go);
      }
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'row-del';
      del.textContent = '✕';
      del.title = 'Remove this task';
      del.setAttribute('aria-label', 'Remove ' + r.text);
      let armed = null;                                           // two steps: arm, then confirm within 3s
      del.addEventListener('click', async () => {
        if (!armed) {
          del.textContent = '?'; del.classList.add('armed');
          armed = setTimeout(() => { armed = null; del.textContent = '✕'; del.classList.remove('armed'); }, 3000);
          return;
        }
        clearTimeout(armed); armed = null;
        const res = await api.remove(r.id);
        if (res && res.ok === false) { showError(res.error || 'Could not remove'); setStatus('NOT REMOVED', true); del.textContent = '✕'; del.classList.remove('armed'); }
      });
      li.appendChild(del);
      ul.appendChild(li);
    });
  }

  function renderLists() {
    const rows = Array.isArray(task.tasks) ? task.tasks : [];
    listCount.textContent = rows.length ? `${rows.filter((r) => !r.checked).length}/${rows.length} OPEN` : '';
    renderRows(listEl, rows);
    if (miniOpen) renderRows(miniListEl, rows.filter((r) => !r.checked));
  }

  function render() {
    renderLists();
    view.classList.toggle('none', task.state !== 'ok');
    view.classList.toggle('done', task.state === 'ok' && !!task.checked);
    if (task.state === 'ok') {
      view.textContent = task.text;
      view.tabIndex = 0;
      view.setAttribute('role', 'button');
      hint.textContent = task.checked ? 'Marked done. Click to edit.' : 'Click the task to edit.';
    } else {
      view.textContent = 'No task selected';
      view.tabIndex = -1;
      view.removeAttribute('role');
      hint.textContent = 'Pick one in Lifebot with the circle button.';
    }
    renderStart();
    renderMini();
    // tick locally once a second while a timer runs (no polling of the main process)
    clearInterval(tick);
    tick = null;
    if (task.timer && task.timer.running && task.timer.endsAt) {
      tick = setInterval(() => { renderStart(); renderMini(); renderLists(); }, 1000);
    }
  }

  function startEdit() {
    if (task.state !== 'ok' || editing) return;
    editing = true;
    baseText = task.text;
    editor.value = task.text;
    view.hidden = true;
    editor.hidden = false;
    hint.textContent = 'Enter saves · Esc cancels';
    showError('');
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  }

  function endEdit() {
    editing = false;
    editor.hidden = true;
    view.hidden = false;
    showError('');
    render();
  }

  async function save() {
    const newText = editor.value;
    const trimmed = newText.trim();
    if (trimmed.length > MAX) { showError(`Too long: ${trimmed.length}/${MAX} characters (nothing was saved)`); return; }
    const res = await api.update({ id: task.id, oldText: baseText, newText });
    if (res.ok) {
      task = { ...task, id: res.id, text: res.text };
      endEdit();
      setStatus('SAVED');
    } else if (res.code === 'conflict') {
      task = { ...task, text: res.currentText };
      endEdit();
      showError(res.error);
      setStatus('CHANGED', true);
    } else {
      showError(res.error || 'Could not save');      // keep the draft open so nothing is lost
      setStatus('NOT SAVED', true);
    }
  }

  view.addEventListener('click', startEdit);
  view.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); startEdit(); } });
  editor.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); save(); }
    else if (e.key === 'Escape') { e.preventDefault(); endEdit(); setStatus(''); }
  });

  const picker = $('picker'), pickerMin = $('picker-min'), pickerNote = $('picker-note');

  function markPreset() {
    const v = parseInt(pickerMin.value, 10);
    picker.querySelectorAll('.chip').forEach((c) => c.classList.toggle('on', parseInt(c.dataset.m, 10) === v));
  }

  function openPicker() {
    pickerMin.value = task.minutes || 25;
    pickerNote.textContent = task.remembered ? 'Last length used for this task' : 'Pick a length (minutes)';
    picker.hidden = false;
    hint.hidden = true;
    markPreset();
    pickerMin.focus();
    pickerMin.select();
  }

  function closePicker() { picker.hidden = true; hint.hidden = false; }

  async function confirmPicker() {
    const m = parseInt(pickerMin.value, 10);
    if (!Number.isFinite(m) || m < 1 || m > 180) { pickerNote.textContent = 'Enter 1 to 180 minutes'; return; }
    closePicker();
    const res = await api.start(m);
    if (res && res.ok === false) { showError(res.error || 'Could not start'); setStatus('NOT STARTED', true); }
  }

  picker.querySelectorAll('.chip').forEach((c) => c.addEventListener('click', () => { pickerMin.value = c.dataset.m; markPreset(); }));
  pickerMin.addEventListener('input', markPreset);
  $('picker-go').addEventListener('click', confirmPicker);
  picker.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); confirmPicker(); }
    else if (e.key === 'Escape') { e.preventDefault(); closePicker(); }
  });

  startBtn.addEventListener('click', async () => {
    if (timerFor().kind === 'mine') { await api.stop(); return; }
    if (picker.hidden) openPicker(); else closePicker();           // choose the length first
  });
  $('wc-min').addEventListener('click', () => api.collapse(true));
  $('wc-expand').addEventListener('click', () => api.collapse(false));
  $('wc-hide').addEventListener('click', () => api.hide());
  $('wc-home').addEventListener('click', () => api.openApp());

  const setMini = (on) => document.body.classList.toggle('mini', !!on);
  function setMiniOpen(on) {
    miniOpen = !!on;
    document.body.classList.toggle('list', miniOpen);
    miniListEl.hidden = !miniOpen;
    miniListBtn.setAttribute('aria-expanded', String(miniOpen));
    if (miniOpen) renderLists();
  }
  miniListBtn.addEventListener('click', () => api.miniList(!miniOpen));
  api.onMode((m) => { setMini(m.collapsed); setMiniOpen(!!m.collapsed && !!m.list); });

  api.onChange((next) => {
    if (typeof next.collapsed === 'boolean') { setMini(next.collapsed); if (!next.collapsed) setMiniOpen(false); }
    if (editing && next.state === 'ok' && next.text !== baseText) {
      showError('This task changed in Lifebot. Esc reloads it; saving will be refused if it differs.');
      setStatus('CHANGED', true);
      return;                                            // never overwrite the user's draft
    }
    task = next;
    if (!editing) render();
  });

  api.get().then((s) => { task = s; setMini(!!s.collapsed); render(); });
  // a task started from the pill's list closes it (main resizes the window back)
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && miniOpen && !editing) api.miniList(false); });
  window.__tw = {
    debug: () => ({ editing, task, pickerOpen: !$('picker').hidden, pickerValue: $('picker-min').value, pickerNote: $('picker-note').textContent, status: statusEl.textContent, error: errorEl.hidden ? '' : errorEl.textContent,
      mini: document.body.classList.contains('mini'), startLabel: startBtn.textContent, startDisabled: startBtn.disabled, miniText: miniText.textContent,
      rows: [...listEl.querySelectorAll('.task-row')].map((r) => ({ text: r.querySelector('.row-text').textContent, current: r.classList.contains('current'), canStart: !!r.querySelector('.row-go') && !r.querySelector('.row-go').disabled, running: !!r.querySelector('.row-run') })),
      miniOpen, miniRows: miniListEl.querySelectorAll('.task-row').length }),
  };
}());
