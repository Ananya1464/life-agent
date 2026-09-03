// Pixel Pomodoro App Logic
// State Machine: 'setup' | 'timer' | 'alarm' | 'log'

let currentState = 'setup';
let timerInterval = null;
let alarmInterval = null;

let plannedMinutes = 25;
let sessionStartTime = null;
let sessionEndTime = null;
let sessionDurationMs = 0;
let taskName = '';
let sessionResult = 'completed'; // 'completed' | 'abandoned'

// DOM Elements
const pitContainer = document.getElementById('pit-container');
const wedgeCanvas = document.getElementById('wedge-canvas');
const wedgeCtx = wedgeCanvas.getContext('2d');

const setupView = document.getElementById('setup-view');
const timerView = document.getElementById('timer-view');
const alarmView = document.getElementById('alarm-view');
const logView = document.getElementById('log-view');

const inputMinutes = document.getElementById('input-minutes');
const inputTask = document.getElementById('input-task');
const btnStart = document.getElementById('btn-start');

const timerTaskDisplay = document.getElementById('timer-task-display');
const timerCountdown = document.getElementById('timer-countdown');
const btnAbandon = document.getElementById('btn-abandon');

const logStatusBadge = document.getElementById('log-status-badge');
const logTimeDetails = document.getElementById('log-time-details');
const btnLog = document.getElementById('btn-log');
const btnSkip = document.getElementById('btn-skip');
const btnSelectLog = document.getElementById('btn-select-log');

// Format 2 digits
const pad2 = (num) => String(num).padStart(2, '0');

// Format MM:SS
const formatMMSS = (ms) => {
  const totalSecs = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  return `${pad2(m)}:${pad2(s)}`;
};

// Format Timestamp YYYY-MM-DD HH:mm
const formatTimestamp = (date) => {
  const y = date.getFullYear();
  const m = pad2(date.getMonth() + 1);
  const d = pad2(date.getDate());
  const hh = pad2(date.getHours());
  const mm = pad2(date.getMinutes());
  return `${y}-${m}-${d} ${hh}:${mm}`;
};

// Clear Tan Wedge Canvas
const clearWedge = () => {
  wedgeCtx.clearRect(0, 0, 104, 104);
};

// Draw Tan Wedge (#c38a42) sweeping clockwise from 12 o'clock (-PI/2)
const drawWedge = (fraction) => {
  clearWedge();
  if (fraction <= 0) return;
  const clamped = Math.min(1, Math.max(0, fraction));
  const startAngle = -Math.PI / 2;
  const endAngle = startAngle + (clamped * 2 * Math.PI);

  wedgeCtx.beginPath();
  wedgeCtx.moveTo(52, 52);
  wedgeCtx.arc(52, 52, 52, startAngle, endAngle, false);
  wedgeCtx.closePath();
  wedgeCtx.fillStyle = '#c38a42';
  wedgeCtx.fill();
};

// Switch Active View
const switchState = (newState) => {
  currentState = newState;
  setupView.style.display = (newState === 'setup') ? 'flex' : 'none';
  timerView.style.display = (newState === 'timer') ? 'flex' : 'none';
  alarmView.style.display = (newState === 'alarm') ? 'flex' : 'none';
  logView.style.display = (newState === 'log') ? 'flex' : 'none';

  if (newState !== 'alarm') {
    pitContainer.style.backgroundColor = '#57301f';
  }
};

// 1. SETUP -> TIMER
const startTimer = () => {
  let val = parseInt(inputMinutes.value, 10);
  if (isNaN(val) || val < 1) val = 25;
  if (val > 180) val = 180;
  plannedMinutes = val;
  inputMinutes.value = val;

  taskName = inputTask.value.trim().slice(0, 24);
  timerTaskDisplay.textContent = taskName ? taskName.toUpperCase() : 'FOCUS';

  sessionDurationMs = plannedMinutes * 60 * 1000;
  sessionStartTime = Date.now();
  sessionEndTime = sessionStartTime + sessionDurationMs;

  switchState('timer');
  updateTimerTick();

  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(updateTimerTick, 100);
};

// Timer Tick (Wall-clock based)
const updateTimerTick = () => {
  const now = Date.now();
  const elapsedMs = now - sessionStartTime;
  const remainingMs = sessionEndTime - now;

  if (remainingMs <= 0) {
    // Time's up!
    clearInterval(timerInterval);
    timerInterval = null;
    clearWedge();
    triggerAlarm();
    return;
  }

  timerCountdown.textContent = formatMMSS(remainingMs);
  const fraction = elapsedMs / sessionDurationMs;
  drawWedge(fraction);
};

