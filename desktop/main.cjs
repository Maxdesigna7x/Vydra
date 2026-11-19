const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const { mkdir, readFile } = require('node:fs/promises');
const path = require('node:path');
const { layout, minimum, ready, prepare, pythonCommand, writeAtomic, freeSpace } = require('./runtime.cjs');

function handleSquirrelEvent() {
  if (process.platform !== 'win32') return false;
  const event = process.argv[1];
  if (event === '--squirrel-obsolete') { app.quit(); return true; }
  const actions = {
    '--squirrel-install': '--createShortcut',
    '--squirrel-updated': '--createShortcut',
    '--squirrel-uninstall': '--removeShortcut',
  };
  if (!Object.hasOwn(actions, event)) return false;
  const update = path.resolve(path.dirname(process.execPath), '..', 'Update.exe');
  const child = spawn(update, [actions[event], path.basename(process.execPath)], { windowsHide: true, stdio: 'ignore' });
  child.once('error', () => app.quit());
  child.once('close', () => app.quit());
  return true;
}
let setupWindow;
let engineWindow;
let engine;
let installing = false;
let quitting = false;
let config;

function configFile() { return path.join(app.getPath('userData'), 'settings.json'); }
function resourceFolder() { return path.join(app.isPackaged ? process.resourcesPath : __dirname, 'resources'); }
function defaultFolder() {
  if (process.platform === 'win32') return path.join(process.env.LOCALAPPDATA || app.getPath('userData'), 'Vydra', 'Data');
  return path.join(process.env.XDG_DATA_HOME || path.join(app.getPath('home'), '.local', 'share'), 'Vydra');
}

function progress(message) {
  if (setupWindow && !setupWindow.isDestroyed()) setupWindow.webContents.send('setup:progress', message);
}

function setup() {
  if (setupWindow && !setupWindow.isDestroyed()) return setupWindow.show();
  setupWindow = new BrowserWindow({
    width: 760, height: 720, minWidth: 580, minHeight: 560, title: 'Configurar Vydra',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), sandbox: true, contextIsolation: true },
  });
  setupWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  setupWindow.webContents.on('will-navigate', event => event.preventDefault());
  setupWindow.on('close', event => {
    if (installing) {
      event.preventDefault();
      progress('La preparación sigue en curso. Si se interrumpe, Vydra recuperará las etapas completadas.\n');
    }
  });
  setupWindow.on('closed', () => { setupWindow = null; });
  setupWindow.loadFile(path.join(__dirname, 'setup.html'));
}

async function startEngine(paths) {
  const runtime = path.join(paths.core, 'desktop_bootstrap.py');
  const child = spawn(paths.tools, pythonCommand(paths, [runtime, 'serve', paths.state]), {
    env: paths.env, cwd: paths.core, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  });
  engine = child;
  child.stdin.on('error', () => {});
  child.stderr.on('data', bytes => progress(bytes.toString()));
  const lines = createInterface({ input: child.stdout });
  let opened = false;
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      child.stdin.end();
      reject(new Error('El motor local no respondió en 60 segundos.'));
    }, 60_000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('close', code => {
      clearTimeout(timer);
      if (engine === child) engine = null;
      if (!opened) reject(new Error(`El motor se cerró durante el inicio (código ${code}).`));
      else if (!quitting && engineWindow && !engineWindow.isDestroyed()) {
        dialog.showErrorBox('Vydra', 'La sesión local terminó. Puedes volver a abrir Vydra.');
        setup();
        engineWindow.close();
      }
    });
    lines.on('line', line => {
      const match = /^VYDRA_READY (http:\/\/127\.0\.0\.1:[0-9]+\/)$/u.exec(line);
      if (match) { clearTimeout(timer); resolve(match[1]); }
      else progress(`${line}\n`);
    });
  });
  const loopback = new URL(url).origin;
  engineWindow = new BrowserWindow({
    title: 'Vydra', width: 1220, height: 870, minWidth: 820, minHeight: 600,
    webPreferences: { sandbox: true, contextIsolation: true },
  });
  const allowed = target => new URL(target).origin === loopback;
  const guardNavigation = (event, target) => {
    if (!allowed(target)) event.preventDefault();
  };
  function configureContents(contents) {
    contents.on('will-navigate', guardNavigation);
    contents.on('will-redirect', guardNavigation);
    contents.setWindowOpenHandler(({ url: target }) => {
      if (allowed(target)) return { action: 'allow' };
      if (new URL(target).protocol === 'https:') shell.openExternal(target).catch(console.error);
      return { action: 'deny' };
    });
    contents.on('did-create-window', popup => configureContents(popup.webContents));
  }
  configureContents(engineWindow.webContents);
  engineWindow.on('closed', () => {
    engineWindow = null;
    if (engine === child) child.stdin.end();
  });
  try {
    await engineWindow.loadURL(url);
    opened = true;
  } catch (error) {
    engineWindow?.close();
    throw error;
  }
  setupWindow?.hide();
}

