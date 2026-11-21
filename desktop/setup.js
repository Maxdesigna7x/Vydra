const api = window.vydraSetup;
const $ = id => document.getElementById(id);
const form = document.querySelector('form');
const folder = $('folder');
const mode = () => new FormData(form).get('mode');
const stages = new Map([...document.querySelectorAll('[data-stage]')].map(stage => [stage.dataset.stage, stage]));
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
const phaseNames = { transfer: 'Downloading', working: 'In progress', retry: 'Retrying', done: 'Complete', stopped: 'Stopped' };
const speed = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
let settings;
let timer;
let estimateRequest = 0;
let currentEstimate;
let selection;
let running = false;
let latest;
let lastUpdate;

function formatDownload(bytes) {
  if (!Number.isFinite(bytes)) return '—';
  if (!bytes) return '0 MB';
  if (bytes < 1e6) return '<1 MB';
  if (bytes < 1e9) return `≈${number.format(bytes / 1e6)} MB`;
  return `≈${number.format(bytes / 1e9)} GB`;
}

function showDownloadEstimate(sizes) {
  const values = sizes ? Object.values(sizes) : [];
  $('download-total').textContent = values.length ? formatDownload(values.reduce((sum, bytes) => sum + bytes, 0)) : '—';
  for (const stage of stages.keys()) $('estimate-' + stage).textContent = formatDownload(sizes?.[stage]);
}

async function showEstimate() {
  const requested = ++estimateRequest;
  const target = folder.value.trim();
  const device = mode();
  currentEstimate = undefined;
  showDownloadEstimate();
  $('space').textContent = target ? 'Checking the selected folder…' : '';
  if (!target) return;
  try {
    const result = await api.estimate(target, device);
    if (requested !== estimateRequest) return;
    currentEstimate = { folder: target, mode: device, stages: result.stages };
    const gib = 1024 ** 3;
    $('space').textContent = `${number.format(result.free / gib)} GiB free · Up to ${result.minimum / gib} GiB for a fresh installation`;
    showDownloadEstimate(result.stages);
  } catch {
    if (requested === estimateRequest) $('space').textContent = 'Could not estimate downloads and available disk space.';
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
  $('active-item').textContent = item + (stale ? ' · Waiting for data' : scope === 'file' && phase === 'transfer' ? ' · Current file' : '');
  const mb = bytes => `${number.format(bytes / 1e6)} MB`;
  $('bytes').textContent = known ? `${mb(received)} / ${mb(total)}` : Number.isFinite(received) ? mb(received) : '—';
  $('rate').textContent = !stale && phase === 'transfer' && rate > 0 ? `${speed.format(rate / 1e6)} MB/s` : '—';
  $('eta').textContent = !stale && phase === 'transfer' ? duration(eta) : '—';
}

function showProgress(event) {
  const stage = stages.get(event.stage);
  if (!running || !stage) return;
  const name = stage.querySelector('.stage-name').textContent;
  for (const entry of stages.values()) entry.removeAttribute('aria-current');
  if (event.phase === 'done') {
    stage.dataset.state = 'done';
    stage.setAttribute('aria-label', `${name}, complete`);
  } else {
    stage.removeAttribute('data-state');
    stage.removeAttribute('aria-label');
    stage.setAttribute('aria-current', 'step');
  }
  // Keep the completed byte count during hashing or extraction within this stage.
  if (event.stage !== 'dependencies' && event.stage === latest?.stage && event.phase === 'working' && latest.scope !== 'file' && event.received === undefined) {
    event = { received: latest.received, total: latest.total, ...event };
  }
  latest = event;
  lastUpdate = performance.now();
  $('active-stage').textContent = name;
  renderTransfer();
}

$('download-update').onclick = api.downloadUpdate;
api.updates(update => {
  $('update-notice').hidden = !update;
  if (!update) return;
  $('update-message').textContent = update.prerelease
    ? `Preview version v${update.version} is available` : `Vydra v${update.version} is available`;
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
  await showEstimate();
}

$('choose').onclick = async () => {
  const chosen = await api.choose();
  if (chosen) { folder.value = chosen; await showEstimate(); }
};
$('default-folder').onclick = () => {
  folder.value = settings.defaultFolder;
  showEstimate();
};
form.oninput = () => {
  clearTimeout(timer);
  timer = setTimeout(showEstimate, 300);
};
$('pause').onclick = async () => {
  $('pause').disabled = true;
  $('status').textContent = 'Pausing setup…';
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
  $('device-summary').textContent = selection.mode === 'cuda' ? 'Device · NVIDIA GPU' : 'Device · CPU';
  for (const [key, stage] of stages) {
    $('stage-size-' + key).textContent = formatDownload(selection.stages?.[key]);
    stage.removeAttribute('data-state');
    stage.removeAttribute('aria-label');
  }
  latest = undefined;
  showProgress({ stage: 'dependencies', phase: 'working', item: 'Checking disk space and device' });
  $('preparation-heading').focus();
  try {
    await api.install(selection.folder, selection.mode);
    $('status').textContent = 'Vydra is ready.';
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
  const target = folder.value.trim();
  const device = mode();
  const stages = currentEstimate?.folder === target && currentEstimate.mode === device ? currentEstimate.stages : undefined;
  selection = { folder: target, mode: device, stages };
  void install();
};

$('install').disabled = true;
initialize().catch(error => {
  $('status').textContent = error.message;
  $('configuration').hidden = true;
  $('preparation').hidden = false;
});
