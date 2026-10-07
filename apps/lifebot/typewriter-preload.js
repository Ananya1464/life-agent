// Preload for the floating typewriter card: a narrow surface, no filesystem, shell or generic IPC.
const { contextBridge, ipcRenderer } = require('electron');

const subscribe = (channel) => (handler) => {
  const listener = (_event, payload) => handler(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};

contextBridge.exposeInMainWorld('typewriterAPI', {
  get: () => ipcRenderer.invoke('tw:get'),
  update: (input) => ipcRenderer.invoke('tw:update', {
    id: input && input.id, oldText: input && input.oldText, newText: input && input.newText,
  }),
  start: (minutes, id) => ipcRenderer.invoke('tw:start', id === undefined ? { minutes } : { minutes, id }),
  select: (id) => ipcRenderer.invoke('tw:select', id),
  remove: (id) => ipcRenderer.invoke('tw:remove', id),
  miniList: (open) => ipcRenderer.invoke('tw:miniList', !!open),
  stop: () => ipcRenderer.invoke('tw:stop'),
  collapse: (collapsed) => ipcRenderer.invoke('widget:collapse', { widget: 'typewriter', collapsed: !!collapsed }),
  hide: () => ipcRenderer.invoke('widget:hide', { widget: 'typewriter' }),
  openApp: () => ipcRenderer.invoke('widget:openApp', { tab: 'tasks' }),
  onChange: subscribe('tw:state'),
  onMode: subscribe('widget:mode'),
});
