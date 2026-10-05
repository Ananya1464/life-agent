/**
 * Lifebot desktop app - main process.
 *
 * Owns the authoritative state (tasks file, reminders, Pomodoro clock) so everything keeps working
 * while the window is closed to the tray. The renderer is just a view; the Python agent is reached
 * through lib/pybridge.js.
 */
const { app, BrowserWindow, Tray, Menu, Notification, ipcMain, nativeImage, shell, screen } = require('electron');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const path = require('node:path');

const { PyBridge } = require('./lib/pybridge.js');
const envLib = require('./lib/env.js');
const R = require('./lib/reminders.js');
const P = require('./lib/pomodoro.js');
const T = require('./lib/tasks.js');
const Days = require('./lib/taskdays.js');
const Nudges = require('./lib/nudges.js');
const Schedule = require('./lib/schedule.js');
const ntfy = require('./lib/ntfy.js');
const widgetpos = require('./lib/widgetpos.js');
const taskedit = require('./lib/taskedit.js');
const { createStore } = require('./lib/store.js');

const APP_ID = 'com.ananya.lifebot';
const HIDDEN_START = process.argv.includes('--hidden');
const ICON_PATH = path.join(__dirname, 'assets', 'icon.png');
const DEFAULT_SETTINGS = { ntfyTopic: '', openAtLogin: true, notifications: true, sound: true, avocado: true, typewriter: true, nudges: true, briefings: true, focusMin: 25, breakMin: 5 };
const OUTBOX_MAX = 500;

let win = null;
let avocado = null;
let typewriter = null;
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
// Smoke runs must never touch real data: default the profile and tasks file into the smoke dir
if (SMOKE_DIR && !process.env.LIFEBOT_USER_DATA) process.env.LIFEBOT_USER_DATA = path.join(SMOKE_DIR, 'profile');
if (SMOKE_DIR && !process.env.LIFEBOT_TASKS_FILE) process.env.LIFEBOT_TASKS_FILE = path.join(SMOKE_DIR, 'tasks.md');
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
const tasksFile = () => process.env.LIFEBOT_TASKS_FILE || store.get().tasksFile || path.join(app.getPath('documents'), 'Typewriter', 'tasks.md');

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

/** Tasks in the file, each annotated with the day it was first seen (see lib/taskdays.js). */
function currentTasks() {
  const today = todayIso();
  const res = Days.annotate(T.listTasks(readTasksMarkdown(), today), store.get().taskFirstSeen, today);
  if (res.changed) store.update((d) => { d.taskFirstSeen = res.firstSeen; });
  // a task carried over from yesterday keeps being the current one: ids start with today's date
  const cur = store.get().currentTaskId;
  if (cur && !res.tasks.some((t) => t.id === cur)) {
    const moved = Days.idForDay(cur, today);
    if (moved !== cur && res.tasks.some((t) => t.id === moved)) store.update((d) => { d.currentTaskId = moved; });
  }
  return res.tasks;
}

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
        const result = await bridge.request(item.method, item.params, 30000);
        if (result && result.reward) announceReward(result.reward);
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

/** Latest game stats (diamonds, level, streak) for the HUD; null while the agent is unavailable. */
let gameStats = null;

function announceReward(reward) {
  gameStats = reward.stats;
  send('game', gameStats);
  if (reward.diamonds > 0 || reward.level_up) send('reward', reward);
}

async function refreshGame() {
  if (!bridge) return;
  try { gameStats = await bridge.request('game_stats', {}, 15000); send('game', gameStats); }
  catch (err) { console.log('game stats unavailable:', err.message); }
}

// ------------------------------------------------------------------ pomodoro (authoritative clock)
function pomoCfg() { const s = settings(); return { focusMin: s.focusMin, breakMin: s.breakMin }; }

function applyPomo(result) {
  pomo = result.state;
  for (const e of result.events) handlePomoEvent(e);
  broadcastPomo();
  sendTypewriter();
}

function handlePomoEvent(e) {
  const taskText = (e.task && e.task.text) || 'Free focus';
  const base = { task: taskText, task_id: (e.task && e.task.id) || 'free', run_id: e.runId };
  if (e.type === 'started') {
    enqueue('record_focus', { ...base, phase: 'started' });
  } else if (e.type === 'completed') {
    enqueue('record_focus', { ...base, phase: 'completed', duration_seconds: e.durationSec });
    bumpStats(e.durationSec);
    store.update((d) => { d.lastFocusEndedAt = Date.now(); });
    celebrateAvocado();
    notify('Focus session complete', `${taskText} - take a ${settings().breakMin}-minute break.`, 'focus');
    send('toast', { text: `Focus complete: ${taskText}` });
    pushPhone('Focus session complete', taskText);
  } else if (e.type === 'abandoned') {
    enqueue('record_focus', { ...base, phase: 'abandoned', duration_seconds: e.durationSec });
    store.update((d) => { d.lastFocusEndedAt = Date.now(); });
  } else if (e.type === 'break_done') {
    notify('Break over', 'Ready for the next focus session?', 'focus');
  }
}

// ------------------------------------------------------------------ proactive nudges (rules live in lib/nudges.js)
/** Everything the pure engine needs, read from the app's own state. */
function nudgeInput(now = Date.now()) {
  const st = store.get();
  const v = P.view(pomo, now);
  return {
    now, tzOffsetMin: new Date(now).getTimezoneOffset(),
    settings: { nudges: settings().nudges !== false && settings().notifications !== false },
    tasks: currentTasks().map((t) => ({ id: t.id, text: t.text, checked: !!t.checked, isToday: !!t.isToday, carried: !!t.carried, date: t.date })),
    currentTaskId: st.currentTaskId || null,
    pomo: { phase: v.phase, running: !!v.running },
    lastFocusEndedAt: st.lastFocusEndedAt || null,
    log: st.nudgeLog || { sent: [] },
    snoozedUntil: st.nudgeSnoozedUntil || null,
  };
}

/** What a click on a nudge does. Only ever an explicit, in-app action: nothing is sent or deleted. */
function actOnNudge(nudge) {
  const task = nudge.taskId ? currentTasks().find((t) => t.id === nudge.taskId) : null;
  if (nudge.action === 'start' && task && !task.checked && pomo.phase === 'idle') {
    startFocus({ id: task.id, text: task.text }, nudge.minutes || null);
  } else if (nudge.action === 'pick' && task) {
    store.update((d) => { d.currentTaskId = task.id; });
    broadcastTasks(tasksPayload());
    showWindow(); send('navigate', 'tasks');
  } else if (nudge.action === 'triage') {
    showWindow(); send('navigate', 'tasks');
  } else if (nudge.action === 'wrapup') {
    showWindow(); send('navigate', 'chat');
  }
}

function showNudge(nudge, now = Date.now()) {
  store.update((d) => { d.nudgeLog = Nudges.recordOutcome(d.nudgeLog || { sent: [] }, nudge, null, now); });
  const resolve = (outcome) => store.update((d) => { d.nudgeLog = Nudges.recordOutcome(d.nudgeLog || { sent: [] }, nudge, outcome, Date.now()); });
  const n = new Notification({ title: nudge.title, body: nudge.body, icon: ICON_PATH, silent: true });
  let answered = false;
  n.on('click', () => { answered = true; resolve('started'); actOnNudge(nudge); });
  n.on('close', () => { if (!answered) { answered = true; resolve('dismissed'); } });
  n.show();
}

/** One check; shows at most one gentle prompt. Never runs in test mode. */
function runNudgeCheck(now = Date.now()) {
  if (!store || SMOKE_DIR || !Notification.isSupported()) return null;
  let nudge = null;
  try { nudge = Nudges.decide(nudgeInput(now)); } catch (err) { console.error('nudge check failed:', err); }
  if (nudge) showNudge(nudge, now);
  return nudge;
}

