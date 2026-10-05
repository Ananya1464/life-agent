const { contextBridge, ipcRenderer } = require('electron');

const invoke = (channel) => (arg) => ipcRenderer.invoke(channel, arg);
const on = (channel) => (handler) => {
  const listener = (_event, payload) => handler(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};

contextBridge.exposeInMainWorld('lifebot', {
  init: invoke('app:init'),
  tasks: { add: invoke('tasks:add'), toggle: invoke('tasks:toggle'), saveMarkdown: invoke('tasks:saveMarkdown'), setCurrent: invoke('tasks:setCurrent'), remove: invoke('tasks:remove') },
  pomodoro: {
    start: invoke('pomodoro:start'), pause: invoke('pomodoro:pause'), adjust: invoke('pomodoro:adjust'),
    resume: invoke('pomodoro:resume'), stop: invoke('pomodoro:stop'),
  },
  reminders: {
    add: invoke('reminders:add'), remove: invoke('reminders:remove'), done: invoke('reminders:done'),
    snooze: invoke('reminders:snooze'), testPush: invoke('reminders:testPush'),
  },
  settings: { set: invoke('settings:set') },
  briefs: { list: invoke('briefs:list'), run: invoke('briefs:run'), read: invoke('briefs:read') },
  chat: { send: invoke('chat:send'), clear: invoke('chat:clear') },
  dashboard: { open: invoke('dashboard:open') },
  sync: { now: invoke('sync:now') },
  game: { stats: invoke('game:stats') },
  on: {
    pomodoro: on('pomodoro:state'), tasks: on('tasks:changed'), reminders: on('reminders:changed'),
    reminderFired: on('reminder:fired'), bridge: on('bridge:status'), navigate: on('navigate'),
    briefs: on('briefs:changed'), toast: on('toast'), settings: on('settings:changed'), game: on('game'), reward: on('reward'),
  },
});
