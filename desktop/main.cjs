const { app, BrowserWindow, Menu, clipboard, dialog, ipcMain, net, shell } = require('electron');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const { mkdir, readFile } = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { checkForUpdate } = require('./updates.cjs');
const { layout, minimum, ready, prepare, pythonProcess, writeAtomic, freeSpace } = require('./runtime.cjs');

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
let installation;
let quitting = false;
let reconfigure = false;
let config;
let availableUpdate;
let updateRequest;
let showingUpdateDialog = false;

function configFile() { return path.join(app.getPath('userData'), 'settings.json'); }
function resourceFolder() { return path.join(app.isPackaged ? process.resourcesPath : __dirname, 'resources'); }
function windowIcon() { return path.join(resourceFolder(), 'vydra.png'); }
function defaultFolder() {
  if (process.platform === 'win32') return path.join(process.env.LOCALAPPDATA || app.getPath('userData'), 'Vydra', 'Data');
  return path.join(process.env.XDG_DATA_HOME || path.join(app.getPath('home'), '.local', 'share'), 'Vydra');
}

function progress(message) {
  if (setupWindow && !setupWindow.isDestroyed()) setupWindow.webContents.send('setup:progress', message);
}

function sendUpdateNotice(window) {
  if (!window || window.isDestroyed()) return;
  const notice = availableUpdate
    ? { version: availableUpdate.version, prerelease: availableUpdate.prerelease }
    : null;
  window.webContents.send('updates:available', notice);
}

async function downloadUpdate(update = availableUpdate) {
  if (!update) return;
  try { await shell.openExternal(update.url); }
  catch (error) { dialog.showErrorBox('Actualización de Vydra', error.message); }
}

function connectUpdateNotice(window, allowedPage) {
  const contents = window.webContents;
  const allowed = event => event.senderFrame?.url === allowedPage && event.senderFrame.parent === null;
  contents.ipc.on('updates:ready', event => {
    if (allowed(event)) sendUpdateNotice(window);
  });
  contents.ipc.on('updates:download', event => {
    if (allowed(event)) void downloadUpdate();
  });
}

function refreshUpdate() {
  if (!updateRequest) {
    updateRequest = checkForUpdate({
      version: app.getVersion(), platform: process.platform, arch: process.arch,
      fetch: (url, options) => net.fetch(url, options),
    }).then(result => {
      availableUpdate = result;
      sendUpdateNotice(engineWindow);
      sendUpdateNotice(setupWindow);
      return result;
    }).finally(() => { updateRequest = null; });
  }
  return updateRequest;
}

async function showUpdateDialog() {
  if (showingUpdateDialog) return;
  showingUpdateDialog = true;
  try {
    const update = await refreshUpdate();
    const options = update ? {
      message: `Vydra v${update.version} está disponible`,
      detail: update.prerelease ? 'Esta es una versión de prueba.' : '',
      buttons: ['Descargar', 'Más tarde'], defaultId: 0, cancelId: 1,
    } : { message: `Vydra v${app.getVersion()} está al día.`, buttons: ['Aceptar'] };
    const parent = engineWindow || setupWindow;
    const { response } = await (parent ? dialog.showMessageBox(parent, options) : dialog.showMessageBox(options));
    if (update && response === 0) await downloadUpdate(update);
  } catch (error) {
    console.warn('Update check failed:', error.message);
    if (!quitting) dialog.showErrorBox('Actualización de Vydra', 'No se pudieron consultar las actualizaciones. Inténtalo más tarde.');
  } finally {
    showingUpdateDialog = false;
  }
}

function checkForUpdatesInBackground() {
  refreshUpdate().catch(error => console.warn('Update check failed:', error.message));
}

function setup() {
  if (setupWindow && !setupWindow.isDestroyed()) return setupWindow.show();
  setupWindow = new BrowserWindow({
    width: 760, height: 720, minWidth: 580, minHeight: 560, title: 'Configurar Vydra',
    icon: windowIcon(),
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), sandbox: true, contextIsolation: true },
  });
  setupWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  setupWindow.webContents.on('will-navigate', event => event.preventDefault());
  setupWindow.on('close', event => {
    if (installation) {
      event.preventDefault();
      progress('La preparación sigue en curso. Si se interrumpe, Vydra recuperará las etapas completadas.\n');
    }
  });
  setupWindow.on('closed', () => { setupWindow = null; });
  const setupPath = path.join(__dirname, 'setup.html');
  connectUpdateNotice(setupWindow, pathToFileURL(setupPath).href);
  setupWindow.loadFile(setupPath);
}

function configureEngineNavigation(contents, home) {
  const history = contents.navigationHistory;
  const origin = new URL(home).origin;
  const allowed = target => new URL(target).origin === origin;
  const isMainFrame = event => event.senderFrame && event.senderFrame.parent === null;
  const updateToolbar = () => {
    if (!contents.isDestroyed()) {
      contents.send('navigation:state', { canGoBack: history.getActiveIndex() > 0, atHome: contents.getURL() === home });
    }
  };
  contents.ipc.on('navigation:ready', event => {
    if (isMainFrame(event)) updateToolbar();
  });
  contents.ipc.on('navigation:back', event => {
    if (!isMainFrame(event)) return;
    const index = history.getActiveIndex();
    if (index > 0) history.goToIndex(index - 1);
  });
  contents.ipc.on('navigation:home', event => {
    if (!isMainFrame(event) || contents.getURL() === home) return;
    const previous = history.getAllEntries().slice(0, history.getActiveIndex());
    const index = previous.findLastIndex(entry => entry.url === home);
    if (index >= 0) history.goToIndex(index);
    else contents.loadURL(home).catch(console.error);
  });

  const guardNavigation = event => {
    if (!allowed(event.url)) event.preventDefault();
  };
  contents.on('will-navigate', guardNavigation);
  contents.on('will-redirect', guardNavigation);
  contents.on('did-stop-loading', updateToolbar);
  contents.on('did-navigate-in-page', updateToolbar);
  contents.setWindowOpenHandler(({ url: target }) => {
    if (allowed(target)) {
      setImmediate(() => {
        if (!contents.isDestroyed()) contents.loadURL(target).catch(console.error);
      });
    } else if (new URL(target).protocol === 'https:') {
      shell.openExternal(target).catch(console.error);
    }
    return { action: 'deny' };
  });
}