// ------------------------------------------------------------------ scheduled briefings (Lifebot runs the agent's tasks itself)
const BRIEF_TIMEOUT_MS = 15 * 60000;
let briefRunning = null;                                      // name of the task being run, or null
const briefsDir = () => process.env.LIFE_AGENT_BRIEFS_DIR || store.get().briefsDir || path.join(path.dirname(tasksFile()), 'Briefings');

function briefNoteFor(task) {
  try {
    const names = fs.readdirSync(briefsDir()).filter((n) => n.endsWith(` ${task}.md`)).sort();
    return names.length ? names[names.length - 1] : null;
  } catch (_) { return null; }
}

function briefsPayload() {
  const runs = store.get().briefRuns || {};
  return Schedule.SCHEDULE.map((s) => {
    const r = runs[s.task] || {};
    return { task: s.task, label: s.label, time: s.time, weekly: s.day !== undefined, status: briefRunning === s.task ? 'running' : (r.status === 'running' ? 'failed' : (r.status || 'none')),
      day: r.day || null, at: r.at || null, error: r.error || '', note: briefNoteFor(s.task) };
  });
}

function broadcastBriefs() { send('briefs:changed', briefsPayload()); }

/** Run one fixed task as `python -m life_agent.agent.main <task>`; never anything the renderer typed. */
function runBrief(task) {
  if (!Schedule.TASKS.includes(task) || briefRunning || !pythonInfo || !repoRoot) return false;
  const now = Date.now();
  briefRunning = task;
  store.update((d) => { d.briefRuns = Schedule.started(d.briefRuns || {}, task, now, new Date(now).getTimezoneOffset()); });
  broadcastBriefs();
  let out = '';
  let child;
  const done = (ok, error) => {
    if (briefRunning !== task) return;
    briefRunning = null;
    store.update((d) => { d.briefRuns = Schedule.finished(d.briefRuns || {}, task, ok, Date.now(), error); });
    broadcastBriefs();
    if (ok) notify('Briefing ready', (Schedule.SCHEDULE.find((s) => s.task === task) || {}).label || task, 'briefings');
  };
  try {
    child = spawn(pythonInfo.python, ['-m', 'life_agent.agent.main', task], {
      cwd: repoRoot, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', LLM_MAX_RETRIES: '1', LIFE_AGENT_BRIEFS_DIR: briefsDir() },
    });
  } catch (err) { done(false, err.message); return false; }
  const keep = (b) => { out = (out + b.toString('utf8')).slice(-1500); };
  child.stdout.on('data', keep);
  child.stderr.on('data', keep);
  const timer = setTimeout(() => { try { child.kill(); } catch (_) { /* already gone */ } done(false, 'Timed out after 15 minutes'); }, BRIEF_TIMEOUT_MS);
  child.on('error', (err) => { clearTimeout(timer); done(false, err.message); });
  child.on('close', (code) => { clearTimeout(timer); done(code === 0, code === 0 ? '' : (out.trim().split(/\r?\n/).filter(Boolean).pop() || `Exited with code ${code}`)); });
  return true;
}

/** Called every minute: run the earliest due task if nothing else is running. Never in test mode. */
function checkBriefs() {
  if (!store || SMOKE_DIR || briefRunning || settings().briefings === false) return;
  const now = Date.now();
  const next = Schedule.due({ now, tzOffsetMin: new Date(now).getTimezoneOffset(), runs: store.get().briefRuns || {}, running: briefRunning })[0];
  if (next) runBrief(next.task);
}

function snoozeNudges(ms) {
  store.update((d) => { d.nudgeSnoozedUntil = Date.now() + ms; });
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
  sendAvocado('avocado:state', avocadoState());
  if (tray) {
    tray.setToolTip(v.phase === 'idle' ? 'Lifebot'
      : `Lifebot - ${v.phase === 'focus' ? 'Focus' : 'Break'} ${P.format(v.remainingMs)}${v.task ? ' - ' + v.task.text : ''}`);
  }
}

/** Minutes from untrusted input: a whole number 1..180, or null. */
function validMinutes(v) {
  return Number.isFinite(v) ? Math.min(Math.max(Math.round(v), 1), 180) : null;
}

/** Each task remembers the last length it was run with (keyed by its text, so it survives new days). */
const rememberedMinutes = (text) => ((store.get().taskMinutes || {})[T.slug(text || '')]) || null;
function rememberMinutes(text, minutes) {
  if (!text || !minutes) return;
  store.update((d) => { d.taskMinutes = { ...(d.taskMinutes || {}), [T.slug(text)]: minutes }; });
  broadcastTasks(tasksPayload());                               // so the next picker suggests it
}

function startFocus(task, minutes) {
  const known = task && task.id ? currentTasks().find((t) => t.id === task.id) : null;
  const text = known ? known.text : (task && task.text) || 'Free focus';
  if (known && store.get().currentTaskId !== known.id) {       // the card follows the task you are working on
    store.update((d) => { d.currentTaskId = known.id; });
    broadcastTasks(tasksPayload());
  }
  const explicit = validMinutes(minutes);
  const length = explicit || rememberedMinutes(text);          // no explicit choice: reuse what this task used last
  if (explicit) rememberMinutes(text, explicit);
  const cfg = { ...pomoCfg(), ...(length ? { focusMin: length } : {}) };
  applyPomo(P.start(pomo, known ? { id: known.id, text: known.text } : { id: 'free', text }, Date.now(), cfg));
  floatWidgets();
}

/** Like the standalone Pomodoro: when a session starts, the timer (and the task card) float over your other work. */
function floatWidgets() {
  if (settings().avocado === false) { store.update((d) => { d.settings = { ...d.settings, avocado: true }; }); send('settings:changed', settings()); }
  createAvocado();
  if (isCollapsed('avocado')) setCollapsed('avocado', false);
  if (!avocado.isVisible()) avocado.showInactive();
  if (settings().typewriter === false) { store.update((d) => { d.settings = { ...d.settings, typewriter: true }; }); send('settings:changed', settings()); }
  createTypewriter();
  if (isCollapsed('typewriter')) setCollapsed('typewriter', false);
  if (!typewriter.isVisible()) typewriter.showInactive();
}

/** +/- minutes on the running session; the new total becomes that task's remembered length. */
function adjustTimer(deltaMin) {
  if (![-5, 5].includes(deltaMin)) return;
  applyPomo(P.adjust(pomo, deltaMin * 60000, Date.now()));
  if (pomo.phase === 'focus' && pomo.task && pomo.task.id !== 'free') rememberMinutes(pomo.task.text, Math.round(pomo.durationMs / 60000));
}

// ------------------------------------------------------------------ floating avocado timer
function avocadoState() {
  const v = pomoView();
  return {
    phase: v.phase, running: v.running, task: v.task, runId: v.runId, durationMs: v.durationMs,
    remainingMs: v.remainingMs, endsAt: v.running ? Date.now() + v.remainingMs : null, collapsed: isCollapsed('avocado'),
  };
}

const sendAvocado = (channel, payload) => {
  if (avocado && !avocado.isDestroyed()) avocado.webContents.send(channel, payload);
};

let savePosTimer = null;
function saveAvocadoPosition() {
  clearTimeout(savePosTimer);
  savePosTimer = setTimeout(() => {
    if (!avocado || avocado.isDestroyed()) return;
    const { x, y } = avocado.getBounds();
    store.update((d) => { d.avocadoPos = { x, y }; });
  }, 400);
}

