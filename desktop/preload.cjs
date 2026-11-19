const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vydraSetup', {
  settings: () => ipcRenderer.invoke('setup:settings'),
  choose: () => ipcRenderer.invoke('setup:choose'),
  space: folder => ipcRenderer.invoke('setup:space', folder),
  install: (folder, mode) => ipcRenderer.invoke('setup:install', folder, mode),
  pause: () => ipcRenderer.invoke('setup:pause'),
  progress: callback => ipcRenderer.on('setup:progress', (_event, message) => callback(message)),
});
