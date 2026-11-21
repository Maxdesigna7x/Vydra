const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vydraSetup', {
  settings: () => ipcRenderer.invoke('setup:settings'),
  choose: () => ipcRenderer.invoke('setup:choose'),
  estimate: (folder, mode) => ipcRenderer.invoke('setup:estimate', folder, mode),
  install: (folder, mode) => ipcRenderer.invoke('setup:install', folder, mode),
  pause: () => ipcRenderer.invoke('setup:pause'),
  updates: callback => {
    ipcRenderer.on('updates:available', (_event, update) => callback(update));
    ipcRenderer.send('updates:ready');
  },
  downloadUpdate: () => ipcRenderer.send('updates:download'),
  transfer: callback => ipcRenderer.on('setup:transfer', (_event, event) => callback(event)),
  progress: callback => ipcRenderer.on('setup:progress', (_event, message) => callback(message)),
});
