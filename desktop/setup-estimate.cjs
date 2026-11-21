const { createHash } = require('node:crypto');
const { access, readFile, stat } = require('node:fs/promises');
const path = require('node:path');
const assets = require('./setup-assets.json');

// Approximate compressed environment sizes. Package resolution can change the total.
const dependencyDownload = {
  linux: { cpu: 650e6, cuda: 4.3e9 },
  win32: { cpu: 450e6, cuda: 3.7e9 },
};
const zstandardDownload = 6e6;

const exists = file => access(file).then(() => true, () => false);

async function missingBytes(file, expected, partial) {
  const size = async name => (await stat(name).catch(error => {
    if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return null;
    throw error;
  }))?.size ?? 0;
  if (await size(file) === expected) return 0;
  const saved = await size(partial);
  return saved <= expected ? expected - saved : expected;
}

async function downloadEstimate(paths, mode, platform = process.platform) {
  const profile = path.join(paths.env.VYDRA_PROFILE_ROOT, 'prostt5');
  const model = paths.env.VYDRA_PROSTT5_PATH;
  const downloads = path.join(paths.cache, 'profile-downloads');
  const [environmentReady, m4Ready, zstandardReady] = await Promise.all([
    Promise.all([exists(paths.python), readFile(paths.journal, 'utf8').then(JSON.parse).catch(() => ({}))])
      .then(([python, state]) => python && ['dependencies', 'ready'].includes(state.phase)),
    Promise.all(['m4_manifest.json', 'm4_vectors.npy', 'm4_targets.npy', 'm4_classes.json']
      .map(name => exists(path.join(profile, name)))).then(files => files.every(Boolean)),
    exists(path.join(paths.environment, ...(platform === 'win32' ? ['Lib'] : ['lib', 'python3.10']), 'site-packages', 'zstandard')),
  ]);

  const dependencies = (environmentReady ? 0 : dependencyDownload[platform === 'win32' ? 'win32' : 'linux'][mode])
    + (m4Ready || zstandardReady ? 0 : zstandardDownload);
  const modelFiles = Object.entries(assets.prostt5).map(([name, [bytes, digest]]) => {
    const fingerprint = createHash('sha1').update(name).digest('base64').replace(/\+/gu, '-').replace(/\//gu, '_');
    const partial = path.join(model, '.cache', 'huggingface', 'download', `${fingerprint}.${digest}.incomplete`);
    return missingBytes(path.join(model, name), bytes, partial);
  });
  const banks = Object.entries(assets.referenceBanks).map(([name, bytes]) => {
    const file = path.join(paths.artifacts, name);
    return missingBytes(file, bytes, file + '.part');
  });
  if (!m4Ready) {
    assets.m4Parts.forEach(([bytes], index) => {
      const file = path.join(downloads, `prostt5.tar.zst.part-${String(index).padStart(2,'0')}`);
      banks.push(missingBytes(file, bytes, file + '.part'));
    });
  }
  const sum = promises => Promise.all(promises).then(sizes => sizes.reduce((a, b) => a + b, 0));
  const [models, data] = await Promise.all([sum(modelFiles), sum(banks)]);
  return { dependencies, models, data };
}

module.exports = { downloadEstimate };
