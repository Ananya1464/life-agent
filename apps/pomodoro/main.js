const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

let mainWindow = null;

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
  return { logPath: path.join(app.getPath('documents'), 'pomodoro-log.md') };
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
      nodeIntegration: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
};

app.whenReady().then(() => {
  createWindow();

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

ipcMain.on('quit-app', () => {
  app.quit();
});