function createAvocado() {
  if (avocado && !avocado.isDestroyed()) return avocado;
  const displays = screen.getAllDisplays();
  const pos = widgetpos.resolvePosition(store.get().avocadoPos, displays, screen.getPrimaryDisplay(), sizeFor('avocado'));
  avocado = new BrowserWindow({
    ...sizeFor('avocado'), x: pos.x, y: pos.y, show: false, frame: false, transparent: true,
    backgroundColor: '#00000000', resizable: false, useContentSize: true, skipTaskbar: true, title: 'Avocado Timer',
    webPreferences: {
      preload: path.join(__dirname, 'avocado-preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true,
      autoplayPolicy: 'no-user-gesture-required',   // the alarm must sound without a click
      backgroundThrottling: false,                   // exact timing and audio while covered or unfocused
    },
  });
  avocado.setAlwaysOnTop(true, 'floating');          // above ordinary windows, below system UI
  avocado.loadFile(path.join(__dirname, '..', 'pomodoro', 'renderer', 'index.html'));
  avocado.once('ready-to-show', () => { if (settings().avocado !== false) avocado.showInactive(); });   // never steals focus
  avocado.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  avocado.webContents.on('will-navigate', (e) => e.preventDefault());
  avocado.on('move', saveAvocadoPosition);          // debounced; also fires for programmatic moves
  avocado.on('closed', () => { avocado = null; });
  return avocado;
}

function setAvocadoVisible(visible) {
  if (visible) { createAvocado(); if (!avocado.isVisible() && !avocado.webContents.isLoading()) avocado.showInactive(); }
  else if (avocado && !avocado.isDestroyed()) avocado.hide();
}

/** Mark a task done (file + event); used by the avocado's DONE button. */
function completeTask(id) {
  const t = currentTasks().find((x) => x.id === id && !x.checked);
  if (!t) return false;
  writeTasksMarkdown(T.toggle(readTasksMarkdown(), t.lineIndex, true, localStamp()));
  enqueue('record_task', { status: 'completed', task: t.text, task_id: t.id });
  broadcastTasks(tasksPayload());
  return true;
}

// ------------------------------------------------------------------ floating typewriter card (current task)
const TW_SIZE = { width: 290, height: 340 };
const TW_MINI_LIST = { width: 230, height: 214 };       // the minimized pill with its task list open
let twMiniList = false;
const SIZES = {
  avocado: { full: { width: 266, height: 322 }, mini: { width: 96, height: 132 } },
  typewriter: { full: TW_SIZE, mini: { width: 230, height: 50 } },
};
const isCollapsed = (name) => !!((store.get().collapsed || {})[name]);
const sizeFor = (name) => (name === 'typewriter' && twMiniList && isCollapsed(name) ? TW_MINI_LIST : SIZES[name][isCollapsed(name) ? 'mini' : 'full']);
const widgetWindow = (name) => (name === 'avocado' ? avocado : typewriter);

/** Resize a widget to its current size, keeping the bottom-right corner where it was. */
function applyWidgetSize(name) {
  const win = widgetWindow(name);
  if (!win || win.isDestroyed()) return;
  const b = win.getBounds();
  const size = sizeFor(name);
  let x = b.x + b.width - size.width;
  let y = b.y + b.height - size.height;
  if (!widgetpos.isVisible({ x, y, ...size }, screen.getAllDisplays())) {
    ({ x, y } = widgetpos.defaultPosition(screen.getPrimaryDisplay(), size));
  }
  win.setBounds({ x, y, width: size.width, height: size.height });
}

/** Minimize to / restore from a small icon, keeping the bottom-right corner where it was. */
function setCollapsed(name, collapsed) {
  store.update((d) => { d.collapsed = { ...(d.collapsed || {}), [name]: collapsed }; });
  if (name === 'typewriter') twMiniList = false;
  applyWidgetSize(name);
  const win = widgetWindow(name);
  if (win && !win.isDestroyed()) win.webContents.send('widget:mode', { collapsed, list: false });
}

/** Open or close the task list under the minimized typewriter pill. */
function setMiniList(open) {
  twMiniList = !!open && isCollapsed('typewriter');
  applyWidgetSize('typewriter');
  if (typewriter && !typewriter.isDestroyed()) typewriter.webContents.send('widget:mode', { collapsed: isCollapsed('typewriter'), list: twMiniList });
}

function setWidgetVisible(name, visible) {
  if (name === 'avocado') setAvocadoVisible(visible); else setTypewriterVisible(visible);
}

/** What the card shows: the task the user explicitly picked, or "none" (never silently another task). */
function twState() {
  const id = store.get().currentTaskId;
  const t = id ? currentTasks().find((x) => x.id === id) : null;
  const v = pomoView();
  const timer = { phase: v.phase, running: v.running, taskId: v.task ? v.task.id : null, remainingMs: v.remainingMs,
    endsAt: v.running ? Date.now() + v.remainingMs : null };
  const collapsed = isCollapsed('typewriter');
  const minutes = t ? (rememberedMinutes(t.text) || settings().focusMin) : settings().focusMin;
  const tasks = currentTasks().filter((x) => x.isToday).map((x) => ({ id: x.id, text: x.text, checked: !!x.checked }));   // the floating card shows today only
  return t ? { state: 'ok', id: t.id, text: t.text, checked: t.checked, timer, collapsed, minutes, remembered: !!(t && rememberedMinutes(t.text)), tasks }
    : { state: 'none', timer, collapsed, minutes, tasks };
}

const sendTypewriter = () => {
  if (typewriter && !typewriter.isDestroyed()) typewriter.webContents.send('tw:state', twState());
};

function broadcastTasks(payload) {
  send('tasks:changed', payload);
  sendTypewriter();
}

let twPosTimer = null;
function saveTypewriterPosition() {
  clearTimeout(twPosTimer);
  twPosTimer = setTimeout(() => {
    if (!typewriter || typewriter.isDestroyed()) return;
    const { x, y } = typewriter.getBounds();
    store.update((d) => { d.typewriterPos = { x, y }; });
  }, 400);
}

function createTypewriter() {
  if (typewriter && !typewriter.isDestroyed()) return typewriter;
  const displays = screen.getAllDisplays();
  const primary = screen.getPrimaryDisplay();
  // Default: just left of the avocado's default spot, bottom-aligned, so the two never overlap
  const av = widgetpos.defaultPosition(primary, { width: 266, height: 322 });
  const fallback = { x: av.x - TW_SIZE.width - 16, y: av.y + 322 - TW_SIZE.height };
  const saved = store.get().typewriterPos;
  const pos = saved && widgetpos.isVisible({ ...saved, ...sizeFor('typewriter') }, displays) ? { x: Math.round(saved.x), y: Math.round(saved.y) } : fallback;
  typewriter = new BrowserWindow({
    ...sizeFor('typewriter'), x: pos.x, y: pos.y, show: false, frame: false, transparent: true, backgroundColor: '#00000000',
    resizable: false, useContentSize: true, skipTaskbar: true, title: 'Typewriter',
    webPreferences: {
      preload: path.join(__dirname, 'typewriter-preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true,
      backgroundThrottling: false,
    },
  });
  typewriter.setAlwaysOnTop(true, 'floating');
  typewriter.loadFile(path.join(__dirname, 'renderer', 'typewriter.html'));
  typewriter.once('ready-to-show', () => { if (settings().typewriter !== false) typewriter.showInactive(); });   // never steals focus
  typewriter.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  typewriter.webContents.on('will-navigate', (e) => e.preventDefault());
  typewriter.on('move', saveTypewriterPosition);
  typewriter.on('closed', () => { typewriter = null; });
  return typewriter;
}

function setTypewriterVisible(visible) {
  if (visible) { createTypewriter(); if (!typewriter.isVisible() && !typewriter.webContents.isLoading()) typewriter.showInactive(); }
  else if (typewriter && !typewriter.isDestroyed()) typewriter.hide();
}

/** Pick up edits made outside the app (event-based; debounced), so the card never shows stale text. */
let tasksWatcher = null;
function watchTasksFile() {
  try {
    fs.mkdirSync(path.dirname(tasksFile()), { recursive: true });
    let timer = null;
    tasksWatcher = fs.watch(path.dirname(tasksFile()), { persistent: false }, (_event, name) => {
      if (name && name !== path.basename(tasksFile())) return;
      clearTimeout(timer);
      timer = setTimeout(() => broadcastTasks(tasksPayload()), 250);
    });
    tasksWatcher.on('error', () => { /* watching is best-effort */ });
  } catch (err) {
    console.error('tasks watcher unavailable:', err.message);
  }
}

/** Time is up: make sure the avocado is on screen, then celebrate (the timer state stays with Lifebot). */
function celebrateAvocado() {
  if (settings().avocado === false) return;
  createAvocado();
  if (isCollapsed('avocado')) setCollapsed('avocado', false);          // the buttons must be reachable
  if (!avocado.isVisible()) avocado.showInactive();
  sendAvocado('avocado:celebrate', {});
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

/** Delete a task line by id. Refuses while that task is being timed. */
function removeTaskById(id) {
  if (typeof id !== 'string') return { ok: false, error: 'Unknown task' };
  const t = currentTasks().find((x) => x.id === id);
  if (!t) return { ok: false, error: 'That task no longer exists' };
  if (pomo.phase === 'focus' && pomo.task && pomo.task.id === id) return { ok: false, error: 'Stop the timer for this task first' };
  const next = T.removeTask(readTasksMarkdown(), t.lineIndex);
  if (next === null) return { ok: false, error: 'That task line could not be removed' };
  try { writeTasksMarkdown(next); } catch (err) { return { ok: false, error: `Could not remove: ${err.message}` }; }
  store.update((d) => {
    if (d.currentTaskId === id) d.currentTaskId = null;
    if (d.taskFirstSeen) { d.taskFirstSeen = { ...d.taskFirstSeen }; delete d.taskFirstSeen[Days.keyOf(id)]; }
  });
  broadcastTasks(tasksPayload());
  return { ok: true };
}

function tasksPayload() {
  const tasks = currentTasks().map((t) => ({ ...t, lastMinutes: rememberedMinutes(t.text) }));
  return { tasks, markdown: readTasksMarkdown(), done: tasks.filter((t) => t.checked).length, currentTaskId: store.get().currentTaskId || null };
}

function addTask(text) {
  writeTasksMarkdown(T.addTask(readTasksMarkdown(), text));
  recordPlanned();
  broadcastTasks(tasksPayload());
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
  ipcMain.handle('game:stats', async () => { await refreshGame(); return gameStats; });

  ipcMain.handle('app:init', () => ({
    game: gameStats,
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
  ipcMain.handle('tasks:remove', (_e, id) => removeTaskById(id));
  ipcMain.handle('tw:remove', (_e, id) => removeTaskById(id));
  ipcMain.handle('tasks:toggle', (_e, { lineIndex, checked }) => {
    const before = currentTasks().find((t) => t.lineIndex === lineIndex);
    writeTasksMarkdown(T.toggle(readTasksMarkdown(), lineIndex, !!checked, localStamp()));
    if (before && checked) enqueue('record_task', { status: 'completed', task: before.text, task_id: before.id });
    const payload = tasksPayload();
    broadcastTasks(payload);
    return payload;
  });
  ipcMain.handle('tasks:saveMarkdown', (_e, markdown) => {
    writeTasksMarkdown(String(markdown));
    recordPlanned();
    const payload = tasksPayload();
    broadcastTasks(payload);
    return payload;
  });

  ipcMain.handle('pomodoro:start', (_e, task) => {
    startFocus(task, validMinutes(task && task.minutes));
    if (win && !win.isDestroyed() && win.isVisible()) win.minimize();      // get out of the way: keep working, the avocado floats on top
    return pomoView();
  });
  ipcMain.handle('pomodoro:adjust', (_e, deltaMin) => { adjustTimer(deltaMin); return pomoView(); });

  // --- typewriter card: narrow, validated operations only
  ipcMain.handle('tw:get', () => twState());
  ipcMain.handle('tw:update', (_e, input) => {
    const currentId = store.get().currentTaskId;
    if (!input || typeof input.id !== 'string' || input.id !== currentId) {
      return { ok: false, code: 'invalid', error: 'That is no longer the current task' };
    }
    const result = taskedit.applyEdit({ markdown: readTasksMarkdown(), dateIso: todayIso(), id: input.id, oldText: input.oldText, newText: input.newText });
    if (!result.ok) return result;
    if (result.markdown !== readTasksMarkdown()) {
      try { writeTasksMarkdown(result.markdown); }
      catch (err) { return { ok: false, code: 'write_failed', error: `Could not save: ${err.message}` }; }
    }
    store.update((d) => {
      d.currentTaskId = result.id;
      const o = Days.keyOf(input.id), n = Days.keyOf(result.id);       // an edited task keeps its day
      if (o !== n && d.taskFirstSeen && d.taskFirstSeen[o]) { d.taskFirstSeen = { ...d.taskFirstSeen, [n]: d.taskFirstSeen[o] }; delete d.taskFirstSeen[o]; }
    });
    recordPlanned();
    broadcastTasks(tasksPayload());
    return { ok: true, id: result.id, text: result.text };
  });
  ipcMain.handle('tasks:setCurrent', (_e, id) => {
    if (id !== null && typeof id !== 'string') return tasksPayload();
    if (id !== null && !currentTasks().some((t) => t.id === id)) return tasksPayload();
    store.update((d) => { d.currentTaskId = id; });
    broadcastTasks(tasksPayload());
    return tasksPayload();
  });

  // --- floating avocado timer: narrow, validated operations only
  ipcMain.handle('avocado:getState', () => avocadoState());

  // --- shared widget controls (strictly validated)
  const WIDGETS = ['avocado', 'typewriter'];
  ipcMain.handle('widget:collapse', (_e, input) => {
    if (!input || !WIDGETS.includes(input.widget) || typeof input.collapsed !== 'boolean') return false;
    setCollapsed(input.widget, input.collapsed);
    return true;
  });
  ipcMain.handle('widget:hide', (_e, input) => {
    if (!input || !WIDGETS.includes(input.widget)) return false;
    store.update((d) => { d.settings = { ...d.settings, [input.widget]: false }; });
    setWidgetVisible(input.widget, false);
    send('settings:changed', settings());
    return true;
  });
  ipcMain.handle('widget:openApp', (_e, input) => {
    showWindow();
    const tab = input && ['tasks', 'focus'].includes(input.tab) ? input.tab : null;
    if (tab) send('navigate', tab);
    return true;
  });

  // --- typewriter card: start / stop the timer for the current task
  ipcMain.handle('tw:start', (_e, input) => {
    // a specific task (from the card's list) becomes the current one first; ids are checked against the real file
    if (input && input.id !== undefined) {
      if (typeof input.id !== 'string' || !currentTasks().some((x) => x.id === input.id)) return { ok: false, error: 'Unknown task' };
      if (pomo.phase === 'focus') return { ok: false, error: 'A timer is already running' };
      store.update((d) => { d.currentTaskId = input.id; });
    }
    const id = store.get().currentTaskId;
    const t = id ? currentTasks().find((x) => x.id === id) : null;
    if (!t) return { ok: false, error: 'No current task' };
    if (t.checked) return { ok: false, error: 'That task is already done' };
    if (pomo.phase === 'focus') return { ok: false, error: 'A timer is already running' };
    startFocus({ id: t.id, text: t.text }, validMinutes(input && input.minutes));
    if (twMiniList) setMiniList(false);
    if (settings().avocado === false) {                   // started from the card: show the timer
      store.update((d) => { d.settings = { ...d.settings, avocado: true }; });
      setAvocadoVisible(true);
      send('settings:changed', settings());
    }
    return { ok: true };
  });
  ipcMain.handle('tw:miniList', (_e, open) => { if (typeof open === 'boolean') setMiniList(open); return true; });
  ipcMain.handle('tw:select', (_e, id) => {              // make a task the current one without starting it
    if (typeof id !== 'string' || !currentTasks().some((x) => x.id === id)) return { ok: false };
    store.update((d) => { d.currentTaskId = id; });
    broadcastTasks(tasksPayload());
    return { ok: true };
  });
  ipcMain.handle('tw:stop', () => {
    if (pomo.phase === 'focus' && pomo.task && pomo.task.id === store.get().currentTaskId) applyPomo(P.stop(pomo, Date.now()));
    return { ok: true };
  });
  ipcMain.handle('avocado:start', (_e, input) => {
    const minutes = input && Number.isFinite(input.minutes) ? Math.min(Math.max(Math.round(input.minutes), 1), 180) : null;
    const text = input && typeof input.task === 'string' ? input.task.trim().slice(0, 24) : '';
    const known = text ? currentTasks().find((t) => !t.checked && t.text.toLowerCase() === text.toLowerCase()) : null;
    startFocus(known ? { id: known.id, text: known.text } : { text: text || 'Free focus' }, minutes);
    return avocadoState();
  });
  ipcMain.handle('avocado:adjust', (_e, deltaMin) => { adjustTimer(deltaMin); return avocadoState(); });
  ipcMain.handle('avocado:abandon', () => { if (pomo.phase === 'focus') applyPomo(P.stop(pomo, Date.now())); return avocadoState(); });
  // After the celebration: just stop, mark the finished task done, or move on to the next open task
  ipcMain.handle('avocado:ack', (_e, action) => {
    const act = ['stop', 'done', 'next'].includes(action) ? action : 'stop';
    const finished = pomo.phase === 'break' ? pomo.task : null;
    if (pomo.phase === 'break') applyPomo(P.stop(pomo, Date.now()));
    const realTask = finished && finished.id && finished.id !== 'free' ? finished.id : null;
    if (act === 'done' && realTask) completeTask(realTask);
    if (act === 'next') {
      const next = T.nextOpen(currentTasks(), realTask);
      if (next) {
        store.update((d) => { d.currentTaskId = next.id; });
        broadcastTasks(tasksPayload());
        startFocus({ id: next.id, text: next.text });
      } else {
        send('toast', { text: 'No more open tasks' });
      }
    }
    return avocadoState();
  });
  ipcMain.handle('avocado:attention', (_e, on) => {
    if (typeof on === 'boolean' && avocado && !avocado.isDestroyed()) avocado.flashFrame(on);
    return true;
  });
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
    if (typeof patch.sound === 'boolean') clean.sound = patch.sound;
    if (typeof patch.avocado === 'boolean') clean.avocado = patch.avocado;
    if (typeof patch.typewriter === 'boolean') clean.typewriter = patch.typewriter;
    if (typeof patch.nudges === 'boolean') clean.nudges = patch.nudges;
    if (typeof patch.briefings === 'boolean') clean.briefings = patch.briefings;
    for (const k of ['focusMin', 'breakMin']) {
      if (Number.isFinite(patch[k])) clean[k] = Math.min(Math.max(Math.round(patch[k]), 1), 120);
    }
    store.update((d) => { d.settings = { ...d.settings, ...clean }; });
    if ('openAtLogin' in clean) applyLoginItem(clean.openAtLogin);
    if ('avocado' in clean) setAvocadoVisible(clean.avocado);
    if ('typewriter' in clean) setTypewriterVisible(clean.typewriter);
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

  ipcMain.handle('briefs:list', () => briefsPayload());
  ipcMain.handle('briefs:run', (_e, task) => {
    if (typeof task !== 'string' || !Schedule.TASKS.includes(task)) return { ok: false, error: 'Unknown briefing' };
    if (briefRunning) return { ok: false, error: `Already running: ${briefRunning}` };
    if (!pythonInfo) return { ok: false, error: 'The agent (Python) is not available' };
    return { ok: runBrief(task) };
  });
  ipcMain.handle('briefs:read', (_e, task) => {
    if (typeof task !== 'string' || !Schedule.TASKS.includes(task)) return { ok: false, error: 'Unknown briefing' };
    const name = briefNoteFor(task);
    if (!name) return { ok: false, error: 'No note yet. Run it first.' };
    try { return { ok: true, name, text: fs.readFileSync(path.join(briefsDir(), name), 'utf8').slice(0, 60000) }; }
    catch (err) { return { ok: false, error: err.message }; }
  });
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
  win.webContents.once('did-finish-load', () => { if (!HIDDEN_START && !win.isDestroyed() && !win.isVisible()) win.show(); });   // fallback if ready-to-show never fires
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
    { label: 'Show avocado timer', type: 'checkbox', checked: settings().avocado !== false,
      click: (item) => { store.update((d) => { d.settings = { ...d.settings, avocado: item.checked }; }); setAvocadoVisible(item.checked); send('settings:changed', settings()); } },
    { label: 'Show typewriter card', type: 'checkbox', checked: settings().typewriter !== false,
      click: (item) => { store.update((d) => { d.settings = { ...d.settings, typewriter: item.checked }; }); setTypewriterVisible(item.checked); send('settings:changed', settings()); } },
    { label: 'Snooze prompts for 2 hours', click: () => snoozeNudges(2 * 3600000) },
    { label: 'Snooze prompts until tomorrow', click: () => { const d = new Date(); d.setHours(24, 0, 0, 0); snoozeNudges(d.getTime() - Date.now()); } },
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
  if (settings().avocado !== false) createAvocado();
  if (settings().typewriter !== false) createTypewriter();
  watchTasksFile();
  await setupBackend();
  recordPlanned();
  refreshDataInBackground();
  refreshGame();
  checkReminders();                                       // catch anything that came due while the app was closed
  setInterval(flushOutbox, 60000);
  setInterval(runNudgeCheck, 60000);
  setTimeout(checkBriefs, 45000);                      // catch up on briefings missed while the PC was off
  setInterval(checkBriefs, 60000);                   // gentle, rate-limited prompts (lib/nudges.js)
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
  await sleep(300);
  await js(`document.getElementById('picker-go').click()`);   // Start now opens the length picker first
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

  // ---- avocado integration (floating timer driven by Lifebot's clock)
  const av = { exists: !!(avocado && !avocado.isDestroyed()) };
  if (av.exists) {
    const ajs = (code) => avocado.webContents.executeJavaScript(code);
    const ashot = async (name) => { await sleep(700); avocado.webContents.invalidate(); await sleep(400); fs.writeFileSync(path.join(dir, name + '.png'), (await avocado.webContents.capturePage()).toPNG()); };
    av.alwaysOnTop = avocado.isAlwaysOnTop();
    av.visible = avocado.isVisible();
    av.preloadApi = await ajs("Object.keys(window.pomodoroAPI).sort().join(',')");
    av.nodeLeak = await ajs("typeof require + ',' + typeof process");
    const firstOpen = currentTasks().find((t) => !t.checked);
    startFocus({ id: firstOpen.id }, 25);                         // exactly what the Typewriter Start button does
    await sleep(1500);
    av.afterStart = await ajs('window.__pomo.debug().state');
    av.taskShown = await ajs("document.getElementById('timer-task-display').textContent");
    av.timeShown = await ajs("document.getElementById('timer-countdown').textContent");
    av.dupStartIgnored = await ajs("document.getElementById('btn-start').click(); window.__pomo.debug().state");
    await ashot('6-avocado-running');
    pomo = { ...pomo, durationMs: Math.round(pomo.elapsedMs + (Date.now() - pomo.runningSince)) + 800 };   // end in ~0.8s
    await sleep(3200);
    av.celebrating = await ajs('window.__pomo.debug()');
    av.lifebotPhaseAtCompletion = pomo.phase;
    await ashot('7-avocado-celebrating');
    await ajs("document.getElementById('btn-stop-alarm').click()");
    await sleep(700);
    av.afterStopWidget = await ajs('window.__pomo.debug().state');
    av.afterStopLifebot = pomo.phase;
    startFocus({ text: 'Abandon me' }, 25);
    await sleep(1200);
    await ajs("document.getElementById('btn-abandon').click()");
    await sleep(700);
    av.afterAbandonLifebot = pomo.phase;
    av.afterAbandonWidget = await ajs('window.__pomo.debug().state');
    av.initialBounds = avocado.getBounds();
    avocado.setPosition(321, 187);
    await sleep(1000);
    av.savedPosition = store.get().avocadoPos;
    setAvocadoVisible(false);
    av.hidden = !avocado.isVisible();
    setAvocadoVisible(true);
    await sleep(300);
    av.shownAgain = avocado.isVisible();
    av.eventsQueued = (store.get().outbox || []).filter((o) => o.method === 'record_focus').map((o) => o.params.phase);
  }

  // ---- typewriter card integration
  const tw = { exists: !!(typewriter && !typewriter.isDestroyed()) };
  if (tw.exists) {
    const tjs = (code) => typewriter.webContents.executeJavaScript(code);
    const tshot = async (name) => { await sleep(700); typewriter.webContents.invalidate(); await sleep(400); fs.writeFileSync(path.join(dir, name + '.png'), (await typewriter.webContents.capturePage()).toPNG()); };
    const dbg = () => tjs('window.__tw.debug()');
    const readFile = () => fs.readFileSync(tasksFile(), 'utf8');
    tw.alwaysOnTop = typewriter.isAlwaysOnTop();
    tw.visible = typewriter.isVisible();
    tw.api = await tjs("Object.keys(window.typewriterAPI).sort().join(',')");
    tw.nodeLeak = await tjs("typeof require + ',' + typeof process");
    const b1 = typewriter.getBounds();
    tw.initialBounds = { x: b1.x, y: b1.y };
    const b2 = av.initialBounds || { x: 0, y: 0, width: 0, height: 0 };
    tw.overlapsAvocadoAtStart = !(b1.x + b1.width <= b2.x || b2.x + b2.width <= b1.x || b1.y + b1.height <= b2.y || b2.y + b2.height <= b1.y);
    tw.initial = (await dbg()).task;                                   // run 2 should restore the earlier choice
    if (tw.initial.state === 'none') {
      await tshot('8-typewriter-none');
      await js("[...document.querySelectorAll('.pick')][0].click()");   // the real button in Lifebot's Typewriter tab
      await sleep(600);
    }
    tw.afterPick = (await dbg()).task;
    await tshot('9-typewriter-current');

    const edit = async (text) => {
      await tjs("document.getElementById('view').click()");
      await tjs('(() => { const e = document.getElementById("editor"); e.value = ' + JSON.stringify(text) + '; e.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); })()');
      await sleep(700);
      return dbg();
    };
    const esc = () => tjs('document.getElementById("editor").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))');

    tw.emptyEdit = await edit('');
    await esc(); await sleep(200);
    tw.tooLongEdit = await edit('x'.repeat(201));
    await esc(); await sleep(200);
    tw.multilineEdit = await edit('line one\nline two');
    await esc(); await sleep(200);
    tw.fileUnchangedAfterRejects = readFile().includes(tw.afterPick.text);

    const newText = tw.afterPick.text.endsWith(' (edited)') ? tw.afterPick.text.replace(' (edited)', '') : tw.afterPick.text + ' (edited)';
    tw.goodEdit = await edit(newText);
    tw.fileHasEdit = readFile().includes(newText);
    tw.storedCurrentId = store.get().currentTaskId;
    tw.lifebotSeesEdit = (await js("[...document.querySelectorAll('.task-text')].map((e) => e.textContent)")).includes(newText);
    await tshot('10-typewriter-saved');

    // an edit made outside the app while the card is open must never be overwritten
    await tjs("document.getElementById('view').click()");
    writeTasksMarkdown(readFile().replace(newText, 'Changed behind its back'));
    await sleep(900);
    await tjs('(() => { const e = document.getElementById("editor"); e.value = "My stale edit"; e.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); })()');
    await sleep(700);
    tw.staleEdit = await dbg();
    tw.outsideEditSurvived = readFile().includes('Changed behind its back') && !readFile().includes('My stale edit');
    await esc();
    writeTasksMarkdown(readFile().replace('Changed behind its back', newText));   // restore for the next run
    await sleep(600);
    tw.afterRestore = (await dbg()).task;

    typewriter.setPosition(40, 60);
    await sleep(1000);
    tw.savedPosition = store.get().typewriterPos;
    setTypewriterVisible(false);
    tw.hidden = !typewriter.isVisible();
    setTypewriterVisible(true);
    await sleep(300);
    tw.shownAgain = typewriter.isVisible();
  }

  // ---- continuity: minimize/restore, card -> timer -> done/next, hide, open app
  const fl = {};
  if (avocado && typewriter && !avocado.isDestroyed() && !typewriter.isDestroyed()) {
    const aj = (code) => avocado.webContents.executeJavaScript(code);
    const tj = (code) => typewriter.webContents.executeJavaScript(code);
    const ashot = async (name) => { await sleep(600); avocado.webContents.invalidate(); await sleep(300); fs.writeFileSync(path.join(dir, name + '.png'), (await avocado.webContents.capturePage()).toPNG()); };
    const tshot = async (name) => { await sleep(600); typewriter.webContents.invalidate(); await sleep(300); fs.writeFileSync(path.join(dir, name + '.png'), (await typewriter.webContents.capturePage()).toPNG()); };
    const corner = (b) => [b.x + b.width, b.y + b.height];
    addTask('Second open task'); addTask('Third open task');
    setAvocadoVisible(true); setTypewriterVisible(true);
    avocado.setPosition(500, 300); typewriter.setPosition(150, 300); await sleep(500);

    // minimize both with their own buttons; the bottom-right corner stays put
    const a0 = avocado.getBounds(); const t0 = typewriter.getBounds();
    await aj("document.getElementById('wc-min').click()");
    await tj("document.getElementById('wc-min').click()");
    await sleep(700);
    const a1 = avocado.getBounds(); const t1 = typewriter.getBounds();
    fl.mini = {
      avocadoSize: [a1.width, a1.height], typewriterSize: [t1.width, t1.height],
      avocadoCornerKept: JSON.stringify(corner(a0)) === JSON.stringify(corner(a1)),
      typewriterCornerKept: JSON.stringify(corner(t0)) === JSON.stringify(corner(t1)),
      avocadoClass: await aj("document.body.classList.contains('mini')"), typewriterClass: (await tj('window.__tw.debug()')).mini,
      avocadoMiniText: await aj("document.getElementById('mini-time').textContent"),
      stillOnTop: avocado.isAlwaysOnTop() && typewriter.isAlwaysOnTop(), stillVisible: avocado.isVisible() && typewriter.isVisible(),
      stored: store.get().collapsed,
    };
    await ashot('11-avocado-mini'); await tshot('12-typewriter-mini');
    // the minimized pill's drop-down: lists open tasks, can start a particular one
    await tj("document.getElementById('mini-list-btn').click()");
    await sleep(700);
    fl.miniList = { size: [typewriter.getBounds().width, typewriter.getBounds().height], dbg: await tj('(({ miniOpen, miniRows }) => ({ miniOpen, miniRows }))(window.__tw.debug())') };
    await tshot('12b-typewriter-mini-list');
    await tj("document.getElementById('mini-list-btn').click()");
    await sleep(600);
    fl.miniListClosedSize = [typewriter.getBounds().width, typewriter.getBounds().height];
    await aj("document.getElementById('wc-expand').click()");
    await tj("document.getElementById('wc-expand').click()");
    await sleep(700);
    const a2 = avocado.getBounds(); const t2 = typewriter.getBounds();
    fl.expanded = { avocadoSize: [a2.width, a2.height], typewriterSize: [t2.width, t2.height], stored: store.get().collapsed };
    // expanded card lists ALL tasks; a row's play button starts that particular task
    await tshot('12c-typewriter-all-tasks');
    fl.allTasks = (await tj('window.__tw.debug()')).rows;
    const fileTasks = currentTasks();
    const pickRow = fileTasks.find((t) => !t.checked && t.isToday && t.id !== store.get().currentTaskId);
    if (pickRow) {
      await tj(`(() => { const r = [...document.querySelectorAll('#tasklist .task-row')].find((x) => x.querySelector('.row-text').title === ${JSON.stringify(pickRow.text)}); r.querySelector('.row-go').click(); })()`);
      await sleep(1200);
      fl.startedFromList = { expected: pickRow.text, running: pomo.task && pomo.task.text, phase: pomo.phase, currentIsIt: store.get().currentTaskId === pickRow.id };
      await tshot('12d-typewriter-running-from-list');
      applyPomo(P.stop(pomo, Date.now()));
      await sleep(500);
    }

    // day handling: an open task from an earlier day hangs in Lifebot but not on the floating card; tasks can be removed
    const readFile = () => fs.readFileSync(tasksFile(), 'utf8');
    addTask('Remove me');
    store.update((d) => { d.taskFirstSeen = { ...d.taskFirstSeen, 'review-nlp-lecture-notes': '2000-01-01' }; });
    broadcastTasks(tasksPayload());
    await sleep(800);
    const cardRows = () => tj("[...document.querySelectorAll('#tasklist .row-text')].map((e) => e.title)");
    fl.days = {
      cardRows: await cardRows(),
      lifebotCarried: await js(`[...document.querySelectorAll('#task-list .task')].map((e) => e.querySelector('.task-text').textContent + (e.querySelector('.task-ts') && /from/.test(e.querySelector('.task-ts').textContent) ? ' [carried]' : ''))`),
      lifebotHeading: await js(`!!document.querySelector('#task-list .phase.carried')`),
    };
    await tshot('12e-typewriter-today-only');
    await tj(`(() => { const r = [...document.querySelectorAll('#tasklist .task-row')].find((x) => x.querySelector('.row-text').title === 'Remove me'); r.querySelector('.row-del').click(); })()`);
    await sleep(300);
    fl.days.afterFirstClick = readFile().includes('Remove me');                       // armed only: still there
    await tj(`(() => { const r = [...document.querySelectorAll('#tasklist .task-row')].find((x) => x.querySelector('.row-text').title === 'Remove me'); r.querySelector('.row-del').click(); })()`);
    await sleep(800);
    fl.days.afterSecondClick = readFile().includes('Remove me');
    fl.days.cardRowsAfter = await cardRows();

    // proactive nudges: the pure engine fed with this app's real state at 11:00 local (nothing is shown in test mode)
    store.update((d) => { d.nudgeLog = { sent: [] }; d.nudgeSnoozedUntil = null; });
    const eleven = new Date(); eleven.setHours(11, 0, 0, 0);
    const nIn = nudgeInput(eleven.getTime());
    const decided = Nudges.decide({ ...nIn, pomo: { phase: 'idle', running: false }, lastFocusEndedAt: null });
    fl.nudge = {
      openTasks: nIn.tasks.filter((t) => !t.checked).length, carriedSeen: nIn.tasks.filter((t) => t.carried).length,
      decided, showsNothingInTestMode: runNudgeCheck() === null,
      silentWhileTimerRuns: Nudges.decide({ ...nIn, pomo: { phase: 'focus', running: true } }) === null,
      silentWhenOff: Nudges.decide({ ...nIn, settings: { nudges: false } }) === null,
    };
    // briefings tab: lists every scheduled task, shows a saved note, refuses anything not on the fixed schedule
    fs.mkdirSync(briefsDir(), { recursive: true });
    fs.writeFileSync(path.join(briefsDir(), '2026-10-05 ai_edge.md'), '# AI Edge\n\n1. Test opportunity https://example.org\n');
    broadcastBriefs();
    await js(`document.querySelector('[data-tab="briefings"]').click()`);
    await sleep(600);
    fl.briefings = {
      cards: await js(`document.querySelectorAll('#brief-list .brief').length`),
      scheduleSize: Schedule.SCHEDULE.length,
      evilRefused: await js(`window.lifebot.briefs.run('meal_plan; calc.exe')`),
      unknownRead: await js(`window.lifebot.briefs.read('../../secrets')`),
      noteRead: (await js(`window.lifebot.briefs.read('ai_edge')`)).text,
      viewEnabledOnlyWithNote: await js(`[...document.querySelectorAll('#brief-list .brief')].map((c) => [c.querySelector('strong').textContent, !c.querySelectorAll('button')[1].disabled])`),
      autoRunBlockedInTestMode: (checkBriefs(), briefRunning === null),
    };
    await js(`[...document.querySelectorAll('#brief-list .brief')].find((c) => /opportunities/i.test(c.querySelector('strong').textContent)).querySelectorAll('button')[1].click()`);
    await sleep(500);
    fl.briefings.noteShown = await js(`[...document.querySelectorAll('.brief-note')].some((n) => !n.hidden && /Test opportunity/.test(n.textContent))`);
    await shot('13-briefings');
    if (decided && decided.action === 'pick') {
      actOnNudge(decided);
      fl.nudge.pickMadeCurrent = store.get().currentTaskId === decided.taskId;
    }

    // card -> timer in one step (the current task was picked earlier; make sure it is open)
    const cur = currentTasks().find((t) => t.id === store.get().currentTaskId);
    fl.currentBefore = cur ? { text: cur.text, checked: cur.checked } : null;
    await tj("document.getElementById('start').click()");                 // opens the length picker
    await sleep(300);
    await tj("document.getElementById('picker-go').click()");              // confirm the suggested length
    await sleep(1500);
    fl.cardStart = { phase: pomo.phase, task: pomo.task && pomo.task.text, avocado: await aj('window.__pomo.debug().state'),
      avocadoTask: await aj("document.getElementById('timer-task-display').textContent"), cardButton: (await tj('window.__tw.debug()')).startLabel };
    // minimized while running: the mini avocado counts down
    await aj("document.getElementById('wc-min').click()"); await sleep(700);
    fl.miniWhileRunning = await aj("document.getElementById('mini-time').textContent");
    await ashot('13-avocado-mini-running');

    // finish: the avocado must auto-expand, then DONE marks the task done
    pomo = { ...pomo, durationMs: Math.round(pomo.elapsedMs + (Date.now() - pomo.runningSince)) + 800 };
    await sleep(3400);
    fl.autoExpanded = !isCollapsed('avocado') && avocado.getBounds().width === 266;
    fl.celebrating = (await aj('window.__pomo.debug()')).celebrating;
    await ashot('14-avocado-actions');
    const doneId = store.get().currentTaskId;
    await aj("document.getElementById('btn-done').click()");
    await sleep(900);
    const doneTask = currentTasks().find((t) => t.id === doneId);
    fl.done = { checkedInFile: !!(doneTask && doneTask.checked), lifebotPhase: pomo.phase, cardLabel: (await tj('window.__tw.debug()')).startLabel,
      completedEventQueued: (store.get().outbox || []).some((o) => o.method === 'record_task' && o.params.status === 'completed' && o.params.task_id === doneId) };

    // NEXT: run a different open task to completion, press NEXT, expect the following open task to start
    const open = currentTasks().filter((t) => !t.checked);
    fl.openLeft = open.length;
    if (open.length >= 2) {
      startFocus({ id: open[0].id }, 25);
      await sleep(800);
      pomo = { ...pomo, durationMs: Math.round(pomo.elapsedMs + (Date.now() - pomo.runningSince)) + 800 };
      await sleep(3400);
      await aj("document.getElementById('btn-next').click()");
      await sleep(1200);
      fl.next = { expectedTask: open[1].text, runningTask: pomo.task && pomo.task.text, phase: pomo.phase, currentNow: store.get().currentTaskId === open[1].id,
        avocadoTask: await aj("document.getElementById('timer-task-display').textContent") };
      await aj("document.getElementById('btn-abandon').click()"); await sleep(600);
    }

    // hide with the x button, open Lifebot with the house button, then bring the widget back
    await tj("document.getElementById('wc-hide').click()");
    await sleep(500);
    fl.hide = { typewriterHidden: !typewriter.isVisible(), settingStored: settings().typewriter === false };
    win.hide();
    await aj("document.getElementById('wc-home').click()");
    await sleep(700);
    fl.home = { lifebotVisible: win.isVisible() };
    store.update((d) => { d.settings = { ...d.settings, typewriter: true }; });
    setTypewriterVisible(true);
    await sleep(400);
    fl.restored = { typewriterVisible: typewriter.isVisible() };
  }

  // ---- choosing and adjusting the timer length
  const ln = {};
  if (avocado && typewriter && !avocado.isDestroyed() && !typewriter.isDestroyed()) {
    const aj = (code) => avocado.webContents.executeJavaScript(code);
    const tj = (code) => typewriter.webContents.executeJavaScript(code);
    const mins = () => Math.round(pomo.durationMs / 60000);
    const guard = (run) => async (code) => { try { return await run(code); } catch (e) { (ln.failedSteps = ln.failedSteps || []).push(String(code).slice(0, 110)); return null; } };
    const jsq = guard(js), ajq = guard(aj), tjq = guard(tj);
    if (pomo.phase !== 'idle') applyPomo(P.stop(pomo, Date.now()));
    await jsq("document.querySelector('[data-tab=tasks]').click()");
    await sleep(500);

    // Start on a task in Lifebot now asks for the length first
    await jsq("document.querySelector('.start').click()");
    await sleep(400);
    ln.pickerOpened = await jsq("!document.getElementById('picker').hidden");
    ln.pickerTask = await jsq("document.getElementById('picker-task').textContent");
    ln.pickerStartValue = await jsq("document.getElementById('picker-minutes').value");
    ln.timerNotStartedYet = pomo.phase === 'idle';
    await jsq("document.getElementById('picker-minutes').value = '0'; document.getElementById('picker-go').click()");
    await sleep(300);
    ln.invalidRejected = { error: await jsq("document.getElementById('picker-error').textContent"), stillOpen: await jsq("!document.getElementById('picker').hidden"), idle: pomo.phase === 'idle' };
    await jsq("document.querySelectorAll('#picker-presets .chip')[2].click()");
    ln.presetHighlighted = await jsq("document.querySelector('#picker-presets .chip.on').dataset.m");
    await jsq("document.getElementById('picker-go').click()");
    await sleep(1300);
    const pickedTask = pomo.task && pomo.task.text;
    ln.started = { phase: pomo.phase, minutes: mins(), task: pickedTask, focusTabShown: await jsq("document.getElementById('view-focus').classList.contains('active')") };

    ln.mainMinimizedAfterStart = win.isMinimized();
    ln.floating = { avocadoVisible: avocado.isVisible(), typewriterVisible: typewriter.isVisible(), avocadoOnTop: avocado.isAlwaysOnTop(), typewriterOnTop: typewriter.isAlwaysOnTop() };
    ln.cardFollowsStartedTask = ((await tjq('window.__tw.debug()')).task || {}).text === pickedTask;
    // adjust while running: from the avocado, then from the Focus tab
    await ajq("document.getElementById('btn-plus').click()"); await sleep(500);
    ln.afterAvocadoPlus = mins();
    await jsq("document.getElementById('focus-plus').click()"); await sleep(500);
    ln.afterFocusPlus = mins();
    await ajq("document.getElementById('btn-minus').click()"); await sleep(500);
    ln.afterAvocadoMinus = mins();
    ln.avocadoShowsNewTime = await ajq("document.getElementById('timer-countdown').textContent");
    await jsq("for (let i = 0; i < 40; i++) document.getElementById('focus-plus').click()"); await sleep(900);
    ln.cappedAt = mins();
    await jsq("for (let i = 0; i < 60; i++) document.getElementById('focus-minus').click()"); await sleep(900);
    ln.floorMinutes = Math.round(pomo.durationMs / 60000);           // at least one minute remains
    await jsq("document.getElementById('focus-plus').click()"); await sleep(300);
    applyPomo(P.stop(pomo, Date.now()));
    ln.remembered = (store.get().taskMinutes || {})[T.slug(pickedTask || '')];

    // the next time, the picker suggests the remembered length
    await jsq("document.querySelector('[data-tab=tasks]').click()"); await sleep(400);
    await jsq("[...document.querySelectorAll('.task')].find((r) => r.querySelector('.task-text').textContent === " + JSON.stringify(pickedTask) + ").querySelector('.start').click()");
    await sleep(400);
    ln.nextPicker = { value: await jsq("document.getElementById('picker-minutes').value"), hint: await jsq("document.getElementById('picker-hint').textContent") };
    await jsq("document.getElementById('picker').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))");
    await sleep(300);
    ln.escapeClosedWithoutStarting = { closed: await jsq("document.getElementById('picker').hidden"), idle: pomo.phase === 'idle' };

    // the typewriter card has its own picker
    store.update((d) => { d.currentTaskId = (currentTasks().find((t) => !t.checked) || {}).id || null; });
    broadcastTasks(tasksPayload()); await sleep(500);
    await tjq("(() => { const p = document.getElementById('picker'); if (!p.hidden) p.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); })()");
    await tjq("document.getElementById('start').click()"); await sleep(400);
    const cardPicker = await tjq('window.__tw.debug()');
    typewriter.webContents.invalidate(); await sleep(500); fs.writeFileSync(path.join(dir, '15-card-picker.png'), (await typewriter.webContents.capturePage()).toPNG());
    ln.cardPicker = { open: cardPicker.pickerOpen, value: cardPicker.pickerValue, note: cardPicker.pickerNote, timerNotStarted: pomo.phase === 'idle' };
    await tjq("document.querySelectorAll('#picker .chip')[0].click(); document.getElementById('picker-go').click()");
    await sleep(1300);
    ln.cardStarted = { phase: pomo.phase, minutes: mins() };
    applyPomo(P.stop(pomo, Date.now()));
  }

  const outbox = (store.get().outbox || []).map((o) => `${o.method}:${o.params.phase || o.params.status || ''}`);
  if (bridge) { await sleep(1500); await flushOutbox(); }
  const outboxLeft = (store.get().outbox || []).length;
  const result = { errors, afterStart, paused, afterStop, chat, chatReply, outbox, outboxLeft, avocado: av, typewriter: tw, flow: fl, length: ln,
    reminders: remindersView().length, tasks: currentTasks().map((t) => [t.text, t.checked]) };
  fs.writeFileSync(path.join(dir, 'smoke.json'), JSON.stringify(result, null, 2));
  quitting = true;
  app.quit();
}

app.on('before-quit', () => { quitting = true; if (bridge) bridge.stop(); if (avocado && !avocado.isDestroyed()) avocado.destroy(); if (typewriter && !typewriter.isDestroyed()) typewriter.destroy(); if (tasksWatcher) tasksWatcher.close(); });
app.on('window-all-closed', () => { /* stay alive in the tray */ });
