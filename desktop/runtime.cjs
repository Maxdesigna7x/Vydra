const { spawn } = require('node:child_process');
const { appendFileSync } = require('node:fs');
const { access, mkdir, readFile, rename, statfs, writeFile, cp } = require('node:fs/promises');
const path = require('node:path');

const version = require('./package.json').version;
const windows = process.platform === 'win32';
const gib = 1024 ** 3;
const minimum = { cpu: 12 * gib, cuda: 22 * gib };

function layout(root, mode, resources) {
  const environment = path.join(root, 'env', `${version}-${mode}`);
  const cache = path.join(root, 'cache');
  const temp = path.join(root, 'tmp');
  const core = path.join(root, 'app', version, 'vydra_core');
  const artifacts = path.join(root, 'artifacts', 'artifacts-v1');
  return {
    environment, cache, temp, core, artifacts,
    tools: path.join(resources, windows ? 'micromamba.exe' : 'micromamba'),
    python: windows ? path.join(environment, 'python.exe') : path.join(environment, 'bin', 'python'),
    engine: path.join(resources, 'vydra_core'),
    state: path.join(root, 'runs'),
    marker: path.join(environment, '.vydra-ready'),
    env: {
      ...process.env,
      MAMBA_ROOT_PREFIX: path.join(cache, 'mamba'),
      PIP_CACHE_DIR: path.join(cache, 'pip'),
      HF_HOME: path.join(cache, 'huggingface'),
      HF_HUB_DOWNLOAD_TIMEOUT: '120',
      HF_HUB_ETAG_TIMEOUT: '60',
      HF_HUB_DISABLE_XET: '1',
      VYDRA_PROFILE_ROOT: path.join(root, 'profiles'),
      VYDRA_DESKTOP_ARTIFACTS: artifacts,
      VYDRA_PROSTT5_PATH: path.join(root, 'models', 'prostt5-07a6547'),
      VYDRA_DESKTOP_MODE: mode,
      TMPDIR: temp, TEMP: temp, TMP: temp,
      PYTHONNOUSERSITE: '1',
      PYTHONUTF8: '1',
      PYTHONUNBUFFERED: '1',
    },
  };
}

function packages(mode) {
  if (windows) return ['python=3.10', 'pip', 'numpy=1.26.4', 'faiss=1.14.3=*_cpu'];
  const common = ['python=3.10', 'pip', 'numpy=1.26.4'];
  return mode === 'cuda'
    ? [...common, 'pytorch-gpu=2.10.0=cuda129*', 'cuda-version=12.9', 'faiss=1.14.3=py310cuda129*']
    : [...common, 'pytorch-cpu=2.10.0', 'faiss=1.14.3=*_cpu'];
}

async function freeSpace(folder) {
  let ancestor = folder;
  while (true) {
    try {
      const { bsize, bavail } = await statfs(ancestor);
      return bsize * bavail;
    } catch (error) {
      if (error.code !== 'ENOENT' || ancestor === path.dirname(ancestor)) throw error;
      ancestor = path.dirname(ancestor);
    }
  }
}

async function writeAtomic(file, value) {
  const partial = `${file}.part`;
  await writeFile(partial, value);
  await rename(partial, file);
}

async function ready(paths) {
  try {
    if (await readFile(paths.marker, 'utf8') !== version) return false;
    await Promise.all([
      paths.python,
      path.join(paths.core, 'desktop_bootstrap.py'),
      path.join(paths.artifacts, 'Struct_prototype_bank.pt'),
      path.join(paths.artifacts, 'Non_Struct_prototype_bank.pt'),
      path.join(paths.env.VYDRA_PROSTT5_PATH, '.vydra-model-ready'),
      path.join(paths.env.VYDRA_PROSTT5_PATH, 'pytorch_model.bin'),
    ].map(file => access(file)));
    return true;
  } catch {
    return false;
  }
}

function run(command, args, options, log, signal) {
  signal?.throwIfAborted();
  const child = spawn(command, args, {
    ...options, windowsHide: true, detached: !windows, stdio: ['ignore', 'pipe', 'pipe'],
  });
  function stop() {
    if (!child.pid) return;
    if (windows) {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { windowsHide: true, stdio: 'ignore' });
      killer.once('error', () => child.kill());
      return;
    }
    try { process.kill(-child.pid, 'SIGTERM'); }
    catch (error) { if (error.code !== 'ESRCH') child.kill(); }
  }
  signal?.addEventListener('abort', stop, { once: true });
  for (const pipe of [child.stdout, child.stderr]) pipe.on('data', bytes => log(bytes.toString()));
  return new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('close', code => {
      signal?.removeEventListener('abort', stop);
      if (signal?.aborted) reject(signal.reason);
      else if (code === 0) resolve();
      else reject(new Error(`El proceso terminó con código ${code}. Consulta el registro de instalación.`));
    });
  });
}