function registerSetupHandlers() {
  const handle = (channel, callback) => ipcMain.handle(channel, (event, ...args) => {
    if (event.sender !== setupWindow?.webContents || event.senderFrame !== event.sender.mainFrame) {
      throw new Error('Invalid setup request.');
    }
    return callback(...args);
  });
  handle('setup:settings', () => ({ current: config, defaultFolder: defaultFolder(), minimum,
    cudaLabel: process.platform === 'win32' ? 'Modelos en NVIDIA · FAISS en CPU' : 'Modelos y FAISS en NVIDIA' }));
  handle('setup:choose', async () => {
    const result = await dialog.showOpenDialog(setupWindow, { properties: ['openDirectory', 'createDirectory'] });
    return result.filePaths[0];
  });
  handle('setup:space', folder => freeSpace(path.resolve(folder)));
  handle('setup:install', async (root, mode) => {
    if (installing || engine) throw new Error('Ya hay una sesión de Vydra activa.');
    if (typeof root !== 'string' || !path.isAbsolute(root) || !Object.hasOwn(minimum, mode)) {
      throw new Error('Selecciona una carpeta absoluta y un modo de instalación.');
    }
    installing = true;
    try {
      config = { root: path.normalize(root), mode };
      await mkdir(path.dirname(configFile()), { recursive: true });
      await writeAtomic(configFile(), JSON.stringify(config));
      const paths = await prepare(config.root, config.mode, resourceFolder(), progress);
      await startEngine(paths);
    } finally {
      installing = false;
    }
  });
}

async function start() {
  app.setAppUserModelId('com.squirrel.vydra_desktop.vydra-desktop');
  registerSetupHandlers();
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Vydra', submenu: [
      { label: 'Ver carpeta de datos', click: () => { if (config) shell.openPath(config.root); } },
      { label: 'Configurar almacenamiento y dispositivo', click: () => {
        if (engine) dialog.showMessageBox(engineWindow, { message: 'Cierra la ventana de análisis para cambiar la configuración.' });
        else setup();
      } },
      { role: 'quit', label: 'Salir' },
    ] },
    { label: 'Edición', submenu: [{ role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
  ]));
  config = await readFile(configFile(), 'utf8').then(JSON.parse).catch(() => null);
  if (!process.argv.includes('--setup') && config && typeof config.root === 'string' &&
      path.isAbsolute(config.root) && Object.hasOwn(minimum, config.mode)) {
    const paths = layout(config.root, config.mode, resourceFolder());
    if (await ready(paths)) {
      try { return await startEngine(paths); }
      catch (error) { dialog.showErrorBox('Vydra', error.message); }
    }
  }
  setup();
}

if (handleSquirrelEvent()) {
  // Squirrel finishes shortcut management before the normal app starts.
} else if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const window = engineWindow || setupWindow;
    window?.show();
    window?.focus();
  });
  app.on('before-quit', event => {
    if (installing) { event.preventDefault(); return; }
    quitting = true;
    if (engine) engine.stdin.end();
  });
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(start).catch(error => { dialog.showErrorBox('Vydra', error.message); app.quit(); });
}
