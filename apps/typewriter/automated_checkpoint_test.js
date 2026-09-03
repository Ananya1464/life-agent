const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

let mainWindow = null;
const ARTIFACT_DIR = 'C:\\Users\\Ananya\\.gemini\\antigravity-ide\\brain\\25415e2b-830e-4fbb-a3e8-ec3e05fdfdce';

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

  mainWindow.webContents.on('console-message', (event, level, message) => {
    console.log('[RENDERER]', message);
  });

  mainWindow.webContents.on('did-finish-load', async () => {
    console.log('did-finish-load fired');
    
    // Wait for DOM rendering and font layout
    await new Promise(res => setTimeout(res, 800));

    // 1. Inspect Initial Counter and DOM State
    const initialCounter = await mainWindow.webContents.executeJavaScript(`
      document.getElementById('done-counter').textContent
    `);
    console.log('[TEST] Initial counter on screen:', initialCounter);

    // Capture initial screenshot
    const initialImage = await mainWindow.webContents.capturePage();
    const screenshotPath = path.join(ARTIFACT_DIR, 'typewriter_checklist_initial.png');
    fs.writeFileSync(screenshotPath, initialImage.toPNG());
    console.log('[TEST] Saved initial checklist screenshot to:', screenshotPath);

    // 2. Programmatically Click an Unchecked Task Item ("task-0": Install dependencies)
    console.log('\n[TEST] Programmatically clicking unchecked item (task-0: Install dependencies)...');
    const toggleResult1 = await mainWindow.webContents.executeJavaScript(`
      (() => {
        const item = document.querySelector('.checklist-item[data-task-id="task-0"]');
        if (!item) return { error: 'item not found' };
        item.click();
        return {
          counter: document.getElementById('done-counter').textContent,
          isChecked: item.classList.contains('checked'),
          text: item.querySelector('.task-label').innerText
        };
      })()
    `);
    console.log('[TEST] Toggle 1 result:', JSON.stringify(toggleResult1, null, 2));

    await new Promise(res => setTimeout(res, 300));

    // Capture toggled screenshot
    const toggledImage = await mainWindow.webContents.capturePage();
    const toggledScreenshotPath = path.join(ARTIFACT_DIR, 'typewriter_checklist_toggled.png');
    fs.writeFileSync(toggledScreenshotPath, toggledImage.toPNG());
    console.log('[TEST] Saved toggled checklist screenshot to:', toggledScreenshotPath);

    // 3. Programmatically Click an already-checked task item ("task-1": Initialize git repo)
    console.log('\n[TEST] Programmatically unchecking item (task-1: Initialize git repo)...');
    const toggleResult2 = await mainWindow.webContents.executeJavaScript(`
      (() => {
        const item = document.querySelector('.checklist-item[data-task-id="task-1"]');
        if (!item) return { error: 'item not found' };
        item.click();
        return {
          counter: document.getElementById('done-counter').textContent,
          isChecked: item.classList.contains('checked'),
          text: item.querySelector('.task-label').innerText
        };
      })()
    `);
    console.log('[TEST] Toggle 2 result:', JSON.stringify(toggleResult2, null, 2));

    await new Promise(res => setTimeout(res, 500));
    console.log('\n[TEST] Automated test completed successfully. Exiting.');
    app.quit();
  });

  mainWindow.on('closed', () => console.log('mainWindow closed event fired'));

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
};

app.whenReady().then(() => {
  createWindow();
});
