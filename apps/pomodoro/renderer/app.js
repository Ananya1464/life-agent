// Avocado Timer - renderer logic
// State machine: 'setup' | 'timer' | 'alarm'
// The timer is wall-clock based (end timestamp), so sleep, throttling or window changes never cause drift.

const L = window.PomoLogic;
// "Managed" mode: running inside Lifebot, whose clock is the single source of truth. This window then
// only displays that state, reports button presses, and celebrates when Lifebot says time is up.
const managed = !!(window.pomodoroAPI && window.pomodoroAPI.managed);
let managedRunId = null;

let currentState = 'setup';
let timerInterval = null;
let flashInterval = null;

let plannedMinutes = 25;
let sessionStartTime = null;
let sessionEndTime = null;
let sessionDurationMs = 0;
let taskName = '';
let completionHandled = false;   // guards against a second "time's up" for the same session

// DOM Elements
const pitContainer = document.getElementById('pit-container');
const wedgeCanvas = document.getElementById('wedge-canvas');
const wedgeCtx = wedgeCanvas.getContext('2d');

const setupView = document.getElementById('setup-view');
const timerView = document.getElementById('timer-view');
const alarmView = document.getElementById('alarm-view');

const inputMinutes = document.getElementById('input-minutes');
const inputTask = document.getElementById('input-task');
const btnStart = document.getElementById('btn-start');

const timerTaskDisplay = document.getElementById('timer-task-display');
const timerCountdown = document.getElementById('timer-countdown');
const btnAbandon = document.getElementById('btn-abandon');
const btnStopAlarm = document.getElementById('btn-stop-alarm');
const btnDone = document.getElementById('btn-done');
const btnNext = document.getElementById('btn-next');
const miniTime = document.getElementById('mini-time');
const setMini = (on) => document.body.classList.toggle('mini', !!on);
const setMiniText = (text) => { miniTime.textContent = text; };

const clearWedge = () => wedgeCtx.clearRect(0, 0, 104, 104);

// Tan wedge (#c38a42) sweeping clockwise from 12 o'clock
const drawWedge = (fraction) => {
  clearWedge();
  if (fraction <= 0) return;
  const clamped = Math.min(1, Math.max(0, fraction));
  const startAngle = -Math.PI / 2;
  wedgeCtx.beginPath();
  wedgeCtx.moveTo(52, 52);
  wedgeCtx.arc(52, 52, 52, startAngle, startAngle + clamped * 2 * Math.PI, false);
  wedgeCtx.closePath();
  wedgeCtx.fillStyle = '#c38a42';
  wedgeCtx.fill();
};

const switchState = (newState) => {
  currentState = newState;
  setupView.style.display = newState === 'setup' ? 'flex' : 'none';
  timerView.style.display = newState === 'timer' ? 'flex' : 'none';
  alarmView.style.display = newState === 'alarm' ? 'flex' : 'none';
  if (newState !== 'alarm') pitContainer.style.backgroundColor = '#57301f';
};

// 1. SETUP -> TIMER
const startTimer = () => {
  if (currentState !== 'setup') return;           // never start a second timer
  plannedMinutes = L.clampMinutes(inputMinutes.value);
  inputMinutes.value = plannedMinutes;

  taskName = inputTask.value.trim().slice(0, 24);
  timerTaskDisplay.textContent = taskName ? taskName.toUpperCase() : 'FOCUS';

  if (managed) {                                   // Lifebot starts the session; its state update switches the view
    window.pomodoroAPI.start(plannedMinutes, taskName);
    return;
  }

  sessionDurationMs = plannedMinutes * 60 * 1000;
  sessionStartTime = Date.now();
  sessionEndTime = sessionStartTime + sessionDurationMs;
  completionHandled = false;

  switchState('timer');
  updateTimerTick();

  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(updateTimerTick, 100);
};

const updateTimerTick = () => {
  if (currentState !== 'timer') return;
  const now = Date.now();
  const remaining = L.remainingMs(sessionEndTime, now);
  if (managed && remaining <= 0) {                 // wait for Lifebot's completion event
    timerCountdown.textContent = '00:00';
    drawWedge(1);
    return;
  }
  if (remaining <= 0) {
    clearInterval(timerInterval);
    timerInterval = null;
    clearWedge();
    triggerAlarm();
    return;
  }
  timerCountdown.textContent = L.formatMMSS(remaining);
  setMiniText(L.formatMMSS(remaining));
  drawWedge((now - sessionStartTime) / sessionDurationMs);
};

// Abandon a running session (Ctrl+C)
const abandonSession = () => {
  if (currentState !== 'timer') return;
  clearInterval(timerInterval);
  timerInterval = null;
  if (managed) { window.pomodoroAPI.abandon(); resetToSetup(); return; }
  commitLog('abandoned', Date.now() - sessionStartTime);
  resetToSetup();
};

// 2. TIME'S UP: audible alarm + happy, hungry avocado + confetti
const triggerAlarm = () => {
  if (currentState === 'alarm' || completionHandled) return;   // exactly one completion per session
  completionHandled = true;
  setMiniText('DONE!');
  switchState('alarm');
  document.body.classList.add('celebrate');
  window.Alarm.start();
  window.Confetti.start();
  if (window.pomodoroAPI && window.pomodoroAPI.alarmAttention) window.pomodoroAPI.alarmAttention(true);

  let toggle = false;
  if (flashInterval) clearInterval(flashInterval);
  flashInterval = setInterval(() => {
    toggle = !toggle;
    pitContainer.style.backgroundColor = toggle ? '#c38a42' : '#D9A97A';
  }, 500);
};

