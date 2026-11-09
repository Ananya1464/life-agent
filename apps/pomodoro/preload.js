const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pomodoroAPI', {
  windowShake: () => ipcRenderer.invoke('window-shake'),
  writeLog: (logLine) => ipcRenderer.invoke('write-log', logLine),
  selectLogDestination: () => ipcRenderer.invoke('select-log-path'),
  getLogDestination: () => ipcRenderer.invoke('get-log-path'),
  alarmAttention: (on) => ipcRenderer.invoke('alarm-attention', !!on),
  quit: () => ipcRenderer.send('quit-app')
});
