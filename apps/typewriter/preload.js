const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('typewriterAPI', {
  getStoragePath: () => ipcRenderer.invoke('get-storage-path'),
  quit: () => ipcRenderer.send('quit-app')
});
