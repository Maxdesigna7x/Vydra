'use strict';

window.createVydraDesktopRuns = ({ selectRun, showReport }) => {
  const $ = id => document.getElementById(id);
  const modelNames = new Map();
  const statuses = {
    queued: 'En cola', starting: 'Iniciando', running: 'En curso', cancelling: 'Cancelando',
    complete: 'Completada', completed: 'Completada', failed: 'Fallida', cancelled: 'Cancelada',
    interrupted: 'Interrumpida',
  };
  const stages = {
    'Preparing input': 'Preparando entrada', 'Locating protein model': 'Buscando modelo',
    'Loading models and generating embeddings': 'Cargando modelo',
    'Generating embeddings': 'Generando embeddings', 'Classifying proteins': 'Clasificando proteínas',
    'Writing results': 'Guardando resultados', 'Generating report': 'Generando informe',
  };
  const active = run => ['starting', 'running', 'cancelling'].includes(run.status);
  const completed = run => ['complete', 'completed'].includes(run.status);
  const name = path => path?.split(/[\\/]/).filter(Boolean).at(-1) || '—';
  const model = run => modelNames.get(run.model || 'prostt5') || run.model || 'ProstT5';
  const method = run => (run.classifier || 'mlp').toUpperCase();
  const date = run => run.created_at ? new Date(run.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }) : '';
  const device = run => ({auto: 'Automático', cuda: 'NVIDIA', cpu: 'CPU'})[run.device] || '—';
  const details = $('desktop-run-details');
  const list = $('desktop-run-list');
  const task = $('desktop-new-task');
  let lastRender;

  function describe(run, position) {
    if (position) return `En cola · ${position}`;
    const status = statuses[run.status] || run.status;
    if (run.status !== 'running') return status;
    const stage = stages[run.stage] || run.stage;
    const chunks = run.stage === 'Generating embeddings' && Number.isInteger(run.chunks_total);
    const progress = chunks ? `${run.chunks_done || 0}/${run.chunks_total}`
      : Number.isInteger(run.processed) && run.total ? `${run.processed}/${run.total}` : '';
    return [status, stage, progress].filter(Boolean).join(' · ');
  }

  function card(row) {
    const { run, title, state, summary, created } = row;
    const item = document.createElement('li');
    item.className = 'desktop-run';
    item.dataset.status = run.status;
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'desktop-run-summary';
    open.dataset.action = 'details';
    open.dataset.run = run.id;
    open.title = [run.input, run.output, summary, state].filter(Boolean).join('\n');
    const titleText = document.createElement('strong');
    titleText.textContent = title;
    const stateText = document.createElement('span');
    stateText.className = 'desktop-run-status';
    stateText.textContent = state;
    const meta = document.createElement('span');
    meta.className = 'desktop-run-meta';
    meta.textContent = summary;
    const timestamp = document.createElement('time');
    timestamp.className = 'desktop-run-time';
    timestamp.dateTime = run.created_at || '';
    timestamp.textContent = created;
    open.append(titleText, stateText, meta, timestamp);
    open.onclick = () => {
      selectRun(run.id);
      details.showModal();
    };
    item.append(open);

    if (completed(run) && run.report_path) {
      const report = document.createElement('button');
      report.type = 'button';
      report.className = 'button quiet desktop-open-report';
      report.textContent = 'Informe';
      report.dataset.action = 'report';
      report.dataset.run = run.id;
      report.onclick = () => showReport(run);
      item.append(report);
    }
    return item;
  }

  function render(runs) {
    const queued = runs.filter(run => run.status === 'queued').reverse();
    const ordered = [...runs.filter(active), ...queued,
      ...runs.filter(run => !active(run) && run.status !== 'queued')];
    const positions = new Map(queued.map((run, index) => [run.id, index + 1]));
    const rows = ordered.map(run => ({
      run, title: name(run.input), state: describe(run, positions.get(run.id)), created: date(run),
      summary: `${model(run)} · M4: ${method(run)} · ${device(run)} · Salida: ${name(run.output)}`,
    }));
    const signature = JSON.stringify(rows.map(({run, title, state, summary, created}) =>
      [run.id, run.input, run.output, run.status, run.report_path, title, state, summary, created]));
    if (signature === lastRender) return;
    lastRender = signature;
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset : null;
    $('desktop-empty').hidden = rows.length > 0;
    list.replaceChildren(...rows.map(card));
    if (focused) {
      [...list.querySelectorAll('[data-run]')].find(button =>
        button.dataset.run === focused.run && button.dataset.action === focused.action)?.focus({ preventScroll: true });
    }
  }

  function showDetails(run) {
    $('desktop-run-title').textContent = name(run.input);
    $('desktop-run-parameters').textContent = `${model(run)} · M4: ${method(run)} · ${device(run)}`;
    $('desktop-run-input').textContent = run.input || '—';
    $('desktop-run-date').textContent = run.created_at ? new Date(run.created_at).toLocaleString() : '';
  }

  function mount(config) {
    for (const entry of config.models) modelNames.set(entry.id, entry.name);
    document.documentElement.classList.add('desktop-runs');
    task.append($('run-form'));
    details.append($('status-section'));
    $('desktop-new').onclick = () => {
      $('form-error').textContent = '';
      task.showModal();
      $('source').focus();
    };
    $('desktop-task-close').onclick = () => task.close();
    $('desktop-details-close').onclick = () => details.close();
  }

  return { mount, render, showDetails, closeTask: () => task.close() };
};
