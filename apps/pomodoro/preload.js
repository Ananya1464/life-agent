const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pomodoroAPI', {
  windowShake: () => ipcRenderer.invoke('window-shake'),
  writeLog: (logLine) => ipcRenderer.invoke('write-log', logLine),
  selectLogDestination: () => ipcRenderer.invoke('select-log-path'),
  getLogDestination: () => ipcRenderer.invoke('get-log-path'),
  quit: () => ipcRenderer.send('quit-app')
});
