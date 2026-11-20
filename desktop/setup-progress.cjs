const { stat } = require('node:fs/promises');
const path = require('node:path');

function progressReporter(send, now = () => performance.now()) {
  let key;
  let samples = [];
  return event => {
    if (event.phase !== 'transfer' || !Number.isFinite(event.received)) {
      key = undefined;
      samples = [];
      send(event);
      return;
    }
    const time = now();
    const stream = [event.stage, event.scope, event.scope === 'file' ? event.item : '', event.total].join('|');
    if (stream !== key || event.received < (samples.at(-1)?.bytes ?? 0)) samples = [];
    key = stream;
    samples = samples.filter(sample => time - sample.time <= 9000);
    samples.push({ time, bytes: event.received });
    const first = samples[0];
    const elapsed = (time - first.time) / 1000;
    const rate = elapsed >= .5 ? (event.received - first.bytes) / elapsed : 0;
    send({
      ...event,
      rate: rate > 0 ? rate : null,
      eta: rate > 0 && event.total > event.received ? (event.total - event.received) / rate : null,
    });
  };
}

function packageArchives(plan, cache) {
  return (plan.actions?.FETCH || []).flatMap(entry => {
    if (!Number.isSafeInteger(entry.size) || entry.size <= 0) return [];
    const url = new URL(entry.url);
    if (url.origin !== 'https://conda.anaconda.org' || !/^\/conda-forge\/[\w-]+\/[\w.+-]+\.(conda|tar\.bz2)$/u.test(url.pathname)) return [];
    return [{ file: path.join(cache, 'pkgs', 'https', url.hostname, ...url.pathname.split('/').filter(Boolean)), total: entry.size }];
  });
}

async function watchArchives(archives, emit) {
  const total = archives.reduce((sum, archive) => sum + archive.total, 0);
  let stopped = false;
  let sampling = false;
  let previous = -1;
  async function measure() {
    if (stopped || sampling) return;
    sampling = true;
    try {
      const sizes = await Promise.all(archives.map(async archive => {
        const exact = await stat(archive.file).catch(() => null);
        if (exact) return Math.min(archive.total, exact.size);
        const inProgress = await stat(archive.file + '.part').catch(() => null);
        return Math.min(archive.total, inProgress?.size ?? 0);
      }));
      if (stopped) return;
      const received = sizes.reduce((sum, size) => sum + size, 0);
      if (received !== previous) {
        previous = received;
        emit({ phase: received === total ? 'working' : 'transfer',
          item: received === total ? 'Instalando paquetes del entorno' : 'Paquetes de conda-forge', total, received });
      }
    } finally {
      sampling = false;
    }
  }
  if (!total) return () => {};
  await measure();
  const timer = setInterval(() => void measure(), 850);
  timer.unref();
  return () => { stopped = true; clearInterval(timer); };
}

function pipProgress(emit) {
  let item = 'Paquete de Python';
  return line => {
    const meter = /^Progress (\d+) of (\d+)$/u.exec(line.trim());
    if (meter) {
      const received = Number(meter[1]);
      const total = Number(meter[2]) || null;
      emit({ phase: 'transfer', scope: 'file', item, received, total });
      return;
    }
    const downloading = /^\s*Downloading (\S+)/u.exec(line);
    if (downloading) {
      item = downloading[1].replace(/\.whl\.metadata$/u, '');
      emit({ phase: 'working', item });
    } else if (/^Installing collected packages:/u.test(line.trim())) {
      emit({ phase: 'working', item: 'Instalando bibliotecas de Python' });
    }
  };
}

module.exports = { progressReporter, packageArchives, watchArchives, pipProgress };
