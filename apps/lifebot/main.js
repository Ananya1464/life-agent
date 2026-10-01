/**
 * Lifebot desktop app - main process.
 *
 * Owns the authoritative state (tasks file, reminders, Pomodoro clock) so everything keeps working
 * while the window is closed to the tray. The renderer is just a view; the Python agent is reached
 * through lib/pybridge.js.
 */
const { app, BrowserWindow, Tray, Menu, Notification, ipcMain, nativeImage, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const { PyBridge } = require('./lib/pybridge.js');
const envLib = require('./lib/env.js');
const R = require('./lib/reminders.js');
const P = require('./lib/pomodoro.js');
const T = require('./lib/tasks.js');
const ntfy = require('./lib/ntfy.js');
const { createStore } = require('./lib/store.js');

const APP_ID = 'com.ananya.lifebot';
const HIDDEN_START = process.argv.includes('--hidden');
const ICON_PATH = path.join(__dirname, 'assets', 'icon.png');
const DEFAULT_SETTINGS = { ntfyTopic: '', openAtLogin: true, notifications: true, focusMin: 25, breakMin: 5 };
const OUTBOX_MAX = 500;

let win = null;
let tray = null;
let bridge = null;
let store = null;
let pythonInfo = null;
let repoRoot = null;
let pomo = P.idle();
let quitting = false;
let flushing = false;

app.setAppUserModelId(APP_ID);

// Test mode (LIFEBOT_SMOKE_DIR): isolated profile, no autostart registration, no single-instance lock
const SMOKE_DIR = process.env.LIFEBOT_SMOKE_DIR || '';
if (process.env.LIFEBOT_USER_DATA) app.setPath('userData', process.env.LIFEBOT_USER_DATA);

if (!SMOKE_DIR && !app.requestSingleInstanceLock()) {
  app.quit();
} else if (!SMOKE_DIR) {
  app.on('second-instance', () => showWindow());
}

// ------------------------------------------------------------------ helpers
const send = (channel, payload) => {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
};

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Local wall-clock timestamp (YYYY-MM-DDTHH:mm) for the "(done ...)" marker; toISOString() would be UTC. */
function localStamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${todayIso()}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

const settings = () => ({ ...DEFAULT_SETTINGS, ...store.get().settings });
const tasksFile = () => process.env.LIFEBOT_TASKS_FILE || path.join(app.getPath('documents'), 'Typewriter', 'tasks.md');

function readTasksMarkdown() {
  try {
    return fs.readFileSync(tasksFile(), 'utf8');
  } catch (err) {
    if (err.code !== 'ENOENT') console.error('tasks read failed:', err.message);
    return T.DEFAULT_MARKDOWN;
  }
}

function writeTasksMarkdown(markdown) {
  fs.mkdirSync(path.dirname(tasksFile()), { recursive: true });
  const tmp = `${tasksFile()}.tmp`;
  fs.writeFileSync(tmp, markdown, 'utf8');
  fs.renameSync(tmp, tasksFile());
}

const currentTasks = () => T.listTasks(readTasksMarkdown(), todayIso());

function notify(title, body, tab) {
  if (!settings().notifications || !Notification.isSupported()) return;
  const n = new Notification({ title, body, icon: ICON_PATH });
  n.on('click', () => { showWindow(); if (tab) send('navigate', tab); });
  n.show();
}

// ------------------------------------------------------------------ python bridge + outbox
async function setupBackend() {
  if (process.env.LIFEBOT_NO_PYTHON) return;
  repoRoot = envLib.findRepoRoot(__dirname);
  if (!repoRoot) { console.error('Life Agent repo not found; chat and syncing are disabled.'); return; }
  const dotEnv = (() => {
    try { return envLib.parseDotEnv(fs.readFileSync(path.join(repoRoot, '.env'), 'utf8')); } catch (_) { return {}; }
  })();
  const s = settings();
  if (!s.ntfyTopic && dotEnv.NTFY_TOPIC) store.update((d) => { d.settings = { ...d.settings, ntfyTopic: dotEnv.NTFY_TOPIC }; });

  // Probing interpreters takes several seconds, so remember the one that worked last time
  const cached = store.get().pythonPath;
  pythonInfo = cached && (cached === 'python' || fs.existsSync(cached))
    ? { python: cached, score: -1, missing: [] }
    : await envLib.pickPython(envLib.candidatePythons(repoRoot));
  if (pythonInfo && pythonInfo.python !== cached) store.update((d) => { d.pythonPath = pythonInfo.python; });
  if (!pythonInfo) { console.error('No usable Python found; chat and syncing are disabled.'); send('bridge:status', 'offline'); return; }
  // In test mode the agent runs in a sandbox: its own data dir, no Notion sync, dashboard in the temp dir
  const sandbox = SMOKE_DIR ? path.join(SMOKE_DIR, 'bridge-cwd') : null;
  if (sandbox) fs.mkdirSync(sandbox, { recursive: true });
  bridge = new PyBridge({
    python: pythonInfo.python, cwd: sandbox || repoRoot,
    env: {
      ...process.env, PYTHONPATH: path.join(repoRoot, 'src'), PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1',
      LLM_MAX_RETRIES: '1',               // interactive chat: fail over to the backup model quickly
      ...(sandbox ? { EVENTS_SYNC_DATA_SOURCE_ID: '', EVENTS_SYNC_DB_ID: '', LIFE_AGENT_DASHBOARD_DIR: path.join(sandbox, 'dashboard') } : {}),
    },
  });
  bridge.on('status', (status) => {
    send('bridge:status', status);
    if (status === 'online') flushOutbox();
    // a cached interpreter that no longer works: forget it so the next launch probes again
    if (status === 'offline' && Date.now() - bridge.lastStart < 3000) store.update((d) => { d.pythonPath = null; });
  });
  bridge.on('log', (line) => console.log('[python]', line));
  bridge.start();
  flushOutbox();
}

/** Record-type calls go through a persistent outbox so nothing is lost while Python is down. */
function enqueue(method, params) {
  store.update((d) => {
    d.outbox = d.outbox || [];
    d.outbox.push({ method, params });
    if (d.outbox.length > OUTBOX_MAX) d.outbox.splice(0, d.outbox.length - OUTBOX_MAX);
  });
  flushOutbox();
}

async function flushOutbox() {
  if (flushing || !bridge) return;
  flushing = true;
  try {
    while ((store.get().outbox || []).length) {
      const item = store.get().outbox[0];
      try {
        await bridge.request(item.method, item.params, 30000);
      } catch (err) {
        if (/^ValueError|^KeyError|^TypeError/.test(err.message)) {
          console.error('dropping invalid outbox item:', err.message);   // would never succeed
        } else {
          return;                                                         // bridge down/slow: retry later
        }
      }
      store.update((d) => { d.outbox.shift(); });
    }
  } finally {
    flushing = false;
  }
}

/** On launch: push any unsynced events to Notion and refresh the Obsidian dashboard. Best effort. */
function refreshDataInBackground() {
  if (!bridge) return;
  bridge.request('sync', {}, 120000).catch((err) => console.log('startup sync skipped:', err.message));
  bridge.request('refresh_dashboard', {}, 60000).catch((err) => console.log('startup dashboard skipped:', err.message));
}

// ------------------------------------------------------------------ pomodoro (authoritative clock)
function pomoCfg() { const s = settings(); return { focusMin: s.focusMin, breakMin: s.breakMin }; }

function applyPomo(result) {
  pomo = result.state;
  for (const e of result.events) handlePomoEvent(e);
  broadcastPomo();
}

function handlePomoEvent(e) {
  const taskText = (e.task && e.task.text) || 'Free focus';
  const base = { task: taskText, task_id: (e.task && e.task.id) || 'free', run_id: e.runId };
  if (e.type === 'started') {
    enqueue('record_focus', { ...base, phase: 'started' });
  } else if (e.type === 'completed') {
    enqueue('record_focus', { ...base, phase: 'completed', duration_seconds: e.durationSec });
    bumpStats(e.durationSec);
    notify('Focus session complete', `${taskText} - take a ${settings().breakMin}-minute break.`, 'focus');
    send('toast', { text: `Focus complete: ${taskText}` });
    pushPhone('Focus session complete', taskText);
  } else if (e.type === 'abandoned') {
    enqueue('record_focus', { ...base, phase: 'abandoned', duration_seconds: e.durationSec });
  } else if (e.type === 'break_done') {
    notify('Break over', 'Ready for the next focus session?', 'focus');
  }
}

function bumpStats(seconds) {
  store.update((d) => {
    const day = todayIso();
    if (!d.stats || d.stats.date !== day) d.stats = { date: day, completed: 0, seconds: 0 };
    d.stats.completed += 1;
    d.stats.seconds += seconds;
  });
}

function pomoView() {
  const v = P.view(pomo, Date.now());
  const stats = store.get().stats;
  return { ...v, stats: stats && stats.date === todayIso() ? stats : { date: todayIso(), completed: 0, seconds: 0 } };
}

function broadcastPomo() {
  const v = pomoView();
  send('pomodoro:state', v);
  if (tray) {
    tray.setToolTip(v.phase === 'idle' ? 'Lifebot'
      : `Lifebot - ${v.phase === 'focus' ? 'Focus' : 'Break'} ${P.format(v.remainingMs)}${v.task ? ' - ' + v.task.text : ''}`);
  }
}

function startFocus(task) {
  const known = task && task.id ? currentTasks().find((t) => t.id === task.id) : null;
  applyPomo(P.start(pomo, known ? { id: known.id, text: known.text } : { id: 'free', text: (task && task.text) || 'Free focus' }, Date.now(), pomoCfg()));
}

setInterval(() => {
  if (!store) return;                                     // before the app is ready
  const r = P.tick(pomo, Date.now(), pomoCfg());
  if (r.events.length) applyPomo(r); else if (pomo.phase !== 'idle') broadcastPomo();
}, 1000);

// ------------------------------------------------------------------ reminders
function remindersView() {
  return (store.get().reminders || []).filter((r) => r.status !== 'done')
    .sort((a, b) => String(a.at).localeCompare(String(b.at)));
}

function pushPhone(title, body) {
  const topic = settings().ntfyTopic;
  if (topic) ntfy.send(topic, title, body).then((r) => { if (!r.ok) console.error('ntfy:', r.error); });
}

function checkReminders() {
  const now = new Date();
  const due = R.due(store.get().reminders || [], now);
  if (!due.length) return;
  store.update((d) => {
    d.reminders = d.reminders.map((r) => (due.find((x) => x.id === r.id) ? R.fire(r, now) : r));
  });
  due.slice(0, 5).forEach((r) => {
    notify('Lifebot reminder', r.text, 'reminders');
    pushPhone('Lifebot reminder', r.text);
    send('reminder:fired', { id: r.id, text: r.text, repeat: r.repeat });
  });
  if (due.length > 5) notify('Lifebot reminders', `${due.length - 5} more reminders are due.`, 'reminders');
  send('reminders:changed', remindersView());
}
setInterval(() => { if (!store) return; try { checkReminders(); } catch (e) { console.error('reminder check failed:', e); } }, 5000);

function addReminder(input) {
  const reminder = R.make(input, new Date());
  store.update((d) => { d.reminders = [...(d.reminders || []), reminder]; });
  send('reminders:changed', remindersView());
  return reminder;
}

function mutateReminder(id, fn) {
  store.update((d) => { d.reminders = (d.reminders || []).map((r) => (r.id === id ? fn(r) : r)); });
  send('reminders:changed', remindersView());
}

// ------------------------------------------------------------------ tasks
function recordPlanned() {
  const day = todayIso();
  const seen = new Set((store.get().planned || {})[day] || []);
  const fresh = currentTasks().filter((t) => !t.checked && !seen.has(t.id));
  fresh.forEach((t) => enqueue('record_task', { status: 'planned', task: t.text, task_id: t.id }));
  if (fresh.length) {
    store.update((d) => { d.planned = { [day]: [...seen, ...fresh.map((t) => t.id)] }; });
  }
}

function tasksPayload() {
  const tasks = currentTasks();
  return { tasks, markdown: readTasksMarkdown(), done: tasks.filter((t) => t.checked).length };
}

function addTask(text) {
  writeTasksMarkdown(T.addTask(readTasksMarkdown(), text));
  recordPlanned();
  send('tasks:changed', tasksPayload());
}

// ------------------------------------------------------------------ chat
function applyChatActions(actions) {
  const applied = [];
  for (const a of actions || []) {
    try {
      if (a.type === 'add_reminder') { addReminder({ text: a.text, at: a.at, repeat: a.repeat }); applied.push(a.type); }
      else if (a.type === 'add_task') { addTask(a.text); applied.push(a.type); }
      else if (a.type === 'start_focus') { startFocus({ id: a.taskId, text: a.text }); send('navigate', 'focus'); applied.push(a.type); }
    } catch (err) {
      console.error(`chat action ${a.type} failed:`, err.message);
    }
  }
  return applied;
}

async function chat({ message, history }) {
  if (!bridge) {
    return { reply: 'My brain (the Python agent) is not available right now. Tasks, reminders and the timer still work.', actions: [] };
  }
  const state = {
    tasks: currentTasks().map((t) => ({ id: t.id, text: t.text, checked: t.checked })),
    reminders: remindersView().map((r) => ({ id: r.id, text: r.text, at: r.at, repeat: r.repeat, status: r.status })),
  };
  try {
    const out = await bridge.request('chat', { message, history: (history || []).slice(-10), state }, 90000);
    out.applied = applyChatActions(out.actions);
    return out;
  } catch (err) {
    return { reply: `I could not reach my brain (${err.message}). Please try again in a moment.`, actions: [], applied: [] };
  }
}

// ------------------------------------------------------------------ ipc
function registerIpc() {
  ipcMain.handle('app:init', () => ({
    ...tasksPayload(),
    reminders: remindersView(),
    settings: settings(),
    pomodoro: pomoView(),
    bridge: bridge && bridge.online ? 'online' : 'offline',
    python: pythonInfo,
    chat: store.get().chat || [],
    today: todayIso(),
  }));

  ipcMain.handle('tasks:add', (_e, text) => { addTask(String(text || '')); return tasksPayload(); });
  ipcMain.handle('tasks:toggle', (_e, { lineIndex, checked }) => {
    const before = currentTasks().find((t) => t.lineIndex === lineIndex);
    writeTasksMarkdown(T.toggle(readTasksMarkdown(), lineIndex, !!checked, localStamp()));
    if (before && checked) enqueue('record_task', { status: 'completed', task: before.text, task_id: before.id });
    const payload = tasksPayload();
    send('tasks:changed', payload);
    return payload;
  });
  ipcMain.handle('tasks:saveMarkdown', (_e, markdown) => {
    writeTasksMarkdown(String(markdown));
    recordPlanned();
    const payload = tasksPayload();
    send('tasks:changed', payload);
    return payload;
  });

  ipcMain.handle('pomodoro:start', (_e, task) => { startFocus(task); return pomoView(); });
  ipcMain.handle('pomodoro:pause', () => { applyPomo(P.pause(pomo, Date.now())); return pomoView(); });
  ipcMain.handle('pomodoro:resume', () => { applyPomo(P.resume(pomo, Date.now())); return pomoView(); });
  ipcMain.handle('pomodoro:stop', () => { applyPomo(P.stop(pomo, Date.now())); return pomoView(); });

  ipcMain.handle('reminders:add', (_e, input) => { addReminder(input); return remindersView(); });
  ipcMain.handle('reminders:remove', (_e, id) => {
    store.update((d) => { d.reminders = (d.reminders || []).filter((r) => r.id !== id); });
    send('reminders:changed', remindersView());
    return remindersView();
  });
  ipcMain.handle('reminders:done', (_e, id) => { mutateReminder(id, (r) => R.complete(r, new Date())); return remindersView(); });
  ipcMain.handle('reminders:snooze', (_e, { id, minutes }) => {
    const r = (store.get().reminders || []).find((x) => x.id === id);
    if (!r) return remindersView();
    if (r.repeat === 'none') mutateReminder(id, (x) => R.snooze(x, minutes, new Date()));
    else addReminder({ text: r.text, at: R.snooze(r, minutes, new Date()).at, repeat: 'none' });   // snooze one occurrence only
    return remindersView();
  });
  ipcMain.handle('reminders:testPush', async () => {
    const topic = settings().ntfyTopic;
    if (!ntfy.isValidTopic(topic)) return { ok: false, error: 'Enter a valid ntfy topic first (letters, numbers, - and _)' };
    return ntfy.send(topic, 'Lifebot test', 'Phone notifications are working.');
  });

  ipcMain.handle('settings:set', (_e, patch) => {
    const clean = {};
    if (typeof patch.ntfyTopic === 'string') clean.ntfyTopic = patch.ntfyTopic.trim();
    if (typeof patch.openAtLogin === 'boolean') clean.openAtLogin = patch.openAtLogin;
    if (typeof patch.notifications === 'boolean') clean.notifications = patch.notifications;
    for (const k of ['focusMin', 'breakMin']) {
      if (Number.isFinite(patch[k])) clean[k] = Math.min(Math.max(Math.round(patch[k]), 1), 120);
    }
    store.update((d) => { d.settings = { ...d.settings, ...clean }; });
    if ('openAtLogin' in clean) applyLoginItem(clean.openAtLogin);
    return settings();
  });

  ipcMain.handle('chat:send', async (_e, payload) => {
    const out = await chat(payload || {});
    const history = [...(store.get().chat || []),
      { role: 'user', text: String(payload.message || '').slice(0, 2000) },
      { role: 'bot', text: String(out.reply || '').slice(0, 4000) }].slice(-60);
    store.update((d) => { d.chat = history; });
    return out;
  });
  ipcMain.handle('chat:clear', () => { store.update((d) => { d.chat = []; }); return []; });

  ipcMain.handle('dashboard:open', async () => {
    if (!bridge) return { ok: false, error: 'The Python agent is not available' };
    try {
      const { path: note } = await bridge.request('refresh_dashboard', {}, 60000);
      await shell.openExternal(`obsidian://open?path=${encodeURIComponent(note)}`);
      return { ok: true, path: note };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  });
  ipcMain.handle('sync:now', async () => {
    if (!bridge) return { ok: false, error: 'The Python agent is not available' };
    try { return { ok: true, result: await bridge.request('sync', {}, 120000) }; }
    catch (err) { return { ok: false, error: err.message }; }
  });
}

// ------------------------------------------------------------------ window, tray, autostart
function createWindow() {
  win = new BrowserWindow({
    width: 1040, height: 720, minWidth: 820, minHeight: 560, show: false,
    backgroundColor: '#14131f', title: 'Lifebot', icon: ICON_PATH,
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#14131f', symbolColor: '#cfcde6', height: 40 },
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.setMenuBarVisibility(false);
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.once('ready-to-show', () => { if (!HIDDEN_START) win.show(); });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e) => e.preventDefault());
  win.on('close', (e) => {
    if (quitting || !tray) return;
    e.preventDefault();
    win.hide();
    if (!store.get().trayHintShown) {
      store.update((d) => { d.trayHintShown = true; });
      notify('Lifebot is still running', 'It lives in the system tray so your reminders keep working. Right-click the icon to quit.');
    }
  });
}

function showWindow() {
  if (!win || win.isDestroyed()) createWindow();
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function createTray() {
  const image = nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 });
  tray = new Tray(image);
  tray.setToolTip('Lifebot');
  tray.on('click', () => { if (win && win.isVisible() && win.isFocused()) win.hide(); else showWindow(); });
  const menu = () => Menu.buildFromTemplate([
    { label: 'Open Lifebot', click: () => showWindow() },
    { label: 'Chat with Lifebot', click: () => { showWindow(); send('navigate', 'chat'); } },
    { label: 'Open dashboard in Obsidian', click: () => { showWindow(); send('navigate', 'dashboard'); } },
    { type: 'separator' },
    { label: 'Start with Windows', type: 'checkbox', checked: settings().openAtLogin,
      click: (item) => { store.update((d) => { d.settings = { ...d.settings, openAtLogin: item.checked }; }); applyLoginItem(item.checked); send('settings:changed', settings()); } },
    { type: 'separator' },
    { label: 'Quit Lifebot', click: () => { quitting = true; app.quit(); } },
  ]);
  tray.on('right-click', () => tray.popUpContextMenu(menu()));
}

function applyLoginItem(enabled) {
  if (SMOKE_DIR) return;                                  // never touch real startup settings from tests
  if (process.platform !== 'win32' && process.platform !== 'darwin') return;
  app.setLoginItemSettings({
    openAtLogin: enabled, path: process.execPath,
    args: app.isPackaged ? ['--hidden'] : [app.getAppPath(), '--hidden'],
  });
}

app.whenReady().then(async () => {
  store = createStore(path.join(app.getPath('userData'), 'lifebot.json'), {
    reminders: [], settings: {}, outbox: [], chat: [], planned: {}, stats: null, firstRunDone: false,
  });
  if (!store.get().firstRunDone) {
    store.update((d) => { d.firstRunDone = true; d.settings = { ...DEFAULT_SETTINGS, ...d.settings }; });
    applyLoginItem(true);                                // start with Windows by default
  }
  registerIpc();
  createTray();
  createWindow();
  await setupBackend();
  recordPlanned();
  refreshDataInBackground();
  checkReminders();                                       // catch anything that came due while the app was closed
  setInterval(flushOutbox, 60000);
  if (SMOKE_DIR) runSmoke(SMOKE_DIR).catch((err) => { console.error('SMOKE FAILED', err); app.exit(2); });
});

/** Drive the real UI through every tab, save screenshots, and report console errors (test mode only). */
async function runSmoke(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const wc = win.webContents;
  const errors = [];
  wc.on('console-message', (_e, level, message) => { if (level >= 2) errors.push(message); });
  if (wc.isLoading()) await new Promise((r) => wc.once('did-finish-load', r));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const js = (code) => wc.executeJavaScript(code);
  const shot = async (name) => { await sleep(900); wc.invalidate(); await sleep(500); fs.writeFileSync(path.join(dir, `${name}.png`), (await wc.capturePage()).toPNG()); };
  await sleep(800);
  win.show();

  await shot('1-chat');
  await js(`(async () => {
    await window.lifebot.tasks.add('Write the project report');
    await window.lifebot.tasks.add('Email Prof. Rao about the internship');
    await window.lifebot.tasks.add('Review NLP lecture notes');
    const first = (await window.lifebot.init()).tasks[1];
    await window.lifebot.tasks.toggle({ lineIndex: first.lineIndex, checked: true });
    const d = new Date(Date.now() + 3600000); const p = (n) => String(n).padStart(2, '0');
    const at = d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes());
    await window.lifebot.reminders.add({ text: 'Stretch and drink water', at, repeat: 'daily' });
    await window.lifebot.reminders.add({ text: 'Evening check-in', at, repeat: 'weekdays' });
  })()`);
  await js(`document.querySelector('[data-tab="tasks"]').click()`); await shot('2-typewriter');
  // the Start button on a task must switch to Focus and start the timer for THAT task
  await js(`[...document.querySelectorAll('.start')][0].click()`);
  await sleep(1500);
  const afterStart = await js(`({ tabActive: document.getElementById('view-focus').classList.contains('active'),
    task: document.getElementById('focus-task').textContent, phase: document.getElementById('focus-phase').textContent,
    time: document.getElementById('focus-time').textContent })`);
  await shot('3-focus');
  await js(`document.getElementById('focus-pause').click()`); await sleep(400);
  const paused = await js(`document.getElementById('focus-phase').textContent`);
  await js(`document.getElementById('focus-resume').click()`); await sleep(300);
  await js(`document.getElementById('focus-stop').click()`); await sleep(400);
  const afterStop = await js(`document.getElementById('focus-phase').textContent`);
  await js(`document.querySelector('[data-tab="reminders"]').click()`); await shot('4-reminders');
  await js(`document.querySelector('[data-tab="chat"]').click()`);
  if (bridge) { for (let i = 0; i < 60; i++) { try { await bridge.request('ping', {}, 5000); break; } catch (_) { await sleep(1000); } } }
  const chatMsg = JSON.stringify(process.env.LIFEBOT_SMOKE_CHAT || 'hello');
  const chat = await js(`window.lifebot.chat.send({ message: ${chatMsg}, history: [] })`);
  const chatReply = chat.reply;
  await sleep(500);

  const outbox = (store.get().outbox || []).map((o) => `${o.method}:${o.params.phase || o.params.status || ''}`);
  if (bridge) { await sleep(1500); await flushOutbox(); }
  const outboxLeft = (store.get().outbox || []).length;
  const result = { errors, afterStart, paused, afterStop, chat, chatReply, outbox, outboxLeft,
    reminders: remindersView().length, tasks: currentTasks().map((t) => [t.text, t.checked]) };
  fs.writeFileSync(path.join(dir, 'smoke.json'), JSON.stringify(result, null, 2));
  quitting = true;
  app.quit();
}

app.on('before-quit', () => { quitting = true; if (bridge) bridge.stop(); });
app.on('window-all-closed', () => { /* stay alive in the tray */ });
