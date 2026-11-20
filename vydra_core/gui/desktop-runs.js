'use strict';

window.createVydraDesktopRuns = ({ selectRun, showReport }) => {
  const $ = id => document.getElementById(id);
  const modelNames = new Map();
  const statuses = {
    queued: 'Queued', starting: 'Starting', running: 'Running', cancelling: 'Cancelling',
    complete: 'Completed', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled',
    interrupted: 'Interrupted',
  };
  const active = run => ['starting', 'running', 'cancelling'].includes(run.status);
  const completed = run => ['complete', 'completed'].includes(run.status);
  const name = path => path?.split(/[\\/]/).filter(Boolean).at(-1) || '—';
  const model = run => modelNames.get(run.model || 'prostt5') || run.model || 'ProstT5';
  const method = run => run.classifier === 'both' ? 'MLP + FAISS' : (run.classifier || 'mlp').toUpperCase();
  function comparison(run) {
    const counts = run.result?.overall;
    return counts?.m4_compared ? ` · ${counts.m4_agree}/${counts.m4_compared} match` : '';
  }
  const date = run => run.created_at ? new Date(run.created_at).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }) : '';
  const device = run => ({auto: 'Automatic', cuda: 'NVIDIA', cpu: 'CPU'})[run.device] || '—';
  const integers = new Intl.NumberFormat('en-US');
  const rates = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
  const duration = seconds => {
    const total = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor(total / 60) % 60;
    if (hours) return `${hours}h ${minutes}m`;
    if (minutes) return `${minutes}m ${String(total % 60).padStart(2, '0')}s`;
    return `${total}s`;
  };
  const count = (done, total) => `${integers.format(Math.max(0, done || 0))}/${integers.format(total)}`;
  const details = $('desktop-run-details');
  const list = $('desktop-run-list');
  const task = $('desktop-new-task');
  let lastRender;

  function describe(run, position) {
    if (position) return `Queued · ${position}`;
    const status = statuses[run.status] || run.status;
    if (run.status !== 'running') return status;
    return [status, run.stage].filter(Boolean).join(' · ');
  }

  function liveProgress(run, now) {
    if (!active(run)) return null;
    const embedding = run.stage === 'Generating embeddings';
    const classification = run.stage === 'Classifying proteins';
    const sequences = Number.isInteger(run.total) && run.total > 0;
    const chunks = Number.isInteger(run.chunks_total) && run.chunks_total > 0;
    const total = embedding && chunks ? run.chunks_total : classification && sequences ? run.total : null;
    const done = total === null ? null : Math.min(total, Math.max(0, (embedding ? run.chunks_done : run.processed) || 0));
    const fresh = !run.last_progress_at || now - run.last_progress_at < 300;
    const rate = fresh && Number.isFinite(run.phase_rate) && run.phase_rate > 0 ? run.phase_rate : null;
    const remaining = rate && total !== null ? (total - done) / rate : null;
    const elapsed = Number.isFinite(run.started_timestamp) ? Math.max(0, now - run.started_timestamp)
      : run.elapsed_seconds || 0;
    const eta = remaining === null
      ? (embedding || classification ? 'Stage ETA: —' : '')
      : `Stage ETA: ${remaining > 0 ? '~' : ''}${duration(Math.ceil(remaining))}`;
    const metrics = [
      sequences ? `Sequences ${count(run.processed, run.total)}` : '',
      chunks ? `Chunks ${count(run.chunks_done, run.chunks_total)}` : '',
      embedding ? `Batch ${integers.format(run.batch_size_active || 0)}` : '',
      embedding ? `${rate === null ? '—' : rate < 0.01 ? '<0.01' : rates.format(rate)} chunks/s` : '',
    ].filter(Boolean).join(' · ');
    return { total, done, time: [`Elapsed ${duration(elapsed)}`, eta].filter(Boolean).join(' · '), metrics };
  }

  function updateLiveCard(item, row) {
    const { run, state, summary, live } = row;
    const open = item.querySelector('.desktop-run-summary');
    open.title = [run.input, run.output, summary, state, live.time, live.metrics].filter(Boolean).join('\n');
    item.querySelector('.desktop-run-status').textContent = `${state} · ${live.time}`;
    item.querySelector('.desktop-run-metrics').textContent = live.metrics;
    const progress = item.querySelector('progress');
    if (live.total === null) progress.removeAttribute('value');
    else {
      progress.max = live.total;
      progress.value = live.done;
    }
  }

  function card(row) {
    const { run, title, state, summary, created, live } = row;
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
    const extra = document.createElement(live ? 'span' : 'time');
    extra.className = live ? 'desktop-run-metrics' : 'desktop-run-time';
    if (!live) extra.dateTime = run.created_at || '';
    if (!live) extra.textContent = created;
    open.append(titleText, stateText, meta, extra);
    open.onclick = () => {
      selectRun(run.id);
      details.showModal();
    };
    item.append(open);
    if (live) {
      const progress = document.createElement('progress');
      progress.className = 'desktop-run-progress';
      progress.setAttribute('aria-label', 'Stage progress');
      item.append(progress);
      updateLiveCard(item, row);
    }

    if (completed(run) && run.report_path) {
      const report = document.createElement('button');
      report.type = 'button';
      report.className = 'button quiet desktop-open-report';
      report.textContent = 'Report';
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
    const now = Date.now() / 1000;
    const rows = ordered.map(run => ({
      run, title: name(run.input), state: describe(run, positions.get(run.id)), created: date(run), live: liveProgress(run, now),
      summary: `${model(run)} · M4: ${method(run)}${comparison(run)} · ${device(run)} · Output: ${name(run.output)}`,
    }));
    const signature = JSON.stringify(rows.map(({run, title, state, summary, created, live}) =>
      [run.id, run.input, run.output, run.status, run.report_path, title, live ? null : state, summary, created]));
    if (signature === lastRender) {
      rows.forEach((row, index) => { if (row.live) updateLiveCard(list.children[index], row); });
      return;
    }
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
    $('desktop-run-parameters').textContent = `${model(run)} · M4: ${method(run)}${comparison(run)} · ${device(run)}`;
    $('desktop-run-input').textContent = run.input || '—';
    $('desktop-run-date').textContent = run.created_at ? new Date(run.created_at).toLocaleString('en-US') : '';
  }

  function mount(config) {
    for (const entry of config.models) modelNames.set(entry.id, entry.name);
    document.documentElement.classList.add('desktop-runs');
    const brand = document.querySelector('main > header > div:first-child');
    brand.classList.add('desktop-brand');
    const icon = document.createElement('img');
    icon.src = '/vydra.png';
    icon.alt = '';
    icon.addEventListener('error', () => icon.remove(), { once: true });
    brand.prepend(icon);
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
