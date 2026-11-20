const api = window.vydraSetup;
const $ = id => document.getElementById(id);
const form = document.querySelector('form');
const folder = $('folder');
const mode = () => new FormData(form).get('mode');
const stages = new Map([...document.querySelectorAll('[data-stage]')].map(stage => [stage.dataset.stage, stage]));
const number = new Intl.NumberFormat('es', { maximumFractionDigits: 1 });
const phaseNames = { transfer: 'Descargando', working: 'En proceso', retry: 'Reintentando', done: 'Completada', stopped: 'Detenida' };
const speed = new Intl.NumberFormat('es', { maximumFractionDigits: 2 });
let settings;
let timer;
let spaceRequest = 0;
let selection;
let running = false;
let latest;
let lastUpdate;

async function showSpace() {
  const requested = ++spaceRequest;
  const target = folder.value.trim();
  if (!target) { $('space').textContent = ''; return; }
  try {
    const gib = 1024 ** 3;
    const required = settings.minimum[mode()] / gib;
    const free = await api.space(target) / gib;
    if (requested === spaceRequest) {
      $('space').textContent = `${number.format(free)} GiB libres · Hasta ${required} GiB para una instalación nueva`;
    }
  } catch {
    if (requested === spaceRequest) $('space').textContent = 'No se pudo comprobar el espacio de esta carpeta.';
  }
}

function duration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const remainder = Math.ceil(seconds);
  if (remainder >= 3600) return `${Math.floor(remainder / 3600)} h ${Math.floor(remainder % 3600 / 60)} min`;
  if (remainder >= 60) return `${Math.floor(remainder / 60)} min ${remainder % 60} s`;
  return `${remainder} s`;
}

function renderTransfer() {
  if (!latest) return;
  const { phase, item, received, total, rate, eta, scope } = latest;
  const stale = phase === 'transfer' && performance.now() - lastUpdate > 5500;
  const known = Number.isFinite(received) && total > 0;
  const value = phase === 'done' ? 100 : known ? Math.min(100, received * 100 / total) : null;
  if (value === null) $('transfer-bar').removeAttribute('value');
  else $('transfer-bar').value = value;
  $('percent').textContent = value === null ? '—' : `${Math.floor(value)} %`;
  const label = phaseNames[phase] || '';
  if ($('phase-label').textContent !== label) $('phase-label').textContent = label;
  $('active-item').textContent = item + (stale ? ' · Esperando datos' : scope === 'file' && phase === 'transfer' ? ' · Archivo actual' : '');
  const mb = bytes => `${number.format(bytes / 1e6)} MB`;
  $('bytes').textContent = known ? `${mb(received)} / ${mb(total)}` : Number.isFinite(received) ? mb(received) : '—';
  $('rate').textContent = !stale && phase === 'transfer' && rate > 0 ? `${speed.format(rate / 1e6)} MB/s` : '—';
  $('eta').textContent = !stale && phase === 'transfer' ? duration(eta) : '—';
}

function showProgress(event) {
  const stage = stages.get(event.stage);
  if (!running || !stage) return;
  for (const entry of stages.values()) entry.removeAttribute('aria-current');
  if (event.phase === 'done') {
    stage.dataset.state = 'done';
    stage.setAttribute('aria-label', `${stage.textContent}, completada`);
  } else {
    stage.removeAttribute('data-state');
    stage.removeAttribute('aria-label');
    stage.setAttribute('aria-current', 'step');
  }
  // Keep the completed byte count during hashing or extraction within this stage.
  if (event.stage === latest?.stage && event.phase === 'working' && latest.scope !== 'file' && event.received === undefined) {
    event = { received: latest.received, total: latest.total, ...event };
  }
  latest = event;
  lastUpdate = performance.now();
  $('active-stage').textContent = stage.textContent;
  renderTransfer();
}

$('download-update').onclick = api.downloadUpdate;
api.updates(update => {
  $('update-notice').hidden = !update;
  if (!update) return;
  $('update-message').textContent = update.prerelease
    ? `Versión de prueba v${update.version} disponible` : `Vydra v${update.version} está disponible`;
});

api.progress(message => {
  const readable = message.replace(/^(VYDRA_SETUP .*|Progress \d+ of \d+)\r?\n?/gmu, '');
  if (!readable) return;
  $('details').hidden = false;
  $('log').textContent = ($('log').textContent + readable).slice(-20_000);
  $('log').scrollTop = $('log').scrollHeight;
});
api.transfer(showProgress);
setInterval(() => { if (running) renderTransfer(); }, 1000);

async function initialize() {
  settings = await api.settings();
  $('cuda-label').textContent = settings.cudaLabel;
  folder.value = settings.current?.root || settings.defaultFolder;
  form.elements.mode.value = settings.current?.mode || 'cuda';
  $('install').disabled = false;
  await showSpace();
}

$('choose').onclick = async () => {
  const chosen = await api.choose();
  if (chosen) { folder.value = chosen; await showSpace(); }
};
$('default-folder').onclick = () => {
  folder.value = settings.defaultFolder;
  showSpace();
};
form.oninput = () => {
  clearTimeout(timer);
  timer = setTimeout(showSpace, 300);
};
$('pause').onclick = async () => {
  $('pause').disabled = true;
  $('status').textContent = 'Pausando preparación…';
  await api.pause();
};
$('back').onclick = () => {
  $('preparation').hidden = true;
  $('configuration').hidden = false;
  folder.focus();
};
$('retry').onclick = () => install();

async function install() {
  if (running) return;
  running = true;
  $('configuration').hidden = true;
  $('preparation').hidden = false;
  $('retry').hidden = $('back').hidden = true;
  $('pause').hidden = $('pause').disabled = false;
  $('status').textContent = '';
  $('destination').textContent = selection.folder;
  $('device-summary').textContent = selection.mode === 'cuda' ? 'Dispositivo · GPU NVIDIA' : 'Dispositivo · CPU';
  for (const stage of stages.values()) {
    stage.removeAttribute('data-state');
    stage.removeAttribute('aria-label');
  }
  latest = undefined;
  showProgress({ stage: 'environment', phase: 'working', item: 'Comprobando espacio y dispositivo' });
  $('preparation-heading').focus();
  try {
    await api.install(selection.folder, selection.mode);
    $('status').textContent = 'Vydra está listo.';
  } catch (error) {
    $('status').textContent = error.message.replace(/^Error invoking remote method .*?: (Error: )?/u, '');
    $('retry').hidden = $('back').hidden = false;
    if (latest?.phase !== 'done') {
      latest = { ...latest, phase: 'stopped' };
      renderTransfer();
    }
    $('retry').focus();
  } finally {
    running = false;
    $('pause').hidden = true;
  }
}
form.onsubmit = event => {
  event.preventDefault();
  selection = { folder: folder.value.trim(), mode: mode() };
  void install();
};

$('install').disabled = true;
initialize().catch(error => {
  $('status').textContent = error.message;
  $('configuration').hidden = true;
  $('preparation').hidden = false;
});
