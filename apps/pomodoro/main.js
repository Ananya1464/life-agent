const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

let mainWindow = null;

// Test mode (POMODORO_SMOKE_DIR): isolated profile and log, no single-instance lock
const SMOKE_DIR = process.env.POMODORO_SMOKE_DIR || '';
if (process.env.POMODORO_USER_DATA) app.setPath('userData', process.env.POMODORO_USER_DATA);
if (!SMOKE_DIR && !app.requestSingleInstanceLock()) {
  app.quit();                                    // one avocado is enough
} else if (!SMOKE_DIR) {
  app.on('second-instance', () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.showInactive(); } });
}

const getConfigPath = () => path.join(app.getPath('userData'), 'pomodoro-config.json');

const loadConfig = () => {
  try {
    const configPath = getConfigPath();
    if (fs.existsSync(configPath)) {
      return JSON.parse(fs.readFileSync(configPath, 'utf8'));
    }
  } catch (err) {
    console.error('Failed to load config:', err);
  }
  return { logPath: process.env.POMODORO_LOG_PATH || path.join(app.getPath('documents'), 'pomodoro-log.md') };
};

const saveConfig = (config) => {
  try {
    const configPath = getConfigPath();
    fs.mkdirSync(path.dirname(configPath), { recursive: true });
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
  } catch (err) {
    console.error('Failed to save config:', err);
  }
};

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 266,
    height: 322,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    alwaysOnTop: true,
    resizable: false,
    useContentSize: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      autoplayPolicy: 'no-user-gesture-required',   // the alarm must sound without a click
      backgroundThrottling: false                    // keep timers and audio exact while unfocused/covered
    }
  });
  mainWindow.setAlwaysOnTop(true, 'floating');       // above ordinary windows, below system UI

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
};

app.whenReady().then(() => {
  createWindow();
  if (SMOKE_DIR) runSmoke(SMOKE_DIR).catch((err) => { console.error('SMOKE FAILED', err); app.exit(2); });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// IPC Handlers
ipcMain.handle('get-log-path', async () => {
  const config = loadConfig();
  return config.logPath;
});

ipcMain.handle('select-log-path', async () => {
  if (!mainWindow) return null;
  const currentConfig = loadConfig();
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: 'Select Pomodoro Log Markdown File',
    defaultPath: currentConfig.logPath || path.join(app.getPath('documents'), 'pomodoro-log.md'),
    filters: [
      { name: 'Markdown Files', extensions: ['md', 'markdown', 'txt'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (!canceled && filePath) {
    currentConfig.logPath = filePath;
    saveConfig(currentConfig);
    return filePath;
  }
  return currentConfig.logPath;
});

ipcMain.handle('write-log', async (event, logLine) => {
  try {
    const config = loadConfig();
    const targetFile = config.logPath || path.join(app.getPath('documents'), 'pomodoro-log.md');
    fs.mkdirSync(path.dirname(targetFile), { recursive: true });
    fs.appendFileSync(targetFile, logLine + '\n', 'utf8');
    return { success: true, filePath: targetFile };
  } catch (err) {
    console.error('Failed to write log:', err);
    return { success: false, error: err.message };
  }
});

ipcMain.handle('window-shake', async () => {
  // Reserved for alarm state shake
  if (!mainWindow) return;
  const bounds = mainWindow.getBounds();
  const originalX = bounds.x;
  const originalY = bounds.y;
  
  const startTime = Date.now();
  const duration = 2000;
  
  const shakeInterval = setInterval(() => {
    if (Date.now() - startTime > duration || !mainWindow || mainWindow.isDestroyed()) {
      clearInterval(shakeInterval);
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.setBounds({ x: originalX, y: originalY, width: bounds.width, height: bounds.height });
      }
      return;
    }
    const dx = Math.floor((Math.random() * 15) - 7);
    const dy = Math.floor((Math.random() * 15) - 7);
    mainWindow.setBounds({ x: originalX + dx, y: originalY + dy, width: bounds.width, height: bounds.height });
  }, 40);
});

// Taskbar attention flash while the alarm rings (strictly boolean-validated)
ipcMain.handle('alarm-attention', async (event, on) => {
  if (typeof on !== 'boolean' || !mainWindow || mainWindow.isDestroyed()) return false;
  mainWindow.flashFrame(on);
  return true;
});

ipcMain.on('quit-app', () => {
  app.quit();
});

/** Drive the real window through a full session, save screenshots and report (test mode only). */
async function runSmoke(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const wc = mainWindow.webContents;
  const errors = [];
  wc.on('console-message', (_e, level, message) => { if (level >= 2) errors.push(message); });
  if (wc.isLoading()) await new Promise((r) => wc.once('did-finish-load', r));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const js = (code) => wc.executeJavaScript(code);
  const shot = async (name) => { await sleep(700); wc.invalidate(); await sleep(400); fs.writeFileSync(path.join(dir, name + '.png'), (await wc.capturePage()).toPNG()); };
  const result = { errors, alwaysOnTop: mainWindow.isAlwaysOnTop() };
  await sleep(600);
  await shot('1-idle');

  await js("document.getElementById('input-minutes').value = '25'; document.getElementById('input-task').value = 'Write report'; document.getElementById('btn-start').click();");
  result.afterStart = await js('window.__pomo.debug()');
  result.duplicateStart = await js("document.getElementById('btn-start').click(); window.__pomo.debug().state");
  await shot('2-timer');
  const t1 = await js("document.getElementById('timer-countdown').textContent"); await sleep(2200);
  const t2 = await js("document.getElementById('timer-countdown').textContent");
  result.countdown = [t1, t2];

  // Make the session end 1.2s from now (the end timestamp is the single source of truth)
  await js('sessionEndTime = Date.now() + 1200;');
  await sleep(2600);
  result.atAlarm = await js('window.__pomo.debug()');
  result.windowFocused = mainWindow.isFocused();
  await shot('3-celebration');
  await sleep(1200);
  result.alarmStillRinging = await js('window.__pomo.debug().alarm.playing');
  await shot('4-celebration-later');

  await js("document.getElementById('btn-stop-alarm').click();");
  await sleep(500);
  result.afterStop = await js('window.__pomo.debug()');
  const logFile = process.env.POMODORO_LOG_PATH;
  result.logLines = logFile && fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8').trim().split(/\r?\n/) : [];
  await shot('5-after-stop');
  fs.writeFileSync(path.join(dir, 'smoke.json'), JSON.stringify(result, null, 2));
  app.quit();
}
