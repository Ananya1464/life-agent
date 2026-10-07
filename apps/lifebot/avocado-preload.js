// Preload for the floating avocado timer when it runs inside Lifebot ("managed" mode).
// Only a narrow, validated surface is exposed: no filesystem, no shell, no generic IPC.
const { contextBridge, ipcRenderer } = require('electron');

const subscribe = (channel) => (handler) => {
  const listener = (_event, payload) => handler(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};

contextBridge.exposeInMainWorld('pomodoroAPI', {
  managed: true,
  start: (minutes, task) => ipcRenderer.invoke('avocado:start', { minutes, task }),
  abandon: () => ipcRenderer.invoke('avocado:abandon'),
  adjust: (deltaMin) => ipcRenderer.invoke('avocado:adjust', deltaMin),         // -5 or +5 minutes
  ack: (action) => ipcRenderer.invoke('avocado:ack', action),          // 'stop' | 'done' | 'next'
  alarmAttention: (on) => ipcRenderer.invoke('avocado:attention', !!on),
  getState: () => ipcRenderer.invoke('avocado:getState'),
  collapse: (collapsed) => ipcRenderer.invoke('widget:collapse', { widget: 'avocado', collapsed: !!collapsed }),
  hide: () => ipcRenderer.invoke('widget:hide', { widget: 'avocado' }),
  openApp: () => ipcRenderer.invoke('widget:openApp', { tab: 'focus' }),
  onState: subscribe('avocado:state'),
  onCelebrate: subscribe('avocado:celebrate'),
  onMode: subscribe('widget:mode'),
});