const stopAlarm = (action) => {
  if (currentState !== 'alarm') return;
  window.Alarm.stop();
  window.Confetti.stop();                       // pieces already in the air finish falling
  if (flashInterval) { clearInterval(flashInterval); flashInterval = null; }
  document.body.classList.remove('celebrate');
  if (window.pomodoroAPI && window.pomodoroAPI.alarmAttention) window.pomodoroAPI.alarmAttention(false);
  if (managed) window.pomodoroAPI.ack(action === 'done' || action === 'next' ? action : 'stop');   // Lifebot already recorded the session
  else commitLog('completed', sessionDurationMs);
  resetToSetup();
};

// Sessions are logged automatically in the same markdown format the app has always used
const commitLog = async (result, elapsedMs) => {
  const logLine = L.buildLogLine({ date: new Date(), plannedMinutes, result, elapsedMs, task: taskName });
  if (window.pomodoroAPI && window.pomodoroAPI.writeLog) {
    try { await window.pomodoroAPI.writeLog(logLine); } catch (err) { console.error('log failed', err); }
  }
};

const resetToSetup = () => {
  clearWedge();
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  if (flashInterval) { clearInterval(flashInterval); flashInterval = null; }
  taskName = '';
  inputTask.value = '';
  switchState('setup');
  setMiniText('READY');
  setTimeout(() => { inputMinutes.focus(); inputMinutes.select(); }, 50);
};

// Managed mode: render Lifebot's state, and celebrate on its completion event
const applyManagedState = (s) => {
  if (!managed) return;
  if (typeof s.collapsed === 'boolean') setMini(s.collapsed);
  if (currentState === 'alarm') return;                      // never interrupt a celebration
  if (s.phase === 'focus') {
    const isNewRun = s.runId !== managedRunId;
    managedRunId = s.runId;
    taskName = s.task && s.task.text ? s.task.text.slice(0, 24) : '';
    timerTaskDisplay.textContent = taskName ? taskName.toUpperCase() : 'FOCUS';
    sessionDurationMs = s.durationMs;
    plannedMinutes = Math.round(s.durationMs / 60000);
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    switchState('timer');
    if (s.running && s.endsAt) {
      sessionEndTime = s.endsAt;
      sessionStartTime = s.endsAt - s.durationMs;
      completionHandled = false;
      updateTimerTick();
      timerInterval = setInterval(updateTimerTick, 100);
    } else {                                                  // paused in Lifebot: freeze the display
      timerCountdown.textContent = L.formatMMSS(s.remainingMs);
      setMiniText(L.formatMMSS(s.remainingMs));
      drawWedge(1 - s.remainingMs / s.durationMs);
    }
    if (isNewRun) completionHandled = false;
  } else if (currentState === 'timer') {                      // stopped from Lifebot or finished elsewhere
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    managedRunId = null;
    resetToSetup();
  }
};

if (managed) {
  document.body.classList.add('managed');
  const api = window.pomodoroAPI;
  document.getElementById('wc-min').addEventListener('click', () => api.collapse(true));
  document.getElementById('wc-expand').addEventListener('click', () => api.collapse(false));
  document.getElementById('wc-hide').addEventListener('click', () => api.hide());
  document.getElementById('wc-home').addEventListener('click', () => api.openApp());
  document.getElementById('btn-minus').addEventListener('click', () => api.adjust(-5));
  document.getElementById('btn-plus').addEventListener('click', () => api.adjust(5));
  api.onMode((m) => setMini(m.collapsed));
  window.pomodoroAPI.onState(applyManagedState);
  window.pomodoroAPI.onCelebrate(() => {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    clearWedge();
    triggerAlarm();
  });
  window.pomodoroAPI.getState().then(applyManagedState);
}

// Events
btnStart.addEventListener('click', startTimer);
btnAbandon.addEventListener('click', abandonSession);
btnStopAlarm.addEventListener('click', () => stopAlarm('stop'));
btnDone.addEventListener('click', () => stopAlarm('done'));
btnNext.addEventListener('click', () => stopAlarm('next'));

window.addEventListener('keydown', (e) => {
  if (currentState === 'timer' && e.ctrlKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    abandonSession();
  } else if (currentState === 'setup' && e.key === 'Enter') {
    e.preventDefault();
    startTimer();
  } else if (currentState === 'alarm' && (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape')) {
    e.preventDefault();
    stopAlarm('stop');
  }
});

window.addEventListener('DOMContentLoaded', () => {
  inputMinutes.focus();
  inputMinutes.select();
});

// Read-only snapshot used by the automated smoke test
window.__pomo = {
  debug: () => ({
    state: currentState, celebrating: document.body.classList.contains('celebrate'),
    alarm: window.Alarm.debug(), confettiActive: window.Confetti.isActive(), confettiCount: window.Confetti.count(),
    hasInterval: timerInterval !== null,
  }),
};