function pythonProcess(paths, args) {
  if (!windows) {
    return { command: paths.tools, args: ['run', '-p', paths.environment, paths.python, ...args], env: paths.env };
  }
  // Micromamba's Windows batch wrapper splits some paths containing spaces.
  // Start the managed interpreter directly with the environment's DLL paths.
  const env = { ...paths.env, CONDA_PREFIX: paths.environment };
  const originalPath = Object.keys(env).find(key => key.toLowerCase() === 'path');
  const directories = ['', 'Library/mingw-w64/bin', 'Library/usr/bin', 'Library/bin', 'Scripts', 'bin'];
  env[originalPath || 'PATH'] = [
    ...directories.map(directory => path.join(paths.environment, directory)), env[originalPath] || '',
  ].join(path.delimiter);
  return { command: paths.python, args, env };
}

async function prepare(root, mode, resources, log, { dependenciesOnly = false, signal } = {}) {
  const paths = layout(root, mode, resources);
  if (!dependenciesOnly && await ready(paths)) return paths;
  if (!windows && mode === 'cuda' && !dependenciesOnly) {
    await run('nvidia-smi', ['--query-gpu=name,driver_version', '--format=csv,noheader'], {}, log, signal);
  }
  const available = await freeSpace(root);
  if (available < gib) throw new Error('La unidad necesita al menos 1 GiB libre para continuar.');
  const journal = path.join(root, 'app', version, `setup-${mode}.json`);
  const previous = await readFile(journal, 'utf8').then(JSON.parse).catch(() => ({}));
  if (!dependenciesOnly && !previous.phase && available < minimum[mode]) {
    throw new Error(`Espacio insuficiente. Se estiman ${minimum[mode] / gib} GiB para preparar este modo.`);
  }
  for (const folder of [paths.temp, paths.cache, paths.state, path.dirname(paths.core)]) {
    await mkdir(folder, { recursive: true });
  }
  const logfile = path.join(root, 'setup.log');
  const progress = message => {
    try { appendFileSync(logfile, message, 'utf8'); }
    catch (error) { console.error('Could not write setup.log', error); }
    log(message);
  };
  const python = args => {
    const launch = pythonProcess(paths, args);
    return run(launch.command, launch.args, { env: launch.env }, progress, signal);
  };
  const hasPython = await access(paths.python).then(() => true).catch(() => false);
  if (!hasPython || !previous.phase || previous.phase === 'installing') {
    await writeAtomic(journal, JSON.stringify({ phase: 'installing' }));
    progress('Preparando el entorno de Vydra…\n');
    const solveEnv = mode === 'cuda' && !windows && dependenciesOnly
      ? { ...paths.env, CONDA_OVERRIDE_CUDA: '12.9' } : paths.env;
    const exists = await access(path.join(paths.environment, 'conda-meta', 'history')).then(() => true).catch(() => false);
    await run(paths.tools, ['--no-rc', exists ? 'install' : 'create', '-y', '--always-copy', '-p', paths.environment,
      '-c', 'conda-forge', '--override-channels', ...packages(mode)], { env: solveEnv }, progress, signal);
    if (windows) {
      const index = mode === 'cuda' ? 'cu126' : 'cpu';
      await python(['-m', 'pip', 'install', '--retries', '6', '--timeout', '120',
        '--index-url', `https://download.pytorch.org/whl/${index}`, 'torch==2.10.0']);
    }
    await python(['-m', 'pip', 'install', '--retries', '6', '--timeout', '120',
      '-r', path.join(resources, 'requirements.txt')]);
    await writeAtomic(journal, JSON.stringify({ phase: 'dependencies' }));
  }
  await cp(paths.engine, paths.core, { recursive: true });
  await cp(path.join(paths.engine, 'artifacts'), paths.artifacts, { recursive: true });
  const bootstrap = path.join(paths.core, 'desktop_bootstrap.py');
  await cp(path.join(resources, 'desktop_bootstrap.py'), bootstrap);
  await python([bootstrap, dependenciesOnly ? 'imports' : 'prepare', mode]);
  if (!dependenciesOnly) {
    await writeAtomic(paths.marker, version);
    await writeAtomic(journal, JSON.stringify({ phase: 'ready' }));
  }
  return paths;
}

module.exports = { layout, minimum, ready, prepare, pythonProcess, writeAtomic, freeSpace };
