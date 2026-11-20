const api = window.vydraSetup;
const form = document.querySelector('form');
const folder = document.getElementById('folder');
const status = document.getElementById('status');
const space = document.getElementById('space');
const log = document.getElementById('log');
const pause = document.getElementById('pause');
const mode = () => new FormData(form).get('mode');
const controls = Array.from(form.querySelectorAll('button, input'));
let settings;
let timer;
let spaceRequest = 0;

async function showSpace() {
  const requested = ++spaceRequest;
  const target = folder.value.trim();
  if (!target) { space.textContent = ''; return; }
  try {
    const gib = 1024 ** 3;
    const required = settings.minimum[mode()] / gib;
    const free = await api.space(target) / gib;
    if (requested === spaceRequest) {
      space.textContent = `${free.toFixed(1)} GiB libres · Hasta ${required} GiB estimados para una instalación nueva.`;
    }
  } catch {
    if (requested === spaceRequest) space.textContent = 'No se pudo comprobar el espacio de esta carpeta.';
  }
}

document.getElementById('download-update').onclick = api.downloadUpdate;
api.updates(update => {
  document.getElementById('update-notice').hidden = !update;
  if (!update) return;
  document.getElementById('update-message').textContent = update.prerelease
    ? `Versión de prueba v${update.version} disponible`
    : `Vydra v${update.version} está disponible`;
});

api.progress(message => {
  document.getElementById('details').hidden = false;
  log.textContent = (log.textContent + message).slice(-20_000);
  log.scrollTop = log.scrollHeight;
});

async function initialize() {
  settings = await api.settings();
  document.getElementById('cuda-label').textContent = settings.cudaLabel;
  folder.value = settings.current?.root || settings.defaultFolder;
  const selected = form.elements.mode;
  selected.value = settings.current?.mode || 'cuda';
  await showSpace();
}

document.getElementById('choose').addEventListener('click', async () => {
  const chosen = await api.choose();
  if (chosen) { folder.value = chosen; await showSpace(); }
});
document.getElementById('default-folder').addEventListener('click', () => {
  folder.value = settings.defaultFolder;
  showSpace();
});
form.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(showSpace, 300);
});
pause.addEventListener('click', async () => {
  pause.disabled = true;
  status.textContent = 'Pausando preparación…';
  await api.pause();
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  const selectedMode = mode();
  for (const control of controls) control.disabled = true;
  pause.hidden = false;
  pause.disabled = false;
  status.textContent = 'Preparando Vydra. Puedes consultar el registro mientras avanza.';
  try {
    await api.install(folder.value.trim(), selectedMode);
    status.textContent = 'Vydra está listo.';
  } catch (error) {
    status.textContent = error.message.replace(/^Error invoking remote method .*?: (Error: )?/u, '');
  } finally {
    pause.hidden = true;
    for (const control of controls) control.disabled = false;
  }
});

initialize().catch(error => { status.textContent = error.message; });
