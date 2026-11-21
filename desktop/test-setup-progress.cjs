const test = require('node:test');
const assert = require('node:assert/strict');
const { packageArchives, pipProgress, progressReporter, watchArchives } = require('./setup-progress.cjs');
const { mkdtemp, rm, writeFile } = require('node:fs/promises');
const { tmpdir } = require('node:os');
const path = require('node:path');

test('speed excludes previously saved bytes and resets between downloads', () => {
  const events = [];
  const baseline = { stage: 'models', phase: 'transfer', item: 'ProstT5', total: 500 };
  let now = 1000;
  const report = progressReporter(event => events.push(event), () => now);
  report({ ...baseline, received: 100 });
  now += 2000;
  report({ ...baseline, received: 200 });
  assert.equal(events[0].rate, null);
  assert.equal(events[1].rate, 50);
  assert.equal(events[1].eta, 6);
  report({ ...baseline, received: 0 });
  assert.equal(events.at(-1).rate, null);
  now += 1000;
  report({ stage: 'data', phase: 'transfer', received: 20, total: 50 });
  assert.equal(events.at(-1).rate, null);
});

test('pip distinguishes current wheel byte counts and package installation', () => {
  const events = [];
  const report = pipProgress(event => events.push(event));
  report('Downloading torch-2.10.whl (12.3 MB)');
  report('Progress 20 of 100');
  report('Installing collected packages: torch');
  assert.deepEqual(events[1], { phase: 'transfer', scope: 'file', item: 'torch-2.10.whl', received: 20, total: 100 });
  assert.equal(events[2].phase, 'working');
});

test('conda plan measures only downloaded archives in the managed cache', async () => {
  const filename = 'python-3.10.20-abc.conda';
  const plan = { actions: {
    FETCH: [{ url: 'https://conda.anaconda.org/conda-forge/linux-64/' + filename, size: 100 }],
    LINK: [{ url: 'https://conda.anaconda.org/conda-forge/linux-64/other.conda', size: 10 }],
  } };
  const archives = packageArchives(plan, 'isolated-cache');
  assert.deepEqual(archives, [{ file: path.join('isolated-cache', 'pkgs', 'https', 'conda.anaconda.org', 'conda-forge', 'linux-64', filename), total: 100 }]);
  const directory = await mkdtemp(path.join(tmpdir(), 'vydra-telemetry-'));
  try {
    const target = path.join(directory, filename);
    await writeFile(target + '.part', Buffer.alloc(40));
    const events = [];
    const stop = await watchArchives([{ file: target, total: 100 }], event => events.push(event));
    stop();
    assert.equal(events[0].received, 40);
    assert.equal(events[0].total, 100);
  } finally {
    await rm(directory, { recursive: true });
  }
});