// Abort Session (Ctrl+C)
const abandonSession = () => {
  if (currentState !== 'timer') return;
  clearInterval(timerInterval);
  timerInterval = null;

  const actualElapsedMs = Date.now() - sessionStartTime;
  sessionResult = 'abandoned';
  showLogPrompt(actualElapsedMs);
};

// 2. ALARM STATE
const triggerAlarm = () => {
  switchState('alarm');
  let toggle = false;

  if (alarmInterval) clearInterval(alarmInterval);
  alarmInterval = setInterval(() => {
    toggle = !toggle;
    pitContainer.style.backgroundColor = toggle ? '#c38a42' : '#D9A97A';
  }, 220);

  // Sound and window shake are deferred per prompt instructions until visual/flow confirmation
};

const stopAlarm = () => {
  if (alarmInterval) {
    clearInterval(alarmInterval);
    alarmInterval = null;
  }
  pitContainer.style.backgroundColor = '#57301f';
  sessionResult = 'completed';
  showLogPrompt(sessionDurationMs);
};

// 3. LOG PROMPT STATE
const showLogPrompt = (actualElapsedMs) => {
  clearWedge();
  switchState('log');

  const actualElapsedMMSS = formatMMSS(actualElapsedMs);

  if (sessionResult === 'completed') {
    logStatusBadge.textContent = 'COMPLETED';
    logStatusBadge.className = 'log-status completed';
  } else {
    logStatusBadge.textContent = 'ABANDONED';
    logStatusBadge.className = 'log-status abandoned';
  }

  logTimeDetails.innerHTML = `${plannedMinutes} min planned<br>${actualElapsedMMSS} elapsed`;
};

// Commit Log Entry
const commitLog = async () => {
  const now = new Date();
  const dateStr = formatTimestamp(now);
  const actualElapsed = (sessionResult === 'completed') 
    ? `${plannedMinutes}:00` 
    : formatMMSS(Date.now() - sessionStartTime);

  const checkMark = (sessionResult === 'completed') ? '[x]' : '[ ]';
  const taskLabel = taskName || '(no task)';
  const statusLabel = sessionResult;

  // Exact specified Markdown line format:
  // - [x] YYYY-MM-DD HH:mm — 25 min planned, 25:00 elapsed — "task" — completed
  const logLine = `- ${checkMark} ${dateStr} — ${plannedMinutes} min planned, ${actualElapsed} elapsed — "${taskLabel}" — ${statusLabel}`;

  if (window.pomodoroAPI && window.pomodoroAPI.writeLog) {
    const res = await window.pomodoroAPI.writeLog(logLine);
    console.log('[LOG RESULT]', res);
  }

  resetToSetup();
};

// Skip Log Entry
const skipLog = () => {
  resetToSetup();
};

// Reset to Setup State
const resetToSetup = () => {
  clearWedge();
  if (timerInterval) clearInterval(timerInterval);
  if (alarmInterval) clearInterval(alarmInterval);

  taskName = '';
  inputTask.value = '';

  switchState('setup');

  // Focus and select the minutes field as specified
  setTimeout(() => {
    inputMinutes.focus();
    inputMinutes.select();
  }, 50);
};

// Event Listeners
btnStart.addEventListener('click', startTimer);
btnAbandon.addEventListener('click', abandonSession);

btnLog.addEventListener('click', commitLog);
btnSkip.addEventListener('click', skipLog);

// Select / Persist Log Destination
btnSelectLog.addEventListener('click', async () => {
  if (window.pomodoroAPI && window.pomodoroAPI.selectLogDestination) {
    const selected = await window.pomodoroAPI.selectLogDestination();
    if (selected) {
      btnSelectLog.title = `Log: ${selected}`;
    }
  }
});

// Load Initial Log Path
if (window.pomodoroAPI && window.pomodoroAPI.getLogDestination) {
  window.pomodoroAPI.getLogDestination().then((logPath) => {
    if (logPath) {
      btnSelectLog.title = `Log: ${logPath}`;
    }
  });
}

// Global Keyboard Handler
window.addEventListener('keydown', (e) => {
  // Ctrl+C to abandon while timing
  if (currentState === 'timer' && e.ctrlKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    abandonSession();
    return;
  }

  // Setup: Enter starts session
  if (currentState === 'setup' && e.key === 'Enter') {
    e.preventDefault();
    startTimer();
    return;
  }

  // Alarm: Enter stops alarm and goes to log prompt
  if (currentState === 'alarm' && e.key === 'Enter') {
    e.preventDefault();
    stopAlarm();
    return;
  }

  // Log: Enter logs, Escape skips
  if (currentState === 'log') {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitLog();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      skipLog();
    }
  }
});

// Initial Focus
window.addEventListener('DOMContentLoaded', () => {
  inputMinutes.focus();
  inputMinutes.select();
});