async function startEngine(paths) {
  const runtime = path.join(paths.core, 'desktop_bootstrap.py');
  const launch = pythonProcess(paths, [runtime, 'serve', paths.state]);
  const child = spawn(launch.command, launch.args, {
    env: launch.env, cwd: paths.core, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
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
  engineWindow = new BrowserWindow({
    title: 'Vydra', width: 1220, height: 870, minWidth: 820, minHeight: 600,
    icon: windowIcon(),
    webPreferences: {
      preload: path.join(__dirname, 'navigation-preload.cjs'), sandbox: true, contextIsolation: true,
    },
  });
  configureEngineNavigation(engineWindow.webContents, url);
  connectUpdateNotice(engineWindow, url);
  engineWindow.on('closed', () => {
    engineWindow = null;
    if (engine === child) {
      child.stdin.end();
      if (!quitting && !reconfigure && opened) app.quit();
    }
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
  handle('setup:pause', () => installation?.abort(new Error('Preparación pausada. Vuelve a usar la misma carpeta y el mismo modo para continuar.')));
  handle('setup:install', async (root, mode) => {
    if (installation || engine) throw new Error('Ya hay una sesión de Vydra activa.');
    if (typeof root !== 'string' || !path.isAbsolute(root) || !Object.hasOwn(minimum, mode)) {
      throw new Error('Selecciona una carpeta absoluta y un modo de instalación.');
    }
    installation = new AbortController();
    try {
      config = { root: path.normalize(root), mode };
      await mkdir(path.dirname(configFile()), { recursive: true });
      await writeAtomic(configFile(), JSON.stringify(config));
      const paths = await prepare(config.root, config.mode, resourceFolder(), progress, { signal: installation.signal });
      installation.signal.throwIfAborted();
      await startEngine(paths);
    } finally {
      installation = null;
    }
  });
}

async function copyMcpConfig() {
  if (!config || !engineWindow || !engine) {
    dialog.showErrorBox('Vydra MCP', 'Abre Vydra y completa la configuración antes de conectar un cliente MCP.');
    return;
  }
  const choice = await dialog.showOpenDialog(engineWindow, {
    title: 'Elige las carpetas a las que podrá acceder el cliente MCP',
    buttonLabel: 'Copiar configuración',
    properties: ['openDirectory', 'multiSelections'],
  });
  if (choice.canceled || !choice.filePaths.length) return;
  const paths = layout(config.root, config.mode, resourceFolder());
  clipboard.writeText(JSON.stringify({
    mcpServers: {
      vydra: {
        command: paths.python,
        args: [path.join(paths.core, 'mcp_server.py'), '--desktop-data-dir', config.root,
          ...choice.filePaths.flatMap(folder => ['--root', folder])],
      },
    },
  }, null, 2));
  await dialog.showMessageBox(engineWindow, {
    message: 'Configuración MCP copiada',
    detail: 'Agrega el servidor Vydra a la configuración de tu cliente MCP y mantén abierta la app mientras se ejecuten las tareas.',
  });
}

async function start() {
  app.setAppUserModelId('com.squirrel.vydra_desktop.vydra-desktop');
  registerSetupHandlers();
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Vydra', submenu: [
      { label: 'Buscar actualizaciones…', click: showUpdateDialog },
      { label: 'Copiar configuración MCP…', click: copyMcpConfig },
      { label: 'Ver carpeta de datos', click: () => { if (config) shell.openPath(config.root); } },
      { label: 'Configurar almacenamiento y dispositivo', click: async () => {
        if (!engineWindow || !engine) { setup(); return; }
        const { response } = await dialog.showMessageBox(engineWindow, {
          message: 'Vydra cerrará la sesión de análisis para abrir la configuración.',
          detail: 'Si hay un análisis activo, se conservarán sus puntos de reanudación.',
          buttons: ['Abrir configuración', 'Cancelar'], defaultId: 1, cancelId: 1,
        });
        if (response !== 0 || !engine || !engineWindow) return;
        reconfigure = true;
        engine.once('close', () => { reconfigure = false; setup(); });
        // Keep the single-instance desktop app alive until the engine exits.
        setup();
        setupWindow.hide();
        engineWindow.close();
      } },
      { role: 'quit', label: 'Salir' },
    ] },
    { label: 'Edición', submenu: [{ role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
  ]));
  checkForUpdatesInBackground();
  setInterval(checkForUpdatesInBackground, 6 * 60 * 60 * 1000).unref();
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

if (process.platform === 'linux') app.commandLine.appendSwitch('class', 'Vydra');

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
    if (installation) { event.preventDefault(); return; }
    quitting = true;
    if (engine) engine.stdin.end();
  });
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(start).catch(error => { dialog.showErrorBox('Vydra', error.message); app.quit(); });
}
