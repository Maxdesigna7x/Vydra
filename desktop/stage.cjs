const { execFileSync } = require('node:child_process');
const { chmod, copyFile, mkdir, readFile, writeFile } = require('node:fs/promises');
const { createHash } = require('node:crypto');
const path = require('node:path');

const release = 'https://github.com/mamba-org/micromamba-releases/releases/download/2.10.0-0';
const builds = {
  linux: ['micromamba-linux-64', '701f39c06f8e6a670a0e186c8479b9e5c0502a2f0cda6cef65d83bdd2875e8bd'],
  win32: ['micromamba-win-64.exe', 'f8b4284bd4eb1134122eaf93b3ea6c7be567e596de5829e1a6f478e34e41974a'],
};

async function stage() {
  if (process.arch !== 'x64' || !builds[process.platform]) throw new Error('Use a Linux or Windows x64 build machine.');
  const source = path.resolve(__dirname, '..');
  const output = path.join(__dirname, 'resources');
  const tracked = execFileSync('git', ['ls-files', '-z', 'vydra_core'], { cwd: source, encoding: 'utf8' });
  for (const relative of tracked.split('\0').filter(Boolean)) {
    const destination = path.join(output, relative);
    await mkdir(path.dirname(destination), { recursive: true });
    await copyFile(path.join(source, relative), destination);
  }
  for (const name of ['requirements.txt', 'desktop_bootstrap.py']) {
    await copyFile(path.join(__dirname, name), path.join(output, name));
  }
  await copyFile(path.join(__dirname, 'third-party', 'micromamba-LICENSE.txt'), path.join(output, 'micromamba-LICENSE.txt'));
  await copyFile(path.join(__dirname, 'assets', 'vydra.png'), path.join(output, 'vydra.png'));
  const [asset, digest] = builds[process.platform];
  const target = path.join(output, process.platform === 'win32' ? 'micromamba.exe' : 'micromamba');
  const hash = bytes => createHash('sha256').update(bytes).digest('hex');
  let bytes = await readFile(target).catch(error => {
    if (error.code !== 'ENOENT') throw error;
    return Buffer.alloc(0);
  });
  if (hash(bytes) !== digest) {
    const response = await fetch(`${release}/${asset}`, { signal: AbortSignal.timeout(600_000) });
    if (!response.ok) throw new Error(`Micromamba download failed: HTTP ${response.status}`);
    bytes = Buffer.from(await response.arrayBuffer());
    if (hash(bytes) !== digest) throw new Error('Micromamba checksum mismatch.');
    await writeFile(target, bytes);
  }
  if (process.platform === 'linux') await chmod(target, 0o755);
}

stage().catch(error => { console.error(error); process.exitCode = 1; });
