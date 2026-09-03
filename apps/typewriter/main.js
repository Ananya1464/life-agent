const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

let mainWindow = null;

const getTypewriterDir = () => path.join(app.getPath('documents'), 'Typewriter');

// Ensure storage directory exists
const ensureStorageDir = () => {
  const dir = getTypewriterDir();
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch (err) {
    console.error('Failed to create Typewriter storage directory:', err);
  }
  return dir;
};

const createWindow = () => {
  console.log('createWindow started');
  mainWindow = new BrowserWindow({
    width: 420,
    height: 720,
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

  console.log(`mainWindow created with id: ${mainWindow.id}`);
  console.log('isVisible:', mainWindow.isVisible());
  console.log('bounds:', JSON.stringify(mainWindow.getBounds()));

  mainWindow.on('ready-to-show', () => {
    console.log('ready-to-show fired');
    console.log('ready-to-show - isVisible:', mainWindow.isVisible());
    console.log('ready-to-show - bounds:', JSON.stringify(mainWindow.getBounds()));
    mainWindow.show();
    console.log('called show(), isVisible now:', mainWindow.isVisible());
  });

  mainWindow.webContents.on('did-finish-load', () => console.log('did-finish-load fired'));
  mainWindow.webContents.on('console-message', (event, level, message) => {
    console.log('[RENDERER]', message);
  });
  mainWindow.on('unresponsive', () => console.log('window unresponsive'));
  mainWindow.webContents.on('render-process-gone', (event, details) => {
    console.log('RENDER PROCESS GONE:', JSON.stringify(details, null, 2));
  });
  mainWindow.on('closed', () => console.log('mainWindow closed event fired'));

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
};

app.whenReady().then(() => {
  ensureStorageDir();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// IPC Handlers
ipcMain.handle('get-storage-path', async () => {
  return getTypewriterDir();
});

ipcMain.on('quit-app', () => {
  app.quit();
});
