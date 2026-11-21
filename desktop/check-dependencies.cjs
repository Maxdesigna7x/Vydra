const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const { prepare, pythonProcess } = require('./runtime.cjs');
const path = require('node:path');

async function checkService(paths) {
  const launch = pythonProcess(paths, [path.join(paths.core, 'desktop_bootstrap.py'), 'serve', paths.state]);
  const child = spawn(launch.command, launch.args, { env: launch.env, stdio: ['pipe', 'pipe', 'inherit'] });
  child.stdin.on('error', () => {});
  const lines = createInterface({ input: child.stdout });
  const closed = new Promise(resolve => child.once('close', resolve));
  try {
    const url = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Local interface startup timed out.')), 30_000);
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('close', code => { clearTimeout(timer); reject(new Error(`Local interface exited: ${code}`)); });
      lines.on('line', line => {
        const match = /^VYDRA_READY (http:\/\/127\.0\.0\.1:[0-9]+\/)$/u.exec(line);
        if (match) { clearTimeout(timer); resolve(match[1]); }
      });
    });
    const response = await fetch(new URL('/api/config', url), { signal: AbortSignal.timeout(10_000) });
    const config = await response.json();
    if (!response.ok || config.desktop?.mode !== process.argv[3]) throw new Error('Unexpected local configuration.');
    const pages = await Promise.all(['/', '/run-queue.js', '/run-queue.css'].map(route =>
      fetch(new URL(route, url), { signal: AbortSignal.timeout(10_000) })));
    if (pages.some(page => !page.ok) || !(await pages[0].text()).includes('id="run-queue"')) {
      throw new Error('The local backend did not serve the shared run queue.');
    }
    console.log('Local Vydra backend served the shared run queue with the selected device mode.');
  } finally {
    child.stdin.end();
    const timer = setTimeout(() => child.kill(), 5_000);
    await closed;
    clearTimeout(timer);
  }
}

const [root, mode] = process.argv.slice(2);
if (!root || !['cuda', 'cpu'].includes(mode)) {
  throw new Error('Usage: node check-dependencies.cjs DATA_DIR cpu|cuda');
}
prepare(path.resolve(root), mode, path.join(__dirname, 'resources'), text => process.stdout.write(text),
  { dependenciesOnly: true }).then(checkService).catch(error => { console.error(error); process.exitCode = 1; });
